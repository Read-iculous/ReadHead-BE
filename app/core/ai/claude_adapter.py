"""Anthropic streaming adapter with isolated system prompt and no retries."""

from collections.abc import AsyncGenerator
from typing import Any, cast

import anthropic

from app.core.ai.base import BaseAIProvider
from app.core.ai.cleanup import shielded_context
from app.core.ai.errors import provider_error
from app.core.ai.formatter import HistoryFormatter


class ClaudeProvider(BaseAIProvider):
    """Request-scoped Claude integration with context-managed stream closure."""

    async def generate_stream(
        self, messages: list[dict], model: str
    ) -> AsyncGenerator[str, None]:
        self.finish_reason = None
        system, turns = HistoryFormatter.normalize(messages)
        try:
            async with shielded_context(
                anthropic.AsyncAnthropic(api_key=self.key, max_retries=0, timeout=45)
            ) as client:
                async with shielded_context(
                    client.messages.stream(
                        model=model,
                        system=system,
                        messages=cast(Any, turns),
                        max_tokens=4096,
                    )
                ) as stream:
                    async for token in stream.text_stream:
                        yield token
                    message = await stream.get_final_message()
                    if message.stop_reason is not None:
                        self.finish_reason = {
                            "end_turn": "stop",
                            "stop_sequence": "stop",
                            "max_tokens": "length",
                            "model_context_window_exceeded": "length",
                        }.get(message.stop_reason, message.stop_reason)
        except (anthropic.APIError, ValueError) as exc:
            raise provider_error(exc) from exc

    async def validate_key(self) -> bool:
        """Check the provider model listing without generating user content."""
        try:
            async with shielded_context(
                anthropic.AsyncAnthropic(api_key=self.key, max_retries=0, timeout=10)
            ) as client:
                await client.models.list(limit=1)
                return True
        except anthropic.APIError as exc:
            raise provider_error(exc) from exc
