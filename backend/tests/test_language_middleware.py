"""Tests for the canonical response-language rule injected by LanguageMiddleware."""

from __future__ import annotations

import pytest

from agents.middleware.base import MiddlewareContext
from agents.middleware.prompt import (
    CANONICAL_LANGUAGE_RULE_TEMPLATE,
    LanguageMiddleware,
    build_language_rule,
)


@pytest.mark.parametrize(
    "lang, expected_name",
    [
        ("de", "German"),
        ("en", "English"),
        ("fr", "French"),
        ("es", "Spanish"),
        ("it", "Italian"),
        ("pt", "Portuguese"),
        ("nl", "Dutch"),
        ("pl", "Polish"),
        ("ja", "Japanese"),
        ("zh", "Chinese"),
    ],
)
def test_build_language_rule_uses_canonical_template(lang: str, expected_name: str) -> None:
    rule = build_language_rule(lang)
    assert rule is not None
    assert rule == CANONICAL_LANGUAGE_RULE_TEMPLATE.format(language=expected_name)
    assert f"configured language: {expected_name}" in rule
    assert "technical identifiers" in rule


@pytest.mark.parametrize("lang", ["", "xx", "klingon", None])
def test_build_language_rule_unknown_lang_returns_none(lang) -> None:
    assert build_language_rule(lang) is None  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_language_middleware_appends_rule_for_german_user() -> None:
    middleware = LanguageMiddleware(lambda: "de")
    ctx = MiddlewareContext(
        agent_name="kubernetes",
        message="Wie geht es dem Cluster?",
        final_system_prompt="You are Ninko's Kubernetes specialist.",
    )

    await middleware.pre_process(ctx)

    assert "Response language:" in ctx.final_system_prompt
    assert "configured language: German" in ctx.final_system_prompt
    assert "technical identifiers" in ctx.final_system_prompt
    assert ctx.extra["language"] == "de"


@pytest.mark.asyncio
async def test_language_middleware_appends_rule_for_english_user() -> None:
    middleware = LanguageMiddleware(lambda: "en")
    ctx = MiddlewareContext(
        agent_name="kubernetes",
        final_system_prompt="You are Ninko's Kubernetes specialist.",
    )

    await middleware.pre_process(ctx)

    assert "configured language: English" in ctx.final_system_prompt
    assert ctx.extra["language"] == "en"


@pytest.mark.asyncio
async def test_language_middleware_does_not_overwrite_existing_prompt() -> None:
    middleware = LanguageMiddleware(lambda: "de")
    base_prompt = "You are a specialist agent.\n\nFollow your tool rules."
    ctx = MiddlewareContext(final_system_prompt=base_prompt)

    await middleware.pre_process(ctx)

    assert ctx.final_system_prompt.startswith(base_prompt)
    assert ctx.final_system_prompt.endswith(build_language_rule("de") or "")


@pytest.mark.asyncio
async def test_language_middleware_unknown_language_is_noop() -> None:
    middleware = LanguageMiddleware(lambda: "klingon")
    ctx = MiddlewareContext(final_system_prompt="Base.")

    await middleware.pre_process(ctx)

    assert ctx.final_system_prompt == "Base."
    assert "language" not in ctx.extra


@pytest.mark.asyncio
async def test_language_middleware_swallows_recoverable_get_language_errors() -> None:
    def _raise() -> str:
        raise ValueError("settings unavailable")

    middleware = LanguageMiddleware(_raise)
    ctx = MiddlewareContext(final_system_prompt="Base.")

    result = await middleware.pre_process(ctx)

    assert result.short_circuit is False
    assert ctx.final_system_prompt == "Base."
    assert "language" not in ctx.extra


@pytest.mark.asyncio
async def test_canonical_rule_text_is_english_regardless_of_target_language() -> None:
    """The instruction itself is English even when the target language is not.

    This is the entire point of PLAN.md Phase 2: a single canonical rule with
    a variable language slot, not ten translated variants.
    """
    de_rule = build_language_rule("de")
    ja_rule = build_language_rule("ja")
    assert de_rule is not None and ja_rule is not None
    assert "Answer in the user's configured language" in de_rule
    assert "Answer in the user's configured language" in ja_rule
    # No language-specific surface text leaks through
    assert "Antworte" not in de_rule
    assert "日本語" not in ja_rule
