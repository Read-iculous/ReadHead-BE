"""Real AnyIO cancellation scopes exercise mocked provider resource lifetimes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import anyio
import pytest
from starlette.responses import StreamingResponse

from app.core.ai import claude_adapter, gemini_adapter, openai_adapter
from app.core.ai.base import BaseAIProvider
from app.core.ai.cleanup import shielded_cleanup
from app.core.auth import Principal
from app.services import ai_service


class FakeResource:
    """Resource whose asynchronous cleanup cannot finish in a cancelled scope."""

    def __init__(self) -> None:
        self.closed = False
        self.entered = False
        self.choices = [SimpleNamespace(delta=SimpleNamespace(content="hello"))]
        self.sent = False
        self.text_stream = self

    async def __aenter__(self):
        self.entered = True
        return self

    async def __aexit__(self, *args):
        await self.close()

    async def close(self) -> None:
        await anyio.sleep(0.001)
        self.closed = True

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.sent:
            self.sent = True
            return self
        await anyio.sleep_forever()

    async def aiter_lines(self):
        yield 'data: {"candidates":[{"content":{"parts":[{"text":"hello"}]}}]}'
        await anyio.sleep_forever()

    def raise_for_status(self) -> None:
        pass


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["openai", "claude", "gemini"])
@pytest.mark.parametrize("cancel_during_read", [False, True])
async def test_provider_closes_stream_and_client_under_anyio_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    provider_name: str,
    cancel_during_read: bool,
) -> None:
    client, stream = FakeResource(), FakeResource()
    if provider_name == "openai":

        async def create(**kwargs):
            return stream

        client.chat = SimpleNamespace(completions=SimpleNamespace(create=create))
        monkeypatch.setattr(
            openai_adapter.openai, "AsyncOpenAI", lambda **kwargs: client
        )
        provider = openai_adapter.OpenAIProvider("mock-key")
    elif provider_name == "claude":
        client.messages = SimpleNamespace(stream=lambda **kwargs: stream)

        # Claude yields strings from text_stream, whereas OpenAI yields SDK chunks.
        async def text_stream():
            yield "hello"
            await anyio.sleep_forever()

        stream.text_stream = text_stream()
        monkeypatch.setattr(
            claude_adapter.anthropic, "AsyncAnthropic", lambda **kwargs: client
        )
        provider = claude_adapter.ClaudeProvider("mock-key")
    else:
        client.stream = lambda *args, **kwargs: stream
        monkeypatch.setattr(
            gemini_adapter.httpx, "AsyncClient", lambda **kwargs: client
        )
        provider = gemini_adapter.GeminiProvider("mock-key")
    received = []
    ready = anyio.Event()

    if cancel_during_read:

        async def consume():
            async for token in provider.generate_stream(
                [{"role": "user", "content": "source"}], "test-model"
            ):
                received.append(token)
                ready.set()

        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await ready.wait()
            await anyio.sleep(0)
            group.cancel_scope.cancel()
    else:
        generator = provider.generate_stream(
            [{"role": "user", "content": "source"}], "test-model"
        )
        with anyio.CancelScope() as scope:
            received.append(await generator.__anext__())
            scope.cancel()
            await generator.aclose()

    assert received == ["hello"]
    assert stream.closed, "Upstream resource cleanup did not finish"
    assert client.closed, "Provider client cleanup did not finish"


@pytest.mark.asyncio
@pytest.mark.parametrize("private", [False, True])
@pytest.mark.parametrize("asgi_disconnect", [False, True])
async def test_sse_disconnect_finishes_upstream_lease_and_partial_write_cleanup(
    monkeypatch: pytest.MonkeyPatch,
    private: bool,
    asgi_disconnect: bool,
) -> None:
    resource, lease = FakeResource(), FakeResource()

    class Provider(BaseAIProvider):
        """Offline provider that stalls after the first token."""

        async def generate_stream(self, messages, model):
            try:
                yield "hello"
                await anyio.sleep_forever()
            finally:
                await shielded_cleanup(resource.close)

        async def validate_key(self):
            return True

    provider = Provider("mock-key")
    prepared = ai_service.PreparedStream(
        uuid4(),
        uuid4(),
        private,
        "openai",
        "test-model",
        provider,
        [{"role": "user", "content": "source"}],
        {"p-1": "source"},
        lease,
    )
    principal = Principal(uuid4(), uuid4(), "user")
    persisted = []

    async def persist(*args):
        await anyio.sleep(0.001)
        persisted.append(args)

    monkeypatch.setattr(ai_service, "persist", persist)
    monkeypatch.setattr(ai_service.redis, "metric", AsyncMock())
    monkeypatch.setattr(ai_service.redis.client, "exists", AsyncMock(return_value=0))
    received = []
    ready = anyio.Event()

    async def consume():
        async for event in ai_service.generate(principal, prepared):
            received.append(event)
            if event.startswith("event: token"):
                ready.set()

    if asgi_disconnect:

        async def receive():
            await ready.wait()
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body":
                body = message.get("body", b"").decode()
                received.append(body)
                if body.startswith("event: token"):
                    ready.set()

        response = StreamingResponse(ai_service.generate(principal, prepared))
        with anyio.fail_after(3):
            await response(
                {"type": "http", "asgi": {"spec_version": "2.3"}}, receive, send
            )
    else:
        async with anyio.create_task_group() as group:
            group.start_soon(consume)
            await ready.wait()
            await anyio.sleep(0)
            group.cancel_scope.cancel()

    assert resource.closed
    assert lease.closed
    assert provider.key == ""
    assert prepared.messages == [] and prepared.sources == {}
    assert not any(event.startswith("event: done") for event in received)
    assert len(persisted) == (0 if private else 1)
    if not private:
        assert persisted[0][2] == "hello"
        assert persisted[0][3]["grounding_notes"] == "interrupted_by_client"
