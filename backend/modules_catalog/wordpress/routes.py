"""
WordPress Modul – FastAPI Router für Dashboard-API.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

from .tools import (
    get_site_info,
    list_plugins,
    list_pages,
    get_page,
    list_posts,
    get_post,
    list_users,
    get_site_settings,
    list_media,
)

logger = logging.getLogger("ninko.modules.wordpress.routes")
router = APIRouter()


@router.get("/info")
async def site_info(connection_id: str = ""):
    """WordPress-Instanz Informationen."""
    return await get_site_info.ainvoke({"connection_id": connection_id})


@router.get("/plugins")
async def plugins(status: str = "all", connection_id: str = ""):
    """Installierte Plugins auflisten."""
    return await list_plugins.ainvoke({"status": status, "connection_id": connection_id})


@router.get("/pages")
async def pages(status: str = "any", per_page: int = 20, connection_id: str = ""):
    """WordPress-Seiten auflisten."""
    return await list_pages.ainvoke({"status": status, "per_page": per_page, "connection_id": connection_id})


@router.get("/pages/{page_id}")
async def page_detail(page_id: int, connection_id: str = ""):
    """Einzelne Seite abrufen."""
    return await get_page.ainvoke({"page_id": page_id, "connection_id": connection_id})


@router.get("/posts")
async def posts(status: str = "any", per_page: int = 20, connection_id: str = ""):
    """Beiträge auflisten."""
    return await list_posts.ainvoke({"status": status, "per_page": per_page, "connection_id": connection_id})


@router.get("/posts/{post_id}")
async def post_detail(post_id: int, connection_id: str = ""):
    """Einzelnen Beitrag abrufen."""
    return await get_post.ainvoke({"post_id": post_id, "connection_id": connection_id})


@router.get("/users")
async def users(connection_id: str = ""):
    """Benutzer auflisten."""
    return await list_users.ainvoke({"connection_id": connection_id})


@router.get("/settings")
async def settings(connection_id: str = ""):
    """Site-Einstellungen abrufen."""
    return await get_site_settings.ainvoke({"connection_id": connection_id})


@router.get("/media")
async def media(per_page: int = 20, connection_id: str = ""):
    """Medien auflisten."""
    return await list_media.ainvoke({"per_page": per_page, "connection_id": connection_id})
