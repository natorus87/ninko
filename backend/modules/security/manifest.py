"""Security Core — Modulmanifest."""

from __future__ import annotations

from core.module_registry import ModuleManifest


async def check_security_health() -> dict:
    """Health-Check: DB erreichbar, mindestens ein Scanner registriert."""
    try:
        from .scanner_registry import get_scanner_registry

        registered = len(get_scanner_registry().list_definitions(enabled_only=True))
        from . import db

        await db.list_targets()  # erzwingt DB-Init, wirft bei Problemen
        if registered == 0:
            return {"status": "warning", "detail": "Keine Scanner registriert."}
        return {"status": "ok", "detail": f"{registered} Scanner registriert."}
    except (RuntimeError, ValueError, TypeError, OSError) as exc:
        return {"status": "error", "detail": str(exc)}


module_manifest = ModuleManifest(
    name="security",
    display_name="Security",
    description=(
        "Security Core: run and schedule vulnerability, container, Kubernetes, "
        "repository, network, and AI-platform security scans through isolated "
        "scanner adapters. Manage scan targets, review and triage findings, "
        "request approval for intrusive scans, and generate security reports. "
        "Never executes free-form shell commands or scanners outside the "
        "registered scanner registry."
    ),
    version="0.1.0",
    author="Ninko Team",
    enabled_by_default=True,
    env_prefix="SECURITY_",
    required_secrets=[],
    optional_secrets=[],
    routing_keywords=[
        "security scan", "vulnerability", "vulnerabilities", "cve",
        "sicherheitsscan", "sicherheitspruefung", "schwachstelle", "schwachstellen",
        "pentest", "penetration test", "security audit", "sicherheitsaudit",
        "container scan", "image scan", "trivy", "security finding", "security findings",
        "scan target", "security target", "finding", "findings",
        "security report", "sicherheitsbericht", "cvss", "cwe",
    ],
    api_prefix="/api/security",
    dashboard_tab={
        "id": "security",
        "label": "Security",
        "icon": (
            '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" '
            'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round">'
            '<path d="M12 2 4 6v6c0 5 3.5 8.5 8 10 4.5-1.5 8-5 8-10V6z"/>'
            "</svg>"
        ),
    },
    health_check=check_security_health,
)
