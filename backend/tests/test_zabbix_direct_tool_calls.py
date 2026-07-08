from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from core.tool_registry import ToolTier, get_tool_registry


BACKEND_DIR = Path(__file__).resolve().parents[1]
ZABBIX_DIR = BACKEND_DIR / "modules_catalog" / "zabbix"


class FakeTool:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.calls: list[dict[str, Any]] = []

    async def ainvoke(self, payload: dict[str, Any]) -> Any:
        self.calls.append(payload)
        return self.result


def _install_fake_zabbix_tools(monkeypatch: pytest.MonkeyPatch) -> dict[str, FakeTool]:
    package = types.ModuleType("modules_catalog.zabbix")
    package.__path__ = [str(ZABBIX_DIR)]
    tools = types.ModuleType("modules_catalog.zabbix.tools")

    fake_tools = {
        "get_zabbix_status": FakeTool({"status": "online"}),
        "list_zabbix_hosts": FakeTool([{"hostid": "1", "name": "web"}]),
        "get_zabbix_host": FakeTool({"hostid": "1", "name": "web"}),
        "list_zabbix_items": FakeTool([{"itemid": "10"}]),
        "list_zabbix_triggers": FakeTool([{"triggerid": "20"}]),
        "get_zabbix_problems": FakeTool([{"eventid": "30"}]),
        "list_zabbix_graphs": FakeTool([{"graphid": "40"}]),
        "get_zabbix_host_group": FakeTool([{"groupid": "50"}]),
        "list_zabbix_templates": FakeTool([{"templateid": "60"}]),
        "list_zabbix_actions": FakeTool([{"actionid": "70"}]),
        "get_zabbix_history": FakeTool([{"clock": "80", "value": "1"}]),
        "create_zabbix_host": FakeTool({"hostid": "90"}),
        "delete_zabbix_host": FakeTool({"deleted": "90"}),
    }
    for name, fake_tool in fake_tools.items():
        setattr(tools, name, fake_tool)

    monkeypatch.setitem(sys.modules, "modules_catalog.zabbix", package)
    monkeypatch.setitem(sys.modules, "modules_catalog.zabbix.tools", tools)
    return fake_tools


def _load_module(module_name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


async def test_zabbix_status_route_invokes_structured_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tools = _install_fake_zabbix_tools(monkeypatch)
    routes = _load_module("zabbix_routes_under_test", ZABBIX_DIR / "routes.py")

    response = await routes.get_status(connection_id="conn-1")

    assert response.success is True
    assert response.data == {"status": "online"}
    assert fake_tools["get_zabbix_status"].calls == [{"connection_id": "conn-1"}]


async def test_zabbix_create_host_route_invokes_structured_tool_with_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tools = _install_fake_zabbix_tools(monkeypatch)
    routes = _load_module("zabbix_routes_under_test_create", ZABBIX_DIR / "routes.py")

    response = await routes.create_host(
        host_name="web-01",
        ip="10.0.0.5",
        group_id="2",
        connection_id="conn-1",
    )

    assert response.success is True
    assert response.data == {"hostid": "90"}
    assert fake_tools["create_zabbix_host"].calls == [
        {
            "host_name": "web-01",
            "ip": "10.0.0.5",
            "group_id": "2",
            "connection_id": "conn-1",
        }
    ]


async def test_zabbix_health_invokes_structured_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_tools = _install_fake_zabbix_tools(monkeypatch)
    manifest = _load_module("modules_catalog.zabbix.manifest", ZABBIX_DIR / "manifest.py")

    response = await manifest.check_zabbix_health(connection_id="conn-1")

    assert response == {
        "status": "ok",
        "detail": "Zabbix reachable",
        "info": {"status": "online"},
    }
    assert fake_tools["get_zabbix_status"].calls == [{"connection_id": "conn-1"}]


def test_zabbix_write_tools_have_deterministic_registry_tiers() -> None:
    registry = get_tool_registry()

    assert registry.tier_of("create_zabbix_host", "zabbix") == ToolTier.WRITE_SYSTEM
    assert registry.tier_of("delete_zabbix_host", "zabbix") == ToolTier.ADMIN
    assert registry.is_readonly("list_zabbix_hosts", "zabbix") is True
