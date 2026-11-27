"""OpenAI SDK adapter with all automatic request retries disabled."""

from collections.abc import AsyncGenerator
from typing import cast

import openai
from openai.types.chat import ChatCompletionMessageParam

from app.core.ai.base import BaseAIProvider
from app.core.ai.cleanup import shielded_cleanup, shielded_context
from app.core.ai.errors import provider_error


class OpenAIProvider(BaseAIProvider):
    """Request-scoped asynchronous OpenAI streaming."""

    async def generate_stream(
        self, messages: list[dict], model: str
    ) -> AsyncGenerator[str, None]:
        self.finish_reason = None
        try:
            async with shielded_context(
                openai.AsyncOpenAI(api_key=self.key, max_retries=0, timeout=45)
            ) as client:
                stream = await client.chat.completions.create(
                    model=model,
                    messages=cast(list[ChatCompletionMessageParam], messages),
                    stream=True,
                    max_tokens=4096,
                )
                try:
                    async for event in stream:
                        if event.choices:
                            choice = event.choices[0]
                            reason = getattr(choice, "finish_reason", None)
                            if reason is not None:
                                self.finish_reason = reason
                            if choice.delta.content:
                                yield choice.delta.content
                finally:
                    await shielded_cleanup(stream.close)
        except (openai.APIError, ValueError) as exc:
            raise provider_error(exc) from exc

    async def validate_key(self) -> bool:
        """Validate authentication without creating a completion."""
        try:
            async with shielded_context(
                openai.AsyncOpenAI(api_key=self.key, max_retries=0, timeout=10)
            ) as client:
                await client.models.list()
                return True
        except openai.APIError as exc:
            raise provider_error(exc) from exc
