"""
Teams Formatter – Bereitet Markdown-Text für Microsoft Teams vor.

Teams unterstützt GitHub-Flavored Markdown nativ (Bold, Italic, Code, Headings, Listen).
Tabellen werden NICHT unterstützt und daher in ASCII-Code-Blöcke konvertiert.
"""

from __future__ import annotations

import re

_MAX_COL_WIDTH = 28


def _ascii_table(md_table: str) -> str:
    """Konvertiert eine Markdown-Tabelle in eine ASCII-Box-Tabelle."""
    lines = md_table.strip().splitlines()
    rows: list[list[str]] = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        # Separator-Zeile überspringen (z.B. |---|:---:|---:|)
        if re.match(r"^\|?[\s:\-\|]+$", line):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return md_table

    num_cols = max(len(r) for r in rows)
    widths = [0] * num_cols
    for row in rows:
        for i, cell in enumerate(row):
            if i < num_cols:
                widths[i] = min(max(widths[i], len(cell)), _MAX_COL_WIDTH)

    sep = "+" + "+".join("-" * (w + 2) for w in widths) + "+"
    lines_out: list[str] = [sep]

    for idx, row in enumerate(rows):
        padded: list[str] = []
        for i in range(num_cols):
            cell = row[i] if i < len(row) else ""
            if len(cell) > widths[i]:
                cell = cell[: widths[i] - 1] + "…"
            padded.append(f" {cell:<{widths[i]}} ")
        lines_out.append("|" + "|".join(padded) + "|")
        if idx == 0:
            lines_out.append(sep)

    lines_out.append(sep)
    return "\n".join(lines_out)


def format_for_teams(text: str) -> str:
    """
    Bereitet Markdown-Text für Teams vor.

    Teams verarbeitet Markdown nativ — nur Tabellen werden konvertiert,
    da Teams-Markdown keine Tabellen unterstützt.
    """
    protected: list[str] = []

    def protect(content: str) -> str:
        idx = len(protected)
        protected.append(content)
        return f"\x00P{idx}\x00"

    # 1. Fenced Code Blocks schützen (unverändert durchlassen)
    text = re.sub(r"```[\s\S]*?```", lambda m: protect(m.group(0)), text)

    # 2. Markdown-Tabellen → ASCII in Code-Block konvertieren
    def _table(m: re.Match) -> str:
        ascii_t = _ascii_table(m.group(0))
        return protect(f"```\n{ascii_t}\n```")

    text = re.sub(r"(?m)(^\|.+\n?)+", _table, text)

    # 3. Platzhalter wiederherstellen
    def _restore(m: re.Match) -> str:
        return protected[int(m.group(1))]

    text = re.sub(r"\x00P(\d+)\x00", _restore, text)

    return text
