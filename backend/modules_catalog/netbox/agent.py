"""NetBox module agent."""

from agents.base_agent import BaseAgent
from modules_catalog.netbox import tools

NETBOX_SYSTEM_PROMPT = """You are Ninko's NetBox DCIM/IPAM specialist.

Capabilities:
- Query sites, devices, racks, circuits, cables, clusters, and interfaces.
- Analyze VLANs, prefixes, and IP addresses.
- Support network documentation and inventory questions.

Tool execution rules:
- Use the available NetBox tools to query and analyze NetBox data.
- Inspect the relevant site, device, rack, or IPAM resource before answering details.

Output format:
- For lists (Devices, IPs, VLANs, Circuits): ALWAYS use Markdown tables.
- Example: | Name | Status | Type | IP |
- NEVER return raw JSON or Python repr as the final answer.
- Always include units for numbers.
- Color-code status when helpful.

Safety and confirmation rules:
- Do not invent inventory state. Only report tool-returned data.

Error handling:
- If a tool fails, explain the concrete NetBox API, permission, or object issue."""


class NetboxAgent(BaseAgent):
    """NetBox DCIM and IPAM specialist agent."""

    name = "netbox"
    description = {
        "de": "NetBox DCIM & IPAM – Devices, Circuits, IP-Adresses, VLANs, Rack-Management",
        "en": "NetBox DCIM & IPAM – Devices, Circuits, IP-Adresses, VLANs, Rack-Management",
        "fr": "NetBox DCIM & IPAM – Appareils, Circuits, Adresses IP, VLANs, Gestion de racks",
        "es": (
            "NetBox DCIM & IPAM – Dispositivos, Circuitos, Direcciones IP, "
            "VLANs, Gestión de racks"
        ),
        "it": "NetBox DCIM & IPAM – Dispositivi, Circuiti, Indirizzi IP, VLAN, Gestione rack",
        "nl": "NetBox DCIM & IPAM – Apparaten, Circuits, IP-adressen, VLANs, Rack-beheer",
        "pl": "NetBox DCIM & IPAM – Urządzenia, Obwody, Adresy IP, VLANy, Zarządzanie rackami",
        "pt": "NetBox DCIM & IPAM – Dispositivos, Circuits, Endereços IP, VLANs, Gestão de racks",
        "ja": "NetBox DCIM & IPAM – デバイス、サーキッツ、IPアドレス、VLAN、ラック管理",
        "zh": "NetBox DCIM与IPAM – 设备、电路、IP地址、VLAN、机柜管理",
    }

    def __init__(self) -> None:
        """Initialize the NetBox agent."""
        super().__init__(
            name="netbox",
            system_prompt=NETBOX_SYSTEM_PROMPT,
            tools=[
                tools.get_netbox_status,
                tools.list_netbox_sites,
                tools.get_netbox_site,
                tools.list_netbox_devices,
                tools.get_netbox_device,
                tools.list_netbox_racks,
                tools.get_netbox_rack,
                tools.list_netbox_vlans,
                tools.list_netbox_prefixes,
                tools.list_netbox_ip_addresses,
                tools.list_netbox_circuits,
                tools.list_netbox_cables,
                tools.list_netbox_clusters,
                tools.get_netbox_device_interfaces,
            ],
        )


agent = NetboxAgent()
