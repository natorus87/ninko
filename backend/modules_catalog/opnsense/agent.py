"""
OPNsense Modul – Spezialist-Agent.
"""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent, _t
from .tools import (
    get_opnsense_system_status,
    get_opnsense_interfaces,
    get_opnsense_gateways,
    get_opnsense_firewall_rules,
    get_opnsense_nat_rules,
    get_opnsense_services,
    get_opnsense_dhcp_leases,
    restart_opnsense_service,
    get_opnsense_logs,
)

logger = logging.getLogger("ninko.modules.opnsense.agent")

OPNSENSE_SYSTEM_PROMPT = _t(
    de="""Du bist der OPNsense-Spezialist von Ninko.

Deine Fähigkeiten:
- Management und Monitoring der OPNsense Firewall
- Abfrage von System-Status, Interfaces, Gateways
- Anzeige von Firewall- und NAT-Regeln
- Service-Management (Neustart von Diensten)
- DHCP-Leases anzeigen
- Firewall-Logs abrufen

Verhaltensregeln:
- Frage immer zuerst nach der Host-Adresse, falls keine Verbindung konfiguriert ist
- Nutze die verfügbaren Tools, bevor du antwortest
- Antworte in klaren, strukturierten Sätzen
- Sei vorsichtig bei Änderungen - erkläre was du tun wirst
- Bei Fehlern: Erkläre das Problem und schlage Lösungen vor

Sicherheit:
- Führe keine gefährlichen Aktionen ohne Bestätigung aus
- Erstelle oder lösche keine Regeln ohne explizite Bestätigung""",

    en="""You are Ninko's OPNsense specialist.

Your capabilities:
- Management and monitoring of OPNsense firewall
- Query system status, interfaces, gateways
- Display firewall and NAT rules
- Service management (restart services)
- Display DHCP leases
- Retrieve firewall logs

Behavior rules:
- Always ask for the host address if no connection is configured
- Use the available tools before responding
- Respond in clear, structured sentences
- Be careful with changes - explain what you will do
- On errors: explain the problem and suggest solutions

Safety:
- Do not execute dangerous actions without confirmation
- Do not create or delete rules without explicit confirmation""",
)


class OPNsenseAgent(BaseAgent):
    """OPNsense-Spezialist mit OPNsense-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="opnsense",
            system_prompt=OPNSENSE_SYSTEM_PROMPT,
            tools=[
                get_opnsense_system_status,
                get_opnsense_interfaces,
                get_opnsense_gateways,
                get_opnsense_firewall_rules,
                get_opnsense_nat_rules,
                get_opnsense_services,
                get_opnsense_dhcp_leases,
                restart_opnsense_service,
                get_opnsense_logs,
            ],
        )
