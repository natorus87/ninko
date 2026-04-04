"""
Ninko – Hauptanwendung (Entry Point).
Lädt Module dynamisch, registriert Routen, startet Monitor.
"""

from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

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
from api.routes_themes import router as themes_router
from api.routes_operations import router as operations_router

# Logging konfigurieren
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s │ %(name)-30s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("ninko.main")

from core.auth import (
    ROLE_ADMIN,
    ROLE_READ,
    ROLE_WRITE,
    module_access_allows,
    resolve_request_auth,
    resolve_request_role,
    role_allows,
)
from core.rate_limit import InMemoryRateLimiter
from core.rbac import RbacStore

# Redis-Log-Handler (nach Redis-Verfügbarkeit lazy)
from core.log_handler import RedisLogHandler as _RedisLogHandler
_redis_log_handler = _RedisLogHandler(level=logging.INFO)
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
            REDIS_KEY_LLM, REDIS_KEY_LLM_PROVIDERS, REDIS_KEY_EMBED_MODEL,
            _reconfigure_llm, _apply_default_provider,
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
                _default = next((p for p in _providers if p.get("is_default")), _providers[0])
                logger.info(
                    "LLM-Provider aus Redis wiederhergestellt: %s (backend=%s, model=%s)",
                    _default.get("name"), _default.get("backend"), _default.get("model"),
                )
            else:
                logger.info("LLM-Provider-Liste in Redis ist leer – nutze Standard-Env-Vars.")
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
                logger.info("Keine LLM-Einstellungen in Redis – nutze Standard-Env-Vars.")

        # ③ Globales Embedding-Modell aus Redis laden
        _embed_raw = await _redis_startup.connection.get(REDIS_KEY_EMBED_MODEL)
        if _embed_raw:
            _embed_model = _embed_raw if isinstance(_embed_raw, str) else _embed_raw.decode()
            _os.environ["EMBED_MODEL"] = _embed_model
            logger.info("Embedding-Modell aus Redis wiederhergestellt: %s", _embed_model)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError, json.JSONDecodeError) as _exc:
        logger.warning("LLM-Startup-Config konnte nicht geladen werden: %s", _exc)

    # ── RBAC Bootstrap-Admin synchronisieren ──────────────────────────────────
    try:
        if settings.API_AUTH_ENABLED and settings.ADMIN_PASSWORD:
            rbac_store = RbacStore()
            await rbac_store.bootstrap_admin_if_needed(
                settings.ADMIN_USERNAME or "admin",
                settings.ADMIN_PASSWORD,
            )
            logger.info("RBAC Bootstrap-Admin synchronisiert: %s", settings.ADMIN_USERNAME or "admin")
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError, json.JSONDecodeError) as _rbac_exc:
        logger.warning("RBAC Bootstrap konnte nicht synchronisiert werden: %s", _rbac_exc)

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
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError, json.JSONDecodeError) as _exc2:
        logger.warning("STT/TTS/OCR-Startup-Config konnte nicht geladen werden: %s", _exc2)

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
            _sg_model, _sg_profile_id, settings.SAFEGUARD_TIMEOUT_SECONDS,
        )
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as _sg_exc:
        logger.warning("Safeguard-Middleware konnte nicht initialisiert werden: %s", _sg_exc)
        app.state.safeguard = None

    # ── Dynamischer Agenten-Pool laden ────────────────
    from core.agent_pool import get_agent_pool
    agent_pool = get_agent_pool()
    await agent_pool.load_from_redis()
    app.state.agent_pool = agent_pool

    # ── Orchestrator ──────────────────────────────────
    orchestrator = OrchestratorAgent(registry)
    app.state.orchestrator = orchestrator
    set_orchestrator(orchestrator)

    # ── Monitor Agent (Background) ────────────────────
    monitor = MonitorAgent(registry)
    monitor_task = asyncio.create_task(monitor.start_loop())
    app.state.monitor = monitor

    # ── Scheduler Agent (Background) ──────────────────
    scheduler = SchedulerAgent(registry, orchestrator)
    scheduler_task = asyncio.create_task(scheduler.start_loop())
    app.state.scheduler = scheduler

    # ── Safeguard paused-agent cleanup (Background) ───
    safeguard = app.state.safeguard
    if safeguard:
        async def _sg_cleanup_loop() -> object:
            while True:
                await asyncio.sleep(60)
                try:
                    await safeguard.cleanup_paused_agents()
                except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError):
                    pass
        sg_cleanup_task = asyncio.create_task(_sg_cleanup_loop())
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

    # ── Frontend Static Files ────────────────────────
    # MUST mount AFTER module routes, otherwise the catch-all
    # StaticFiles("/") will shadow /api/k8s/* etc.
    _possible_frontend = [
        Path(__file__).resolve().parent / "frontend",        # /app/frontend (Docker)
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
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
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
            app.mount("/", StaticFiles(directory=str(_fdir), html=True), name="frontend")
            logger.info("Frontend served from: %s", _fdir)
            break

    logger.info("═" * 60)
    logger.info("  Ninko bereit! Module: %d", len(registry.list_modules()))
    logger.info("═" * 60)

    yield

    # ── Shutdown ──────────────────────────────────────
    logger.info("Ninko wird heruntergefahren…")
    
    # Telegram Bot stoppen (falls geladen)
    if telegram_bot is not None:
        await telegram_bot.stop()
    
    await monitor.stop()
    monitor_task.cancel()
    await scheduler.stop()
    scheduler_task.cancel()
    if safeguard:
        sg_cleanup_task.cancel()

    from core.redis_client import get_redis
    redis = get_redis()
    await redis.close()

    logger.info("Ninko beendet.")


# ── FastAPI App ───────────────────────────────────────
app = FastAPI(
    title="Ninko",
    description="Modularer IT-Operations-AI-Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────
_cors_origins = [
    o.strip()
    for o in (settings.CORS_ALLOW_ORIGINS or "").split(",")
    if o.strip()
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
    h.strip()
    for h in (settings.CORS_ALLOW_HEADERS or "").split(",")
    if h.strip()
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
    _rate_limiter = InMemoryRateLimiter(
        per_minute=settings.API_RATE_LIMIT_PER_MINUTE,
        burst=settings.API_RATE_LIMIT_BURST,
    )
else:
    _rate_limiter = None


def _required_role_for_request(path: str, method: str) -> str | None:
    # Public/health endpoints
    if path == "/health":
        return None

    if not path.startswith("/api/"):
        return None

    if path == "/api/auth/login" or path == "/api/auth/logout" or path == "/api/auth/me":
        return None
    if path.startswith("/api/auth/"):
        return ROLE_ADMIN

    method_u = method.upper()
    is_mutating = method_u in {"POST", "PUT", "PATCH", "DELETE"}

    # Sensitive read endpoints
    if path.startswith("/api/secrets"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/logs"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/ws"):
        return ROLE_READ
    if path.startswith("/api/plugins"):
        return ROLE_ADMIN
    if path.startswith("/api/safeguard"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/settings"):
        return ROLE_ADMIN if is_mutating else ROLE_READ
    if path.startswith("/api/connections"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/themes"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/agents"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/workflows"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/memory"):
        return ROLE_WRITE if is_mutating else ROLE_READ
    if path.startswith("/api/modules"):
        return ROLE_READ

    # Default for remaining API endpoints:
    # - writes require write role
    # - reads are open unless covered above
    if is_mutating:
        return ROLE_WRITE
    return None


_CORE_API_PREFIXES = {
    "auth",
    "themes",
    "modules",
    "memory",
    "secrets",
    "settings",
    "ws",
    "safeguard",
    "scheduler",
    "plugins",
    "connections",
    "agents",
    "workflows",
    "logs",
    "transcription",
    "tts",
    "image-gen",
    "skills",
    "operations",
    "chat",
    "images",
}


def _extract_module_id_from_path(path: str) -> str | None:
    if not path.startswith("/api/"):
        return None
    parts = [p for p in path.split("/") if p]
    if len(parts) < 2:
        return None
    first = parts[1].strip().lower()
    if first in _CORE_API_PREFIXES:
        return None
    return first


@app.middleware("http")
async def api_security_middleware(request: Request, call_next) -> object:
    path = request.url.path

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
        client_ip = request.client.host if request.client else "unknown"

        if _rate_limiter is not None:
            allowed, retry_after = await _rate_limiter.allow(client_ip)
            if not allowed:
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Rate limit exceeded. Please retry later."},
                    headers={"Retry-After": str(retry_after)},
                )

        required_role = _required_role_for_request(path, request.method)
        if required_role is not None:
            auth_ctx = resolve_request_auth(request)
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
            auth_ctx = resolve_request_auth(request)
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

# ── Cache Prevention Middleware ───────────────────────
@app.middleware("http")
async def add_no_cache_header(request: Request, call_next) -> object:
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

# ── Core-Routen ──────────────────────────────────────
app.include_router(chat_router)
app.include_router(auth_router)
app.include_router(themes_router)
app.include_router(modules_router)
app.include_router(memory_router)
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

# ── Health Endpoint ──────────────────────────────────
# NOTE: Must be registered BEFORE the catch-all static mount
@app.get("/health")
async def health() -> object:
    """Basis Health-Check."""
    return {
        "status": "ok",
        "service": "ninko",
        "version": "0.9.2",
    }
