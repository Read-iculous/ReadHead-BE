"""Domain errors independent of HTTP response objects."""

from typing import Any


class AppException(Exception):
    """Represent a documented API failure with safe public details."""

    def __init__(
        self,
        status: int,
        code: str,
        detail: str,
        field: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        super().__init__(detail)
        self.status, self.code, self.detail, self.field = status, code, detail, field
        self.headers, self.extra = headers or {}, extra

    def payload(self) -> dict[str, Any]:
        """Return the standardized error envelope."""
        return dict(detail=self.detail, code=self.code, field=self.field, **self.extra)
