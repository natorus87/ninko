from agents.base_agent import BaseAgent, _t
from .tools import (
    get_fritz_devices,
    get_fritz_wan_status,
    get_fritz_bandwidth,
    get_fritz_wlan_status,
    set_fritz_wlan_state,
    set_fritz_guest_wlan_state,
    get_fritz_smarthome_devices,
    set_fritz_smarthome_switch,
    set_fritz_smarthome_temperature,
    get_fritz_call_list,
    get_fritz_system_info,
    reboot_fritzbox,
)

class FritzBoxAgent(BaseAgent):
    """FritzBox specialist managing networks, WLAN, smart home and diagnostics."""

    def __init__(self):
        super().__init__(
            name="fritzbox",
            system_prompt=_t(
                "Du bist Ninko's FritzBox-Spezialist. Du verwaltest Netzwerke, "
                "WLAN-Verbindungen, Smart Home Geräte (DECT/AHA) und lieferst Diagnosen.\n\n"
                "WICHTIGE REGELN:\n"
                "1. Für ALLE Abfragen (Status, Geräte, WAN, etc.) und Aktionen (WLAN ein/aus, Temperatur, etc.) "
                "MUSST du das passende Tool aufrufen. Beschreibe NICHT was du tun würdest – tu es.\n"
                "2. Für destruktive Aktionen (Reboot, Netzwerk-Einstellungen ändern) frage kurz nach Bestätigung.\n"
                "3. Beim Einschalten/Ausschalten von WLAN oder Smart-Home-Geräten: direkt `set_fritz_wlan_state`, "
                "`set_fritz_guest_wlan_state` oder `set_fritz_smarthome_switch` aufrufen – kein Zwischentext.\n"
                "4. Bei unklaren Anfragen: erst `get_fritz_devices` oder `get_fritz_smarthome_devices` aufrufen "
                "um den aktuellen Stand zu sehen, dann handeln.",
                "You are Ninko's FritzBox specialist. You manage networks, "
                "WLAN connections, smart home devices (DECT/AHA) and provide diagnostics.\n\n"
                "IMPORTANT RULES:\n"
                "1. For ALL queries (status, devices, WAN, etc.) and actions (WLAN on/off, temperature, etc.) "
                "you MUST call the appropriate tool. Do NOT describe what you would do — just do it.\n"
                "2. For destructive actions (reboot, changing network settings) ask for confirmation briefly.\n"
                "3. When enabling/disabling WLAN or smart home devices: directly call `set_fritz_wlan_state`, "
                "`set_fritz_guest_wlan_state` or `set_fritz_smarthome_switch` — no intermediate text.\n"
                "4. For unclear requests: first call `get_fritz_devices` or `get_fritz_smarthome_devices` "
                "to see the current state, then act.",
            ),
            tools=[
                get_fritz_devices,
                get_fritz_wan_status,
                get_fritz_bandwidth,
                get_fritz_wlan_status,
                set_fritz_wlan_state,
                set_fritz_guest_wlan_state,
                get_fritz_smarthome_devices,
                set_fritz_smarthome_switch,
                set_fritz_smarthome_temperature,
                get_fritz_call_list,
                get_fritz_system_info,
                reboot_fritzbox,
            ],
        )
