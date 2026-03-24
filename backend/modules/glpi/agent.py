"""
GLPI Modul – Spezialist-Agent.
Integriert sich mit Kubernetes-Modul via Redis PubSub Events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os

from agents.base_agent import BaseAgent
from core.redis_client import get_redis
from modules.glpi.tools import (
    create_ticket,
    get_ticket,
    search_tickets,
    update_ticket,
    close_ticket,
    add_followup,
    add_solution,
    search_users,
    list_groups,
    list_categories,
    get_ticket_stats,
)

logger = logging.getLogger("kumio.modules.glpi.agent")

GLPI_SYSTEM_PROMPT = """Du bist der GLPI Helpdesk-Spezialist von Kumio.

Deine Fähigkeiten:
- Ticket-Erstellung und -Verwaltung
- Ticket-Suche nach Status, Priorität, Stichwort
- Follow-ups und Lösungen hinzufügen
- Tickets schließen mit Lösungsbeschreibung
- Benutzer- und Gruppensuche
- Ticket-Statistiken

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


class GlpiAgent(BaseAgent):
    """GLPI Helpdesk-Spezialist mit Redis PubSub Event-Listener."""

    def __init__(self) -> None:
        super().__init__(
            name="glpi",
            system_prompt=GLPI_SYSTEM_PROMPT,
            tools=[
                create_ticket,
                get_ticket,
                search_tickets,
                update_ticket,
                close_ticket,
                add_followup,
                add_solution,
                search_users,
                list_groups,
                list_categories,
                get_ticket_stats,
            ],
        )

        # Auto-Incident-Ticket-Erstellung starten
        auto_create = os.environ.get("GLPI_AUTO_CREATE_INCIDENTS", "false").lower() == "true"
        if auto_create:
            asyncio.get_event_loop().create_task(self._listen_for_incidents())
            logger.info("GLPI Auto-Incident-Erstellung aktiviert.")

    async def _listen_for_incidents(self) -> None:
        """
        Lauscht auf Redis PubSub Events von anderen Modulen.
        Bei incident_detected Events: automatisch GLPI-Ticket erstellen.
        """
        redis = get_redis()
        pubsub = await redis.subscribe_events()

        logger.info("GLPI Event-Listener gestartet.")

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

            except Exception as exc:
                logger.error("GLPI Event-Listener Fehler: %s", exc)
                await asyncio.sleep(5)

    async def _handle_event(self, event: dict) -> None:
        """Verarbeitet ein eingehendes Event."""
        event_type = event.get("event_type", "")
        severity = event.get("severity", "")

        if event_type == "incident_detected" and severity in ("critical", "high"):
            source = event.get("source_module", "unknown")
            data = event.get("data", {})

            title = f"[Auto] {source.upper()} Incident: {data.get('error', data.get('namespace', 'Fehler erkannt'))}"
            description = (
                f"Automatisch erstelltes Ticket von Kumio.\n\n"
                f"Quell-Modul: {source}\n"
                f"Schweregrad: {severity}\n"
                f"Details:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
            )

            priority = 5 if severity == "critical" else 4

            try:
                result = await create_ticket.ainvoke({
                    "title": title,
                    "description": description,
                    "priority": priority,
                    "ticket_type": 1,  # Incident
                })
                logger.info(
                    "Auto-Ticket erstellt: %s → #%s",
                    title,
                    result.get("ticket_id", "?"),
                )
            except Exception as exc:
                logger.error("Auto-Ticket-Erstellung fehlgeschlagen: %s", exc)
