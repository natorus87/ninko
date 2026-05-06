"""
Ninko Chat API – Haupt-Interface für Chat-Kommunikation.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse

from schemas.chat import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    ChatMessage,
)
from core.redis_client import get_redis
from core.context_manager import get_context_manager
from core import status_bus
from core.operation_journal import get_operation_journal
from core.auth import auth_tenant_id, resolve_request_auth
from agents.base_agent import _t, _TOOL_SAFEGUARD_SENTINEL
from core.safeguard import ActionCategory

logger = logging.getLogger("ninko.api.chat")
router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _tenant_session_id(request: Request, session_id: str) -> str:
    auth_ctx = resolve_request_auth(request)
    tenant_id = auth_tenant_id(auth_ctx)
    return f"{tenant_id}:{session_id}"


def _parse_sentinel(response_text: str) -> dict:
    """Extrahiert Tool-Infos aus dem Safeguard-Sentinel-String."""
    try:
        return json.loads(response_text[len(_TOOL_SAFEGUARD_SENTINEL):])
    except json.JSONDecodeError:
        return {}


def _tool_confirmation_response(info: dict, session_id: str) -> ChatResponse:
    """Baut eine ChatResponse für eine Tool-Level Safeguard Confirmation."""
    tool_name = info.get("tool_name", "unbekannt")
    category  = info.get("category", "UNKNOWN")
    rationale = info.get("rationale", "")
    return ChatResponse(
        response=_t(
            f"⚠️ **Tool-Bestätigung erforderlich**\n\n"
            f"Der Agent möchte folgendes Tool ausführen:\n\n"
            f"**Tool:** `{tool_name}`\n"
            f"**Kategorie:** {category}\n"
            f"**Begründung:** {rationale}\n\n"
            f"Sende die Nachricht erneut mit `confirmed: true` um fortzufahren.",
            f"⚠️ **Tool Confirmation Required**\n\n"
            f"The agent wants to execute a tool:\n\n"
            f"**Tool:** `{tool_name}`\n"
            f"**Category:** {category}\n"
            f"**Rationale:** {rationale}\n\n"
            f"Resend the message with `confirmed: true` to proceed.",
        ),
        module_used=None,
        session_id=session_id,
        confirmation_required=True,
        safeguard=info,
        timestamp=datetime.now(timezone.utc),
    )


@router.post("/", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    """
    Haupt-Chat-Endpunkt.
    Routet die Nachricht über den Orchestrator an das passende Modul.
    """
    orchestrator = request.app.state.orchestrator
    redis = get_redis()
    ctx_mgr = get_context_manager()
    op_journal = get_operation_journal()
    current_tx_id: str | None = None
    scoped_session_id = _tenant_session_id(request, body.session_id)

    # Status-Queue vorab erstellen (damit SSE-Consumer sofort lesen kann)
    status_bus.get_queue(scoped_session_id)

    # ── Tool-Level Safeguard: Resume nach Bestätigung ─────────────────────────
    # Wenn confirmed=True und ein Tool-Call auf Bestätigung wartet → resumieren
    if body.confirmed:
        current_tx_id = await op_journal.get_pending_for_session(scoped_session_id)
        if current_tx_id:
            await op_journal.mark_confirmed(current_tx_id)
        pending_raw = await redis.connection.get(
            f"ninko:safeguard_tool_pending:{scoped_session_id}"
        )
        if pending_raw:
            # Audit: user confirmed the pending tool call
            try:
                _pending_info = json.loads(pending_raw)
                safeguard = getattr(request.app.state, "safeguard", None)
                if safeguard:
                    await safeguard._audit_log(
                        action="tool_confirmed",
                        category=ActionCategory(_pending_info.get("category", "STATE_CHANGING")),
                        text=body.message,
                        session_id=scoped_session_id,
                        agent_id=_pending_info.get("agent", ""),
                        tool_name=_pending_info.get("tool_name", ""),
                        outcome="confirmed",
                        rationale=_pending_info.get("rationale", ""),
                    )
            except json.JSONDecodeError as exc:
                logger.warning("Audit-Log für Tool-Confirmation fehlgeschlagen: %s", exc)
            # Redis-Key nicht löschen — resume_tool_execution() macht das selbst
            response_text, did_compact = await orchestrator.resume_tool_execution(scoped_session_id)
            await status_bus.done(scoped_session_id)

            # Resume hat weiteren Tool-Call aufgedeckt → nochmals Bestätigung
            if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
                info = _parse_sentinel(response_text)
                return _tool_confirmation_response(info, body.session_id)

            # Normales Ergebnis nach Resume → History speichern und zurückgeben
            if current_tx_id:
                await op_journal.mark_executed(
                    current_tx_id,
                    module=None,
                    summary=response_text[:600],
                )
                await op_journal.clear_pending_for_session(scoped_session_id)
            await redis.store_chat_message(
                session_id=scoped_session_id, role="user", content=body.message
            )
            await redis.store_chat_message(
                session_id=scoped_session_id, role="assistant", content=response_text
            )
            updated_history = await redis.get_chat_history(scoped_session_id)
            budget = ctx_mgr.get_budget_info(updated_history)
            return ChatResponse(
                response=response_text,
                module_used=None,
                session_id=body.session_id,
                context_budget=budget,
                compacted=did_compact,
                timestamp=datetime.now(timezone.utc),
            )

    # ── Safeguard-Check (vor dem 4-tier Routing) ──────────────────────────────
    safeguard = getattr(request.app.state, "safeguard", None)
    if safeguard and not body.confirmed:
        sg_result = await safeguard.check(body.message, session_id=scoped_session_id)
        if sg_result.requires_confirmation:
            if sg_result.category in (ActionCategory.DESTRUCTIVE, ActionCategory.STATE_CHANGING):
                current_tx_id = await op_journal.create_pending(
                    session_id=scoped_session_id,
                    text=body.message,
                    category=sg_result.category.value,
                    rationale=sg_result.rationale,
                    source="chat_safeguard",
                )
            sg_payload = sg_result.to_dict()
            if current_tx_id:
                sg_payload["transaction_id"] = current_tx_id
            await status_bus.done(scoped_session_id)
            return ChatResponse(
                response=_t(
                    f"⚠️ **Bestätigung erforderlich**\n\n"
                    f"Diese Aktion erfordert eine explizite Bestätigung.\n\n"
                    f"**Kategorie:** {sg_result.category.value}\n"
                    f"**Begründung:** {sg_result.rationale}\n\n"
                    f"Sende die Nachricht erneut mit `confirmed: true` um fortzufahren.",
                    f"⚠️ **Confirmation Required**\n\n"
                    f"This action requires explicit confirmation.\n\n"
                    f"**Category:** {sg_result.category.value}\n"
                    f"**Rationale:** {sg_result.rationale}\n\n"
                    f"Resend the message with `confirmed: true` to proceed.",
                ),
                module_used=None,
                session_id=body.session_id,
                confirmation_required=True,
                safeguard=sg_payload,
                timestamp=datetime.now(timezone.utc),
            )
        # Auto-mode: autonomous denial (no user dialog)
        if sg_result.auto_decided and sg_result.auto_decision == "deny":
            await status_bus.done(scoped_session_id)
            return ChatResponse(
                response=_t(
                    f"🛡️ **SafeGuard Auto-Mode: Aktion abgelehnt**\n\n"
                    f"**Kategorie:** {sg_result.category.value}\n"
                    f"**Begründung:** {sg_result.rationale}",
                    f"🛡️ **SafeGuard Auto-Mode: Action Denied**\n\n"
                    f"**Category:** {sg_result.category.value}\n"
                    f"**Reason:** {sg_result.rationale}",
                ),
                module_used=None,
                session_id=body.session_id,
                confirmation_required=False,
                safeguard=sg_result.to_dict(),
                timestamp=datetime.now(timezone.utc),
            )

    # Chat-History laden
    history = await redis.get_chat_history(scoped_session_id)

    # Nachricht an Orchestrator routen
    response_text, module_used, did_compact = await orchestrator.route(
        message=body.message,
        chat_history=history,
        session_id=scoped_session_id,
        confirmed=body.confirmed,
        force_module=body.force_module,
    )

    # ── Tool-Level Safeguard Sentinel prüfen ─────────────────────────────────
    # Wenn ein Tool-Call während der Route-Ausführung Bestätigung braucht
    if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
        await status_bus.done(scoped_session_id)
        info = _parse_sentinel(response_text)
        category = str(info.get("category", "UNKNOWN")).upper()
        if category in {"DESTRUCTIVE", "STATE_CHANGING"}:
            current_tx_id = await op_journal.create_pending(
                session_id=body.session_id,
                text=body.message,
                category=category,
                rationale=str(info.get("rationale", "")),
                source="tool_safeguard",
                module=module_used,
                tool_name=str(info.get("tool_name", "")),
            )
            info["transaction_id"] = current_tx_id
        return _tool_confirmation_response(info, body.session_id)

    # SSE-Consumer signalisieren: Verarbeitung abgeschlossen
    await status_bus.done(scoped_session_id)

    # Bei Komprimierung: System-Nachricht sichtbar in History ablegen
    if did_compact:
        summary = None
        if hasattr(orchestrator, "get_last_compaction_summary"):
            summary = orchestrator.get_last_compaction_summary()
        await redis.store_chat_message(
            session_id=scoped_session_id,
            role="system_compaction",
            content=summary
            or _t(
                "Der Gesprächsverlauf wurde komprimiert, "
                "um Platz für neue Nachrichten zu schaffen. "
                "Die wichtigsten Informationen wurden zusammengefasst und bleiben erhalten.",
                "The conversation history was compacted to make room for new messages. "
                "The most important information was summarized and is preserved.",
            ),
        )

    # Nachrichten in Working Memory speichern
    await redis.store_chat_message(
        session_id=scoped_session_id,
        role="user",
        content=body.message,
    )
    await redis.store_chat_message(
        session_id=scoped_session_id,
        role="assistant",
        content=response_text,
    )

    # Context-Budget berechnen
    updated_history = await redis.get_chat_history(scoped_session_id)
    budget = ctx_mgr.get_budget_info(updated_history)
    if current_tx_id:
        await op_journal.mark_executed(
            current_tx_id,
            module=module_used,
            summary=response_text[:600],
        )
        await op_journal.clear_pending_for_session(scoped_session_id)

    return ChatResponse(
        response=response_text,
        module_used=module_used,
        session_id=body.session_id,
        context_budget=budget,
        compacted=did_compact,
        timestamp=datetime.now(timezone.utc),
    )


@router.get("/stream")
async def chat_stream(session_id: str, request: Request) -> StreamingResponse:
    """
    SSE-Stream für Live-Status-Updates während der Chat-Verarbeitung.
    Verbinde BEVOR der POST /api/chat/ abgeschickt wird.
    """
    auth_ctx = resolve_request_auth(request)
    if not auth_ctx:
        raise HTTPException(status_code=401, detail="Unauthorized")
    scoped_session_id = _tenant_session_id(request, session_id)
    q = status_bus.get_queue(scoped_session_id)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=90.0)
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
                    if event.get("type") == "done":
                        break
                except asyncio.TimeoutError:
                    yield 'data: {"type":"keepalive"}\n\n'
        finally:
            status_bus.cleanup(scoped_session_id)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/history/{session_id}", response_model=ChatHistoryResponse)
async def get_history(session_id: str, request: Request) -> ChatHistoryResponse:
    """Gibt die Chat-History einer Session zurück."""
    redis = get_redis()
    scoped_session_id = _tenant_session_id(request, session_id)
    messages = await redis.get_chat_history(scoped_session_id)

    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            ChatMessage(role=m["role"], content=m["content"]) for m in messages
        ],
        total=len(messages),
    )


@router.delete("/history/{session_id}")
async def clear_history(session_id: str, request: Request) -> dict:
    """Löscht die Chat-History einer Session."""
    redis = get_redis()
    scoped_session_id = _tenant_session_id(request, session_id)
    await redis.clear_chat_history(scoped_session_id)
    return {"status": "ok", "session_id": session_id, "message": "History gelöscht."}


@router.put("/history/{session_id}")
async def replace_history(session_id: str, body: dict, request: Request) -> dict:
    """Ersetzt die Chat-History einer Session vollständig (für Löschen/Retry)."""
    redis = get_redis()
    scoped_session_id = _tenant_session_id(request, session_id)
    messages: list[dict] = body.get("messages", [])
    await redis.clear_chat_history(scoped_session_id)
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if content:
            await redis.store_chat_message(session_id=scoped_session_id, role=role, content=content)
    return {"status": "ok", "session_id": session_id, "count": len(messages)}


# ── UI History (persistente, geräteübergreifende Konversationsliste) ────────

@router.get("/ui-history")
async def get_ui_history(request: Request) -> dict:
    """Gibt alle gespeicherten Konversationen zurück (geräteübergreifend)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    entries = await redis.ui_history_get_all(tenant_id=tenant_id)
    return {"conversations": entries}


@router.post("/ui-history")
async def save_ui_history(body: dict, request: Request) -> dict:
    """Speichert oder aktualisiert einen Konversationseintrag."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    await redis.ui_history_save(body, tenant_id=tenant_id)
    return {"status": "ok"}


@router.delete("/ui-history/{conv_id}")
async def delete_ui_history(conv_id: str, request: Request) -> dict:
    """Löscht einen Konversationseintrag."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    await redis.ui_history_delete(conv_id, tenant_id=tenant_id)
    return {"status": "ok", "id": conv_id}
