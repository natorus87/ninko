"""
Ninko LLM Factory – Backend-Switch für Ollama und LM Studio (OpenAI-kompatibel).
Embeddings und Chat-LLM nutzen denselben konfigurierten Provider.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from core.config import get_settings


def _normalize_msg_content(msg: BaseMessage) -> BaseMessage:
    """Konvertiert Listen-Content zu String (LM Studio Jinja-Kompatibilität).

    Qwen3.5 und ähnliche Modelle haben Chat-Templates mit `is sequence`-Tests
    in Jinja2. LM Studio's eingebettete Jinja2-Version kennt diesen Test nicht
    → `Unknown test: sequence`. Das passiert wenn LangChain nach Tool-Calls
    Content als Liste serialisiert (multimodales Format).
    Fix: Content-Listen vor dem API-Call immer zu Plain-String konvertieren.
    """
    if not isinstance(msg.content, list):
        return msg
    parts: list[str] = []
    for part in msg.content:
        if isinstance(part, dict):
            parts.append(part.get("text", ""))
        else:
            parts.append(str(part))
    return msg.model_copy(update={"content": "".join(parts).strip()})


def _convert_tool_messages_to_text(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Konvertiert AIMessage+ToolMessage Tool-Call-Paare zu Qwen3.5-Text-Format.

    LM Studio's Jinja-Template verwendet `is sequence` auf dem `tool_calls`-Feld
    von AIMessages (eine Python-Liste). Da LM Studio's Jinja2 diesen Test nicht
    kennt, schlägt das Template fehl (HTTP 400).

    Fix: Tool-Calls als <tool_call>-Text in den AIMessage-Content einbetten
    und ToolMessages als <tool_response>-HumanMessages umwandeln. Dadurch
    enthält keine Message mehr ein `tool_calls`-Listenfeld und das Template
    läuft ohne `is sequence`-Check durch.

    Qwen3.5 versteht das <tool_call>/<tool_response>-Format nativ (so ist es
    trainiert), generiert korrekte Tool-Calls als Text, und LM Studio wandelt
    diese zurück in das OpenAI-`tool_calls`-Format um.
    """
    result: list[BaseMessage] = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            tc_blocks: list[str] = []
            for tc in msg.tool_calls:
                tc_json = json.dumps(
                    {"name": tc.get("name", ""), "arguments": tc.get("args", {})},
                    ensure_ascii=False,
                )
                tc_blocks.append(f"<tool_call>\n{tc_json}\n</tool_call>")
            content = (str(msg.content or "")).strip()
            if content:
                content += "\n"
            content += "\n".join(tc_blocks)
            result.append(AIMessage(content=content))
        elif isinstance(msg, ToolMessage):
            result.append(HumanMessage(
                content=f"<tool_response>\n{msg.content}\n</tool_response>"
            ))
        else:
            result.append(msg)
    return result


def _inject_tools_into_system(
    messages: list[BaseMessage],
    tools: list[dict],
) -> list[BaseMessage]:
    """Injiziert Tool-Definitionen als Text in die SystemMessage.

    LM Studio's Jinja2 unterstützt `is sequence` nicht. Das betrifft nicht nur
    Message-Content (→ HTTP 400, behoben durch _normalize_msg_content), sondern
    auch die Tool-Sektion im Template: Die Jinja-Verarbeitung schlägt still
    fehl und das Modell sieht nur Beispiel-Tool-Namen ('example_function_name')
    statt der echten Tools.

    Fix: Tool-Definitionen explizit als JSON-Text in die SystemMessage
    anhängen. Das Modell sieht die echten Tool-Namen unabhängig vom Template.
    """
    if not tools or not messages:
        return messages

    # Tool-Defs als kompakten JSON-Block formatieren
    tool_entries: list[str] = []
    for t in tools:
        fn = t.get("function", {}) if isinstance(t, dict) else {}
        name = fn.get("name", "")
        desc = fn.get("description", "")
        params = fn.get("parameters", {})
        props = params.get("properties", {})
        required = params.get("required", [])
        param_parts: list[str] = []
        for pname, pschema in props.items():
            pdesc = pschema.get("description", pschema.get("type", ""))
            req = " (required)" if pname in required else ""
            param_parts.append(f"  - {pname}{req}: {pdesc}")
        params_text = "\n".join(param_parts) if param_parts else "  (no parameters)"
        tool_entries.append(f"### {name}\n{desc}\nParameters:\n{params_text}")

    tool_block = (
        "\n\n---\n## Available Tools\n"
        "The following tools are available. Use them by their exact names:\n\n"
        + "\n\n".join(tool_entries)
    )

    result = list(messages)
    for i, msg in enumerate(result):
        if isinstance(msg, SystemMessage):
            result[i] = SystemMessage(content=str(msg.content) + tool_block)
            break
    return result


class _NormalizingChatOpenAI(ChatOpenAI):
    """ChatOpenAI-Subklasse die Listen-Content zu Strings normalisiert.

    Verhindert 'Unknown test: sequence' in LM Studio's Jinja2 bei multimodalem
    Content (Liste statt String). Gilt für alle OpenAI-kompatiblen Anbieter.
    """

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        return super()._generate(
            [_normalize_msg_content(m) for m in messages],
            stop=stop, run_manager=run_manager, **kwargs,
        )

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        return await super()._agenerate(
            [_normalize_msg_content(m) for m in messages],
            stop=stop, run_manager=run_manager, **kwargs,
        )


class _LMStudioChatOpenAI(_NormalizingChatOpenAI):
    """Erweitert _NormalizingChatOpenAI um LM Studio-spezifische Fixes.

    Zwei zusätzliche Fixes auf LM Studio-Ebene (Jinja2-`is sequence`-Bug):

    1. Tool-Message-Konvertierung: AIMessage.tool_calls (Liste) und ToolMessages
       werden zu <tool_call>/<tool_response>-Text umgewandelt, damit kein
       `tool_calls`-Listenfeld mehr in der API-Payload landet.

    2. Tool-Text-Injection: Tool-Definitionen werden als lesbaren Text in die
       SystemMessage injiziert, da LM Studio's Template-Tool-Injektion still
       fehlschlägt und das Modell sonst 'example_function_name' verwendet.
    """

    def _prepare(self, messages: list[BaseMessage], tools: list[dict]) -> list[BaseMessage]:
        converted = _convert_tool_messages_to_text(messages)
        injected = _inject_tools_into_system(converted, tools)
        return [_normalize_msg_content(m) for m in injected]

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        prepared = self._prepare(messages, kwargs.get("tools", []))
        # Basis-Klasse (ChatOpenAI) direkt aufrufen, nicht _NormalizingChatOpenAI
        # (die würde nochmal normalisieren — _prepare macht das bereits)
        return ChatOpenAI._generate(self, prepared, stop=stop, run_manager=run_manager, **kwargs)

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        prepared = self._prepare(messages, kwargs.get("tools", []))
        return await ChatOpenAI._agenerate(self, prepared, stop=stop, run_manager=run_manager, **kwargs)

logger = logging.getLogger("ninko.llm_factory")

# Gecachte Context-Window-Größe des aktuell geladenen Modells
_cached_context_window: Optional[int] = None
_DEFAULT_CONTEXT_WINDOW = 32768  # sicherer Fallback wenn API nicht erreichbar

# Generation-Counter – wird bei jedem Provider-Wechsel erhöht
# Agents prüfen diesen Wert und re-initialisieren ihr LLM bei Abweichung
_llm_generation: int = 0


def get_llm_generation() -> int:
    """Gibt die aktuelle LLM-Generation zurück (steigt bei jedem Provider-Wechsel)."""
    return _llm_generation


async def get_model_context_window() -> int:
    """
    Fragt die LLM API nach der Context-Window-Größe des geladenen Modells.
    Gibt den gecachten Wert zurück wenn bereits abgefragt.
    Fallback: _DEFAULT_CONTEXT_WINDOW (32768).
    """
    global _cached_context_window
    if _cached_context_window is not None:
        return _cached_context_window

    settings = get_settings()
    try:
        if settings.LLM_BACKEND == "ollama":
            # Ollama hat kein standardisiertes /models Endpoint für context_length
            _cached_context_window = _DEFAULT_CONTEXT_WINDOW
            return _cached_context_window

        # LM Studio oder OpenAI-kompatibel – /v1/models Endpoint
        if settings.LLM_BACKEND == "openai_compatible":
            base_url = settings.OPENAI_BASE_URL.rstrip("/")
        else:
            base_url = settings.LMSTUDIO_BASE_URL.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = base_url + "/v1"

        headers = {}
        if settings.LLM_BACKEND == "openai_compatible" and settings.OPENAI_API_KEY:
            headers["Authorization"] = f"Bearer {settings.OPENAI_API_KEY}"

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{base_url}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            models = data.get("data", [])
            if models:
                model = models[0]
                ctx = (
                    model.get("context_length")
                    or model.get("max_context_length")
                    or (model.get("meta", {}) or {}).get("context_length")
                )
                if ctx and isinstance(ctx, int) and ctx > 0:
                    _cached_context_window = ctx
                    logger.info(
                        "Context-Window aus API gelesen: %d Tokens (Modell: %s)",
                        ctx, model.get("id", "unbekannt"),
                    )
                    return ctx
    except Exception as exc:
        logger.debug("Context-Window-Abfrage fehlgeschlagen (Fallback %d): %s", _DEFAULT_CONTEXT_WINDOW, exc)

    _cached_context_window = _DEFAULT_CONTEXT_WINDOW
    logger.info("Context-Window: Fallback auf %d Tokens", _DEFAULT_CONTEXT_WINDOW)
    return _cached_context_window


def invalidate_context_window_cache() -> None:
    """Cache leeren und Generation erhöhen — z.B. nach Provider-/Modell-Wechsel via UI."""
    global _cached_context_window, _llm_generation
    _cached_context_window = None
    _llm_generation += 1


def _get_lmstudio_base_url(raw_url: str) -> str:
    """Stellt sicher, dass die LM Studio Base-URL auf /v1 endet."""
    base = raw_url.rstrip("/")
    if not base.endswith("/v1"):
        base = base + "/v1"
    return base


def get_llm() -> BaseChatModel:
    """
    Gibt je nach LLM_BACKEND das passende Chat-Modell zurück.
    Unterstützte Backends: 'ollama', 'lmstudio' (OpenAI-kompatibel), 'openai_compatible' (mit API-Key).
    """
    settings = get_settings()

    if settings.LLM_BACKEND == "ollama":
        # Legacy-Fallback: Ollama (nur noch für lokale Entwicklung)
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            raise ImportError("langchain-ollama ist nicht installiert. Nutze LM Studio als Backend.")
        logger.info(
            "LLM-Backend: Ollama (Legacy) – Modell=%s, URL=%s",
            settings.OLLAMA_MODEL,
            settings.OLLAMA_BASE_URL,
        )
        return ChatOllama(
            model=settings.OLLAMA_MODEL,
            base_url=settings.OLLAMA_BASE_URL,
            temperature=settings.LLM_TEMPERATURE,
            num_predict=settings.MAX_OUTPUT_TOKENS,
        )

    elif settings.LLM_BACKEND == "openai_compatible":
        # OpenAI-kompatibel mit API-Key (OpenRouter, Groq, Together, etc.)
        base_url = _get_lmstudio_base_url(settings.OPENAI_BASE_URL)
        api_key = settings.OPENAI_API_KEY or "sk-placeholder"
        logger.info(
            "LLM-Backend: OpenAI-kompatibel – URL=%s, Modell=%s",
            base_url,
            settings.OPENAI_MODEL,
        )
        return _NormalizingChatOpenAI(
            base_url=base_url,
            api_key=api_key,
            model=settings.OPENAI_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.MAX_OUTPUT_TOKENS,
        )

    else:
        # Standard: LM Studio / OpenAI-kompatibler Endpoint (lokal, kein API-Key)
        base_url = _get_lmstudio_base_url(settings.LMSTUDIO_BASE_URL)
        logger.info(
            "LLM-Backend: LM Studio – URL=%s, Modell=%s",
            base_url,
            settings.LMSTUDIO_MODEL,
        )
        return _LMStudioChatOpenAI(
            base_url=base_url,
            api_key="lm-studio",
            model=settings.LMSTUDIO_MODEL,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.MAX_OUTPUT_TOKENS,
        )


def get_embeddings() -> Embeddings:
    """
    Gibt das Embedding-Modell zurück.
    Nutzt das globale EMBED_MODEL und verbindet sich über den aktiven LLM-Provider
    (gleiche Base-URL und API-Key), da nur eine ChromaDB existiert und das
    Embedding-Modell einheitlich sein muss.
    """
    settings = get_settings()
    embed_model = settings.EMBED_MODEL

    if settings.LLM_BACKEND == "ollama":
        try:
            from langchain_ollama import OllamaEmbeddings
        except ImportError:
            raise ImportError("langchain-ollama ist nicht installiert. Nutze LM Studio als Backend.")
        logger.info(
            "Embedding-Backend: Ollama – Modell=%s, URL=%s",
            embed_model, settings.OLLAMA_BASE_URL,
        )
        return OllamaEmbeddings(
            model=embed_model,
            base_url=settings.OLLAMA_BASE_URL,
        )

    elif settings.LLM_BACKEND == "openai_compatible":
        base_url = _get_lmstudio_base_url(settings.OPENAI_BASE_URL)
        api_key = settings.OPENAI_API_KEY or "sk-placeholder"
        logger.info(
            "Embedding-Backend: OpenAI-kompatibel – Modell=%s, URL=%s",
            embed_model, base_url,
        )
        return OpenAIEmbeddings(
            base_url=base_url,
            api_key=api_key,
            model=embed_model,
            check_embedding_ctx_length=False,
        )

    else:
        # LM Studio
        base_url = _get_lmstudio_base_url(settings.LMSTUDIO_BASE_URL)
        logger.info(
            "Embedding-Backend: LM Studio – Modell=%s, URL=%s",
            embed_model, base_url,
        )
        return OpenAIEmbeddings(
            base_url=base_url,
            api_key="lm-studio",
            model=embed_model,
            check_embedding_ctx_length=False,
        )


def get_safeguard_openai_client():
    """
    Gibt einen (AsyncOpenAI, model_name)-Tuple für den Safeguard-Classifier zurück.
    Nutzt denselben LLM-Provider wie der Rest der App — kein separater Endpoint nötig.
    """
    from openai import AsyncOpenAI

    settings = get_settings()

    if settings.LLM_BACKEND == "openai_compatible":
        base_url = _get_lmstudio_base_url(settings.OPENAI_BASE_URL)
        api_key = settings.OPENAI_API_KEY or "sk-placeholder"
        model = settings.OPENAI_MODEL
    elif settings.LLM_BACKEND == "ollama":
        # Ollama hat einen OpenAI-kompatiblen Endpoint unter /v1
        base_url = settings.OLLAMA_BASE_URL.rstrip("/") + "/v1"
        api_key = "ollama"
        model = settings.OLLAMA_MODEL
    else:
        # lmstudio (Standard)
        base_url = _get_lmstudio_base_url(settings.LMSTUDIO_BASE_URL)
        api_key = "lm-studio"
        model = settings.LMSTUDIO_MODEL

    client = AsyncOpenAI(base_url=base_url, api_key=api_key)
    return client, model
