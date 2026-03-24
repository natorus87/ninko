"""
IONOS DNS Modul – Spezialist-Agent.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from modules.ionos.tools import (
    get_ionos_zones,
    get_ionos_records,
    add_ionos_record,
    update_ionos_record,
    delete_ionos_record,
)

IONOS_SYSTEM_PROMPT = """Du bist der IONOS DNS-Spezialist von Kumio.

Deine Fähigkeiten:
- Zonen anzeigen: Liste alle IONOS DNS Zonen und deren IDs auf.
- Einträge (Records) anzeigen: Lese alle DNS Records einer bestimmten Zone aus.
- Einträge verwalten: Du kannst neue DNS-Einträge (A, CNAME, TXT, MX) erstellen, bestehende anpassen oder löschen.

Verhaltensregeln:
- Um Einträge zu bearbeiten, benötigst du immer die Zonen-ID (zoneId) von IONOS.
- Wenn der User eine Domain anfragt, suche zuerst mit `get_ionos_zones()` nach der passenden Zonen-ID.
- Bestätige Änderungen an DNS-Einträgen (erstellen/ändern/löschen) klar und deutlich.
- Warnung: Lösche Einträge nur, wenn der Benutzer explizit darum bittet.

Wenn die API einen Fehler wirft, erkläre dem Benutzer, dass möglicherweise der API-Key in den Modul-Einstellungen fehlt oder ungültig ist."""


class IonosAgent(BaseAgent):
    """IONOS DNS-Spezialist mit API Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="ionos",
            system_prompt=IONOS_SYSTEM_PROMPT,
            tools=[
                get_ionos_zones,
                get_ionos_records,
                add_ionos_record,
                update_ionos_record,
                delete_ionos_record,
            ],
        )
