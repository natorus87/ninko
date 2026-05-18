"""Regression tests for Telegram Markdown-to-HTML formatting."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_FORMATTER_PATH = (
    Path(__file__).resolve().parents[1] / "modules_catalog" / "telegram" / "formatter.py"
)
_SPEC = importlib.util.spec_from_file_location("telegram_formatter", _FORMATTER_PATH)
assert _SPEC and _SPEC.loader
_FORMATTER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_FORMATTER)
format_for_telegram = _FORMATTER.format_for_telegram


def test_markdown_table_cells_are_cleaned_inside_pre_block() -> None:
    text = (
        "| Metrik | Wert |\n"
        "| --- | --- |\n"
        "| **Nodes** | `1` |\n"
        "| **Failing Pods** | 0 ✅ |\n"
    )

    formatted = format_for_telegram(text)

    assert formatted.startswith("<pre>")
    assert "**Nodes**" not in formatted
    assert "`1`" not in formatted
    assert "| Nodes" in formatted
    assert "| 1" in formatted


def test_indented_markdown_table_is_converted() -> None:
    text = (
        "  | VMID | Name |\n"
        "  | --- | --- |\n"
        "  | `100` | **proxmox-vm** |\n"
    )

    formatted = format_for_telegram(text)

    assert formatted.startswith("<pre>")
    assert "`100`" not in formatted
    assert "**proxmox-vm**" not in formatted
    assert "| 100" in formatted
