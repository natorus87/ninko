"""Message Hub — Modulmanifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_message_hub_health() -> dict:
    """Health-Check: Prüft ob Hub läuft und Routen konfiguriert sind."""
    try:
        from .hub import get_message_hub
        from .db import list_routes

        hub = get_message_hub()
        routes = await list_routes()
        active = sum(1 for r in routes if r.enabled)

        if hub is None:
            return {"status": "warning", "detail": f"Hub nicht aktiv. {len(routes)} Routen konfiguriert."}

        status = hub.get_status()
        running = sum(1 for w in status.workers if w.running)
        return {
            "status": "ok",
            "detail": f"{running}/{len(status.workers)} Worker aktiv | {active} aktive Routen",
        }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="message_hub",
    display_name="Message Hub",
    description=(
        "Message Hub: bidirectional channel routing across Email (IMAP IDLE), "
        "Discord, and Telegram. Maps external channel IDs to Ninko sessions; "
        "manage incoming messages, hub status, and routing rules."
    ),
    version="1.0.1",
    author="Ninko",
    enabled_by_default=True,
    env_prefix="MESSAGE_HUB_",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "message hub",
        "kanal routing",
        "channel routing",
        "eingehende nachrichten",
        "incoming messages",
        "message routing",
        "hub status",
        "hub route",
        "routing regel",
    ],
    api_prefix="/api/message_hub",
    dashboard_tab={
        "id": "message_hub",
        "label": "Message Hub",
        "icon": (
            '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round">'
            '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>'
            '<line x1="9" y1="10" x2="15" y2="10"/>'
            '<line x1="12" y1="7" x2="12" y2="13"/>'
            "</svg>"
        ),
    },
    health_check=check_message_hub_health,
)
