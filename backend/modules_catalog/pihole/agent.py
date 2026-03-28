"""
Pi-hole Modul – Spezialist-Agent.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from .tools import (
    get_pihole_summary,
    get_query_log,
    get_top_domains,
    get_top_clients,
    toggle_blocking,
    get_blocklists,
    add_domain_to_list,
    remove_domain_from_list,
    get_pihole_system,
    get_custom_dns_records,
    add_custom_dns_record,
    remove_custom_dns_record,
    get_cname_records,
    add_cname_record,
    remove_cname_record,
    get_dhcp_leases,
    delete_dhcp_lease,
    update_gravity,
    flush_dns_cache,
    flush_logs,
    flush_network_table,
    get_system_messages,
    dismiss_system_message,
)

PIHOLE_SYSTEM_PROMPT = """Du bist der Pi-hole DNS-Spezialist von Ninko.

Deine Fähigkeiten:
- DNS-Statistiken: Blockierte Anfragen, Clients, Top-Domains
- Query-Log: Letzte DNS-Anfragen anzeigen und analysieren
- Blocking-Steuerung: DNS-Blocking aktivieren/deaktivieren (zeitlich begrenzt)
- Domain-Management: Domains auf White-/Blacklist setzen
- Blocklisten: Konfigurierte Adlists anzeigen
- System-Info: Pi-hole Version, Gravity-Status, Uptime

Verhaltensregeln:
- Zeige Statistiken übersichtlich mit Zahlen und Prozenten
- IMMER das passende Tool aufrufen – beschreibe NICHT was du tun würdest, führe es direkt aus
- Bei Blocking-Änderungen (`toggle_blocking`): SOFORT aufrufen, danach Auswirkungen erklären
- Bei Domain-Listen-Änderungen: SOFORT `add_domain_to_list` oder `remove_domain_from_list` aufrufen, dann bestätigen
- Verwende Emojis für bessere Übersichtlichkeit (🛡 Blockiert, ✅ Erlaubt, 🔍 Queries)
- Bei Gravity-Updates oder Flush-Befehlen: Weise darauf hin, dass diese etwas Zeit in Anspruch nehmen oder sofort den Cache leeren
- Wenn Pi-hole nicht konfiguriert ist, weise auf die Modul-Einstellungen hin

Bei DNS-Problemen:
- Prüfe zuerst den Pi-hole Status und System-Meldungen
- Analysiere die Query-Logs
- Prüfe ob die Domain blockiert (Adlist), weitergeleitet oder per CNAME/Local DNS aufgelöst wird
- Schlage ggf. White-/Blacklist-Anpassungen vor und setze sie direkt um wenn der User es bestätigt"""


class PiholeAgent(BaseAgent):
    """Pi-hole DNS-Spezialist mit allen Pi-hole-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="pihole",
            system_prompt=PIHOLE_SYSTEM_PROMPT,
            tools=[
                get_pihole_summary,
                get_query_log,
                get_top_domains,
                get_top_clients,
                toggle_blocking,
                get_blocklists,
                add_domain_to_list,
                remove_domain_from_list,
                get_pihole_system,
                get_custom_dns_records,
                add_custom_dns_record,
                remove_custom_dns_record,
                get_cname_records,
                add_cname_record,
                remove_cname_record,
                get_dhcp_leases,
                delete_dhcp_lease,
                update_gravity,
                flush_dns_cache,
                flush_logs,
                flush_network_table,
                get_system_messages,
                dismiss_system_message,
            ],
        )
