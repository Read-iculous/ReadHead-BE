"""Hostname-based domain policy with explicit wildcard semantics."""

import fnmatch
from urllib.parse import urlsplit


def normalize_domain(value: str) -> str:
    """Use one IDNA representation for hostnames and wildcard hostname patterns."""
    return value.rstrip(".").casefold().encode("idna").decode("ascii").rstrip(".")


def blocked(url: str, patterns: list[str]) -> bool:
    """Match hostnames only, never URL substrings or attacker-controlled paths."""
    try:
        host = normalize_domain(urlsplit(url).hostname or "")
        patterns = [normalize_domain(pattern) for pattern in patterns]
    except UnicodeError:
        return True
    return any(
        fnmatch.fnmatchcase(host, p) or (p.startswith("*.") and host == p[2:])
        for p in patterns
    )
