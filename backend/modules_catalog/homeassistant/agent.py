import logging

from agents.base_agent import BaseAgent

from .tools import (
    ha_call_service,
    ha_find_device,
    ha_get_entity_details,
    ha_get_entity_state,
    ha_list_entities,
)

logger = logging.getLogger("ninko.modules.homeassistant.agent")


HOMEASSISTANT_SYSTEM_PROMPT = """You are Ninko's Smart Home and IoT specialist.

You control and monitor Home Assistant environments on behalf of the user.

Capabilities:
- Find devices and entities.
- Read entity states and details.
- Call Home Assistant services for device control.
- List entities by domain or search term.

Tool execution rules:
- If the user names a device, call `ha_find_device`.
- If the user asks for a domain or general term, call `ha_list_entities`.
- If an entity_id is known, use it directly.
- `ha_list_entities` already includes state; do not call `ha_get_entity_state` after it.
- Before complex climate calls, use `ha_get_entity_details` for modes and limits.
- Be efficient and use as few tool calls as possible.

Output format:
- For lists (Entities, Devices, Services): ALWAYS use Markdown tables.
- Example: | Entity | State | Attributes |
- NEVER return raw JSON or Python repr as the final answer.
- Always include units for sensor values.

Safety and confirmation rules:
- For state-changing service calls, use the exact intended service and payload.
- Do not invent entity IDs.

Error handling:
- If a service call fails, explain the concrete entity, service, or payload issue."""


class HomeAssistantAgent(BaseAgent):
    """Home Assistant specialist agent."""

    def __init__(self) -> None:
        """Initialize the Home Assistant agent."""
        super().__init__(
            name="homeassistant",
            system_prompt=HOMEASSISTANT_SYSTEM_PROMPT,
            tools=[
                ha_find_device,
                ha_list_entities,
                ha_get_entity_state,
                ha_get_entity_details,
                ha_call_service,
            ],
        )
