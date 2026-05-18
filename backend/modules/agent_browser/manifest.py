"""
Agent Browser Modul – Manifest & Health-Check.

Wrappt das CLI-Tool `agent-browser` (https://agent-browser.dev) für
Webseiten-Tests: Funktionsprüfung, Element-Interaktion, Screenshots.
"""

from __future__ import annotations

import asyncio
import logging
import shutil

from core.module_registry import ModuleManifest

logger = logging.getLogger("ninko.modules.agent_browser")

_AGENT_BROWSER_BIN = "agent-browser"
_HEALTH_TIMEOUT = 5.0


async def check_agent_browser_health() -> dict:
    """Prüft, ob die `agent-browser` Binary verfügbar ist und antwortet."""
    if shutil.which(_AGENT_BROWSER_BIN) is None:
        return {
            "status": "error",
            "detail": (
                f"`{_AGENT_BROWSER_BIN}` nicht im PATH. "
                "Image-Build muss `npm install -g agent-browser` enthalten."
            ),
        }

    try:
        proc = await asyncio.create_subprocess_exec(
            _AGENT_BROWSER_BIN,
            "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(), timeout=_HEALTH_TIMEOUT
        )
    except asyncio.TimeoutError:
        return {"status": "error", "detail": "agent-browser --version timeout"}
    except OSError as exc:
        return {"status": "error", "detail": f"agent-browser exec error: {exc}"}

    if proc.returncode != 0:
        err = (stderr or b"").decode(errors="replace").strip()[:200]
        return {"status": "error", "detail": f"agent-browser exit {proc.returncode}: {err}"}

    version = (stdout or b"").decode(errors="replace").strip() or "unknown"
    return {"status": "ok", "detail": f"agent-browser {version}"}


module_manifest = ModuleManifest(
    name="agent_browser",
    display_name="Agent Browser",
    description=(
        "Browser automation for website testing: open pages, click elements, "
        "type into forms, take screenshots, snapshot accessibility tree, "
        "validate that IT-tools and web UIs work as expected."
    ),
    version="1.0.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="NINKO_MODULE_AGENT_BROWSER",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "browser",
        "website",
        "webseite",
        "web ui",
        "ui test",
        "ui-test",
        "klick",
        "click",
        "screenshot",
        "render",
        "snapshot",
        "browser test",
        "webseiten test",
        "frontend test",
        "agent-browser",
        "agent browser",
        "form test",
        "selenium",
        "playwright",
    ],
    api_prefix="/api/agent-browser",
    health_check=check_agent_browser_health,
)
