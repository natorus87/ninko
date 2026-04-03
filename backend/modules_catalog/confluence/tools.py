"""
Confluence Module — LangGraph @tool functions.
"""

from __future__ import annotations

import logging
import os
import base64
from typing import Any

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.confluence.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Load config and secrets from ConnectionManager or env vars."""
    if connection_id:
        conn = await ConnectionManager.get_connection("confluence", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Confluence-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Confluence connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Confluence avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión de Confluence con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Confluence con ID '{connection_id}' non trovata.",
                    nl=f"Confluence-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Confluence z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Confluence com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のConfluence接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Confluence连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("confluence")

    if conn:
        base_url = conn.config.get("url", "")
        vault = get_vault()
        email = conn.config.get("email", "")
        api_key = None
        api_key_path = conn.vault_keys.get("CONFLUENCE_API_KEY")
        if api_key_path:
            api_key = await vault.get_secret(api_key_path)
        return {"base_url": base_url.rstrip("/"), "email": email, "api_key": api_key}

    base_url = os.environ.get("CONFLUENCE_URL", "")
    email = os.environ.get("CONFLUENCE_EMAIL", "")
    api_key = os.environ.get("CONFLUENCE_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de=(
                    "Keine Confluence-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY setzen."
                ),
                en=(
                    "No Confluence connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY."
                ),
                fr=(
                    "Aucune connexion Confluence configurée. "
                    "Veuillez créer une connexion dans Paramètres → Module → Engrenage, "
                    "ou définir les variables d'environnement CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY."
                ),
                es=(
                    "No hay conexión de Confluence configurada. "
                    "Por favor cree una conexión en Configuración → Módulo → Engranaje, "
                    "o establezca las variables de entorno CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY."
                ),
                it=(
                    "Nessuna connessione Confluence configurata. "
                    "Per favore crea una connessione in Impostazioni → Modulo → Ingranaggio, "
                    "o imposta le variabili di ambiente CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY."
                ),
                nl=(
                    "Geen Confluence-verbinding geconfigureerd. "
                    "Maak een verbinding aan in Instellingen → Module → Tandwiel, "
                    "of stel de omgevingsvariabelen CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY in."
                ),
                pl=(
                    "Nie skonfigurowano połączenia Confluence. "
                    "Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → Ikona koła zębatego "
                    "lub ustaw zmienne środowiskowe CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY."
                ),
                pt=(
                    "Nenhuma conexão Confluence configurada. "
                    "Por favor crie uma conexão em Configurações → Módulo → Engrenagem, "
                    "ou defina as variáveis de ambiente CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY."
                ),
                ja=(
                    "Confluence接続が設定されていません。 "
                    "ダッシュボードで設定→モジュール→歯車から接続を作成するか、"
                    "環境変数CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEYを設定してください。"
                ),
                zh=(
                    "未配置Confluence连接。 "
                    "请在设置→模块→齿轮下创建连接，"
                    "或设置环境变量CONFLUENCE_URL / CONFLUENCE_EMAIL / CONFLUENCE_API_KEY。"
                ),
            )
        )

    return {"base_url": base_url.rstrip("/"), "email": email, "api_key": api_key}


def _build_auth_header(email: str, api_key: str) -> str:
    """Build Basic Auth header for Confluence."""
    credentials = f"{email}:{api_key}"
    encoded = base64.b64encode(credentials.encode()).decode()
    return f"Basic {encoded}"


async def _confluence_request(
    base_url: str,
    auth_header: str,
    method: str,
    endpoint: str,
    params: dict | None = None,
    data: dict | None = None,
) -> dict:
    """Make a request to the Confluence API."""
    headers = {
        "Authorization": auth_header,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    url = f"{base_url}/wiki/api/v2{endpoint}"
    async with httpx.AsyncClient(timeout=30.0) as client:
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
        return resp.json()


@tool
async def get_confluence_spaces(connection_id: str = "") -> dict:
    """
    Retrieve all spaces from Confluence.
    Use this when the user asks for spaces or to see available wikis.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            "/spaces",
            {"limit": 25},
        )
        return {
            "status": "success",
            "spaces": result.get("results", []),
            "total": result.get("totalSize", 0),
        }
    except Exception as e:
        logger.error("get_confluence_spaces failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_confluence_space(space_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific space.
    Use this when the user asks for details about a specific space.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            f"/spaces/{space_id}",
        )
        return {
            "status": "success",
            "space": result,
        }
    except Exception as e:
        logger.error("get_confluence_space failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_confluence_pages(
    space_id: str = "",
    limit: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Retrieve pages from Confluence.
    Use this when the user asks for pages or documents.
    Can filter by space.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        params = {"limit": min(limit, 100), "sort": "-modified-date"}
        if space_id:
            params["space-id"] = space_id

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            "/pages",
            params,
        )
        return {
            "status": "success",
            "pages": result.get("results", []),
            "total": result.get("totalSize", 0),
        }
    except Exception as e:
        logger.error("get_confluence_pages failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_confluence_page(page_id: str, connection_id: str = "") -> dict:
    """
    Get details of a specific page including content.
    Use this when the user asks for a specific page content.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            f"/pages/{page_id}",
            {"body-format": "storage"},
        )
        return {
            "status": "success",
            "page": result,
        }
    except Exception as e:
        logger.error("get_confluence_page failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def create_confluence_page(
    space_id: str,
    title: str,
    content: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new page in Confluence.
    Use this when the user asks to create a new page or document.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        page_data = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
        }
        if content:
            page_data["body"] = {"representation": "storage", "value": content}

        result = await _confluence_request(
            client["base_url"],
            auth,
            "POST",
            "/pages",
            data=page_data,
        )
        return {
            "status": "success",
            "message": f"Page created: {result.get('id')}",
            "page": result,
        }
    except Exception as e:
        logger.error("create_confluence_page failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def update_confluence_page(
    page_id: str,
    title: str = "",
    content: str = "",
    connection_id: str = "",
) -> dict:
    """
    Update an existing page.
    Use this when the user asks to update page content or title.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        page_data = {}
        if title:
            page_data["title"] = title
        if content:
            page_data["body"] = {"representation": "storage", "value": content}

        result = await _confluence_request(
            client["base_url"],
            auth,
            "PUT",
            f"/pages/{page_id}",
            data=page_data,
        )
        return {
            "status": "success",
            "message": f"Page {page_id} updated.",
            "page": result,
        }
    except Exception as e:
        logger.error("update_confluence_page failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_confluence_blog_posts(
    space_id: str = "",
    limit: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Retrieve blog posts from Confluence.
    Use this when the user asks for blog posts or news.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        params = {"limit": min(limit, 100), "sort": "-created-date"}
        if space_id:
            params["space-id"] = space_id

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            "/blog-posts",
            params,
        )
        return {
            "status": "success",
            "posts": result.get("results", []),
            "total": result.get("totalSize", 0),
        }
    except Exception as e:
        logger.error("get_confluence_blog_posts failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def create_confluence_blog_post(
    space_id: str,
    title: str,
    content: str = "",
    connection_id: str = "",
) -> dict:
    """
    Create a new blog post in Confluence.
    Use this when the user asks to create a blog post or article.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        post_data = {
            "spaceId": space_id,
            "status": "current",
            "title": title,
        }
        if content:
            post_data["body"] = {"representation": "storage", "value": content}

        result = await _confluence_request(
            client["base_url"],
            auth,
            "POST",
            "/blog-posts",
            data=post_data,
        )
        return {
            "status": "success",
            "message": f"Blog post created: {result.get('id')}",
            "post": result,
        }
    except Exception as e:
        logger.error("create_confluence_blog_post failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def search_confluence(
    query: str,
    cql: str = "",
    limit: int = 25,
    connection_id: str = "",
) -> dict:
    """
    Search Confluence content using CQL (Confluence Query Language).
    Use this when the user asks to search for pages, blog posts, or content.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        params = {"limit": min(limit, 100)}
        if query:
            params["cql"] = f'text ~ "{query}"'
        elif cql:
            params["cql"] = cql
        else:
            raise ValueError("Either query or cql parameter is required")

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            "/pages",
            params,
        )
        return {
            "status": "success",
            "results": result.get("results", []),
            "total": result.get("totalSize", 0),
        }
    except Exception as e:
        logger.error("search_confluence failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_confluence_labels(connection_id: str = "") -> dict:
    """
    Retrieve all labels used in Confluence.
    Use this when the user asks for available labels or tags.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            "/labels",
            {"limit": 100},
        )
        return {
            "status": "success",
            "labels": result.get("results", []),
            "total": result.get("totalSize", 0),
        }
    except Exception as e:
        logger.error("get_confluence_labels failed: %s", e)
        return {"error": "Request failed. Check server logs."}


@tool
async def get_confluence_page_history(page_id: str, connection_id: str = "") -> dict:
    """
    Get version history of a page.
    Use this when the user asks for page history or previous versions.
    """
    try:
        client = await _get_api_client(connection_id)
        auth = _build_auth_header(client["email"], client["api_key"])

        result = await _confluence_request(
            client["base_url"],
            auth,
            "GET",
            f"/pages/{page_id}/versions",
            {"limit": 20},
        )
        return {
            "status": "success",
            "versions": result.get("results", []),
            "total": result.get("totalSize", 0),
        }
    except Exception as e:
        logger.error("get_confluence_page_history failed: %s", e)
        return {"error": "Request failed. Check server logs."}
