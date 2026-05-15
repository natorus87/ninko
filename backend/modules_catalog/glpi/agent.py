"""GLPI module specialist agent.

Integrates with Kubernetes module via Redis PubSub events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from contextlib import suppress

from agents.base_agent import BaseAgent
from core.redis_client import get_redis

from .tools import (
    add_followup,
    add_solution,
    add_watcher,
    assign_ticket,
    close_ticket,
    create_ticket,
    get_ticket,
    get_ticket_attachments,
    get_ticket_followups,
    get_ticket_image_ocr,
    get_ticket_solutions,
    get_ticket_stats,
    list_categories,
    list_groups,
    search_tickets,
    search_users,
    update_ticket,
)

logger = logging.getLogger("ninko.modules.glpi.agent")

# Configurable default watcher for new tickets (env var, default: "Sophy").
_GLPI_DEFAULT_WATCHER = os.getenv("GLPI_DEFAULT_WATCHER", "Sophy")

GLPI_SYSTEM_PROMPT = f"""You are Ninko's GLPI Helpdesk specialist.

Capabilities:
- Ticket creation and management
- Ticket search by status, priority, keyword
- Retrieve follow-ups, solutions, and attachments
- OCR on ticket images (screenshots/photos)
- Closing tickets with resolution descriptions
- User and group search
- Ticket statistics
- Add watchers to tickets (add_watcher)
- Assign tickets (assign_ticket)

Tool execution rules:
- ALWAYS call the appropriate tool directly; do not describe what you would do.
- If all required info is present, call `create_ticket` immediately.
- If priority or category is missing, ask briefly, then call `create_ticket`.

Output format:
- For lists (Tickets, Computers, Users, Items): ALWAYS use Markdown tables
- Example: | ID | Title | Status | Assignee |
- NEVER return raw JSON or Python repr as the final answer
- Always include units for numbers
- Color-code status when helpful

IMPORTANT - Handling NEW tickets (Status=NEW):
1. First search for user "{_GLPI_DEFAULT_WATCHER}" with search_users("{_GLPI_DEFAULT_WATCHER}")
2. Add {_GLPI_DEFAULT_WATCHER} as watcher with add_watcher(ticket_id, watcher_user_id)
3. Write a helpful response/followup with add_followup()
4. Set status to "Pending" (4) with update_ticket(status=4)
5. DO NOT close immediately - wait for user response first!

Behavior rules:
- Create tickets with clear, meaningful titles
- ALWAYS call the appropriate tool directly — do not describe what you would do
- If all required info is present: call `create_ticket` immediately, do not ask again
- If priority/category is missing: ask briefly, then call `create_ticket` immediately
- Show ticket details in a clear format
- Use color indicators for priorities:
  🔴 Very high/Critical, 🟠 High, 🟡 Medium, 🟢 Low
- Link to GLPI when possible

Priorities:
1 = Very low, 2 = Low, 3 = Medium, 4 = High, 5 = Very high, 6 = Critical

Status:
1 = New, 2 = In progress, 3 = Planned, 4 = Pending, 5 = Solved, 6 = Closed

Safety and confirmation rules:
- Do not close new tickets immediately; wait for the user's response first.

Error handling:
- If a tool fails, explain the concrete GLPI API, ticket, or permission issue."""


class GlpiAgent(BaseAgent):
    """GLPI Helpdesk specialist with Redis PubSub event listener."""

    def __init__(self) -> None:
        """Initialize the GLPI agent."""
        super().__init__(
            name="glpi",
            system_prompt=GLPI_SYSTEM_PROMPT,
            tools=[
                create_ticket,
                get_ticket,
                search_tickets,
                update_ticket,
                close_ticket,
                add_followup,
                add_solution,
                add_watcher,
                assign_ticket,
                search_users,
                list_groups,
                list_categories,
                get_ticket_stats,
                get_ticket_attachments,
                get_ticket_image_ocr,
                get_ticket_followups,
                get_ticket_solutions,
            ],
        )

        # Graceful shutdown event for event listener
        self._stop_event = asyncio.Event()

        # Auto-incident ticket creation
        auto_create = (
            os.environ.get("GLPI_AUTO_CREATE_INCIDENTS", "false").lower() == "true"
        )
        if auto_create:
            self._listener_task = asyncio.create_task(self._listen_for_incidents())
            logger.info("GLPI auto-incident creation enabled.")

    async def stop(self) -> None:
        """Stop the event listener gracefully."""
        self._stop_event.set()
        if hasattr(self, "_listener_task"):
            try:
                await asyncio.wait_for(self._listener_task, timeout=2.0)
            except TimeoutError:
                self._listener_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._listener_task
        logger.info("GLPI event listener stopped.")

    async def _listen_for_incidents(self) -> None:
        """Listen for Redis PubSub incident events.

        On incident_detected events: automatically creates a GLPI ticket.
        """
        redis = get_redis()
        pubsub = await redis.subscribe_events()

        logger.info("GLPI event listener started.")

        while not self._stop_event.is_set():
            try:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=True, timeout=1.0
                )

                if message and message.get("type") == "message":
                    try:
                        event = json.loads(message["data"])
                        await self._handle_event(event)
                    except json.JSONDecodeError:
                        pass

                # Check stop event with timeout instead of sleep
                with suppress(TimeoutError):
                    await asyncio.wait_for(self._stop_event.wait(), timeout=0.5)

            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                ImportError,
            ) as exc:
                logger.error("GLPI event listener error: %s", exc)
                await asyncio.sleep(5)

    async def _handle_event(self, event: dict) -> None:
        """Processes an incoming event."""
        event_type = event.get("event_type", "")
        severity = event.get("severity", "")

        if event_type == "incident_detected" and severity in ("critical", "high"):
            source = event.get("source_module", "unknown")
            data = event.get("data", {})

            error = data.get("error", data.get("namespace", "Error detected"))
            title = f"[Auto] {source.upper()} Incident: {error}"
            description = (
                f"Automatically created ticket by Ninko.\n\n"
                f"Source module: {source}\n"
                f"Severity: {severity}\n"
                f"Details:\n{json.dumps(data, ensure_ascii=False, indent=2)}"
            )

            priority = 5 if severity == "critical" else 4

            try:
                result = await create_ticket.ainvoke(
                    {
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "ticket_type": 1,  # Incident
                    }
                )
                logger.info(
                    "Auto-ticket created: %s → #%s",
                    title,
                    result.get("ticket_id", "?"),
                )
            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                OSError,
                ImportError,
            ) as exc:
                logger.error("Auto-ticket creation failed: %s", exc)
