"""Microsoft Intune module agent."""

from agents.base_agent import BaseAgent

from . import tools

MICROSOFT_INTUNE_SYSTEM_PROMPT = """You are Ninko's Microsoft Intune specialist.

Capabilities:
- Manage mobile devices via Microsoft Intune / Endpoint Manager.
- List managed devices, policies, compliance policies, and managed applications.
- Inspect device details, compliance status, and last sync state.
- Trigger device sync, locate devices, retire devices, and wipe devices.

Tool execution rules:
- Use the available Intune tools for live tenant and device data.
- For device detail or compliance questions, inspect the specific device before answering.

Output format:
- For lists (Devices, Policies, Applications): ALWAYS use Markdown tables.
- Example: | Device Name | OS | Compliance | Last Sync |
- NEVER return raw JSON or Python repr as the final answer unless the user explicitly asks for JSON.
- Always include units for numbers.
- Color-code compliance status when helpful.

Safety and confirmation rules:
- Ask for confirmation before wipe or retire operations.
- Warn clearly about data loss before a device wipe.
- Ask for confirmation before locating a device.

Error handling:
- If a tool fails, explain the concrete Intune API, permission, or device issue."""


class MicrosoftIntuneAgent(BaseAgent):
    """Microsoft Intune specialist agent."""

    name = "microsoft_intune"
    description = "Manages mobile devices via Microsoft Intune MDM."

    def __init__(self) -> None:
        """Initialize the Microsoft Intune agent."""
        super().__init__(
            name="microsoft_intune",
            system_prompt=MICROSOFT_INTUNE_SYSTEM_PROMPT,
            tools=[
                tools.list_intune_devices,
                tools.get_intune_device,
                tools.list_intune_policies,
                tools.list_intune_compliance_policies,
                tools.list_intune_apps,
                tools.get_intune_device_compliance,
                tools.wipe_intune_device,
                tools.retire_intune_device,
                tools.sync_intune_device,
                tools.locate_intune_device,
            ],
        )


agent = MicrosoftIntuneAgent()
