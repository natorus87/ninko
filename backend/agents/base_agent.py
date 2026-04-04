"""
Ninko BaseAgent – Abstrakte Basis für alle Agenten.
Nutzt LangGraph für Tool-Calling und Conversation-Management.
"""

from __future__ import annotations

import asyncio
import json as _json
import logging
import re
from typing import Any, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    from core.safeguard import SafeguardMiddleware

from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.prebuilt import create_react_agent

from core.llm_factory import get_llm, get_model_context_window, get_llm_generation
from core.memory import get_memory
from core.context_manager import get_context_manager
from core import status_bus

logger = logging.getLogger("ninko.agents.base")

_BASE_AGENT_RECOVERABLE_EXCEPTIONS = (
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
    KeyError,
    RuntimeError,
    OSError,
    _json.JSONDecodeError,
    asyncio.TimeoutError,
)


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
    """
    Returns text in the correct language based on LANGUAGE setting.
    Supports: de, en, fr, es, it, nl, pl, pt, ja, zh
    If a language is not provided, falls back to English.
    """
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


# ── Tool-Name → Status-Label (10 Sprachen via _t()) ──────────────────────────
_TOOL_LABELS: dict[str, str] = {
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
    # Synology
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
    "add_user_to_group": _t(de="Füge User zu Gruppe hinzu", en="Adding user to group"),
    "remove_user_from_group": _t(
        de="Entferne User von Gruppe", en="Removing user from group"
    ),
    "shutdown_synologyNAS": _t(de="Fahre NAS herunter", en="Shutting down NAS"),
    "reboot_synologyNAS": _t(de="Boote NAS neu", en="Rebooting NAS"),
    # HPE iLO
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
    # Microsoft Entra
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
    "add_user_to_group": _t(de="Füge User zu Gruppe", en="Adding user to group"),
    # Microsoft Intune
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
    # Slack
    "list_slack_channels": _t(de="Lade Channels", en="Loading channels"),
    "list_slack_users": _t(de="Lade Benutzer", en="Loading users"),
    "get_slack_channel_history": _t(de="Lade Historie", en="Loading history"),
    "search_slack_messages": _t(de="Suche Nachrichten", en="Searching messages"),
    "send_slack_message": _t(de="Sende Nachricht", en="Sending message"),
    "send_slack_dm": _t(de="Sende DM", en="Sending DM"),
    "upload_slack_file": _t(de="Lade Datei hoch", en="Uploading file"),
    "create_slack_channel": _t(de="Erstelle Channel", en="Creating channel"),
    "invite_user_to_channel": _t(de="Lade Benutzer ein", en="Inviting user"),
    # Lenovo XClarity
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
    # OpenProject
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
    # Nextcloud
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
    # Cisco
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
    # MikroTik
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
    # Netgear
    "get_netgear_sysinfo": _t(de="Lade Geräteinfo", en="Loading device info"),
    "list_netgear_ports": _t(de="Lade Ports", en="Loading ports"),
    "list_netgear_vlans": _t(de="Lade VLANs", en="Loading VLANs"),
    "get_netgear_port_stats": _t(de="Lade Port-Stats", en="Loading port stats"),
    "list_netgear_arp": _t(de="Lade ARP", en="Loading ARP"),
    "list_netgear_lldp": _t(de="Lade LLDP", en="Loading LLDP"),
    "enable_netgear_port": _t(de="Aktiviere Port", en="Enabling port"),
    "disable_netgear_port": _t(de="Deaktiviere Port", en="Disabling port"),
    "reboot_netgear": _t(de="Neustart Gerät", en="Rebooting device"),
    # Ubiquiti
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
    # Redmine
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
    # GLPI
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
    # Confluence
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
    # Jira
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
    # Discord
    "get_discord_guild_info": _t(de="Lade Server-Info", en="Loading server info"),
    "list_discord_channels": _t(de="Lade Kanäle", en="Loading channels"),
    "list_discord_members": _t(de="Lade Mitglieder", en="Loading members"),
    "send_discord_message": _t(de="Sende Nachricht", en="Sending message"),
    "create_discord_channel": _t(de="Erstelle Kanal", en="Creating channel"),
    "get_discord_channel_messages": _t(de="Lade Nachrichten", en="Loading messages"),
    "search_discord_messages": _t(de="Suche Nachrichten", en="Searching messages"),
    "delete_discord_channel": _t(de="Lösche Kanal", en="Deleting channel"),
    # Zabbix
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
}


class _StatusEmitter(AsyncCallbackHandler):
    """Emittiert Tool-Start-Events als Status-Updates an den Status-Bus."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id

    async def on_tool_start(self, serialized: dict, input_str: str, **kwargs) -> None:  # type: ignore[override]
        tool_name = serialized.get("name", "")
        label = _TOOL_LABELS.get(tool_name)
        if not label:
            label = tool_name.replace("_", " ").title()
        await status_bus.emit(self.session_id, f"{label}…")

    async def on_llm_start(self, serialized: dict, messages: list, **kwargs) -> None:  # type: ignore[override]
        await status_bus.emit(
            self.session_id,
            _t(
                de="Denke nach…",
                en="Thinking…",
                fr="Réfléchis…",
                es="Pensando…",
                it="Pensando…",
                nl="Denken…",
                pl="Myślę…",
                pt="Pensando…",
                ja="考え中…",
                zh="思考中…",
            ),
        )


_DEFAULT_AGENT_TIMEOUT_SECONDS = 1800
# Ab dieser Tool-Anzahl wird JIT Tool Injection aktiviert
_DEFAULT_JIT_THRESHOLD = 6
# Max. Tools nach JIT-Filterung (Kontext-Sparsamkeit)
_DEFAULT_JIT_MAX_TOOLS = 8

# Strong references to background tasks to prevent premature GC
_background_tasks: set[asyncio.Task] = set()

# Auto-Memorize Cooldown: (agent_name, session_id) → letzter Zeitstempel (monotonic)
_memorize_cooldowns: dict[tuple[str, str], float] = {}
_DEFAULT_MEMORIZE_COOLDOWN_SECS = 60.0  # Max 1 Auto-Memorize pro Minute pro Agent
# Agenten die kein Auto-Memorize brauchen (Background-Loops)
_MEMORIZE_EXCLUDED_AGENTS = {"monitor", "scheduler"}
_MEMORIZE_STOP_WORDS = {
    "NICHTS",
    "NOTHING",
    "RIEN",
    "NADA",
    "NULLA",
    "NIETS",
    "NIC",
    "何もない",
    "没有",
}

# ── Tool-level Safeguard (global, gesetzt von main.py via set_global_safeguard) ──
# Sentinel-String der in routes_chat.py erkannt wird wenn ein Tool-Call Bestätigung braucht
_TOOL_SAFEGUARD_SENTINEL = "__TOOL_SAFEGUARD__"

# Paused safeguard agents: session_id → (sg_agent, thread_config)
# Hält den unterbrochenen LangGraph-Agenten für den Resume-Aufruf am Leben.
_paused_sg_agents: dict[str, tuple] = {}
# Session-spezifische Locks verhindern parallele Safeguard-Runs/Resumes
_safeguard_session_locks: dict[str, asyncio.Lock] = {}

_global_safeguard: "SafeguardMiddleware | None" = None


def set_global_safeguard(sg: "SafeguardMiddleware") -> None:
    """Setzt die globale Safeguard-Instanz (wird von main.py aufgerufen)."""
    global _global_safeguard
    _global_safeguard = sg
    logger.info("Globale Safeguard-Instanz registriert.")


def _get_safeguard_session_lock(session_id: str) -> asyncio.Lock:
    """Gibt den Lock für eine Session zurück (lazy init)."""
    if session_id not in _safeguard_session_locks:
        _safeguard_session_locks[session_id] = asyncio.Lock()
    return _safeguard_session_locks[session_id]


def _get_agent_timeout_seconds() -> int:
    """Lädt den Agent-Timeout aus der Config mit robustem Fallback."""
    try:
        from core.config import get_settings

        timeout = int(get_settings().AGENT_TIMEOUT_SECONDS)
        return timeout if timeout > 0 else _DEFAULT_AGENT_TIMEOUT_SECONDS
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_AGENT_TIMEOUT_SECONDS


def _get_jit_threshold() -> int:
    """JIT-Schwelle aus zentraler Config laden (Fallback auf Default)."""
    try:
        from core.config import get_settings

        value = int(get_settings().AGENT_JIT_THRESHOLD)
        return max(1, value)
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_JIT_THRESHOLD


def _get_jit_max_tools() -> int:
    """Maximale Anzahl JIT-Tools aus zentraler Config laden (Fallback auf Default)."""
    try:
        from core.config import get_settings

        value = int(get_settings().AGENT_JIT_MAX_TOOLS)
        return max(1, value)
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_JIT_MAX_TOOLS


def _get_memorize_cooldown_secs() -> float:
    """Auto-Memorize-Cooldown aus zentraler Config laden (Fallback auf Default)."""
    try:
        from core.config import get_settings

        value = float(get_settings().AGENT_MEMORIZE_COOLDOWN_SECS)
        return max(0.0, value)
    except (ImportError, AttributeError, TypeError, ValueError):
        return _DEFAULT_MEMORIZE_COOLDOWN_SECS


# Sprachanweisungen für Language-Injection am Ende jedes System-Prompts
_LANG_INSTRUCTIONS: dict[str, str] = {
    "de": "Antworte immer auf Deutsch. Verwende passende Emojis in deinen Antworten, um sie lebendiger und übersichtlicher zu gestalten – z. B. am Anfang von Abschnitten, bei Status-Angaben oder zur Hervorhebung wichtiger Punkte.",
    "en": "Always respond in English. Use fitting emojis in your responses to make them more lively and clear – e.g. at the start of sections, for status indicators, or to highlight key points.",
    "fr": "Réponds toujours en français.",
    "es": "Responde siempre en español.",
    "it": "Rispondi sempre in italiano.",
    "nl": "Antwoord altijd in het Nederlands.",
    "pl": "Zawsze odpowiadaj po polsku.",
    "pt": "Responda sempre em português.",
    "ja": "常に日本語で回答してください。",
    "zh": "请始终用中文回答。",
}


def _extract_text(content: str | list) -> str:
    """Extrahiert reinen Text aus AIMessage/ToolMessage.content.

    LangChain liefert für multimodale Inhalte eine Liste von Dicts
    ({ "type": "text", "text": "..." } oder { "type": "image_url", ... }).
    Alle anderen Typen werden via str() konvertiert.
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(item.get("text", str(item)))
            else:
                parts.append(str(item))
        return "".join(parts)
    return str(content)


_RE_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)


def _strip_thinking(text: str) -> str:
    """Entfernt <think>...</think> Blöcke aus Thinking-Model-Antworten.

    Qwen3.5, DeepSeek-R1 und ähnliche Modelle generieren interne
    Überlegungen in <think>-Tags, die nicht an den User weitergegeben werden sollen.
    """
    return _RE_THINK.sub("", text).strip()


class BaseAgent:
    """
    Abstrakte Basis – alle Agenten erben hiervon.
    Kapselt LLM-Aufruf, Tool-Binding und Context-Management.
    """

    def __init__(
        self,
        name: str,
        system_prompt: str,
        tools: Sequence[BaseTool] | None = None,
    ) -> None:
        self.name = name
        self.system_prompt = system_prompt
        self.tools = list(tools or [])

        self._llm = get_llm()
        self._llm_generation = get_llm_generation()
        self._memory = get_memory()
        self._context_mgr = get_context_manager()

        # LangGraph ReAct Agent erstellen
        self._agent = create_react_agent(
            model=self._llm,
            tools=self.tools,
        )

        logger.info(
            "Agent '%s' initialisiert mit %d Tools.",
            self.name,
            len(self.tools),
        )

    def _select_tools_for_request(self, message: str) -> list[BaseTool]:
        """
        JIT Tool Injection (OpenClaw-Prinzip):
        Gibt nur die für diese Anfrage relevanten Tools zurück.
        Reduziert Kontext-Overhead bei Agenten mit vielen Tools.
        """
        jit_threshold = _get_jit_threshold()
        jit_max_tools = _get_jit_max_tools()

        if len(self.tools) <= jit_threshold:
            return self.tools

        msg_lower = message.lower()
        # Wörter mit mind. 2 Zeichen extrahieren (IT-Fachbegriffe wie IP, VM, K8s, HA, DNS)
        words = [
            w.strip(".,!?:;")
            for w in msg_lower.replace("-", " ").split()
            if len(w.strip(".,!?:;")) >= 2
        ]

        scored: list[tuple[int, BaseTool]] = []
        for t in self.tools:
            searchable = f"{t.name} {t.description or ''}".lower()
            score = sum(1 for w in words if w in searchable)
            scored.append((score, t))

        # Tools mit mindestens 1 Treffer
        relevant = [t for s, t in scored if s > 0]

        # Fallback: zu wenige gefunden → alle Tools zurückgeben
        if len(relevant) < 3:
            return self.tools

        # Sortiert nach Score, max. JIT-Max-Tools
        top = sorted(scored, key=lambda x: x[0], reverse=True)
        selected = [t for _, t in top[:jit_max_tools]]
        logger.debug(
            "JIT Tool Injection: Agent '%s' %d → %d Tools.",
            self.name,
            len(self.tools),
            len(selected),
        )
        return selected

    async def _dynamic_prompt_appendix(self) -> str:
        """Erzeugt dynamischen Kontext (z.B. Connections), der an den System-Prompt gehängt wird."""
        if self.name in ("orchestrator", "monitor", "scheduler"):
            return ""

        try:
            from core.connections import ConnectionManager

            conns = await ConnectionManager.list_connections(self.name)
            if not conns:
                return ""

            info = _t(
                "VERFÜGBARE VERBINDUNGEN FÜR DIESES MODUL:\n",
                "AVAILABLE CONNECTIONS FOR THIS MODULE:\n",
            )
            for c in conns:
                d = " [DEFAULT]" if c.is_default else ""
                info += f"- connection_id: '{c.id}' | Name: '{c.name}' | Env: '{c.environment}'{d}\n"

            info += _t(
                "\nWICHTIG: Nutze IMMER die passende 'connection_id' für Tools! "
                "Wenn der User keine Umgebung nennt, nutze die Default-Verbindung.",
                "\nIMPORTANT: ALWAYS use the appropriate 'connection_id' for tools! "
                "If the user does not specify an environment, use the default connection.",
            )
            return info
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as e:
            logger.warning("Fehler beim Laden der Connections für Prompt: %s", e)
            return ""

    async def invoke(
        self,
        message: str,
        chat_history: list[dict] | None = None,
        session_id: str = "",
        confirmed: bool = False,
    ) -> tuple[str, bool]:
        """
        Führt den Agenten mit einer Nachricht aus.

        Gibt (antwort, wurde_komprimiert) zurück.
        `wurde_komprimiert` ist True wenn der Kontext in diesem Aufruf
        per LLM-Summary komprimiert wurde — der Aufrufer kann dann eine
        System-Nachricht in die sichtbare Chat-History einfügen.

        1. Context-Window kalibrieren (einmalig, gecacht)
        2. Chat-History auf Token-Budget trimmen / komprimieren
        3. System-Prompt + History + aktuelle Nachricht zusammenbauen
        4. LangGraph Agent ausführen
        5. Antwort + Compaction-Flag zurückgeben
        """
        # Chat-History aufbereiten
        history = chat_history or []

        # LLM neu initialisieren wenn Provider gewechselt wurde
        current_gen = get_llm_generation()
        if current_gen != self._llm_generation:
            self._llm = get_llm()
            self._agent = create_react_agent(model=self._llm, tools=self.tools)
            self._llm_generation = current_gen
            logger.info(
                "Agent '%s': LLM nach Provider-Wechsel neu initialisiert.", self.name
            )

        # Context-Window einmalig kalibrieren (gecacht nach erstem Aufruf)
        model_window = await get_model_context_window()
        self._context_mgr.update_from_model_window(model_window)

        # Context-Budget prüfen: Komprimierung oder Trimming
        did_compact = False
        if self._context_mgr.should_reset(history):
            await status_bus.emit(
                session_id, _t("Kontext wird komprimiert…", "Compacting context…")
            )
            (
                trimmed_history,
                did_compact,
            ) = await self._context_mgr.compact_messages_async(history, self._llm)
        else:
            # Einzelne sehr lange Nachrichten vorher stutzen (opencode Pruning)
            history = self._context_mgr.trim_large_messages(history)
            trimmed_history = self._context_mgr.trim_messages(
                messages=history,
                system_prompt=self.system_prompt,
            )

        # Dynamischen Zusatz für den System Prompt holen
        appendix = await self._dynamic_prompt_appendix()
        final_system_prompt = self.system_prompt
        if appendix:
            final_system_prompt += f"\n\n{appendix}"

        # Soul-Injection: Identität an den Anfang des System-Prompts setzen
        try:
            from core.soul_manager import get_soul_manager

            soul = get_soul_manager().get_soul(self.name)
            if soul:
                final_system_prompt = soul + "\n\n---\n\n" + final_system_prompt
                logger.debug("Soul MD für Agent '%s' injiziert.", self.name)
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
            logger.debug("Soul-Injection fehlgeschlagen (ignoriert): %s", exc)

        # Sprachanweisung injizieren
        try:
            from core.config import get_settings as _gs

            lang = _gs().LANGUAGE
            lang_instruction = _LANG_INSTRUCTIONS.get(lang)
            if lang_instruction:
                final_system_prompt += f"\n\n{lang_instruction}"
        except (ImportError, AttributeError, TypeError, ValueError):
            pass  # Fallback: keine Sprachanweisung

        # Aktuelles Datum + Uhrzeit injizieren (Timezone aus Config)
        try:
            from datetime import datetime
            import zoneinfo
            from core.config import get_settings as _gs2

            tz_name = _gs2().TIMEZONE
            tz = zoneinfo.ZoneInfo(tz_name)
            now = datetime.now(tz)
            weekdays_de = [
                "Montag",
                "Dienstag",
                "Mittwoch",
                "Donnerstag",
                "Freitag",
                "Samstag",
                "Sonntag",
            ]
            weekdays_en = [
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ]
            lang = _gs().LANGUAGE if "lang" in dir() else "de"
            if lang == "de":
                dt_str = (
                    f"Aktuelles Datum: {weekdays_de[now.weekday()]}, "
                    f"{now.day:02d}.{now.month:02d}.{now.year} | "
                    f"Uhrzeit: {now.strftime('%H:%M')} ({tz_name})"
                )
            else:
                dt_str = (
                    f"Current date: {weekdays_en[now.weekday()]}, "
                    f"{now.strftime('%B %d, %Y')} | "
                    f"Time: {now.strftime('%H:%M')} ({tz_name})"
                )
            final_system_prompt += f"\n\n{dt_str}"
        except (ImportError, AttributeError, ValueError, RuntimeError) as exc:
            logger.debug("Datetime-Injection fehlgeschlagen (ignoriert): %s", exc)

        # Komprimierungs-Zusammenfassungen aus der History einsammeln (role="system")
        # und in den System-Prompt integrieren (nicht als separate SystemMessage —
        # Thinking-Modelle wie Qwen3.5 akzeptieren nur EINEN System-Block am Anfang)
        for msg in trimmed_history:
            if msg.get("role") == "system":
                final_system_prompt += "\n\n" + msg.get("content", "")

        # RAG-Kontext in den System-Prompt integrieren
        try:
            memory_hits = await self._memory.search(query=message, top_k=3)
            relevant_hits = [
                hit
                for hit in memory_hits
                if hit.get("distance") is None or hit["distance"] < 0.5
            ]
            if relevant_hits:
                rag_context = "\n\n".join(
                    f"[Memory] {hit['content']}" for hit in relevant_hits
                )
                final_system_prompt += (
                    "\n\n"
                    + _t(
                        "Relevanter Kontext aus dem Memory:\n",
                        "Relevant context from memory:\n",
                    )
                    + rag_context
                )
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
            logger.debug("Memory-Suche fehlgeschlagen: %s", exc)

        # Skills-Injection in den System-Prompt integrieren
        try:
            from core.skills_manager import get_skills_manager

            sm = get_skills_manager()
            matching_skills = sm.find_matching_skills(message, self.name)
            if matching_skills:
                skill_text = sm.build_injection(matching_skills)
                final_system_prompt += f"\n\n{skill_text}"
                logger.debug(
                    "Agent '%s': %d Skill(s) injiziert: %s",
                    self.name,
                    len(matching_skills),
                    [s.name for s in matching_skills],
                )
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
            logger.debug("Skills-Injection fehlgeschlagen (ignoriert): %s", exc)

        # Nachrichten aufbauen — genau EIN SystemMessage-Block am Anfang
        # (Thinking-Modelle wie Qwen3.5 erlauben nur einen System-Block)
        messages: list[BaseMessage] = [
            SystemMessage(content=final_system_prompt),
        ]

        for msg in trimmed_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
            # role="system" → bereits in final_system_prompt integriert
            # role="system_compaction" → UI-Notification, nicht für LLM bestimmt

        messages.append(HumanMessage(content=message))

        # JIT Tool Injection: nur relevante Tools für diese Anfrage laden
        active_tools = self._select_tools_for_request(message)
        if len(active_tools) != len(self.tools):
            # Temporären Agent mit gefiltertem Tool-Set erstellen
            jit_agent = create_react_agent(model=self._llm, tools=active_tools)
        else:
            jit_agent = self._agent

        # Agent ausführen – kein Schrittzähler (wie Roo Code), stattdessen Timeout
        AGENT_TIMEOUT = _get_agent_timeout_seconds()
        run_config: dict = {"recursion_limit": 10000}
        if session_id:
            run_config["callbacks"] = [_StatusEmitter(session_id)]
        try:
            # Safeguard-Pfad: interrupt_before=["tools"] + MemorySaver wenn aktiv
            # .enabled wird durch das aktive Profil gesteuert (disabled-Profil → False)
            use_safeguard = (
                _global_safeguard is not None
                and _global_safeguard.enabled
                and not confirmed
                and bool(session_id)
                and bool(active_tools)
            )

            if use_safeguard:
                # Wenn bereits ein pausierter Tool-Call in dieser Session wartet, nicht überschreiben.
                if session_id in _paused_sg_agents:
                    return _t(
                        "Für diese Session gibt es bereits eine ausstehende Tool-Bestätigung. "
                        "Bestätige zuerst den offenen Schritt (confirmed=true).",
                        "There is already a pending tool confirmation for this session. "
                        "Confirm the open step first (confirmed=true).",
                    ), did_compact

                async with _get_safeguard_session_lock(session_id):
                    raw_result = await self._run_with_safeguard(
                        messages, active_tools, run_config, session_id
                    )
                # Sentinel-String → Tool-Call braucht Bestätigung
                if isinstance(raw_result, str):
                    return raw_result, did_compact
                result = raw_result
            else:
                result = await asyncio.wait_for(
                    jit_agent.ainvoke(
                        {"messages": messages},
                        config=run_config,
                    ),
                    timeout=AGENT_TIMEOUT,
                )

            # Letzte AI-Nachricht extrahieren
            all_messages = result.get("messages", [])
            ai_messages = [
                m for m in all_messages if isinstance(m, AIMessage) and m.content
            ]

            if ai_messages:
                raw = _extract_text(ai_messages[-1].content)
                response = _strip_thinking(raw)
                # Thinking-Only-Antwort: Modell hat nur <think>-Blöcke generiert, kein Text
                if not response:
                    logger.debug(
                        "Agent '%s': AI-Antwort enthielt nur <think>-Blöcke, suche Tool-Ergebnis.",
                        self.name,
                    )
                    ai_messages = []  # Fallback auf Tool-Messages auslösen
            if not ai_messages:
                # Fallback: letztes Tool-Ergebnis verwenden wenn kein AI-Text vorhanden
                # (passiert wenn LLM nach Tool-Aufruf keinen Text generiert oder nur <think>)
                tool_messages = [
                    m for m in all_messages if isinstance(m, ToolMessage) and m.content
                ]
                if tool_messages:
                    response = _extract_text(tool_messages[-1].content)
                    logger.debug(
                        "Agent '%s': kein AI-Text, nutze letztes Tool-Ergebnis als Antwort.",
                        self.name,
                    )
                else:
                    response = _t("Keine Antwort generiert.", "No response generated.")

            logger.debug(
                "Agent '%s' Antwort: %s…",
                self.name,
                response[:100],
            )

            # Langzeitgedächtnis: relevante Fakten im Hintergrund speichern
            # Triviale Antworten (< 80 Zeichen) überspringen – kein Mehrwert
            # Background-Agenten (monitor, scheduler) ausschließen + Cooldown pro Agent
            _now = asyncio.get_running_loop().time()
            _cooldown_key = (self.name, session_id or "__no_session__")
            _last = _memorize_cooldowns.get(_cooldown_key, 0.0)
            if (
                len(response) >= 80
                and self.name not in _MEMORIZE_EXCLUDED_AGENTS
                and (_now - _last) >= _get_memorize_cooldown_secs()
            ):
                _memorize_cooldowns[_cooldown_key] = _now
                _task = asyncio.create_task(self._auto_memorize(message, response))
                _background_tasks.add(_task)
                _task.add_done_callback(_background_tasks.discard)

            return response, did_compact

        except asyncio.TimeoutError:
            logger.warning("Agent '%s' Timeout nach %ds.", self.name, AGENT_TIMEOUT)
            return _t(
                "Die Anfrage hat zu lange gedauert und wurde abgebrochen. "
                "Bitte versuche es mit einer spezifischeren Frage erneut.",
                "The request took too long and was aborted. "
                "Please try again with a more specific question.",
            ), False
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
            exc_str = str(exc)
            # Spezifische LM Studio / LLM Fehler benutzerfreundlich machen
            if "Model unloaded" in exc_str:
                user_msg = _t(
                    "Fehler: Das KI-Modell ist gerade nicht verfügbar (nicht geladen). "
                    "Bitte prüfe LM Studio und lade das Modell neu.",
                    "Error: The AI model is currently unavailable (not loaded). "
                    "Please check LM Studio and reload the model.",
                )
            else:
                logger.warning(
                    "Agent '%s' Fehler wird gegenüber User sanitisiert. raw_error=%s",
                    self.name,
                    exc_str[:300],
                )
                user_msg = _t(
                    "Fehler: Bei der Verarbeitung ist ein interner Fehler aufgetreten. "
                    "Bitte versuche es erneut oder präzisiere die Anfrage.",
                    "Error: An internal processing error occurred. "
                    "Please retry or make the request more specific.",
                )
            logger.error("Agent '%s' Fehler: %s", self.name, exc, exc_info=True)
            return user_msg, False

    def _extract_result_response(self, result: dict) -> str:
        """Extrahiert den Antwort-Text aus einem LangGraph-Ergebnis-Dict."""
        all_messages = result.get("messages", [])
        ai_messages = [
            m for m in all_messages if isinstance(m, AIMessage) and m.content
        ]

        if ai_messages:
            raw = _extract_text(ai_messages[-1].content)
            response = _strip_thinking(raw)
            if response:
                return response
            # Thinking-only: Fallback auf ToolMessages
        tool_messages = [
            m for m in all_messages if isinstance(m, ToolMessage) and m.content
        ]
        if tool_messages:
            return _extract_text(tool_messages[-1].content)
        return _t("Keine Antwort generiert.", "No response generated.")

    async def _sg_loop(
        self,
        sg_agent: Any,
        thread_config: dict,
        input_data: dict | None,
        session_id: str,
    ) -> "dict | str":
        """
        Kern-Schleife für den Safeguard-Interrupt-Mechanismus.

        Führt den Agenten aus und pausiert vor jedem Tool-Call. Gibt das
        LangGraph-Ergebnis-Dict zurück wenn die Ausführung abgeschlossen ist,
        oder einen Sentinel-String wenn ein Tool-Call Bestätigung benötigt.
        """
        AGENT_TIMEOUT = _get_agent_timeout_seconds()

        while True:
            result = await asyncio.wait_for(
                sg_agent.ainvoke(input_data, config=thread_config),
                timeout=AGENT_TIMEOUT,
            )
            input_data = None  # Folge-Iterationen = Resume vom Checkpoint

            # Prüfen ob der Graph vor einem Tool-Call pausiert ist
            state = sg_agent.get_state(thread_config)
            if not (state.next and "tools" in state.next):
                # Ausführung abgeschlossen
                return result

            # Paused — pending Tool-Calls aus dem State lesen
            all_msgs = state.values.get("messages", [])
            ai_with_tools = [
                m
                for m in all_msgs
                if isinstance(m, AIMessage) and getattr(m, "tool_calls", None)
            ]
            if not ai_with_tools:
                # Sollte nicht vorkommen, aber sicher resumieren
                continue

            last_ai = ai_with_tools[-1]

            # Alle pending Tool-Calls prüfen (Parallel-Tool-Calls möglich)
            dangerous_call = None
            for tool_call in last_ai.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call.get("args", {})
                if _global_safeguard is None or not _global_safeguard.enabled:
                    logger.warning(
                        "[Safeguard] Instanz während Lauf verloren/deaktiviert "
                        "(Agent: %s, Session: %s) – setze Ausführung ohne erneuten Check fort.",
                        self.name,
                        session_id,
                    )
                    dangerous_call = None
                    break

                sg_result = await _global_safeguard.check_tool_call(
                    tool_name,
                    tool_args,
                    agent_id=self.name,
                    session_id=session_id,
                )
                if sg_result.requires_confirmation:
                    dangerous_call = (tool_name, tool_args, sg_result)
                    break  # Ersten gefährlichen Call als Confirmation-Request nehmen

            if dangerous_call is None:
                # Alle Tools sind SAFE → sofort resumieren (transparent)
                continue

            tool_name, tool_args, sg_result = dangerous_call

            # Pausiert: Zustand im Modul-Dict speichern + in Redis vermerken
            _paused_sg_agents[session_id] = (sg_agent, thread_config)
            from core.redis_client import get_redis

            redis = get_redis()
            await redis.connection.setex(
                f"ninko:safeguard_tool_pending:{session_id}",
                300,
                _json.dumps(
                    {
                        "tool_name": tool_name,
                        "tool_args": tool_args,
                        "agent": self.name,
                        "category": sg_result.category.value,
                        "rationale": sg_result.rationale,
                    }
                ),
            )

            logger.info(
                "[Safeguard] Tool-Call '%s' pausiert (Agent: '%s', Session: '%s').",
                tool_name,
                self.name,
                session_id,
            )
            return f"{_TOOL_SAFEGUARD_SENTINEL}" + _json.dumps(
                {
                    "tool_name": tool_name,
                    "category": sg_result.category.value,
                    "rationale": sg_result.rationale,
                }
            )

    async def _run_with_safeguard(
        self,
        messages: list,
        active_tools: list,
        run_config: dict,
        session_id: str,
    ) -> "dict | str":
        """
        Führt den Agenten mit aktivem Safeguard-Interrupt aus.
        Erstellt einen temporären Agenten mit MemorySaver + interrupt_before=["tools"].
        """
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()
        sg_agent = create_react_agent(
            model=self._llm,
            tools=active_tools,
            checkpointer=checkpointer,
            interrupt_before=["tools"],
        )
        thread_config = {**run_config, "configurable": {"thread_id": session_id}}
        return await self._sg_loop(
            sg_agent, thread_config, {"messages": messages}, session_id
        )

    async def resume_safeguard_tool(self, session_id: str) -> tuple[str, bool]:
        """
        Setzt die Ausführung nach Safeguard-Bestätigung durch den User fort.
        Holt den pausierten Agenten aus _paused_sg_agents und resumiert den Graph.
        """
        if session_id not in _paused_sg_agents:
            logger.warning(
                "[Safeguard] Resume angefragt, aber kein pausierter Agent für Session '%s'.",
                session_id,
            )
            return _t(
                "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                "Error: No pending tool call for this session.",
            ), False

        async with _get_safeguard_session_lock(session_id):
            # Nicht poppen bevor Resume erfolgreich ist — sonst State-Verlust bei Fehlern.
            paused = _paused_sg_agents.get(session_id)
            if paused is None:
                return _t(
                    "Fehler: Kein ausstehender Tool-Aufruf für diese Session.",
                    "Error: No pending tool call for this session.",
                ), False
            sg_agent, thread_config = paused
            try:
                result = await self._sg_loop(sg_agent, thread_config, None, session_id)
            except asyncio.TimeoutError:
                logger.warning(
                    "Agent '%s' Timeout beim Resume (Session: %s).",
                    self.name,
                    session_id,
                )
                return _t(
                    "Die Ausführung hat zu lange gedauert und wurde abgebrochen.",
                    "Execution timed out and was aborted.",
                ), False
            except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
                logger.error(
                    "Agent '%s' Fehler beim Resume: %s", self.name, exc, exc_info=True
                )
                return _t(
                    "Fehler: Resume fehlgeschlagen. Bitte erneut bestätigen oder Anfrage wiederholen.",
                    "Error: Resume failed. Please confirm again or retry the request.",
                ), False

            # Weiterer Sentinel? (nächster gefährlicher Tool-Call)
            if isinstance(result, str):
                return result, False

            # Erfolg: pausierten Zustand + Pending-Key aufräumen
            _paused_sg_agents.pop(session_id, None)
            try:
                from core.redis_client import get_redis

                redis = get_redis()
                await redis.connection.delete(
                    f"ninko:safeguard_tool_pending:{session_id}"
                )
            except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
                logger.debug(
                    "[Safeguard] Pending-Key Cleanup fehlgeschlagen (Session: %s): %s",
                    session_id,
                    exc,
                )
            return self._extract_result_response(result), False

    async def store_incident(
        self,
        summary: str,
        details: str,
        severity: str = "info",
    ) -> str:
        """Speichert einen Incident im Semantic Memory."""
        return await self._memory.store_incident(
            module=self.name,
            summary=summary,
            details=details,
            severity=severity,
        )

    async def _auto_memorize(self, user_msg: str, ai_response: str) -> None:
        """
        Extrahiert und speichert dauerhaft relevante Fakten aus dem Gespräch.
        Läuft als Hintergrund-Task, blockiert nie die Antwortzeit.
        """
        try:
            prompt = _t(
                "Extrahiere aus diesem Gespräch NUR dauerhaft relevante Fakten "
                "(z.B. Namen des Users, IPs, Präferenzen, Entscheidungen, gelöste Probleme, gelernte Konfigurationen). "
                "Schreibe NUR 1-2 prägnante Sätze – in der Sprache des Users. "
                "Wenn NICHTS dauerhaft Merkenswertes vorhanden ist, schreibe exakt (ohne Sonderzeichen): NICHTS\n\n"
                f"User: {user_msg}\nAssistent: {ai_response[:800]}",
                "Extract ONLY permanently relevant facts from this conversation "
                "(e.g. user names, IPs, preferences, decisions, solved problems, learned configurations). "
                "Write ONLY 1-2 concise sentences — in the user's language. "
                "If NOTHING permanently noteworthy is present, write exactly (no special characters) "
                "one of: NOTHING / NICHTS / RIEN / NADA / NULLA / NIETS / NIC\n\n"
                f"User: {user_msg}\nAssistant: {ai_response[:800]}",
            )
            result = await self._llm.ainvoke([HumanMessage(content=prompt)])
            fact = (
                result.content.strip()
                if hasattr(result, "content")
                else str(result).strip()
            )
            if fact and fact.strip("*_ \n").upper() not in _MEMORIZE_STOP_WORDS:
                await self._memory.store(
                    content=fact,
                    category="agent_memory",
                    metadata={"agent": self.name, "source": "auto"},
                )
                logger.debug(
                    "Auto-Memory gespeichert für Agent '%s': %s…", self.name, fact[:80]
                )
        except _BASE_AGENT_RECOVERABLE_EXCEPTIONS as exc:
            logger.debug("Auto-Memorize fehlgeschlagen (ignoriert): %s", exc)
