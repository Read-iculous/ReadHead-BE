"""Gemini asynchronous HTTP adapter; only fixed provider hosts are contacted."""

import json
import re
from collections.abc import AsyncGenerator

import httpx

from app.core.ai.base import BaseAIProvider
from app.core.ai.cleanup import shielded_context
from app.core.ai.errors import provider_error
from app.core.ai.formatter import HistoryFormatter
from app.core.exceptions import AppException


class GeminiProvider(BaseAIProvider):
    """Translate standard roles into Gemini content parts."""

    async def generate_stream(
        self, messages: list[dict], model: str
    ) -> AsyncGenerator[str, None]:
        self.finish_reason = None
        if not re.fullmatch(r"[a-zA-Z0-9_.-]+", model):
            raise AppException(422, "VALIDATION_ERROR", "Invalid model name", "model")
        system, turns = HistoryFormatter.normalize(messages)
        payload = dict(
            contents=[
                dict(
                    role="model" if t["role"] == "assistant" else "user",
                    parts=[dict(text=t["content"])],
                )
                for t in turns
            ],
            systemInstruction=dict(parts=[dict(text=system)]),
            generationConfig=dict(maxOutputTokens=4096),
        )
        try:
            async with shielded_context(
                httpx.AsyncClient(timeout=httpx.Timeout(45, connect=10))
            ) as client:
                async with shielded_context(
                    client.stream(
                        "POST",
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:streamGenerateContent",
                        params={"alt": "sse"},
                        headers={"x-goog-api-key": self.key},
                        json=payload,
                    )
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        event = json.loads(line[5:])
                        if "error" in event:
                            raise AppException(
                                502, "UPSTREAM_AI_ERROR", "Gemini generation failed"
                            )
                        for candidate in event.get("candidates", []):
                            reason = candidate.get("finishReason")
                            if isinstance(reason, str):
                                self.finish_reason = {
                                    "STOP": "stop",
                                    "MAX_TOKENS": "length",
                                }.get(reason, reason)
                            for part in candidate.get("content", {}).get("parts", []):
                                if part.get("text"):
                                    yield part["text"]
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise provider_error(exc) from exc

    async def validate_key(self) -> bool:
        """List available models using the user's key in a header."""
        try:
            async with shielded_context(httpx.AsyncClient(timeout=10)) as client:
                response = await client.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": self.key},
                    params={"pageSize": 1},
                )
                response.raise_for_status()
                return True
        except httpx.HTTPError as exc:
            raise provider_error(exc) from exc
