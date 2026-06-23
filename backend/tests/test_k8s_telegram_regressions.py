from types import SimpleNamespace

from agents.base_agent import BaseAgent
from agents.orchestrator import OrchestratorAgent
from core.safeguard import ActionCategory, SafeguardMiddleware, _keyword_prefilter


def _find_tasmota_devices() -> str:
    """Find Tasmota devices through a FRITZ!Box discovery query."""
    return "[]"


def test_jit_tool_selection_accepts_plain_callable_tools(monkeypatch):
    monkeypatch.setattr("agents.base_agent._get_jit_threshold", lambda: 0)
    monkeypatch.setattr("agents.base_agent._get_jit_max_tools", lambda: 5)

    agent = BaseAgent.__new__(BaseAgent)
    agent.name = "fritzbox"
    agent.tools = [_find_tasmota_devices]

    selected = BaseAgent._select_tools_for_request(
        agent, "Benutze FRITZ!Box, um alle Tasmota Geraete zu finden"
    )

    assert selected == [_find_tasmota_devices]


def test_german_find_request_is_safe_without_classifier():
    middleware = SafeguardMiddleware.__new__(SafeguardMiddleware)

    result = middleware._fast_prefilter_short(
        "Benutze FRITZ!Box, um alle Tasmota Geräte zu finden"
    )

    assert result is not None
    assert result["category"] is ActionCategory.SAFE


def test_readonly_prefilter_does_not_hide_destructive_followup():
    result = _keyword_prefilter("Finde alle Testgeräte und lösche sie")

    assert result.hit is True
    assert result.category is ActionCategory.DESTRUCTIVE


async def test_fritzbox_tasmota_fast_path_filters_devices(monkeypatch):
    async def fake_ainvoke(payload):
        assert payload == {"connection_id": ""}
        return [
            {
                "name": "tasmota-steckdose-01",
                "ip": "192.168.178.40",
                "mac": "AA:BB:CC:DD:EE:01",
                "status": "Online",
                "interface": "WLAN",
            },
            {
                "name": "printer",
                "ip": "192.168.178.41",
                "mac": "AA:BB:CC:DD:EE:02",
                "status": "Online",
                "interface": "LAN",
            },
        ]

    fake_tool = SimpleNamespace(name="get_fritz_devices", ainvoke=fake_ainvoke)
    fake_agent = SimpleNamespace(tools=[fake_tool])

    class FakeRegistry:
        def get_agent(self, module_id):
            return fake_agent if module_id == "fritzbox" else None

    orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
    orchestrator.registry = FakeRegistry()
    response, module, did_compact, _summary = await orchestrator._try_fritzbox_tasmota_fast_path(
        "Benutze FRITZ!Box, um alle Tasmota Geräte zu finden",
        "test-session",
    )

    assert module == "fritzbox"
    assert did_compact is False
    assert "tasmota-steckdose-01" in response
    assert "printer" not in response


async def test_react_fallback_returns_user_facing_llm_error(monkeypatch):
    async def fake_emit_trace(*args, **kwargs):
        return None

    async def fake_invoke(*args, **kwargs):
        raise ConnectionError("All connection attempts failed")

    monkeypatch.setattr("agents.orchestrator.status_bus.emit_trace", fake_emit_trace)

    orchestrator = OrchestratorAgent.__new__(OrchestratorAgent)
    orchestrator.name = "orchestrator"
    orchestrator.invoke = fake_invoke

    response, module, did_compact, _meta = await orchestrator._fallback_to_react_loop(
        message="Hallo",
        chat_history=[],
        session_id="telegram_test",
        confirmed=False,
    )

    assert module is None
    assert did_compact is False
    assert "KI-Backend" in response
