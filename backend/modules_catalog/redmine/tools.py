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
    Get total hours for a specific user in a date range with pagination.
    Use this for 'hours in month' questions to get accurate totals.

    DE: Stunden-Report für einen Benutzer im Zeitraum. Nutze dies für 'Stunden im Monat' Fragen.
    EN: Hours report for a user in a date range. Use this for 'hours in month' questions.
    FR: Rapport d\'heures pour un utilisateur sur une période. Utilisez pour les questions 'heures dans le mois'.
    ES: Informe de horas para un usuario en un rango de fechas. Úselo para preguntas 'horas en el mes'.

    Parameters:
    - user_id: User ID (e.g., "32")
    - from_date: Start date (YYYY-MM-DD, e.g., "2026-03-01")
    - to_date: End date (YYYY-MM-DD, e.g., "2026-03-31")
    - project_id: Optional project filter

    Returns:
    - total_hours: Sum of all hours
    - entry_count: Number of entries
    - entries: List with date, hours, project, issue_id
    """
    try:
        client = await _get_api_client(connection_id)
        params: dict[str, Any] = {}
        _add_if_set(params, "include", "trackers,issue_categories,attachments,wiki_pages")
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            f"projects/{project_id}.json",
            params=params if params else None,
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
    assigned_to_id: str = "",
    status: str = "open",
    limit: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Retrieve issues (tickets) from Redmine.
    Use this when the user asks for tickets, issues, or bugs.
    Can filter by project, assigned user, and status (open/closed/all).

    Parameters:
    - assigned_to_id: Filter by assigned user ID (e.g., "32")
    - status: "open", "closed", or "*" for all
    - project_id: Optional project filter
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"limit": min(limit, 100), "sort": "updated_on:desc"}
        if project_id:
            params["project_id"] = project_id
        if assigned_to_id:
            params["assigned_to_id"] = assigned_to_id
        if status:
            params["status_id"] = status

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
    user_id: str = "",
    from_date: str = "",
    to_date: str = "",
    connection_id: str = "",
) -> dict:
    """
    Retrieve time entries from Redmine (first 100 only, no pagination).
    Use this when the user asks for time entries, logged hours, or time tracking.
    For monthly totals with many entries, use get_redmine_user_hours_report instead.

    DE: Zeiteinträge abrufen (nur erste 100). Nutze get_redmine_user_hours_report für Monatssummen.
    EN: Retrieve time entries (first 100 only). Use get_redmine_user_hours_report for monthly totals.
    FR: Récupérer les entrées de temps (100 premières seulement). Utilisez get_redmine_user_hours_report pour les totaux mensuels.
    ES: Recuperar entradas de tiempo (solo primeras 100). Use get_redmine_user_hours_report para totales mensuales.
    IT: Recupera voci temporali (solo prime 100). Usa get_redmine_user_hours_report per totali mensili.
    NL: Time entries ophalen (alleen eerste 100). Gebruik get_redmine_user_hours_report voor maandtotalen.
    PL: Pobierz wpisy czasu (tylko pierwsze 100). Użyj get_redmine_user_hours_report dla sum miesięcznych.
    PT: Recuperar entradas de tempo (apenas primeiras 100). Use get_redmine_user_hours_report para totais mensais.
    JA: 時間エントリを取得（最初の100のみ）。月次合計にはget_redmine_user_hours_reportを使用。
    ZH: 检索时间条目（仅前100个）。月度总计请使用get_redmine_user_hours_report。

    Parameters:
    - user_id: Filter by user ID (e.g., "32" for Sebastian Broers)
    - from_date: Start date (YYYY-MM-DD)
    - to_date: End date (YYYY-MM-DD)
    - project_id: Optional project filter
    """
    try:
        client = await _get_api_client(connection_id)
        params = {"limit": 100}
        if project_id:
            params["project_id"] = project_id
        if user_id:
            params["user_id"] = user_id
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
        logger.error("get_redmine_time_entries failed: %s", e)
        return _public_error()


@tool
async def get_redmine_user_hours_report(
    user_id: str,
    from_date: str,
    to_date: str,
    project_id: str = "",
    max_detail_entries: int = 20,
    connection_id: str = "",
) -> dict:
    """
    Get total hours for a specific user in a date range with pagination.
    Use this for 'hours in month' questions to get accurate totals.

    DE: Stunden-Report für einen Benutzer im Zeitraum. Nutze dies für 'Stunden im Monat' Fragen.
    EN: Hours report for a user in a date range. Use this for 'hours in month' questions.
    FR: Rapport d\'heures pour un utilisateur sur une période. Utilisez pour 'heures dans le mois'.
    ES: Informe de horas para un usuario en un rango de fechas. Úselo para 'horas en el mes'.
    IT: Report ore per un utente in un intervallo di date. Usa per 'ore nel mese'.
    NL: Urenrapport voor een gebruiker in een datumbereik. Gebruik voor 'uren in de maand'.
    PL: Raport godzin dla użytkownika w zakresie dat. Użyj dla 'godziny w miesiącu'.
    PT: Relatório de horas para um usuário em um intervalo de datas. Use para 'horas no mês'.
    JA: 日付範囲内のユーザーの時間レポート。月内の時間に使用。
    ZH: 用户在日期范围内的小时报告。用于月内小时数。

    Parameters:
    - user_id: User ID (e.g., "32")
    - from_date: Start date (YYYY-MM-DD, e.g., "2026-03-01")
    - to_date: End date (YYYY-MM-DD, e.g., "2026-03-31")
    - project_id: Optional project filter
    - max_detail_entries: Max entries to return in details (default 20)

    Returns:
    - total_hours: Sum of all hours
    - days_count: Number of unique days
    - entry_count: Total number of entries
    - summary_by_day: List of {date, total_hours, entry_count}
    - entries: Detailed entries (max max_detail_entries)
    - has_more_entries: Boolean if more entries exist
    """
    try:
        client = await _get_api_client(connection_id)

        all_entries = []
        offset = 0
        limit = 100
        total_count = None

        # Paginate through all results
        while True:
            params = {
                "limit": limit,
                "offset": offset,
                "user_id": user_id,
                "from": from_date,
                "to": to_date,
            }
            if project_id:
                params["project_id"] = project_id

            result = await _redmine_request(
                client["base_url"],
                client["api_key"],
                "GET",
                "time_entries.json",
                params,
                verify_ssl=client["verify_ssl"],
            )

            entries = result.get("time_entries", [])
            if not entries:
                break

            all_entries.extend(entries)

            # Check if we've got all entries
            if total_count is None:
                total_count = result.get("total_count", 0)

            offset += len(entries)

            # Safety check: if we got less than limit, we're done
            if len(entries) < limit:
                break

            # Safety check: prevent infinite loops
            if offset >= 10000:
                logger.warning(
                    _t(
                        de="Zu viele Zeiteinträge, stoppe bei 10000",
                        en="Too many time entries, stopping at 10000",
                        fr="Trop d'entrées de temps, arrêt à 10000",
                        es="Demasiadas entradas de tiempo, deteniendo en 10000",
                        it="Troppe voci temporali, arresto a 10000",
                        nl="Te veel tijditems, stoppen bij 10000",
                        pl="Zbyt wiele wpisów czasu, zatrzymanie przy 10000",
                        pt="Muitas entradas de tempo, parando em 10000",
                        ja="時間エントリが多すぎます、10000で停止",
                        zh="时间条目太多，在10000处停止",
                    )
                )
                break

        # Sum hours
        total_hours = sum(float(entry.get("hours", 0)) for entry in all_entries)

        # Format entries for display
        formatted_entries = []
        for entry in all_entries:
            try:
                project_name = ""
                if entry.get("project") and isinstance(entry["project"], dict):
                    project_name = entry["project"].get("name", "")

                issue_id = ""
                if entry.get("issue") and isinstance(entry["issue"], dict):
                    issue_id = str(entry["issue"].get("id", ""))

                formatted_entries.append(
                    {
                        "date": entry.get("spent_on", ""),
                        "hours": float(entry.get("hours", 0)),
                        "project": project_name,
                        "issue_id": issue_id,
                        "comments": entry.get("comments", ""),
                    }
                )
            except (AttributeError, TypeError, ValueError):
                logger.warning(
                    _t(
                        de="Fehlerhafter Time Entry übersprungen: %s",
                        en="Skipping malformed time entry: %s",
                        fr="Entrée de temps incorrecte ignorée: %s",
                        es="Entrada de tiempo malformada omitida: %s",
                        it="Voce temporale malformata saltata: %s",
                        nl="Malformed time entry overgeslagen: %s",
                        pl="Pominięto błędny wpis czasu: %s",
                        pt="Ignorando entrada de tempo malformada: %s",
                        ja="不正な時間エントリをスキップ: %s",
                        zh="跳过格式错误的时间条目: %s",
                    ),
                    entry,
                )
                continue

        # Group by day for compact summary (prevents LLM overload)
        from collections import defaultdict

        summary_by_day = defaultdict(lambda: {"hours": 0.0, "entries": []})
        for entry in formatted_entries:
            date = entry["date"]
            summary_by_day[date]["hours"] += entry["hours"]
            summary_by_day[date]["entries"].append(entry)

        # Sort by date
        sorted_days = sorted(summary_by_day.items(), reverse=True)

        # Limit detailed entries to prevent context overflow
        limited_entries = formatted_entries[:max_detail_entries]
        has_more = len(formatted_entries) > max_detail_entries

        return {
            "status": "success",
            "user_id": user_id,
            "from_date": from_date,
            "to_date": to_date,
            "total_hours": total_hours,
            "entry_count": len(all_entries),
            "days_count": len(sorted_days),
            "summary_by_day": [
                {
                    "date": date,
                    "total_hours": data["hours"],
                    "entry_count": len(data["entries"]),
                }
                for date, data in sorted_days
            ],
            "entries": limited_entries,
            "has_more_entries": has_more,
            "total_entries": len(formatted_entries),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error(
            _t(
                de="get_redmine_user_hours_report fehlgeschlagen für user_id=%s von=%s bis=%s: %s",
                en="get_redmine_user_hours_report failed for user_id=%s from=%s to=%s: %s",
                fr="get_redmine_user_hours_report échoué pour user_id=%s de=%s à=%s: %s",
                es="get_redmine_user_hours_report falló para user_id=%s desde=%s hasta=%s: %s",
                it="get_redmine_user_hours_report fallito per user_id=%s da=%s a=%s: %s",
                nl="get_redmine_user_hours_report mislukt voor user_id=%s van=%s tot=%s: %s",
                pl="get_redmine_user_hours_report nie powiodło się dla user_id=%s od=%s do=%s: %s",
                pt="get_redmine_user_hours_report falhou para user_id=%s de=%s até=%s: %s",
                ja="get_redmine_user_hours_report が user_id=%s の %s から %s までで失敗: %s",
                zh="get_redmine_user_hours_report 失败 user_id=%s 从=%s 到=%s: %s",
            ),
            user_id,
            from_date,
            to_date,
            e,
            exc_info=True,
        )
        return {
            "error": _t(
                de=f"Zeiteinträge-Abfrage fehlgeschlagen: {str(e)}",
                en=f"Time entries query failed: {str(e)}",
                fr=f"Échec de la requête des entrées de temps: {str(e)}",
                es=f"Error en la consulta de entradas de tiempo: {str(e)}",
                it=f"Query delle voci temporali fallita: {str(e)}",
                nl=f"Tijditems query mislukt: {str(e)}",
                pl=f"Zapytanie o wpisy czasu nie powiodło się: {str(e)}",
                pt=f"Consulta de entradas de tempo falhou: {str(e)}",
                ja=f"時間エントリのクエリに失敗しました: {str(e)}",
                zh=f"时间条目查询失败: {str(e)}",
            )
        }


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
            1 for i in issues if not i.get("status", {}).get("is_closed")
        )
        closed_count = sum(
            1 for i in issues if i.get("status", {}).get("is_closed")
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


# ═══════════════════════════════════════════════════════════════════════════════
# HRM Erweiterte Tools - Abwesenheiten, Kapazitäten, Feiertage verwalten
# ═══════════════════════════════════════════════════════════════════════════════


@tool
async def get_redmine_hrm_attendance_types(connection_id: str = "") -> dict:
    """
    Get all HRM attendance types/statuses (vacation, sick, etc.).
    Use this before creating attendance entries to know available types.

    DE: Abwesenheitstypen abrufen (Urlaub, Krankheit, etc.)
    EN: Get attendance types (vacation, sick leave, etc.)
    FR: Types d\'absence (congés, maladie, etc.)
    ES: Tipos de asistencia (vacaciones, enfermedad, etc.)
    """
    try:
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "GET",
                "endpoint": "attendance_types.json",
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_hrm_attendance_types failed: %s", e)
        return _public_error()


@tool
async def update_redmine_hrm_attendance(
    attendance_id: str,
    attendance_payload: Any,
    connection_id: str = "",
) -> dict:
    """
    Update an existing HRM attendance entry.
    Use this to edit vacation, sick leave, or other attendance entries.

    DE: Abwesenheitseintrag bearbeiten (Urlaub, Krankheit)
    EN: Update attendance entry (vacation, sick leave)
    FR: Modifier une entrée d\'absence (congés, maladie)
    ES: Actualizar entrada de asistencia (vacaciones, enfermedad)

    Example payload: {"attendance": {"status": "sick", "date": "2026-04-03"}}
    """
    try:
        payload = _coerce_dict(attendance_payload, "attendance_payload")
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "PUT",
                "endpoint": f"attendances/{attendance_id}.json",
                "payload": payload,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("update_redmine_hrm_attendance failed: %s", e)
        return _public_error()


@tool
async def delete_redmine_hrm_attendance(
    attendance_id: str,
    connection_id: str = "",
) -> dict:
    """
    Delete an HRM attendance entry.
    Use this to remove vacation, sick leave, or other attendance entries.

    DE: Abwesenheitseintrag löschen
    EN: Delete attendance entry
    FR: Supprimer une entrée d\'absence
    ES: Eliminar entrada de asistencia
    """
    try:
        return await call_redmine_hrm_api.ainvoke(
            {
                "method": "DELETE",
                "endpoint": f"attendances/{attendance_id}.json",
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("delete_redmine_hrm_attendance failed: %s", e)
        return _public_error()


@tool
async def get_redmine_time_entry_activities(connection_id: str = "") -> dict:
    """
    Get all time entry activities (development, meeting, etc.).
    Use this before logging time to know available activity types.

    DE: Aktivitäten für Zeiterfassung abrufen
    EN: Get time entry activities
    FR: Activités de saisie du temps
    ES: Actividades de registro de tiempo
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "enumerations/time_entry_activities.json",
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "activities": result.get("time_entry_activities", []),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_time_entry_activities failed: %s", e)
        return _public_error()


@tool
async def get_redmine_hrm_user_report(
    user_id: str,
    year: str,
    month: str,
    connection_id: str = "",
) -> dict:
    """
    Get comprehensive HRM report for a user including:
    - Total vacation days
    - Sick days
    - Other absences
    - Working days
    - Capacity/utilization

    DE: HRM Monatsreport für Benutzer (Urlaub, Krankheit, Abwesenheiten)
    EN: HRM monthly report for user (vacation, sick, absences)
    FR: Rapport HRM mensuel (congés, maladie, absences)
    ES: Informe HRM mensual (vacaciones, enfermedad, ausencias)

    Parameters:
    - user_id: User ID (e.g., "32")
    - year: Year (e.g., "2026")
    - month: Month (e.g., "03" for March)
    """
    try:
        # Calculate date range for the month
        from_date = f"{year}-{month}-01"
        # Simple month length calculation (doesn't handle all edge cases but sufficient)
        month_lengths = {
            "01": 31,
            "02": 28,
            "03": 31,
            "04": 30,
            "05": 31,
            "06": 30,
            "07": 31,
            "08": 31,
            "09": 30,
            "10": 31,
            "11": 30,
            "12": 31,
        }
        last_day = month_lengths.get(month, 30)
        to_date = f"{year}-{month}-{last_day}"

        # Get all attendances for the user in the month
        attendances_result = await get_redmine_hrm_attendances.ainvoke(
            {
                "from_date": from_date,
                "to_date": to_date,
                "user_id": user_id,
                "limit": 500,
                "connection_id": connection_id,
            }
        )

        if attendances_result.get("status") != "success":
            return {"error": "Failed to fetch attendances"}

        # Get capacity for the user
        capacity_result = await get_redmine_hrm_user_capacity.ainvoke(
            {
                "user_id": user_id,
                "from_date": from_date,
                "to_date": to_date,
                "connection_id": connection_id,
            }
        )

        # Analyze attendances
        attendances = attendances_result.get("data", {}).get("attendances", [])

        vacation_days = 0
        sick_days = 0
        other_absences = 0
        attendance_details = []

        for att in attendances:
            att_type = att.get("type", "").lower()
            status = att.get("status", "").lower()
            date = att.get("date", "")

            if "vacation" in att_type or "urlaub" in att_type:
                vacation_days += 1
                attendance_details.append(
                    {"date": date, "type": "vacation", "status": status}
                )
            elif "sick" in att_type or "krank" in att_type:
                sick_days += 1
                attendance_details.append(
                    {"date": date, "type": "sick", "status": status}
                )
            elif status not in ["present", "anwesend", "working"]:
                other_absences += 1
                attendance_details.append(
                    {"date": date, "type": "other", "status": status}
                )

        # Get time entries for the month
        time_result = await get_redmine_user_hours_report.ainvoke(
            {
                "user_id": user_id,
                "from_date": from_date,
                "to_date": to_date,
                "connection_id": connection_id,
            }
        )

        total_hours = (
            time_result.get("total_hours", 0)
            if time_result.get("status") == "success"
            else 0
        )

        return {
            "status": "success",
            "user_id": user_id,
            "year": year,
            "month": month,
            "summary": {
                "vacation_days": vacation_days,
                "sick_days": sick_days,
                "other_absences": other_absences,
                "total_absence_days": vacation_days + sick_days + other_absences,
                "total_hours_logged": total_hours,
            },
            "capacity": capacity_result.get("data", {})
            if capacity_result.get("status") == "success"
            else {},
            "attendance_details": attendance_details,
            "attendance_raw": attendances,
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_hrm_user_report failed: %s", e)
        return _public_error()


@tool
async def create_redmine_hrm_vacation(
    user_id: str,
    date: str,
    half_day: bool = False,
    comments: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a vacation entry for a user.
    Simplified wrapper for creating vacation attendance.

    DE: Urlaub eintragen für Benutzer
    EN: Create vacation entry for user
    FR: Créer une entrée de congés
    ES: Crear entrada de vacaciones

    Parameters:
    - user_id: User ID (e.g., "32")
    - date: Date (YYYY-MM-DD)
    - half_day: True for half day vacation
    - comments: Optional comments
    """
    try:
        payload = {
            "attendance": {
                "user_id": user_id,
                "date": date,
                "status": "vacation_half_day" if half_day else "vacation",
            }
        }
        if comments:
            payload["attendance"]["comments"] = comments

        return await create_redmine_hrm_attendance.ainvoke(
            {
                "attendance_payload": payload,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("create_redmine_hrm_vacation failed: %s", e)
        return _public_error()


@tool
async def create_redmine_hrm_sick_leave(
    user_id: str,
    date: str,
    half_day: bool = False,
    comments: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a sick leave entry for a user.
    Simplified wrapper for creating sick leave attendance.

    DE: Krankheit eintragen für Benutzer
    EN: Create sick leave entry for user
    FR: Créer une entrée de maladie
    ES: Crear entrada de baja por enfermedad

    Parameters:
    - user_id: User ID (e.g., "32")
    - date: Date (YYYY-MM-DD)
    - half_day: True for half day sick leave
    - comments: Optional comments (e.g., doctor's note number)
    """
    try:
        payload = {
            "attendance": {
                "user_id": user_id,
                "date": date,
                "status": "sick_half_day" if half_day else "sick",
            }
        }
        if comments:
            payload["attendance"]["comments"] = comments

        return await create_redmine_hrm_attendance.ainvoke(
            {
                "attendance_payload": payload,
                "connection_id": connection_id,
            }
        )
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("create_redmine_hrm_sick_leave failed: %s", e)
        return _public_error()


# ═══════════════════════════════════════════════════════════════════════════════
# User Administration Tools - Benutzerverwaltung
# ═══════════════════════════════════════════════════════════════════════════════


@tool
async def create_redmine_user(
    login: str,
    firstname: str,
    lastname: str,
    mail: str,
    password: str = "",
    admin: bool = False,
    connection_id: str = "",
) -> dict:
    """
    Create a new user in Redmine.
    Use this when the user asks to create a new Redmine account or add a user.

    DE: Neuen Redmine-Benutzer erstellen
    EN: Create new Redmine user
    FR: Créer un nouvel utilisateur Redmine
    ES: Crear nuevo usuario Redmine

    Parameters:
    - login: Username/login (required, unique)
    - firstname: First name
    - lastname: Last name
    - mail: Email address
    - password: Initial password (if empty, user must set via email)
    - admin: Grant administrator privileges (default: False)

    Returns:
    - Created user details including ID
    """
    try:
        client = await _get_api_client(connection_id)
        user_data = {
            "login": login,
            "firstname": firstname,
            "lastname": lastname,
            "mail": mail,
            "admin": admin,
        }
        if password:
            user_data["password"] = password

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            "users.json",
            data={"user": user_data},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"User created: {login} (ID: {result.get('user', {}).get('id')})",
            "user": result.get("user", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("create_redmine_user failed: %s", e)
        return _public_error()


@tool
async def get_redmine_user_details(user_id: str, connection_id: str = "") -> dict:
    """
    Get detailed information about a specific Redmine user.
    Use this to retrieve user details including email, groups, and permissions.

    DE: Benutzerdetails abrufen
    EN: Get user details
    FR: Détails de l'utilisateur
    ES: Detalles del usuario

    Parameters:
    - user_id: User ID (e.g., "32")

    Returns:
    - User details including groups, memberships, and API key presence
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            f"users/{user_id}.json",
            {"include": "groups,memberships"},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "user": result.get("user", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_user_details failed: %s", e)
        return _public_error()


@tool
async def update_redmine_user(
    user_id: str,
    firstname: str = "",
    lastname: str = "",
    mail: str = "",
    admin: bool | None = None,
    status: str = "",  # "1" = active, "3" = locked
    connection_id: str = "",
) -> dict:
    """
    Update an existing Redmine user's information.
    Use this to change user details, email, admin status, or activate/deactivate.

    DE: Benutzer aktualisieren (Status, Admin, E-Mail ändern)
    EN: Update user (status, admin, email)
    FR: Mettre à jour l'utilisateur
    ES: Actualizar usuario

    Parameters:
    - user_id: User ID to update (required)
    - firstname: New first name (optional)
    - lastname: New last name (optional)
    - mail: New email address (optional)
    - admin: Set admin privileges True/False (optional)
    - status: "1" for active, "3" for locked/inactive (optional)

    Returns:
    - Updated user details
    """
    try:
        client = await _get_api_client(connection_id)
        user_data = {}
        if firstname:
            user_data["firstname"] = firstname
        if lastname:
            user_data["lastname"] = lastname
        if mail:
            user_data["mail"] = mail
        if admin is not None:
            user_data["admin"] = admin
        if status:
            user_data["status"] = status

        if not user_data:
            return {"error": "No fields to update provided"}

        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "PUT",
            f"users/{user_id}.json",
            data={"user": user_data},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"User #{user_id} updated successfully.",
            "user": result.get("user", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("update_redmine_user failed: %s", e)
        return _public_error()


@tool
async def delete_redmine_user(user_id: str, connection_id: str = "") -> dict:
    """
    Delete a Redmine user permanently.
    Use with caution - this cannot be undone!

    DE: Benutzer löschen (unwiderruflich!)
    EN: Delete user (permanent!)
    FR: Supprimer l'utilisateur (définitif!)
    ES: Eliminar usuario (¡permanente!)

    Parameters:
    - user_id: User ID to delete

    Returns:
    - Success confirmation
    """
    try:
        client = await _get_api_client(connection_id)
        await _redmine_request(
            client["base_url"],
            client["api_key"],
            "DELETE",
            f"users/{user_id}.json",
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"User #{user_id} deleted successfully.",
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("delete_redmine_user failed: %s", e)
        return _public_error()


@tool
async def lock_redmine_user(user_id: str, connection_id: str = "") -> dict:
    """
    Lock/Deactivate a Redmine user (status = 3).
    Locked users cannot log in but their data is preserved.

    DE: Benutzer sperren (kann sich nicht mehr anmelden)
    EN: Lock user (cannot login anymore)
    FR: Verrouiller l'utilisateur
    ES: Bloquear usuario

    Parameters:
    - user_id: User ID to lock

    Returns:
    - Success confirmation
    """
    return await update_redmine_user.ainvoke(
        {"user_id": user_id, "status": "3", "connection_id": connection_id}
    )


@tool
async def unlock_redmine_user(user_id: str, connection_id: str = "") -> dict:
    """
    Unlock/Reactivate a locked Redmine user (status = 1).
    Restores user login capability.

    DE: Benutzer entsperren (Login wieder möglich)
    EN: Unlock user (login restored)
    FR: Déverrouiller l'utilisateur
    ES: Desbloquear usuario

    Parameters:
    - user_id: User ID to unlock

    Returns:
    - Success confirmation
    """
    return await update_redmine_user.ainvoke(
        {"user_id": user_id, "status": "1", "connection_id": connection_id}
    )


@tool
async def reset_redmine_user_password(
    user_id: str, new_password: str, connection_id: str = ""
) -> dict:
    """
    Reset/change a user's password in Redmine.
    Use this for password resets or forced password changes.

    DE: Passwort zurücksetzen/zuruecksetzen/ändern, Reset
    EN: Reset/change password
    FR: Réinitialiser le mot de passe
    ES: Restablecer contraseña

    Parameters:
    - user_id: User ID
    - new_password: New password (must meet Redmine password policy)

    Returns:
    - Success confirmation
    """
    try:
        client = await _get_api_client(connection_id)
        await _redmine_request(
            client["base_url"],
            client["api_key"],
            "PUT",
            f"users/{user_id}.json",
            data={"user": {"password": new_password}},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"Password reset for user #{user_id}.",
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("reset_redmine_user_password failed: %s", e)
        return _public_error()


@tool
async def add_redmine_user_to_group(
    user_id: str, group_id: str, connection_id: str = ""
) -> dict:
    """
    Add a user to a Redmine group.
    Use this to assign group memberships for permissions.

    DE: Benutzer zur Gruppe hinzufügen
    EN: Add user to group
    FR: Ajouter l'utilisateur au groupe
    ES: Agregar usuario al grupo

    Parameters:
    - user_id: User ID
    - group_id: Group ID

    Returns:
    - Success confirmation
    """
    try:
        client = await _get_api_client(connection_id)
        await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            f"groups/{group_id}/users.json",
            data={"user_id": user_id},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"User #{user_id} added to group #{group_id}.",
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("add_redmine_user_to_group failed: %s", e)
        return _public_error()


@tool
async def remove_redmine_user_from_group(
    user_id: str, group_id: str, connection_id: str = ""
) -> dict:
    """
    Remove a user from a Redmine group.
    Use this to revoke group memberships.

    DE: Benutzer aus Gruppe entfernen
    EN: Remove user from group
    FR: Retirer l'utilisateur du groupe
    ES: Eliminar usuario del grupo

    Parameters:
    - user_id: User ID
    - group_id: Group ID

    Returns:
    - Success confirmation
    """
    try:
        client = await _get_api_client(connection_id)
        await _redmine_request(
            client["base_url"],
            client["api_key"],
            "DELETE",
            f"groups/{group_id}/users/{user_id}.json",
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"User #{user_id} removed from group #{group_id}.",
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("remove_redmine_user_from_group failed: %s", e)
        return _public_error()


@tool
async def get_redmine_groups(connection_id: str = "") -> dict:
    """
    List all Redmine groups.
    Use this to see available groups for user assignments.

    DE: Alle Gruppen auflisten
    EN: List all groups
    FR: Lister tous les groupes
    ES: Listar todos los grupos

    Returns:
    - List of groups with IDs
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "GET",
            "groups.json",
            {"limit": 100},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "groups": result.get("groups", []),
            "total": result.get("total_count", 0),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("get_redmine_groups failed: %s", e)
        return _public_error()


@tool
async def create_redmine_group(name: str, connection_id: str = "") -> dict:
    """
    Create a new user group in Redmine.
    Use this to organize users into permission groups.

    DE: Neue Gruppe erstellen
    EN: Create new group
    FR: Créer un nouveau groupe
    ES: Crear nuevo grupo

    Parameters:
    - name: Group name (required, unique)

    Returns:
    - Created group details
    """
    try:
        client = await _get_api_client(connection_id)
        result = await _redmine_request(
            client["base_url"],
            client["api_key"],
            "POST",
            "groups.json",
            data={"group": {"name": name}},
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"Group created: {name} (ID: {result.get('group', {}).get('id')})",
            "group": result.get("group", {}),
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("create_redmine_group failed: %s", e)
        return _public_error()


@tool
async def delete_redmine_group(group_id: str, connection_id: str = "") -> dict:
    """
    Delete a Redmine group.
    Use this to remove empty or unused groups.

    DE: Gruppe löschen
    EN: Delete group
    FR: Supprimer le groupe
    ES: Eliminar grupo

    Parameters:
    - group_id: Group ID to delete

    Returns:
    - Success confirmation
    """
    try:
        client = await _get_api_client(connection_id)
        await _redmine_request(
            client["base_url"],
            client["api_key"],
            "DELETE",
            f"groups/{group_id}.json",
            verify_ssl=client["verify_ssl"],
        )
        return {
            "status": "success",
            "message": f"Group #{group_id} deleted.",
        }
    except _REDMINE_TOOL_EXCEPTIONS as e:
        logger.error("delete_redmine_group failed: %s", e)
        return _public_error()
