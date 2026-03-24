"""
Telegram Modul – Manifest mit Metadaten und Health-Check.
"""

from __future__ import annotations

import logging
import httpx

from core.module_registry import ModuleManifest
from core.vault import get_vault

logger = logging.getLogger("kumio.modules.telegram")


async def check_telegram_health(connection_id: str = "") -> dict:
    """Health-Check für den Telegram Bot via getMe API."""
    try:
        from core.connections import ConnectionManager
        vault = get_vault()
        
        if connection_id:
            conn = await ConnectionManager.get_connection("telegram", connection_id)
        else:
            conn = await ConnectionManager.get_default_connection("telegram")
            
        bot_token = ""
        if conn and "TELEGRAM_BOT_TOKEN" in conn.vault_keys:
            bot_token = await vault.get_secret(conn.vault_keys["TELEGRAM_BOT_TOKEN"])
            
        if not bot_token:
            return {"status": "warning", "detail": "Kein Telegram Bot Token konfiguriert."}

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.telegram.org/bot{bot_token}/getMe")
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    bot_name = data["result"].get("username", "Unknown Bot")
                    return {"status": "ok", "detail": f"Verbunden als @{bot_name}"}
                else:
                    return {"status": "error", "detail": "Telegram API meldete Fehler."}
            elif resp.status_code == 401:
                return {"status": "error", "detail": "Unauthorized: Bot Token ist ungültig."}
            else:
                return {"status": "error", "detail": f"HTTP {resp.status_code}: {resp.text[:100]}"}

    except Exception as e:
        return {"status": "error", "detail": f"Telegram API nicht erreichbar: {e}"}


module_manifest = ModuleManifest(
    name="telegram",
    display_name="Telegram Bot",
    description="Ermöglicht das Chatten mit dem Kumio Orchestrator über Telegram",
    version="1.0.0",
    author="Kumio Team",
    enabled_by_default=True,
    env_prefix="TELEGRAM_",
    required_secrets=[],
    optional_secrets=["TELEGRAM_BOT_TOKEN"],
    routing_keywords=[
        "telegram", "telegram-nachricht", "telegram nachricht",
        "per telegram", "via telegram", "messenger",
        "benachrichtige", "telegram-gruppe", "telegram-kanal",
    ],
    api_prefix="/api/telegram",
    dashboard_tab={"id": "telegram", "label": "Telegram", "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>'},
    health_check=check_telegram_health,
)
