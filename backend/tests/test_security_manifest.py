"""Unit-Tests fuer das Security-Core-Modulmanifest (Task 5).

Der volle Modul-Import (inkl. BaseAgent-Instantiierung) braucht eine laufende
ChromaDB + Redis-Instanz (wie jeder andere Ninko-Agent) und wird deshalb NICHT
hier als Unit-Test abgebildet, um das Test-Gate nicht wieder zahnlos zu machen
(siehe project_hardening_2026_07.md). Manuell verifiziert gegen den laufenden
Dev-Stack: module_manifest.name == 'security', agent.tools enthaelt alle 6
Security-Tools, Trivy ist registriert (siehe project_security_core.md).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from modules.security.manifest import check_security_health, module_manifest

pytestmark = pytest.mark.unit


def test_manifest_has_required_fields():
    assert module_manifest.name == "security"
    assert module_manifest.api_prefix == "/api/security"
    assert module_manifest.routing_keywords
    assert "cve" in module_manifest.routing_keywords
    assert module_manifest.health_check is check_security_health


@pytest.mark.asyncio
async def test_health_check_ok_when_scanners_registered():
    with (
        patch("modules.security.scanner_registry.get_scanner_registry") as mock_registry,
        patch("modules.security.db.list_targets", AsyncMock(return_value=[])),
    ):
        mock_registry.return_value.list_definitions.return_value = [object()]
        result = await check_security_health()
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_health_check_warns_when_no_scanners_registered():
    with (
        patch("modules.security.scanner_registry.get_scanner_registry") as mock_registry,
        patch("modules.security.db.list_targets", AsyncMock(return_value=[])),
    ):
        mock_registry.return_value.list_definitions.return_value = []
        result = await check_security_health()
    assert result["status"] == "warning"


@pytest.mark.asyncio
async def test_health_check_reports_error_on_db_failure():
    with patch("modules.security.db.list_targets", AsyncMock(side_effect=OSError("db unreachable"))):
        result = await check_security_health()
    assert result["status"] == "error"
    assert "db unreachable" in result["detail"]
