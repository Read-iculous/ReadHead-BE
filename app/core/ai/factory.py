"""Provider factory keeping vendor SDKs out of business services."""

from app.core.ai.base import BaseAIProvider
from app.core.ai.claude_adapter import ClaudeProvider
from app.core.ai.gemini_adapter import GeminiProvider
from app.core.ai.openai_adapter import OpenAIProvider
from app.core.exceptions import AppException

DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "gemini": "gemini-1.5-flash",
    "claude": "claude-3-5-sonnet-latest",
}


class ProviderFactory:
    """Select a request-scoped adapter from documented provider names."""

    @staticmethod
    def create(provider: str, key: str) -> BaseAIProvider:
        """Inject the decrypted user key only into its chosen adapter."""
        classes: dict[str, type[BaseAIProvider]] = {
            "openai": OpenAIProvider,
            "gemini": GeminiProvider,
            "claude": ClaudeProvider,
        }
        if provider not in classes:
            raise AppException(400, "UNSUPPORTED_PROVIDER", "Provider is not supported")
        return classes[provider](key)
