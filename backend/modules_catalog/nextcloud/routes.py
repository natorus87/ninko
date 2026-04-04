"""
Nextcloud Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter

logger = logging.getLogger("ninko.modules.nextcloud.routes")

router = APIRouter(tags=["nextcloud"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_nextcloud_health

    return await check_nextcloud_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get Nextcloud status for dashboard."""
    try:
        from .tools import _get_api_client, _ocs_request

        client = await _get_api_client(connection_id)
        users = await _ocs_request("GET", "/cloud/users", client)
        shares = await _ocs_request("GET", "/apps/files_sharing/api/v1/shares", client)
        storage = await _ocs_request("GET", f"/cloud/users/{client['user']}", client)

        user_list = users.get("users", []) if isinstance(users, dict) else []
        share_list = shares if isinstance(shares, list) else shares.get("data", [])

        quota = storage.get("quota", {})
        used = quota.get("used", 0) if quota else 0

        return {
            "users_count": len(user_list),
            "shares_count": len(share_list),
            "storage_used": used,
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"error": str(exc)}
