from agents.base_agent import BaseAgent
from modules.fritzbox.tools import (
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
    def __init__(self):
        super().__init__(
            name="fritzbox",
            system_prompt=(
                "Du bist Ninko's FritzBox-Spezialist. Du verwaltest Netzwerke, "
                "WLAN-Verbindungen, Smart Home Geräte (DECT/AHA) und lieferst Diagnosen.\n\n"
                "WICHTIGE REGELN:\n"
                "1. Für ALLE Abfragen (Status, Geräte, WAN, etc.) und Aktionen (WLAN ein/aus, Temperatur, etc.) "
                "MUSST du das passende Tool aufrufen. Beschreibe NICHT was du tun würdest – tu es.\n"
                "2. Für destruktive Aktionen (Reboot, Netzwerk-Einstellungen ändern) frage kurz nach Bestätigung.\n"
                "3. Beim Einschalten/Ausschalten von WLAN oder Smart-Home-Geräten: direkt `set_fritz_wlan_state`, "
                "`set_fritz_guest_wlan_state` oder `set_fritz_smarthome_switch` aufrufen – kein Zwischentext.\n"
                "4. Bei unklaren Anfragen: erst `get_fritz_devices` oder `get_fritz_smarthome_devices` aufrufen "
                "um den aktuellen Stand zu sehen, dann handeln."
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
