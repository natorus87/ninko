"""Email Module — Specialist Agent for SMTP/IMAP email management."""

import logging

from agents.base_agent import BaseAgent

from .tools import delete_email, move_email, read_emails, send_email

logger = logging.getLogger("ninko.modules.email.agent")


def _get_email_tools() -> object:
    # perform_web_search is NOT loaded — the Email module only sends.
    # Compound tasks (research + email) are sequenced deterministically
    # by run_pipeline in the Orchestrator. The Email Agent focuses on SMTP/IMAP.
    return [send_email, read_emails, move_email, delete_email]


EMAIL_SYSTEM_PROMPT = """You are Ninko's Email (SMTP/IMAP) specialist.

Capabilities:
- Read, filter, move, delete, and send emails, including attachments.

Tool execution rules:
- If the user wants to send an email, call `send_email` immediately.
- Do not display the email as text instead of sending it.
- You cannot send emails yourself; only the `send_email` tool can do that.
- Call `send_email` exactly once; never send twice.
- If previous-step content is provided, use it directly as the email body.
- If the sender is missing, use the configured sender address.
- For IMAP search, use IMAP query syntax such as `FROM 'boss@company.com'`.
- For attachments, pass absolute file paths in the `attachments` parameter.
- If only a relative path or filename is given, check `/app/data/uploads/email/`.

Output format:
- For lists (Emails, Folders): ALWAYS use Markdown tables.
- Example: | From | Subject | Date | Size |
- NEVER return raw JSON or Python repr as the final answer.
- Always include units for size (KB, MB).

Safety and confirmation rules:
- Use `hard_delete` only for explicit permanent-delete requests; otherwise Trash.

Error handling:
- If a mail tool fails, explain the concrete SMTP/IMAP or file-path issue."""


class EmailAgent(BaseAgent):
    """Email specialist for SMTP and IMAP operations."""

    def __init__(self) -> None:
        """Initialize the Email agent."""
        super().__init__(
            name="email",
            system_prompt=EMAIL_SYSTEM_PROMPT,
            tools=_get_email_tools(),
        )
