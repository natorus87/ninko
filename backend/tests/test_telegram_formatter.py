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
format_chunks_for_telegram = _FORMATTER.format_chunks_for_telegram


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


def test_long_bold_text_is_split_into_valid_html_chunks() -> None:
    chunks = format_chunks_for_telegram("**" + ("x" * 5000) + "**")

    assert len(chunks) == 2
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert all(chunk.count("<b>") == chunk.count("</b>") for chunk in chunks)
    assert all(chunk.startswith("<b>") and chunk.endswith("</b>") for chunk in chunks)
    assert "**" not in "".join(chunks)


def test_long_fenced_code_preserves_markup_and_whitespace() -> None:
    code = "  first\n" + ("x" * 4100) + "\n  last"

    chunks = format_chunks_for_telegram(f"```python\n{code}\n```")

    assert len(chunks) == 2
    assert all(len(chunk) <= 4000 for chunk in chunks)
    assert all(chunk.startswith('<pre><code class="language-python">') for chunk in chunks)
    assert all(chunk.endswith("</code></pre>") for chunk in chunks)
    reconstructed = "".join(
        chunk.removeprefix('<pre><code class="language-python">')
        .removesuffix("</code></pre>")
        for chunk in chunks
    )
    assert reconstructed == f"{code}\n"
