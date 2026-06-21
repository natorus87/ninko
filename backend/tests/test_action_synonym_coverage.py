"""Regression tests for German action synonyms in module routing/JIT metadata."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


ACTION_SYNONYM_TARGETS: dict[str, dict[str, tuple[str, ...]]] = {
    "cisco": {
        "enable_cisco_interface": ("aktivieren", "einschalten"),
        "disable_cisco_interface": ("deaktivieren", "ausschalten"),
        "set_cisco_interface_vlan": ("setzen", "schalten"),
    },
    "docker": {
        "start_container": ("starten", "starte"),
        "stop_container": ("stoppen", "stoppe", "herunterfahren"),
        "restart_container": ("neustart", "neustarten", "neu starten"),
    },
    "fritzbox": {
        "set_fritz_wlan_state": ("aktivieren", "deaktivieren", "einschalten", "ausschalten"),
        "set_fritz_guest_wlan_state": ("aktivieren", "deaktivieren", "einschalten", "ausschalten"),
        "set_fritz_smarthome_switch": ("einschalten", "ausschalten", "schalten"),
        "set_fritz_smarthome_temperature": ("setzen", "temperatur setzen"),
        "reboot_fritzbox": ("neustart", "neustarten", "neu starten"),
    },
    "hpe_ilo": {
        "server_power_on": ("einschalten", "anschalten"),
        "server_power_off": ("ausschalten", "herunterfahren", "abschalten"),
        "server_reset_ilo": ("neustart", "reset", "zurücksetzen"),
    },
    "kubernetes": {
        "restart_pod": ("neustart", "neustarten", "neu starten"),
        "rollout_restart": ("neustart", "neustarten", "neu starten"),
    },
    "lenovo_xclarity": {
        "power_on_xclarity_server": ("einschalten", "anschalten"),
        "power_off_xclarity_server": ("ausschalten", "herunterfahren", "abschalten"),
        "restart_xclarity_server": ("neustart", "neustarten", "neu starten"),
    },
    "linux_server": {
        "reboot_server": ("neustart", "neustarten", "neu starten"),
        "confirm_reboot": ("neustart", "neustarten", "neu starten"),
    },
    "microsoft_entra": {
        "disable_entra_user": ("deaktivieren", "ausschalten"),
        "reset_entra_user_password": ("zurücksetzen", "zuruecksetzen", "reset"),
    },
    "microsoft_intune": {
        "sync_intune_device": ("synchronisieren", "sync"),
    },
    "mikrotik": {
        "enable_mikrotik_interface": ("aktivieren", "einschalten"),
        "disable_mikrotik_interface": ("deaktivieren", "ausschalten"),
        "reboot_mikrotik": ("neustart", "neustarten", "neu starten"),
    },
    "netgear": {
        "enable_netgear_port": ("aktivieren", "einschalten"),
        "disable_netgear_port": ("deaktivieren", "ausschalten"),
        "reboot_netgear": ("neustart", "neustarten", "neu starten"),
    },
    "opnsense": {
        "restart_opnsense_service": ("neustart", "neustarten", "neu starten"),
        "set_opnsense_interface": ("setzen", "schalten", "aktivieren", "deaktivieren"),
        "set_opnsense_dhcp": ("setzen", "aktivieren", "deaktivieren"),
    },
    "pihole": {
        "toggle_blocking": ("umschalten", "aktivieren", "deaktivieren"),
    },
    "proxmox": {
        "start_vm": ("starten", "starte"),
        "stop_vm": ("stoppen", "stoppe", "herunterfahren"),
        "reboot_vm": ("neustart", "neustarten", "neu starten"),
        "reset_vm": ("reset", "zurücksetzen", "zuruecksetzen"),
        "start_container": ("starten", "starte"),
        "stop_container": ("stoppen", "stoppe", "herunterfahren"),
        "reboot_container": ("neustart", "neustarten", "neu starten"),
    },
    "redmine": {
        "reset_redmine_user_password": ("zurücksetzen", "zuruecksetzen", "reset"),
    },
    "synology": {
        "restart_synology_service": ("neustart", "neustarten", "neu starten"),
        "shutdown_synologyNAS": ("herunterfahren", "abschalten", "ausschalten"),
        "reboot_synologyNAS": ("neustart", "neustarten", "neu starten"),
    },
    "tasmota": {
        "set_tasmota_power": ("einschalten", "ausschalten", "schalten"),
        "set_tasmota_group_power": ("einschalten", "ausschalten", "schalten"),
    },
    "ubiquiti": {
        "restart_ubiquiti_device": ("neustart", "neustarten", "neu starten"),
        "enable_ubiquiti_wlan": ("aktivieren", "einschalten"),
        "disable_ubiquiti_wlan": ("deaktivieren", "ausschalten"),
    },
}


def _module_dir(module: str) -> Path:
    catalog = ROOT / "modules_catalog" / module
    if catalog.exists():
        return catalog
    return ROOT / "modules" / module


def _tool_docstrings(module: str) -> dict[str, str]:
    tree = ast.parse((_module_dir(module) / "tools.py").read_text(encoding="utf-8"))
    docs: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        is_tool = False
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Name) and target.id == "tool":
                is_tool = True
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                is_tool = True
        if is_tool:
            docs[node.name] = ast.get_docstring(node) or ""
    return docs


def _manifest_text(module: str) -> str:
    tree = ast.parse((_module_dir(module) / "manifest.py").read_text(encoding="utf-8"))
    parts: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or getattr(node.func, "id", "") != "ModuleManifest":
            continue
        for keyword in node.keywords:
            if keyword.arg not in {"description", "routing_keywords"}:
                continue
            try:
                value = ast.literal_eval(keyword.value)
            except (ValueError, SyntaxError):
                continue
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value)
    return " ".join(parts).casefold()


def test_action_tools_include_german_synonyms_for_jit_selection() -> None:
    for module, tools in ACTION_SYNONYM_TARGETS.items():
        docs = _tool_docstrings(module)
        for tool_name, terms in tools.items():
            searchable = f"{tool_name} {docs[tool_name]}".casefold()
            missing = [term for term in terms if term not in searchable]
            assert not missing, f"{module}.{tool_name} misses JIT terms: {missing}"


def test_action_modules_include_german_synonyms_for_routing() -> None:
    for module, tools in ACTION_SYNONYM_TARGETS.items():
        searchable = _manifest_text(module)
        expected_terms = sorted({term for terms in tools.values() for term in terms})
        missing = [term for term in expected_terms if term not in searchable]
        assert not missing, f"{module} manifest misses routing terms: {missing}"
