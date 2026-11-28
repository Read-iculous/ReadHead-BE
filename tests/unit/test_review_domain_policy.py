"""Blacklist equivalence and wildcard isolation across Unicode/IDNA domains."""

import pytest

from app.core.privacy.domain_filter import blocked


@pytest.mark.parametrize(
    ("url", "patterns", "expected"),
    [
        ("https://bücher.de/article", ["bücher.de"], True),
        ("https://xn--bcher-kva.de/article", ["bücher.de"], True),
        ("https://bücher.de/article", ["xn--bcher-kva.de"], True),
        ("https://bücher.de/article", ["*.bücher.de"], True),
        ("https://read.xn--bcher-kva.de/article", ["*.bücher.de"], True),
        ("https://BÜCHER.de./article", ["*.bücher.de."], True),
        ("https://evilbücher.de/article", ["*.bücher.de"], False),
        ("https://bücher.de.attacker.example/article", ["*.bücher.de"], False),
        ("https://intranet.corp/article", ["intranet.*"], True),
        ("https://example.com/bücher.de", ["*.bücher.de"], False),
    ],
)
def test_idna_blacklist_semantics(
    url: str, patterns: list[str], expected: bool
) -> None:
    assert blocked(url, patterns) is expected


@pytest.mark.parametrize("dot", ["\u3002", "\uff0e", "\uff61"])
def test_unicode_dns_root_dot_is_normalized_for_hosts_and_patterns(dot: str) -> None:
    assert blocked(f"https://bank.com{dot}/statement", ["bank.com"])
    assert blocked("https://bank.com/statement", [f"bank.com{dot}"])
    assert blocked(f"https://sub.bank.com{dot}/statement", [f"*.bank.com{dot}"])
