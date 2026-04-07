"""
GLPI module — specialist agent.
Integrates with Kubernetes module via Redis PubSub events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from agents.base_agent import BaseAgent, _t
from core.redis_client import get_redis
from .tools import (
    create_ticket,
    get_ticket,
    search_tickets,
    update_ticket,
    close_ticket,
    add_followup,
    add_solution,
    add_watcher,
    assign_ticket,
    search_users,
    list_groups,
    list_categories,
    get_ticket_stats,
    get_ticket_attachments,
    get_ticket_image_ocr,
    get_ticket_followups,
    get_ticket_solutions,
)

logger = logging.getLogger("ninko.modules.glpi.agent")

GLPI_SYSTEM_PROMPT_DE = """Du bist der GLPI Helpdesk-Spezialist von Ninko.

Deine Fähigkeiten:
- Ticket-Erstellung und -Verwaltung
- Ticket-Suche nach Status, Priorität, Stichwort
- Follow-ups, Lösungen und Anhänge abrufen
- OCR auf Ticket-Bildern (Screenshot-/Foto-Analyse)
- Tickets schließen mit Lösungsbeschreibung
- Benutzer- und Gruppensuche
- Ticket-Statistiken
- Beobachter zu Tickets hinzufügen (add_watcher)
- Tickets zuweisen (assign_ticket)

WICHTIG - Bearbeitung neuer Tickets (Status=NEU):
1. Suche zuerst Benutzer "Sophy" mit search_users("Sophy")
2. Füge Sophy als Beobachter hinzu mit add_watcher(ticket_id, sophy_user_id)
3. Schreibe eine hilfreiche Antwort/Followup mit add_followup()
4. Setze Status auf "Wartend" (4) mit update_ticket(status=4)
5. NICHT direkt schließen - erst auf User-Antwort warten!

Verhaltensregeln:
- Erstelle Tickets mit klaren, aussagekräftigen Titeln
- IMMER das passende Tool direkt aufrufen – nicht beschreiben was du tun würdest
- Wenn alle nötigen Infos vorhanden: sofort `create_ticket` aufrufen, nicht nochmal fragen
- Falls Priorität/Kategorie fehlen: kurz nachfragen, dann SOFORT `create_ticket` aufrufen
- Zeige Ticket-Details in übersichtlicher Form
- Nutze Farb-Indikatoren für Prioritäten:
  🔴 Sehr hoch/Kritisch, 🟠 Hoch, 🟡 Mittel, 🟢 Niedrig
- Verlinke zu GLPI wenn möglich

Prioritäten:
1 = Sehr niedrig, 2 = Niedrig, 3 = Mittel, 4 = Hoch, 5 = Sehr hoch, 6 = Kritisch

Status:
1 = Neu, 2 = In Bearbeitung, 3 = Geplant, 4 = Wartend, 5 = Gelöst, 6 = Geschlossen"""

GLPI_SYSTEM_PROMPT_EN = """You are the GLPI Helpdesk specialist of Ninko.

Your capabilities:
- Ticket creation and management
- Ticket search by status, priority, keyword
- Retrieve follow-ups, solutions, and attachments
- OCR on ticket images (screenshots/photos)
- Closing tickets with resolution descriptions
- User and group search
- Ticket statistics
- Add watchers to tickets (add_watcher)
- Assign tickets (assign_ticket)

IMPORTANT - Handling NEW tickets (Status=NEW):
1. First search for user "Sophy" with search_users("Sophy")
2. Add Sophy as watcher with add_watcher(ticket_id, sophy_user_id)
3. Write a helpful response/followup with add_followup()
4. Set status to "Pending" (4) with update_ticket(status=4)
5. DO NOT close immediately - wait for user response first!

Behavior rules:
- Create tickets with clear, meaningful titles
- ALWAYS call the appropriate tool directly — do not describe what you would do
- If all required info is present: call `create_ticket` immediately, do not ask again
- If priority/category is missing: ask briefly, then call `create_ticket` immediately
- Show ticket details in a clear format
- Use color indicators for priorities:
  🔴 Very high/Critical, 🟠 High, 🟡 Medium, 🟢 Low
- Link to GLPI when possible

Priorities:
1 = Very low, 2 = Low, 3 = Medium, 4 = High, 5 = Very high, 6 = Critical

Status:
1 = New, 2 = In progress, 3 = Planned, 4 = Pending, 5 = Solved, 6 = Closed"""


class GlpiAgent(BaseAgent):
    """GLPI Helpdesk specialist with Redis PubSub event listener."""

    def __init__(self) -> None:
        super().__init__(
            name="glpi",
            system_prompt=_t(GLPI_SYSTEM_PROMPT_DE, GLPI_SYSTEM_PROMPT_EN),
            tools=[
                create_ticket,
                get_ticket,
                search_tickets,
                update_ticket,
                close_ticket,
                add_followup,
                add_solution,
                add_watcher,
                assign_ticket,
                search_users,
                list_groups,
                list_categories,
                get_ticket_stats,
                get_ticket_attachments,
                get_ticket_image_ocr,
                get_ticket_followups,
                get_ticket_solutions,
            ],
        )

        # Auto-incident ticket creation
        auto_create = (
            os.environ.get("GLPI_AUTO_CREATE_INCIDENTS", "false").lower() == "true"
        )
        if auto_create:
            asyncio.get_event_loop().create_task(self._listen_for_incidents())
            logger.info("GLPI auto-incident creation enabled.")

    async def _listen_for_incidents(self) -> None:
        """
        Listens for Redis PubSub events from other modules.
        On incident_detected events: automatically creates a GLPI ticket.
        """
        redis = get_redis()
        pubsub = await redis.subscribe_events()

        logger.info("GLPI event listener started.")

        while True:
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )

                if message and message.get("type") == "message":
                    try:
                        event = json.loads(message["data"])
                        await self._handle_event(event)
                    except json.JSONDecodeError:
                        pass

                await asyncio.sleep(0.5)

            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                ImportError,
            ) as exc:
                logger.error("GLPI event listener error: %s", exc)
                await asyncio.sleep(5)

    async def _handle_event(self, event: dict) -> None:
        """Processes an incoming event."""
        event_type = event.get("event_type", "")
        severity = event.get("severity", "")

        if event_type == "incident_detected" and severity in ("critical", "high"):
            source = event.get("source_module", "unknown")
            data = event.get("data", {})

            title = f"[Auto] {source.upper()} Incident: {data.get('error', data.get('namespace', 'Error detected'))}"
            description = (
                f"Automatically created ticket by Ninko.\n\n"
                f"Source module: {source}\n"
                f"Severity: {severity}\n"
                f"Details:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
            )

            priority = 5 if severity == "critical" else 4

            try:
                result = await create_ticket.ainvoke(
                    {
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "ticket_type": 1,  # Incident
                    }
                )
                logger.info(
                    "Auto-ticket created: %s → #%s",
                    title,
                    result.get("ticket_id", "?"),
                )
            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                ImportError,
            ) as exc:
                logger.error("Auto-ticket creation failed: %s", exc)
