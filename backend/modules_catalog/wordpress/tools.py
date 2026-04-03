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
            resp = await client.post(url, headers=headers, json=json_body, params=params)
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
    except Exception as e:
        return {"error": str(e)}


@tool
async def get_updates_info(connection_id: str = "") -> dict:
    """
    Check for available updates (WordPress core, plugins, themes).
    Requires admin privileges.
    """
    try:
        settings = await _wp_api("GET", "/settings", connection_id)
        # WP REST API Settings does not include update info directly.
        # We check the plugin list for available updates.
        plugins = await _wp_api("GET", "/plugins", connection_id, params={"per_page": 100})
        plugins_with_updates = [
            {"name": p.get("name", ""), "slug": p.get("plugin", ""), "version": p.get("version", "")}
            for p in plugins
            if p.get("update_available", False)
        ]
        return {
            "plugins_with_updates": plugins_with_updates,
            "plugin_update_count": len(plugins_with_updates),
        }
    except Exception as e:
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
        plugins = await _wp_api("GET", "/plugins", connection_id, params={"per_page": 100})
        result = []
        for p in plugins:
            is_active = p.get("status") == "active"
            if status == "active" and not is_active:
                continue
            if status == "inactive" and is_active:
                continue
            result.append({
                "slug": p.get("plugin", ""),
                "name": p.get("name", ""),
                "version": p.get("version", ""),
                "status": p.get("status", ""),
                "description": (p.get("description", {}).get("raw", "") or "")[:120],
                "update_available": p.get("update_available", False),
            })
        return result
    except Exception as e:
        return [{"error": str(e)}]


@tool
async def search_plugins(query: str, connection_id: str = "") -> list[dict]:
    """
    Search the WordPress.org plugin directory for new plugins.
    Returns results with name, slug, rating, and download count.
    """
    try:
        client_cfg = await _get_wp_client(connection_id)
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
    except Exception as e:
        return [{"error": str(e)}]


@tool
async def install_plugin(slug: str, connection_id: str = "") -> dict:
    """
    Install a plugin from the WordPress.org directory by slug.
    Example: slug='akismet' or slug='yoast-seo'
    """
    try:
        result = await _wp_api("POST", "/plugins", connection_id, json_body={"slug": slug})
        return {
            "slug": result.get("plugin", slug),
            "name": result.get("name", ""),
            "status": result.get("status", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', slug)}' erfolgreich installiert.",
                en=f"Plugin '{result.get('name', slug)}' installed successfully.",
            ),
        }
    except Exception as e:
        return {"slug": slug, "error": str(e)}


@tool
async def activate_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Activate an installed plugin.
    plugin_slug format: 'akismet/akismet' (folder/file without .php)
    """
    try:
        result = await _wp_api("POST", f"/plugins/{plugin_slug}", connection_id, json_body={"status": "active"})
        return {
            "slug": result.get("plugin", plugin_slug),
            "name": result.get("name", ""),
            "status": result.get("status", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', plugin_slug)}' aktiviert.",
                en=f"Plugin '{result.get('name', plugin_slug)}' activated.",
            ),
        }
    except Exception as e:
        return {"slug": plugin_slug, "error": str(e)}


@tool
async def deactivate_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Deactivate an active plugin.
    plugin_slug format: 'akismet/akismet'
    """
    try:
        result = await _wp_api("POST", f"/plugins/{plugin_slug}", connection_id, json_body={"status": "inactive"})
        return {
            "slug": result.get("plugin", plugin_slug),
            "name": result.get("name", ""),
            "status": result.get("status", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', plugin_slug)}' deaktiviert.",
                en=f"Plugin '{result.get('name', plugin_slug)}' deactivated.",
            ),
        }
    except Exception as e:
        return {"slug": plugin_slug, "error": str(e)}


@tool
async def update_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Update a plugin to the latest version.
    plugin_slug format: 'akismet/akismet'
    """
    try:
        result = await _wp_api("PUT", f"/plugins/{plugin_slug}", connection_id, json_body={"update": True})
        return {
            "slug": result.get("plugin", plugin_slug),
            "name": result.get("name", ""),
            "version": result.get("version", ""),
            "detail": _t(
                de=f"Plugin '{result.get('name', plugin_slug)}' aktualisiert.",
                en=f"Plugin '{result.get('name', plugin_slug)}' updated.",
            ),
        }
    except Exception as e:
        return {"slug": plugin_slug, "error": str(e)}


@tool
async def delete_plugin(plugin_slug: str, connection_id: str = "") -> dict:
    """
    Delete a deactivated plugin.
    plugin_slug format: 'akismet/akismet'
    DESTRUCTIVE — requires confirmation. Plugin must be deactivated first.
    """
    try:
        result = await _wp_api("DELETE", f"/plugins/{plugin_slug}", connection_id)
        return {
            "slug": plugin_slug,
            "status": "deleted",
            "detail": _t(
                de=f"Plugin '{plugin_slug}' wurde gelöscht.",
                en=f"Plugin '{plugin_slug}' has been deleted.",
            ),
        }
    except Exception as e:
        return {"slug": plugin_slug, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Page Management Tools
# ═══════════════════════════════════════════════════════

@tool
async def list_pages(status: str = "publish", per_page: int = 20, search: str = "", connection_id: str = "") -> list[dict]:
    """
    List WordPress pages.
    status: 'publish', 'draft', 'pending', 'trash', 'any'
    search: search term for title/content
    """
    try:
        params: dict[str, Any] = {"per_page": per_page, "orderby": "modified", "order": "desc"}
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
    except Exception as e:
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
    except Exception as e:
        return {"error": str(e)}


@tool
async def create_page(title: str, content: str, status: str = "draft", slug: str = "", parent: int = 0, connection_id: str = "") -> dict:
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
            ),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
async def update_page(page_id: int, title: str = "", content: str = "", status: str = "", slug: str = "", connection_id: str = "") -> dict:
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
            return {"error": _t(de="Keine Änderungen angegeben.", en="No changes specified.")}

        result = await _wp_api("PUT", f"/pages/{page_id}", connection_id, json_body=body)
        return {
            "id": result["id"],
            "title": result.get("title", {}).get("rendered", ""),
            "slug": result.get("slug", ""),
            "status": result.get("status", ""),
            "modified": result.get("modified", ""),
            "detail": _t(
                de=f"Seite ID {page_id} aktualisiert.",
                en=f"Page ID {page_id} updated.",
            ),
        }
    except Exception as e:
        return {"page_id": page_id, "error": str(e)}


@tool
async def delete_page(page_id: int, force: bool = False, connection_id: str = "") -> dict:
    """
    Delete a WordPress page.
    force=false moves to trash, force=true permanently deletes.
    DESTRUCTIVE when force=true — requires confirmation.
    """
    try:
        params = {"force": 1} if force else {}
        result = await _wp_api("DELETE", f"/pages/{page_id}", connection_id, params=params)
        return {
            "page_id": page_id,
            "status": "deleted" if force else "trashed",
            "detail": _t(
                de=f"Seite ID {page_id} {'endgültig gelöscht' if force else 'in den Papierkorb verschoben'}.",
                en=f"Page ID {page_id} {'permanently deleted' if force else 'moved to trash'}.",
            ),
        }
    except Exception as e:
        return {"page_id": page_id, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Posts Management Tools
# ═══════════════════════════════════════════════════════

@tool
async def list_posts(status: str = "publish", per_page: int = 20, search: str = "", connection_id: str = "") -> list[dict]:
    """
    List WordPress posts.
    status: 'publish', 'draft', 'pending', 'trash', 'any'
    search: search term
    """
    try:
        params: dict[str, Any] = {"per_page": per_page, "orderby": "modified", "order": "desc"}
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
    except Exception as e:
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
    except Exception as e:
        return {"error": str(e)}


@tool
async def create_post(title: str, content: str, status: str = "draft", slug: str = "", categories: str = "", tags: str = "", connection_id: str = "") -> dict:
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
            body["categories"] = [int(c.strip()) for c in categories.split(",") if c.strip()]
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
            ),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
async def update_post(post_id: int, title: str = "", content: str = "", status: str = "", slug: str = "", connection_id: str = "") -> dict:
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
            return {"error": _t(de="Keine Änderungen angegeben.", en="No changes specified.")}

        result = await _wp_api("PUT", f"/posts/{post_id}", connection_id, json_body=body)
        return {
            "id": result["id"],
            "title": result.get("title", {}).get("rendered", ""),
            "status": result.get("status", ""),
            "modified": result.get("modified", ""),
            "detail": _t(
                de=f"Beitrag ID {post_id} aktualisiert.",
                en=f"Post ID {post_id} updated.",
            ),
        }
    except Exception as e:
        return {"post_id": post_id, "error": str(e)}


@tool
async def delete_post(post_id: int, force: bool = False, connection_id: str = "") -> dict:
    """
    Delete a WordPress post.
    force=false → trash, force=true → permanent delete.
    """
    try:
        params = {"force": 1} if force else {}
        result = await _wp_api("DELETE", f"/posts/{post_id}", connection_id, params=params)
        return {
            "post_id": post_id,
            "status": "deleted" if force else "trashed",
            "detail": _t(
                de=f"Beitrag ID {post_id} {'endgültig gelöscht' if force else 'in den Papierkorb verschoben'}.",
                en=f"Post ID {post_id} {'permanently deleted' if force else 'moved to trash'}.",
            ),
        }
    except Exception as e:
        return {"post_id": post_id, "error": str(e)}


# ═══════════════════════════════════════════════════════
# Categories & Tags
# ═══════════════════════════════════════════════════════

@tool
async def list_categories(connection_id: str = "") -> list[dict]:
    """List all post categories."""
    try:
        cats = await _wp_api("GET", "/categories", connection_id, params={"per_page": 100})
        return [
            {"id": c["id"], "name": c.get("name", ""), "slug": c.get("slug", ""), "count": c.get("count", 0)}
            for c in cats
        ]
    except Exception as e:
        return [{"error": str(e)}]


@tool
async def create_category(name: str, slug: str = "", parent: int = 0, connection_id: str = "") -> dict:
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
            ),
        }
    except Exception as e:
        return {"error": str(e)}


@tool
async def list_tags(connection_id: str = "") -> list[dict]:
    """List all tags."""
    try:
        tags = await _wp_api("GET", "/tags", connection_id, params={"per_page": 100})
        return [
            {"id": t["id"], "name": t.get("name", ""), "slug": t.get("slug", ""), "count": t.get("count", 0)}
            for t in tags
        ]
    except Exception as e:
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
            ),
        }
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════
# User Management
# ═══════════════════════════════════════════════════════

@tool
async def list_users(per_page: int = 20, connection_id: str = "") -> list[dict]:
    """List WordPress users."""
    try:
        users = await _wp_api("GET", "/users", connection_id, params={"per_page": per_page})
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
    except Exception as e:
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
        async with httpx.AsyncClient(timeout=15, verify=client_cfg["verify_ssl"]) as client:
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
    except Exception as e:
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
    except Exception as e:
        return {"error": str(e)}


@tool
async def update_site_settings(title: str = "", description: str = "", posts_per_page: int = 0, connection_id: str = "") -> dict:
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
            return {"error": _t(de="Keine Änderungen angegeben.", en="No changes specified.")}

        result = await _wp_api("PUT", "/settings", connection_id, json_body=body)
        return {
            "title": result.get("title", ""),
            "description": result.get("description", ""),
            "detail": _t(
                de="Einstellungen aktualisiert.",
                en="Settings updated.",
            ),
        }
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════
# Media-Management
# ═══════════════════════════════════════════════════════

@tool
async def list_media(per_page: int = 20, media_type: str = "", connection_id: str = "") -> list[dict]:
    """
    List uploaded media files.
    media_type: 'image', 'video', 'audio', 'document' or empty for all.
    """
    try:
        params: dict[str, Any] = {"per_page": per_page, "orderby": "date", "order": "desc"}
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
    except Exception as e:
        return [{"error": str(e)}]
