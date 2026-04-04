"""Zabbix module — LangGraph @tool functions."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.zabbix.tools")

ZABBIX_API_VERSION = "api_version"


async def _get_zabbix_config(connection_id: str = "") -> dict:
    """Load Zabbix config and secrets from ConnectionManager."""
    if connection_id:
        conn = await ConnectionManager.get_connection("zabbix", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Zabbix-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Zabbix connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Zabbix avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión Zabbix con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Zabbix con ID '{connection_id}' non trovata.",
                    nl=f"Zabbix-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Zabbix z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Zabbix com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のZabbix接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Zabbix连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("zabbix")

    if conn:
        vault = get_vault()
        password = conn.vault_keys.get("ZABBIX_PASSWORD")
        password_value = (
            await vault.get_secret(password)
            if password
            else conn.config.get("password", "")
        )
        return {
            "url": conn.config.get("url", ""),
            "user": conn.config.get("user", ""),
            "password": password_value,
        }

    url = os.environ.get("ZABBIX_URL", "")
    user = os.environ.get("ZABBIX_USER", "")
    password = os.environ.get("ZABBIX_PASSWORD", "")

    if not url:
        raise ValueError(
            _t(
                de="Keine Zabbix-Verbindung konfiguriert. Bitte Zabbix-URL in den Einstellungen setzen.",
                en="No Zabbix connection configured. Please set Zabbix URL in settings.",
                fr="Aucune connexion Zabbix configurée. Veuillez définir l'URL Zabbix dans les paramètres.",
                es="No hay conexión Zabbix configurada. Por favor configure la URL de Zabbix en la configuración.",
                it="Nessuna connessione Zabbix configurata. Per favore imposta l'URL di Zabbix nelle impostazioni.",
                nl="Geen Zabbix-verbinding geconfigureerd. Stel alstublieft de Zabbix-URL in in de instellingen.",
                pl="Nie skonfigurowano połączenia Zabbix. Ustaw adres URL Zabbix w ustawieniach.",
                pt="Nenhuma conexão Zabbix configurada. Por favor, defina a URL do Zabbix nas configurações.",
                ja="Zabbix接続が設定されていません。設定でZabbixのURLを設定してください。",
                zh="未配置Zabbix连接。请在设置中设置Zabbix URL。",
            )
        )

    return {"url": url, "user": user, "password": password}


async def _zabbix_request(
    url: str, user: str, password: str, method: str, params: dict = None
) -> Any:
    """Make a request to Zabbix API."""
    headers = {"Content-Type": "application/json"}

    auth_payload = {
        "jsonrpc": "2.0",
        "method": "user.login",
        "params": {"user": user, "password": password},
        "id": 1,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        auth_resp = await client.post(url, headers=headers, json=auth_payload)
        auth_data = auth_resp.json()

        if "error" in auth_data:
            raise ValueError(f"Zabbix auth error: {auth_data['error']}")

        auth_token = auth_data.get("result")

        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "auth": auth_token,
            "id": 2,
        }

        resp = await client.post(url, headers=headers, json=payload)
        data = resp.json()

        if "error" in data:
            raise ValueError(f"Zabbix API error: {data['error']}")

        return data.get("result", [])


@tool("get_zabbix_status")
async def get_zabbix_status(connection_id: str = "") -> Dict:
    """
    Get Zabbix server status and version.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        Dict with version, server info, and timestamp
    """
    config = await _get_zabbix_config(connection_id)
    url = config["url"]

    async with httpx.AsyncClient(timeout=15) as client:
        auth_payload = {
            "jsonrpc": "2.0",
            "method": "user.login",
            "params": {"user": config["user"], "password": config["password"]},
            "id": 1,
        }
        auth_resp = await client.post(url, json=auth_payload)
        auth_data = auth_resp.json()
        auth_token = auth_data.get("result")

        version_payload = {
            "jsonrpc": "2.0",
            "method": "api.version.get",
            "params": {},
            "auth": auth_token,
            "id": 2,
        }
        version_resp = await client.post(url, json=version_payload)
        version_data = version_resp.json()
        version = version_data.get("result", "unknown")

        info_payload = {
            "jsonrpc": "2.0",
            "method": "server.runnable",
            "params": {},
            "auth": auth_token,
            "id": 3,
        }

        return {
            "version": version,
            "url": url,
            "status": "online" if auth_token else "offline",
        }


@tool("list_zabbix_hosts")
async def list_zabbix_hosts(connection_id: str = "") -> List[Dict]:
    """
    List all Zabbix hosts.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of host objects with id, name, status
    """
    config = await _get_zabbix_config(connection_id)
    result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "host.get",
        {
            "output": ["hostid", "name", "status", "lastsync"],
            "selectInterfaces": ["ip"],
        },
    )

    hosts = []
    for host in result:
        hosts.append(
            {
                "hostid": host.get("hostid"),
                "name": host.get("name"),
                "status": host.get("status"),
                "ip": host.get("interfaces", [{}])[0].get("ip")
                if host.get("interfaces")
                else None,
            }
        )

    return hosts


@tool("get_zabbix_host")
async def get_zabbix_host(host_id: str, connection_id: str = "") -> Dict:
    """
    Get detailed information about a specific Zabbix host.

    Args:
        host_id: Zabbix host ID
        connection_id: Optional connection ID for named connection

    Returns:
        Host details including items, triggers, graphs
    """
    config = await _get_zabbix_config(connection_id)

    host_result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "host.get",
        {
            "hostids": [host_id],
            "output": "extend",
            "selectItems": ["itemid", "name", "key_", "lastvalue"],
            "selectTriggers": ["triggerid", "description", "status", "priority"],
        },
    )

    if not host_result:
        raise ValueError(f"Host {host_id} not found")

    host = host_result[0]
    return {
        "hostid": host.get("hostid"),
        "name": host.get("name"),
        "status": host.get("status"),
        "items": host.get("items", [])[:20],
        "triggers": host.get("triggers", [])[:20],
    }


@tool("list_zabbix_items")
async def list_zabbix_items(host_id: str = "", connection_id: str = "") -> List[Dict]:
    """
    List monitoring items (metrics).

    Args:
        host_id: Optional host ID to filter items
        connection_id: Optional connection ID for named connection

    Returns:
        List of item objects
    """
    config = await _get_zabbix_config(connection_id)
    params = {
        "output": [
            "itemid",
            "name",
            "key_",
            "lastvalue",
            "lastclock",
            "state",
            "status",
        ]
    }
    if host_id:
        params["hostids"] = [host_id]

    result = await _zabbix_request(
        config["url"], config["user"], config["password"], "item.get", params
    )

    items = []
    for item in result:
        items.append(
            {
                "itemid": item.get("itemid"),
                "name": item.get("name"),
                "key": item.get("key_"),
                "lastvalue": item.get("lastvalue"),
                "lastclock": item.get("lastclock"),
                "state": item.get("state"),
            }
        )

    return items[:100]


@tool("list_zabbix_triggers")
async def list_zabbix_triggers(
    host_id: str = "", connection_id: str = ""
) -> List[Dict]:
    """
    List trigger definitions.

    Args:
        host_id: Optional host ID to filter triggers
        connection_id: Optional connection ID for named connection

    Returns:
        List of trigger objects
    """
    config = await _get_zabbix_config(connection_id)
    params = {
        "output": [
            "triggerid",
            "description",
            "status",
            "priority",
            "lastchange",
            "flags",
        ]
    }
    if host_id:
        params["hostids"] = [host_id]

    result = await _zabbix_request(
        config["url"], config["user"], config["password"], "trigger.get", params
    )

    triggers = []
    for trigger in result:
        triggers.append(
            {
                "triggerid": trigger.get("triggerid"),
                "description": trigger.get("description"),
                "status": trigger.get("status"),
                "priority": trigger.get("priority"),
                "lastchange": trigger.get("lastchange"),
            }
        )

    return triggers[:100]


@tool("get_zabbix_problems")
async def get_zabbix_problems(host_id: str = "", connection_id: str = "") -> List[Dict]:
    """
    Get current problems (active triggers).

    Args:
        host_id: Optional host ID to filter problems
        connection_id: Optional connection ID for named connection

    Returns:
        List of problem objects
    """
    config = await _get_zabbix_config(connection_id)
    params = {"output": "extend", "sortfield": "severity", "sortorder": "DESC"}
    if host_id:
        params["hostids"] = [host_id]

    result = await _zabbix_request(
        config["url"], config["user"], config["password"], "problem.get", params
    )

    problems = []
    for prob in result:
        problems.append(
            {
                "eventid": prob.get("eventid"),
                "name": prob.get("name"),
                "severity": prob.get("severity"),
                "host": prob.get("host"),
                "clock": prob.get("clock"),
            }
        )

    return problems[:50]


@tool("list_zabbix_graphs")
async def list_zabbix_graphs(host_id: str = "", connection_id: str = "") -> List[Dict]:
    """
    List graphs for hosts.

    Args:
        host_id: Optional host ID to filter graphs
        connection_id: Optional connection ID for named connection

    Returns:
        List of graph objects
    """
    config = await _get_zabbix_config(connection_id)
    params = {"output": ["graphid", "name", "width", "height"]}
    if host_id:
        params["hostids"] = [host_id]

    result = await _zabbix_request(
        config["url"], config["user"], config["password"], "graph.get", params
    )

    graphs = []
    for g in result:
        graphs.append(
            {
                "graphid": g.get("graphid"),
                "name": g.get("name"),
                "width": g.get("width"),
                "height": g.get("height"),
            }
        )

    return graphs[:50]


@tool("list_zabbix_actions")
async def list_zabbix_actions(connection_id: str = "") -> List[Dict]:
    """
    List alert/notification actions.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of action objects
    """
    config = await _get_zabbix_config(connection_id)
    result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "action.get",
        {
            "output": ["actionid", "name", "status", "esc_period", "def_shortdata"],
            "selectOperations": "extend",
        },
    )

    actions = []
    for a in result:
        actions.append(
            {
                "actionid": a.get("actionid"),
                "name": a.get("name"),
                "status": a.get("status"),
                "esc_period": a.get("esc_period"),
            }
        )

    return actions


@tool("get_zabbix_history")
async def get_zabbix_history(
    item_id: str, from_time: str = "", limit: int = 50, connection_id: str = ""
) -> List[Dict]:
    """
    Get historical data for an item.

    Args:
        item_id: Zabbix item ID
        from_time: Start time (Unix timestamp or relative like '24h')
        limit: Maximum number of records
        connection_id: Optional connection ID for named connection

    Returns:
        List of history data points
    """
    config = await _get_zabbix_config(connection_id)

    item_result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "item.get",
        {"itemids": [item_id], "output": ["value_type"]},
    )

    if not item_result:
        raise ValueError(f"Item {item_id} not found")

    value_type = int(item_result[0].get("value_type", 0))

    params = {"itemids": [item_id], "limit": limit, "sortorder": "DESC"}
    if from_time:
        params["time_from"] = from_time if from_time.isdigit() else None

    history_result = await _zabbix_request(
        config["url"], config["user"], config["password"], "history.get", params
    )

    history = []
    for h in history_result:
        history.append(
            {
                "clock": h.get("clock"),
                "value": h.get("value"),
                "ns": h.get("ns"),
            }
        )

    return history


@tool("get_zabbix_host_group")
async def get_zabbix_host_group(connection_id: str = "") -> List[Dict]:
    """
    List host groups.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of host group objects
    """
    config = await _get_zabbix_config(connection_id)
    result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "hostgroup.get",
        {"output": ["groupid", "name"]},
    )

    groups = []
    for g in result:
        groups.append(
            {
                "groupid": g.get("groupid"),
                "name": g.get("name"),
            }
        )

    return groups


@tool("list_zabbix_templates")
async def list_zabbix_templates(connection_id: str = "") -> List[Dict]:
    """
    List templates.

    Args:
        connection_id: Optional connection ID for named connection

    Returns:
        List of template objects
    """
    config = await _get_zabbix_config(connection_id)
    result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "template.get",
        {"output": ["templateid", "name"]},
    )

    templates = []
    for t in result:
        templates.append(
            {
                "templateid": t.get("templateid"),
                "name": t.get("name"),
            }
        )

    return templates


@tool("create_zabbix_host")
async def create_zabbix_host(
    host_name: str, ip: str, group_id: str = "1", connection_id: str = ""
) -> Dict:
    """
    Create a new Zabbix host.

    Args:
        host_name: Name of the new host
        ip: IP address of the host
        group_id: Host group ID (default: 1)
        connection_id: Optional connection ID for named connection

    Returns:
        Created host object
    """
    config = await _get_zabbix_config(connection_id)

    result = await _zabbix_request(
        config["url"],
        config["user"],
        config["password"],
        "host.create",
        {
            "host": host_name,
            "interfaces": [
                {"type": 1, "main": 1, "useip": 1, "ip": ip, "dns": "", "port": "10050"}
            ],
            "groups": [{"groupid": group_id}],
        },
    )

    return {"hostid": result.get("hostids", [""])[0], "host": host_name}


@tool("delete_zabbix_host")
async def delete_zabbix_host(host_id: str, connection_id: str = "") -> Dict:
    """
    Delete a Zabbix host.

    Args:
        host_id: Zabbix host ID to delete
        connection_id: Optional connection ID for named connection

    Returns:
        Deletion result
    """
    config = await _get_zabbix_config(connection_id)

    result = await _zabbix_request(
        config["url"], config["user"], config["password"], "host.delete", [host_id]
    )

    return {"deleted": host_id, "result": "success" if result else "failed"}
