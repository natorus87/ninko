"""Regression tests for Teams message formatting."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_FORMATTER_PATH = (
    Path(__file__).resolve().parents[1] / "modules_catalog" / "teams" / "formatter.py"
)
_SPEC = importlib.util.spec_from_file_location("teams_formatter", _FORMATTER_PATH)
assert _SPEC and _SPEC.loader
_FORMATTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FORMATTER)
format_for_teams = _FORMATTER.format_for_teams


def test_markdown_table_cells_are_cleaned_inside_code_block() -> None:
    text = (
        "| Metrik | Wert |\n"
        "| --- | --- |\n"
        "| **Nodes** | `1` |\n"
        "| **Failing Pods** | 0 ✅ |\n"
    )

    formatted = format_for_teams(text)

    assert formatted.startswith("```")
    assert "**Nodes**" not in formatted
    assert "`1`" not in formatted
    assert "| Nodes" in formatted
    assert "| 1" in formatted
