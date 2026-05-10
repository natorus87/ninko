from __future__ import annotations

from pathlib import Path
import sys

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.lint_routing_keywords import (
    RoutingKeyword,
    iter_routing_keywords,
    validate_keywords,
)


def test_current_routing_keywords_pass_linter() -> None:
    assert validate_keywords(iter_routing_keywords(_REPO_ROOT)) == []


def test_rejects_new_short_keyword_without_allowlist() -> None:
    errors = validate_keywords(
        [RoutingKeyword(module="example", keyword="vm", path=Path("manifest.py"))]
    )

    assert "shorter than 4 characters" in errors[0]


def test_rejects_stopword_keyword() -> None:
    errors = validate_keywords(
        [RoutingKeyword(module="example", keyword="und", path=Path("manifest.py"))]
    )

    assert "is a stopword" in errors[0]


def test_allows_existing_short_keyword_allowlist() -> None:
    errors = validate_keywords(
        [RoutingKeyword(module="proxmox", keyword="vm", path=Path("manifest.py"))]
    )

    assert errors == []
