"""Regression tests for canonical-English system prompts in BaseAgent.

PLAN.md item 2.2: All system prompts sent to the LLM must be plain ``str`` in
English, not ``_t(de=..., en=...)`` wrappers. The response language is injected
centrally by ``LanguageMiddleware`` at render time, so per-language drift in the
prompt itself is a bug.

These tests guard three sites in ``agents/base_agent.py``:

* ``_dynamic_prompt_appendix`` — connection list baked into the system prompt
* ``_auto_memorize`` — JSON fact-extraction prompt sent to the LLM
* ``_LANG_INSTRUCTIONS`` — dead code that was removed in PLAN.md item 2.2
"""

from __future__ import annotations

from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from agents.base_agent import BaseAgent


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _make_connection(
    *,
    id: str = "conn-1",
    name: str = "Production",
    environment: str = "prod",
    is_default: bool = False,
):
    """Return a minimal stand-in for ``ConnectionRead`` with the four fields
    that ``_dynamic_prompt_appendix`` reads.
    """
    conn = MagicMock()
    conn.id = id
    conn.name = name
    conn.environment = environment
    conn.is_default = is_default
    return conn


def _build_agent(stack: ExitStack) -> BaseAgent:
    """Construct a BaseAgent bypassing the real LLM, memory, and LangGraph.

    ``BaseAgent.__init__`` wires up a Chroma client, an LLM HTTP client, and a
    LangGraph ReAct agent. None of those are needed for the prompt-content
    assertions below, so we patch them all with cheap mocks for the duration
    of the test.
    """
    mock_memory = MagicMock()
    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(
        return_value=MagicMock(content='{"fact": "x", "importance": 0.5}')
    )
    mock_context_mgr = MagicMock()

    # Tools list is empty; create_react_agent just has to be importable.
    stack.enter_context(patch("agents.base_agent.get_memory", return_value=mock_memory))
    stack.enter_context(patch("agents.base_agent.get_llm", return_value=mock_llm))
    stack.enter_context(
        patch("agents.base_agent.get_llm_generation", return_value=0)
    )
    stack.enter_context(
        patch(
            "agents.base_agent.get_context_manager", return_value=mock_context_mgr
        )
    )
    stack.enter_context(
        patch("agents.base_agent.wrap_tools_with_sanitizer", lambda tools: tools)
    )
    stack.enter_context(
        patch(
            "agents.base_agent.create_react_agent", lambda model, tools: MagicMock()
        )
    )

    return BaseAgent(name="kubernetes", system_prompt="You are a k8s specialist.")


# ─────────────────────────────────────────────────────────────────────────────
# Group 1: _dynamic_prompt_appendix is canonical English
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_dynamic_prompt_appendix_uses_english_header_with_connections() -> None:
    """With one connection, the appendix must start with the English header."""
    with ExitStack() as stack:
        agent = _build_agent(stack)
        conn = _make_connection()
        stack.enter_context(
            patch(
                "core.connections.ConnectionManager.list_connections",
                AsyncMock(return_value=[conn]),
            )
        )

        appendix = await agent._dynamic_prompt_appendix()

    assert "AVAILABLE CONNECTIONS FOR THIS MODULE" in appendix
    assert "VERFÜGBARE VERBINDUNGEN" not in appendix


@pytest.mark.asyncio
async def test_dynamic_prompt_appendix_marks_default_connection() -> None:
    """Default connections get the [DEFAULT] suffix in the prompt."""
    with ExitStack() as stack:
        agent = _build_agent(stack)
        default_conn = _make_connection(is_default=True)
        stack.enter_context(
            patch(
                "core.connections.ConnectionManager.list_connections",
                AsyncMock(return_value=[default_conn]),
            )
        )

        appendix = await agent._dynamic_prompt_appendix()

    assert "[DEFAULT]" in appendix
    assert "connection_id: 'conn-1'" in appendix
    assert "Name: 'Production'" in appendix
    assert "Env: 'prod'" in appendix


@pytest.mark.asyncio
async def test_dynamic_prompt_appendix_emits_english_footer() -> None:
    """The closing instruction line must be the canonical English variant."""
    with ExitStack() as stack:
        agent = _build_agent(stack)
        conn = _make_connection()
        stack.enter_context(
            patch(
                "core.connections.ConnectionManager.list_connections",
                AsyncMock(return_value=[conn]),
            )
        )

        appendix = await agent._dynamic_prompt_appendix()

    assert "IMPORTANT: ALWAYS use the appropriate 'connection_id' for tools" in appendix
    assert "WICHTIG: Nutze IMMER" not in appendix
    assert "default connection" in appendix


@pytest.mark.asyncio
async def test_dynamic_prompt_appendix_is_empty_when_no_connections() -> None:
    with ExitStack() as stack:
        agent = _build_agent(stack)
        stack.enter_context(
            patch(
                "core.connections.ConnectionManager.list_connections",
                AsyncMock(return_value=[]),
            )
        )

        appendix = await agent._dynamic_prompt_appendix()

    assert appendix == ""


@pytest.mark.asyncio
async def test_dynamic_prompt_appendix_stays_english_under_german_settings() -> None:
    """Regression: even with LANGUAGE=de, the prompt must not contain German."""
    with ExitStack() as stack:
        agent = _build_agent(stack)
        conn = _make_connection()
        stack.enter_context(
            patch(
                "core.connections.ConnectionManager.list_connections",
                AsyncMock(return_value=[conn]),
            )
        )
        stack.enter_context(patch("agents.base_agent._get_language", return_value="de"))

        appendix = await agent._dynamic_prompt_appendix()

    assert "AVAILABLE CONNECTIONS" in appendix
    assert "VERFÜGBARE" not in appendix
    assert "WICHTIG" not in appendix


# ─────────────────────────────────────────────────────────────────────────────
# Group 2: _auto_memorize extraction prompt is canonical English
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_auto_memorize_prompt_uses_english_extraction_text_under_german_settings() -> None:
    """Even with LANGUAGE=de, the LLM-bound memorize prompt stays in English."""
    with ExitStack() as stack:
        agent = _build_agent(stack)
        # _make_agent gives the LLM a generic JSON; this test only inspects
        # what was *sent* to ainvoke, not the response parsing.
        stack.enter_context(patch("agents.base_agent._get_language", return_value="de"))

        await agent._auto_memorize("user says hi", "ai replies hi")

    sent_messages = agent._llm.ainvoke.call_args.args[0]
    prompt_text = sent_messages[0].content

    assert "Extract ONLY permanently relevant facts" in prompt_text
    assert "Extrahiere" not in prompt_text
    assert "Antworte NUR" not in prompt_text
    assert "Anwender" not in prompt_text
    assert "Assistent" not in prompt_text


@pytest.mark.asyncio
async def test_auto_memorize_prompt_preserves_json_schema_and_importance_scale() -> None:
    """The numeric JSON schema and importance scale must be intact in English."""
    with ExitStack() as stack:
        agent = _build_agent(stack)

        await agent._auto_memorize("user says hi", "ai replies hi")

    prompt_text = agent._llm.ainvoke.call_args.args[0][0].content
    assert '"fact"' in prompt_text
    assert '"importance": 0.5' in prompt_text
    assert "1.0 = critical" in prompt_text
    assert "0.5 = normal" in prompt_text
    assert "0.2 = trivial" in prompt_text
    assert '"NOTHING"' in prompt_text


@pytest.mark.asyncio
async def test_auto_memorize_prompt_inlines_user_and_ai_messages() -> None:
    """The memorize prompt must reference the user/AI input verbatim."""
    with ExitStack() as stack:
        agent = _build_agent(stack)

        long_ai = "x" * 2000  # > 800 char truncation threshold
        await agent._auto_memorize("hello there", long_ai)

    prompt_text = agent._llm.ainvoke.call_args.args[0][0].content
    assert "User: hello there" in prompt_text
    assert "Assistant:" in prompt_text
    # ai_response is truncated to 800 chars
    assert "x" * 800 in prompt_text
    assert "x" * 801 not in prompt_text


# ─────────────────────────────────────────────────────────────────────────────
# Group 3: _LANG_INSTRUCTIONS is gone (regression guard)
# ─────────────────────────────────────────────────────────────────────────────


def test_lang_instructions_removed_from_module() -> None:
    """The dead ``_LANG_INSTRUCTIONS`` dict must not reappear in base_agent."""
    import agents.base_agent as ba

    assert getattr(ba, "_LANG_INSTRUCTIONS", None) is None
