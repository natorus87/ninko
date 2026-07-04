"""
Tests for Proxmox power-operation tools (start, stop, reboot, reset, suspend, resume).

Verifies:
1. Tools call the correct proxmoxer endpoints (no PROXMOX_CONFIRM_DESTRUCTIVE gate).
2. Tools return the expected status/dict structure.
3. Tools are registered with the correct ToolTier (WRITE_SYSTEM, not READONLY).
4. Errors from proxmoxer are surfaced (not swallowed).

Note: conftest.py sets secure default settings before any core.* import,
so we don't need to set env vars here.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from core.tool_registry import ToolTier, get_tool_registry

TOOLS_PATH = Path(__file__).resolve().parents[1] / "modules_catalog" / "proxmox" / "tools.py"
SPEC = importlib.util.spec_from_file_location("proxmox_tools_for_test", TOOLS_PATH)
assert SPEC is not None
proxmox_tools = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(proxmox_tools)
MANIFEST_PATH = Path(__file__).resolve().parents[1] / "modules_catalog" / "proxmox" / "manifest.py"


# ── Helpers ──────────────────────────────────────────────────────────────────


def _mock_proxmox_chain() -> MagicMock:
    """Build a mock proxmoxer chain: proxmox.nodes(node).qemu(vmid).status.X.post()"""
    mock = MagicMock()
    mock.nodes.return_value.qemu.return_value.status.start.post = MagicMock()
    mock.nodes.return_value.qemu.return_value.status.stop.post = MagicMock()
    mock.nodes.return_value.qemu.return_value.status.reboot.post = MagicMock()
    mock.nodes.return_value.qemu.return_value.status.reset.post = MagicMock()
    mock.nodes.return_value.qemu.return_value.status.suspend.post = MagicMock()
    mock.nodes.return_value.qemu.return_value.status.resume.post = MagicMock()
    mock.nodes.return_value.lxc.return_value.status.start.post = MagicMock()
    mock.nodes.return_value.lxc.return_value.status.stop.post = MagicMock()
    mock.nodes.return_value.lxc.return_value.status.reboot.post = MagicMock()
    return mock


def _post_method(tool_name: str, guest_type: str) -> MagicMock:
    """Return the MagicMock for the relevant .post() endpoint."""
    chain = _mock_proxmox_chain()
    guest = getattr(chain.nodes("pve-1"), guest_type)(130)
    action_name = tool_name.replace("_vm", "").replace("_container", "")
    return getattr(guest.status, action_name).post


# ── Power-tool endpoint tests ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_vm_calls_proxmox_start() -> None:
    """start_vm must call proxmox.nodes(node).qemu(vmid).status.start.post()."""
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=_mock_proxmox_chain())
    ):
        result = await proxmox_tools.start_vm.ainvoke({"node": "pve-1", "vmid": 130})

    assert result["action"] == "start"
    assert result["status"] == "success"
    assert "VM 130" in result["target"]
    assert result["node"] == "pve-1"


@pytest.mark.asyncio
async def test_stop_vm_calls_proxmox_stop_directly() -> None:
    """stop_vm must call proxmox.stop.post() directly (no confirmation gate)."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.stop_vm.ainvoke({"node": "pve-1", "vmid": 130})

    # Verify the actual proxmox endpoint was called
    mock.nodes.assert_called_with("pve-1")
    mock.nodes.return_value.qemu.assert_called_with(130)
    mock.nodes.return_value.qemu.return_value.status.stop.post.assert_called_once_with()

    # Verify the result shape (no 'confirmation_required' anymore)
    assert result["action"] == "stop"
    assert result["status"] == "success"
    assert result["status"] != "confirmation_required"


@pytest.mark.asyncio
async def test_reboot_vm_calls_proxmox_reboot() -> None:
    """reboot_vm must call proxmox.nodes(node).qemu(vmid).status.reboot.post()."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.reboot_vm.ainvoke({"node": "pve-1", "vmid": 130})

    mock.nodes.return_value.qemu.return_value.status.reboot.post.assert_called_once_with()
    assert result["action"] == "reboot"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_reset_vm_calls_proxmox_reset_directly() -> None:
    """reset_vm must call proxmox.reset.post() directly (no confirmation gate)."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.reset_vm.ainvoke({"node": "pve-1", "vmid": 130})

    mock.nodes.return_value.qemu.return_value.status.reset.post.assert_called_once_with()
    assert result["action"] == "reset"
    assert result["status"] == "success"
    assert result["status"] != "confirmation_required"


@pytest.mark.asyncio
async def test_suspend_vm_calls_proxmox_suspend() -> None:
    """suspend_vm must call proxmox.nodes(node).qemu(vmid).status.suspend.post()."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.suspend_vm.ainvoke({"node": "pve-1", "vmid": 130})

    mock.nodes.return_value.qemu.return_value.status.suspend.post.assert_called_once_with()
    assert result["action"] == "suspend"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_resume_vm_calls_proxmox_resume() -> None:
    """resume_vm must call proxmox.nodes(node).qemu(vmid).status.resume.post()."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.resume_vm.ainvoke({"node": "pve-1", "vmid": 130})

    mock.nodes.return_value.qemu.return_value.status.resume.post.assert_called_once_with()
    assert result["action"] == "resume"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_start_container_calls_proxmox_start() -> None:
    """start_container must call proxmox.nodes(node).lxc(vmid).status.start.post()."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.start_container.ainvoke({"node": "pve-1", "vmid": 200})

    mock.nodes.return_value.lxc.assert_called_with(200)
    mock.nodes.return_value.lxc.return_value.status.start.post.assert_called_once_with()
    assert result["action"] == "start"
    assert result["target"] == "CT 200"
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_stop_container_calls_proxmox_stop_directly() -> None:
    """stop_container must call proxmox.stop.post() directly (no confirmation gate)."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.stop_container.ainvoke({"node": "pve-1", "vmid": 200})

    mock.nodes.return_value.lxc.return_value.status.stop.post.assert_called_once_with()
    assert result["action"] == "stop"
    assert result["status"] == "success"
    assert result["status"] != "confirmation_required"


@pytest.mark.asyncio
async def test_reboot_container_calls_proxmox_reboot() -> None:
    """reboot_container must call proxmox.nodes(node).lxc(vmid).status.reboot.post()."""
    mock = _mock_proxmox_chain()
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.reboot_container.ainvoke({"node": "pve-1", "vmid": 200})

    mock.nodes.return_value.lxc.return_value.status.reboot.post.assert_called_once_with()
    assert result["action"] == "reboot"
    assert result["status"] == "success"


# ── Error-surfacing tests ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_reboot_vm_surfaces_proxmox_errors() -> None:
    """If proxmoxer raises, the error must be in the response (not swallowed)."""
    mock = _mock_proxmox_chain()
    mock.nodes.return_value.qemu.return_value.status.reboot.post.side_effect = RuntimeError(
        "VM is locked"
    )
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.reboot_vm.ainvoke({"node": "pve-1", "vmid": 130})

    assert result["status"] == "error"
    assert "VM is locked" in result["detail"]


@pytest.mark.asyncio
async def test_stop_vm_surfaces_proxmox_errors() -> None:
    """stop_vm must surface errors (not return confirmation_required)."""
    mock = _mock_proxmox_chain()
    mock.nodes.return_value.qemu.return_value.status.stop.post.side_effect = ValueError(
        "VMID 9999 not found"
    )
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.stop_vm.ainvoke({"node": "pve-1", "vmid": 9999})

    assert result["status"] == "error"
    assert "9999" in result["detail"]
    assert "not found" in result["detail"]


# ── smart_* type-detection tests (LXC must not be misdetected as QEMU) ────────


@pytest.mark.asyncio
async def test_detect_target_type_uses_resource_type_field() -> None:
    """cluster/resources?type=vm liefert qemu UND lxc — der Typ kommt aus dem Feld."""
    mock = _mock_proxmox_chain()
    mock.cluster.resources.get = MagicMock(
        return_value=[
            {"vmid": 130, "node": "pve-1", "type": "qemu"},
            {"vmid": 200, "node": "pve-1", "type": "lxc"},
        ]
    )
    assert await proxmox_tools._detect_target_type(mock, "pve-1", 200) == "lxc"
    assert await proxmox_tools._detect_target_type(mock, "pve-1", 130) == "qemu"


@pytest.mark.asyncio
async def test_smart_reboot_uses_lxc_endpoint_for_container() -> None:
    """smart_reboot auf einen LXC-Container muss den lxc-Endpoint aufrufen, nicht qemu."""
    mock = _mock_proxmox_chain()
    mock.cluster.resources.get = MagicMock(
        return_value=[{"vmid": 200, "node": "pve-1", "type": "lxc"}]
    )
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.smart_reboot.ainvoke({"node": "pve-1", "vmid": 200})

    assert result["status"] == "success"
    assert result["target_type"] == "lxc"
    mock.nodes.return_value.lxc.return_value.status.reboot.post.assert_called_once_with()
    mock.nodes.return_value.qemu.return_value.status.reboot.post.assert_not_called()


@pytest.mark.asyncio
async def test_smart_start_uses_qemu_endpoint_for_vm() -> None:
    """smart_start auf eine QEMU-VM muss den qemu-Endpoint aufrufen."""
    mock = _mock_proxmox_chain()
    mock.cluster.resources.get = MagicMock(
        return_value=[{"vmid": 130, "node": "pve-1", "type": "qemu"}]
    )
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.smart_start.ainvoke({"node": "pve-1", "vmid": 130})

    assert result["status"] == "success"
    assert result["target_type"] == "qemu"
    mock.nodes.return_value.qemu.return_value.status.start.post.assert_called_once_with()


@pytest.mark.asyncio
async def test_smart_stop_uses_lxc_endpoint_for_container() -> None:
    """smart_stop nutzt denselben Typ-Erkennungspfad — auch für LXC verifizieren."""
    mock = _mock_proxmox_chain()
    mock.cluster.resources.get = MagicMock(
        return_value=[{"vmid": 200, "node": "pve-1", "type": "lxc"}]
    )
    with patch.object(
        proxmox_tools, "_get_proxmox_client", new=AsyncMock(return_value=mock)
    ):
        result = await proxmox_tools.smart_stop.ainvoke({"node": "pve-1", "vmid": 200})

    assert result["status"] == "success"
    assert result["target_type"] == "lxc"
    mock.nodes.return_value.lxc.return_value.status.stop.post.assert_called_once_with()


@pytest.mark.asyncio
async def test_detect_target_type_skips_malformed_resource_entries() -> None:
    """Ein Eintrag ohne gültige vmid darf die Suche nicht abbrechen."""
    mock = _mock_proxmox_chain()
    mock.cluster.resources.get = MagicMock(
        return_value=[
            {"node": "pve-1", "type": "storage"},   # kein vmid
            {"vmid": None, "node": "pve-1"},          # vmid None
            {"vmid": 200, "node": "pve-1", "type": "lxc"},  # Treffer danach
        ]
    )
    assert await proxmox_tools._detect_target_type(mock, "pve-1", 200) == "lxc"


@pytest.mark.asyncio
async def test_detect_target_type_falls_back_when_cluster_unavailable() -> None:
    """Wirft cluster.resources, greift die direkte Endpoint-Probe."""
    from proxmoxer.core import ResourceException

    mock = _mock_proxmox_chain()
    mock.cluster.resources.get = MagicMock(side_effect=ResourceException(500, "x", "y"))
    # qemu-Probe schlägt fehl, lxc-Probe gelingt → "lxc"
    mock.nodes.return_value.qemu.return_value.status.current.get = MagicMock(
        side_effect=ResourceException(404, "not found", "z")
    )
    mock.nodes.return_value.lxc.return_value.status.current.get = MagicMock(
        return_value={"status": "running"}
    )
    assert await proxmox_tools._detect_target_type(mock, "pve-1", 200) == "lxc"


# ── Tool-registry tier tests ─────────────────────────────────────────────────


POWER_TOOLS = (
    "start_vm",
    "stop_vm",
    "reboot_vm",
    "reset_vm",
    "suspend_vm",
    "resume_vm",
    "start_container",
    "stop_container",
    "reboot_container",
)


@pytest.mark.parametrize("tool_name", POWER_TOOLS)
def test_power_tool_is_registered_as_write_system(tool_name: str) -> None:
    """All 9 Proxmox power-tools must be WRITE_SYSTEM tier (→ STATE_CHANGING)."""
    registry = get_tool_registry()
    tier = registry.tier_of(tool_name, "proxmox")
    assert tier == ToolTier.WRITE_SYSTEM, (
        f"{tool_name} must be WRITE_SYSTEM tier for safeguard, got {tier}"
    )
    assert registry.is_readonly(tool_name, "proxmox") is False
    assert tool_name not in registry.readonly_names()


def test_readonly_proxmox_tools_remain_readonly() -> None:
    """Regression: read-only Proxmox tools must stay READONLY after registry changes."""
    registry = get_tool_registry()
    for name in (
        "get_nodes",
        "get_node_status",
        "get_node_ip_addresses",
        "list_node_ip_addresses",
        "list_all_vms",
        "list_vms",
        "get_vm_status",
        "get_vm_ip_addresses",
        "list_vm_ip_addresses",
        "get_vm_config",
        "get_recent_tasks",
    ):
        assert registry.is_readonly(name, "proxmox") is True, f"{name} must be read-only"
        assert registry.tier_of(name, "proxmox") == ToolTier.READONLY


def test_duplicate_tool_names_resolve_with_module_context() -> None:
    """Docker and Proxmox both expose container tools; module context must disambiguate."""
    registry = get_tool_registry()

    assert registry.get("list_containers", "docker").module == "docker"
    assert registry.get("list_containers", "proxmox").module == "proxmox"
    assert registry.is_readonly("list_containers", "docker") is True
    assert registry.is_readonly("list_containers", "proxmox") is True

    assert registry.get("start_container", "docker").module == "docker"
    assert registry.get("start_container", "proxmox").module == "proxmox"
    assert registry.tier_of("start_container", "docker") == ToolTier.WRITE_SYSTEM
    assert registry.tier_of("start_container", "proxmox") == ToolTier.WRITE_SYSTEM


def test_proxmox_power_tool_descriptions_include_german_restart_synonyms() -> None:
    """
    Regression: Proxmox has more tools than the JIT threshold. German restart
    requests must still match the reboot tools before the LLM plans the action.
    """
    vm_description = str(proxmox_tools.reboot_vm.description).lower()
    container_description = str(proxmox_tools.reboot_container.description).lower()

    assert "restart" in vm_description
    assert "neustart" in vm_description
    assert "neustarten" in vm_description
    assert "neu starten" in vm_description
    assert "restart" in container_description
    assert "neustart" in container_description
    assert "neustarten" in container_description


def test_proxmox_manifest_routes_restart_intents_to_proxmox() -> None:
    """Regression: generic VM restart wording must be enough to select Proxmox."""
    tree = ast.parse(MANIFEST_PATH.read_text(encoding="utf-8"))
    routing_keywords: list[str] = []
    description = ""

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "id", "") != "ModuleManifest":
            continue
        for keyword in node.keywords:
            if keyword.arg == "routing_keywords":
                routing_keywords = ast.literal_eval(keyword.value)
            if keyword.arg == "description":
                description = ast.literal_eval(keyword.value)

    assert "neustart" in routing_keywords
    assert "neustarten" in routing_keywords
    assert "restart" in routing_keywords
    assert "reboot" in routing_keywords
    assert "power management" in description.lower()
