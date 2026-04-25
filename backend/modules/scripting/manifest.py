"""
Scripting MVP Module – Manifest.
Persistente Python-Skripte mit sicherer Sandbox-Ausführung.
"""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_scripting_health() -> dict:
    return {"status": "ok", "detail": "Scripting Module bereit"}


module_manifest = ModuleManifest(
    name="scripting",
    display_name="Scripting",
    description="Persistente Python-Skripte mit sicherer Sandbox-Ausführung",
    version="0.1.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="SCRIPTING_",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "automation script",
        "scripting",
        "python automation",
        "script runner",
        "automation",
        "automatisierung",
        "batch",
        "routine",
        "hintergrund",
        "scheduled script",
        "cron script",
    ],
    api_prefix="/api/scripting",
    dashboard_tab={
        "id": "scripting",
        "label": "Scripting",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>',
    },
    health_check=check_scripting_health,
)
