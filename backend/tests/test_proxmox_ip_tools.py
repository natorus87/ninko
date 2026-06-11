from __future__ import annotations

import importlib.util
from pathlib import Path

from core.tool_registry import ToolTier, get_tool_registry

TOOLS_PATH = Path(__file__).resolve().parents[1] / "modules_catalog" / "proxmox" / "tools.py"
SPEC = importlib.util.spec_from_file_location("proxmox_tools_for_test", TOOLS_PATH)
assert SPEC is not None
proxmox_tools = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(proxmox_tools)


def test_extract_qemu_agent_ips_filters_loopback_and_link_local() -> None:
    interfaces = [
        {
            "name": "lo",
            "ip-addresses": [
                {"ip-address": "127.0.0.1", "ip-address-type": "ipv4"},
            ],
        },
        {
            "name": "eth0",
            "ip-addresses": [
                {"ip-address": "192.168.10.25", "ip-address-type": "ipv4"},
                {"ip-address": "fe80::5054:ff:fe12:3456", "ip-address-type": "ipv6"},
            ],
        },
    ]

    assert proxmox_tools._extract_qemu_agent_ips(interfaces) == [
        {
            "interface": "eth0",
            "address": "192.168.10.25",
            "ip": "192.168.10.25",
            "family": "ipv4",
        }
    ]


def test_extract_qemu_agent_ips_strips_cidr_suffix() -> None:
    interfaces = [
        {
            "name": "eth0",
            "ip-addresses": [
                {"ip-address": "192.168.10.25/24", "ip-address-type": "ipv4"},
                {"ip-address": "2001:db8::5/64", "ip-address-type": "ipv6"},
            ],
        }
    ]

    assert proxmox_tools._extract_qemu_agent_ips(interfaces) == [
        {
            "interface": "eth0",
            "address": "192.168.10.25/24",
            "ip": "192.168.10.25",
            "family": "ipv4",
        },
        {
            "interface": "eth0",
            "address": "2001:db8::5/64",
            "ip": "2001:db8::5",
            "family": "ipv6",
        },
    ]


def test_extract_qemu_agent_ips_filters_ipv6_zone_id_link_local() -> None:
    interfaces = [
        {
            "name": "eth0",
            "ip-addresses": [
                {"ip-address": "fe80::1%eth0", "ip-address-type": "ipv6"},
            ],
        }
    ]

    assert proxmox_tools._extract_qemu_agent_ips(interfaces) == []


def test_extract_qemu_agent_ips_preserves_global_ipv6_zone_id() -> None:
    interfaces = [
        {
            "name": "eth0",
            "ip-addresses": [
                {"ip-address": "2001:db8::1%eth0", "ip-address-type": "ipv6"},
            ],
        }
    ]

    assert proxmox_tools._extract_qemu_agent_ips(interfaces) == [
        {
            "interface": "eth0",
            "address": "2001:db8::1%eth0",
            "ip": "2001:db8::1%eth0",
            "family": "ipv6",
        }
    ]


def test_extract_qemu_agent_ips_handles_malformed_input() -> None:
    interfaces = [
        None,
        {},
        {"name": "eth0"},
        {"name": "eth0", "ip-addresses": None},
        {"name": "eth0", "ip-addresses": []},
        {"name": "eth0", "ip-addresses": [None]},
        {"name": "eth0", "ip-addresses": [{}]},
        {"name": "eth0", "ip-addresses": [{"ip-address": "", "ip-address-type": "ipv4"}]},
        {"name": "eth0", "ip-addresses": [{"ip-address": "not.an.ip", "ip-address-type": "ipv4"}]},
        {"name": "eth0", "ip-addresses": [{"ip-address": "8.8.8.8", "ip-address-type": "ipv4"}]},
    ]

    result = proxmox_tools._extract_qemu_agent_ips(interfaces)
    assert result == [
        {
            "interface": "eth0",
            "address": "8.8.8.8",
            "ip": "8.8.8.8",
            "family": "ipv4",
        }
    ]


def test_extract_qemu_agent_ips_deduplicates_by_interface_ip_family() -> None:
    interfaces = [
        {
            "name": "eth0",
            "ip-addresses": [
                {"ip-address": "192.168.10.25", "ip-address-type": "ipv4"},
                {"ip-address": "192.168.10.25", "ip-address-type": "ipv4"},
            ],
        }
    ]

    assert proxmox_tools._extract_qemu_agent_ips(interfaces) == [
        {
            "interface": "eth0",
            "address": "192.168.10.25",
            "ip": "192.168.10.25",
            "family": "ipv4",
        }
    ]


def test_extract_lxc_interface_ips_supports_inet_and_inet6() -> None:
    interfaces = [
        {
            "name": "eth0",
            "inet": "10.0.0.5/24",
            "inet6": "2001:db8::5/64",
        }
    ]

    assert proxmox_tools._extract_lxc_interface_ips(interfaces) == [
        {
            "interface": "eth0",
            "address": "10.0.0.5/24",
            "ip": "10.0.0.5",
            "family": "ipv4",
        },
        {
            "interface": "eth0",
            "address": "2001:db8::5/64",
            "ip": "2001:db8::5",
            "family": "ipv6",
        },
    ]


def test_parse_proxmox_net_config_extracts_static_ips_only() -> None:
    config = {
        "net0": "name=eth0,bridge=vmbr0,ip=192.168.1.44/24,gw=192.168.1.1",
        "net1": "name=eth1,bridge=vmbr1,ip=dhcp,ip6=auto",
        "net2": "virtio=AA:BB:CC:DD:EE:FF,bridge=vmbr2,ip6=2001:db8::44/64",
    }

    assert proxmox_tools._parse_proxmox_net_config(config) == [
        {
            "interface": "net0",
            "address": "192.168.1.44/24",
            "ip": "192.168.1.44",
            "family": "ipv4",
        },
        {
            "interface": "net2",
            "address": "2001:db8::44/64",
            "ip": "2001:db8::44",
            "family": "ipv6",
        },
    ]


def test_proxmox_ip_tools_are_registered_readonly() -> None:
    registry = get_tool_registry()
    for name in (
        "get_node_ip_addresses",
        "list_node_ip_addresses",
        "get_vm_ip_addresses",
        "list_vm_ip_addresses",
    ):
        assert registry.is_readonly(name) is True
        assert registry.tier_of(name) == ToolTier.READONLY
