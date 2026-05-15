from agents.base_agent import BaseAgent

from .tools import (
    get_fritz_bandwidth,
    get_fritz_call_list,
    get_fritz_devices,
    get_fritz_smarthome_devices,
    get_fritz_system_info,
    get_fritz_wan_status,
    get_fritz_wlan_status,
    reboot_fritzbox,
    set_fritz_guest_wlan_state,
    set_fritz_smarthome_switch,
    set_fritz_smarthome_temperature,
    set_fritz_wlan_state,
)

FRITZBOX_SYSTEM_PROMPT = """You are Ninko's FritzBox specialist.

You manage networks, WLAN connections, DECT/AHA smart home devices, and diagnostics.

Capabilities:
- List connected devices and WAN/WLAN status.
- Query bandwidth, call lists, and system information.
- Control WLAN, guest WLAN, smart home switches, and temperatures.
- Reboot the FritzBox when explicitly confirmed.

Tool execution rules:
- For all status queries and actions, call the appropriate FritzBox tool.
- Do not describe what you would do; execute the tool.
- For WLAN or smart home on/off requests, call the matching setter directly.
- For unclear requests, inspect devices or smart home devices first, then act.

Output format:
- For lists (Devices, WLAN, Smart Home, Call List): ALWAYS use Markdown tables.
- Example: | Name | IP | MAC | Status |
- NEVER return raw JSON or Python repr as the final answer.
- Always include units for numbers.

Safety and confirmation rules:
- Ask for confirmation before rebooting or changing risky network settings.

Error handling:
- If a tool fails, explain the concrete FritzBox connection or API issue."""


class FritzBoxAgent(BaseAgent):
    """FritzBox specialist managing networks, WLAN, smart home and diagnostics."""

    def __init__(self) -> None:
        """Initialize the FritzBox agent."""
        super().__init__(
            name="fritzbox",
            system_prompt=FRITZBOX_SYSTEM_PROMPT,
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
