"""
Slack Module – Manifest.

Team Communication via Slack API.
"""

from __future__ import annotations

import logging
import os

import aiohttp

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.slack")


async def check_slack_health() -> dict:
    """Health check for Slack API."""
    try:
        from core.connections import ConnectionManager
        from core.vault import get_vault

        conn = await ConnectionManager.get_default_connection("slack")
        if not conn:
            token = os.environ.get("SLACK_BOT_TOKEN", "")
            if not token:
                return {"status": "ok", "detail": "No connection configured (expected)"}
            vault = get_vault()
            if not token.startswith("xoxb"):
                vault_token = await vault.get_secret("SLACK_BOT_TOKEN")
                if not vault_token or not vault_token.startswith("xoxb"):
                    return {"status": "error", "detail": "Invalid token format"}
                token = vault_token

            async with aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {token}"},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get("https://slack.com/api/team.info") as resp:
                    data = await resp.json()
                    if data.get("ok"):
                        return {
                            "status": "ok",
                            "detail": f"Slack workspace reachable (Env)",
                        }
                    return {"status": "error", "detail": data.get("error", "Unknown")}

        token = conn.config.get("token", "")
        vault = get_vault()
        if token.startswith("xoxb"):
            pass
        else:
            vault_key = conn.vault_keys.get("SLACK_BOT_TOKEN")
            if vault_key:
                token = await vault.get_secret(vault_key)
            else:
                token = os.environ.get("SLACK_BOT_TOKEN", "")

        if not token or not token.startswith("xoxb"):
            return {"status": "error", "detail": "Invalid token"}

        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as session:
            async with session.get("https://slack.com/api/team.info") as resp:
                data = await resp.json()
                if data.get("ok"):
                    return {"status": "ok", "detail": "Slack workspace reachable"}
                return {"status": "error", "detail": data.get("error", "Unknown")}

    except aiohttp.ClientResponseError as e:
        return {"status": "error", "detail": f"HTTP {e.status}: {e.message}"}
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="slack",
    display_name="Slack",
    description="Slack Team Communication – Channels, Messages, Users, and Notifications.",
    version="1.0.0",
    author="Ninko",
    enabled_by_default=False,
    env_prefix="SLACK_",
    required_secrets=["SLACK_BOT_TOKEN"],
    optional_secrets=[],
    routing_keywords=[
        "slack",
        "slack channel",
        "slack nachricht",
        "slack bot",
        "slack webhook",
        "slack notification",
    ],
    api_prefix="/api/slack",
    dashboard_tab={
        "id": "slack",
        "label": "Slack",
        "icon": "💬",
    },
    health_check=check_slack_health,
)
