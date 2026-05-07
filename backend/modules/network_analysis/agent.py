"""Network Analysis Module – Agent."""

from __future__ import annotations

from agents.base_agent import BaseAgent

_SYSTEM_PROMPT = """
Du bist das Network Analysis Modul. Du kannst Netzwerk-Analysen für Webseiten und Server durchführen.

Verfügbare Tools:
- dns_lookup(hostname) — DNS-Lookup, gibt alle IP-Adressen zurück
- reverse_dns(ip_address) — Reverse-DNS, gibt Hostname zurück
- traceroute(hostname) — Netzwerkpfad anzeigen
- ping_host(hostname) — Erreichbarkeit prüfen
- get_network_info(hostname) — Alle Infos kompakt: IPs, Reverse-DNS, Host-Typ

Antworte in der Sprache des Benutzers. Nutze für Analysen immer die Tools,
nicht Web-Search. Präsentiere Ergebnisse strukturiert (Markdown-Tabellen wenn sinnvoll).
"""


class NetworkAnalysisAgent(BaseAgent):
    def __init__(self) -> None:
        from .tools import dns_lookup, reverse_dns, traceroute, ping_host, get_network_info

        super().__init__(
            name="network_analysis",
            system_prompt=_SYSTEM_PROMPT,
            tools=[dns_lookup, reverse_dns, traceroute, ping_host, get_network_info],
        )


agent = NetworkAnalysisAgent()
