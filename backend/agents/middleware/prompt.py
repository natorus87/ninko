"""Prompt enrichment middleware: soul, language, datetime, RAG, skills."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Any

import zoneinfo

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_LANG_INSTRUCTIONS = {
    "de": "Antworte ausschließlich auf Deutsch.",
    "en": "Respond exclusively in English.",
    "fr": "Réponds exclusivement en français.",
    "es": "Responde exclusivamente en español.",
    "it": "Rispondi esclusivamente in italiano.",
    "pt": "Responda exclusivamente em português.",
    "nl": "Antwoord uitsluitend in het Nederlands.",
    "pl": "Odpowiadaj wyłącznie po polsku.",
    "ru": "Отвечай исключительно на русском.",
    "tr": "Sadece Türkçe yanıtla.",
}

_WEEKDAYS_DE = [
    "Montag",
    "Dienstag",
    "Mittwoch",
    "Donnerstag",
    "Freitag",
    "Samstag",
    "Sonntag",
]
_WEEKDAYS_EN = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

_RECOVERABLE = (ImportError, AttributeError, TypeError, ValueError, RuntimeError)


class SoulInjectionMiddleware(BaseMiddleware):
    name = "soul_injection"
    priority = 100

    def __init__(self, get_soul_manager: Any):
        self._get_soul_manager = get_soul_manager

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        try:
            soul = self._get_soul_manager().get_soul(ctx.agent_name)
            if soul:
                ctx.final_system_prompt = soul + "\n\n---\n\n" + ctx.final_system_prompt
                logger.debug("Soul MD für Agent '%s' injiziert.", ctx.agent_name)
        except _RECOVERABLE as exc:
            logger.debug("Soul-Injection fehlgeschlagen (ignoriert): %s", exc)
        return MiddlewareResult()


class LanguageMiddleware(BaseMiddleware):
    name = "language"
    priority = 110

    def __init__(self, get_language: Any):
        self._get_language = get_language

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        try:
            lang = self._get_language()
            instruction = _LANG_INSTRUCTIONS.get(lang)
            if instruction:
                ctx.final_system_prompt += f"\n\n{instruction}"
        except (ImportError, AttributeError, TypeError, ValueError):
            pass
        return MiddlewareResult()


class DatetimeMiddleware(BaseMiddleware):
    name = "datetime"
    priority = 120

    def __init__(self, get_timezone: Any):
        self._get_timezone = get_timezone

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        try:
            tz_name = self._get_timezone()
            tz = zoneinfo.ZoneInfo(tz_name)
            now = datetime.now(tz)
            lang = ctx.extra.get("language", "en")

            if lang == "de":
                dt_str = (
                    f"Aktuelles Datum: {_WEEKDAYS_DE[now.weekday()]}, "
                    f"{now.day:02d}.{now.month:02d}.{now.year} | "
                    f"Uhrzeit: {now.strftime('%H:%M')} ({tz_name})"
                )
            else:
                dt_str = (
                    f"Current date: {_WEEKDAYS_EN[now.weekday()]}, "
                    f"{now.strftime('%B %d, %Y')} | "
                    f"Time: {now.strftime('%H:%M')} ({tz_name})"
                )
            ctx.final_system_prompt += f"\n\n{dt_str}"
        except _RECOVERABLE as exc:
            logger.debug("Datetime-Injection fehlgeschlagen (ignoriert): %s", exc)
        return MiddlewareResult()


class CompactionSummaryMiddleware(BaseMiddleware):
    name = "compaction_summary"
    priority = 130

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        seen: set[str] = set()
        for msg in ctx.trimmed_history:
            if msg.get("role") in ("system", "system_compaction"):
                content = msg.get("content", "")
                if content and content not in seen:
                    ctx.final_system_prompt += "\n\n" + content
                    seen.add(content)
        return MiddlewareResult()


class RAGMiddleware(BaseMiddleware):
    name = "rag"
    priority = 140

    def __init__(self, memory: Any):
        self._memory = memory

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        _RECOVERABLE = (
            ImportError,
            AttributeError,
            TypeError,
            ValueError,
            RuntimeError,
            Exception,
        )
        try:
            hits = await self._memory.search(query=ctx.message, top_k=3)
            relevant = [
                h for h in hits if h.get("distance") is None or h["distance"] < 0.5
            ]
            if relevant:
                rag_ctx = "\n\n".join(f"[Memory] {h['content']}" for h in relevant)
                ctx.final_system_prompt += (
                    "\n\n"
                    + ctx.extra.get(
                        "_t_rag_prefix", "Relevanter Kontext aus dem Memory:\n"
                    )
                    + rag_ctx
                )
        except _RECOVERABLE as exc:
            logger.debug("Memory-Suche fehlgeschlagen: %s", exc)
        return MiddlewareResult()


class KnowledgeGraphMiddleware(BaseMiddleware):
    name = "knowledge_graph"
    priority = 150

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        try:
            from core.knowledge_graph import get_knowledge_graph

            kg = await get_knowledge_graph()
            module_entity_id = f"module:{ctx.agent_name}"

            if module_entity_id in kg._graph:
                related = await kg.suggest_related(module_entity_id)
                if related:
                    kg_text = ctx.extra.get(
                        "_t_kg_prefix", "Related systems from Knowledge Graph:\n"
                    )
                    for item in related[:5]:
                        ent = item.get("entity", {})
                        reason = item.get("reason", "")
                        kg_text += f"- {ent.get('name', ent.get('id'))} ({reason})\n"
                    ctx.final_system_prompt += "\n\n" + kg_text

            incidents = await kg.find_by_type("incident")
            module_incidents = [
                i
                for i in incidents
                if i.get("properties", {}).get("module") == ctx.agent_name
            ]
            if module_incidents:
                inc_text = ctx.extra.get("_t_inc_prefix", "Relevant past incidents:\n")
                for inc in module_incidents[:3]:
                    props = inc.get("properties", {})
                    inc_text += f"- {props.get('summary', inc.get('name'))}\n"
                ctx.final_system_prompt += "\n\n" + inc_text

        except _RECOVERABLE as exc:
            logger.debug("Knowledge Graph RAG fehlgeschlagen: %s", exc)
        return MiddlewareResult()


class SkillsMiddleware(BaseMiddleware):
    name = "skills"
    priority = 160

    def __init__(self, get_skills_manager: Any):
        self._get_skills_manager = get_skills_manager

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        try:
            sm = self._get_skills_manager()
            matching = sm.find_matching_skills(ctx.message, ctx.agent_name)
            if matching:
                skill_text = sm.build_injection(matching)
                ctx.final_system_prompt += f"\n\n{skill_text}"
                logger.debug(
                    "Agent '%s': %d Skill(s) injiziert: %s",
                    ctx.agent_name,
                    len(matching),
                    [s.name for s in matching],
                )
        except _RECOVERABLE as exc:
            logger.debug("Skills-Injection fehlgeschlagen (ignoriert): %s", exc)
        return MiddlewareResult()
