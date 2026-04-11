"""
OpenProject Module — LangGraph @tool functions.
OpenProject API for project management.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.openproject.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get OpenProject API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("openproject", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"OpenProject-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"OpenProject connection with ID '{connection_id}' not found.",
                    fr=f"Connexion OpenProject avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión de OpenProject con ID '{connection_id}' no encontrada.",
                    it=f"Connessione OpenProject con ID '{connection_id}' non trovata.",
                    nl=f"OpenProject-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie OpenProject z ID '{connection_id}' nie znalezione.",
                    pt=f"Conexão OpenProject com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のOpenProject接続が見つかりません。",
                    zh=f"未找到ID为 '{connection_id}' 的OpenProject连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("openproject")

    if conn:
        base_url = conn.config.get("url", "")
        api_key = conn.config.get("api_key", "")
        if not api_key:
            vault = get_vault()
            vault_key = conn.vault_keys.get("OPENPROJECT_API_KEY")
            if vault_key:
                api_key = await vault.get_secret(vault_key)
        return {"base_url": base_url, "api_key": api_key}

    base_url = os.environ.get("OPENPROJECT_HOST", "")
    vault = get_vault()
    api_key = await vault.get_secret("OPENPROJECT_API_KEY")
    if not api_key:
        api_key = os.environ.get("OPENPROJECT_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de="Keine OpenProject-Verbindung konfiguriert.",
                en="No OpenProject connection configured.",
                fr="Aucune connexion OpenProject configurée.",
                es="No hay conexión OpenProject configurada.",
                it="Nessuna connessione OpenProject configurata.",
                nl="Geen OpenProject-verbinding geconfigureerd.",
                pl="Nie skonfigurowano połączenia OpenProject.",
                pt="Nenhuma conexão OpenProject configurada.",
                ja="OpenProject接続が設定されていません。",
                zh="未配置OpenProject连接。",
            )
        )

    return {"base_url": base_url, "api_key": api_key}


async def _op_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to OpenProject API."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/api/v3{path}"
    headers = {"Authorization": f"Bearer {client['api_key']}"}

    logger.debug("OpenProject API request: %s %s", method, url)
    async with httpx.AsyncClient(headers=headers, timeout=30.0, verify=True) as session:
        try:
            resp = await session.request(method, url, json=json)
            if resp.status_code == 204:
                return {"status": "OK"}
            if resp.status_code == 201:
                return resp.json()
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "OpenProject API error: HTTP %s for %s", e.response.status_code, url
            )
            # Response text nicht loggen - könnte sensitive Daten enthalten
            raise ValueError(
                f"OpenProject API returned HTTP {e.response.status_code}"
            ) from e


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_openproject_projects(connection_id: str = "") -> str:
    """
    List all projects in OpenProject.
    Use this to see all available projects.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _op_request("GET", "/projects", client)
        projects = data.get("_embedded", {}).get("elements", [])
        if not projects:
            return _t(
                de="Keine Projekte gefunden",
                en="No projects found",
                fr="Aucun projet trouvé",
                es="No se encontraron proyectos",
                it="Nessun progetto trovato",
                nl="Geen projecten gevonden",
                pl="Nie znaleziono projektów",
                pt="Nenhum projeto encontrado",
                ja="プロジェクトが見つかりません",
                zh="未找到项目",
            )

        lines = [
            "📁 "
            + _t(
                de="Projekte",
                en="Projects",
                fr="Projets",
                es="Proyectos",
                it="Progetti",
                nl="Projecten",
                pl="Projekty",
                pt="Projetos",
                ja="プロジェクト",
                zh="项目",
            )
        ]
        for p in projects[:15]:
            status_icon = "✅" if p.get("status") == "active" else "📦"
            lines.append(f"  {status_icon} {p.get('name', '-')}")
            if p.get("identifier"):
                lines.append(f"      [{p.get('identifier')}]")

        total = len(projects)
        lines.append(f"\n✓ {total} Projekte")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("list_openproject_projects failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def get_openproject_project(project_name: str, connection_id: str = "") -> str:
    """
    Get details of a specific project.
    Use this to see project details and members.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _op_request("GET", "/projects", client)
        projects = data.get("_embedded", {}).get("elements", [])
        project = next(
            (
                p
                for p in projects
                if p.get("name") == project_name or p.get("identifier") == project_name
            ),
            None,
        )
        if not project:
            return _t(
                de=f"Projekt nicht gefunden: {project_name}",
                en=f"Project not found: {project_name}",
                fr=f"Projet non trouvé: {project_name}",
                es=f"Proyecto no encontrado: {project_name}",
                it=f"Progetto non trovato: {project_name}",
                nl=f"Project niet gevonden: {project_name}",
                pl=f"Nie znaleziono projektu: {project_name}",
                pt=f"Projeto não encontrado: {project_name}",
                ja=f"プロジェクトが見つかりません: {project_name}",
                zh=f"未找到项目: {project_name}",
            )

        project_id = project.get("id")
        details = await _op_request("GET", f"/projects/{project_id}", client)

        lines = [
            "📁 "
            + _t(
                de="Projektdetails",
                en="Project details",
                fr="Détails du projet",
                es="Detalles del proyecto",
                it="Dettagli progetto",
                nl="Projectdetails",
                pl="Szczegóły projektu",
                pt="Detalhes do projeto",
                ja="プロジェクト詳細",
                zh="项目详情",
            )
        ]
        lines.append(f"  {details.get('name', '-')}")
        if details.get("description"):
            desc = details.get("description", "")[:150]
            lines.append(f"  📝 {desc}")
        lines.append(f"  Status: {details.get('status', '-')}")
        if details.get("createdAt"):
            lines.append(f"  Erstellt: {details.get('createdAt', '')[:10]}")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("get_openproject_project failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def list_openproject_work_packages(
    project_name: str = "", connection_id: str = ""
) -> str:
    """
    List work packages (tasks, bugs) in OpenProject.
    Use this to see all tasks, optionally filtered by project.
    """
    try:
        client = await _get_api_client(connection_id)
        if project_name:
            projects = await _op_request("GET", "/projects", client)
            proj_list = projects.get("_embedded", {}).get("elements", [])
            project = next(
                (
                    p
                    for p in proj_list
                    if p.get("name") == project_name
                    or p.get("identifier") == project_name
                ),
                None,
            )
            if project:
                data = await _op_request(
                    "GET",
                    f"/projects/{project.get('id')}/work_packages",
                    client,
                )
            else:
                return _t(
                    de=f"Projekt nicht gefunden: {project_name}",
                    en=f"Project not found: {project_name}",
                    fr=f"Projet non trouvé: {project_name}",
                    es=f"Proyecto no encontrado: {project_name}",
                    it=f"Progetto non trovato: {project_name}",
                    nl=f"Project niet gevonden: {project_name}",
                    pl=f"Nie znaleziono projektu: {project_name}",
                    pt=f"Projeto não encontrado: {project_name}",
                    ja=f"プロジェクトが見つかりません: {project_name}",
                    zh=f"未找到项目: {project_name}",
                )
        else:
            data = await _op_request("GET", "/work_packages", client)

        wps = data.get("_embedded", {}).get("elements", [])
        if not wps:
            return _t(
                de="Keine Work Packages gefunden",
                en="No work packages found",
                fr="Aucun package de travail trouvé",
                es="No se encontraron paquetes de trabajo",
                it="Nessun pacchetto di lavoro trovato",
                nl="Geen work packages gevonden",
                pl="Nie znaleziono pakietów pracy",
                pt="Nenhum pacote de trabalho encontrado",
                ja="Work Packageが見つかりません",
                zh="未找到工作包",
            )

        lines = [
            "📋 "
            + _t(
                de="Work Packages",
                en="Work packages",
                fr="Packages de travail",
                es="Paquetes de trabajo",
                it="Pacchetti di lavoro",
                nl="Work packages",
                pl="Pakiety pracy",
                pt="Pacotes de trabalho",
                ja="Work Package",
                zh="工作包",
            )
        ]
        for wp in wps[:15]:
            type_icon = (
                "🐛"
                if wp.get("type") == "Bug"
                else "✅"
                if wp.get("type") == "Task"
                else "📝"
            )
            status = (
                wp.get("status", {}).get("name", "-")
                if isinstance(wp.get("status"), dict)
                else wp.get("status", "-")
            )
            lines.append(f"  {type_icon} #{wp.get('id')} {wp.get('subject', '-')}")
            lines.append(f"      Status: {status}")

        total = len(wps)
        lines.append(f"\n✓ {total} Work Packages")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("list_openproject_work_packages failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def get_openproject_work_package(
    work_package_id: int, connection_id: str = ""
) -> str:
    """
    Get details of a specific work package.
    Use this to see full task details.
    """
    try:
        client = await _get_api_client(connection_id)
        wp = await _op_request("GET", f"/work_packages/{work_package_id}", client)

        lines = [
            "📋 "
            + _t(
                de="Work Package Details",
                en="Work package details",
                fr="Détails du package de travail",
                es="Detalles del paquete de trabajo",
                it="Dettagli pacchetto di lavoro",
                nl="Work package details",
                pl="Szczegóły pakietu pracy",
                pt="Detalhes do pacote de trabalho",
                ja="Work Package詳細",
                zh="工作包详情",
            )
        ]
        lines.append(f"  #{wp.get('id')}: {wp.get('subject', '-')}")
        lines.append(f"  Type: {wp.get('type', '-')}")

        status = wp.get("status")
        if isinstance(status, dict):
            lines.append(f"  Status: {status.get('name', '-')}")
        else:
            lines.append(f"  Status: {status}")

        priority = wp.get("priority")
        if isinstance(priority, dict):
            lines.append(f"  Priority: {priority.get('name', '-')}")

        if wp.get("description"):
            desc = wp.get("description", "")[:200]
            lines.append(f"  📝 {desc}")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("get_openproject_work_package failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def list_openproject_users(connection_id: str = "") -> str:
    """
    List users in OpenProject.
    Use this to see all team members.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _op_request("GET", "/users", client)
        users = data.get("_embedded", {}).get("elements", [])
        if not users:
            return _t(
                de="Keine Benutzer gefunden",
                en="No users found",
                fr="Aucun utilisateur trouvé",
                es="No se encontraron usuarios",
                it="Nessun utente trovato",
                nl="Geen gebruikers gevonden",
                pl="Nie znaleziono użytkowników",
                pt="Nenhum usuário encontrado",
                ja="ユーザーが見つかりません",
                zh="未找到用户",
            )

        lines = [
            "👥 "
            + _t(
                de="Benutzer",
                en="Users",
                fr="Utilisateurs",
                es="Usuarios",
                it="Utenti",
                nl="Gebruikers",
                pl="Użytkownicy",
                pt="Usuários",
                ja="ユーザー",
                zh="用户",
            )
        ]
        for u in users[:15]:
            name = f"{u.get('firstname', '')} {u.get('lastname', '')}".strip() or u.get(
                "login", "-"
            )
            status = u.get("status", "active")
            status_icon = "✅" if status == "active" else "❌"
            lines.append(f"  {status_icon} {name} ({u.get('email', '-')})")

        total = len(users)
        lines.append(f"\n✓ {total} Benutzer")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("list_openproject_users failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def list_openproject_time_entries(
    project_name: str = "", connection_id: str = ""
) -> str:
    """
    List time entries in OpenProject.
    Use this to see logged time.
    """
    try:
        client = await _get_api_client(connection_id)
        if project_name:
            projects = await _op_request("GET", "/projects", client)
            proj_list = projects.get("_embedded", {}).get("elements", [])
            project = next(
                (
                    p
                    for p in proj_list
                    if p.get("name") == project_name
                    or p.get("identifier") == project_name
                ),
                None,
            )
            if project:
                data = await _op_request(
                    "GET",
                    f"/projects/{project.get('id')}/time_entries",
                    client,
                )
            else:
                return _t(
                    de=f"Projekt nicht gefunden: {project_name}",
                    en=f"Project not found: {project_name}",
                    fr=f"Projet non trouvé: {project_name}",
                    es=f"Proyecto no encontrado: {project_name}",
                    it=f"Progetto non trovato: {project_name}",
                    nl=f"Project niet gevonden: {project_name}",
                    pl=f"Nie znaleziono projektu: {project_name}",
                    pt=f"Projeto não encontrado: {project_name}",
                    ja=f"プロジェクトが見つかりません: {project_name}",
                    zh=f"未找到项目: {project_name}",
                )
        else:
            data = await _op_request("GET", "/time_entries", client)

        entries = data.get("_embedded", {}).get("elements", [])
        if not entries:
            return _t(
                de="Keine Time Entries",
                en="No time entries",
                fr="Aucune entrée de temps",
                es="No hay entradas de tiempo",
                it="Nessuna entrada di tempo",
                nl="Geen tijdentries",
                pl="Brak wpisów czasu",
                pt="Nenhuma entrada de tempo",
                ja="時間エントリがありません",
                zh="没有时间条目",
            )

        lines = [
            "⏱️ "
            + _t(
                de="Time Entries",
                en="Time entries",
                fr="Entrées de temps",
                es="Entradas de tiempo",
                it="Entry di tempo",
                nl="Tijdentries",
                pl="Wpisy czasu",
                pt="Entradas de tempo",
                ja="時間エントリ",
                zh="时间条目",
            )
        ]
        for e in entries[:15]:
            hours = e.get("hours", 0)
            date = e.get("spentOn", "-")
            activity = e.get("_embedded", {}).get("activity", {}).get("name", "-")
            lines.append(f"  {date}: {hours}h ({activity})")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("list_openproject_time_entries failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def create_openproject_work_package(
    project_name: str,
    subject: str,
    type: str = "Task",
    description: str = "",
    connection_id: str = "",
) -> str:
    """
    Create a new work package (task) in OpenProject.
    Use this to create a new task.
    """
    try:
        client = await _get_api_client(connection_id)
        projects = await _op_request("GET", "/projects", client)
        proj_list = projects.get("_embedded", {}).get("elements", [])
        project = next(
            (
                p
                for p in proj_list
                if p.get("name") == project_name or p.get("identifier") == project_name
            ),
            None,
        )
        if not project:
            return _t(
                de=f"Projekt nicht gefunden: {project_name}",
                en=f"Project not found: {project_name}",
                fr=f"Projet non trouvé: {project_name}",
                es=f"Proyecto no encontrado: {project_name}",
                it=f"Progetto non trovato: {project_name}",
                nl=f"Project niet gevonden: {project_name}",
                pl=f"Nie znaleziono projektu: {project_name}",
                pt=f"Projeto não encontrado: {project_name}",
                ja=f"プロジェクトが見つかりません: {project_name}",
                zh=f"未找到项目: {project_name}",
            )

        project_id = project.get("id")
        wp_data = {
            "subject": subject,
            "description": {"raw": description},
            "type": type,
            "project": {"href": f"/api/v3/projects/{project_id}"},
        }
        result = await _op_request("POST", "/work_packages", client, json=wp_data)

        return _t(
            de=f"✅ Work Package erstellt: #{result.get('id')} - {subject}",
            en=f"✅ Work package created: #{result.get('id')} - {subject}",
            fr=f"✅ Package de travail créé: #{result.get('id')} - {subject}",
            es=f"✅ Paquete de trabajo creado: #{result.get('id')} - {subject}",
            it=f"✅ Pacchetto di lavoro creato: #{result.get('id')} - {subject}",
            nl=f"✅ Work package aangemaakt: #{result.get('id')} - {subject}",
            pl=f"✅ Utworzono pakiet pracy: #{result.get('id')} - {subject}",
            pt=f"✅ Pacote de trabalho criado: #{result.get('id')} - {subject}",
            ja=f"✅ Work Packageを作成しました: #{result.get('id')} - {subject}",
            zh=f"✅ 已创建工作包: #{result.get('id')} - {subject}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("create_openproject_work_package failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def update_openproject_work_package(
    work_package_id: int,
    status: str = "",
    subject: str = "",
    start_date: str = "",
    due_date: str = "",
    done_ratio: int = -1,
    connection_id: str = "",
) -> str:
    """
    Update a work package (task) in OpenProject.
    Use this to change status, subject, dates, or progress.

    For Gantt chart updates, provide start_date and due_date in ISO format (YYYY-MM-DD).
    The done_ratio (0-100) updates the progress percentage shown in Gantt.
    """
    try:
        client = await _get_api_client(connection_id)

        # First get current work package to obtain lockVersion (required for optimistic locking)
        try:
            current_wp = await _op_request(
                "GET", f"/work_packages/{work_package_id}", client
            )
            lock_version = current_wp.get("lockVersion", 0)
        except Exception:
            lock_version = 0  # Fallback if we can't get current version

        update_data = {
            "lockVersion": lock_version,  # Required for optimistic locking
        }

        if subject:
            update_data["subject"] = subject
        if status:
            status_data = {"name": status}
            update_data["status"] = status_data

        # Gantt-relevant fields
        if start_date:
            # ISO 8601 format expected: "2026-04-10"
            update_data["startDate"] = start_date
        if due_date:
            update_data["dueDate"] = due_date
        if done_ratio >= 0 and done_ratio <= 100:
            update_data["percentageDone"] = done_ratio

        # Only send update if we have data beyond lockVersion
        if len(update_data) > 1:
            await _op_request(
                "PATCH",
                f"/work_packages/{work_package_id}",
                client,
                json=update_data,
            )

            # Build success message with details
            changes = []
            if subject:
                changes.append("subject")
            if status:
                changes.append("status")
            if start_date:
                changes.append("start_date")
            if due_date:
                changes.append("due_date")
            if done_ratio >= 0:
                changes.append(f"progress ({done_ratio}%)")

            change_str = ", ".join(changes) if changes else "data"

            return _t(
                de=f"✅ Work Package #{work_package_id} aktualisiert ({change_str}). Gantt-Diagramm aktualisiert.",
                en=f"✅ Work package #{work_package_id} updated ({change_str}). Gantt chart updated.",
                fr=f"✅ Package de travail #{work_package_id} mis à jour ({change_str}). Diagramme de Gantt mis à jour.",
                es=f"✅ Paquete de trabajo #{work_package_id} actualizado ({change_str}). Diagrama de Gantt actualizado.",
                it=f"✅ Pacchetto di lavoro #{work_package_id} aggiornato ({change_str}). Diagramma di Gantt aggiornato.",
                nl=f"✅ Work package #{work_package_id} bijgewerkt ({change_str}). Gantt-diagram bijgewerkt.",
                pl=f"✅ Zaktualizowano pakiet pracy #{work_package_id} ({change_str}). Wykres Gantt zaktualizowany.",
                pt=f"✅ Pacote de trabalho #{work_package_id} atualizado ({change_str}). Diagrama de Gantt atualizado.",
                ja=f"✅ Work Package #{work_package_id}を更新しました ({change_str})。ガントチャートを更新しました。",
                zh=f"✅ 已更新工作包 #{work_package_id} ({change_str})。甘特图已更新。",
            )
        else:
            return _t(
                de=f"⚠️ Keine Änderungen für Work Package #{work_package_id}",
                en=f"⚠️ No changes for work package #{work_package_id}",
                fr=f"⚠️ Aucune modification pour le package de travail #{work_package_id}",
                es=f"⚠️ Sin cambios para el paquete de trabajo #{work_package_id}",
                it=f"⚠️ Nessuna modifica per il pacchetto di lavoro #{work_package_id}",
                nl=f"⚠️ Geen wijzigingen voor work package #{work_package_id}",
                pl=f"⚠️ Brak zmian dla pakietu pracy #{work_package_id}",
                pt=f"⚠️ Sem alterações para o pacote de trabalho #{work_package_id}",
                ja=f"⚠️ Work Package #{work_package_id}に変更はありません",
                zh=f"⚠️ 工作包 #{work_package_id} 无变更",
            )

    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("update_openproject_work_package failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def log_openproject_time(
    project_name: str,
    hours: float,
    activity: str = "Development",
    work_package_id: int = None,
    comment: str = "",
    connection_id: str = "",
) -> str:
    """
    Log time entry in OpenProject.
    Use this to log hours worked.
    """
    try:
        client = await _get_api_client(connection_id)
        projects = await _op_request("GET", "/projects", client)
        proj_list = projects.get("_embedded", {}).get("elements", [])
        project = next(
            (
                p
                for p in proj_list
                if p.get("name") == project_name or p.get("identifier") == project_name
            ),
            None,
        )
        if not project:
            return _t(
                de=f"Projekt nicht gefunden: {project_name}",
                en=f"Project not found: {project_name}",
                fr=f"Projet non trouvé: {project_name}",
                es=f"Proyecto no encontrado: {project_name}",
                it=f"Progetto non trovato: {project_name}",
                nl=f"Project niet gevonden: {project_name}",
                pl=f"Nie znaleziono projektu: {project_name}",
                pt=f"Projeto não encontrado: {project_name}",
                ja=f"プロジェクトが見つかりません: {project_name}",
                zh=f"未找到项目: {project_name}",
            )

        project_id = project.get("id")
        entry_data = {
            "hours": hours,
            "spentOn": datetime.now().strftime("%Y-%m-%d"),
            "project": {"href": f"/api/v3/projects/{project_id}"},
        }

        if work_package_id:
            entry_data["workPackage"] = {
                "href": f"/api/v3/work_packages/{work_package_id}"
            }

        if comment:
            entry_data["comment"] = {"raw": comment}

        result = await _op_request("POST", "/time_entries", client, json=entry_data)

        return _t(
            de=f"✅ {hours}h gebucht für {project_name}",
            en=f"✅ {hours}h logged for {project_name}",
            fr=f"✅ {hours}h enregistré pour {project_name}",
            es=f"✅ {hours}h registrado para {project_name}",
            it=f"✅ {hours}h registrato per {project_name}",
            nl=f"✅ {hours}h geboekt voor {project_name}",
            pl=f"✅ {hours}zarejestrowane dla {project_name}",
            pt=f"✅ {hours}h registrado para {project_name}",
            ja=f"✅ {hours}hを{project_name}に記録しました",
            zh=f"✅ 已记录 {hours}h 用于 {project_name}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        httpx.RequestError,
        OSError,
    ) as e:
        logger.error("log_openproject_time failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )
