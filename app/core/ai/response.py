"""SSE response ownership of generator and admission-resource cleanup."""

from collections.abc import AsyncGenerator, Awaitable, Callable, Mapping

from starlette.responses import StreamingResponse
from starlette.types import Receive, Scope, Send

from app.core.ai.cleanup import shielded_cleanup


class ManagedStreamingResponse(StreamingResponse):
    """Close a suspended generator even when disconnect occurs inside ASGI send."""

    def __init__(
        self,
        content: AsyncGenerator[str, None],
        *,
        cleanup: Callable[[], Awaitable[None]],
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self.stream = content
        self.cleanup = cleanup
        super().__init__(content, media_type="text/event-stream", headers=headers)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Finalize on normal completion, cancellation and ASGI 2.4 send failure."""
        try:
            await super().__call__(scope, receive, send)
        finally:
            try:
                # GeneratorExit triggers partial persistence if it was suspended
                # at a token yield while StreamingResponse was awaiting send().
                await shielded_cleanup(self.stream.aclose)
            finally:
                # Also release admission if the generator was never started.
                await shielded_cleanup(self.cleanup)
