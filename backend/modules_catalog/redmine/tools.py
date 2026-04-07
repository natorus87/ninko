"""
Redmine Module — LangGraph @tool functions.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.redmine.tools")

_REDMINE_TOOL_EXCEPTIONS = (
    httpx.HTTPError,
    ValueError,
    KeyError,
    TypeError,
    json.JSONDecodeError,
)


def _public_error() -> dict:
    return {"error": "Request failed. Check server logs."}


def _coerce_dict(value: Any, field_name: str) -> dict:
    """Accept dict, empty value, or JSON string and return dict."""
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{field_name} must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError(f"{field_name} must be a JSON object")
        return parsed
    raise ValueError(f"{field_name} must be a dict or JSON string")


def _build_plugin_endpoint(prefix: str, endpoint: str) -> str:
    normalized = endpoint.strip().strip("/")
    if not normalized:
        raise ValueError("endpoint is required")
    if normalized.startswith(("http://", "https://")):
        raise ValueError("endpoint must be relative, not absolute URL")
    plugin_prefix = prefix.strip().strip("/")
    return f"{plugin_prefix}/{normalized}" if plugin_prefix else normalized


def _add_if_set(params: dict, key: str, value: Any) -> None:
    if value is None:
        return
    if isinstance(value, str) and not value.strip():
        return
    params[key] = value


async def _get_api_client(connection_id: str = "") -> dict:
    """Load config and secrets from ConnectionManager or env vars."""
    if connection_id:
        conn = await ConnectionManager.get_connection("redmine", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Redmine-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Redmine connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Redmine avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión de Redmine con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Redmine con ID '{connection_id}' non trovata.",
                    nl=f"Redmine-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Redmine z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Redmine com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のRedmine接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Redmine连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("redmine")

    if conn:
        base_url = conn.config.get("url", "")
        hrm_prefix = conn.config.get(
            "hrm_api_prefix", os.environ.get("REDMINE_HRM_API_PREFIX", "hrm")
        )
        reporting_prefix = conn.config.get(
            "reporting_api_prefix",
            os.environ.get("REDMINE_REPORTING_API_PREFIX", "reporting"),
        )
        # SSL verification - default True, can be disabled for self-signed certs
        verify_ssl = conn.config.get("verify_ssl", True)
        if isinstance(verify_ssl, str):
            verify_ssl = verify_ssl.lower() not in ("false", "0", "no", "off")
        vault = get_vault()
        api_key = None
        api_key_path = conn.vault_keys.get("REDMINE_API_KEY")
        if api_key_path:
            api_key = await vault.get_secret(api_key_path)
        return {
            "base_url": base_url.rstrip("/"),
            "api_key": api_key,
            "hrm_api_prefix": str(hrm_prefix or "hrm"),
            "reporting_api_prefix": str(reporting_prefix or "reporting"),
            "verify_ssl": bool(verify_ssl),
        }

    base_url = os.environ.get("REDMINE_URL", "")
    api_key = os.environ.get("REDMINE_API_KEY", "")
    hrm_prefix = os.environ.get("REDMINE_HRM_API_PREFIX", "hrm")
    reporting_prefix = os.environ.get("REDMINE_REPORTING_API_PREFIX", "reporting")
    # Env var for SSL verification - default True
    verify_ssl = os.environ.get("REDMINE_VERIFY_SSL", "true").lower() not in (
        "false",
        "0",
        "no",
        "off",
    )

    if not base_url:
        raise ValueError(
            _t(
                de=(
                    "Keine Redmine-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen REDMINE_URL / REDMINE_API_KEY setzen."
                ),
                en=(
                    "No Redmine connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars REDMINE_URL / REDMINE_API_KEY."
                ),
                fr=(
                    "Aucune connexion Redmine configurée. "
                    "Veuillez créer une connexion dans Paramètres → Module → Engrenage, "
                    "ou définir les variables d'environnement REDMINE_URL / REDMINE_API_KEY."
                ),
                es=(
                    "No hay conexión de Redmine configurada. "
                    "Por favor cree una conexión en Configuración → Módulo → Engranaje, "
                    "o establezca las variables de entorno REDMINE_URL / REDMINE_API_KEY."
                ),
                it=(
                    "Nessuna connessione Redmine configurata. "
                    "Per favore crea una connessione in Impostazioni → Modulo → Ingranaggio, "
                    "o imposta le variabili di ambiente REDMINE_URL / REDMINE_API_KEY."
                ),
                nl=(
                    "Geen Redmine-verbinding geconfigureerd. "
                    "Maak een verbinding aan in Instellingen → Module → Tandwiel, "
                    "of stel de omgevingsvariabelen REDMINE_URL / REDMINE_API_KEY in."
                ),
                pl=(
                    "Nie skonfigurowano połączenia Redmine. "
                    "Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → Ikona koła zębatego "
                    "lub ustaw zmienne środowiskowe REDMINE_URL / REDMINE_API_KEY."
                ),
                pt=(
                    "Nenhuma conexão Redmine configurada. "
                    "Por favor crie uma conexão em Configurações → Módulo → Engrenagem, "
                    "ou defina as variáveis de ambiente REDMINE_URL / REDMINE_API_KEY."
                ),
                ja=(
                    "Redmine接続が設定されていません。 "
                    "ダッシュボードで設定→モジュール→歯車から接続を作成するか、"
                    "環境変数REDMINE_URL / REDMINE_API_KEYを設定してください。"
                ),
                zh=(
                    "未配置Redmine连接。 "
                    "请在设置→模块→齿轮下创建连接，"
                    "或设置环境变量REDMINE_URL / REDMINE_API_KEY。"
                ),
            )
        )

    return {
        "base_url": base_url.rstrip("/"),
        "api_key": api_key,
        "hrm_api_prefix": hrm_prefix,
        "reporting_api_prefix": reporting_prefix,
        "verify_ssl": bool(verify_ssl),
    }


async def _redmine_request(
    base_url: str,
    api_key: str,
    method: str,
    endpoint: str,
    params: dict | None = None,
    data: dict | None = None,
    verify_ssl: bool = True,
) -> dict:
    """Make a request to the Redmine API."""
    headers = {
        "X-Redmine-API-Key": api_key,
        "Content-Type": "application/json",
    }

    url = f"{base_url}/{endpoint.lstrip('/')}"
    async with httpx.AsyncClient(timeout=30.0, verify=verify_ssl) as client:
        if method.upper() == "GET":
            resp = await client.get(url, params=params, headers=headers)
        elif method.upper() == "POST":
            resp = await client.post(url, json=data, headers=headers)
        elif method.upper() == "PUT":
            resp = await client.put(url, json=data, headers=headers)
        elif method.upper() == "DELETE":
            resp = await client.delete(url, params=params, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        resp.raise_for_status()
        if resp.status_code == 204 or not resp.content:
            return {}
        content_type = resp.headers.get("content-type", "").lower()
        if "application/json" in content_type:
            return resp.json()
        try:
            return resp.json()
        except ValueError:
            return {"raw": resp.text}


@tool
async def get_redmine_projects(connection_id: str = "") -> dict:
    """
    Retrieve all projects from Redmine.
    Use this when the user asks for projects or to see available project list.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "projects.json",
            {"limit": 100},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "projects": result.get("projects", []),
            "total": result.get("total_count", 0),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_projects failed: %s", e)
        return _public_error()


@tool
async def get_redmine_project(project_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific project.
    Use this when the user asks for details about a specific project.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            params,
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "project": result.get("project", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_project failed: %s", e)
        return _public_error()


@tool
async def get_redmine_issues(
    project_id: str = "",
    status: str = "open",
    limit: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Retrieve issues (tickets) from Redmine.
    Use this when the user asks for tickets, issues, or bugs.
    Can filter by project and status (open/closed/all).
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"limit": min(limit, 100), "sort": "updated_on:desc"}
        if project_id:
            params["project_id"] = project_id
        if status:
            params["status_id"] = status

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            params,
        )
        return {
            "status": "success",
            "issues": result.get("issues", []),
            "total": result.get("total_count", 0),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_issues failed: %s", e)
        return _public_error()


@tool
async def get_redmine_issue(issue_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific issue.
    Use this when the user asks for details about a specific ticket.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            f"issues/{issue_id}.json",
            {"include": "journals,attachments,changesets"},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "issue": result.get("issue", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_issue failed: %s", e)
        return _public_error()


@tool
async def create_redmine_issue(
    project_id: str,
    subject: str,
    description: str = "",
    priority_id: str = "",
    assigned_to_id: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new issue in Redmine.
    Use this when the user asks to create a ticket, issue, or bug.
    """
    try:
        client = await _get_api_client(connection_id)
        issue = {
            "project_id": project_id,
            "subject": subject,
        }
        if description:
            issue["description"] = description
        if priority_id:
            issue["priority_id"] = priority_id
        if assigned_to_id:
            issue["assigned_to_id"] = assigned_to_id

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            "issues.json",
            data={"issue": issue},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"Issue created: #{result.get('issue', {}).get('id')}",
            "issue": result.get("issue", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("create_redmine_issue failed: %s", e)
        return _public_error()


@tool
async def update_redmine_issue(
    issue_id: str,
    status_id: str = "",
    priority_id: str = "",
    assigned_to_id: str = "",
    notes: str = "",
    connection_id: str = "",
) -> dict:
    """
    Update an existing issue.
    Use this when the user asks to update a ticket status, priority, or assignee.
    """
    try:
        client = await _get_api_client(connection_id)
        issue = {}
        if status_id:
            issue["status_id"] = status_id
        if priority_id:
            issue["priority_id"] = priority_id
        if assigned_to_id:
            issue["assigned_to_id"] = assigned_to_id

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "PUT",
            f"issues/{issue_id}.json",
            data={"issue": issue, "notes": notes} if notes else {"issue": issue},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"Issue #{issue_id} updated.",
            "issue": result.get("issue", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("update_redmine_issue failed: %s", e)
        return _public_error()


@tool
async def get_redmine_users(connection_id: str = "") -> dict:
    """
    Retrieve all users from Redmine.
    Use this when the user asks for user list or to see who has access.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "users.json",
            {"limit": 100},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "users": result.get("users", []),
            "total": result.get("total_count", 0),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_users failed: %s", e)
        return _public_error()


@tool
async def get_redmine_time_entries(
    project_id: str = "",
    from_date: str = "",
    to_date: str = "",
    connection_id: str = "",
) -> dict:
    """
    Retrieve time entries from Redmine.
    Use this when the user asks for time entries, logged hours, or time tracking.
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"limit": 100}
        if project_id:
            params["project_id"] = project_id
        if from_date:
            params["from"] = from_date
        if to_date:
            params["to"] = to_date

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "time_entries.json",
            params,
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "time_entries": result.get("time_entries", []),
            "total": result.get("total_count", 0),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redamine_time_entries failed: %s", e)
        return _public_error()


@tool
async def log_redmine_time(
    issue_id: str,
    hours: float,
    activity_id: str = "",
    comments: str = "",
    connection_id: str = "",
) -> dict:
    """
    Log time spent on an issue.
    Use this when the user asks to log time or add time entry.
    """
    try:
        client = await _get_api_client(connection_id)
        entry = {
            "issue_id": issue_id,
            "hours": hours,
        }
        if activity_id:
            entry["activity_id"] = activity_id
        if comments:
            entry["comments"] = comments

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            "time_entries.json",
            data={"time_entry": entry},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"Time logged: {hours}h on issue #{issue_id}",
            "time_entry": result.get("time_entry", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("log_redmine_time failed: %s", e)
        return _public_error()


@tool
async def get_redmine_issue_statuses(connection_id: str = "") -> dict:
    """
    Retrieve all possible issue statuses.
    Use this when the user asks for available statuses or workflow states.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issue_statuses.json",
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "statuses": result.get("issue_statuses", []),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_issue_statuses failed: %s", e)
        return _public_error()


@tool
async def get_redmine_priorities(connection_id: str = "") -> dict:
    """
    Retrieve all possible issue priorities.
    Use this when the user asks for available priorities.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "enumerations/issue_priorities.json",
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "priorities": result.get("issue_priorities", []),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_priorities failed: %s", e)
        return _public_error()


@tool
async def search_redmine_issues(
    query: str,
    connection_id: str = "",
) -> dict:
    """
    Search for issues by text query.
    Use this when the user asks to search for tickets or find issues.
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            {"search": query, "limit": 50},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "issues": result.get("issues", []),
            "total": result.get("total_count", 0),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("search_redmine_issues failed: %s", e)
        return _public_error()


@tool
async def get_redmine_issue_counts(
    project_id: str = "",
    connection_id: str = "",
) -> dict:
    """
    Get counts of issues by status for a project.
    Use this when the user asks for a summary or how many open/closed tickets.
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"status_id": "*"}
        if project_id:
            params["project_id"] = project_id

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "issues.json",
            params,
        )

        issues = result.get("issues", [])
        open_count = sum(
            1 for i in issues if i.get("status", {}).get("is_closed") == False
        )
        closed_count = sum(
            1 for i in issues if i.get("status", {}).get("is_closed") == True
        )

        return {
            "status": "success",
            "open": open_count,
            "closed": closed_count,
            "total": len(issues),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_issue_counts failed: %s", e)
        return _public_error()


@tool
async def call_redmine_hrm_api(
    method: str,
    endpoint: str,
    params: Any = None,
    payload: Any = None,
    connection_id: str = "",
) -> dict:
    """
    Call AlphaNodes HRM plugin API endpoints in Redmine (read and write).
    Use this for HRM data such as capacities, attendance, leave, or HRM reports.
    method supports GET/POST/PUT/DELETE.
    endpoint is relative to the configured HRM API prefix.
    """
    try:
        method_normalized = method.upper().strip()
        if method_normalized not in {"GET", "POST", "PUT", "DELETE"}:
            raise ValueError("method must be one of GET, POST, PUT, DELETE")

        client = await _get_api_client(connection_id)
        full_endpoint = _build_plugin_endpoint(client["hrm_api_prefix"], endpoint)
        query_params = _coerce_dict(params, "params")
        body = _coerce_dict(payload, "payload")

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            method_normalized,
            full_endpoint,
            params=query_params if query_params else None,
            data=body if body else None,
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "plugin": "hrm",
            "method": method_normalized,
            "endpoint": full_endpoint,
            "data": result,
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("call_redmine_hrm_api failed: %s", e)
        return _public_error()


@tool
async def call_redmine_reporting_api(
    method: str,
    endpoint: str,
    params: Any = None,
    payload: Any = None,
    connection_id: str = "",
) -> dict:
    """
    Call AlphaNodes Reporting plugin API endpoints in Redmine (read and write).
    Use this for KPI/report data retrieval and report-related write operations.
    method supports GET/POST/PUT/DELETE.
    endpoint is relative to the configured Reporting API prefix.
    """
    try:
        method_normalized = method.upper().strip()
        if method_normalized not in {"GET", "POST", "PUT", "DELETE"}:
            raise ValueError("method must be one of GET, POST, PUT, DELETE")

        client = await _get_api_client(connection_id)
        full_endpoint = _build_plugin_endpoint(client["reporting_api_prefix"], endpoint)
        query_params = _coerce_dict(params, "params")
        body = _coerce_dict(payload, "payload")

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            method_normalized,
            full_endpoint,
            params=query_params if query_params else None,
            data=body if body else None,
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "plugin": "reporting",
            "method": method_normalized,
            "endpoint": full_endpoint,
            "data": result,
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("call_redmine_reporting_api failed: %s", e)
        return _public_error()


@tool
async def get_redmine_hrm_attendances(
    from_date: str = "",
    to_date: str = "",
    user_id: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Get HRM attendance entries from AlphaNodes HRM plugin.
    Endpoint: GET /hrm/attendances.json
    Supports filters: from, to, user_id, limit, offset.
    """
    try:
        params: dict[str, Any] = {}
        _add_if_set(params, "from", from_date)
        _add_if_set(params, "to", to_date)
        _add_if_set(params, "user_id", user_id)
        _add_if_set(params, "limit", max(1, min(limit, 500)))
        _add_if_set(params, "offset", max(0, offset))
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "GET",
                "endpoint": "attendances.json",
                "params": params,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_hrm_attendances failed: %s", e)
        return _public_error()


@tool
async def create_redmine_hrm_attendance(
    attendance_payload: Any,
    connection_id: str = "",
) -> dict:
    """
    Create an HRM attendance entry in AlphaNodes HRM plugin.
    Endpoint: POST /hrm/attendances.json
    attendance_payload must be a JSON object (dict or JSON string), e.g.
    {"attendance": {"user_id": 5, "date": "2026-04-03", "status": "vacation"}}.
    """
    try:
        payload = _coerce_dict(attendance_payload, "attendance_payload")
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "POST",
                "endpoint": "attendances.json",
                "payload": payload,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("create_redmine_hrm_attendance failed: %s", e)
        return _public_error()


@tool
async def get_redmine_hrm_attendance(
    attendance_id: str,
    connection_id: str = "",
) -> dict:
    """
    Get one HRM attendance entry by ID.
    Endpoint: GET /hrm/attendances/{id}.json
    """
    try:
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "GET",
                "endpoint": f"attendances/{attendance_id}.json",
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_hrm_attendance failed: %s", e)
        return _public_error()


@tool
async def get_redmine_hrm_user_capacity(
    user_id: str,
    from_date: str = "",
    to_date: str = "",
    connection_id: str = "",
) -> dict:
    """
    Get HRM capacity/utilization for one user.
    Endpoint: GET /hrm/users/{user_id}/capacity.json
    Supports filters: from, to.
    """
    try:
        params: dict[str, Any] = {}
        _add_if_set(params, "from", from_date)
        _add_if_set(params, "to", to_date)
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "GET",
                "endpoint": f"users/{user_id}/capacity.json",
                "params": params,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_hrm_user_capacity failed: %s", e)
        return _public_error()


@tool
async def get_redmine_hrm_holidays(
    from_date: str = "",
    to_date: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Get configured HRM holidays.
    Endpoint: GET /hrm/holidays.json
    Supports optional filters: from, to, limit, offset.
    """
    try:
        params: dict[str, Any] = {}
        _add_if_set(params, "from", from_date)
        _add_if_set(params, "to", to_date)
        _add_if_set(params, "limit", max(1, min(limit, 500)))
        _add_if_set(params, "offset", max(0, offset))
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "GET",
                "endpoint": "holidays.json",
                "params": params,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_hrm_holidays failed: %s", e)
        return _public_error()


@tool
async def get_redmine_reporting_budgets(
    from_date: str = "",
    to_date: str = "",
    user_id: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Get reporting budgets.
    Endpoint: GET /reporting/budgets.json
    Supports filters: from, to, user_id, limit, offset.
    """
    try:
        params: dict[str, Any] = {}
        _add_if_set(params, "from", from_date)
        _add_if_set(params, "to", to_date)
        _add_if_set(params, "user_id", user_id)
        _add_if_set(params, "limit", max(1, min(limit, 500)))
        _add_if_set(params, "offset", max(0, offset))
        return await call_redmine_reporting_api.ainvoke(
            {
                "method": "GET",
                "endpoint": "budgets.json",
                "params": params,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_reporting_budgets failed: %s", e)
        return _public_error()


@tool
async def get_redmine_project_budgets(
    project_id: str,
    from_date: str = "",
    to_date: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Get budgets for a specific project.
    Endpoint: GET /projects/{project_id}/budgets.json
    Supports optional filters: from, to, limit, offset.
    """
    try:
        client = await _get_api_client(connection_id)
        params: dict[str, Any] = {}
        _add_if_set(params, "from", from_date)
        _add_if_set(params, "to", to_date)
        _add_if_set(params, "limit", max(1, min(limit, 500)))
        _add_if_set(params, "offset", max(0, offset))
        data = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            f"projects/{project_id}/budgets.json",
            params=params if params else None,
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "plugin": "reporting",
            "method": "GET",
            "endpoint": f"projects/{project_id}/budgets.json",
            "data": data,
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_project_budgets failed: %s", e)
        return _public_error()


@tool
async def get_redmine_reporting_time_logs(
    from_date: str = "",
    to_date: str = "",
    user_id: str = "",
    project_id: str = "",
    limit: int = 100,
    offset: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Get advanced reporting time logs.
    Endpoint: GET /reporting/time_logs.json
    Supports filters: from, to, user_id, project_id, limit, offset.
    """
    try:
        params: dict[str, Any] = {}
        _add_if_set(params, "from", from_date)
        _add_if_set(params, "to", to_date)
        _add_if_set(params, "user_id", user_id)
        _add_if_set(params, "project_id", project_id)
        _add_if_set(params, "limit", max(1, min(limit, 500)))
        _add_if_set(params, "offset", max(0, offset))
        return await call_redmine_reporting_api.ainvoke(
            {
                "method": "GET",
                "endpoint": "time_logs.json",
                "params": params,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_reporting_time_logs failed: %s", e)
        return _public_error()
