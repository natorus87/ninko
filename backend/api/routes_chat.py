"""
Ninko Chat API – Haupt-Interface für Chat-Kommunikation.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
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
    HistoryUpdateRequest,
    SessionMessagesResponse,
    UiHistoryEntry,
)
from core.redis_client import get_redis
from core.context_manager import get_context_manager
from core import status_bus
from core.operation_journal import get_operation_journal
from core.auth import auth_tenant_id, resolve_request_auth
from agents.base_agent import _t, _TOOL_SAFEGUARD_SENTINEL
from core.safeguard import ActionCategory, is_bot_confirmation
from core.routing_telemetry import get_routing_telemetry

logger = logging.getLogger("ninko.api.chat")


# Multilinguale Hints für Confirm/Cancel-Erkennung. Wird im Web-Chat
# Fallback genutzt, wenn is_bot_confirmation() (für Bot-Channels, max.
# 3 Wörter) nicht greift — z.B. "Ja, starte die VM neu" oder
# "Oui, redémarre USR-VM-05". Deckt alle 10 Ninko-Sprachen ab.
_MULTILINGUAL_CONFIRM_HINTS: tuple[str, ...] = (
    # Deutsch
    "ja", "jo", "jep", "jup", "jawohl", "klar", "natürlich",
    "bestätig", "starte", "start", "neustart", "neustarten",
    "neu starten", "restart", "reboot", "ausführen", "durchführen",
    "weiter", "los", "mach",
    # English
    "yes", "yep", "yup", "y", "sure", "absolutely", "confirm",
    "proceed", "continue", "run", "go", "do it",
    "restart", "reboot", "start it",
    # Français
    "oui", "ouais", "bien sûr", "d'accord", "vas-y", "lance",
    "redémarre", "redémarrage", "démarre", "exécute", "fais-le",
    # Español
    "sí", "claro", "por supuesto", "vale", "adelante",
    "reinicia", "reiniciar", "arranca", "ejecuta", "hazlo",
    # Italiano
    "sì", "certo", "ovviamente", "d'accordo", "vai", "avvia",
    "riavvia", "riavvio", "esegui", "fallo",
    # Nederlands
    "ja", "jawel", "natuurlijk", "akkoord", "doorgaan", "ga",
    "herstart", "herstarten", "starten", "voer uit", "doe het",
    # Polski
    "tak", "jasne", "oczywiście", "zgoda", "dalej", "uruchom",
    "zrestartuj", "restartuj", "wykonaj", "rób to",
    # Português
    "sim", "claro", "com certeza", "concordo", "avançar", "vai",
    "reiniciar", "reinicia", "executa", "faça",
    # 日本語
    "はい", "うん", "もちろん", "お願いします", "どうぞ",
    "再起動", "リスタート", "実行", "やり直し",
    # 中文
    "是", "好", "当然", "确认", "继续", "可以",
    "重启", "重新启动", "执行", "开始",
)

_MULTILINGUAL_CANCEL_HINTS: tuple[str, ...] = (
    # Deutsch
    "nein", "nicht", "abbrech", "abbruch", "stopp", "halt", "stop",
    "lass", "lieber nicht", "kein",
    # English
    "no", "nope", "cancel", "abort", "stop", "halt", "don't",
    # Français
    "non", "annul", "arrêt", "arrête", "stop", "pas",
    # Español
    "no", "cancel", "anul", "para", "deten", "alto", "parar",
    # Italiano
    "no", "annull", "ferm", "stop", "basta", "non farlo",
    # Nederlands
    "nee", "annuleer", "afbrek", "stop", "halt", "niet doen",
    # Polski
    "nie", "anuluj", "przerwij", "stop", "zatrzymaj", "nie rób",
    # Português
    "não", "cancelar", "anular", "parar", "pare", "interromp",
    # 日本語
    "いいえ", "キャンセル", "中止", "停止", "やめて",
    # 中文
    "不", "不要", "取消", "中止", "停止", "算了",
)


_STRONG_CONFIRM_WORDS: frozenset[str] = frozenset({
    "yes", "ja", "jo", "jep", "jup", "jawohl", "klar", "ok", "okay",
    "bestätige", "bestätig", "confirm", "proceed", "sure", "absolutely",
    "go", "mach", "los", "yep", "yup", "y", "d'accord", "vas-y", "oui",
    "claro", "vale", "sì", "certo", "vai", "jawel", "natuurlijk",
    "akkoord", "doorgaan", "tak", "jasne", "zgoda", "dalej", "sim",
    "はい", "好", "可以",
})

_WEAK_CONFIRM_KEYWORDS: frozenset[str] = frozenset({
    "starte", "start", "restart", "reboot", "neustart", "neustarten",
    "run", "execute", "do", "doit", "esegui", "hazlo", "执行",
    "weiter", "continue", "avançar", "continuar",
})

_CANCEL_WORDS: frozenset[str] = frozenset({
    "no", "nope", "nein", "abbrech", "cancel", "stop", "halt",
    "non", "nie", "annuleer", "anuluj", "いいえ", "不要",
})

_FACTUAL_TERMS: frozenset[str] = frozenset({
    "policy", "config", "log", "logs", "show", "list", "status",
    "describe", "what", "why", "how", "explain", "wo", "was", "wie",
    "warum", "erkläre", "zeig", "liste", "get", "fetch",
    "retrieve", "hol", "finde",
})


def _is_affirmative_confirmation(message: str) -> bool:
    if not message:
        return False
    text = message.strip()
    lower = text.lower()
    tokens = set(re.findall(r"[\w'-]+", lower))

    if tokens & _STRONG_CONFIRM_WORDS:
        if tokens & _CANCEL_WORDS:
            return False
        return True

    if not (tokens & _WEAK_CONFIRM_KEYWORDS):
        return False
    if len(text) > 50:
        return False
    if tokens & _FACTUAL_TERMS:
        return False
    return True


router = APIRouter(prefix="/api/chat", tags=["Chat"])


def _tenant_session_id(request: Request, session_id: str) -> str:
    auth_ctx = resolve_request_auth(request)
    tenant_id = auth_tenant_id(auth_ctx)
    return f"{tenant_id}:{session_id}"


async def _check_session_access(
    request: Request, scoped_session_id: str
) -> None:
    """Prüft, ob der authentifizierte User Zugriff auf die Session hat (IDOR-Schutz).

    Regeln:
    - Anonymer Request: nur erlaubt, wenn die Session noch keinen Owner hat
      (z. B. direkter Erstaufruf vor Login-Set). Sonst 401.
    - Authentifizierter Request: muss entweder Owner sein, oder die Session
      hat noch keinen Owner (dann wird der aktuelle User als Owner gesetzt).

    Raises HTTPException 401 (anonymous + existing owner) oder 403 (mismatch).
    """
    redis = get_redis()
    auth_ctx = resolve_request_auth(request)
    username = str(auth_ctx.get("username")) if auth_ctx else None
    existing_owner = await redis.get_session_owner(scoped_session_id)

    if username is None:
        if existing_owner is not None:
            # Anonymer Request, aber Session ist bereits claimed → blockieren
            raise HTTPException(
                status_code=401,
                detail="Authentifizierung erforderlich für Zugriff auf diese Session.",
            )
        return  # Anonym + ownerlos = OK (sollte nicht vorkommen, aber fail-open)

    # Authentifizierter User
    if existing_owner is None:
        # Erstzugriff: aktuellen User als Owner setzen
        await redis.set_session_owner(scoped_session_id, username)
        return
    if existing_owner != username:
        # Owner-Mismatch: IDOR-Versuch
        raise HTTPException(
            status_code=403,
            detail="Kein Zugriff auf diese Session.",
        )


def _parse_sentinel(response_text: str) -> dict:
    """Extrahiert Tool-Infos aus dem Safeguard-Sentinel-String."""
    try:
        return json.loads(response_text[len(_TOOL_SAFEGUARD_SENTINEL):])
    except json.JSONDecodeError:
        return {}


def _safe_action_category(value: object) -> ActionCategory:
    try:
        return ActionCategory(str(value or "STATE_CHANGING"))
    except ValueError:
        return ActionCategory.STATE_CHANGING


def _tool_confirmation_response(info: dict, session_id: str) -> ChatResponse:
    """Baut eine ChatResponse für eine Tool-Level Safeguard Confirmation."""
    response = _tool_confirmation_text(info)
    return ChatResponse(
        response=response,
        module_used=None,
        session_id=session_id,
        confirmation_required=True,
        safeguard=info,
        timestamp=datetime.now(timezone.utc),
    )


def _tool_confirmation_text(info: dict) -> str:
    """Baut den sichtbaren Chat-Text für eine Tool-Level Confirmation."""
    tool_name = info.get("tool_name", "unbekannt")
    category = info.get("category", "UNKNOWN")
    rationale = info.get("rationale", "")
    args_preview = str(info.get("tool_args_preview") or "").strip()
    args_block_de = f"**Parameter:** `{args_preview}`\n" if args_preview else ""
    args_block_en = f"**Arguments:** `{args_preview}`\n" if args_preview else ""
    return _t(
        f"⚠️ **Tool-Bestätigung erforderlich**\n\n"
        f"Der Agent möchte folgendes Tool ausführen:\n\n"
        f"**Tool:** `{tool_name}`\n"
        f"{args_block_de}"
        f"**Kategorie:** {category}\n"
        f"**Begründung:** {rationale}\n\n"
        f"Sende die Nachricht erneut mit `confirmed: true` um fortzufahren.",
        f"⚠️ **Tool Confirmation Required**\n\n"
        f"The agent wants to execute a tool:\n\n"
        f"**Tool:** `{tool_name}`\n"
        f"{args_block_en}"
        f"**Category:** {category}\n"
        f"**Rationale:** {rationale}\n\n"
        f"Resend the message with `confirmed: true` to proceed.",
    )


def _message_confirmation_text(sg_result) -> str:
    """Baut den sichtbaren Chat-Text für eine Message-Level Confirmation."""
    return _t(
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
    )


_OP_JOURNAL_EXCEPTIONS = (
    KeyError,
    ValueError,
    RuntimeError,
    OSError,
    asyncio.TimeoutError,
    json.JSONDecodeError,
)


async def _resolve_confirmed_message(
    body: ChatRequest,
    scoped_session_id: str,
    redis,
    op_journal,
) -> tuple[str, bool, str | None, str | None]:
    """
    Akzeptiert kurze Textbestaetigungen wie "ok" nur, wenn fuer die Session
    bereits eine SafeGuard-Aktion pending ist.

    Returns:
        (effective_message, confirmed, pending_tx_id, pipeline_id)
        pipeline_id ist gesetzt, wenn eine pausierte Pipeline bestätigt werden soll
        (source="pipeline_safeguard"). In diesem Fall muss der Aufrufer die Pipeline
        via engine.resume(pipeline_id) fortsetzen statt den LLM-Pfad zu nehmen.
    """
    if body.confirmed:
        pending_tx_id = await op_journal.get_pending_for_session(scoped_session_id)
        if pending_tx_id:
            try:
                tx = await op_journal.get(pending_tx_id)
                if tx.get("source") == "chat_safeguard" and tx.get("text"):
                    return tx["text"], True, pending_tx_id, None
                if tx.get("source") == "pipeline_safeguard":
                    pipeline_id = _extract_pipeline_id_from_tx(tx)
                    if pipeline_id:
                        return body.message, True, pending_tx_id, pipeline_id
            except _OP_JOURNAL_EXCEPTIONS as exc:
                logger.warning("Pending SafeGuard transaction lookup failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Ungültige Bestätigung: Keine ausstehende Aktion für diese Session.",
        )

    if not is_bot_confirmation(body.message):
        # Fallback: Wenn eine chat_safeguard-tx pending ist und die User-Antwort
        # wie eine Bestätigung wirkt (z.B. "Ja, starte USR-VM-05 neu"), behandle
        # sie als Confirm-Versuch. Sonst verliert der LLM den Kontext.
        # Strikt wortgrenzenbasiert, um False-Positives bei langen fachlichen
        # Fragen zu vermeiden (z.B. "What's the restart policy?" darf KEIN
        # Confirm für "delete pod xyz?" triggern).
        if _is_affirmative_confirmation(body.message):
            pending_tx_id_fb = await op_journal.get_pending_for_session(scoped_session_id)
            if pending_tx_id_fb:
                try:
                    tx = await op_journal.get(pending_tx_id_fb)
                    if tx.get("source") == "chat_safeguard" and tx.get("text"):
                        return tx["text"], True, pending_tx_id_fb, None
                except _OP_JOURNAL_EXCEPTIONS as exc:
                    logger.warning("Pending SafeGuard fallback lookup failed: %s", exc)
        return body.message, False, None, None

    tool_pending_raw = await redis.connection.get(
        f"ninko:safeguard_tool_pending:{scoped_session_id}"
    )
    pending_tx_id = await op_journal.get_pending_for_session(scoped_session_id)
    if not tool_pending_raw and not pending_tx_id:
        return body.message, False, None, None

    effective_message = body.message
    pipeline_id: str | None = None
    if pending_tx_id and not tool_pending_raw:
        try:
            tx = await op_journal.get(pending_tx_id)
        except _OP_JOURNAL_EXCEPTIONS as exc:
            logger.warning("Pending SafeGuard transaction lookup failed: %s", exc)
            tx = {}
        source = tx.get("source")
        if source == "chat_safeguard" and tx.get("text"):
            effective_message = tx["text"]
        elif source == "pipeline_safeguard":
            pipeline_id = _extract_pipeline_id_from_tx(tx)
            if pipeline_id:
                effective_message = tx.get("text", body.message)

    return effective_message, True, pending_tx_id, pipeline_id


def _extract_pipeline_id_from_tx(tx: dict) -> str | None:
    """Liest pipeline_id aus dem JSON-kodierten metadata-Feld einer op_journal-Transaktion."""
    import json as _json
    raw_meta = tx.get("metadata", "")
    if not raw_meta:
        return None
    try:
        meta = _json.loads(raw_meta)
    except (TypeError, ValueError):
        return None
    if not isinstance(meta, dict):
        return None
    pid = meta.get("pipeline_id")
    return str(pid) if pid else None


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


async def _stream_pipeline_resume(
    request: Request,
    body: ChatRequest,
    scoped_session_id: str,
    request_id: str,
    message_id: str,
    pipeline_id: str,
    current_tx_id: str | None,
    effective_message: str,
    op_journal,
    redis,
) -> AsyncGenerator[str, None]:
    """SSE-Pfad: Setzt eine pausierte Pipeline fort, ohne den LLM zu bemühen."""
    from core.pipeline_engine import get_pipeline_engine, PipelineStatus
    from agents.base_agent import _t

    if current_tx_id:
        await op_journal.mark_confirmed(current_tx_id)

    await status_bus.emit_trace(
        scoped_session_id,
        phase="pipeline_resume",
        label="Pipeline wird fortgesetzt",
        data={"pipeline_id": pipeline_id},
        status="running",
    )

    engine = get_pipeline_engine()
    try:
        # Step-weise: bestätigt nur den wartenden Step. Weitere confirm-Steps → erneuter Pause.
        result = await engine.resume(pipeline_id, scoped_session_id)
    except ValueError as exc:
        await status_bus.emit_trace(
            scoped_session_id,
            phase="pipeline_resume",
            label="Pipeline-Resume fehlgeschlagen",
            detail=str(exc),
            status="error",
        )
        await op_journal.clear_pending_for_session(scoped_session_id)
        await status_bus.done(scoped_session_id)
        yield _stream_frame(
            "final",
            request_id,
            message_id,
            response=_t(
                f"⚠️ Pipeline-Resume fehlgeschlagen: {exc}",
                f"⚠️ Pipeline resume failed: {exc}",
            ),
            meta={
                "confirmation_required": False,
                "session_id": body.session_id,
            },
        )
        return

    # Pipeline pausiert erneut für den nächsten bestätigungspflichtigen Step.
    if result.status == PipelineStatus.AWAITING_CONFIRMATION:
        await status_bus.done(scoped_session_id)
        awaiting = next(
            (s for s in result.steps if s.status.value == "awaiting_confirmation"),
            None,
        )
        yield _stream_frame(
            "final",
            request_id,
            message_id,
            response=_t(
                f"Weiterer Schritt benötigt Bestätigung: **{awaiting.module if awaiting else '?'}**. "
                "Bitte bestätige, um fortzufahren.",
                f"Another step requires confirmation: **{awaiting.module if awaiting else '?'}**. "
                "Please confirm to continue.",
            ),
            meta={
                "confirmation_required": True,
                "pipeline_id": pipeline_id,
                "session_id": body.session_id,
            },
        )
        return

    markdown = result.to_markdown()
    if result.status == PipelineStatus.FAILED:
        response_text = _t(
            f"Pipeline fehlgeschlagen: {result.error}\n\n{markdown}",
            f"Pipeline failed: {result.error}\n\n{markdown}",
        )
    else:
        response_text = markdown or _t(
            "Pipeline abgeschlossen (keine Ausgabe).",
            "Pipeline completed (no output).",
        )

    if current_tx_id:
        await op_journal.mark_executed(
            current_tx_id,
            module=result.steps[0].module if result.steps else None,
            summary=response_text[:600],
        )
    await op_journal.clear_pending_for_session(scoped_session_id)
    await status_bus.done(scoped_session_id)

    yield _stream_frame(
        "final",
        request_id,
        message_id,
        response=response_text,
        meta={
            "confirmation_required": False,
            "pipeline_id": pipeline_id,
            "pipeline_status": result.status.value,
            "session_id": body.session_id,
            "module_used": None,
            "routing_confidence": None,
        },
    )


async def _run_pipeline_resume(
    body: ChatRequest,
    scoped_session_id: str,
    pipeline_id: str,
    current_tx_id: str | None,
    effective_message: str,
    op_journal,
    redis,
    request: Request,
):
    """JSON-Pfad: Setzt eine pausierte Pipeline fort und gibt ein ChatResponse zurück."""
    from core.pipeline_engine import get_pipeline_engine, PipelineStatus
    from core.context_manager import get_context_manager
    from agents.base_agent import _t
    from schemas.chat import ChatResponse

    if current_tx_id:
        await op_journal.mark_confirmed(current_tx_id)

    engine = get_pipeline_engine()
    try:
        # Step-weise: bestätigt nur den wartenden Step. Weitere confirm-Steps → erneuter Pause.
        result = await engine.resume(pipeline_id, scoped_session_id)
    except ValueError as exc:
        await op_journal.clear_pending_for_session(scoped_session_id)
        await status_bus.done(scoped_session_id)
        return ChatResponse(
            response=_t(
                f"⚠️ Pipeline-Resume fehlgeschlagen: {exc}",
                f"⚠️ Pipeline resume failed: {exc}",
            ),
            module_used=None,
            session_id=body.session_id,
            timestamp=datetime.now(timezone.utc),
        )

    # Pipeline pausiert erneut für den nächsten bestätigungspflichtigen Step.
    if result.status == PipelineStatus.AWAITING_CONFIRMATION:
        await status_bus.done(scoped_session_id)
        awaiting = next(
            (s for s in result.steps if s.status.value == "awaiting_confirmation"),
            None,
        )
        return ChatResponse(
            response=_t(
                f"Weiterer Schritt benötigt Bestätigung: **{awaiting.module if awaiting else '?'}**. "
                "Bitte bestätige, um fortzufahren.",
                f"Another step requires confirmation: **{awaiting.module if awaiting else '?'}**. "
                "Please confirm to continue.",
            ),
            module_used=None,
            session_id=body.session_id,
            confirmation_required=True,
            safeguard={
                "source": "pipeline_safeguard",
                "pipeline_id": pipeline_id,
                "module": awaiting.module if awaiting else "",
                "step_index": awaiting.step_index if awaiting else None,
            },
            timestamp=datetime.now(timezone.utc),
        )

    markdown = result.to_markdown()
    if result.status == PipelineStatus.FAILED:
        response_text = _t(
            f"Pipeline fehlgeschlagen: {result.error}\n\n{markdown}",
            f"Pipeline failed: {result.error}\n\n{markdown}",
        )
    else:
        response_text = markdown or _t(
            "Pipeline abgeschlossen (keine Ausgabe).",
            "Pipeline completed (no output).",
        )

    if current_tx_id:
        await op_journal.mark_executed(
            current_tx_id,
            module=result.steps[0].module if result.steps else None,
            summary=response_text[:600],
        )
    await op_journal.clear_pending_for_session(scoped_session_id)

    ctx_mgr = get_context_manager()
    await redis.store_chat_message(
        session_id=scoped_session_id, role="user", content=effective_message
    )
    await redis.store_chat_message(
        session_id=scoped_session_id, role="assistant", content=response_text
    )
    updated_history = await redis.get_chat_history(scoped_session_id)
    budget = ctx_mgr.get_budget_info(updated_history)

    await status_bus.done(scoped_session_id)
    return ChatResponse(
        response=response_text,
        module_used=None,
        session_id=body.session_id,
        context_budget=budget,
        compacted=False,
        timestamp=datetime.now(timezone.utc),
    )


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
    effective_message, confirmed, pending_tx_id, resume_pipeline_id = await _resolve_confirmed_message(
        body, scoped_session_id, redis, op_journal
    )
    if pending_tx_id:
        current_tx_id = pending_tx_id

    if resume_pipeline_id:
        async for frame in _stream_pipeline_resume(
            request, body, scoped_session_id, request_id, message_id,
            resume_pipeline_id, current_tx_id, effective_message,
            op_journal, redis,
        ):
            yield frame
        return

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
                "confirmed": confirmed,
                "force_module": body.force_module,
                "message_length": len(effective_message or ""),
            },
            status="running",
        )
        # ── Tool-Level Safeguard: Resume nach Bestätigung ───────────────────
        if confirmed:
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
                            category=_safe_action_category(_pending_info.get("category")),
                            text=effective_message,
                            session_id=scoped_session_id,
                            agent_id=_pending_info.get("agent", ""),
                            tool_name=_pending_info.get("tool_name", ""),
                            outcome="confirmed",
                            rationale=_pending_info.get("rationale", ""),
                        )

                response_text, did_compact = (
                    await orchestrator.resume_tool_execution(scoped_session_id)
                )

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
                    yield _stream_frame(
                        "final",
                        request_id,
                        message_id,
                        response=_tool_confirmation_text(info),
                        meta=meta,
                    )
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
        if not goto_stream_response and safeguard and not confirmed:
            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="Nachricht wird durch SafeGuard geprüft",
                data={"message_length": len(effective_message or "")},
                status="running",
            )
            sg_result = await safeguard.check(effective_message, session_id=scoped_session_id)
            if sg_result.requires_confirmation:
                await status_bus.emit_trace(
                    scoped_session_id,
                    phase="safeguard",
                    label="SafeGuard fordert Bestätigung",
                    detail=sg_result.rationale,
                    data={"category": sg_result.category.value},
                )
                current_tx_id = await op_journal.create_pending(
                    session_id=scoped_session_id,
                    text=effective_message,
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
                yield _stream_frame(
                    "final",
                    request_id,
                    message_id,
                    response=_message_confirmation_text(sg_result),
                    meta=meta,
                )
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
                yield _stream_frame(
                    "final",
                    request_id,
                    message_id,
                    response=response_text,
                    meta=meta,
                )
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
            await _telemetry.check_and_record_correction(
                session_id=scoped_session_id,
                force_module=body.force_module,
                message=effective_message,
            )

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
                    message=effective_message,
                    chat_history=history,
                    session_id=scoped_session_id,
                    confirmed=confirmed,
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
            if not isinstance(route_result, tuple):
                logger.error(
                    "orchestrator.route() returned non-tuple type: %s", type(route_result)
                )
                raise TypeError(
                    f"Expected tuple, got: {type(route_result).__name__}"
                )
            if len(route_result) != 4:
                logger.error(
                    "orchestrator.route() returned tuple with wrong length: %d", len(route_result)
                )
                raise ValueError(
                    f"Expected 4 elements, got: {len(route_result)}"
                )
            response_text, module_used, did_compact, route_meta = route_result
            route_meta = route_meta or {}
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
                try:
                    token = token_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
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
                    text=effective_message,
                    category=category,
                    rationale=str(info.get("rationale", "")),
                    source="tool_safeguard",
                    module=module_used,
                    tool_name=str(info.get("tool_name", "")),
                    metadata={
                        "tool_signature": str(info.get("tool_signature", "")),
                        "tool_args_preview": str(info.get("tool_args_preview", "")),
                    },
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
                "routing_confidence": route_meta.get("routing_confidence"),
            }
            yield _stream_frame(
                "final",
                request_id,
                message_id,
                response=_tool_confirmation_text(info),
                meta=meta,
            )
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
            if await request.is_disconnected():
                raise asyncio.CancelledError()
            summary = route_meta.get("compaction_summary")
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
        if await request.is_disconnected():
            raise asyncio.CancelledError()
        await redis.store_chat_message(
            session_id=scoped_session_id,
            role="user",
            content=effective_message,
        )
        await redis.store_chat_message(
            session_id=scoped_session_id,
            role="assistant",
            content=response_text,
        )

        # Context-Budget
        updated_history = await redis.get_chat_history(scoped_session_id)
        budget = ctx_mgr.get_budget_info(updated_history)

        if current_tx_id:
            await op_journal.mark_executed(
                current_tx_id,
                module=module_used,
                summary=response_text[:600],
            )
            await op_journal.clear_pending_for_session(scoped_session_id)

        routing_confidence = route_meta.get("routing_confidence")

        # ── R12: Auto-Routing-Telemetrie ─────────────────────────────────────
        if not body.force_module and module_used and _telemetry:
            await _telemetry.record_auto_routing(
                session_id=scoped_session_id,
                module=module_used,
                tier=route_meta.get("tier_used", 0),
                confidence=routing_confidence,
                message=effective_message,
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
        # IDOR-Mitigation: nur der Owner darf Stream/History anfassen
        await _check_session_access(request, scoped_session_id)
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
    # IDOR-Mitigation: nur der Owner darf History/Ops lesen oder schreiben
    await _check_session_access(request, scoped_session_id)
    effective_message, confirmed, pending_tx_id, resume_pipeline_id = await _resolve_confirmed_message(
        body, scoped_session_id, redis, op_journal
    )
    if pending_tx_id:
        current_tx_id = pending_tx_id

    if resume_pipeline_id:
        return await _run_pipeline_resume(
            body, scoped_session_id, resume_pipeline_id, current_tx_id,
            effective_message, op_journal, redis, request,
        )

    # Status-Queue vorab erstellen (damit SSE-Consumer sofort lesen kann)
    status_bus.get_queue(scoped_session_id)
    await status_bus.emit_trace(
        scoped_session_id,
        phase="request",
        label="Chat-Verarbeitung gestartet",
        detail="JSON-Antwortpfad",
        data={
            "confirmed": confirmed,
            "force_module": body.force_module,
            "message_length": len(effective_message or ""),
        },
        status="running",
    )

    # ── Tool-Level Safeguard: Resume nach Bestätigung ─────────────────────────
    # Wenn confirmed=True und ein Tool-Call auf Bestätigung wartet → resumieren
    if confirmed:
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
                        category=_safe_action_category(_pending_info.get("category")),
                        text=effective_message,
                        session_id=scoped_session_id,
                        agent_id=_pending_info.get("agent", ""),
                        tool_name=_pending_info.get("tool_name", ""),
                        outcome="confirmed",
                        rationale=_pending_info.get("rationale", ""),
                    )
            except json.JSONDecodeError as exc:
                logger.warning("Audit-Log für Tool-Confirmation fehlgeschlagen: %s", exc)
            # Redis-Key nicht löschen — resume_tool_execution() macht das selbst
            response_text, did_compact = (
                await orchestrator.resume_tool_execution(scoped_session_id)
            )
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
                session_id=scoped_session_id, role="user", content=effective_message
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
    if safeguard and not confirmed:
        await status_bus.emit_trace(
            scoped_session_id,
            phase="safeguard",
            label="Nachricht wird durch SafeGuard geprüft",
            data={"message_length": len(effective_message or "")},
            status="running",
        )
        sg_result = await safeguard.check(effective_message, session_id=scoped_session_id)
        if sg_result.requires_confirmation:
            await status_bus.emit_trace(
                scoped_session_id,
                phase="safeguard",
                label="SafeGuard fordert Bestätigung",
                detail=sg_result.rationale,
                data={"category": sg_result.category.value},
            )
            current_tx_id = await op_journal.create_pending(
                session_id=scoped_session_id,
                text=effective_message,
                category=sg_result.category.value,
                rationale=sg_result.rationale,
                source="chat_safeguard",
            )
            sg_payload = sg_result.to_dict()
            if current_tx_id:
                sg_payload["transaction_id"] = current_tx_id
            await status_bus.done(scoped_session_id)
            return ChatResponse(
                response=_message_confirmation_text(sg_result),
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
        await _telemetry.check_and_record_correction(
            session_id=scoped_session_id,
            force_module=body.force_module,
            message=effective_message,
        )

    # Nachricht an Orchestrator routen
    await status_bus.emit_trace(
        scoped_session_id,
        phase="routing",
        label="Routing gestartet",
        data={"force_module": body.force_module},
        status="running",
    )
    response_text, module_used, did_compact, route_meta = await orchestrator.route(
        message=effective_message,
        chat_history=history,
        session_id=scoped_session_id,
        confirmed=confirmed,
        force_module=body.force_module,
    )
    route_meta = route_meta or {}
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
                text=effective_message,
                category=category,
                rationale=str(info.get("rationale", "")),
                source="tool_safeguard",
                module=module_used,
                tool_name=str(info.get("tool_name", "")),
                metadata={
                    "tool_signature": str(info.get("tool_signature", "")),
                    "tool_args_preview": str(info.get("tool_args_preview", "")),
                },
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
        summary = route_meta.get("compaction_summary")
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
        content=effective_message,
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

    routing_confidence = route_meta.get("routing_confidence")

    # ── R12: Auto-Routing-Ergebnis für Korrektur-Erkennung speichern ──────────
    if not body.force_module and module_used and _telemetry:
        await _telemetry.record_auto_routing(
            session_id=scoped_session_id,
            module=module_used,
            tier=route_meta.get("tier_used", 0),
            confidence=routing_confidence,
            message=effective_message,
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
    # IDOR-Mitigation: nur der Owner darf den Status-Stream dieser Session lesen
    await _check_session_access(request, scoped_session_id)
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
    # IDOR-Mitigation: nur der Owner darf History lesen (CWE-639)
    await _check_session_access(request, scoped_session_id)
    messages = await redis.get_chat_history(scoped_session_id)

    return ChatHistoryResponse(
        session_id=session_id,
        messages=[
            ChatMessage(role=m["role"], content=m["content"]) for m in messages
        ],
        total=len(messages),
    )


@router.delete("/history/{session_id}", response_model=SessionMessagesResponse)
async def clear_history(session_id: str, request: Request) -> SessionMessagesResponse:
    """Löscht die Chat-History einer Session."""
    redis = get_redis()
    scoped_session_id = _tenant_session_id(request, session_id)
    # IDOR-Mitigation: nur der Owner darf History löschen
    await _check_session_access(request, scoped_session_id)
    await redis.clear_chat_history(scoped_session_id)
    from core.agent_event_journal import get_agent_event_journal

    await get_agent_event_journal().delete_session(
        tenant_id=auth_tenant_id(resolve_request_auth(request)),
        session_id=scoped_session_id,
    )
    await redis.clear_session_owner(scoped_session_id)
    return SessionMessagesResponse(
        status="ok", session_id=session_id, message="History gelöscht."
    )


@router.put("/history/{session_id}", response_model=SessionMessagesResponse)
async def replace_history(
    session_id: str, body: HistoryUpdateRequest, request: Request
) -> SessionMessagesResponse:
    """Ersetzt die Chat-History einer Session vollständig (für Löschen/Retry)."""
    redis = get_redis()
    scoped_session_id = _tenant_session_id(request, session_id)
    # IDOR-Mitigation: nur der Owner darf History ersetzen
    await _check_session_access(request, scoped_session_id)
    await redis.clear_chat_history(scoped_session_id)
    stored = 0
    for msg in body.messages:
        if msg.content:  # Leerer Content wird übersprungen (analog zur alten Logik)
            await redis.store_chat_message(
                session_id=scoped_session_id, role=msg.role, content=msg.content
            )
            stored += 1
    return SessionMessagesResponse(status="ok", session_id=session_id, count=stored)


# ── UI History (persistente, geräteübergreifende Konversationsliste) ────────

@router.get("/ui-history")
async def get_ui_history(request: Request) -> dict:
    """Gibt alle gespeicherten Konversationen zurück (geräteübergreifend)."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    entries = await redis.ui_history_get_all(tenant_id=tenant_id)
    return {"conversations": entries}


@router.post("/ui-history", response_model=SessionMessagesResponse)
async def save_ui_history(
    body: UiHistoryEntry, request: Request
) -> SessionMessagesResponse:
    """Speichert oder aktualisiert einen Konversationseintrag."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    await redis.ui_history_save(body.model_dump(), tenant_id=tenant_id)
    return SessionMessagesResponse(status="ok")


@router.delete("/ui-history/{conv_id}", response_model=SessionMessagesResponse)
async def delete_ui_history(conv_id: str, request: Request) -> SessionMessagesResponse:
    """Löscht einen Konversationseintrag."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    await redis.ui_history_delete(conv_id, tenant_id=tenant_id)
    return SessionMessagesResponse(status="ok", session_id=conv_id)


@router.delete("/ui-history", response_model=SessionMessagesResponse)
async def delete_all_ui_history(request: Request) -> SessionMessagesResponse:
    """Löscht den gesamten Chatverlauf."""
    redis = get_redis()
    tenant_id = auth_tenant_id(resolve_request_auth(request))
    await redis.ui_history_clear_all(tenant_id=tenant_id)
    return SessionMessagesResponse(status="ok")
