"""Template module specialist agent."""

from __future__ import annotations

import logging

from agents.base_agent import BaseAgent

from .tools import beispiel_tool, lade_daten

logger = logging.getLogger("ninko.modules.template.agent")

TEMPLATE_SYSTEM_PROMPT = """You are Ninko's Template specialist.

Capabilities:
- Run example operations via the module tools
- Load structured data for dashboards and analysis
- Explain clearly which configuration is missing when a tool fails

Tool execution rules:
- Use the available tools before responding when live module data is needed.

Output format:
- For lists: ALWAYS use Markdown tables.
- NEVER return raw JSON or Python repr as the final answer.

Safety and confirmation rules:
- Do not perform destructive actions without explicit confirmation.

Error handling:
- If a tool fails, explain the concrete configuration or runtime issue."""


class TemplateAgent(BaseAgent):
    """Template specialist with the template tools."""

    def __init__(self) -> None:
        super().__init__(
            # REQUIRED: module name must match manifest.name exactly.
            # Name MUSS dem manifest.name entsprechen
            name="template",
            system_prompt=TEMPLATE_SYSTEM_PROMPT,
            tools=[beispiel_tool, lade_daten],
        )
