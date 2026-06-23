"""
Ninko – Hauptanwendung (Entry Point).
Lädt Module dynamisch, registriert Routen, startet Monitor.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from cryptography.fernet import InvalidToken
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from core.config import get_settings
from core.module_registry import ModuleRegistry, set_registry
from agents.orchestrator import OrchestratorAgent, set_orchestrator
from agents.monitor_agent import MonitorAgent
from agents.scheduler_agent import SchedulerAgent
from api.routes_chat import router as chat_router
from api.routes_modules import router as modules_router
from api.routes_memory import router as memory_router
from api.routes_secrets import router as secrets_router
from api.routes_settings import router as settings_router
from api.routes_ws import router as ws_router
from api.routes_scheduler import router as schedules_router
from api.routes_plugins import router as plugins_router
from api.routes_connections import router as connections_router
from api.routes_agents import router as agents_router
from api.routes_workflows import router as workflows_router
from api.routes_logs import router as logs_router
from api.routes_transcription import router as transcription_router
from api.routes_tts import router as tts_router
from api.routes_image_gen import router as image_gen_router
from api.routes_skills import router as skills_router
from api.routes_safeguard import router as safeguard_router
from api.routes_safeguard_profiles import router as safeguard_profiles_router
from api.routes_safeguard_audit import router as safeguard_audit_router
from api.routes_auth import router as auth_router
from api.routes_auth import _is_trusted_proxy
from api.routes_themes import router as themes_router
from api.routes_operations import router as operations_router
from api.routes_knowledge_graph import router as knowledge_graph_router
from api.routes_alerts import router as alerts_router
from api.routes_subagent import router as subagent_router
from api.routes_audit import router as audit_router
from api.routes_metrics import router as metrics_router
from api.routes_routing import router as routing_router

# Logging konfigurieren
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s │ %(name)-30s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ninko.main")

# Gemeinsame Exceptions für Startup-Fehlerbehandlung
_MAIN_RECOVERABLE_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    ImportError,
    json.JSONDecodeError,
)

_SECRET_LOG_PATTERNS = (
    (re.compile(r"(https://api\.telegram\.org/bot)[^/\s\"']+"), r"\1<redacted>"),
    (
        re.compile(
            r"(?i)([?&](?:token|api_key|apikey|access_token|auth_token|password|secret)=)"
            r"[^&\s\"']+"
        ),
        r"\1<redacted>",
    ),
    (re.compile(r"(?i)(bearer\s+)[a-z0-9._~+/\-]+=*"), r"\1<redacted>"),
)


def _redact_log_text(value: str) -> str:
    redacted = value
    for pattern, replacement in _SECRET_LOG_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


class SecretRedactionFilter(logging.Filter):
    """Redacts credentials before console and Redis handlers format log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = _redact_log_text(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    key: _redact_log_text(value) if isinstance(value, str) else value
                    for key, value in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    _redact_log_text(value) if isinstance(value, str) else value
                    for value in record.args
                )
        return True


_secret_redaction_filter = SecretRedactionFilter()
for _handler in logging.getLogger().handlers:
    _handler.addFilter(_secret_redaction_filter)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from core.auth import (
    auth_tenant_id,
    is_active_api_token,
    module_access_allows,
    reset_current_tenant_id,
    resolve_request_auth_async,
    resolve_request_role,
    role_allows,
    set_current_tenant_id,
)
from core.api_security_policy import (
    extract_module_id_from_path,
    required_role_for_request,
)
from core.rate_limit import RedisRateLimiter
from core.rbac import RbacStore

# Redis-Log-Handler (nach Redis-Verfügbarkeit lazy)
from core.log_handler import RedisLogHandler as _RedisLogHandler

_redis_log_handler = _RedisLogHandler(level=logging.INFO)
_redis_log_handler.addFilter(_secret_redaction_filter)
root_logger = logging.getLogger()
if not any(isinstance(h, _RedisLogHandler) for h in root_logger.handlers):
    root_logger.addHandler(_redis_log_handler)


@asynccontextmanager
async def lifespan(app: FastAPI) -> object:
    """Application Lifespan – Startup und Shutdown."""
    logger.info("═" * 60)
    logger.info("  Ninko – IT-Operations AI-Agent wird gestartet…")
    logger.info("═" * 60)

    # ── LLM-Settings aus Redis wiederherstellen ──────────────
    # Prüft zuerst den neuen Multi-Provider-Key, dann den Legacy-Key.
    # Damit ist nach jedem Container-Neustart der konfigurierte Provider aktiv.
    try:
        from core.redis_client import get_redis as _get_redis_startup
        from api.routes_settings import (
            REDIS_KEY_LLM,
            REDIS_KEY_LLM_PROVIDERS,
            REDIS_KEY_EMBED_MODEL,
            REDIS_KEY_EMBED_PROVIDER,
            _reconfigure_llm,
            _apply_default_provider,
        )
        from schemas.settings import LlmSettings
        import json as _json
        import os as _os

        _redis_startup = _get_redis_startup()

        # ① Neues Multi-Provider-System hat Vorrang
        _providers_raw = await _redis_startup.connection.get(REDIS_KEY_LLM_PROVIDERS)
        if _providers_raw:
            _providers = _json.loads(_providers_raw)
            if _providers:
                _apply_default_provider(_providers)
                _default = next(
                    (p for p in _providers if p.get("is_default")), _providers[0]
                )
                logger.info(
                    "LLM-Provider aus Redis wiederhergestellt: %s (backend=%s, model=%s)",
                    _default.get("name"),
                    _default.get("backend"),
                    _default.get("model"),
                )
            else:
                logger.info(
                    "LLM-Provider-Liste in Redis ist leer – nutze Standard-Env-Vars."
                )
        else:
            # ② Fallback: Legacy Single-Provider-Key
            _llm_raw = await _redis_startup.connection.get(REDIS_KEY_LLM)
            if _llm_raw:
                _llm_data = _json.loads(_llm_raw)
                _llm_settings = LlmSettings(**_llm_data)
                _reconfigure_llm(_llm_settings)
                logger.info(
                    "LLM-Einstellungen aus Redis wiederhergestellt (Legacy): backend=%s",
                    _llm_settings.backend,
                )
            else:
                logger.info(
                    "Keine LLM-Einstellungen in Redis – nutze Standard-Env-Vars."
                )

        # ③ Globales Embedding-Modell aus Redis laden
        _embed_raw = await _redis_startup.connection.get(REDIS_KEY_EMBED_MODEL)
        if _embed_raw:
            _embed_model = (
                _embed_raw if isinstance(_embed_raw, str) else _embed_raw.decode()
            )
            _os.environ["EMBED_MODEL"] = _embed_model
            logger.info(
                "Embedding-Modell aus Redis wiederhergestellt: %s", _embed_model
            )

        # ④ Separaten Embedding-Provider aus Redis laden.
        # Ohne diesen Schritt fällt get_embeddings() nach einem Restart auf den
        # Chat-LLM-Endpoint zurück, der nicht zwingend /embeddings bereitstellt.
        _embed_provider_raw = await _redis_startup.connection.get(
            REDIS_KEY_EMBED_PROVIDER
        )
        if _embed_provider_raw:
            _embed_provider = _json.loads(_embed_provider_raw)
            if _embed_provider.get("use_custom"):
                _embed_backend = str(_embed_provider.get("backend") or "").strip()
                _embed_base_url = str(_embed_provider.get("base_url") or "").strip()
                _embed_api_key = str(_embed_provider.get("api_key") or "").strip()
                _embed_provider_model = str(_embed_provider.get("model") or "").strip()
                if _embed_backend:
                    _os.environ["EMBED_BACKEND"] = _embed_backend
                if _embed_base_url:
                    _os.environ["EMBED_BASE_URL"] = _embed_base_url
                if _embed_api_key:
                    _os.environ["EMBED_API_KEY"] = _embed_api_key
                if _embed_provider_model:
                    _os.environ["EMBED_MODEL"] = _embed_provider_model
                logger.info(
                    "Embedding-Provider aus Redis wiederhergestellt: backend=%s, model=%s, url=%s",
                    _embed_backend or "-",
                    _embed_provider_model or _os.environ.get("EMBED_MODEL", "-"),
                    _embed_base_url or "-",
                )
            else:
                for _key in ("EMBED_BACKEND", "EMBED_BASE_URL", "EMBED_API_KEY"):
                    _os.environ.pop(_key, None)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as _exc:
        logger.warning("LLM-Startup-Config konnte nicht geladen werden: %s", _exc)

    # ── Startup-Recovery für persistente Stores ──────────────────────────────
    try:
        from core.redis_client import get_redis as _get_redis_recovery
        from core.vault import get_vault
        from core.workflow_engine import sweep_orphan_workflow_runs

        vault_migrated = await get_vault().migrate_legacy_sqlite_secrets()
        if vault_migrated:
            logger.info("Vault-Startup-Migration: %d Legacy-Secrets re-encrypted.", vault_migrated)

        workflow_interrupted = await sweep_orphan_workflow_runs(_get_redis_recovery())
        if workflow_interrupted:
            logger.warning(
                "Workflow-Recovery: %d verwaiste laufende Runs als interrupted markiert.",
                workflow_interrupted,
            )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        InvalidToken,
        json.JSONDecodeError,
    ) as _recovery_exc:
        logger.warning("Startup-Recovery konnte nicht abgeschlossen werden: %s", _recovery_exc)

    # ── RBAC Bootstrap-Admin synchronisieren ──────────────────────────────────
    try:
        if settings.API_AUTH_ENABLED:
            bootstrap_password = (
                settings.ADMIN_PASSWORD or settings.BOOTSTRAP_ADMIN_PASSWORD
            )
            if bootstrap_password:
                rbac_store = RbacStore()
                # force_password=True nur bei BOOTSTRAP_ADMIN_PASSWORD (nicht ADMIN_PASSWORD):
                # Damit wird ein geändertes Bootstrap-Passwort beim nächsten Start übernommen,
                # aber selbst gesetzte Passwörter (via ADMIN_PASSWORD) bleiben erhalten.
                using_bootstrap = not bool(settings.ADMIN_PASSWORD)
                await rbac_store.bootstrap_admin_if_needed(
                    settings.ADMIN_USERNAME or "admin",
                    bootstrap_password,
                    force_password=using_bootstrap,
                    must_change_password=using_bootstrap,
                )
                if not settings.ADMIN_PASSWORD:
                    logger.warning(
                        "RBAC Bootstrap nutzt BOOTSTRAP_ADMIN_PASSWORD für User '%s'. "
                        "Bitte Passwort nach dem ersten Login ändern.",
                        settings.ADMIN_USERNAME or "admin",
                    )
                logger.info(
                    "RBAC Bootstrap-Admin synchronisiert: %s",
                    settings.ADMIN_USERNAME or "admin",
                )
            else:
                logger.warning(
                    "API_AUTH_ENABLED=true aber kein Bootstrap-Passwort konfiguriert."
                )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as _rbac_exc:
        logger.warning(
            "RBAC Bootstrap konnte nicht synchronisiert werden: %s", _rbac_exc
        )

    # ── STT + TTS + OCR Settings aus Redis wiederherstellen ───────────────────
    try:
        from api.routes_settings import REDIS_KEY_STT, REDIS_KEY_TTS, REDIS_KEY_OCR
        import json as _json2
        import os as _os2
        from core.redis_client import get_redis as _get_redis2

        _redis2 = _get_redis2()

        _stt_raw = await _redis2.connection.get(REDIS_KEY_STT)
        if _stt_raw:
            for _k, _v in _json2.loads(_stt_raw).items():
                _os2.environ[_k] = str(_v).lower() if isinstance(_v, bool) else str(_v)
            logger.info("STT-Settings aus Redis wiederhergestellt.")

        _tts_raw = await _redis2.connection.get(REDIS_KEY_TTS)
        if _tts_raw:
            for _k, _v in _json2.loads(_tts_raw).items():
                _os2.environ[_k] = str(_v).lower() if isinstance(_v, bool) else str(_v)
            logger.info("TTS-Settings aus Redis wiederhergestellt.")

        _ocr_raw = await _redis2.connection.get(REDIS_KEY_OCR)
        if _ocr_raw:
            for _k, _v in _json2.loads(_ocr_raw).items():
                _os2.environ[_k] = str(_v).lower() if isinstance(_v, bool) else str(_v)
            logger.info("OCR-Settings aus Redis wiederhergestellt.")
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as _exc2:
        logger.warning(
            "STT/TTS/OCR-Startup-Config konnte nicht geladen werden: %s", _exc2
        )

    # ── Module Discovery ──────────────────────────────
    registry = ModuleRegistry()
    registry.discover_and_load()
    registry.register_routes(app)
    app.state.registry = registry
    set_registry(registry)

    # ── Soul Manager laden ────────────────────────────
    from core.soul_manager import get_soul_manager

    soul_manager = get_soul_manager()
    soul_manager.load()
    await soul_manager.load_from_redis()

    # Modul-Souls auto-generieren (nur für Module ohne existierende Soul)
    for mod in registry.get_registered_modules().values():
        if not soul_manager.has_soul(mod.manifest.name):
            tool_names = [t.name for t in mod.agent.tools] if mod.agent else []
            soul_md = soul_manager.generate_module_soul(
                name=mod.manifest.name,
                display_name=mod.manifest.display_name,
                description=mod.manifest.description,
                tool_names=tool_names,
            )
            await soul_manager.save_soul(mod.manifest.name, soul_md)

    app.state.soul_manager = soul_manager

    # ── Skills laden ──────────────────────────────────
    from core.skills_manager import get_skills_manager

    skills_manager = get_skills_manager()
    skills_manager.load()
    app.state.skills_manager = skills_manager

    # ── Skill-Marketplace ────────────────────────────
    from core.skill_marketplace import get_skill_marketplace

    app.state.skill_marketplace = get_skill_marketplace()
    logger.info("SkillMarketplace initialisiert.")

    # ── Safeguard-Middleware ───────────────────────────
    try:
        from core.safeguard import SafeguardMiddleware
        from core.safeguard_profiles import SafeguardProfileStore
        from core.agent_config_store import AgentConfigStore
        from core.llm_factory import get_safeguard_openai_client

        _sg_client, _sg_model = get_safeguard_openai_client()

        # Profile-Store initialisieren und Built-ins seeden
        _sg_profile_store = SafeguardProfileStore()
        await _sg_profile_store.seed_builtins()

        # Aktive Profil-ID laden (mit Legacy-Migration "true"/"false" → "moderate"/"disabled")
        _sg_profile_id = await _sg_profile_store.migrate_legacy()

        safeguard = SafeguardMiddleware(
            client=_sg_client,
            model=_sg_model,
            timeout=settings.SAFEGUARD_TIMEOUT_SECONDS,
            enabled=(_sg_profile_id != "disabled"),
            agent_store=AgentConfigStore(),
            profile_store=_sg_profile_store,
        )
        safeguard._active_profile_id = _sg_profile_id
        app.state.safeguard = safeguard
        from agents.base_agent import set_global_safeguard

        set_global_safeguard(safeguard)
        logger.info(
            "Safeguard-Middleware initialisiert (Modell: %s, Profil: %s, Timeout: %.1fs).",
            _sg_model,
            _sg_profile_id,
            settings.SAFEGUARD_TIMEOUT_SECONDS,
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
    ) as _sg_exc:
        logger.warning(
            "Safeguard-Middleware konnte nicht initialisiert werden: %s", _sg_exc
        )
        app.state.safeguard = None

    # ── Knowledge Graph initialisieren ────────────────
    from core.knowledge_graph import get_knowledge_graph

    kg = await get_knowledge_graph()
    kg_stats = await kg.get_stats()
    logger.info(
        "Knowledge Graph bereit: %d nodes, %d edges, %d tenants",
        kg_stats.get("nodes", 0),
        kg_stats.get("edges", 0),
        kg_stats.get("tenants", 0),
    )

    # ── Dynamischer Agenten-Pool laden ────────────────
    from core.agent_pool import get_agent_pool

    agent_pool = get_agent_pool()
    await agent_pool.load_from_redis()
    app.state.agent_pool = agent_pool

    # ── Orchestrator ──────────────────────────────────
    orchestrator = OrchestratorAgent(registry)
    app.state.orchestrator = orchestrator
    set_orchestrator(orchestrator)

    # ── Routing-Telemetrie (R12) ──────────────────────
    from core.routing_telemetry import init_routing_telemetry
    from core.redis_client import get_redis as _get_redis_telemetry
    init_routing_telemetry(_get_redis_telemetry())

    # ── Monitor Agent (Background) ────────────────────
    monitor = MonitorAgent(registry)
    monitor_task = asyncio.create_task(monitor.start_loop())
    monitor_task.add_done_callback(
        lambda t: (
            logger.error("Monitor task ended with exception: %s", t.exception())
            if not t.cancelled() and t.exception() is not None
            else None
        )
    )
    app.state.monitor = monitor
    app.state.monitor_task = monitor_task

    # ── Scheduler Agent (Background) ──────────────────
    scheduler = SchedulerAgent(registry, orchestrator)
    scheduler_task = asyncio.create_task(scheduler.start_loop())
    scheduler_task.add_done_callback(
        lambda t: (
            logger.error("Scheduler task ended with exception: %s", t.exception())
            if not t.cancelled() and t.exception() is not None
            else None
        )
    )
    app.state.scheduler = scheduler
    app.state.scheduler_task = scheduler_task
    from agents.scheduler_agent import set_scheduler_agent
    set_scheduler_agent(scheduler)

    # ── Safeguard paused-agent cleanup (Background) ───
    safeguard = app.state.safeguard
    if safeguard:

        async def _sg_cleanup_loop() -> object:
            while True:
                await asyncio.sleep(60)
                try:
                    await safeguard.cleanup_paused_agents()
                except _MAIN_RECOVERABLE_EXCEPTIONS as exc:
                    logger.warning("sg_cleanup_loop: Fehler beim Cleanup: %s", exc)

        sg_cleanup_task = asyncio.create_task(_sg_cleanup_loop())
        sg_cleanup_task.add_done_callback(
            lambda t: (
                logger.error("sg_cleanup_loop unerwartet beendet: %s", t.exception())
                if not t.cancelled() and t.exception() is not None
                else None
            )
        )
        app.state.sg_cleanup_task = sg_cleanup_task
        logger.info("Safeguard paused-agent cleanup task started.")

    # ── Telegram Polling Bot (optional – catalog module) ──
    telegram_bot = None
    try:
        from modules.telegram.bot import init_telegram_bot as _init_tg

        telegram_bot = _init_tg(app)
        app.state.telegram_bot = telegram_bot
        await telegram_bot.start()
    except ModuleNotFoundError:
        # Telegram is a catalog module; only available when installed via Marketplace
        try:
            from plugins.telegram.bot import init_telegram_bot as _init_tg

            telegram_bot = _init_tg(app)
            app.state.telegram_bot = telegram_bot
            await telegram_bot.start()
        except ModuleNotFoundError:
            logger.info("Telegram-Bot nicht verfügbar (Modul nicht installiert)")

    # ── Message Hub (optional – catalog module) ───────
    # ── Message Hub (Core-Modul) ───────────────────────
    from modules.message_hub.hub import init_message_hub as _init_mh

    message_hub = _init_mh(app)
    app.state.message_hub = message_hub
    await message_hub.start()

    # ── Frontend Static Files ────────────────────────
    # MUST mount AFTER module routes, otherwise the catch-all
    # StaticFiles("/") will shadow /api/k8s/* etc.
    _possible_frontend = [
        Path(__file__).resolve().parent / "frontend",  # /app/frontend (Docker)
        Path(__file__).resolve().parent.parent / "frontend",  # ../frontend (local dev)
    ]
    for _fdir in _possible_frontend:
        if _fdir.is_dir():
            _frontend_dir = _fdir

            @app.get("/", include_in_schema=False)
            async def serve_index(request: Request) -> object:
                if settings.API_AUTH_ENABLED and resolve_request_role(request) is None:
                    return RedirectResponse(url="/login", status_code=302)
                response = FileResponse(str(_frontend_dir / "index.html"))
                response.headers["Cache-Control"] = (
                    "no-cache, no-store, must-revalidate"
                )
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response

            @app.get("/login", include_in_schema=False)
            async def serve_login(request: Request) -> object:
                if not settings.API_AUTH_ENABLED:
                    return RedirectResponse(url="/", status_code=302)
                if resolve_request_role(request) is not None:
                    return RedirectResponse(url="/", status_code=302)
                return FileResponse(str(_frontend_dir / "login.html"))

            app.mount("/static", StaticFiles(directory=str(_fdir)), name="static")
            app.mount(
                "/", StaticFiles(directory=str(_fdir), html=True), name="frontend"
            )
            logger.info("Frontend served from: %s", _fdir)
            break

    logger.info("═" * 60)
    logger.info("  Ninko bereit! Module: %d", len(registry.list_modules()))
    logger.info("═" * 60)

    yield

    # ── Shutdown ──────────────────────────────────────
    logger.info("Ninko wird heruntergefahren…")

    # MemoryQueue stoppen (Flush verbleibender Messages)
    from core.memory_queue import get_memory_queue

    memory_queue = get_memory_queue()
    await memory_queue.stop()

    # Telegram Bot stoppen (falls geladen)
    if telegram_bot is not None:
        await telegram_bot.stop()

    # Message Hub stoppen (falls geladen)
    if message_hub is not None:
        await message_hub.stop()

    await monitor.stop()
    monitor_task.cancel()
    await scheduler.stop()
    scheduler_task.cancel()
    sg_cleanup_task = getattr(app.state, "sg_cleanup_task", None)
    if sg_cleanup_task:
        sg_cleanup_task.cancel()

    from core.redis_client import get_redis

    redis = get_redis()
    await redis.close()

    logger.info("Ninko beendet.")


# ── FastAPI App ───────────────────────────────────────
app = FastAPI(
    title="Ninko",
    description="Modularer IT-Operations-AI-Agent",
    version="1.3.2",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────
_cors_origins = [
    o.strip() for o in (settings.CORS_ALLOW_ORIGINS or "").split(",") if o.strip()
]
if not _cors_origins:
    _cors_origins = ["http://localhost:8000", "http://127.0.0.1:8000"]

_cors_methods = [
    m.strip().upper()
    for m in (settings.CORS_ALLOW_METHODS or "").split(",")
    if m.strip()
]
if not _cors_methods:
    _cors_methods = ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]

_cors_headers = [
    h.strip() for h in (settings.CORS_ALLOW_HEADERS or "").split(",") if h.strip()
]
if not _cors_headers:
    _cors_headers = ["Authorization", "Content-Type", "X-API-Key"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=_cors_methods,
    allow_headers=_cors_headers,
)

if settings.API_RATE_LIMIT_ENABLED:
    _rate_limiter = RedisRateLimiter(
        per_minute=settings.API_RATE_LIMIT_PER_MINUTE,
        burst=settings.API_RATE_LIMIT_BURST,
    )
else:
    _rate_limiter = None


def _required_role_for_request(path: str, method: str) -> str | None:
    return required_role_for_request(path, method)


def _extract_module_id_from_path(path: str) -> str | None:
    return extract_module_id_from_path(path)


def _extract_api_key_from_request(request: Request) -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token
    return request.headers.get("X-API-Key", "").strip()


async def _is_active_user_api_token(username: str, raw_token: str) -> bool:
    # Delegates to core.auth so HTTP middleware and the WebSocket resolver share
    # one revocation check (single source of truth for the RBAC token state).
    return await is_active_api_token(username, raw_token)


@app.middleware("http")
async def api_security_middleware(request: Request, call_next) -> object:
    path = request.url.path
    tenant_token = None

    try:
        # Frontend-Auth-Guard (wenn Auth aktiviert):
        # / und /index.html sowie alle HTML-Routen hinter Login schützen.
        if settings.API_AUTH_ENABLED and not path.startswith("/api/"):
            public_non_api = (
                path == "/health"
                or path == "/login"
                or path.startswith("/static/")
                or path == "/favicon.ico"
            )
            if not public_non_api and resolve_request_role(request) is None:
                return RedirectResponse(url="/login", status_code=302)

        # API-only security/rate limiting
        if path.startswith("/api/"):
            # CWE-918: Validate X-Forwarded-For only from trusted proxies
            client_ip = request.client.host if request.client else "unknown"
            if request.client and _is_trusted_proxy(request.client.host):
                forwarded = request.headers.get("x-forwarded-for", "")
                if forwarded:
                    client_ip = forwarded.split(",", 1)[0].strip()

            auth_ctx = await resolve_request_auth_async(request)
            tenant_token = set_current_tenant_id(auth_tenant_id(auth_ctx))
            if auth_ctx and str(auth_ctx.get("auth_source", "")) == "api_token":
                raw_token = _extract_api_key_from_request(request)
                username = str(auth_ctx.get("username", "")).strip()
                if not await _is_active_user_api_token(username, raw_token):
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Missing or invalid API key."},
                    )
            if auth_ctx and bool(auth_ctx.get("password_change_required", False)):
                allowed_while_reset = {
                    "/api/auth/me",
                    "/api/auth/change-password",
                    "/api/auth/logout",
                }
                if path not in allowed_while_reset:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": "Password change required before accessing this endpoint."
                        },
                    )

            # Module frontend files are exempt — they are static assets loaded in bulk
            # on every page load (2 requests × N modules can exceed burst limit).
            _is_module_frontend = (
                re.match(r"^/api/modules/[^/]+/frontend/", path) is not None
            )

            if _rate_limiter is not None and not _is_module_frontend:
                allowed, retry_after = await _rate_limiter.allow(client_ip)
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={"detail": "Rate limit exceeded. Please retry later."},
                        headers={"Retry-After": str(retry_after)},
                    )

            required_role = _required_role_for_request(path, request.method)
            if required_role is not None:
                actual_role = auth_ctx.get("role") if auth_ctx else None
                if actual_role is None:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Missing or invalid API key."},
                    )
                if not role_allows(required_role, actual_role):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "Insufficient role for this operation."},
                    )

            # Module-level ACL (module routes only, no effect on core API routes)
            module_id = _extract_module_id_from_path(path)
            if module_id and settings.API_AUTH_ENABLED:
                if auth_ctx is None:
                    return JSONResponse(
                        status_code=401,
                        content={"detail": "Missing or invalid API key."},
                    )
                if not module_access_allows(auth_ctx, module_id, request.method):
                    return JSONResponse(
                        status_code=403,
                        content={"detail": f"Access denied for module '{module_id}'."},
                    )

        return await call_next(request)
    finally:
        if tenant_token is not None:
            reset_current_tenant_id(tenant_token)


# ── Cache Prevention Middleware ───────────────────────
@app.middleware("http")
async def add_no_cache_header(request: Request, call_next) -> object:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
    return response


# ── Security Headers Middleware ───────────────────────
# CSP als HTTP-Header (überlegen dem <meta>-Tag):
# - frame-ancestors wirkt nur als HTTP-Header, nicht als <meta>
# - 'unsafe-inline' bleibt für Scripts vorerst nötig, weil Modul-Frontends
#   weiterhin inline onclick/oninput/onkeydown und einzelne Inline-Scripts
#   verwenden. Entfernen erst nach vollständiger Modul-Migration.
_CSP = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    # data: für inline-generierte Bilder (base64), blob: für TTS-Audio-Blobs
    # https: für Bilder aus externen Quellen (Web-Search-Ergebnisse, Modul-Icons)
    "img-src 'self' data: blob: https:; "
    # wss: nur für verschlüsselte WebSocket-Verbindungen; ws: (unverschlüsselt)
    # wird für lokale Dev-Setups ohne TLS benötigt
    "connect-src 'self' wss: ws://localhost:* ws://127.0.0.1:*; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'; "
    "upgrade-insecure-requests;"
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next) -> object:
    response = await call_next(request)
    response.headers["Content-Security-Policy"] = _CSP
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Core-Routen ──────────────────────────────────────
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(themes_router)
app.include_router(modules_router)
app.include_router(memory_router)
app.include_router(audit_router)
app.include_router(metrics_router)
app.include_router(secrets_router)
app.include_router(settings_router)
app.include_router(ws_router)
app.include_router(schedules_router)
app.include_router(plugins_router)
app.include_router(connections_router)
app.include_router(agents_router)
app.include_router(workflows_router)
app.include_router(logs_router)
app.include_router(transcription_router)
app.include_router(tts_router)
app.include_router(image_gen_router)
app.include_router(skills_router)
app.include_router(safeguard_router)
app.include_router(safeguard_profiles_router)
app.include_router(safeguard_audit_router)
app.include_router(operations_router)
app.include_router(knowledge_graph_router)
app.include_router(alerts_router)
app.include_router(subagent_router, prefix="/api/subagent")
app.include_router(routing_router)


# ── Health Endpoint ──────────────────────────────────
# NOTE: Must be registered BEFORE the catch-all static mount
@app.get("/health")
async def health() -> object:
    """Basis Health-Check."""
    return {
        "status": "ok",
        "service": "ninko",
        "version": "1.3.4",
    }
