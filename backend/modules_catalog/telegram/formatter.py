"""
Telegram Formatter – Konvertiert Markdown zu Telegram-kompatiblem HTML.

Unterstützte Elemente:
- Fenced Code Blocks (```) → <pre><code>…</code></pre>
- Markdown-Tabellen → ASCII-Box-Tabelle in <pre>
- Inline Code → <code>
- Headings (# – ######) → <b>
- Bold (**text** / __text__) → <b>
- Italic (*text* / _text_) → <i>
- Links [text](url) → <a href="url">text</a>
- Restlicher Text: HTML-escaped (<, >, & werden escapt)

Analog zu gramiojs/format (TypeScript), aber in Python für Telegram-HTML-Modus.
"""

from __future__ import annotations

import re

# Maximale Spaltenbreite in ASCII-Tabellen
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
        if re.match(r'^\|?[\s:\-\|]+$', line):
            continue
        cells = [_clean_table_cell(c.strip()) for c in line.strip("|").split("|")]
        rows.append(cells)

    if not rows:
        return md_table

    num_cols = max(len(r) for r in rows)

    # Spaltenbreiten berechnen (cap bei _MAX_COL_WIDTH)
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
            lines_out.append(sep)  # Kopfzeilen-Trenner

    lines_out.append(sep)
    return "\n".join(lines_out)


def _escape_html(text: str) -> str:
    """Escapt HTML-Sonderzeichen für Telegram."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _clean_table_cell(cell: str) -> str:
    """Remove inline Markdown markers before rendering cells in <pre> blocks."""
    cell = re.sub(r"`([^`\n]+)`", r"\1", cell)
    cell = re.sub(r"\*\*(.+?)\*\*", r"\1", cell)
    cell = re.sub(r"__(.+?)__", r"\1", cell)
    cell = re.sub(r"\*([^*\n]+)\*", r"\1", cell)
    cell = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"\1", cell)
    return cell


def format_for_telegram(text: str) -> str:
    """
    Konvertiert Markdown-formatierten Text in Telegram-HTML (parse_mode=HTML).

    Verarbeitung in dieser Reihenfolge:
    1. Fenced Code Blocks schützen (```)
    2. Markdown-Tabellen → ASCII in <pre> schützen
    3. Inline-Code schützen
    4. HTML-Zeichen im Rest escapen
    5. Headings, Bold, Italic, Links konvertieren
    6. Geschützte Blöcke wiederherstellen
    """
    # Platzhalter-System: geschützte HTML-Blöcke werden durch \x00P{idx}\x00 ersetzt,
    # damit nachfolgende Regex-Schritte sie nicht verändern.
    protected: list[str] = []

    def protect(html: str) -> str:
        idx = len(protected)
        protected.append(html)
        return f"\x00P{idx}\x00"

    # ── 1. Fenced Code Blocks ─────────────────────────────────────────────────
    def _fenced(m: re.Match) -> str:
        lang = m.group(1).strip()
        code = _escape_html(m.group(2))
        inner = (
            f'<code class="language-{lang}">{code}</code>'
            if lang
            else f"<code>{code}</code>"
        )
        return protect(f"<pre>{inner}</pre>")

    text = re.sub(r"```(\w*)\n?([\s\S]*?)```", _fenced, text)

    # ── 2. Markdown-Tabellen → ASCII in <pre> ────────────────────────────────
    def _table(m: re.Match) -> str:
        ascii_t = _ascii_table(m.group(0))
        return protect(f"<pre>{_escape_html(ascii_t)}</pre>")

    # Aufeinanderfolgende Zeilen, die mit | beginnen
    text = re.sub(r"(?m)(^[ \t]*\|.+\n?)+", _table, text)

    # ── 3. Inline Code ────────────────────────────────────────────────────────
    def _inline_code(m: re.Match) -> str:
        return protect(f"<code>{_escape_html(m.group(1))}</code>")

    text = re.sub(r"`([^`\n]+)`", _inline_code, text)

    # ── 4. HTML-Zeichen im restlichen Text escapen ────────────────────────────
    # Marker \x00P{idx}\x00 werden dabei ausgelassen
    parts = re.split(r"(\x00P\d+\x00)", text)
    text = "".join(
        part if re.match(r"\x00P\d+\x00", part) else _escape_html(part)
        for part in parts
    )

    # ── 5. Inline-Formatierung ────────────────────────────────────────────────

    # Headings (# bis ######)
    text = re.sub(r"^#{1,6}\s+(.+)$", r"<b>\1</b>", text, flags=re.MULTILINE)

    # Bold: **text** oder __text__
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text, flags=re.DOTALL)
    text = re.sub(r"__(.+?)__", r"<b>\1</b>", text, flags=re.DOTALL)

    # Italic: *text* oder _text_ (Wort-Unterstriche nicht treffen)
    text = re.sub(r"\*([^*\n]+)\*", r"<i>\1</i>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", text)

    # Links: [text](url)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)

    # ── 6. Platzhalter wiederherstellen ──────────────────────────────────────
    def _restore(m: re.Match) -> str:
        return protected[int(m.group(1))]

    text = re.sub(r"\x00P(\d+)\x00", _restore, text)

    return text


def format_chunks_for_telegram(text: str, max_len: int = 4000) -> list[str]:
    """Format text as independently valid Telegram HTML chunks.

    Markdown is formatted before splitting so constructs spanning a chunk
    boundary retain their meaning. Open HTML tags are closed at the end of a
    chunk and reopened in the next one; tags and entities are never split.
    """
    if not text:
        return [""]
    if max_len < 16:
        raise ValueError("max_len must leave room for Telegram HTML markup")

    formatted = format_for_telegram(text)
    token_matches = re.finditer(
        r"</?[a-z]+(?:\s[^>]*)?>|&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);|.",
        formatted,
        flags=re.DOTALL,
    )
    chunks: list[str] = []
    current = ""
    open_tags: list[tuple[str, str]] = []

    def closing_markup(tags: list[tuple[str, str]]) -> str:
        return "".join(f"</{name}>" for name, _ in reversed(tags))

    for match in token_matches:
        token = match.group(0)
        next_tags = list(open_tags)
        opening = re.fullmatch(r"<([a-z]+)(?:\s[^>]*)?>", token)
        closing = re.fullmatch(r"</([a-z]+)>", token)
        if opening:
            next_tags.append((opening.group(1), token))
        elif closing and next_tags and next_tags[-1][0] == closing.group(1):
            next_tags.pop()

        if len(current) + len(token) + len(closing_markup(next_tags)) > max_len:
            if not current:
                raise ValueError("A single HTML token exceeds the Telegram message limit")
            chunks.append(current + closing_markup(open_tags))
            current = "".join(opening_tag for _, opening_tag in open_tags)
            if len(current) + len(token) + len(closing_markup(next_tags)) > max_len:
                raise ValueError("Telegram HTML nesting exceeds the message limit")

        current += token
        open_tags = next_tags

    if current:
        chunks.append(current + closing_markup(open_tags))

    return chunks
