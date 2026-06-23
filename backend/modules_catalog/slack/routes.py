"""
Slack Module — FastAPI routes.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

logger = logging.getLogger("ninko.modules.slack.routes")

router = APIRouter(tags=["slack"])


@router.get("/health")
async def health_check() -> object:
    """Health check endpoint."""
    from .manifest import check_slack_health

    return await check_slack_health()


@router.get("/status")
async def get_status(connection_id: str = "") -> object:
    """Get Slack workspace status."""
    try:
        from .tools import _get_token, _slack_request

        token = await _get_token(connection_id)
        team = await _slack_request("POST", "/team.info", token)
        channels = await _slack_request(
            "POST", "/conversations.list", token, {"limit": 1}
        )
        users = await _slack_request("POST", "/users.list", token)

        return {
            "workspace": team.get("team", {}).get("name", ""),
            "channels_count": len(channels.get("channels", [])),
            "users_count": len(users.get("members", [])),
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
