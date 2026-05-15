"""Licium knowledge architect agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import (
    append_licium_log,
    create_licium_note,
    get_licium_note,
    get_licium_wiki_meta,
    ingest_existing_licium_notes,
    lint_licium_wiki,
    list_licium_tree,
    search_licium,
    setup_licium_wiki,
    update_licium_note,
    update_licium_wiki_index,
)

_SYSTEM_PROMPT = """You are Ninko's Licium Knowledge Architect.

You manage a structured knowledge base following the Karpathy LLM-Wiki pattern:
knowledge is compiled, cross-referenced, and maintained.

Capabilities:
- Ingest new sources into the Ninko Wiki.
- Query semantic notes and synthesize cited answers.
- Lint wiki health and report gaps, orphans, and conflicts.

Tool execution rules:
- For existing Licium-note imports, immediately call `ingest_existing_licium_notes`.
- For new ingest, call `get_licium_wiki_meta` first and initialize if needed.
- During ingest, complete all required steps; do not stop after listing metadata.
- For queries, search first, read relevant notes, then synthesize with note IDs.
- For lint requests, call `lint_licium_wiki` and report findings.
- Log ingest, query, and lint operations with `append_licium_log`.

Output format:
- For lists (Wiki pages, Search results, Tree structure): ALWAYS use Markdown tables.
- Example: | Title | Folder | Modified |
- NEVER return raw JSON or Python repr as the final answer.
- Cite facts with note-ID links such as `[Source: {note_id}]`.

Safety and confirmation rules:
- Mark contradictions explicitly.
- Keep pages focused; split unrelated concepts into separate pages.

Error handling:
- On errors, provide a concrete message and do not silently abort."""


class LiciumAgent(BaseAgent):
    """Knowledge architect for the Licium knowledge base."""

    def __init__(self) -> None:
        """Initialize the Licium agent."""
        super().__init__(
            name="licium",
            system_prompt=_SYSTEM_PROMPT,
            tools=[
                search_licium,
                list_licium_tree,
                get_licium_note,
                get_licium_wiki_meta,
                setup_licium_wiki,
                ingest_existing_licium_notes,
                create_licium_note,
                update_licium_note,
                update_licium_wiki_index,
                append_licium_log,
                lint_licium_wiki,
            ],
        )

    async def invoke(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
        confirmed: bool = False,
        wants_stream: bool = False,
        token_callback=None,
        cancellation_check=None,
    ) -> tuple[str, bool]:
        """Use a deterministic fast path for existing-note batch ingest."""
        msg = (message or "").casefold()
        wants_existing_notes = any(
            marker in msg
            for marker in (
                "bestehende notizen",
                "bestehenden notizen",
                "existing notes",
                "alle notizen",
            )
        )
        wants_ingest = any(marker in msg for marker in ("ingest", "ingeste", "import"))
        wants_wiki = "wiki" in msg or "ninko-wiki" in msg or "ninko wiki" in msg
        if wants_existing_notes and wants_ingest and wants_wiki:
            result = await ingest_existing_licium_notes.ainvoke({})
            return str(result), False

        return await super().invoke(
            message=message,
            chat_history=chat_history,
            session_id=session_id,
            confirmed=confirmed,
            wants_stream=wants_stream,
            token_callback=token_callback,
            cancellation_check=cancellation_check,
        )


agent = LiciumAgent()
