"""
Microsoft Entra Module — LangGraph @tool functions.
Microsoft Graph API (Azure AD / Entra ID).
"""

from __future__ import annotations

import logging
import os
from typing import Optional
from urllib.parse import quote

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.microsoft_entra.tools")

GRAPH_URL = "https://graph.microsoft.com/v1.0"


def _graph_user_path(user_principal_name: str) -> str:
    """Return a Microsoft Graph /users path preserving UPN semantics."""
    user = user_principal_name.strip()
    if not user:
        raise ValueError(
            _t(
                de="Benutzer-ID darf nicht leer sein.",
                en="User ID must not be empty.",
            )
        )
    return f"/users/{quote(user, safe='')}"


def _escape_odata_string(value: str) -> str:
    return value.replace("'", "''")


async def _get_user_object_id(user_principal_name: str, token: str) -> str:
    user = await _graph_request("GET", _graph_user_path(user_principal_name), token)
    object_id = user.get("id")
    if not object_id:
        raise ValueError(
            _t(
                de=f"Benutzer-ID nicht gefunden für: {user_principal_name}",
                en=f"User object ID not found for: {user_principal_name}",
            )
        )
    return object_id


async def _get_token(connection_id: str = "") -> str:
    """Get access token using client credentials flow."""
    if connection_id:
        conn = await ConnectionManager.get_connection("microsoft_entra", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Entra-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Entra connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Entra avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión de Entra con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Entra con ID '{connection_id}' non trovata.",
                    nl=f"Entra-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Nie znaleziono połączenia Entra o ID '{connection_id}'.",
                    pt=f"Conexão Entra com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' の Entra 接続が見つかりません。",
                    zh=f"未找到 ID 为 '{connection_id}' 的 Entra 连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("microsoft_entra")

    if conn:
        tenant_id = conn.config.get("tenant_id", "")
        client_id = conn.config.get("client_id", "")
        vault = get_vault()
        client_secret = None
        secret_path = conn.vault_keys.get("ENTRA_CLIENT_SECRET")
        if secret_path:
            client_secret = await vault.get_secret(secret_path)
        if not client_secret:
            client_secret = os.environ.get("ENTRA_CLIENT_SECRET", "")
    else:
        tenant_id = os.environ.get("ENTRA_TENANT_ID", "")
        client_id = os.environ.get("ENTRA_CLIENT_ID", "")
        vault = get_vault()
        client_secret = await vault.get_secret("ENTRA_CLIENT_SECRET")

    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            _t(
                de="Keine Entra-Verbindung konfiguriert.",
                en="No Entra connection configured.",
                fr="Aucune connexion Entra configurée.",
                es="No hay conexión Entra configurada.",
                it="Nessuna connessione Entra configurata.",
                nl="Geen Entra-verbinding geconfigureerd.",
                pl="Nie skonfigurowano połączenia Entra.",
                pt="Nenhuma conexão Entra configurada.",
                ja="Entra 接続が設定されていません。",
                zh="未配置 Entra 连接。",
            )
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


async def _graph_request(
    method: str, path: str, token: str, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to Microsoft Graph."""
    url = f"{GRAPH_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        async with session.request(method, url, json=json) as resp:
            if resp.status == 204:
                return {"status": "OK"}
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ════════════════════════════════════════════════��══════


@tool
async def list_entra_users(connection_id: str = "") -> str:
    """
    List users in Microsoft Entra ID.
    Use this to get all users or search for specific users.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/users", token)
        users = data.get("value", [])
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
        total = len(users)
        shown = min(total, 15)
        for u in users[:shown]:
            enabled = "✅" if u.get("accountEnabled", True) else "❌"
            lines.append(
                f"  {enabled} {u.get('displayName', '-')} <{u.get('userPrincipalName', '-')}>"
            )

        if total > shown:
            extra = total - shown
            lines.append(
                "\n💡 "
                + _t(
                    de=f"+{extra} weitere Benutzer (insgesamt {total})",
                    en=f"+{extra} more users (total {total})",
                    fr=f"+{extra} autres utilisateurs (total {total})",
                    es=f"+{extra} usuarios más (total {total})",
                    it=f"+{extra} altri utenti (totale {total})",
                    nl=f"+{extra} meer gebruikers (totaal {total})",
                    pl=f"+{extra} więcej użytkowników (łącznie {total})",
                    pt=f"+{extra} mais usuários (total {total})",
                    ja=f"他 {extra} ユーザー (合計 {total})",
                    zh=f"还有 {extra} 个用户 (共 {total})",
                )
            )
        else:
            lines.append(
                "\n✓ "
                + _t(
                    de=f"{total} Benutzer gesamt",
                    en=f"{total} users total",
                    fr=f"{total} utilisateurs au total",
                    es=f"{total} usuarios en total",
                    it=f"{total} utenti in totale",
                    nl=f"{total} gebruikers totaal",
                    pl=f"{total} użytkowników łącznie",
                    pt=f"{total} usuários no total",
                    ja=f"合計 {total} ユーザー",
                    zh=f"共 {total} 个用户",
                )
            )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_entra_users failed: %s", e)
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
async def search_entra_user(query: str, connection_id: str = "") -> str:
    """
    Search for a user by name or email.
    Use this when looking for a specific user.
    """
    try:
        token = await _get_token(connection_id)
        filter_escape = query.replace("'", "''")
        data = await _graph_request(
            "GET",
            f"/users?$filter=startswith(displayName,'{filter_escape}') or startswith(mail,'{filter_escape}') or startswith(userPrincipalName,'{filter_escape}')&$top=10",
            token,
        )
        users = data.get("value", [])
        if not users:
            return _t(
                de=f"Kein Benutzer gefunden für '{query}'",
                en=f"No user found for '{query}'",
                fr=f"Aucun utilisateur trouvé pour '{query}'",
                es=f"No se encontró ningún usuario para '{query}'",
                it=f"Nessun utente trovato per '{query}'",
                nl=f"Geen gebruiker gevonden voor '{query}'",
                pl=f"Nie znaleziono użytkownika dla '{query}'",
                pt=f"Nenhum usuário encontrado para '{query}'",
                ja=f"'{query}' のユーザーは見つかりません",
                zh=f"未找到用户 '{query}'",
            )

        lines = [
            "🔍 "
            + _t(
                de="Suchergebnisse",
                en="Search results",
                fr="Résultats de recherche",
                es="Resultados de búsqueda",
                it="Risultati della ricerca",
                nl="Zoekresultaten",
                pl="Wyniki wyszukiwania",
                pt="Resultados da pesquisa",
                ja="検索結果",
                zh="搜索结果",
            )
            + f" '{query}'"
        ]
        for u in users:
            enabled = "✅" if u.get("accountEnabled", True) else "❌"
            lines.append(
                f"  {enabled} {u.get('displayName', '-')}\n    {u.get('userPrincipalName', '-')}"
            )
            if u.get("jobTitle"):
                lines.append(f"    📋 {u.get('jobTitle')}")
            if u.get("department"):
                lines.append(f"    🏢 {u.get('department')}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("search_entra_user failed: %s", e)
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
async def get_user_details(user_principal_name: str, connection_id: str = "") -> str:
    """
    Get detailed information about a specific user.
    Use this to get full user details including manager, device, licenses.
    """
    try:
        token = await _get_token(connection_id)
        user = await _graph_request("GET", _graph_user_path(user_principal_name), token)

        lines = [
            "👤 "
            + _t(
                de="Benutzerdetails",
                en="User details",
                fr="Détails de l'utilisateur",
                es="Detalles del usuario",
                it="Dettagli dell'utente",
                nl="Gebruikersdetails",
                pl="Szczegóły użytkownika",
                pt="Detalhes do usuário",
                ja="ユーザー詳細",
                zh="用户详情",
            )
        ]
        lines.append(f"  {user.get('displayName', '-')}")
        lines.append(f"  📧 {user.get('userPrincipalName', '-')}")
        if user.get("mail"):
            lines.append(f"  📫 {user.get('mail')}")
        if user.get("jobTitle"):
            lines.append(f"  📋 {user.get('jobTitle')}")
        if user.get("department"):
            lines.append(f"  🏢 {user.get('department')}")
        if user.get("officeLocation"):
            lines.append(f"  📍 {user.get('officeLocation')}")

        status = _t(
            de="✅ Aktiv" if user.get("accountEnabled") else "❌ Deaktiviert",
            en="✅ Active" if user.get("accountEnabled") else "❌ Disabled",
            fr="✅ Actif" if user.get("accountEnabled") else "❌ Désactivé",
            es="✅ Activo" if user.get("accountEnabled") else "❌ Deshabilitado",
            it="✅ Attivo" if user.get("accountEnabled") else "❌ Disabilitato",
            nl="✅ Actief" if user.get("accountEnabled") else "❌ Uitgeschakeld",
            pl="✅ Aktywny" if user.get("accountEnabled") else "❌ Wyłączony",
            pt="✅ Ativo" if user.get("accountEnabled") else "❌ Desativado",
            ja="✅ 有効" if user.get("accountEnabled") else "❌ 無効",
            zh="✅ 启用" if user.get("accountEnabled") else "❌ 禁用",
        )
        lines.append(f"  Status: {status}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_user_details failed: %s", e)
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
async def list_entra_groups(connection_id: str = "") -> str:
    """
    List groups in Microsoft Entra ID.
    Use this to get all groups or security groups.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/groups", token)
        groups = data.get("value", [])
        if not groups:
            return _t(
                de="Keine Gruppen gefunden",
                en="No groups found",
                fr="Aucun groupe trouvé",
                es="No se encontraron grupos",
                it="Nessun gruppo trovato",
                nl="Geen groepen gevonden",
                pl="Nie znaleziono grup",
                pt="Nenhum grupo encontrado",
                ja="グループが見つかりません",
                zh="未找到组",
            )

        lines = [
            "👥 "
            + _t(
                de="Gruppen",
                en="Groups",
                fr="Groupes",
                es="Grupos",
                it="Gruppi",
                nl="Groepen",
                pl="Grupy",
                pt="Grupos",
                ja="グループ",
                zh="组",
            )
        ]
        for g in groups[:15]:
            sec = "🔒" if g.get("securityEnabled") else "📧"
            dyn = "⚡" if "DynamicMembership" in g.get("groupTypes", []) else ""
            lines.append(f"  {sec}{dyn} {g.get('displayName', '-')}")

        count = len(groups)
        lines.append(
            "\n✓ "
            + _t(
                de=f"{count} Gruppen gesamt",
                en=f"{count} groups total",
                fr=f"{count} groupes au total",
                es=f"{count} grupos en total",
                it=f"{count} gruppi in totale",
                nl=f"{count} groepen totaal",
                pl=f"{count} grup łącznie",
                pt=f"{count} grupos no total",
                ja=f"{count} グループ (合計)",
                zh=f"{count} 个组 (共)",
            )
        )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_entra_groups failed: %s", e)
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
async def get_group_members(group_name: str, connection_id: str = "") -> str:
    """
    Get members of a specific group.
    Use this to see who belongs to a group.
    """
    try:
        token = await _get_token(connection_id)
        group_filter = _escape_odata_string(group_name)
        search = f"/groups?$filter=startswith(displayName,'{group_filter}')"
        data = await _graph_request("GET", search, token)
        groups = data.get("value", [])
        if not groups:
            return _t(
                de=f"Gruppe nicht gefunden: {group_name}",
                en=f"Group not found: {group_name}",
                fr=f"Groupe non trouvé: {group_name}",
                es=f"Grupo no encontrado: {group_name}",
                it=f"Gruppo non trovato: {group_name}",
                nl=f"Groep niet gevonden: {group_name}",
                pl=f"Nie znaleziono grupy: {group_name}",
                pt=f"Grupo não encontrado: {group_name}",
                ja=f"グループが見つかりません: {group_name}",
                zh=f"未找到组: {group_name}",
            )

        group = groups[0]
        group_id = group["id"]

        members = await _graph_request("GET", f"/groups/{group_id}/members", token)
        mems = members.get("value", [])
        if not mems:
            return _t(
                de=f"Keine Mitglieder in '{group.get('displayName')}'",
                en=f"No members in '{group.get('displayName')}'",
                fr=f"Aucun membre dans '{group.get('displayName')}'",
                es=f"Sin miembros en '{group.get('displayName')}'",
                it=f"Nessun membro in '{group.get('displayName')}'",
                nl=f"Geen leden in '{group.get('displayName')}'",
                pl=f"Brak członków w '{group.get('displayName')}'",
                pt=f"Nenhum membro em '{group.get('displayName')}'",
                ja=f"'{group.get('displayName')}' にメンバーがいません",
                zh=f"'{group.get('displayName')}' 中没有成员",
            )

        lines = [
            "👥 "
            + _t(
                de="Gruppenmitglieder",
                en="Group members",
                fr="Membres du groupe",
                es="Miembros del grupo",
                it="Membri del gruppo",
                nl="Groepleden",
                pl="Członkowie grupy",
                pt="Membros do grupo",
                ja="グループメンバー",
                zh="组成员",
            )
            + f": {group.get('displayName')}"
        ]
        for m in mems:
            obj_type = m.get("@odata.type", "#microsoft.graphirectoryObject")
            if "user" in obj_type.lower():
                icon = "👤"
            elif "group" in obj_type.lower():
                icon = "👥"
            else:
                icon = "📦"
            lines.append(f"  {icon} {m.get('displayName', '-')}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_group_members failed: %s", e)
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
async def list_entra_applications(connection_id: str = "") -> str:
    """
    List registered applications in Entra ID.
    Use this to see all Azure AD applications.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/applications", token)
        apps = data.get("value", [])
        if not apps:
            return _t(
                de="Keine Anwendungen gefunden",
                en="No applications found",
                fr="Aucune application trouvée",
                es="No se encontraron aplicaciones",
                it="Nessuna applicazione trovata",
                nl="Geen applicaties gevonden",
                pl="Nie znaleziono aplikacji",
                pt="Nenhum aplicativo encontrado",
                ja="アプリケーションが見つかりません",
                zh="未找到应用程序",
            )

        lines = [
            "📱 "
            + _t(
                de="Anwendungen",
                en="Applications",
                fr="Applications",
                es="Aplicaciones",
                it="Applicazioni",
                nl="Applicaties",
                pl="Aplikacje",
                pt="Aplicativos",
                ja="アプリケーション",
                zh="应用程序",
            )
        ]
        for a in apps[:15]:
            lines.append(f"  • {a.get('displayName', '-')}")
            if a.get("publisherDomain"):
                lines.append(
                    "    "
                    + _t(
                        de=f"Herausgeber: {a.get('publisherDomain')}",
                        en=f"Publisher: {a.get('publisherDomain')}",
                        fr=f"Éditeur: {a.get('publisherDomain')}",
                        es=f"Editor: {a.get('publisherDomain')}",
                        it=f"Editore: {a.get('publisherDomain')}",
                        nl=f"Uitgever: {a.get('publisherDomain')}",
                        pl=f"Wydawca: {a.get('publisherDomain')}",
                        pt=f"Editor: {a.get('publisherDomain')}",
                        ja=f"発行元: {a.get('publisherDomain')}",
                        zh=f"发布者: {a.get('publisherDomain')}",
                    )
                )

        count = len(apps)
        lines.append(
            "\n✓ "
            + _t(
                de=f"{count} Anwendungen gesamt",
                en=f"{count} applications total",
                fr=f"{count} applications au total",
                es=f"{count} aplicaciones en total",
                it=f"{count} applicazioni in totale",
                nl=f"{count} applicaties totaal",
                pl=f"{count} aplikacji łącznie",
                pt=f"{count} aplicativos no total",
                ja=f"{count} アプリケーション (合計)",
                zh=f"{count} 个应用程序 (共)",
            )
        )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_entra_applications failed: %s", e)
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
async def list_entra_devices(connection_id: str = "") -> str:
    """
    List registered devices in Entra ID.
    Use this to see all devices registered in the tenant.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request("GET", "/devices", token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de="Keine Geräte gefunden",
                en="No devices found",
                fr="Aucun appareil trouvé",
                es="No se encontraron dispositivos",
                it="Nessun dispositivo trovato",
                nl="Geen apparaten gevonden",
                pl="Nie znaleziono urządzeń",
                pt="Nenhum dispositivo encontrado",
                ja="デバイスが見つかりません",
                zh="未找到设备",
            )

        lines = [
            "💻 "
            + _t(
                de="Geräte",
                en="Devices",
                fr="Appareils",
                es="Dispositivos",
                it="Dispositivi",
                nl="Apparaten",
                pl="Urządzenia",
                pt="Dispositivos",
                ja="デバイス",
                zh="设备",
            )
        ]
        for d in devices[:15]:
            os = d.get("operatingSystem", "-")
            compliant = "✅" if d.get("isCompliant") else "❌"
            lines.append(f"  {compliant} {d.get('displayName', '-')} ({os})")

        count = len(devices)
        lines.append(
            "\n✓ "
            + _t(
                de=f"{count} Geräte gesamt",
                en=f"{count} devices total",
                fr=f"{count} appareils au total",
                es=f"{count} dispositivos en total",
                it=f"{count} dispositivi in totale",
                nl=f"{count} apparaten totaal",
                pl=f"{count} urządzeń łącznie",
                pt=f"{count} dispositivos no total",
                ja=f"{count} デバイス (合計)",
                zh=f"{count} 个设备 (共)",
            )
        )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_entra_devices failed: %s", e)
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
async def create_entra_user(
    display_name: str,
    user_principal_name: str,
    password: str,
    connection_id: str = "",
) -> str:
    """
    Create a new user in Microsoft Entra ID.
    Use this to create a new user account.
    """
    try:
        token = await _get_token(connection_id)
        user_data = {
            "accountEnabled": True,
            "displayName": display_name,
            "mailNickname": display_name.replace(" ", ""),
            "userPrincipalName": user_principal_name,
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": password,
            },
        }
        result = await _graph_request("POST", "/users", token, json=user_data)
        return _t(
            de=f"✅ Benutzer erstellt: {result.get('userPrincipalName')}",
            en=f"✅ User created: {result.get('userPrincipalName')}",
            fr=f"✅ Utilisateur créé: {result.get('userPrincipalName')}",
            es=f"✅ Usuario creado: {result.get('userPrincipalName')}",
            it=f"✅ Utente creato: {result.get('userPrincipalName')}",
            nl=f"✅ Gebruiker aangemaakt: {result.get('userPrincipalName')}",
            pl=f"✅ Utworzono użytkownika: {result.get('userPrincipalName')}",
            pt=f"✅ Usuário criado: {result.get('userPrincipalName')}",
            ja=f"✅ ユーザー作成: {result.get('userPrincipalName')}",
            zh=f"✅ 用户已创建: {result.get('userPrincipalName')}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("create_entra_user failed: %s", e)
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
async def disable_entra_user(user_principal_name: str, connection_id: str = "") -> str:
    """
    Disable a user account.
    Use this to disable a user's access.
    German: Benutzer deaktivieren or ausschalten.
    """
    try:
        token = await _get_token(connection_id)
        await _graph_request(
            "PATCH",
            _graph_user_path(user_principal_name),
            token,
            json={"accountEnabled": False},
        )
        return _t(
            de=f"✅ Benutzer deaktiviert: {user_principal_name}",
            en=f"✅ User disabled: {user_principal_name}",
            fr=f"✅ Utilisateur désactivé: {user_principal_name}",
            es=f"✅ Usuario desactivado: {user_principal_name}",
            it=f"✅ Utente disabilitato: {user_principal_name}",
            nl=f"✅ Gebruiker uitgeschakeld: {user_principal_name}",
            pl=f"✅ Użytkownik wyłączony: {user_principal_name}",
            pt=f"✅ Usuário desativado: {user_principal_name}",
            ja=f"✅ ユーザー無効化: {user_principal_name}",
            zh=f"✅ 用户已禁用: {user_principal_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("disable_entra_user failed: %s", e)
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
async def reset_entra_user_password(
    user_principal_name: str,
    new_password: str,
    connection_id: str = "",
) -> str:
    """
    Reset a user's password.
    Use this to reset a user's password.
    German: Passwort zurücksetzen/zuruecksetzen or reset.
    """
    try:
        token = await _get_token(connection_id)
        await _graph_request(
            "PATCH",
            _graph_user_path(user_principal_name),
            token,
            json={
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": False,
                    "password": new_password,
                }
            },
        )
        return _t(
            de=f"✅ Passwort zurückgesetzt für: {user_principal_name}",
            en=f"✅ Password reset for: {user_principal_name}",
            fr=f"✅ Mot de passe réinitialisé pour: {user_principal_name}",
            es=f"✅ Contraseña reiniciada para: {user_principal_name}",
            it=f"✅ Password ripristinata per: {user_principal_name}",
            nl=f"✅ Wachtwoord gereset voor: {user_principal_name}",
            pl=f"✅ Hasło zresetowane dla: {user_principal_name}",
            pt=f"✅ Senha redefinida para: {user_principal_name}",
            ja=f"✅ パスワードリセット: {user_principal_name}",
            zh=f"✅ 密码已重置: {user_principal_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("reset_entra_user_password failed: %s", e)
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
async def create_entra_group(
    display_name: str,
    description: str = "",
    security_enabled: bool = True,
    connection_id: str = "",
) -> str:
    """
    Create a new security group.
    Use this to create a new group.
    """
    try:
        token = await _get_token(connection_id)
        group_data = {
            "displayName": display_name,
            "description": description,
            "mailEnabled": False,
            "securityEnabled": security_enabled,
        }
        result = await _graph_request("POST", "/groups", token, json=group_data)
        return _t(
            de=f"✅ Gruppe erstellt: {result.get('displayName')}",
            en=f"✅ Group created: {result.get('displayName')}",
            fr=f"✅ Groupe créé: {result.get('displayName')}",
            es=f"✅ Grupo creado: {result.get('displayName')}",
            it=f"✅ Gruppo creato: {result.get('displayName')}",
            nl=f"✅ Groep aangemaakt: {result.get('displayName')}",
            pl=f"✅ Utworzono grupę: {result.get('displayName')}",
            pt=f"✅ Grupo criado: {result.get('displayName')}",
            ja=f"✅ グループ作成: {result.get('displayName')}",
            zh=f"✅ 组已创建: {result.get('displayName')}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("create_entra_group failed: %s", e)
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
async def add_user_to_group(
    user_principal_name: str,
    group_name: str,
    connection_id: str = "",
) -> str:
    """
    Add a user to a group.
    Use this to add a user to a security group.
    """
    try:
        token = await _get_token(connection_id)

        group_filter = _escape_odata_string(group_name)
        search = f"/groups?$filter=displayName eq '{group_filter}'"
        data = await _graph_request("GET", search, token)
        groups = data.get("value", [])
        if not groups:
            return _t(
                de=f"Gruppe nicht gefunden: {group_name}",
                en=f"Group not found: {group_name}",
                fr=f"Groupe non trouvé: {group_name}",
                es=f"Grupo no encontrado: {group_name}",
                it=f"Gruppo non trovato: {group_name}",
                nl=f"Groep niet gevonden: {group_name}",
                pl=f"Nie znaleziono grupy: {group_name}",
                pt=f"Grupo não encontrado: {group_name}",
                ja=f"グループが見つかりません: {group_name}",
                zh=f"未找到组: {group_name}",
            )

        group_id = groups[0]["id"]

        user_id = await _get_user_object_id(user_principal_name, token)
        await _graph_request(
            "POST",
            f"/groups/{group_id}/members/$ref",
            token,
            json={
                "@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"
            },
        )
        return _t(
            de=f"✅ Benutzer zur Gruppe hinzugefügt: {user_principal_name} → {group_name}",
            en=f"✅ User added to group: {user_principal_name} → {group_name}",
            fr=f"✅ Utilisateur ajouté au groupe: {user_principal_name} → {group_name}",
            es=f"✅ Usuario añadido al grupo: {user_principal_name} → {group_name}",
            it=f"✅ Utente aggiunto al gruppo: {user_principal_name} → {group_name}",
            nl=f"✅ Gebruiker toegevoegd aan groep: {user_principal_name} → {group_name}",
            pl=f"✅ Użytkownik dodany do grupy: {user_principal_name} → {group_name}",
            pt=f"✅ Usuário adicionado ao grupo: {user_principal_name} → {group_name}",
            ja=f"✅ グループに追加: {user_principal_name} → {group_name}",
            zh=f"✅ 用户已添加到组: {user_principal_name} → {group_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("add_user_to_group failed: %s", e)
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
