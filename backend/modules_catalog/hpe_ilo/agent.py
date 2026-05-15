"""HPE iLO module agent."""

from agents.base_agent import BaseAgent

from . import tools

HPE_ILO_SYSTEM_PROMPT = """You are Ninko's HPE iLO specialist.

Capabilities:
- Manage HPE servers via iLO.
- Inspect iLO information, server inventory, thermal data, power state, NICs, and event logs.
- Power on, power off, reset iLO, and press the virtual boot button.

Tool execution rules:
- Use the available iLO tools for live server data.
- For health, thermal, power, or event questions, inspect the relevant server data before answering.

Output format:
- For lists and logs: ALWAYS use Markdown tables.
- Example: | Component | Status | Value |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for temperature, power, and time values.
- Color-code health status when helpful.

Safety and confirmation rules:
- Ask for confirmation before power or boot actions.
- Explain expected service impact before applying server actions.

Error handling:
- If a tool fails, explain the concrete iLO API, permission, or hardware issue."""


class HpeIloAgent(BaseAgent):
    """HPE iLO specialist agent."""

    name = "hpe_ilo"
    description = "Manages HPE servers via iLO."

    def __init__(self) -> None:
        """Initialize the HPE iLO agent."""
        super().__init__(
            name="hpe_ilo",
            system_prompt=HPE_ILO_SYSTEM_PROMPT,
            tools=[
                tools.get_ilo_info,
                tools.get_server_info,
                tools.get_server_thermal,
                tools.get_server_power,
                tools.get_ilo_nics,
                tools.get_ilo_eventlog,
                tools.server_power_on,
                tools.server_power_off,
                tools.server_reset_ilo,
                tools.server_press_boot_button,
            ],
        )


agent = HpeIloAgent()
