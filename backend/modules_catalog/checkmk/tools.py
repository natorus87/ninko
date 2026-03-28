"""
Checkmk Modul – LangGraph @tool-Funktionen.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.checkmk.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """
    Lädt Konfiguration und Secrets aus dem ConnectionManager.
    Unterstützt Username/Password und API-Token Auth.
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("checkmk", connection_id)
        if not conn:
            raise ValueError(f"Checkmk-Verbindung mit ID '{connection_id}' nicht gefunden.")
    else:
        conn = await ConnectionManager.get_default_connection("checkmk")

    if conn:
        base_url = conn.config.get("url", "").rstrip("/")
        site = conn.config.get("site", "")
        username = conn.config.get("username", "")
        vault = get_vault()

        password = None
        token = None

        password_path = conn.vault_keys.get("CHECKMK_API_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)

        token_path = conn.vault_keys.get("CHECKMK_API_TOKEN")
        if token_path:
            token = await vault.get_secret(token_path)

        return {
            "base_url": base_url,
            "site": site,
            "username": username,
            "password": password,
            "token": token,
            "use_token": bool(token),
        }

    base_url = os.environ.get("CHECKMK_URL", "").rstrip("/")
    site = os.environ.get("CHECKMK_SITE", "")
    username = os.environ.get("CHECKMK_API_USERNAME", "")
    password = os.environ.get("CHECKMK_API_PASSWORD", "")
    token = os.environ.get("CHECKMK_API_TOKEN", "")

    if not base_url:
        raise ValueError(
            "Keine Checkmk-Verbindung konfiguriert. "
            "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
            "oder die Env-Variablen CHECKMK_URL / CHECKMK_SITE setzen."
        )

    return {
        "base_url": base_url,
        "site": site,
        "username": username,
        "password": password,
        "token": token,
        "use_token": bool(token),
    }


async def _make_checkmk_request(
    method: str,
    endpoint: str,
    client_config: dict,
    json_data: Optional[dict] = None,
) -> dict:
    """Macht einen API-Request an Checkmk."""
    base_url = client_config["base_url"]
    site = client_config["site"]
    username = client_config["username"]
    use_token = client_config.get("use_token", False)

    password = client_config.get("password") or ""
    token = client_config.get("token") or ""

    auth = ("automation", token) if use_token else (username, password)
    headers = {"Accept": "application/json"}

    url = f"{base_url}/{site}/check_mk/api/0.1/{endpoint.lstrip('/')}"

    async with httpx.AsyncClient(timeout=30.0) as httpx_client:
        if method.upper() == "GET":
            resp = await httpx_client.get(url, auth=auth, headers=headers)
        elif method.upper() == "POST":
            resp = await httpx_client.post(url, auth=auth, headers=headers, json=json_data)
        else:
            resp = await httpx_client.request(method, url, auth=auth, headers=headers, json=json_data)

        if resp.status_code >= 400:
            try:
                error_detail = resp.json().get("detail", resp.text)
            except Exception:
                error_detail = resp.text
            raise Exception(f"Checkmk API Error {resp.status_code}: {error_detail}")

        return resp.json()


@tool
async def checkmk_get_hosts(connection_id: str = "", filter_name: str = "") -> str:
    """
    Lädt Hosts aus Checkmk.
    Nutze dieses Tool, wenn der User nach überwachten Systemen, Hosts,
    Host-Übersichten oder Monitoring-Zielen fragt.
    Loads hosts from Checkmk. Use this tool when the user asks for monitored systems,
    hosts, host overviews, or monitoring targets.
    """
    try:
        client = await _get_api_client(connection_id)

        params = {}
        if filter_name:
            params["filter"] = f"name:.{filter_name}"

        result = await _make_checkmk_request("GET", "/objects/host", client, json_data=params)

        hosts = result.get("hosts", [])
        if not hosts:
            return "Keine Hosts gefunden."

        summary = []
        for h in hosts[:20]:
            name = h.get("id", {}).get("name", "unbekannt")
            summary.append(f"• {name}")

        total = len(hosts)
        more = f"\n... und {total - 20} weitere" if total > 20 else ""
        return f"Hosts ({total}):\n{chr(10).join(summary)}{more}"

    except Exception as e:
        logger.error("Fehler beim Laden der Hosts: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_get_services(connection_id: str = "", host_name: str = "") -> str:
    """
    Lädt Services aus Checkmk.
    Nutze dieses Tool, wenn der User nach Services, Service-Übersichten
    oder Monitoring-Checks fragt.
    Loads services from Checkmk. Use this tool when the user asks for services,
    service overviews, or monitoring checks.
    """
    try:
        client = await _get_api_client(connection_id)

        if not host_name:
            endpoint = "/objects/service"
            result = await _make_checkmk_request("GET", endpoint, client)
            services = result.get("services", [])[:50]
        else:
            endpoint = f"/objects/host/{host_name}/services"
            result = await _make_checkmk_request("GET", endpoint, client)
            services = result.get("services", [])

        if not services:
            return "Keine Services gefunden."

        summary = []
        for s in services[:20]:
            desc = s.get("id", {}).get("service_description", "unbekannt")
            summary.append(f"• {desc}")

        total = len(services)
        more = f"\n... und {total - 20} weitere" if total > 20 else ""
        return f"Services ({total}):\n{chr(10).join(summary)}{more}"

    except Exception as e:
        logger.error("Fehler beim Laden der Services: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_get_host_status(connection_id: str = "", host_name: str = "") -> str:
    """
    Lädt den Status eines Hosts aus Checkmk.
    Nutze dieses Tool, wenn der User nach dem Status eines bestimmten Hosts fragt.
    Loads the status of a specific host. Use this tool when the user asks
    for the status of a particular host.
    """
    try:
        if not host_name:
            return "Fehler: Host-Name erforderlich."

        client = await _get_api_client(connection_id)
        endpoint = f"/objects/host/{host_name}/status"
        result = await _make_checkmk_request("GET", endpoint, client)

        status_info = result.get("hosts", [{}])[0] if result.get("hosts") else {}
        host_state = status_info.get("state", "unknown")
        state_info = {0: "UP", 1: "DOWN", 2: "UNREACHABLE"}.get(host_state, f"UNKNOWN ({host_state})")

        return f"Host: {host_name}\nStatus: {state_info}"

    except Exception as e:
        logger.error("Fehler beim Laden des Host-Status: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_get_service_status(connection_id: str = "", host_name: str = "", service_desc: str = "") -> str:
    """
    Lädt den Status eines Services auf einem Host aus Checkmk.
    Nutze dieses Tool, wenn der User nach dem Status eines bestimmten Service fragt.
    Loads the status of a specific service on a host. Use this tool when the user
    asks for the status of a specific service.
    """
    try:
        if not host_name or not service_desc:
            return "Fehler: Host-Name und Service-Beschreibung erforderlich."

        client = await _get_api_client(connection_id)
        endpoint = f"/objects/host/{host_name}/services"
        result = await _make_checkmk_request("GET", endpoint, client)

        services = result.get("services", [])
        service = next(
            (s for s in services if s.get("id", {}).get("service_description") == service_desc),
            None
        )

        if not service:
            return f"Service '{service_desc}' auf Host '{host_name}' nicht gefunden."

        state = service.get("state", -1)
        state_map = {0: "OK", 1: "WARN", 2: "CRIT", 3: "UNKNOWN"}
        state_str = state_map.get(state, f"UNKNOWN ({state})")

        return f"Host: {host_name}\nService: {service_desc}\nStatus: {state_str}"

    except Exception as e:
        logger.error("Fehler beim Laden des Service-Status: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_get_alerts(connection_id: str = "", max_results: int = 20) -> str:
    """
    Lädt aktuelle Probleme und Alarme aus Checkmk.
    Nutze dieses Tool, wenn der User nach aktuellen Problemen, WARN/CRIT-Zuständen
    oder offenen Alarmen fragt.
    Loads current problems and alerts from Checkmk. Use this tool when the user
    asks for current issues, WARN/CRIT states, or open alerts.
    """
    try:
        client = await _get_api_client(connection_id)

        endpoint = "/objects/service"
        result = await _make_checkmk_request("GET", endpoint, client)
        services = result.get("services", [])

        problem_services = [s for s in services if s.get("state", 0) in [1, 2, 3]]

        if not problem_services:
            return "Keine aktuellen Probleme gefunden. Alle Services im OK-Zustand."

        summary = []
        for s in problem_services[:max_results]:
            host = s.get("id", {}).get("host_name", "unbekannt")
            desc = s.get("id", {}).get("service_description", "unbekannt")
            state = s.get("state", -1)
            state_map = {1: "⚠️ WARN", 2: "🔴 CRIT", 3: "❓ UNKNOWN"}
            state_str = state_map.get(state, f"STATE {state}")
            summary.append(f"{state_str} | {host} | {desc}")

        total = len(problem_services)
        more = f"\n... und {total - max_results} weitere" if total > max_results else ""
        return f"Probleme ({total}):\n{chr(10).join(summary)}{more}"

    except Exception as e:
        logger.error("Fehler beim Laden der Alarme: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_get_host_details(connection_id: str = "", host_name: str = "") -> str:
    """
    Lädt Detailinformationen zu einem Host aus Checkmk.
    Nutze dieses Tool, wenn der User nach detaillierten Informationen zu einem Host fragt.
    Loads detailed information about a host. Use this tool when the user asks
    for detailed information about a specific host.
    """
    try:
        if not host_name:
            return "Fehler: Host-Name erforderlich."

        client = await _get_api_client(connection_id)
        endpoint = f"/objects/host/{host_name}/status"
        result = await _make_checkmk_request("GET", endpoint, client)

        host_data = result.get("hosts", [{}])[0] if result.get("hosts") else {}
        if not host_data:
            return f"Host '{host_name}' nicht gefunden."

        name = host_data.get("id", {}).get("name", host_name)
        state = host_data.get("state", -1)
        state_map = {0: "UP", 1: "DOWN", 2: "UNREACHABLE"}
        state_str = state_map.get(state, f"UNKNOWN ({state})")

        output = f"Host: {name}\nStatus: {state_str}\n"

        custom_vars = host_data.get("custom_variables", {})
        if custom_vars:
            output += f"Custom Vars: {custom_vars}\n"

        return output

    except Exception as e:
        logger.error("Fehler beim Laden der Host-Details: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_get_service_details(connection_id: str = "", host_name: str = "", service_desc: str = "") -> str:
    """
    Lädt Detailinformationen zu einem Service aus Checkmk.
    Nutze dieses Tool, wenn der User nach detaillierten Informationen zu einem Service fragt.
    Loads detailed information about a service. Use this tool when the user asks
    for detailed information about a specific service.
    """
    try:
        if not host_name or not service_desc:
            return "Fehler: Host-Name und Service-Beschreibung erforderlich."

        client = await _get_api_client(connection_id)
        endpoint = f"/objects/host/{host_name}/services"
        result = await _make_checkmk_request("GET", endpoint, client)

        services = result.get("services", [])
        service = next(
            (s for s in services if s.get("id", {}).get("service_description") == service_desc),
            None
        )

        if not service:
            return f"Service '{service_desc}' auf Host '{host_name}' nicht gefunden."

        state = service.get("state", -1)
        state_map = {0: "OK", 1: "WARN", 2: "CRIT", 3: "UNKNOWN"}
        state_str = state_map.get(state, f"UNKNOWN ({state})")

        output = f"Host: {host_name}\nService: {service_desc}\nStatus: {state_str}\n"

        return output

    except Exception as e:
        logger.error("Fehler beim Laden der Service-Details: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_search_hosts(connection_id: str = "", search_term: str = "") -> str:
    """
    Sucht Hosts in Checkmk anhand eines Suchbegriffs.
    Nutze dieses Tool, wenn der User nach bestimmten Hosts sucht.
    Searches for hosts in Checkmk by a search term. Use this tool when the user
    searches for specific hosts.
    """
    try:
        if not search_term:
            return "Fehler: Suchbegriff erforderlich."

        return await checkmk_get_hosts.ainvoke(
            {"connection_id": connection_id, "filter_name": search_term}
        )

    except Exception as e:
        logger.error("Fehler bei der Host-Suche: %s", e)
        return f"Fehler: {e}"


@tool
async def checkmk_search_services(connection_id: str = "", search_term: str = "") -> str:
    """
    Sucht Services in Checkmk anhand eines Suchbegriffs.
    Nutze dieses Tool, wenn der User nach bestimmten Services sucht.
    Searches for services in Checkmk by a search term. Use this tool when the user
    searches for specific services.
    """
    try:
        if not search_term:
            return "Fehler: Suchbegriff erforderlich."

        client = await _get_api_client(connection_id)
        endpoint = "/objects/service"
        result = await _make_checkmk_request("GET", endpoint, client)

        services = result.get("services", [])
        matched = [
            s for s in services
            if search_term.lower() in s.get("id", {}).get("service_description", "").lower()
        ][:20]

        if not matched:
            return f"Keine Services gefunden, die '{search_term}' enthalten."

        summary = []
        for s in matched:
            host = s.get("id", {}).get("host_name", "unbekannt")
            desc = s.get("id", {}).get("service_description", "unbekannt")
            summary.append(f"• {host} | {desc}")

        total = len(matched)
        more = f"\n... und {total - 20} weitere" if total > 20 else ""
        return f"Services mit '{search_term}' ({total}):\n{chr(10).join(summary)}{more}"

    except Exception as e:
        logger.error("Fehler bei der Service-Suche: %s", e)
        return f"Fehler: {e}"
