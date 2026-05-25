"""
Ninko Chat API – Haupt-Interface für Chat-Kommunikation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
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
from core.routing_telemetry import get_routing_telemetry

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


# ── Stream-Frame-Helper ────────────────────────────────────────────────────────


def _stream_frame(frame_type: str, request_id: str, message_id: str, **fields) -> str:
    """Baut ein SSE-Frame als JSON-String."""
    data = {"type": frame_type, "request_id": request_id, "message_id": message_id}
    data.update(fields)
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _wants_chat_stream(request: Request) -> bool:
    """Prueft robust, ob der Client den Chat als SSE streamen moechte."""
    accept = request.headers.get("accept", "")
    return "text/event-stream" in accept.lower()


async def _stream_safe_generate(
    request: Request,
    body: ChatRequest,
    scoped_session_id: str,
    request_id: str,
    message_id: str,
) -> AsyncGenerator[str, None]:
    """
    Generiert die Chat-Antwort und streamt Tokens via SSE.
    Fängt CancelledError ab um bei Client-Abbruch sauber zu stoppen.
    """
    orchestrator = request.app.state.orchestrator
    redis = get_redis()
    ctx_mgr = get_context_manager()
    op_journal = get_operation_journal()

    response_text = ""
    streamed_text = ""
    live_stream_used = False
    module_used: str | None = None
    did_compact = False
    current_tx_id: str | None = None
    token_queue: asyncio.Queue[str] = asyncio.Queue(maxsize=1000)

    async def _emit_live_token(token: str) -> None:
        if token:
            await token_queue.put(token)

    async def _is_cancelled() -> bool:
        return await request.is_disconnected()

    async def _mark_current_tx_failed(error: str) -> None:
        nonlocal current_tx_id
        if not current_tx_id:
            return
        try:
            await op_journal.mark_failed(current_tx_id, error=error)
            await op_journal.clear_pending_for_session(scoped_session_id)
        except Exception as journal_exc:
            logger.warning(
                "Operation-Journal Cleanup fehlgeschlagen: %s",
                type(journal_exc).__name__,
            )
        finally:
            current_tx_id = None

    try:
        await status_bus.emit_trace(
            scoped_session_id,
            phase="request",
            label="Chat-Verarbeitung gestartet",
            detail="Streaming-Antwortpfad",
            data={
                "confirmed": body.confirmed,
                "force_module": body.force_module,
                "message_length": len(body.message or ""),
            },
            status="running",
        )
        # ── Tool-Level Safeguard: Resume nach Bestätigung ───────────────────
        if body.confirmed:
            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="Bestätigte Tool-Ausführung wird fortgesetzt",
                data={"confirmed": True},
                status="running",
            )
            current_tx_id = await op_journal.get_pending_for_session(scoped_session_id)
            if current_tx_id:
                await op_journal.mark_confirmed(current_tx_id)
            pending_raw = await redis.connection.get(
                f"ninko:safeguard_tool_pending:{scoped_session_id}"
            )
            if pending_raw:
                try:
                    _pending_info = json.loads(pending_raw) or {}
                except json.JSONDecodeError as exc:
                    logger.warning("Audit-Log für Tool-Confirmation fehlgeschlagen: %s", exc)
                    _pending_info = {}
                if _pending_info:
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

                response_text, did_compact = await orchestrator.resume_tool_execution(scoped_session_id)

                if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
                    await status_bus.done(scoped_session_id)
                    info = _parse_sentinel(response_text)
                    meta = {
                        "confirmation_required": True,
                        "safeguard": info,
                        "session_id": body.session_id,
                        "context_budget": None,
                        "compacted": False,
                        "module_used": None,
                        "routing_confidence": None,
                    }
                    yield _stream_frame("final", request_id, message_id, response="", meta=meta)
                    return

                if current_tx_id:
                    await op_journal.mark_executed(
                        current_tx_id,
                        module=None,
                        summary=response_text[:600],
                    )
                    await op_journal.clear_pending_for_session(scoped_session_id)
                    current_tx_id = None

                await status_bus.done(scoped_session_id)
                module_used = None
                history = []
                _telemetry = get_routing_telemetry()
                goto_stream_response = True
            else:
                goto_stream_response = False
        else:
            goto_stream_response = False

        # ── Safeguard-Check ──────────────────────────────────────────────────
        safeguard = getattr(request.app.state, "safeguard", None)
        if not goto_stream_response and safeguard and not body.confirmed:
            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="Nachricht wird durch SafeGuard geprüft",
                data={"message_length": len(body.message or "")},
                status="running",
            )
            sg_result = await safeguard.check(body.message, session_id=scoped_session_id)
            if sg_result.requires_confirmation:
                await status_bus.emit_trace(
                    scoped_session_id,
                    phase="safeguard",
                    label="SafeGuard fordert Bestätigung",
                    detail=sg_result.rationale,
                    data={"category": sg_result.category.value},
                )
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
                # No tokens before final for confirmation flows
                meta = {
                    "confirmation_required": True,
                    "safeguard": sg_payload,
                    "session_id": body.session_id,
                    "context_budget": None,
                    "compacted": False,
                    "module_used": None,
                    "routing_confidence": None,
                }
                yield _stream_frame("final", request_id, message_id, response="", meta=meta)
                return

            if sg_result.auto_decided and sg_result.auto_decision == "deny":
                await status_bus.emit_trace(
                    scoped_session_id,
                    phase="safeguard",
                    label="SafeGuard lehnt automatisch ab",
                    detail=sg_result.rationale,
                    data={"category": sg_result.category.value},
                    status="error",
                )
                await status_bus.done(scoped_session_id)
                response_text = _t(
                    f"🛡️ **SafeGuard Auto-Mode: Aktion abgelehnt**\n\n"
                    f"**Kategorie:** {sg_result.category.value}\n"
                    f"**Begründung:** {sg_result.rationale}",
                    f"🛡️ **SafeGuard Auto-Mode: Action Denied**\n\n"
                    f"**Category:** {sg_result.category.value}\n"
                    f"**Reason:** {sg_result.rationale}",
                )
                meta = {
                    "confirmation_required": False,
                    "safeguard": sg_result.to_dict(),
                    "session_id": body.session_id,
                    "context_budget": None,
                    "compacted": False,
                    "module_used": None,
                    "routing_confidence": None,
                }
                yield _stream_frame("final", request_id, message_id, response=response_text, meta=meta)
                return

            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="Nachrichten-SafeGuard freigegeben",
                data={"category": sg_result.category.value},
            )

        # ── Chat-History laden ───────────────────────────────────────────────
        if not goto_stream_response:
            history = await redis.get_chat_history(scoped_session_id)
            await status_bus.emit_trace(
                scoped_session_id,
                phase="context",
                label="Chat-History geladen",
                data={"history_messages": len(history)},
            )

        # ── R12: Korrektur erkennen ──────────────────────────────────────────
        _telemetry = get_routing_telemetry()
        if not goto_stream_response and body.force_module and _telemetry:
            _correction = await _telemetry.check_and_record_correction(
                session_id=scoped_session_id,
                force_module=body.force_module,
                message=body.message,
            )
            if _correction and hasattr(orchestrator, "apply_embedding_corrections"):
                _examples = await _telemetry.get_correction_examples(body.force_module)
                orchestrator.apply_embedding_corrections(body.force_module, _examples)

        # ── Routing ───────────────────────────────────────────────────────────
        if not goto_stream_response:
            await status_bus.emit_trace(
                scoped_session_id,
                phase="routing",
                label="Routing gestartet",
                data={"force_module": body.force_module},
                status="running",
            )
            route_task = asyncio.create_task(
                orchestrator.route(
                    message=body.message,
                    chat_history=history,
                    session_id=scoped_session_id,
                    confirmed=body.confirmed,
                    force_module=body.force_module,
                    wants_stream=True,
                    token_callback=_emit_live_token,
                    cancellation_check=_is_cancelled,
                )
            )

            while True:
                if await _is_cancelled():
                    route_task.cancel()
                    raise asyncio.CancelledError()
                try:
                    token = await asyncio.wait_for(token_queue.get(), timeout=0.05)
                except asyncio.TimeoutError:
                    if route_task.done():
                        break
                    token = ""

                if token:
                    live_stream_used = True
                    streamed_text += token
                    yield _stream_frame("token", request_id, message_id, text=token)

            route_result = await route_task
            if not isinstance(route_result, tuple) or len(route_result) != 3:
                logger.error(
                    "orchestrator.route() returned invalid type: %s", type(route_result)
                )
                raise TypeError(
                    f"Expected (str, str|None, bool), got: {type(route_result).__name__}"
                )
            response_text, module_used, did_compact = route_result
            await status_bus.emit_trace(
                scoped_session_id,
                phase="routing",
                label="Routing abgeschlossen",
                data={
                    "module_used": module_used,
                    "compacted": did_compact,
                    "response_length": len(response_text or ""),
                },
            )

            # Verbleibende Tokens nach route_task.done() drainen, um Token-Verlust
            # zwischen letztem queue.get()-Timeout und Task-Completion zu vermeiden.
            while not token_queue.empty():
                token = token_queue.get_nowait()
                if token:
                    live_stream_used = True
                    streamed_text += token
                    yield _stream_frame("token", request_id, message_id, text=token)

        # ── Tool-Level Safeguard Sentinel prüfen ─────────────────────────────
        if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
            await status_bus.done(scoped_session_id)
            info = _parse_sentinel(response_text)
            category = str(info.get("category", "UNKNOWN")).upper()
            if category in {"DESTRUCTIVE", "STATE_CHANGING"}:
                current_tx_id = await op_journal.create_pending(
                    session_id=scoped_session_id,
                    text=body.message,
                    category=category,
                    rationale=str(info.get("rationale", "")),
                    source="tool_safeguard",
                    module=module_used,
                    tool_name=str(info.get("tool_name", "")),
                )
                info["transaction_id"] = current_tx_id
            # Buffer response - no streaming tokens before final for confirmations
            meta = {
                "confirmation_required": True,
                "safeguard": info,
                "session_id": body.session_id,
                "context_budget": None,
                "compacted": False,
                "module_used": module_used,
                "routing_confidence": getattr(orchestrator, "_last_routing_confidence", None),
            }
            yield _stream_frame("final", request_id, message_id, response="", meta=meta)
            return

        await status_bus.emit_trace(
            scoped_session_id,
            phase="request",
            label="Chat-Verarbeitung abgeschlossen",
            data={"module_used": module_used, "response_length": len(response_text or "")},
        )
        # ── Stream Tokens in Chunks ───────────────────────────────────────────
        # Mini-Chunking: ~8 Zeichen pro Frame + 60ms Pause zwischen Chunks fuer
        # ein fluessig wirkendes Streaming (viele kleine Updates statt grosser Sprunge).
        if not live_stream_used:
            chunk_size = 8
            chunk_delay = 0.06
            chunks_total = max(1, (len(response_text) + chunk_size - 1) // chunk_size)
            for idx, i in enumerate(range(0, len(response_text), chunk_size)):
                if await request.is_disconnected():
                    raise asyncio.CancelledError()
                chunk = response_text[i : i + chunk_size]
                streamed_text += chunk
                yield _stream_frame("token", request_id, message_id, text=chunk)
                if idx < chunks_total - 1:
                    await asyncio.sleep(chunk_delay)

        # ── Komprimierung ────────────────────────────────────────────────────
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

        # ── History speichern ────────────────────────────────────────────────
        await redis.store_chat_message(session_id=scoped_session_id, role="user", content=body.message)
        await redis.store_chat_message(session_id=scoped_session_id, role="assistant", content=response_text)

        # Context-Budget
        updated_history = await redis.get_chat_history(scoped_session_id)
        budget = ctx_mgr.get_budget_info(updated_history)

        if current_tx_id:
            await op_journal.mark_executed(current_tx_id, module=module_used, summary=response_text[:600])
            await op_journal.clear_pending_for_session(scoped_session_id)

        routing_confidence = getattr(orchestrator, "_last_routing_confidence", None)

        # ── R12: Auto-Routing-Telemetrie ─────────────────────────────────────
        if not body.force_module and module_used and _telemetry:
            await _telemetry.record_auto_routing(
                session_id=scoped_session_id,
                module=module_used,
                tier=getattr(orchestrator, "_last_tier_used", 0),
                confidence=routing_confidence,
                message=body.message,
            )

        # ── Final Frame ───────────────────────────────────────────────────────
        meta = {
            "module_used": module_used,
            "session_id": body.session_id,
            "context_budget": budget,
            "compacted": did_compact,
            "confirmation_required": False,
            "safeguard": None,
            "routing_confidence": routing_confidence,
        }
        # Status-SSE erst direkt vor dem finalen Chat-Frame schließen. So bleibt
        # der sichtbare Trace während langsamem Fallback-Chunking konsistent.
        await status_bus.done(scoped_session_id)
        yield _stream_frame("final", request_id, message_id, response=response_text, meta=meta)

    except asyncio.CancelledError:
        # Client hat abgebrochen — keine Assistant-History für unvollständige Antwort
        await _mark_current_tx_failed(
            "Chat streaming cancelled before execution completed."
        )
        await status_bus.done(scoped_session_id)
        yield _stream_frame(
            "cancelled",
            request_id,
            message_id,
            partial_response=streamed_text,
        )
        raise
    except Exception as exc:
        await _mark_current_tx_failed(
            "Chat streaming failed before execution completed."
        )
        logger.error(
            "Chat-Streaming fehlgeschlagen: %s",
            type(exc).__name__,
            exc_info=False,
        )
        await status_bus.done(scoped_session_id)
        yield _stream_frame(
            "error",
            request_id,
            message_id,
            message=_t(
                "Fehler: Bei der Verarbeitung ist ein interner Fehler aufgetreten.",
                "Error: An internal error occurred while processing the request.",
            ),
            recoverable=True,
        )


@router.post("/")
async def chat(request: Request, body: ChatRequest):
    """
    Haupt-Chat-Endpunkt.
    Routet die Nachricht über den Orchestrator an das passende Modul.

    Bei Accept: text/event-stream wird ein SSE-Stream zurückgegeben.
    """
    # Streaming-Pfad: Client wants SSE
    if _wants_chat_stream(request):
        scoped_session_id = _tenant_session_id(request, body.session_id)
        status_bus.get_queue(scoped_session_id)  # Ensure queue exists for SSE consumer
        request_id = str(uuid.uuid4())
        message_id = str(uuid.uuid4())

        # Send start frame immediately
        async def start_and_stream():
            yield _stream_frame("start", request_id, message_id)
            async for frame in _stream_safe_generate(
                request, body, scoped_session_id, request_id, message_id
            ):
                yield frame

        return StreamingResponse(
            start_and_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ── Bestehender blockierender JSON-Pfad ──────────────────────────────────
    orchestrator = request.app.state.orchestrator
    redis = get_redis()
    ctx_mgr = get_context_manager()
    op_journal = get_operation_journal()
    current_tx_id: str | None = None
    scoped_session_id = _tenant_session_id(request, body.session_id)

    # Status-Queue vorab erstellen (damit SSE-Consumer sofort lesen kann)
    status_bus.get_queue(scoped_session_id)
    await status_bus.emit_trace(
        scoped_session_id,
        phase="request",
        label="Chat-Verarbeitung gestartet",
        detail="JSON-Antwortpfad",
        data={
            "confirmed": body.confirmed,
            "force_module": body.force_module,
            "message_length": len(body.message or ""),
        },
        status="running",
    )

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
        await status_bus.emit_trace(
            scoped_session_id,
            phase="safeguard",
            label="Nachricht wird durch SafeGuard geprüft",
            data={"message_length": len(body.message or "")},
            status="running",
        )
        sg_result = await safeguard.check(body.message, session_id=scoped_session_id)
        if sg_result.requires_confirmation:
            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="SafeGuard fordert Bestätigung",
                detail=sg_result.rationale,
                data={"category": sg_result.category.value},
            )
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
            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="SafeGuard lehnt automatisch ab",
                detail=sg_result.rationale,
                data={"category": sg_result.category.value},
                status="error",
            )
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
        await status_bus.emit_trace(
            scoped_session_id,
            phase="safeguard",
            label="Nachrichten-SafeGuard freigegeben",
            data={"category": sg_result.category.value},
        )

    # Chat-History laden
    history = await redis.get_chat_history(scoped_session_id)
    await status_bus.emit_trace(
        scoped_session_id,
        phase="context",
        label="Chat-History geladen",
        data={"history_messages": len(history)},
    )

    # ── R12: Korrektur erkennen (vor route()) ─────────────────────────────────
    _telemetry = get_routing_telemetry()
    if body.force_module and _telemetry:
        _correction = await _telemetry.check_and_record_correction(
            session_id=scoped_session_id,
            force_module=body.force_module,
            message=body.message,
        )
        if _correction and hasattr(orchestrator, "apply_embedding_corrections"):
            _examples = await _telemetry.get_correction_examples(body.force_module)
            orchestrator.apply_embedding_corrections(body.force_module, _examples)

    # Nachricht an Orchestrator routen
    await status_bus.emit_trace(
        scoped_session_id,
        phase="routing",
        label="Routing gestartet",
        data={"force_module": body.force_module},
        status="running",
    )
    response_text, module_used, did_compact = await orchestrator.route(
        message=body.message,
        chat_history=history,
        session_id=scoped_session_id,
        confirmed=body.confirmed,
        force_module=body.force_module,
    )
    await status_bus.emit_trace(
        scoped_session_id,
        phase="routing",
        label="Routing abgeschlossen",
        data={
            "module_used": module_used,
            "compacted": did_compact,
            "response_length": len(response_text or ""),
        },
    )

    # ── Tool-Level Safeguard Sentinel prüfen ─────────────────────────────────
    # Wenn ein Tool-Call während der Route-Ausführung Bestätigung braucht
    if response_text.startswith(_TOOL_SAFEGUARD_SENTINEL):
        await status_bus.done(scoped_session_id)
        info = _parse_sentinel(response_text)
        category = str(info.get("category", "UNKNOWN")).upper()
        if category in {"DESTRUCTIVE", "STATE_CHANGING"}:
            current_tx_id = await op_journal.create_pending(
                session_id=scoped_session_id,
                text=body.message,
                category=category,
                rationale=str(info.get("rationale", "")),
                source="tool_safeguard",
                module=module_used,
                tool_name=str(info.get("tool_name", "")),
            )
            info["transaction_id"] = current_tx_id
        return _tool_confirmation_response(info, body.session_id)

    await status_bus.emit_trace(
        scoped_session_id,
        phase="request",
        label="Chat-Verarbeitung abgeschlossen",
        data={"module_used": module_used, "response_length": len(response_text or "")},
    )
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

    routing_confidence = getattr(orchestrator, "_last_routing_confidence", None)

    # ── R12: Auto-Routing-Ergebnis für Korrektur-Erkennung speichern ──────────
    if not body.force_module and module_used and _telemetry:
        await _telemetry.record_auto_routing(
            session_id=scoped_session_id,
            module=module_used,
            tier=getattr(orchestrator, "_last_tier_used", 0),
            confidence=routing_confidence,
            message=body.message,
        )

    return ChatResponse(
        response=response_text,
        module_used=module_used,
        session_id=body.session_id,
        context_budget=budget,
        compacted=did_compact,
        timestamp=datetime.now(timezone.utc),
        routing_confidence=routing_confidence,
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


_REPLACE_HISTORY_MAX_MESSAGES = 500
_REPLACE_HISTORY_MAX_CONTENT_LEN = 32_768
_REPLACE_HISTORY_ALLOWED_ROLES = frozenset({"user", "assistant"})


@router.put("/history/{session_id}")
async def replace_history(session_id: str, body: dict, request: Request) -> dict:
    """Ersetzt die Chat-History einer Session vollständig (für Löschen/Retry)."""
    redis = get_redis()
    scoped_session_id = _tenant_session_id(request, session_id)
    messages: list[dict] = body.get("messages", [])
    if not isinstance(messages, list):
        raise HTTPException(status_code=422, detail="'messages' muss eine Liste sein.")
    if len(messages) > _REPLACE_HISTORY_MAX_MESSAGES:
        raise HTTPException(
            status_code=422,
            detail=f"Maximal {_REPLACE_HISTORY_MAX_MESSAGES} Nachrichten pro Aufruf.",
        )
    await redis.clear_chat_history(scoped_session_id)
    stored = 0
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        role = msg.get("role", "user")
        if role not in _REPLACE_HISTORY_ALLOWED_ROLES:
            continue
        content = msg.get("content", "")
        if not isinstance(content, str):
            continue
        content = content[:_REPLACE_HISTORY_MAX_CONTENT_LEN]
        if content:
            await redis.store_chat_message(session_id=scoped_session_id, role=role, content=content)
            stored += 1
    return {"status": "ok", "session_id": session_id, "count": stored}


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
