"""
WordPress Module — LangGraph @tool functions.
WordPress management via WP REST API v2 with Application Passwords.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.tls import get_connection_verify_arg
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.wordpress.tools")


async def _get_wp_client(connection_id: str = "") -> dict:
    """
    Build WordPress API config from ConnectionManager.
    WP REST API v2 uses HTTP Basic Auth with Application Passwords.
    """
    if connection_id:
        conn = await ConnectionManager.get_connection("wordpress", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"WordPress-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"WordPress connection with ID '{connection_id}' not found.",
                    fr=f"Connexion WordPress avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión de WordPress con ID '{connection_id}' no encontrada.",
                    it=f"Connessione WordPress con ID '{connection_id}' non trovata.",
                    nl=f"WordPress-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie WordPress z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão WordPress com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のWordPress接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的WordPress连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("wordpress")

    vault = get_vault()

    if conn:
        site_url = conn.config.get("url", "").rstrip("/")
        username = conn.config.get("username", "")

        app_password = None
        pw_path = conn.vault_keys.get("WORDPRESS_APP_PASSWORD")
        if pw_path:
            app_password = await vault.get_secret(pw_path)
    else:
        site_url = os.environ.get("WORDPRESS_URL", "").rstrip("/")
        username = os.environ.get("WORDPRESS_USERNAME", "")
        app_password = os.environ.get("WORDPRESS_APP_PASSWORD", "")

    if not site_url:
        raise ValueError(
            _t(
                de=(
                    "Keine WordPress-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen "
                    "(URL, Benutzername, Application Password)."
                ),
                en=(
                    "No WordPress connection configured. "
                    "Please create a connection in the dashboard under Settings → Module → Gear icon "
                    "(URL, username, Application Password)."
                ),
                fr=(
                    "Aucune connexion WordPress configurée. "
                    "Veuillez créer une connexion dans le tableau de bord sous Paramètres → Module → Icône d'engrenage "
                    "(URL, nom d'utilisateur, Application Password)."
                ),
                es=(
                    "No hay conexión de WordPress configurada. "
                    "Por favor cree una conexión en el panel bajo Configuración → Módulo → Icono de engranaje "
                    "(URL, nombre de usuario, Application Password)."
                ),
                it=(
                    "Nessuna connessione WordPress configurata. "
                    "Per favore crea una connessione nel cruscotto sotto Impostazioni → Modulo → Icona ingranaggio "
                    "(URL, nome utente, Application Password)."
                ),
                nl=(
                    "Geen WordPress-verbinding geconfigureerd. "
                    "Maak een verbinding aan in het dashboard onder Instellingen → Module → Tandwielpictogram "
                    "(URL, gebruikersnaam, Application Password)."
                ),
                pl=(
                    "Nie skonfigurowano połączenia WordPress. "
                    "Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → Ikona koła zębatego "
                    "(URL, nazwa użytkownika, Application Password)."
                ),
                pt=(
                    "Nenhuma conexão WordPress configurada. "
                    "Por favor crie uma conexão no painel em Configurações → Módulo → Ícone de engrenagem "
                    "(URL, nome de usuário, Application Password)."
                ),
                ja=(
                    "WordPress接続が設定されていません。 "
                    "ダッシュボードで設定→モジュール→歯車アイコンから接続を作成 "
                    "（URL、ユーザー名、Application Password）。"
                ),
                zh=(
                    "未配置WordPress连接。 "
                    "请在仪表板中的设置→模块→齿轮图标下创建连接 "
                    "（URL、用户名、Application Password）。"
                ),
            )
        )

    if not username or not app_password:
        raise ValueError(
            _t(
                de=(
                    "WordPress-Benutzername oder Application Password fehlen. "
                    "Ein Application Password erstellst du in WP unter Benutzer → Profil → Application Passwords."
                ),
                en=(
                    "WordPress username or Application Password missing. "
                    "Create an Application Password in WP under Users → Profile → Application Passwords."
                ),
                fr=(
                    "Nom d'utilisateur WordPress ou Application Password manquant. "
                    "Créez un Application Password dans WP sous Utilisateurs → Profil → Application Passwords."
                ),
                es=(
                    "Falta el nombre de usuario o Application Password de WordPress. "
                    "Crea un Application Password en WP bajo Usuarios → Perfil → Application Passwords."
                ),
                it=(
                    "Nome utente WordPress o Application Password mancante. "
                    "Crea un Application Password in WP sotto Utenti → Profilo → Application Passwords."
                ),
                nl=(
                    "WordPress-gebruikersnaam of Application Password ontbreekt. "
                    "Maak een Application Password aan in WP onder Gebruikers → Profiel → Application Passwords."
                ),
                pl=(
                    "Brak nazwy użytkownika WordPress lub Application Password. "
                    "Utwórz Application Password w WP pod Użytkownicy → Profil → Application Passwords."
                ),
                pt=(
                    "Nome de usuário ou Application Password do WordPress ausente. "
                    "Crie um Application Password no WP em Usuários → Perfil → Application Passwords."
                ),
                ja=(
                    "WordPressのユーザー名またはApplication Passwordが設定されていません。 "
                    "WPでユーザー→プロファイル→Application Passwordsに Application Password を作成してください。"
                ),
                zh=(
                    "缺少WordPress用户名或Application Password。 "
                    "在WP中创建Application Password：用户→个人资料→应用程序密码。"
                ),
            )
        )

    # Basic Auth Header
    credentials = base64.b64encode(f"{username}:{app_password}".encode()).decode()
    headers = {
        "Authorization": f"Basic {credentials}",
        "Content-Type": "application/json",
    }

    verify_ssl = await get_connection_verify_arg(conn, "wordpress", default_verify=True)

    return {
        "base_url": site_url,
        "api_base": f"{site_url}/wp-json/wp/v2",
        "headers": headers,
        "username": username,
        "verify_ssl": verify_ssl,
    }


async def _wp_api(
    method: str,
    path: str,
    connection_id: str = "",
    json_body: dict | None = None,
    params: dict | None = None,
) -> Any:
    """Execute a WP REST API call."""
    client_cfg = await _get_wp_client(connection_id)
    url = f"{client_cfg['api_base']}{path}"
    headers = client_cfg["headers"]
    verify = client_cfg["verify_ssl"]

    async with httpx.AsyncClient(timeout=30, verify=verify) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers, params=params)
        elif method == "POST":
            resp = await client.post(
                url, headers=headers, json=json_body, params=params
            )
        elif method == "PUT":
            resp = await client.put(url, headers=headers, json=json_body, params=params)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers, params=params)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code >= 400:
            raise RuntimeError(f"WP API Error {resp.status_code}: {resp.text[:500]}")

        if resp.status_code == 204:
            return {"status": "success"}

        return resp.json()


async def _wp_api_root(connection_id: str = "") -> dict:
    """Fetch API root info (without /wp/v2 path)."""
    client_cfg = await _get_wp_client(connection_id)
    url = f"{client_cfg['base_url']}/wp-json/"
    verify = client_cfg["verify_ssl"]
    async with httpx.AsyncClient(timeout=15, verify=verify) as client:
        resp = await client.get(url, headers=client_cfg["headers"])
        if resp.status_code >= 400:
            raise RuntimeError(f"WP API Error {resp.status_code}: {resp.text[:500]}")
        return resp.json()


def _truncate(text: str, max_lines: int = 50, max_chars: int = 4000) -> str:
    """Truncate long outputs."""
    lines = text.split("\n")
    if len(lines) > max_lines:
        text = "\n".join(lines[:max_lines]) + f"\n[…{len(lines) - max_lines} Zeilen]"
    if len(text) > max_chars:
        text = text[:max_chars] + "\n[…gekürzt]"
    return text


# ═══════════════════════════════════════════════════════
# Site-Info Tools
# ═══════════════════════════════════════════════════════


@tool
async def get_site_info(connection_id: str = "") -> dict:
    """
    Return basic information about the WordPress instance:
    name, description, URL, WP version, language.
    """
    try:
        data = await _wp_api_root(connection_id)
        return {
            "name": data.get("name", ""),
            "description": data.get("description", ""),
            "url": data.get("url", ""),
            "home": data.get("home", ""),
            "wp_version": data.get("version", ""),
            "api_version": data.get("namespaces", []),
            "timezone": data.get("timezone_string", ""),
            "language": data.get("language", ""),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def get_updates_info(connection_id: str = "") -> dict:
    """
    Check for available updates (WordPress core, plugins, themes).
    Requires admin privileges.
    """
    try:
        await _wp_api("GET", "/settings", connection_id)
        # WP REST API Settings does not include update info directly.
        # We check the plugin list for available updates.
        plugins = await _wp_api(
            "GET", "/plugins", connection_id, params={"per_page": 100}
        )
        plugins_with_updates = [
            {
                "name": p.get("name", ""),
                "slug": p.get("plugin", ""),
                "version": p.get("version", ""),
            }
            for p in plugins
            if p.get("update_available", False)
        ]
        return {
            "plugins_with_updates": plugins_with_updates,
            "plugin_update_count": len(plugins_with_updates),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════
# Plugin-Management Tools
# ═══════════════════════════════════════════════════════


@tool
async def list_plugins(status: str = "all", connection_id: str = "") -> list[dict]:
    """
    List all installed plugins.
    status: 'all', 'active', 'inactive'
    """
    try:
        plugins = await _wp_api(
            "GET", "/plugins", connection_id, params={"per_page": 100}
        )
        result = []
        for p in plugins:
            is_active = p.get("status") == "active"
            if status == "active" and not is_active:
                continue
            if status == "inactive" and is_active:
                continue
            result.append(
                {
                    "slug": p.get("plugin", ""),
                    "name": p.get("name", ""),
                    "version": p.get("version", ""),
                    "status": p.get("status", ""),
                    "description": (p.get("description", {}).get("raw", "") or "")[
                        :120
                    ],
                    "update_available": p.get("update_available", False),
                }
            )
        return result
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def search_plugins(query: str, connection_id: str = "") -> list[dict]:
    """
    Search the WordPress.org plugin directory for new plugins.
    Returns results with name, slug, rating, and download count.
    """
    try:
        await _get_wp_client(connection_id)
        # WordPress.org Plugin API (external, not WP REST API)
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://api.wordpress.org/plugins/info/1.2/",
                params={
                    "action": "query_plugins",
                    "search": query,
                    "per_page": 10,
                    "fields[short_description]": 1,
                    "fields[rating]": 1,
                    "fields[active_installs]": 1,
                    "fields[last_updated]": 1,
                },
            )
            if resp.status_code >= 400:
                return [{"error": f"WordPress.org API Error: {resp.status_code}"}]
            data = resp.json()
            plugins = data.get("plugins", [])
            return [
                {
                    "slug": p.get("slug", ""),
                    "name": p.get("name", ""),
                    "version": p.get("version", ""),
                    "short_description": (p.get("short_description", "") or "")[:150],
                    "active_installs": p.get("active_installs", 0),
                    "rating": p.get("rating", 0),
                    "last_updated": p.get("last_updated", ""),
                }
                for p in plugins[:10]
            ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def install_plugin(slug: str, connection_id: str = "") -> dict:
    """
    Install a plugin from the WordPress.org directory by slug.
    Example: slug='akismet' or slug='yoast-seo'
    """
    try:
        result = await _wp_api(
            "POST", "/plugins", connection_id, json_body={"slug": slug}
        )
        return {
            "slug": result.get("plugin", slug),
            "name": result.get("name", ""),
            "status": result.get("status", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', slug)}' erfolgreich installiert.",
                en=f"Plugin '{result.get('name', slug)}' installed successfully.",
                fr=f"Plugin '{result.get('name', slug)}' installé avec succès.",
                es=f"Plugin '{result.get('name', slug)}' instalado con éxito.",
                it=f"Plugin '{result.get('name', slug)}' installato con successo.",
                nl=f"Plugin '{result.get('name', slug)}' succesvol geïnstalleerd.",
                pl=f"Plugin '{result.get('name', slug)}' pomyślnie zainstalowany.",
                pt=f"Plugin '{result.get('name', slug)}' instalado com sucesso.",
                ja=f"プラグイン '{result.get('name', slug)}' をインストールしました。",
                zh=f"插件 '{result.get('name', slug)}' 安装成功。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"slug": slug, "error": str(e)}


@tool
async def activate_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Activate an installed plugin.
    plugin_slug format: 'akismet/akismet' (folder/file without .php)
    """
    try:
        result = await _wp_api(
            "POST",
            f"/plugins/{plugin_slug}",
            connection_id,
            json_body={"status": "active"},
        )
        return {
            "slug": result.get("plugin", plugin_slug),
            "name": result.get("name", ""),
            "status": result.get("status", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', plugin_slug)}' aktiviert.",
                en=f"Plugin '{result.get('name', plugin_slug)}' activated.",
                fr=f"Plugin '{result.get('name', plugin_slug)}' activé.",
                es=f"Plugin '{result.get('name', plugin_slug)}' activado.",
                it=f"Plugin '{result.get('name', plugin_slug)}' attivato.",
                nl=f"Plugin '{result.get('name', plugin_slug)}' geactiveerd.",
                pl=f"Plugin '{result.get('name', plugin_slug)}' włączony.",
                pt=f"Plugin '{result.get('name', plugin_slug)}' ativado.",
                ja=f"プラグイン '{result.get('name', plugin_slug)}' を有効化しました。",
                zh=f"插件 '{result.get('name', plugin_slug)}' 已激活。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"slug": plugin_slug, "error": str(e)}


@tool
async def deactivate_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Deactivate an active plugin.
    plugin_slug format: 'akismet/akismet'
    """
    try:
        result = await _wp_api(
            "POST",
            f"/plugins/{plugin_slug}",
            connection_id,
            json_body={"status": "inactive"},
        )
        return {
            "slug": result.get("plugin", plugin_slug),
            "name": result.get("name", ""),
            "status": result.get("status", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', plugin_slug)}' deaktiviert.",
                en=f"Plugin '{result.get('name', plugin_slug)}' deactivated.",
                fr=f"Plugin '{result.get('name', plugin_slug)}' désactivé.",
                es=f"Plugin '{result.get('name', plugin_slug)}' desactivado.",
                it=f"Plugin '{result.get('name', plugin_slug)}' disattivato.",
                nl=f"Plugin '{result.get('name', plugin_slug)}' gedeactiveerd.",
                pl=f"Plugin '{result.get('name', plugin_slug)}' wyłączony.",
                pt=f"Plugin '{result.get('name', plugin_slug)}' desativado.",
                ja=f"プラグイン '{result.get('name', plugin_slug)}' を無効化しました。",
                zh=f"插件 '{result.get('name', plugin_slug)}' 已停用。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"slug": plugin_slug, "error": str(e)}


@tool
async def update_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Update a plugin to the latest version.
    plugin_slug format: 'akismet/akismet'
    """
    try:
        result = await _wp_api(
            "PUT", f"/plugins/{plugin_slug}", connection_id, json_body={"update": True}
        )
        return {
            "slug": result.get("plugin", plugin_slug),
            "name": result.get("name", ""),
            "version": result.get("version", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', plugin_slug)}' aktualisiert.",
                en=f"Plugin '{result.get('name', plugin_slug)}' updated.",
                fr=f"Plugin '{result.get('name', plugin_slug)}' mis à jour.",
                es=f"Plugin '{result.get('name', plugin_slug)}' actualizado.",
                it=f"Plugin '{result.get('name', plugin_slug)}' aggiornato.",
                nl=f"Plugin '{result.get('name', plugin_slug)}' bijgewerkt.",
                pl=f"Plugin '{result.get('name', plugin_slug)}' zaktualizowany.",
                pt=f"Plugin '{result.get('name', plugin_slug)}' atualizado.",
                ja=f"プラグイン '{result.get('name', plugin_slug)}' を更新しました。",
                zh=f"插件 '{result.get('name', plugin_slug)}' 已更新。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"slug": plugin_slug, "error": str(e)}


@tool
async def delete_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Delete a deactivated plugin.
    plugin_slug format: 'akismet/akismet'
    DESTRUCTIVE — requires confirmation. Plugin must be deactivated first.
    """
    try:
        await _wp_api("DELETE", f"/plugins/{plugin_slug}", connection_id)
        return {
            "slug": plugin_slug,
            "status": "deleted",
            "detail": _t(
                de=f"Plugin '{plugin_slug}' wurde gelöscht.",
                en=f"Plugin '{plugin_slug}' has been deleted.",
                fr=f"Plugin '{plugin_slug}' a été supprimé.",
                es=f"Plugin '{plugin_slug}' ha sido eliminado.",
                it=f"Plugin '{plugin_slug}' è stato eliminato.",
                nl=f"Plugin '{plugin_slug}' is verwijderd.",
                pl=f"Plugin '{plugin_slug}' został usunięty.",
                pt=f"Plugin '{plugin_slug}' foi excluído.",
                ja=f"プラグイン '{plugin_slug}' を削除しました。",
                zh=f"插件 '{plugin_slug}' 已删除。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"slug": plugin_slug, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Page Management Tools
# ═══════════════════════════════════════════════════════


@tool
async def list_pages(
    status: str = "publish",
    per_page: int = 20,
    search: str = "",
    connection_id: str = "",
) -> list[dict]:
    """
    List WordPress pages.
    status: 'publish', 'draft', 'pending', 'trash', 'any'
    search: search term for title/content
    """
    try:
        params: dict[str, Any] = {
            "per_page": per_page,
            "orderby": "modified",
            "order": "desc",
        }
        if status != "any":
            params["status"] = status
        if search:
            params["search"] = search
        pages = await _wp_api("GET", "/pages", connection_id, params=params)
        return [
            {
                "id": p["id"],
                "title": p.get("title", {}).get("rendered", ""),
                "slug": p.get("slug", ""),
                "status": p.get("status", ""),
                "date": p.get("date", ""),
                "modified": p.get("modified", ""),
                "author": p.get("author", 0),
                "parent": p.get("parent", 0),
                "link": p.get("link", ""),
                "excerpt": (p.get("excerpt", {}).get("rendered", "") or "")[:150],
            }
            for p in pages
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def get_page(page_id: int, connection_id: str = "") -> dict:
    """
    Return a single page with full content.
    page_id: The WordPress page ID.
    """
    try:
        p = await _wp_api("GET", f"/pages/{page_id}", connection_id)
        return {
            "id": p["id"],
            "title": p.get("title", {}).get("rendered", ""),
            "slug": p.get("slug", ""),
            "status": p.get("status", ""),
            "content": p.get("content", {}).get("rendered", ""),
            "excerpt": p.get("excerpt", {}).get("rendered", ""),
            "date": p.get("date", ""),
            "modified": p.get("modified", ""),
            "author": p.get("author", 0),
            "parent": p.get("parent", 0),
            "menu_order": p.get("menu_order", 0),
            "link": p.get("link", ""),
            "template": p.get("template", ""),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def create_page(
    title: str,
    content: str,
    status: str = "draft",
    slug: str = "",
    parent: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Create a new WordPress page.
    title: page title
    content: page content (HTML allowed)
    status: 'draft', 'publish', 'pending', 'private'
    slug: URL slug (optional, auto-generated if empty)
    parent: parent page ID (0 = top-level page)
    """
    try:
        body: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if slug:
            body["slug"] = slug
        if parent:
            body["parent"] = parent

        result = await _wp_api("POST", "/pages", connection_id, json_body=body)
        return {
            "id": result["id"],
            "title": result.get("title", {}).get("rendered", ""),
            "slug": result.get("slug", ""),
            "status": result.get("status", ""),
            "link": result.get("link", ""),
            "detail": _t(
                de=f"Seite '{result.get('title', {}).get('rendered', '')}' erstellt (ID: {result['id']}).",
                en=f"Page '{result.get('title', {}).get('rendered', '')}' created (ID: {result['id']}).",
                fr=f"Page '{result.get('title', {}).get('rendered', '')}' créée (ID: {result['id']}).",
                es=f"Página '{result.get('title', {}).get('rendered', '')}' creada (ID: {result['id']}).",
                it=f"Pagina '{result.get('title', {}).get('rendered', '')}' creata (ID: {result['id']}).",
                nl=f"Pagina '{result.get('title', {}).get('rendered', '')}' aangemaakt (ID: {result['id']}).",
                pl=f"Strona '{result.get('title', {}).get('rendered', '')}' utworzona (ID: {result['id']}).",
                pt=f"Página '{result.get('title', {}).get('rendered', '')}' criada (ID: {result['id']}).",
                ja=f"ページ '{result.get('title', {}).get('rendered', '')}' を作成しました（ID: {result['id']}）。",
                zh=f"页面 '{result.get('title', {}).get('rendered', '')}' 已创建（ID: {result['id']}）。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def update_page(
    page_id: int,
    title: str = "",
    content: str = "",
    status: str = "",
    slug: str = "",
    connection_id: str = "",
) -> dict:
    """
    Update an existing WordPress page.
    Only specified fields are changed.
    page_id: page ID
    title: new title (optional)
    content: new content (optional)
    status: new status (optional): 'draft', 'publish', 'pending', 'trash'
    slug: new slug (optional)
    """
    try:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if content:
            body["content"] = content
        if status:
            body["status"] = status
        if slug:
            body["slug"] = slug

        if not body:
            return {
                "error": _t(
                    de="Keine Änderungen angegeben.",
                    en="No changes specified.",
                    fr="Aucun changement spécifié.",
                    es="No se especificaron cambios.",
                    it="Nessuna modifica specificata.",
                    nl="Geen wijzigingen opgegeven.",
                    pl="Nie określono żadnych zmian.",
                    pt="Nenhuma alteração especificada.",
                    ja="変更が指定されていません。",
                    zh="未指定任何更改。",
                )
            }

        result = await _wp_api(
            "PUT", f"/pages/{page_id}", connection_id, json_body=body
        )
        return {
            "id": result["id"],
            "title": result.get("title", {}).get("rendered", ""),
            "slug": result.get("slug", ""),
            "status": result.get("status", ""),
            "modified": result.get("modified", ""),
            "detail": _t(
                de=f"Seite ID {page_id} aktualisiert.",
                en=f"Page ID {page_id} updated.",
                fr=f"Page ID {page_id} mise à jour.",
                es=f"Página ID {page_id} actualizada.",
                it=f"Pagina ID {page_id} aggiornata.",
                nl=f"Pagina ID {page_id} bijgewerkt.",
                pl=f"Strona ID {page_id} zaktualizowana.",
                pt=f"Página ID {page_id} atualizada.",
                ja=f"ページ ID {page_id} を更新しました。",
                zh=f"页面 ID {page_id} 已更新。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"page_id": page_id, "error": str(e)}


@tool
async def delete_page(
    page_id: int, force: bool = False, connection_id: str = ""
) -> dict:
    """
    Delete a WordPress page.
    force=false moves to trash, force=true permanently deletes.
    DESTRUCTIVE when force=true — requires confirmation.
    """
    try:
        params = {"force": 1} if force else {}
        await _wp_api(
            "DELETE", f"/pages/{page_id}", connection_id, params=params
        )
        return {
            "page_id": page_id,
            "status": "deleted" if force else "trashed",
            "detail": _t(
                de=f"Seite ID {page_id} {'endgültig gelöscht' if force else 'in den Papierkorb verschoben'}.",
                en=f"Page ID {page_id} {'permanently deleted' if force else 'moved to trash'}.",
                fr=f"Page ID {page_id} {'supprimée définitivement' if force else 'déplacée dans la corbeille'}.",
                es=f"Página ID {page_id} {'eliminada permanentemente' if force else 'movida a la papelera'}.",
                it=f"Pagina ID {page_id} {'eliminata definitivamente' if force else 'spostata nel cestino'}.",
                nl=f"Pagina ID {page_id} {'permanent verwijderd' if force else 'naar prullenbak verplaatst'}.",
                pl=f"Strona ID {page_id} {'trwale usunięta' if force else 'przeniesiona do kosza'}.",
                pt=f"Página ID {page_id} {'excluída permanentemente' if force else 'movida para a lixeira'}.",
                ja=f"ページ ID {page_id} を{'完全に削除' if force else 'ゴミ箱に移動'}しました。",
                zh=f"页面 ID {page_id} 已{'永久删除' if force else '移至回收站'}。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"page_id": page_id, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Posts Management Tools
# ═══════════════════════════════════════════════════════


@tool
async def list_posts(
    status: str = "publish",
    per_page: int = 20,
    search: str = "",
    connection_id: str = "",
) -> list[dict]:
    """
    List WordPress posts.
    status: 'publish', 'draft', 'pending', 'trash', 'any'
    search: search term
    """
    try:
        params: dict[str, Any] = {
            "per_page": per_page,
            "orderby": "modified",
            "order": "desc",
        }
        if status != "any":
            params["status"] = status
        if search:
            params["search"] = search
        posts = await _wp_api("GET", "/posts", connection_id, params=params)
        return [
            {
                "id": p["id"],
                "title": p.get("title", {}).get("rendered", ""),
                "slug": p.get("slug", ""),
                "status": p.get("status", ""),
                "date": p.get("date", ""),
                "modified": p.get("modified", ""),
                "author": p.get("author", 0),
                "categories": p.get("categories", []),
                "tags": p.get("tags", []),
                "link": p.get("link", ""),
                "excerpt": (p.get("excerpt", {}).get("rendered", "") or "")[:150],
            }
            for p in posts
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def get_post(post_id: int, connection_id: str = "") -> dict:
    """
    Return a single post with full content.
    """
    try:
        p = await _wp_api("GET", f"/posts/{post_id}", connection_id)
        return {
            "id": p["id"],
            "title": p.get("title", {}).get("rendered", ""),
            "slug": p.get("slug", ""),
            "status": p.get("status", ""),
            "content": p.get("content", {}).get("rendered", ""),
            "excerpt": p.get("excerpt", {}).get("rendered", ""),
            "date": p.get("date", ""),
            "modified": p.get("modified", ""),
            "author": p.get("author", 0),
            "categories": p.get("categories", []),
            "tags": p.get("tags", []),
            "link": p.get("link", ""),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def create_post(
    title: str,
    content: str,
    status: str = "draft",
    slug: str = "",
    categories: str = "",
    tags: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new WordPress post.
    title: title
    content: content (HTML allowed)
    status: 'draft', 'publish', 'pending', 'private'
    slug: URL slug (optional)
    categories: comma-separated category IDs (e.g. '1,3,5')
    tags: comma-separated tag IDs (e.g. '2,4')
    """
    try:
        body: dict[str, Any] = {
            "title": title,
            "content": content,
            "status": status,
        }
        if slug:
            body["slug"] = slug
        if categories:
            body["categories"] = [
                int(c.strip()) for c in categories.split(",") if c.strip()
            ]
        if tags:
            body["tags"] = [int(t.strip()) for t in tags.split(",") if t.strip()]

        result = await _wp_api("POST", "/posts", connection_id, json_body=body)
        return {
            "id": result["id"],
            "title": result.get("title", {}).get("rendered", ""),
            "slug": result.get("slug", ""),
            "status": result.get("status", ""),
            "link": result.get("link", ""),
            "detail": _t(
                de=f"Beitrag '{result.get('title', {}).get('rendered', '')}' erstellt (ID: {result['id']}).",
                en=f"Post '{result.get('title', {}).get('rendered', '')}' created (ID: {result['id']}).",
                fr=f"Article '{result.get('title', {}).get('rendered', '')}' créé (ID: {result['id']}).",
                es=f"Artículo '{result.get('title', {}).get('rendered', '')}' creado (ID: {result['id']}).",
                it=f"Articolo '{result.get('title', {}).get('rendered', '')}' creato (ID: {result['id']}).",
                nl=f"Bericht '{result.get('title', {}).get('rendered', '')}' aangemaakt (ID: {result['id']}).",
                pl=f"Wpis '{result.get('title', {}).get('rendered', '')}' utworzony (ID: {result['id']}).",
                pt=f"Post '{result.get('title', {}).get('rendered', '')}' criado (ID: {result['id']}).",
                ja=f"投稿 '{result.get('title', {}).get('rendered', '')}' を作成しました（ID: {result['id']}）。",
                zh=f"文章 '{result.get('title', {}).get('rendered', '')}' 已创建（ID: {result['id']}）。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def update_post(
    post_id: int,
    title: str = "",
    content: str = "",
    status: str = "",
    slug: str = "",
    connection_id: str = "",
) -> dict:
    """
    Update an existing WordPress post.
    Only specified fields are changed.
    """
    try:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if content:
            body["content"] = content
        if status:
            body["status"] = status
        if slug:
            body["slug"] = slug

        if not body:
            return {
                "error": _t(
                    de="Keine Änderungen angegeben.",
                    en="No changes specified.",
                    fr="Aucun changement spécifié.",
                    es="No se especificaron cambios.",
                    it="Nessuna modifica specificata.",
                    nl="Geen wijzigingen opgegeven.",
                    pl="Nie określono żadnych zmian.",
                    pt="Nenhuma alteração especificada.",
                    ja="変更が指定されていません。",
                    zh="未指定任何更改。",
                )
            }

        result = await _wp_api(
            "PUT", f"/posts/{post_id}", connection_id, json_body=body
        )
        return {
            "id": result["id"],
            "title": result.get("title", {}).get("rendered", ""),
            "status": result.get("status", ""),
            "modified": result.get("modified", ""),
            "detail": _t(
                de=f"Beitrag ID {post_id} aktualisiert.",
                en=f"Post ID {post_id} updated.",
                fr=f"Article ID {post_id} mis à jour.",
                es=f"Artículo ID {post_id} actualizado.",
                it=f"Articolo ID {post_id} aggiornato.",
                nl=f"Bericht ID {post_id} bijgewerkt.",
                pl=f"Wpis ID {post_id} zaktualizowany.",
                pt=f"Post ID {post_id} atualizado.",
                ja=f"投稿 ID {post_id} を更新しました。",
                zh=f"文章 ID {post_id} 已更新。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"post_id": post_id, "error": str(e)}


@tool
async def delete_post(
    post_id: int, force: bool = False, connection_id: str = ""
) -> dict:
    """
    Delete a WordPress post.
    force=false → trash, force=true → permanent delete.
    """
    try:
        params = {"force": 1} if force else {}
        await _wp_api(
            "DELETE", f"/posts/{post_id}", connection_id, params=params
        )
        return {
            "post_id": post_id,
            "status": "deleted" if force else "trashed",
            "detail": _t(
                de=f"Beitrag ID {post_id} {'endgültig gelöscht' if force else 'in den Papierkorb verschoben'}.",
                en=f"Post ID {post_id} {'permanently deleted' if force else 'moved to trash'}.",
                fr=f"Article ID {post_id} {'supprimé définitivement' if force else 'déplacé dans la corbeille'}.",
                es=f"Artículo ID {post_id} {'eliminado permanentemente' if force else 'movido a la papelera'}.",
                it=f"Articolo ID {post_id} {'eliminato definitivamente' if force else 'spostato nel cestino'}.",
                nl=f"Bericht ID {post_id} {'permanent verwijderd' if force else 'naar prullenbak verplaatst'}.",
                pl=f"Wpis ID {post_id} {'trwale usunięty' if force else 'przeniesiony do kosza'}.",
                pt=f"Post ID {post_id} {'excluído permanentemente' if force else 'movido para a lixeira'}.",
                ja=f"投稿 ID {post_id} を{'完全に削除' if force else 'ゴミ箱に移動'}しました。",
                zh=f"文章 ID {post_id} 已{'永久删除' if force else '移至回收站'}。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"post_id": post_id, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Categories & Tags
# ═══════════════════════════════════════════════════════


@tool
async def list_categories(connection_id: str = "") -> list[dict]:
    """List all post categories."""
    try:
        cats = await _wp_api(
            "GET", "/categories", connection_id, params={"per_page": 100}
        )
        return [
            {
                "id": c["id"],
                "name": c.get("name", ""),
                "slug": c.get("slug", ""),
                "count": c.get("count", 0),
            }
            for c in cats
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def create_category(
    name: str, slug: str = "", parent: int = 0, connection_id: str = ""
) -> dict:
    """Create a new category."""
    try:
        body: dict[str, Any] = {"name": name}
        if slug:
            body["slug"] = slug
        if parent:
            body["parent"] = parent
        result = await _wp_api("POST", "/categories", connection_id, json_body=body)
        return {
            "id": result["id"],
            "name": result.get("name", ""),
            "slug": result.get("slug", ""),
            "detail": _t(
                de=f"Kategorie '{result.get('name', '')}' erstellt (ID: {result['id']}).",
                en=f"Category '{result.get('name', '')}' created (ID: {result['id']}).",
                fr=f"Catégorie '{result.get('name', '')}' créée (ID: {result['id']}).",
                es=f"Categoría '{result.get('name', '')}' creada (ID: {result['id']}).",
                it=f"Categoria '{result.get('name', '')}' creata (ID: {result['id']}).",
                nl=f"Categorie '{result.get('name', '')}' aangemaakt (ID: {result['id']}).",
                pl=f"Kategoria '{result.get('name', '')}' utworzona (ID: {result['id']}).",
                pt=f"Categoria '{result.get('name', '')}' criada (ID: {result['id']}).",
                ja=f"カテゴリー '{result.get('name', '')}' を作成しました（ID: {result['id']}）。",
                zh=f"类别 '{result.get('name', '')}' 已创建（ID: {result['id']}）。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def list_tags(connection_id: str = "") -> list[dict]:
    """List all tags."""
    try:
        tags = await _wp_api("GET", "/tags", connection_id, params={"per_page": 100})
        return [
            {
                "id": t["id"],
                "name": t.get("name", ""),
                "slug": t.get("slug", ""),
                "count": t.get("count", 0),
            }
            for t in tags
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def create_tag(name: str, slug: str = "", connection_id: str = "") -> dict:
    """Create a new tag."""
    try:
        body: dict[str, Any] = {"name": name}
        if slug:
            body["slug"] = slug
        result = await _wp_api("POST", "/tags", connection_id, json_body=body)
        return {
            "id": result["id"],
            "name": result.get("name", ""),
            "detail": _t(
                de=f"Tag '{result.get('name', '')}' erstellt (ID: {result['id']}).",
                en=f"Tag '{result.get('name', '')}' created (ID: {result['id']}).",
                fr=f"Tag '{result.get('name', '')}' créé (ID: {result['id']}).",
                es=f"Etiqueta '{result.get('name', '')}' creada (ID: {result['id']}).",
                it=f"Tag '{result.get('name', '')}' creato (ID: {result['id']}).",
                nl=f"Tag '{result.get('name', '')}' aangemaakt (ID: {result['id']}).",
                pl=f"Tag '{result.get('name', '')}' utworzony (ID: {result['id']}).",
                pt=f"Tag '{result.get('name', '')}' criado (ID: {result['id']}).",
                ja=f"タグ '{result.get('name', '')}' を作成しました（ID: {result['id']}）。",
                zh=f"标签 '{result.get('name', '')}' 已创建（ID: {result['id']}）。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════════════════


@tool
async def list_users(per_page: int = 20, connection_id: str = "") -> list[dict]:
    """List WordPress users."""
    try:
        users = await _wp_api(
            "GET", "/users", connection_id, params={"per_page": per_page}
        )
        return [
            {
                "id": u["id"],
                "name": u.get("name", ""),
                "username": u.get("slug", ""),
                "email": u.get("email", ""),
                "roles": u.get("roles", []),
                "registered": u.get("registered_date", ""),
            }
            for u in users
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]


@tool
async def get_current_user(connection_id: str = "") -> dict:
    """
    Return information about the currently authenticated user.
    Useful for checking permissions.
    """
    try:
        client_cfg = await _get_wp_client(connection_id)
        url = f"{client_cfg['api_base']}/users/me"
        async with httpx.AsyncClient(
            timeout=15, verify=client_cfg["verify_ssl"]
        ) as client:
            resp = await client.get(url, headers=client_cfg["headers"])
            if resp.status_code >= 400:
                return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
            u = resp.json()
            return {
                "id": u["id"],
                "name": u.get("name", ""),
                "username": u.get("slug", ""),
                "email": u.get("email", ""),
                "roles": u.get("roles", []),
                "capabilities": list(u.get("capabilities", {}).keys())[:30],
                "description": u.get("description", ""),
            }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════
# Settings
# ═══════════════════════════════════════════════════════


@tool
async def get_site_settings(connection_id: str = "") -> dict:
    """
    Return WordPress settings (title, subtitle, language, timezone, etc.).
    Requires admin privileges.
    """
    try:
        settings = await _wp_api("GET", "/settings", connection_id)
        return {
            "title": settings.get("title", ""),
            "description": settings.get("description", ""),
            "url": settings.get("url", ""),
            "email": settings.get("email", ""),
            "timezone": settings.get("timezone_string", ""),
            "language": settings.get("language", ""),
            "date_format": settings.get("date_format", ""),
            "time_format": settings.get("time_format", ""),
            "posts_per_page": settings.get("posts_per_page", 0),
            "default_category": settings.get("default_category", 0),
            "default_post_format": settings.get("default_post_format", ""),
            "permalink_structure": settings.get("permalink_structure", ""),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


@tool
async def update_site_settings(
    title: str = "",
    description: str = "",
    posts_per_page: int = 0,
    connection_id: str = "",
) -> dict:
    """
    Update WordPress settings.
    Only specified fields are changed.
    title: new site title
    description: new subtitle
    posts_per_page: posts per page
    """
    try:
        body: dict[str, Any] = {}
        if title:
            body["title"] = title
        if description:
            body["description"] = description
        if posts_per_page:
            body["posts_per_page"] = posts_per_page

        if not body:
            return {
                "error": _t(
                    de="Keine Änderungen angegeben.",
                    en="No changes specified.",
                    fr="Aucun changement spécifié.",
                    es="No se especificaron cambios.",
                    it="Nessuna modifica specificata.",
                    nl="Geen wijzigingen opgegeven.",
                    pl="Nie określono żadnych zmian.",
                    pt="Nenhuma alteração especificada.",
                    ja="変更が指定されていません。",
                    zh="未指定任何更改。",
                )
            }

        result = await _wp_api("PUT", "/settings", connection_id, json_body=body)
        return {
            "title": result.get("title", ""),
            "description": result.get("description", ""),
            "detail": _t(
                de="Einstellungen aktualisiert.",
                en="Settings updated.",
                fr="Paramètres mis à jour.",
                es="Configuración actualizada.",
                it="Impostazioni aggiornate.",
                nl="Instellingen bijgewerkt.",
                pl="Ustawienia zaktualizowane.",
                pt="Configurações atualizadas.",
                ja="設定を更新しました。",
                zh="设置已更新。",
            ),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════
# Media-Management
# ═══════════════════════════════════════════════════════


@tool
async def list_media(
    per_page: int = 20, media_type: str = "", connection_id: str = ""
) -> list[dict]:
    """
    List uploaded media files.
    media_type: 'image', 'video', 'audio', 'document' or empty for all.
    """
    try:
        params: dict[str, Any] = {
            "per_page": per_page,
            "orderby": "date",
            "order": "desc",
        }
        if media_type:
            params["media_type"] = media_type
        media = await _wp_api("GET", "/media", connection_id, params=params)
        return [
            {
                "id": m["id"],
                "title": m.get("title", {}).get("rendered", ""),
                "media_type": m.get("media_type", ""),
                "mime_type": m.get("mime_type", ""),
                "source_url": m.get("source_url", ""),
                "date": m.get("date", ""),
                "alt_text": m.get("alt_text", ""),
                "filesize": m.get("media_details", {}).get("filesize", 0),
            }
            for m in media
        ]
    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        return [{"error": str(e)}]
