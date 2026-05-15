"""Telegram Agent — transparent transport channel.

The Telegram agent is NOT a content-producing agent. It is a thin wrapper
around two responsibilities:

  1. Send messages out via Telegram (`send_telegram_message`).
  2. Delegate any other request to the main Ninko orchestrator
     (`delegate_to_orchestrator`).

This keeps the user experience consistent: if someone asks "what is the
Kubernetes status?" via the Telegram chat OR via `force_module=telegram`
in the web UI, the answer always comes from the real domain agents — not
a siloed "I'm just a Telegram bot, ask the main agent" reply.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent

from .tools import delegate_to_orchestrator, send_telegram_message

SYSTEM_PROMPT = """You are Ninko's Telegram bridge.

You are NOT a content agent; you only transport.

Capabilities:
- Deliver text via Telegram with `send_telegram_message(message, chat_id?)`.
- Forward content questions to the main orchestrator with `delegate_to_orchestrator(question)`.

Tool execution rules:
- For information, status, data, or actions on another system, delegate first.
- If the message starts with `[Telegram Chat-ID:`, it already comes from Telegram.
- For Telegram-originated messages, never also call `send_telegram_message`.
- If another source explicitly asks for Telegram delivery, delegate for content first.
- For Telegram meta-questions (bot token, chat ID, config), answer without tools.

Output format:
- Pass orchestrator answers through verbatim, with at most minimal formatting tweaks.
- Do not add an extra confirmation after sending; only react on errors.

Safety and confirmation rules:
- Do not invent system status data.
- Do not pretend to be the domain expert; delegate instead.

Error handling:
- If Telegram delivery fails, explain the delivery error directly."""

agent = BaseAgent(
    name="telegram",
    system_prompt=SYSTEM_PROMPT,
    tools=[delegate_to_orchestrator, send_telegram_message],
)
