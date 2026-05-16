"""
CodeLab Modul – Manifest.
"""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_codelab_health() -> dict:
    """Health-Check: immer verfügbar, da keine externe Verbindung nötig."""
    return {"status": "ok", "detail": "CodeLab Sandbox bereit"}


module_manifest = ModuleManifest(
    name="codelab",
    display_name="CodeLab",
    description=(
        "Code-Lab / coding sandbox: execute and analyze code in Python, Bash, "
        "JavaScript and other languages. Refactor, review, explain, optimize code; "
        "find bugs, suggest fixes, write unit tests, regex, algorithms. Improve "
        "text, spelling, formulation."
    ),
    version="1.0.1",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="CODELAB_",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "code", "programmieren", "programm",
        "bash", "javascript", "ausführen", "kompilieren",
        "code verbessern", "code optimieren", "refactoring", "refaktorieren",
        "code review", "code prüfen", "code erklären", "code analysieren",
        "text verbessern", "text optimieren", "text überarbeiten",
        "schreiben verbessern", "formulierung", "rechtschreibung",
        "sandbox", "codelab", "snippet", "funktion schreiben",
        "algorithmus", "regex", "fehler im code", "bug finden",
        "unit test", "unittest", "dokumentation schreiben",
    ],
    api_prefix="/api/codelab",
    dashboard_tab={
        "id": "codelab",
        "label": "CodeLab",
        "icon": '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"></polyline><polyline points="8 6 2 12 8 18"></polyline></svg>',
    },
    health_check=check_codelab_health,
)
