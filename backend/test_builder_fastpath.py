from __future__ import annotations

import unittest

from agents.orchestrator import OrchestratorAgent, RoutingConfig


class BuilderIntentDetectionTest(unittest.TestCase):
    def test_agent_create_intent_vs_howto(self) -> None:
        self.assertTrue(
            OrchestratorAgent._wants_agent_creation(
                "Erstelle bitte einen Agenten für Kubernetes Incidents."
            )
        )
        self.assertTrue(
            OrchestratorAgent._wants_agent_creation(
                "create an agent for email triage"
            )
        )
        self.assertFalse(
            OrchestratorAgent._wants_agent_creation(
                "Wie erstelle ich einen Agenten in Ninko?"
            )
        )

    def test_workflow_create_intent_vs_howto(self) -> None:
        self.assertTrue(
            OrchestratorAgent._wants_workflow_creation(
                "Erstelle einen Workflow für Backup + Healthcheck."
            )
        )
        self.assertTrue(
            OrchestratorAgent._wants_workflow_creation(
                "build workflow for nightly reports"
            )
        )
        self.assertFalse(
            OrchestratorAgent._wants_workflow_creation(
                "How to create a workflow with conditions?"
            )
        )


class BuilderFastPathRouteTest(unittest.IsolatedAsyncioTestCase):
    async def test_route_uses_agent_fastpath(self) -> None:
        agent = object.__new__(OrchestratorAgent)
        agent._refresh_routing_map = lambda: None

        async def _load_cfg(session_id: str = "") -> RoutingConfig:
            return RoutingConfig()

        async def _auto_create_custom_agent(message: str, session_id: str):
            return "agent-created", False

        agent._load_routing_config = _load_cfg
        agent._proactive_routing_adjust = lambda session_id, message, chat_history, cfg: cfg
        agent._wants_agent_creation = lambda message: True
        agent._wants_workflow_creation = lambda message: False
        agent._auto_create_custom_agent = _auto_create_custom_agent

        response, module, did_compact = await OrchestratorAgent.route(
            agent,
            message="Erstelle einen Agenten für Linux Monitoring",
            chat_history=[],
            session_id="test-session",
        )

        self.assertEqual(response, "agent-created")
        self.assertEqual(module, "orchestrator")
        self.assertFalse(did_compact)

    async def test_route_uses_workflow_fastpath(self) -> None:
        agent = object.__new__(OrchestratorAgent)
        agent._refresh_routing_map = lambda: None

        async def _load_cfg(session_id: str = "") -> RoutingConfig:
            return RoutingConfig()

        async def _auto_create_workflow(message: str, session_id: str):
            return "workflow-created", False

        agent._load_routing_config = _load_cfg
        agent._proactive_routing_adjust = lambda session_id, message, chat_history, cfg: cfg
        agent._wants_agent_creation = lambda message: False
        agent._wants_workflow_creation = lambda message: True
        agent._auto_create_workflow = _auto_create_workflow

        response, module, did_compact = await OrchestratorAgent.route(
            agent,
            message="Erstelle einen Workflow für Deploy und Rollback",
            chat_history=[],
            session_id="test-session",
        )

        self.assertEqual(response, "workflow-created")
        self.assertEqual(module, "orchestrator")
        self.assertFalse(did_compact)


if __name__ == "__main__":
    unittest.main()
