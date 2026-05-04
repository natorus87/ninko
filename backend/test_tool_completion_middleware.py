"""Tests for agent tool completion validation."""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from langchain_core.messages import AIMessage, ToolMessage

from agents.middleware.base import MiddlewareContext
from agents.middleware.tool_completion import ToolCompletionValidationMiddleware


class TestToolCompletionValidationMiddleware(unittest.IsolatedAsyncioTestCase):
    async def test_blocks_licium_existing_notes_ingest_without_required_tool(self):
        middleware = ToolCompletionValidationMiddleware()
        ctx = MiddlewareContext(
            message="Lies meine bestehenden Notizen und ingeste sie ins Ninko-Wiki",
            agent_name="licium",
            response="Ich erstelle jetzt die Struktur und lese dann alle Notizen ein.",
            result={
                "messages": [
                    AIMessage(content="", tool_calls=[]),
                    ToolMessage(
                        content="tree output",
                        tool_call_id="call_1",
                        name="list_licium_tree",
                    ),
                    AIMessage(
                        content="Ich erstelle jetzt die Struktur und lese dann alle Notizen ein."
                    ),
                ]
            },
        )

        await middleware.post_process(ctx)

        self.assertIn("nicht als abgeschlossen", ctx.response)
        self.assertIn("ingest_existing_licium_notes", ctx.response)
        self.assertIn("list_licium_tree", ctx.response)

    async def test_allows_licium_existing_notes_ingest_with_required_tool(self):
        middleware = ToolCompletionValidationMiddleware()
        ctx = MiddlewareContext(
            message="Lies meine bestehenden Notizen und ingeste sie ins Ninko-Wiki",
            agent_name="licium",
            response="## Licium-Ingest abgeschlossen\nImportiert: 3",
            result={
                "messages": [
                    ToolMessage(
                        content="## Licium-Ingest abgeschlossen",
                        tool_call_id="call_1",
                        name="ingest_existing_licium_notes",
                    ),
                    AIMessage(content="## Licium-Ingest abgeschlossen\nImportiert: 3"),
                ]
            },
        )

        await middleware.post_process(ctx)

        self.assertEqual(ctx.response, "## Licium-Ingest abgeschlossen\nImportiert: 3")

    async def test_detects_executed_tool_from_tool_call_id_when_tool_message_has_no_name(self):
        middleware = ToolCompletionValidationMiddleware()
        ctx = MiddlewareContext(
            message="Lies meine bestehenden Notizen und ingeste sie ins Ninko-Wiki",
            agent_name="licium",
            response="## Licium-Ingest abgeschlossen\nImportiert: 3",
            result={
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "id": "call_1",
                                "name": "ingest_existing_licium_notes",
                                "args": {},
                            }
                        ],
                    ),
                    ToolMessage(
                        content="## Licium-Ingest abgeschlossen",
                        tool_call_id="call_1",
                    ),
                    AIMessage(content="## Licium-Ingest abgeschlossen\nImportiert: 3"),
                ]
            },
        )

        await middleware.post_process(ctx)

        self.assertEqual(ctx.response, "## Licium-Ingest abgeschlossen\nImportiert: 3")

    async def test_blocks_future_commitment_after_read_tool_without_write_tool(self):
        middleware = ToolCompletionValidationMiddleware()
        ctx = MiddlewareContext(
            message="Bitte richte das Wiki ein",
            agent_name="licium",
            response="Ich werde jetzt die Wiki-Struktur erstellen.",
            result={
                "messages": [
                    ToolMessage(
                        content="meta output",
                        tool_call_id="call_1",
                        name="get_licium_wiki_meta",
                    ),
                    AIMessage(content="Ich werde jetzt die Wiki-Struktur erstellen."),
                ]
            },
        )

        await middleware.post_process(ctx)

        self.assertIn("nächsten Schritt angekündigt", ctx.response)


if __name__ == "__main__":
    unittest.main()
