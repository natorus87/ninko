"""Lenovo XClarity module agent."""

from agents.base_agent import BaseAgent

from . import tools

LENOVO_XCLARITY_SYSTEM_PROMPT = """You are Ninko's Lenovo XClarity specialist.

Capabilities:
- Manage Lenovo ThinkSystem and ThinkBlade servers via XClarity Administrator.
- List managed servers, chassis, storage enclosures, events, and firmware versions.
- Inspect server details, health, alerts, and power state.
- Power on, power off, restart, and identify servers.

Tool execution rules:
- Use the available XClarity tools for live hardware data.
- For server detail or health questions, inspect the specific server before answering.

Output format:
- For lists (Servers, Chassis, Storage, Events): ALWAYS use Markdown tables.
- Example: | Server | Status | Power | Health |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for numbers.
- Color-code health status when helpful.

Safety and confirmation rules:
- Ask for confirmation before power on, power off, or restart operations.
- Ask for confirmation before identifying a server with the locator LED.

Error handling:
- If a tool fails, explain the concrete XClarity API, permission, or hardware issue."""


class LenovoXClarityAgent(BaseAgent):
    """Lenovo XClarity specialist agent."""

    name = "lenovo_xclarity"
    description = (
        "Manages Lenovo ThinkSystem/ThinkBlade servers via XClarity Administrator."
    )

    def __init__(self) -> None:
        """Initialize the Lenovo XClarity agent."""
        super().__init__(
            name="lenovo_xclarity",
            system_prompt=LENOVO_XCLARITY_SYSTEM_PROMPT,
            tools=[
                tools.list_xclarity_servers,
                tools.get_xclarity_server_details,
                tools.list_xclarity_chassis,
                tools.list_xclarity_storage,
                tools.get_xclarity_server_health,
                tools.list_xclarity_events,
                tools.get_xclarity_firmware,
                tools.power_on_xclarity_server,
                tools.power_off_xclarity_server,
                tools.restart_xclarity_server,
                tools.identify_xclarity_server,
            ],
        )


agent = LenovoXClarityAgent()
