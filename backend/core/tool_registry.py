"""
Zentrale Tool-Metadaten-Registry.

Speichert für jedes Tool: Modul, readonly-Flag, destructive-Flag,
required_bins (z.B. ["kubectl"]) und required_envs.

Verwendung:
    from core.tool_registry import get_tool_registry

    registry = get_tool_registry()
    registry.is_readonly("get_pods")         # True
    registry.is_available("kubectl_apply")   # False wenn kubectl fehlt
    registry.readonly_names()                # frozenset — von safeguard genutzt
"""

from __future__ import annotations

import ast
import os
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class ToolTier(str, Enum):
    """
    5-Level Permission Tier für deterministischen Safeguard-Check.

    Tier-Bedeutung:
      READONLY     — kein Nebeneffekt, nur lesen/suchen
      COMMUNICATE  — sendet Nachrichten nach außen (Email, Slack, Discord, Telegram)
      WRITE_DATA   — erstellt/ändert Daten (Tickets, Wiki, DNS-Einträge, Memory)
      WRITE_SYSTEM — ändert Infrastruktur (restart, scale, enable/disable)
      ADMIN        — destruktiv / irreversibel (delete, wipe, shutdown, purge)

    Vorteile gegenüber bool-Flags:
      - Deterministisch: O(1) Lookup, kein 8s LLM-Timeout
      - Granular: COMMUNICATE ist eine eigene Kategorie (wichtig für externe Channels)
      - Erweiterbar: externe Bot-Requests können auf WRITE_DATA gecapped werden
    """

    READONLY = "READONLY"
    COMMUNICATE = "COMMUNICATE"
    WRITE_DATA = "WRITE_DATA"
    WRITE_SYSTEM = "WRITE_SYSTEM"
    ADMIN = "ADMIN"


@dataclass(slots=True, frozen=True)
class ToolMetadata:
    """Metadaten für ein einzelnes Tool."""

    name: str
    module: str  # z.B. "kubernetes", "proxmox", "core"
    readonly: bool = False
    destructive: bool = False
    tier: ToolTier | None = None  # Wenn None, wird aus readonly/destructive inferiert
    required_bins: tuple[str, ...] = ()  # binaries die shutil.which() finden muss
    required_envs: tuple[str, ...] = ()  # env vars die gesetzt sein müssen


def _get_language() -> str:
    """Gibt den konfigurierten Sprach-Code zurück (gecacht, Fallback: 'de')."""
    try:
        from core.config import get_settings

        return get_settings().LANGUAGE
    except (ImportError, AttributeError):
        return "de"


def _t(
    de: str,
    en: str,
    fr: str = "",
    es: str = "",
    it: str = "",
    nl: str = "",
    pl: str = "",
    pt: str = "",
    ja: str = "",
    zh: str = "",
) -> str:
    """Liefert den lokalisierten Text passend zur konfigurierten Sprache."""
    lang = _get_language()
    translations = {
        "de": de,
        "en": en,
        "fr": fr or en,
        "es": es or en,
        "it": it or en,
        "nl": nl or en,
        "pl": pl or en,
        "pt": pt or en,
        "ja": ja or en,
        "zh": zh or en,
    }
    return translations.get(lang, en)


_TOOL_STATUS_LABELS: dict[str, str] = {
    "execute_code": _t(de="Führe Code aus", en="Executing code"),
    "get_available_languages": _t(
        de="Prüfe verfügbare Sprachen", en="Checking available languages"
    ),
    "get_cluster_status": _t(de="Lade Cluster-Status", en="Loading cluster status"),
    "get_all_pods": _t(de="Lade Pods", en="Loading pods"),
    "get_failing_pods": _t(de="Prüfe fehlerhafte Pods", en="Checking failing pods"),
    "list_namespaces": _t(de="Lade Namespaces", en="Loading namespaces"),
    "list_services": _t(de="Lade Services", en="Loading services"),
    "restart_pod": _t(de="Starte Pod neu", en="Restarting pod"),
    "rollout_restart": _t(
        de="Führe Rollout-Restart durch", en="Performing rollout restart"
    ),
    "scale_deployment": _t(de="Skaliere Deployment", en="Scaling deployment"),
    "get_recent_events": _t(de="Lade Cluster-Events", en="Loading cluster events"),
    "get_pihole_summary": _t(
        de="Lade Pi-hole Statistiken", en="Loading Pi-hole statistics"
    ),
    "get_query_log": _t(de="Lade DNS-Query-Log", en="Loading DNS query log"),
    "toggle_blocking": _t(de="Konfiguriere Blocking", en="Configuring blocking"),
    "add_domain_to_list": _t(de="Aktualisiere Domain-Liste", en="Updating domain list"),
    "remove_domain_from_list": _t(
        de="Aktualisiere Domain-Liste", en="Updating domain list"
    ),
    "update_gravity": _t(de="Aktualisiere Gravity", en="Updating gravity"),
    "flush_dns_cache": _t(de="Leere DNS-Cache", en="Flushing DNS cache"),
    "perform_web_search": _t(de="Durchsuche das Web", en="Searching the web"),
    "web_search": _t(de="Durchsuche das Web", en="Searching the web"),
    "execute_cli_command": _t(de="Führe CLI-Befehl aus", en="Executing CLI command"),
    "call_module_agent": _t(de="Rufe Modul-Agent auf", en="Calling module agent"),
    "run_pipeline": _t(de="Führe Pipeline aus", en="Running pipeline"),
    "create_linear_workflow": _t(de="Erstelle Workflow", en="Creating workflow"),
    "execute_workflow": _t(de="Führe Workflow aus", en="Executing workflow"),
    "remember_fact": _t(de="Speichere im Gedächtnis", en="Saving to memory"),
    "recall_memory": _t(de="Durchsuche Gedächtnis", en="Searching memory"),
    "forget_fact": _t(de="Suche zu löschende Fakten", en="Searching facts to forget"),
    "confirm_forget": _t(de="Lösche Fakten", en="Deleting facts"),
    "create_custom_agent": _t(de="Erstelle Agenten", en="Creating agent"),
    "install_skill": _t(de="Installiere Skill", en="Installing skill"),
    "get_fritzbox_status": _t(de="Lade FritzBox-Status", en="Loading FritzBox status"),
    "get_connected_devices": _t(
        de="Lade verbundene Geräte", en="Loading connected devices"
    ),
    "get_call_list": _t(de="Lade Anrufliste", en="Loading call list"),
    "get_ha_entities": _t(
        de="Lade Home Assistant Entitäten", en="Loading Home Assistant entities"
    ),
    "call_ha_service": _t(de="Steuere Gerät", en="Controlling device"),
    "get_dns_zones": _t(de="Lade DNS-Zonen", en="Loading DNS zones"),
    "get_zone_records": _t(de="Lade DNS-Einträge", en="Loading DNS records"),
    "create_dns_record": _t(de="Erstelle DNS-Eintrag", en="Creating DNS record"),
    "send_email": _t(de="Sende E-Mail", en="Sending email"),
    "fetch_emails": _t(de="Lade E-Mails", en="Fetching emails"),
    "send_telegram_message": _t(
        de="Sende Telegram-Nachricht", en="Sending Telegram message"
    ),
    "generate_image": _t(de="Generiere Bild", en="Generating image"),
    "checkmk_get_hosts": _t(de="Lade Hosts", en="Loading hosts"),
    "checkmk_get_services": _t(de="Lade Services", en="Loading services"),
    "checkmk_get_host_status": _t(de="Prüfe Host-Status", en="Checking host status"),
    "checkmk_get_service_status": _t(
        de="Prüfe Service-Status", en="Checking service status"
    ),
    "checkmk_get_alerts": _t(de="Lade Alarme", en="Loading alerts"),
    "checkmk_get_host_details": _t(de="Lade Host-Details", en="Loading host details"),
    "checkmk_get_service_details": _t(
        de="Lade Service-Details", en="Loading service details"
    ),
    "checkmk_search_hosts": _t(de="Suche Hosts", en="Searching hosts"),
    "checkmk_search_services": _t(de="Suche Services", en="Searching services"),
    "get_synology_system_info": _t(de="Lade System-Info", en="Loading system info"),
    "get_synology_storage": _t(de="Lade Storage", en="Loading storage"),
    "get_synology_packages": _t(de="Lade Pakete", en="Loading packages"),
    "get_synology_services": _t(de="Lade Services", en="Loading services"),
    "get_synology_tasks": _t(de="Lade Tasks", en="Loading tasks"),
    "restart_synology_service": _t(de="Starte Service neu", en="Restarting service"),
    "check_synology_updates": _t(de="Prüfe Updates", en="Checking updates"),
    "install_synology_update": _t(de="Installiere Update", en="Installing update"),
    "install_synology_package": _t(de="Installiere Paket", en="Installing package"),
    "uninstall_synology_package": _t(
        de="Deinstalliere Paket", en="Uninstalling package"
    ),
    "get_synology_network_info": _t(de="Lade Netzwerk-Info", en="Loading network info"),
    "get_synology_users": _t(de="Lade Benutzer", en="Loading users"),
    "get_synology_groups": _t(de="Lade Gruppen", en="Loading groups"),
    "create_synology_user": _t(de="Erstelle Benutzer", en="Creating user"),
    "delete_synology_user": _t(de="Lösche Benutzer", en="Deleting user"),
    "change_synology_user_password": _t(de="Ändere Passwort", en="Changing password"),
    "create_synology_group": _t(de="Erstelle Gruppe", en="Creating group"),
    "add_user_to_group": _t(
        de="Füge User zu Entra-Gruppe hinzu", en="Adding user to Entra group"
    ),
    "remove_user_from_group": _t(
        de="Entferne User von Gruppe", en="Removing user from group"
    ),
    "shutdown_synologyNAS": _t(de="Fahre NAS herunter", en="Shutting down NAS"),
    "reboot_synologyNAS": _t(de="Boote NAS neu", en="Rebooting NAS"),
    "get_ilo_info": _t(de="Lade iLO-Info", en="Loading iLO info"),
    "get_server_info": _t(de="Lade Server-Info", en="Loading server info"),
    "get_server_thermal": _t(de="Lade Thermal", en="Loading thermal"),
    "get_server_power": _t(de="Lade Power", en="Loading power"),
    "get_ilo_nics": _t(de="Lade Netzwerk", en="Loading network"),
    "get_ilo_eventlog": _t(de="Lade Events", en="Loading events"),
    "server_power_on": _t(de="Schalte Server ein", en="Powering on server"),
    "server_power_off": _t(de="Schalte Server aus", en="Powering off server"),
    "server_reset_ilo": _t(de="Reset iLO", en="Resetting iLO"),
    "server_press_boot_button": _t(de="Boot-Button", en="Pressing boot button"),
    "list_entra_users": _t(de="Lade Benutzer", en="Loading users"),
    "search_entra_user": _t(de="Suche Benutzer", en="Searching user"),
    "get_user_details": _t(de="Lade Benutzerdetails", en="Loading user details"),
    "list_entra_groups": _t(de="Lade Gruppen", en="Loading groups"),
    "get_group_members": _t(de="Lade Gruppenmitglieder", en="Loading group members"),
    "list_entra_applications": _t(de="Lade Anwendungen", en="Loading applications"),
    "list_entra_devices": _t(de="Lade Geräte", en="Loading devices"),
    "create_entra_user": _t(de="Erstelle Benutzer", en="Creating user"),
    "disable_entra_user": _t(de="Deaktiviere Benutzer", en="Disabling user"),
    "reset_entra_user_password": _t(
        de="Setze Passwort zurück", en="Resetting password"
    ),
    "create_entra_group": _t(de="Erstelle Gruppe", en="Creating group"),
    "list_intune_devices": _t(de="Lade Geräte", en="Loading devices"),
    "get_intune_device": _t(de="Lade Gerätedetails", en="Loading device details"),
    "list_intune_policies": _t(de="Lade Richtlinien", en="Loading policies"),
    "list_intune_compliance_policies": _t(
        de="Lade Compliance", en="Loading compliance"
    ),
    "list_intune_apps": _t(de="Lade Apps", en="Loading apps"),
    "get_intune_device_compliance": _t(de="Prüfe Compliance", en="Checking compliance"),
    "wipe_intune_device": _t(de="Wipe Gerät", en="Wiping device"),
    "retire_intune_device": _t(de="Retire Gerät", en="Retiring device"),
    "sync_intune_device": _t(de="Sync Gerät", en="Syncing device"),
    "locate_intune_device": _t(de="Lokalisiere Gerät", en="Locating device"),
    "list_slack_channels": _t(de="Lade Channels", en="Loading channels"),
    "list_slack_users": _t(de="Lade Benutzer", en="Loading users"),
    "get_slack_channel_history": _t(de="Lade Historie", en="Loading history"),
    "search_slack_messages": _t(de="Suche Nachrichten", en="Searching messages"),
    "send_slack_message": _t(de="Sende Nachricht", en="Sending message"),
    "send_slack_dm": _t(de="Sende DM", en="Sending DM"),
    "upload_slack_file": _t(de="Lade Datei hoch", en="Uploading file"),
    "create_slack_channel": _t(de="Erstelle Channel", en="Creating channel"),
    "invite_user_to_channel": _t(de="Lade Benutzer ein", en="Inviting user"),
    "list_xclarity_servers": _t(de="Lade Server", en="Loading servers"),
    "get_xclarity_server_details": _t(
        de="Lade Serverdetails", en="Loading server details"
    ),
    "list_xclarity_chassis": _t(de="Lade Chassis", en="Loading chassis"),
    "list_xclarity_storage": _t(de="Lade Storage", en="Loading storage"),
    "get_xclarity_server_health": _t(de="Prüfe Gesundheit", en="Checking health"),
    "list_xclarity_events": _t(de="Lade Events", en="Loading events"),
    "get_xclarity_firmware": _t(de="Lade Firmware", en="Loading firmware"),
    "power_on_xclarity_server": _t(de="Schalte Server ein", en="Powering on server"),
    "power_off_xclarity_server": _t(de="Schalte Server aus", en="Powering off server"),
    "restart_xclarity_server": _t(de="Neustart Server", en="Restarting server"),
    "identify_xclarity_server": _t(de="Identifiziere Server", en="Identifying server"),
    "list_openproject_projects": _t(de="Lade Projekte", en="Loading projects"),
    "get_openproject_project": _t(de="Lade Projekt", en="Loading project"),
    "list_openproject_work_packages": _t(de="Lade Tasks", en="Loading work packages"),
    "get_openproject_work_package": _t(
        de="Lade Task-Details", en="Loading task details"
    ),
    "list_openproject_users": _t(de="Lade Benutzer", en="Loading users"),
    "list_openproject_time_entries": _t(
        de="Lade Zeitbuchungen", en="Loading time entries"
    ),
    "create_openproject_work_package": _t(de="Erstelle Task", en="Creating task"),
    "update_openproject_work_package": _t(de="Aktualisiere Task", en="Updating task"),
    "log_openproject_time": _t(de="Buche Zeit", en="Logging time"),
    "list_nextcloud_files": _t(de="Lade Dateien", en="Loading files"),
    "search_nextcloud_files": _t(de="Suche Dateien", en="Searching files"),
    "list_nextcloud_users": _t(de="Lade Benutzer", en="Loading users"),
    "get_nextcloud_user": _t(de="Lade Benutzerdetails", en="Loading user details"),
    "list_nextcloud_shares": _t(de="Lade Shares", en="Loading shares"),
    "get_nextcloud_storage": _t(de="Lade Speicher", en="Loading storage"),
    "create_nextcloud_folder": _t(de="Erstelle Ordner", en="Creating folder"),
    "upload_nextcloud_file": _t(de="Lade Datei hoch", en="Uploading file"),
    "delete_nextcloud_file": _t(de="Lösche Datei", en="Deleting file"),
    "create_nextcloud_share": _t(de="Erstelle Share", en="Creating share"),
    "create_nextcloud_user": _t(de="Erstelle Benutzer", en="Creating user"),
    "get_cisco_device_info": _t(de="Lade Geräteinfo", en="Loading device info"),
    "list_cisco_interfaces": _t(de="Lade Interfaces", en="Loading interfaces"),
    "get_cisco_interface_details": _t(
        de="Lade Interface-Details", en="Loading interface details"
    ),
    "list_cisco_vlans": _t(de="Lade VLANs", en="Loading VLANs"),
    "list_cisco_routes": _t(de="Lade Routen", en="Loading routes"),
    "list_cisco_mac_addresses": _t(de="Lade MAC-Table", en="Loading MAC table"),
    "get_cisco_poe_status": _t(de="Lade PoE-Status", en="Loading PoE status"),
    "enable_cisco_interface": _t(de="Aktiviere Interface", en="Enabling interface"),
    "disable_cisco_interface": _t(de="Deaktiviere Interface", en="Disabling interface"),
    "create_cisco_vlan": _t(de="Erstelle VLAN", en="Creating VLAN"),
    "set_cisco_interface_vlan": _t(de="Setze VLAN", en="Setting VLAN"),
    "get_mikrotik_identity": _t(de="Lade Geräteinfo", en="Loading device info"),
    "list_mikrotik_interfaces": _t(de="Lade Interfaces", en="Loading interfaces"),
    "get_mikrotik_interface_stats": _t(
        de="Lade Interface-Stats", en="Loading interface stats"
    ),
    "list_mikrotik_routes": _t(de="Lade Routen", en="Loading routes"),
    "list_mikrotik_dhcp_leases": _t(de="Lade DHCP-Leases", en="Loading DHCP leases"),
    "list_mikrotik_firewall_rules": _t(de="Lade Firewall", en="Loading firewall rules"),
    "list_mikrotik_queues": _t(de="Lade Queues", en="Loading queues"),
    "list_mikrotik_wireless_clients": _t(
        de="Lade Wireless-Clients", en="Loading wireless clients"
    ),
    "enable_mikrotik_interface": _t(de="Aktiviere Interface", en="Enabling interface"),
    "disable_mikrotik_interface": _t(
        de="Deaktiviere Interface", en="Disabling interface"
    ),
    "reboot_mikrotik": _t(de="Neustart Router", en="Rebooting router"),
    "create_mikrotik_firewall_rule": _t(
        de="Erstelle Firewall-Regel", en="Creating firewall rule"
    ),
    "add_mikrotik_ip_address": _t(de="Füge IP hinzu", en="Adding IP address"),
    "get_netgear_sysinfo": _t(de="Lade Geräteinfo", en="Loading device info"),
    "list_netgear_ports": _t(de="Lade Ports", en="Loading ports"),
    "list_netgear_vlans": _t(de="Lade VLANs", en="Loading VLANs"),
    "get_netgear_port_stats": _t(de="Lade Port-Stats", en="Loading port stats"),
    "list_netgear_arp": _t(de="Lade ARP", en="Loading ARP"),
    "list_netgear_lldp": _t(de="Lade LLDP", en="Loading LLDP"),
    "enable_netgear_port": _t(de="Aktiviere Port", en="Enabling port"),
    "disable_netgear_port": _t(de="Deaktiviere Port", en="Disabling port"),
    "reboot_netgear": _t(de="Neustart Gerät", en="Rebooting device"),
    "list_ubiquiti_devices": _t(de="Lade Geräte", en="Loading devices"),
    "list_ubiquiti_clients": _t(de="Lade Clients", en="Loading clients"),
    "get_ubiquiti_device": _t(de="Lade Gerätedetails", en="Loading device details"),
    "list_ubiquiti_wlans": _t(de="Lade WLANs", en="Loading WLANs"),
    "list_ubiquiti_switch_ports": _t(de="Lade Ports", en="Loading ports"),
    "get_ubiquiti_network_stats": _t(
        de="Lade Netzwerk-Stats", en="Loading network stats"
    ),
    "list_ubiquiti_firewall_rules": _t(de="Lade Firewall", en="Loading firewall rules"),
    "restart_ubiquiti_device": _t(de="Neustart Gerät", en="Restarting device"),
    "enable_ubiquiti_wlan": _t(de="Aktiviere WLAN", en="Enabling WLAN"),
    "disable_ubiquiti_wlan": _t(de="Deaktiviere WLAN", en="Disabling WLAN"),
    "kick_ubiquiti_client": _t(de="Trenne Client", en="Kicking client"),
    "get_redmine_projects": _t(de="Lade Projekte", en="Loading projects"),
    "get_redmine_project": _t(de="Lade Projekt", en="Loading project"),
    "get_redmine_issues": _t(de="Lade Tickets", en="Loading issues"),
    "get_redmine_issue": _t(de="Lade Ticket", en="Loading issue"),
    "create_redmine_issue": _t(de="Erstelle Ticket", en="Creating issue"),
    "update_redmine_issue": _t(de="Aktualisiere Ticket", en="Updating issue"),
    "get_redmine_users": _t(de="Lade Benutzer", en="Loading users"),
    "get_redmine_time_entries": _t(de="Lade Zeiten", en="Loading time entries"),
    "log_redmine_time": _t(de="Logge Zeit", en="Logging time"),
    "get_redmine_issue_statuses": _t(de="Lade Status", en="Loading statuses"),
    "get_redmine_priorities": _t(de="Lade Prioritäten", en="Loading priorities"),
    "search_redmine_issues": _t(de="Suche Tickets", en="Searching issues"),
    "get_redmine_issue_counts": _t(de="Zähle Tickets", en="Counting issues"),
    "create_ticket": _t(de="Erstelle Ticket", en="Creating ticket"),
    "get_ticket": _t(de="Lade Ticket", en="Loading ticket"),
    "search_tickets": _t(de="Suche Tickets", en="Searching tickets"),
    "update_ticket": _t(de="Aktualisiere Ticket", en="Updating ticket"),
    "close_ticket": _t(de="Schließe Ticket", en="Closing ticket"),
    "add_followup": _t(de="Füge Follow-up hinzu", en="Adding follow-up"),
    "add_solution": _t(de="Füge Lösung hinzu", en="Adding solution"),
    "search_users": _t(de="Suche Benutzer", en="Searching users"),
    "list_groups": _t(de="Lade Gruppen", en="Loading groups"),
    "list_categories": _t(de="Lade Kategorien", en="Loading categories"),
    "get_ticket_stats": _t(de="Lade Statistik", en="Loading stats"),
    "get_ticket_attachments": _t(de="Lade Anhänge", en="Loading attachments"),
    "get_ticket_followups": _t(de="Lade Antworten", en="Loading replies"),
    "get_ticket_solutions": _t(de="Lade Lösungen", en="Loading solutions"),
    "get_confluence_spaces": _t(de="Lade Spaces", en="Loading spaces"),
    "get_confluence_space": _t(de="Lade Space", en="Loading space"),
    "get_confluence_pages": _t(de="Lade Seiten", en="Loading pages"),
    "get_confluence_page": _t(de="Lade Seite", en="Loading page"),
    "create_confluence_page": _t(de="Erstelle Seite", en="Creating page"),
    "update_confluence_page": _t(de="Aktualisiere Seite", en="Updating page"),
    "get_confluence_blog_posts": _t(de="Lade Blog-Posts", en="Loading blog posts"),
    "create_confluence_blog_post": _t(de="Erstelle Blog-Post", en="Creating blog post"),
    "search_confluence": _t(de="Suche Confluence", en="Searching Confluence"),
    "get_confluence_labels": _t(de="Lade Labels", en="Loading labels"),
    "get_confluence_page_history": _t(de="Lade Historie", en="Loading history"),
    "get_jira_projects": _t(de="Lade Projekte", en="Loading projects"),
    "get_jira_project": _t(de="Lade Projekt", en="Loading project"),
    "get_jira_issues": _t(de="Lade Issues", en="Loading issues"),
    "get_jira_issue": _t(de="Lade Issue", en="Loading issue"),
    "create_jira_issue": _t(de="Erstelle Issue", en="Creating issue"),
    "update_jira_issue": _t(de="Aktualisiere Issue", en="Updating issue"),
    "get_jira_boards": _t(de="Lade Boards", en="Loading boards"),
    "get_jira_sprints": _t(de="Lade Sprints", en="Loading sprints"),
    "get_jira_sprint": _t(de="Lade Sprint", en="Loading sprint"),
    "search_jira": _t(de="Suche Jira", en="Searching Jira"),
    "get_jira_issue_transitions": _t(de="Lade Transitions", en="Loading transitions"),
    "transition_jira_issue": _t(de="Transitioniere Issue", en="Transitioning issue"),
    "get_jira_priorities": _t(de="Lade Prioritäten", en="Loading priorities"),
    "get_jira_issue_counts": _t(de="Zähle Issues", en="Counting issues"),
    "get_discord_guild_info": _t(de="Lade Server-Info", en="Loading server info"),
    "list_discord_channels": _t(de="Lade Kanäle", en="Loading channels"),
    "list_discord_members": _t(de="Lade Mitglieder", en="Loading members"),
    "send_discord_message": _t(de="Sende Nachricht", en="Sending message"),
    "create_discord_channel": _t(de="Erstelle Kanal", en="Creating channel"),
    "get_discord_channel_messages": _t(de="Lade Nachrichten", en="Loading messages"),
    "search_discord_messages": _t(de="Suche Nachrichten", en="Searching messages"),
    "delete_discord_channel": _t(de="Lösche Kanal", en="Deleting channel"),
    "get_zabbix_status": _t(de="Lade Status", en="Loading status"),
    "list_zabbix_hosts": _t(de="Lade Hosts", en="Loading hosts"),
    "get_zabbix_host": _t(de="Lade Host", en="Loading host"),
    "list_zabbix_items": _t(de="Lade Items", en="Loading items"),
    "list_zabbix_triggers": _t(de="Lade Trigger", en="Loading triggers"),
    "get_zabbix_problems": _t(de="Lade Probleme", en="Loading problems"),
    "list_zabbix_graphs": _t(de="Lade Graphen", en="Loading graphs"),
    "list_zabbix_actions": _t(de="Lade Actions", en="Loading actions"),
    "get_zabbix_history": _t(de="Lade History", en="Loading history"),
    "get_zabbix_host_group": _t(de="Lade Gruppen", en="Loading groups"),
    "list_zabbix_templates": _t(de="Lade Templates", en="Loading templates"),
    "create_zabbix_host": _t(de="Erstelle Host", en="Creating host"),
    "delete_zabbix_host": _t(de="Lösche Host", en="Deleting host"),
    "get_netbox_status": _t(de="Lade Status", en="Loading status"),
    "list_netbox_sites": _t(de="Lade Sites", en="Loading sites"),
    "get_netbox_site": _t(de="Lade Site", en="Loading site"),
    "list_netbox_devices": _t(de="Lade Devices", en="Loading devices"),
    "get_netbox_device": _t(de="Lade Device", en="Loading device"),
    "list_netbox_racks": _t(de="Lade Racks", en="Loading racks"),
    "get_netbox_rack": _t(de="Lade Rack", en="Loading rack"),
    "list_netbox_vlans": _t(de="Lade VLANs", en="Loading VLANs"),
    "list_netbox_prefixes": _t(de="Lade Prefixes", en="Loading prefixes"),
    "list_netbox_ip_addresses": _t(de="Lade IPs", en="Loading IPs"),
    "list_netbox_circuits": _t(de="Lade Circuits", en="Loading circuits"),
    "list_netbox_cables": _t(de="Lade Kabel", en="Loading cables"),
    "list_netbox_clusters": _t(de="Lade Cluster", en="Loading clusters"),
    "get_netbox_device_interfaces": _t(de="Lade Interfaces", en="Loading interfaces"),
    "get_gitlab_status": _t(de="Lade Status", en="Loading status"),
    "list_gitlab_projects": _t(de="Lade Projekte", en="Loading projects"),
    "get_gitlab_project": _t(de="Lade Projekt", en="Loading project"),
    "list_gitlab_pipelines": _t(de="Lade Pipelines", en="Loading pipelines"),
    "get_gitlab_pipeline": _t(de="Lade Pipeline", en="Loading pipeline"),
    "trigger_gitlab_pipeline": _t(de="Starte Pipeline", en="Triggering pipeline"),
    "cancel_gitlab_pipeline": _t(de="Breche Pipeline ab", en="Canceling pipeline"),
    "retry_gitlab_pipeline": _t(de="Wiederhole Pipeline", en="Retrying pipeline"),
    "list_gitlab_jobs": _t(de="Lade Jobs", en="Loading jobs"),
    "get_gitlab_job_log": _t(de="Lade Job-Log", en="Loading job log"),
    "list_gitlab_merge_requests": _t(de="Lade MRs", en="Loading merge requests"),
    "get_gitlab_merge_request": _t(de="Lade MR", en="Loading merge request"),
    "create_gitlab_merge_request": _t(de="Erstelle MR", en="Creating merge request"),
    "accept_gitlab_merge_request": _t(de="Akzeptiere MR", en="Accepting merge request"),
    "list_gitlab_branches": _t(de="Lade Branches", en="Loading branches"),
    "list_gitlab_commits": _t(de="Lade Commits", en="Loading commits"),
    "list_gitlab_tags": _t(de="Lade Tags", en="Loading tags"),
    "create_gitlab_release": _t(de="Erstelle Release", en="Creating release"),
    "list_gitlab_variables": _t(de="Lade Variablen", en="Loading variables"),
    "create_gitlab_variable": _t(de="Erstelle Variable", en="Creating variable"),
    "delete_gitlab_variable": _t(de="Lösche Variable", en="Deleting variable"),
    "get_gitlab_pipeline_schedules": _t(de="Lade Schedules", en="Loading schedules"),
    "create_gitlab_pipeline_schedule": _t(
        de="Erstelle Schedule", en="Creating schedule"
    ),
    "trigger_gitlab_pipeline_schedule": _t(
        de="Starte Schedule", en="Triggering schedule"
    ),
    "get_github_status": _t(de="Lade Status", en="Loading status"),
    "list_github_repos": _t(de="Lade Repos", en="Loading repos"),
    "get_github_repo": _t(de="Lade Repo", en="Loading repo"),
    "list_github_workflows": _t(de="Lade Workflows", en="Loading workflows"),
    "list_github_workflow_runs": _t(de="Lade Runs", en="Loading runs"),
    "get_github_workflow_run": _t(de="Lade Run", en="Loading run"),
    "trigger_github_workflow": _t(de="Starte Workflow", en="Triggering workflow"),
    "cancel_github_workflow_run": _t(de="Breche Run ab", en="Canceling run"),
    "rerun_github_workflow": _t(de="Starte Run neu", en="Re-running workflow"),
    "list_github_jobs": _t(de="Lade Jobs", en="Loading jobs"),
    "get_github_job_logs": _t(de="Lade Logs", en="Loading logs"),
    "list_github_pull_requests": _t(de="Lade PRs", en="Loading PRs"),
    "get_github_pull_request": _t(de="Lade PR", en="Loading PR"),
    "create_github_pull_request": _t(de="Erstelle PR", en="Creating PR"),
    "merge_github_pull_request": _t(de="Merged PR", en="Merging PR"),
    "list_github_issues": _t(de="Lade Issues", en="Loading issues"),
    "create_github_issue": _t(de="Erstelle Issue", en="Creating issue"),
    "list_github_branches": _t(de="Lade Branches", en="Loading branches"),
    "list_github_commits": _t(de="Lade Commits", en="Loading commits"),
    "list_github_tags": _t(de="Lade Tags", en="Loading tags"),
    "list_github_releases": _t(de="Lade Releases", en="Loading releases"),
    "create_github_release": _t(de="Erstelle Release", en="Creating release"),
    "list_github_variables": _t(de="Lade Variablen", en="Loading variables"),
    "create_github_variable": _t(de="Erstelle Variable", en="Creating variable"),
    "delete_github_variable": _t(de="Lösche Variable", en="Deleting variable"),
    "list_github_secrets": _t(de="Lade Secrets", en="Loading secrets"),
    "get_github_repo_content": _t(de="Lade Inhalt", en="Loading content"),
    "search_github_code": _t(de="Suche Code", en="Searching code"),
    "search_github_issues": _t(de="Suche Issues", en="Searching issues"),
    # ── DataViz ────────────────────────────────────────────────────────────
    "create_line_chart": _t(de="Erstelle Liniendiagramm", en="Creating line chart"),
    "create_bar_chart": _t(de="Erstelle Balkendiagramm", en="Creating bar chart"),
    "create_pie_chart": _t(de="Erstelle Kreisdiagramm", en="Creating pie chart"),
    "create_mermaid_diagram": _t(
        de="Erstelle Mermaid-Diagramm", en="Creating mermaid diagram"
    ),
    "create_interactive_chart_plotly": _t(
        de="Erstelle interaktives Diagramm", en="Creating interactive chart"
    ),
    "analyze_data_for_chart": _t(
        de="Analysiere Daten für Diagramm", en="Analyzing data for chart"
    ),
}


def get_tool_status_label(tool_name: str) -> str:
    """Liefert das UI-Statuslabel für ein Tool oder einen lesbaren Fallback."""
    label = _TOOL_STATUS_LABELS.get(tool_name)
    if label:
        return label
    return tool_name.replace("_", " ").title()


class ToolRegistry:
    """Zentrale Registry für Tool-Metadaten."""

    def __init__(self) -> None:
        """Initialisiert die Registry."""
        self._tools: dict[str, ToolMetadata] = {}

    def register(self, meta: ToolMetadata) -> None:
        """Registriert ein einzelnes Tool."""
        self._tools[meta.name] = meta

    def register_many(self, tools: list[ToolMetadata]) -> None:
        """Registriert mehrere Tools."""
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[ToolMetadata]:
        """Ruft Metadaten für ein Tool auf."""
        return self._tools.get(name)

    def is_readonly(self, name: str) -> bool | None:
        """Prüft ob ein Tool readonly ist.

        Returns:
            True wenn Tool registriert und readonly.
            False wenn Tool registriert und nicht readonly.
            None wenn Tool nicht registriert (Caller soll entscheiden).
        """
        meta = self.get(name)
        return meta.readonly if meta else None

    def is_destructive(self, name: str) -> bool:
        """Prüft ob ein Tool destructive ist."""
        meta = self.get(name)
        return meta.destructive if meta else False

    def is_available(self, name: str) -> bool:
        """
        Prüft ob alle required_bins (shutil.which) und required_envs gesetzt sind.

        Returns:
            True wenn Tool registriert und alle Abhängigkeiten erfüllt sind.
            False wenn Tool nicht registriert oder Abhängigkeiten fehlen.
        """
        meta = self.get(name)
        if not meta:
            return False

        # Prüfe required_bins
        for binary in meta.required_bins:
            if shutil.which(binary) is None:
                return False

        # Prüfe required_envs
        for env_var in meta.required_envs:
            if os.environ.get(env_var) is None:
                return False

        return True

    def readonly_names(self) -> frozenset[str]:
        """
        Alle readonly Tool-Namen als frozenset.

        Wird direkt von safeguard.py genutzt zur Klassifizierung von Tools.
        """
        return frozenset(name for name, meta in self._tools.items() if meta.readonly)

    def tier_of(self, name: str) -> ToolTier | None:
        """
        Gibt den effektiven Tier eines Tools zurück.

        Returns None wenn das Tool nicht registriert ist (→ LLM-Fallback).
        Bevorzugt explizites meta.tier, leitet sonst aus readonly/destructive ab.
        """
        meta = self.get(name)
        if meta is None:
            return None
        return _infer_tier(meta.name, meta.readonly, meta.destructive, meta.tier)

    def names_at_or_below(self, max_tier: ToolTier) -> frozenset[str]:
        """
        Alle Tool-Namen deren Tier ≤ max_tier ist (inkl. max_tier selbst).

        Tier-Reihenfolge (aufsteigend): READONLY < COMMUNICATE < WRITE_DATA < WRITE_SYSTEM < ADMIN
        Nützlich für externe Bot-Requests, die auf bestimmtem Tier gecapped werden.
        """
        order = [
            ToolTier.READONLY,
            ToolTier.COMMUNICATE,
            ToolTier.WRITE_DATA,
            ToolTier.WRITE_SYSTEM,
            ToolTier.ADMIN,
        ]
        allowed = set(order[: order.index(max_tier) + 1])
        return frozenset(
            name
            for name, meta in self._tools.items()
            if _infer_tier(meta.name, meta.readonly, meta.destructive, meta.tier)
            in allowed
        )

    def by_module(self, module: str) -> list[ToolMetadata]:
        """Alle Tools eines bestimmten Moduls."""
        return [meta for meta in self._tools.values() if meta.module == module]

    def all_tools(self) -> list[ToolMetadata]:
        """Alle registrierten Tools."""
        return list(self._tools.values())


# Singleton-Instanz
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """Gibt die globale ToolRegistry-Instanz zurück."""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _populate_default_registry(_registry)
        _discover_module_tools(_registry)
    return _registry


def _populate_default_registry(registry: ToolRegistry) -> None:
    """
    Vorpopuliert die Registry mit allen bekannten Tools aus safeguard.py.

    Alle Tools sind readonly=True (zum Schutz).
    Module mit required_bins:
    - kubernetes: requires kubectl
    - docker: requires docker
    """

    # ── Core Module ────────────────────────────────────────────────────────
    core_tools = [
        # READONLY — reine Leseoperationen
        ToolMetadata("recall_memory", "core", readonly=True),
        ToolMetadata("check_alert_state", "core", readonly=True),
        ToolMetadata("get_task", "core", readonly=True),
        ToolMetadata("list_tasks", "core", readonly=True),
        ToolMetadata("task_output", "core", readonly=True),
        ToolMetadata("get_routing_info", "core", readonly=True),
        ToolMetadata("list_scheduled_tasks", "core", readonly=True),
        # WRITE_DATA — schreibt Daten (Memory, Agenten, Skills, Workflows)
        ToolMetadata("remember_fact", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("forget_fact", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("confirm_forget", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("create_custom_agent", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("update_custom_agent", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("install_skill", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("create_dag_workflow", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("create_linear_workflow", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("create_scheduled_task", "core", tier=ToolTier.WRITE_DATA),
        ToolMetadata("generate_image", "core", tier=ToolTier.WRITE_DATA),
        # WRITE_SYSTEM — führt Aktionen aus / verändert Systemzustand
        ToolMetadata("execute_workflow", "core", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("run_pipeline", "core", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("run_parallel_pipeline", "core", tier=ToolTier.WRITE_SYSTEM),
        # ADMIN — destruktiv
        ToolMetadata("delete_scheduled_task", "core", destructive=True, tier=ToolTier.ADMIN),
    ]
    registry.register_many(core_tools)

    # ── Web Search ─────────────────────────────────────────────────────────
    web_search_tools = [
        ToolMetadata("perform_web_search", "web_search", readonly=True),
    ]
    registry.register_many(web_search_tools)

    # ── Kubernetes (requires kubectl) ──────────────────────────────────────
    kubernetes_tools = [
        ToolMetadata(
            "get_cluster_status",
            "kubernetes",
            readonly=True,
            required_bins=("kubectl",),
        ),
        ToolMetadata(
            "get_all_pods", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "get_failing_pods", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "list_namespaces", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "list_services", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "get_recent_events", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "get_resource_yaml", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "get_pod_logs", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "list_ingresses", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "list_pvcs", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "list_deployments", "kubernetes", readonly=True, required_bins=("kubectl",)
        ),
        ToolMetadata(
            "get_deployment_status",
            "kubernetes",
            readonly=True,
            required_bins=("kubectl",),
        ),
    ]
    registry.register_many(kubernetes_tools)

    # ── Proxmox ────────────────────────────────────────────────────────────
    proxmox_tools = [
        ToolMetadata("get_nodes", "proxmox", readonly=True),
        ToolMetadata("get_node_status", "proxmox", readonly=True),
        ToolMetadata("list_all_vms", "proxmox", readonly=True),
        ToolMetadata("list_vms", "proxmox", readonly=True),
        ToolMetadata("get_vm_status", "proxmox", readonly=True),
        ToolMetadata("get_vm_config", "proxmox", readonly=True),
        ToolMetadata("get_recent_tasks", "proxmox", readonly=True),
    ]
    registry.register_many(proxmox_tools)

    # ── PiHole ─────────────────────────────────────────────────────────────
    pihole_tools = [
        ToolMetadata("get_pihole_summary", "pihole", readonly=True),
        ToolMetadata("get_query_log", "pihole", readonly=True),
        ToolMetadata("get_top_domains", "pihole", readonly=True),
        ToolMetadata("get_top_clients", "pihole", readonly=True),
        ToolMetadata("get_blocklists", "pihole", readonly=True),
        ToolMetadata("get_pihole_system", "pihole", readonly=True),
        ToolMetadata("get_custom_dns_records", "pihole", readonly=True),
        ToolMetadata("get_cname_records", "pihole", readonly=True),
        ToolMetadata("get_dhcp_leases", "pihole", readonly=True),
        ToolMetadata("get_system_messages", "pihole", readonly=True),
        ToolMetadata("toggle_blocking", "pihole", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("update_gravity", "pihole", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("flush_dns_cache", "pihole", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("add_domain_to_list", "pihole", tier=ToolTier.WRITE_DATA),
        ToolMetadata("remove_domain_from_list", "pihole", tier=ToolTier.WRITE_DATA),
    ]
    registry.register_many(pihole_tools)

    # ── DataViz ────────────────────────────────────────────────────────────
    dataviz_tools = [
        ToolMetadata("create_line_chart", "dataviz", readonly=True),
        ToolMetadata("create_bar_chart", "dataviz", readonly=True),
        ToolMetadata("create_pie_chart", "dataviz", readonly=True),
        ToolMetadata("create_mermaid_diagram", "dataviz", readonly=True),
        ToolMetadata("create_interactive_chart_plotly", "dataviz", readonly=True),
        ToolMetadata("analyze_data_for_chart", "dataviz", readonly=True),
    ]
    registry.register_many(dataviz_tools)

    # ── FritzBox ────────────────────────────────────────────────────────────
    fritzbox_tools = [
        ToolMetadata("get_fritz_system_info", "fritzbox", readonly=True),
        ToolMetadata("get_fritz_devices", "fritzbox", readonly=True),
        ToolMetadata("get_fritz_wan_status", "fritzbox", readonly=True),
        ToolMetadata("get_fritz_bandwidth", "fritzbox", readonly=True),
        ToolMetadata("get_fritz_wlan_status", "fritzbox", readonly=True),
        ToolMetadata("get_fritz_smarthome_devices", "fritzbox", readonly=True),
        ToolMetadata("get_fritz_call_list", "fritzbox", readonly=True),
    ]
    registry.register_many(fritzbox_tools)

    # ── Home Assistant ──────────────────────────────────────────────────────
    homeassistant_tools = [
        ToolMetadata("ha_get_entity_state", "homeassistant", readonly=True),
        ToolMetadata("ha_list_entities", "homeassistant", readonly=True),
        ToolMetadata("ha_find_device", "homeassistant", readonly=True),
        ToolMetadata("ha_get_entity_details", "homeassistant", readonly=True),
    ]
    registry.register_many(homeassistant_tools)

    # ── IONOS DNS ───────────────────────────────────────────────────────────
    ionos_tools = [
        ToolMetadata("get_ionos_zones", "ionos", readonly=True),
        ToolMetadata("get_ionos_records", "ionos", readonly=True),
    ]
    registry.register_many(ionos_tools)

    # ── Email ───────────────────────────────────────────────────────────────
    email_tools = [
        ToolMetadata("read_emails", "email", readonly=True),
        ToolMetadata("send_email", "email", tier=ToolTier.COMMUNICATE),
        ToolMetadata("fetch_emails", "email", readonly=True),
    ]
    registry.register_many(email_tools)

    # ── Messaging (externe Kanäle) ──────────────────────────────────────────
    # Explizit als COMMUNICATE registriert damit tier_of() O(1) zurückgibt
    # (sonst: _discover_module_tools Fallback oder None → LLM-Fallback)
    messaging_tools = [
        ToolMetadata("send_telegram_message", "telegram", tier=ToolTier.COMMUNICATE),
        ToolMetadata("send_slack_message", "slack", tier=ToolTier.COMMUNICATE),
        ToolMetadata("send_slack_dm", "slack", tier=ToolTier.COMMUNICATE),
        ToolMetadata("upload_slack_file", "slack", tier=ToolTier.COMMUNICATE),
        ToolMetadata("create_slack_channel", "slack", tier=ToolTier.COMMUNICATE),
        ToolMetadata("invite_user_to_channel", "slack", tier=ToolTier.COMMUNICATE),
        ToolMetadata("send_discord_message", "discord", tier=ToolTier.COMMUNICATE),
        ToolMetadata("create_discord_channel", "discord", tier=ToolTier.COMMUNICATE),
    ]
    registry.register_many(messaging_tools)

    # ── GLPI ─────────────────────────────────────────────────────────────────
    glpi_tools = [
        ToolMetadata("get_ticket", "glpi", readonly=True),
        ToolMetadata("search_tickets", "glpi", readonly=True),
        ToolMetadata("search_users", "glpi", readonly=True),
        ToolMetadata("list_groups", "glpi", readonly=True),
        ToolMetadata("list_categories", "glpi", readonly=True),
        ToolMetadata("get_ticket_stats", "glpi", readonly=True),
        ToolMetadata("get_ticket_attachments", "glpi", readonly=True),
        ToolMetadata("get_ticket_followups", "glpi", readonly=True),
        ToolMetadata("get_ticket_solutions", "glpi", readonly=True),
    ]
    registry.register_many(glpi_tools)

    # ── WordPress ───────────────────────────────────────────────────────────
    wordpress_tools = [
        ToolMetadata("get_site_info", "wordpress", readonly=True),
        ToolMetadata("get_updates_info", "wordpress", readonly=True),
        ToolMetadata("list_plugins", "wordpress", readonly=True),
        ToolMetadata("search_plugins", "wordpress", readonly=True),
        ToolMetadata("list_posts", "wordpress", readonly=True),
        ToolMetadata("get_post", "wordpress", readonly=True),
        ToolMetadata("list_pages", "wordpress", readonly=True),
        ToolMetadata("get_page", "wordpress", readonly=True),
        ToolMetadata("list_tags", "wordpress", readonly=True),
        ToolMetadata("list_users", "wordpress", readonly=True),
        ToolMetadata("get_current_user", "wordpress", readonly=True),
        ToolMetadata("get_site_settings", "wordpress", readonly=True),
        ToolMetadata("list_media", "wordpress", readonly=True),
    ]
    registry.register_many(wordpress_tools)

    # ── Docker (requires docker) ────────────────────────────────────────────
    docker_tools = [
        ToolMetadata(
            "list_containers", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata(
            "inspect_container", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata(
            "get_container_logs", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata(
            "get_container_stats", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata("list_images", "docker", readonly=True, required_bins=("docker",)),
        ToolMetadata(
            "list_volumes", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata(
            "get_docker_info", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata(
            "get_docker_version", "docker", readonly=True, required_bins=("docker",)
        ),
        ToolMetadata(
            "get_docker_disk_usage", "docker", readonly=True, required_bins=("docker",)
        ),
    ]
    registry.register_many(docker_tools)

    # ── Linux Server ────────────────────────────────────────────────────────
    linux_server_tools = [
        ToolMetadata("get_system_info", "linux_server", readonly=True),
        ToolMetadata("get_disk_usage", "linux_server", readonly=True),
        ToolMetadata("get_top_processes", "linux_server", readonly=True),
        ToolMetadata("get_journal", "linux_server", readonly=True),
        ToolMetadata("get_logfile", "linux_server", readonly=True),
        ToolMetadata("read_file", "linux_server", readonly=True),
        ToolMetadata("list_directory", "linux_server", readonly=True),
        ToolMetadata("get_network_info", "linux_server", readonly=True),
        ToolMetadata("check_port", "linux_server", readonly=True),
        ToolMetadata("check_last_logins", "linux_server", readonly=True),
    ]
    registry.register_many(linux_server_tools)

    # ── OPNsense ────────────────────────────────────────────────────────────
    opnsense_tools = [
        # ── Read-only ──────────────────────────────────────────────────────────
        ToolMetadata("get_opnsense_system_status", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_interfaces", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_gateways", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_firewall_rules", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_nat_rules", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_services", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_dhcp_leases", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_logs", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_dhcp_settings", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_virtual_ips", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_firmware_info", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_firmware_status", "opnsense", readonly=True),
        ToolMetadata("get_opnsense_changelog", "opnsense", readonly=True),
        # ── WRITE_SYSTEM: mutates firewall/network config ──────────────────────
        ToolMetadata("create_opnsense_firewall_rule", "opnsense", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("create_opnsense_nat_rule", "opnsense", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("set_opnsense_interface", "opnsense", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("set_opnsense_dhcp", "opnsense", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("create_opnsense_virtual_ip", "opnsense", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("restart_opnsense_service", "opnsense", tier=ToolTier.WRITE_SYSTEM),
        # ── ADMIN: destructive / irreversible ─────────────────────────────────
        ToolMetadata("delete_opnsense_firewall_rule", "opnsense", destructive=True, tier=ToolTier.ADMIN),
        ToolMetadata("delete_opnsense_nat_rule", "opnsense", destructive=True, tier=ToolTier.ADMIN),
        ToolMetadata("delete_opnsense_virtual_ip", "opnsense", destructive=True, tier=ToolTier.ADMIN),
    ]
    registry.register_many(opnsense_tools)

    # ── Tasmota ─────────────────────────────────────────────────────────────
    tasmota_tools = [
        ToolMetadata("get_tasmota_status", "tasmota", readonly=True),
        ToolMetadata("get_tasmota_power", "tasmota", readonly=True),
        ToolMetadata("get_tasmota_sensors", "tasmota", readonly=True),
        ToolMetadata("get_tasmota_wifi_info", "tasmota", readonly=True),
    ]
    registry.register_many(tasmota_tools)

    # ── Qdrant ──────────────────────────────────────────────────────────────
    qdrant_tools = [
        ToolMetadata("search_knowledge", "qdrant", readonly=True),
        ToolMetadata("list_knowledge_collections", "qdrant", readonly=True),
        ToolMetadata("get_collection_stats", "qdrant", readonly=True),
        ToolMetadata("add_knowledge", "qdrant", tier=ToolTier.WRITE_DATA),
        ToolMetadata("add_knowledge_bulk", "qdrant", tier=ToolTier.WRITE_DATA),
        ToolMetadata("delete_knowledge_by_id", "qdrant", destructive=True, tier=ToolTier.ADMIN),
        ToolMetadata("delete_by_filter", "qdrant", destructive=True, tier=ToolTier.ADMIN),
    ]
    registry.register_many(qdrant_tools)

    # ── Codelab ─────────────────────────────────────────────────────────────
    codelab_tools = [
        ToolMetadata("get_available_languages", "codelab", readonly=True),
    ]
    registry.register_many(codelab_tools)

    # ── Check MK ────────────────────────────────────────────────────────────
    checkmk_tools = [
        ToolMetadata("checkmk_get_hosts", "checkmk", readonly=True),
        ToolMetadata("checkmk_get_services", "checkmk", readonly=True),
        ToolMetadata("checkmk_get_host_status", "checkmk", readonly=True),
        ToolMetadata("checkmk_get_service_status", "checkmk", readonly=True),
        ToolMetadata("checkmk_get_alerts", "checkmk", readonly=True),
        ToolMetadata("checkmk_get_host_details", "checkmk", readonly=True),
        ToolMetadata("checkmk_get_service_details", "checkmk", readonly=True),
        ToolMetadata("checkmk_search_hosts", "checkmk", readonly=True),
        ToolMetadata("checkmk_search_services", "checkmk", readonly=True),
    ]
    registry.register_many(checkmk_tools)

    # ── Synology ────────────────────────────────────────────────────────────
    synology_tools = [
        ToolMetadata("get_synology_system_info", "synology", readonly=True),
        ToolMetadata("get_synology_storage", "synology", readonly=True),
        ToolMetadata("get_synology_packages", "synology", readonly=True),
        ToolMetadata("get_synology_services", "synology", readonly=True),
        ToolMetadata("get_synology_tasks", "synology", readonly=True),
        ToolMetadata("check_synology_updates", "synology", readonly=True),
        ToolMetadata("get_synology_network_info", "synology", readonly=True),
        ToolMetadata("get_synology_users", "synology", readonly=True),
        ToolMetadata("get_synology_groups", "synology", readonly=True),
        ToolMetadata("install_synology_update", "synology", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("install_synology_package", "synology", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("uninstall_synology_package", "synology", tier=ToolTier.ADMIN),
        ToolMetadata("restart_synology_service", "synology", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("delete_synology_user", "synology", destructive=True, tier=ToolTier.ADMIN),
        ToolMetadata("create_synology_user", "synology", tier=ToolTier.WRITE_DATA),
        ToolMetadata("change_synology_user_password", "synology", tier=ToolTier.WRITE_SYSTEM),
        ToolMetadata("create_synology_group", "synology", tier=ToolTier.WRITE_DATA),
        ToolMetadata("shutdown_synologyNAS", "synology", destructive=True, tier=ToolTier.ADMIN),
        ToolMetadata("reboot_synologyNAS", "synology", tier=ToolTier.WRITE_SYSTEM),
    ]
    registry.register_many(synology_tools)

    # ── Redmine ─────────────────────────────────────────────────────────────
    redmine_tools = [
        ToolMetadata("get_redmine_projects", "redmine", readonly=True),
        ToolMetadata("get_redmine_project", "redmine", readonly=True),
        ToolMetadata("get_redmine_issues", "redmine", readonly=True),
        ToolMetadata("get_redmine_issue", "redmine", readonly=True),
        ToolMetadata("get_redmine_users", "redmine", readonly=True),
        ToolMetadata("get_redmine_time_entries", "redmine", readonly=True),
        ToolMetadata("get_redmine_issue_statuses", "redmine", readonly=True),
        ToolMetadata("get_redmine_priorities", "redmine", readonly=True),
        ToolMetadata("search_redmine_issues", "redmine", readonly=True),
        ToolMetadata("get_redmine_issue_counts", "redmine", readonly=True),
    ]
    registry.register_many(redmine_tools)

    # ── Confluence ──────────────────────────────────────────────────────────
    confluence_tools = [
        ToolMetadata("get_confluence_spaces", "confluence", readonly=True),
        ToolMetadata("get_confluence_space", "confluence", readonly=True),
        ToolMetadata("get_confluence_pages", "confluence", readonly=True),
        ToolMetadata("get_confluence_page", "confluence", readonly=True),
        ToolMetadata("get_confluence_blog_posts", "confluence", readonly=True),
        ToolMetadata("search_confluence", "confluence", readonly=True),
        ToolMetadata("get_confluence_labels", "confluence", readonly=True),
        ToolMetadata("get_confluence_page_history", "confluence", readonly=True),
    ]
    registry.register_many(confluence_tools)

    # ── Jira ────────────────────────────────────────────────────────────────
    jira_tools = [
        ToolMetadata("get_jira_projects", "jira", readonly=True),
        ToolMetadata("get_jira_project", "jira", readonly=True),
        ToolMetadata("get_jira_issues", "jira", readonly=True),
        ToolMetadata("get_jira_issue", "jira", readonly=True),
        ToolMetadata("get_jira_boards", "jira", readonly=True),
        ToolMetadata("get_jira_sprints", "jira", readonly=True),
        ToolMetadata("get_jira_sprint", "jira", readonly=True),
        ToolMetadata("search_jira", "jira", readonly=True),
        ToolMetadata("get_jira_issue_transitions", "jira", readonly=True),
        ToolMetadata("get_jira_priorities", "jira", readonly=True),
        ToolMetadata("get_jira_issue_counts", "jira", readonly=True),
    ]
    registry.register_many(jira_tools)


    # ── Message Hub ──────────────────────────────────────────────────────────
    message_hub_tools = [
        ToolMetadata("list_message_routes", "message_hub", readonly=True),
        ToolMetadata("get_message_hub_status", "message_hub", readonly=True),
        ToolMetadata("create_message_route", "message_hub", tier=ToolTier.WRITE_DATA),
        ToolMetadata("delete_message_route", "message_hub", destructive=True, tier=ToolTier.ADMIN),
    ]
    registry.register_many(message_hub_tools)


def _discover_module_tools(registry: ToolRegistry) -> None:
    """
    Discover @tool functions from modules_catalog/*/tools.py.

    New modules can expose optional literal dicts inside tools.py:
    - TOOL_REGISTRY_DEFAULTS = {"required_bins": (...), "required_envs": (...)}
    - TOOL_REGISTRY_OVERRIDES = {"tool_name": {"readonly": True, ...}}

    Existing explicit registry entries stay untouched. Discovery only fills gaps,
    so legacy/manual metadata can be migrated incrementally.
    """
    for discovery_root in _tool_source_roots():
        for tools_path in sorted(discovery_root.glob("*/tools.py")):
            module_id = tools_path.parent.name
            if module_id.startswith("_"):
                continue
            try:
                source = tools_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(tools_path))
                defaults = _extract_literal_dict(tree, "TOOL_REGISTRY_DEFAULTS")
                overrides = _extract_literal_dict(tree, "TOOL_REGISTRY_OVERRIDES")
            except (OSError, SyntaxError, ValueError) as exc:
                logger.warning("ToolRegistry discovery skipped %s: %s", tools_path, exc)
                continue

            for tool_name in _find_tool_functions(tree):
                if registry.get(tool_name):
                    continue

                override = overrides.get(tool_name, {})
                if not isinstance(override, dict):
                    logger.warning(
                        "ToolRegistry override for %s.%s ignored: expected dict, got %s",
                        module_id,
                        tool_name,
                        type(override).__name__,
                    )
                    override = {}

                readonly = bool(override.get("readonly", _infer_readonly(tool_name)))
                destructive = bool(
                    override.get("destructive", _infer_destructive(tool_name))
                )
                # Expliziter tier-Override aus TOOL_REGISTRY_OVERRIDES
                tier_raw = override.get("tier")
                explicit_tier: ToolTier | None = None
                if tier_raw is not None:
                    try:
                        explicit_tier = ToolTier(str(tier_raw).upper())
                    except ValueError:
                        logger.warning(
                            "ToolRegistry: ungültiger tier-Wert '%s' für %s.%s — ignoriert.",
                            tier_raw,
                            module_id,
                            tool_name,
                        )

                registry.register(
                    ToolMetadata(
                        name=tool_name,
                        module=str(override.get("module", module_id) or module_id),
                        readonly=readonly,
                        destructive=destructive,
                        tier=_infer_tier(tool_name, readonly, destructive, explicit_tier),
                        required_bins=_tuple_of_str(
                            override.get(
                                "required_bins", defaults.get("required_bins", ())
                            )
                        ),
                        required_envs=_tuple_of_str(
                            override.get(
                                "required_envs", defaults.get("required_envs", ())
                            )
                        ),
                    )
                )


def _tool_source_roots() -> list[Path]:
    roots: list[Path] = []
    seen: set[Path] = set()
    for parent in [Path(__file__).resolve().parent, *Path(__file__).resolve().parents]:
        for dirname in ("modules_catalog", "modules", "plugins"):
            candidate = parent / dirname
            if candidate.exists() and candidate.is_dir() and candidate not in seen:
                roots.append(candidate)
                seen.add(candidate)
    return roots


def _extract_literal_dict(tree: ast.AST, name: str) -> dict:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id == name:
                value = ast.literal_eval(node.value)
                if not isinstance(value, dict):
                    raise ValueError(f"{name} must be a dict literal")
                return value
    return {}


def _find_tool_functions(tree: ast.AST) -> list[str]:
    names: list[str] = []
    for node in getattr(tree, "body", []):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if any(_is_tool_decorator(dec) for dec in node.decorator_list):
            names.append(node.name)
    return names


def _is_tool_decorator(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "tool"
    if isinstance(node, ast.Attribute):
        return node.attr == "tool"
    if isinstance(node, ast.Call):
        return _is_tool_decorator(node.func)
    return False


def _tuple_of_str(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    return ()


def _infer_tier(
    name: str,
    readonly: bool,
    destructive: bool,
    explicit: ToolTier | None = None,
) -> ToolTier:
    """
    Leitet den effektiven ToolTier ab.

    Priorität:
      1. Expliziter tier-Parameter → direkt verwenden
      2. readonly=True → READONLY
      3. destructive=True → ADMIN
      4. Name-Prefix-Heuristik → COMMUNICATE / WRITE_DATA / WRITE_SYSTEM
      5. Fallback → WRITE_SYSTEM (konservativ)
    """
    if explicit is not None:
        return explicit
    if readonly:
        return ToolTier.READONLY

    # Name-Prefix-Heuristik hat Vorrang vor dem `destructive`-Bool,
    # da _infer_destructive() konservativ ist (restart_, stop_ etc. enthalten).
    # COMMUNICATE: externe Nachrichten senden
    _communicate_prefixes = ("send_", "post_", "notify_")
    _communicate_names = {
        "upload_slack_file",
        "create_slack_channel",
        "invite_user_to_channel",
        "create_discord_channel",
    }
    if name.startswith(_communicate_prefixes) or name in _communicate_names:
        return ToolTier.COMMUNICATE

    # WRITE_DATA: Daten erstellen/ändern (reversibel)
    _write_data_prefixes = (
        "create_",
        "update_",
        "log_",
        "add_",
        "transition_",
        "merge_",
        "accept_",
        "invite_",
        "upload_",
        "install_",
    )
    _write_data_names = {
        "close_ticket",
        "remember_fact",
        "forget_fact",
        "confirm_forget",
        "generate_image",
        "create_custom_agent",
        "update_custom_agent",
        "install_skill",
        "create_linear_workflow",
        "create_dag_workflow",
        "execute_workflow",
        "run_pipeline",
        "run_parallel_pipeline",
        "create_scheduled_task",
    }
    if name.startswith(_write_data_prefixes) or name in _write_data_names:
        return ToolTier.WRITE_DATA

    # ADMIN: destruktiv / irreversibel
    _admin_prefixes = (
        "delete_",
        "remove_",
        "wipe_",
        "retire_",
        "destroy_",
        "shutdown_",
        "purge_",
        "drop_",
        "flush_",
    )
    _admin_names = {
        "delete_scheduled_task",
        "kick_ubiquiti_client",
        "server_power_off",
    }
    if name.startswith(_admin_prefixes) or name in _admin_names:
        return ToolTier.ADMIN

    # WRITE_SYSTEM: Infrastruktur-Änderungen
    _write_system_prefixes = (
        "enable_",
        "disable_",
        "toggle_",
        "scale_",
        "restart_",
        "reboot_",
        "start_",
        "stop_",
        "apply_",
        "trigger_",
        "sync_",
        "execute_",
        "run_",
        "rotate_",
        "power_",
        "reset_",
        "cancel_",
        "rollout_",
        "change_",
        "set_",
    )
    _write_system_names = {
        "toggle_blocking",
        "update_gravity",
        "call_ha_service",
        "call_module_agent",
        "execute_cli_command",
    }
    if name.startswith(_write_system_prefixes) or name in _write_system_names:
        return ToolTier.WRITE_SYSTEM

    # Jetzt destructive-Bool als Fallback (nach Name-Prüfung)
    if destructive:
        return ToolTier.ADMIN

    return ToolTier.WRITE_SYSTEM  # konservativer Fallback


def _infer_readonly(tool_name: str) -> bool:
    readonly_prefixes = (
        "get_",
        "list_",
        "search_",
        "fetch_",
        "check_",
        "load_",
        "inspect_",
        "recall_",
    )
    readonly_names = {
        "perform_web_search",
        "web_search",
        "get_available_languages",
        "ha_find_device",
        "ha_get_entity_details",
        "ha_get_entity_state",
        "ha_list_entities",
    }
    return tool_name.startswith(readonly_prefixes) or tool_name in readonly_names


def _infer_destructive(tool_name: str) -> bool:
    destructive_prefixes = (
        "delete_",
        "remove_",
        "reboot_",
        "restart_",
        "stop_",
        "wipe_",
        "retire_",
        "shutdown_",
        "disable_",
        "reset_",
        "suspend_",
        "flush_",
    )
    destructive_names = {
        "accept_gitlab_merge_request",
        "close_ticket",
        "confirm_reboot",
        "kick_ubiquiti_client",
        "merge_github_pull_request",
    }
    return tool_name.startswith(destructive_prefixes) or tool_name in destructive_names


# ── ToolSpec: Erweitertes Schema für die Pipeline Engine ─────────────────────


from dataclasses import dataclass as _dataclass, field as _field
from typing import Any as _Any


@_dataclass(slots=True, frozen=True)
class ToolSpec:
    """
    Vollständige Spezifikation eines Tools für die Pipeline Engine.

    Ergänzt ToolMetadata um Input-/Output-Schemas, Bestätigungsanforderung,
    Timeout und Retry-Regeln. Wird von der PipelineEngine für Validierung
    und SafeGuard-Integration genutzt.
    """

    name: str
    module: str
    description: str = ""
    tier: "ToolTier" = ToolTier.WRITE_SYSTEM
    requires_confirmation: bool = False
    timeout_s: float = 120.0
    max_retries: int = 2
    input_schema: dict[str, _Any] = _field(default_factory=dict)
    output_schema: dict[str, _Any] = _field(default_factory=dict)

    @classmethod
    def from_metadata(cls, meta: "ToolMetadata") -> "ToolSpec":
        """Erstellt eine ToolSpec aus vorhandenen ToolMetadata."""
        tier = meta.tier or _infer_tier(meta.name, meta.destructive)
        requires_confirmation = tier in (ToolTier.ADMIN, ToolTier.WRITE_SYSTEM)
        return cls(
            name=meta.name,
            module=meta.module,
            tier=tier,
            requires_confirmation=requires_confirmation,
            timeout_s=180.0 if tier == ToolTier.ADMIN else 120.0,
            max_retries=0 if tier == ToolTier.ADMIN else 2,
        )


# ── Module-Level ToolSpec Registry ───────────────────────────────────────────

_tool_specs: dict[str, "ToolSpec"] = {}


def register_tool_spec(spec: "ToolSpec") -> None:
    """Registriert eine ToolSpec global."""
    _tool_specs[spec.name] = spec


def get_tool_spec(name: str) -> "ToolSpec | None":
    """Gibt die ToolSpec für ein Tool zurück, falls registriert."""
    return _tool_specs.get(name)


def get_or_infer_tool_spec(name: str, module: str = "unknown") -> "ToolSpec":
    """
    Gibt die ToolSpec zurück oder inferiert sie dynamisch aus dem Tool-Namen.
    Nutzt dieselbe Tier-Heuristik wie _infer_tier().
    """
    if name in _tool_specs:
        return _tool_specs[name]

    tier = _infer_tier(name, _infer_destructive(name))
    requires_confirmation = tier in (ToolTier.ADMIN, ToolTier.WRITE_SYSTEM, ToolTier.COMMUNICATE)
    return ToolSpec(
        name=name,
        module=module,
        tier=tier,
        requires_confirmation=requires_confirmation,
        timeout_s=180.0 if tier == ToolTier.ADMIN else 120.0,
        max_retries=0 if tier == ToolTier.ADMIN else 2,
    )
