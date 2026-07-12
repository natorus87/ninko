"""Unit-Tests fuer die 9 Security-Agent-Profile (Task 6 + Task 12: Remediation/Report)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from modules.security.agent_profiles import SECURITY_AGENT_PROFILES, register_builtin_security_agents

pytestmark = pytest.mark.unit


# ── Statische Profil-Eigenschaften ────────────────────────────────────────


def test_nine_profiles_defined():
    assert len(SECURITY_AGENT_PROFILES) == 9


def test_remediation_agent_denies_scan_creation_and_infra_apply():
    remediation = next(p for p in SECURITY_AGENT_PROFILES if p.name == "Remediation Agent")
    assert "security.scan.create" in remediation.denied_capabilities
    assert "infrastructure.change.apply" in remediation.denied_capabilities
    assert "proposal only" in remediation.system_prompt.lower() or "propose" in remediation.system_prompt.lower()


def test_report_agent_has_no_remediation_capability():
    report_agent = next(p for p in SECURITY_AGENT_PROFILES if p.name == "Security Report Agent")
    assert "security.remediation.propose" not in report_agent.capabilities
    assert "security.scan.create" in report_agent.denied_capabilities


def test_profile_names_are_unique():
    names = [p.name for p in SECURITY_AGENT_PROFILES]
    assert len(names) == len(set(names))


def test_all_profiles_deny_intrusive_by_default():
    for spec in SECURITY_AGENT_PROFILES:
        assert "security.scan.execute.intrusive" in spec.denied_capabilities, spec.name


def test_all_profiles_have_non_empty_capabilities():
    for spec in SECURITY_AGENT_PROFILES:
        assert spec.capabilities, f"{spec.name} hat keine Capabilities"


def test_all_profiles_have_english_prompt_delegating_to_security_module():
    for spec in SECURITY_AGENT_PROFILES:
        assert 'call_module_agent("security"' in spec.system_prompt, spec.name
        assert "execute_cli_command" in spec.system_prompt  # explizit verboten erwaehnt


def test_all_profiles_have_non_reserved_names():
    reserved = {"orchestrator", "monitor", "scheduler"}
    for spec in SECURITY_AGENT_PROFILES:
        assert spec.name.casefold() not in reserved


# ── register_builtin_security_agents (gemockter Pool) ─────────────────────


def _fake_pool(existing_names=None):
    pool = MagicMock()
    pool.list_agents.return_value = [{"name": n} for n in (existing_names or [])]
    pool.register = AsyncMock(side_effect=lambda **kw: (f"id-{kw['name']}", MagicMock()))
    pool._meta = {}
    return pool


@pytest.mark.asyncio
async def test_register_builtin_security_agents_registers_all_when_none_exist(mock_redis):
    pool = _fake_pool(existing_names=[])
    mock_redis.connection.get.return_value = None

    with (
        patch("core.agent_pool.get_agent_pool", return_value=pool),
        patch("core.agent_pool._effective_tenant_id", return_value="default"),
        patch("core.agent_pool._tenant_key", return_value="ninko:agents:default"),
        patch("core.redis_client.get_redis", return_value=mock_redis),
    ):
        registered = await register_builtin_security_agents()

    assert len(registered) == 9
    assert pool.register.await_count == 9


@pytest.mark.asyncio
async def test_register_builtin_security_agents_skips_already_registered(mock_redis):
    existing = [p.name for p in SECURITY_AGENT_PROFILES]  # alle bereits vorhanden
    pool = _fake_pool(existing_names=existing)
    mock_redis.connection.get.return_value = None

    with (
        patch("core.agent_pool.get_agent_pool", return_value=pool),
        patch("core.agent_pool._effective_tenant_id", return_value="default"),
        patch("core.agent_pool._tenant_key", return_value="ninko:agents:default"),
        patch("core.redis_client.get_redis", return_value=mock_redis),
    ):
        registered = await register_builtin_security_agents()

    assert registered == []
    pool.register.assert_not_awaited()


@pytest.mark.asyncio
async def test_register_builtin_security_agents_continues_after_value_error(mock_redis):
    pool = _fake_pool(existing_names=[])

    call_count = {"n": 0}

    async def _register_side_effect(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise ValueError("Name reserviert")
        return f"id-{kwargs['name']}", MagicMock()

    pool.register = AsyncMock(side_effect=_register_side_effect)
    mock_redis.connection.get.return_value = None

    with (
        patch("core.agent_pool.get_agent_pool", return_value=pool),
        patch("core.agent_pool._effective_tenant_id", return_value="default"),
        patch("core.agent_pool._tenant_key", return_value="ninko:agents:default"),
        patch("core.redis_client.get_redis", return_value=mock_redis),
    ):
        registered = await register_builtin_security_agents()

    assert len(registered) == 8  # 1 fehlgeschlagen, 8 erfolgreich
    assert pool.register.await_count == 9


@pytest.mark.asyncio
async def test_register_builtin_security_agents_persists_capabilities_metadata(mock_redis):
    """pool.register() persistiert im echten DynamicAgentPool einen agent_def-Eintrag
    mit passender 'id' nach Redis — der Fake muss das nachbilden, sonst findet der
    Metadaten-Patch-Loop in register_builtin_security_agents() nichts zum Patchen."""
    stored = {"agents": json.dumps([])}

    async def _get(_key):
        return stored["agents"]

    async def _set(_key, value, **_kw):
        stored["agents"] = value

    mock_redis.connection.get.side_effect = _get
    mock_redis.connection.set.side_effect = _set

    counter = {"n": 0}

    async def _fake_register(*, name, system_prompt, description, tenant_id):
        counter["n"] += 1
        agent_id = f"id-{counter['n']}"
        agents = json.loads(stored["agents"])
        agents.append({"id": agent_id, "name": name, "module_names": []})
        stored["agents"] = json.dumps(agents)
        return agent_id, MagicMock()

    pool = MagicMock()
    pool.list_agents.return_value = []
    pool.register = AsyncMock(side_effect=_fake_register)
    pool._meta = {}

    with (
        patch("core.agent_pool.get_agent_pool", return_value=pool),
        patch("core.agent_pool._effective_tenant_id", return_value="default"),
        patch("core.agent_pool._tenant_key", return_value="ninko:agents:default"),
        patch("core.redis_client.get_redis", return_value=mock_redis),
    ):
        await register_builtin_security_agents()

    final_agents = json.loads(stored["agents"])
    assert len(final_agents) == 9
    for entry in final_agents:
        assert entry["module_names"] == ["security"]
        assert "security.scan.execute.intrusive" in entry["security_denied_capabilities"]
