"""Bounded deterministic secret and PII detection; never log input text."""

import re

PATTERNS = {
    "api_key": re.compile(
        r"(?i)\b(?:sk-[a-z0-9_-]{12,}|AIza[a-z0-9_-]{20,}|gh[pousr]_[a-z0-9]{15,})\b"
    ),
    "private_key": re.compile(
        r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?(?:-----END [^-]+-----|$)"
    ),
    "auth_token": re.compile(
        r"(?i)\b(?:bearer\s+[a-z0-9._~-]{10,}|eyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+)"
    ),
    "password": re.compile(
        r"(?i)\b(?:password|passwd|secret|api[_-]?key)\s*[:=]\s*[\x22\x27]?[^\s\x22\x27,;]{4,}"
    ),
    "password_phrase": re.compile(
        r"(?i)\b(?:my|the)\s+(?:password|passwd|passphrase|pin(?:\s+code)?)\s+(?:is|would\s+be)\s+[\x22\x27]?[^\s\x22\x27,;]{4,}"
    ),
    "email": re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
    "national_id": re.compile(r"\b(?:\d{3}-\d{2}-\d{4}|\d{12})\b"),
    "financial_number": re.compile(r"\b(?:\d[ -]?){13,19}\b"),
}


def inspect(text: str) -> tuple[list[str], str]:
    """Identify sensitive types and return a fully redacted preview."""
    found, redacted = [], text
    for kind, pattern in PATTERNS.items():
        if pattern.search(text):
            found.append(kind)
            redacted = pattern.sub("[REDACTED]", redacted)
    return found, redacted
