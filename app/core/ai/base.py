"""Provider-neutral asynchronous generation interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from app.core.ai.cleanup import shielded_cleanup


class BaseAIProvider(ABC):
    """A request-scoped adapter using only the current user's BYOK key."""

    def __init__(self, key: str) -> None:
        self.key = key
        self.finish_reason: str | None = None

    @abstractmethod
    async def generate_stream(
        self, messages: list[dict], model: str
    ) -> AsyncGenerator[str, None]:
        """Yield text chunks, closing upstream resources on cancellation."""
        yield ""

    async def generate_complete(self, messages: list[dict], model: str) -> str:
        """Collect a bounded generation through the same no-retry pipeline."""
        parts = []
        size = 0
        stream = self.generate_stream(messages, model)
        try:
            async for chunk in stream:
                size += len(chunk)
                if size > 100000:
                    from app.core.exceptions import AppException

                    raise AppException(
                        502,
                        "UPSTREAM_AI_ERROR",
                        "Provider response exceeded the safe output limit",
                    )
                parts.append(chunk)
        finally:
            await shielded_cleanup(stream.aclose)
        if self.finish_reason != "stop":
            from app.core.exceptions import AppException

            raise AppException(
                502,
                "UPSTREAM_AI_ERROR",
                "Provider did not complete the response; retry manually",
            )
        text = "".join(parts)
        if not text.strip():
            from app.core.exceptions import AppException

            raise AppException(
                502, "UPSTREAM_AI_ERROR", "Provider returned no usable text"
            )
        return text

    @abstractmethod
    async def validate_key(self) -> bool:
        """Perform a low-cost authentication check without saving invalid keys."""
        raise NotImplementedError
