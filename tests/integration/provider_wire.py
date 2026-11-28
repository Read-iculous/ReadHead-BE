"""Explicit synthetic upstream HTTP fixtures, never real AI or OAuth evidence."""

import asyncio
import importlib
import json
import time
from collections.abc import AsyncIterator
from types import SimpleNamespace
from uuid import uuid4

import httpx


class WireStream(httpx.AsyncByteStream):
    """Yield actual protocol bytes to the installed provider SDK parsers."""

    def __init__(self, events: list[str], wire: "ProviderWire") -> None:
        self.events, self.wire = events, wire

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for index, event in enumerate(self.events):
            if self.wire.before_chunk:
                await self.wire.before_chunk(index)
            await asyncio.sleep(0)
            yield event.encode()

    async def aclose(self) -> None:
        self.wire.closed += 1


class ProviderWire:
    """Control protocol responses while keeping SDK, application and storage real."""

    def __init__(self) -> None:
        self.output = "A supported explanation [p-1]."
        self.status = 200
        self.timeout = False
        self.calls: list[dict] = []
        self.closed = 0
        self.finish_reason = "stop"
        self.before_chunk = None
        self.google = dict(
            aud="google-test-client",
            iss="https://accounts.google.com",
            exp=str(int(time.time()) + 3600),
            email_verified="true",
            sub=uuid4().hex,
            email=f"wire-google-{uuid4().hex}@example.com",
            name="Google test reader",
            picture=None,
        )
        self.github_profile = dict(
            id=uuid4().int % (10**12) + 1, name="GitHub test reader", avatar_url=None
        )
        self.github_emails = [
            dict(
                email=f"wire-github-{uuid4().hex}@example.com",
                primary=True,
                verified=True,
            )
        ]
        self.github_token = {"access_token": "synthetic-github-test-token"}
        self.transport = httpx.MockTransport(self.handle)

    def client(self, **kwargs) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=self.transport, **kwargs)

    def handle(self, request: httpx.Request) -> httpx.Response:
        host, path = request.url.host, request.url.path
        body = json.loads(request.content) if request.content else None
        self.calls.append(dict(host=host, path=path, method=request.method, body=body))
        if host == "oauth2.googleapis.com":
            return httpx.Response(200, json=self.google)
        if host == "github.com":
            return httpx.Response(200, json=self.github_token)
        if host == "api.github.com":
            return httpx.Response(
                200,
                json=(
                    self.github_emails
                    if path.endswith("emails")
                    else self.github_profile
                ),
            )
        if host not in {
            "api.openai.com",
            "api.anthropic.com",
            "generativelanguage.googleapis.com",
        }:
            raise AssertionError(
                "Unexpected upstream host; external networking is forbidden in this fixture"
            )
        key = (
            request.headers.get("authorization", "")
            + request.headers.get("x-api-key", "")
            + request.headers.get("x-goog-api-key", "")
        )
        status = 401 if "rejected-test-key" in key else self.status
        if self.timeout:
            raise httpx.ReadTimeout("synthetic upstream timeout", request=request)
        if status != 200:
            return httpx.Response(
                status,
                json={
                    "error": {
                        "message": "Synthetic upstream error",
                        "type": "invalid_request_error",
                    }
                },
            )
        if request.method == "GET":
            if host == "api.openai.com":
                return httpx.Response(
                    200,
                    json={
                        "object": "list",
                        "data": [
                            {
                                "id": "test-model",
                                "object": "model",
                                "created": 1,
                                "owned_by": "test",
                            }
                        ],
                    },
                )
            if host == "api.anthropic.com":
                return httpx.Response(
                    200,
                    json={
                        "data": [
                            {
                                "id": "test-model",
                                "type": "model",
                                "display_name": "Test model",
                                "created_at": "2026-01-01T00:00:00Z",
                            }
                        ],
                        "has_more": False,
                        "first_id": "test-model",
                        "last_id": "test-model",
                    },
                )
            return httpx.Response(200, json={"models": [{"name": "models/test-model"}]})
        chunks = [
            self.output[: len(self.output) // 2],
            self.output[len(self.output) // 2 :],
        ]
        if host == "api.openai.com":
            events = [
                "data: "
                + json.dumps(
                    {
                        "id": "chatcmpl-test",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": "test-model",
                        "choices": [
                            {
                                "index": 0,
                                "delta": {"content": chunk},
                                "finish_reason": None,
                            }
                        ],
                    }
                )
                + "\n\n"
                for chunk in chunks
            ]
            if self.finish_reason:
                events.append(
                    "data: "
                    + json.dumps(
                        {
                            "id": "chatcmpl-test",
                            "object": "chat.completion.chunk",
                            "created": 1,
                            "model": "test-model",
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {},
                                    "finish_reason": self.finish_reason,
                                }
                            ],
                        }
                    )
                    + "\n\n"
                )
            events.append("data: [DONE]\n\n")
        elif host == "generativelanguage.googleapis.com":
            events = [
                "data: "
                + json.dumps(
                    {"candidates": [{"content": {"parts": [{"text": chunk}]}}]}
                )
                + "\n\n"
                for chunk in chunks
            ]
            if self.finish_reason:
                reason = {"stop": "STOP", "length": "MAX_TOKENS"}.get(
                    self.finish_reason, self.finish_reason
                )
                events.append(
                    "data: "
                    + json.dumps({"candidates": [{"finishReason": reason}]})
                    + "\n\n"
                )
        else:
            values = [
                dict(
                    type="message_start",
                    message=dict(
                        id="msg_test",
                        type="message",
                        role="assistant",
                        model="test-model",
                        content=[],
                        stop_reason=None,
                        stop_sequence=None,
                        usage=dict(input_tokens=1, output_tokens=0),
                    ),
                ),
                dict(
                    type="content_block_start",
                    index=0,
                    content_block=dict(type="text", text=""),
                ),
            ]
            values.extend(
                dict(
                    type="content_block_delta",
                    index=0,
                    delta=dict(type="text_delta", text=chunk),
                )
                for chunk in chunks
            )
            values.extend(
                [
                    dict(type="content_block_stop", index=0),
                    dict(
                        type="message_delta",
                        delta=dict(
                            stop_reason={
                                "stop": "end_turn",
                                "length": "max_tokens",
                            }.get(self.finish_reason, self.finish_reason),
                            stop_sequence=None,
                        ),
                        usage=dict(output_tokens=10),
                    ),
                    dict(type="message_stop"),
                ]
            )
            events = [
                "event: " + value["type"] + "\ndata: " + json.dumps(value) + "\n\n"
                for value in values
            ]
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            stream=WireStream(events, self),
        )

    def install(self, monkeypatch) -> None:
        """Inject mock HTTP only; provider and OAuth service logic are unmodified."""
        import anthropic
        import openai
        from pydantic import SecretStr

        from app.core.ai import claude_adapter, gemini_adapter, openai_adapter
        from app.core.config import get_settings
        from app.services import auth_service

        original_openai, original_claude = openai.AsyncOpenAI, anthropic.AsyncAnthropic

        def sdk_client(package: str):
            native = getattr(
                importlib.import_module(package + "._base_client"), "httpx2", httpx
            )

            class NativeStream(native.AsyncByteStream):
                async def __aiter__(inner) -> AsyncIterator[bytes]:
                    try:
                        async for chunk in inner.response.aiter_bytes():
                            yield chunk
                    except httpx.ReadTimeout as exc:
                        raise native.ReadTimeout("synthetic stream timeout") from exc

                async def aclose(inner) -> None:
                    await inner.response.aclose()

            def native_response(request):
                try:
                    response = self.handle(
                        httpx.Request(
                            request.method,
                            str(request.url),
                            headers=dict(request.headers),
                            content=request.content,
                        )
                    )
                except httpx.ReadTimeout as exc:
                    raise native.ReadTimeout(
                        "synthetic upstream timeout", request=request
                    ) from exc
                if response.is_stream_consumed:
                    return native.Response(
                        response.status_code,
                        headers=dict(response.headers),
                        content=response.content,
                    )
                stream = NativeStream()
                stream.response = response
                return native.Response(
                    response.status_code, headers=dict(response.headers), stream=stream
                )

            return native.AsyncClient(transport=native.MockTransport(native_response))

        monkeypatch.setattr(
            openai_adapter.openai,
            "AsyncOpenAI",
            lambda **kwargs: original_openai(
                http_client=sdk_client("openai"), **kwargs
            ),
        )
        monkeypatch.setattr(
            claude_adapter.anthropic,
            "AsyncAnthropic",
            lambda **kwargs: original_claude(
                http_client=sdk_client("anthropic"),
                **kwargs,
            ),
        )
        http_namespace = SimpleNamespace(
            AsyncClient=self.client, HTTPError=httpx.HTTPError, Timeout=httpx.Timeout
        )
        monkeypatch.setattr(gemini_adapter, "httpx", http_namespace)
        monkeypatch.setattr(auth_service, "httpx", http_namespace)
        settings = get_settings().model_copy(
            update=dict(
                google_client_id="google-test-client",
                github_client_id="github-test-client",
                github_client_secret=SecretStr("synthetic-oauth-test-secret"),
            )
        )
        monkeypatch.setattr(auth_service, "get_settings", lambda: settings)
