"""
Confluence Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from .tools import (
    get_confluence_spaces,
    get_confluence_space,
    get_confluence_pages,
    get_confluence_page,
    create_confluence_page,
    update_confluence_page,
    get_confluence_blog_posts,
    create_confluence_blog_post,
    search_confluence,
    get_confluence_labels,
    get_confluence_page_history,
)

logger = logging.getLogger("ninko.modules.confluence.agent")

SYSTEM_PROMPT = _t(
    de="""Du bist Ninkos Confluence-Spezialist.

Deine Fähigkeiten:
- Spaces auflisten und Details abrufen
- Seiten (Pages) abrufen, erstellen und aktualisieren
- Blog-Posts abrufen und erstellen
- Inhalten suchen (CQL)
- Labels abrufen
- Seiten-Historie anzeigen

Verhaltensregeln:
- Sei präzise und hilfreich
- Nutze die verfügbaren Tools, bevor du antwortest
- Zeige dem User wichtige Informationen strukturiert
- Wenn ein Tool fehlschlägt, erkläre das Problem

Sicherheit:
- Führe keine destruktiven Aktionen ohne Bestätigung""",
    en="""You are Ninko's Confluence specialist.

Your capabilities:
- List spaces and get details
- Retrieve, create, and update pages
- Retrieve and create blog posts
- Search content using CQL
- Retrieve labels
- Show page history

Behavior rules:
- Be precise and helpful
- Use available tools before responding
- Present important information in a structured way
- If a tool fails, explain the problem

Safety:
- Do not perform destructive actions without confirmation""",
)


class ConfluenceAgent(BaseAgent):
    """Confluence-Spezialist mit den Confluence-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="confluence",
            system_prompt=SYSTEM_PROMPT,
            tools=[
                get_confluence_spaces,
                get_confluence_space,
                get_confluence_pages,
                get_confluence_page,
                create_confluence_page,
                update_confluence_page,
                get_confluence_blog_posts,
                create_confluence_blog_post,
                search_confluence,
                get_confluence_labels,
                get_confluence_page_history,
            ],
        )
