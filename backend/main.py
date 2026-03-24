"""
Kumio – Hauptanwendung (Entry Point).
Lädt Module dynamisch, registriert Routen, startet Monitor.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

# Logging konfigurieren
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s │ %(name)-30s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("kumio.main")

# Redis-Log-Handler (nach Redis-Verfügbarkeit lazy)
from core.log_handler import RedisLogHandler as _RedisLogHandler
_redis_log_handler = _RedisLogHandler(level=logging.INFO)
root_logger = logging.getLogger()
if not any(isinstance(h, _RedisLogHandler) for h in root_logger.handlers):
    root_logger.addHandler(_redis_log_handler)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application Lifespan – Startup und Shutdown."""
    logger.info("═" * 60)
    logger.info("  Kumio – IT-Operations AI-Agent wird gestartet…")
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
    except Exception as _exc:
        logger.warning("LLM-Startup-Config konnte nicht geladen werden: %s", _exc)

    # ── STT + TTS Settings aus Redis wiederherstellen ─────────────────────────
    try:
        from api.routes_settings import REDIS_KEY_STT, REDIS_KEY_TTS
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
    except Exception as _exc2:
        logger.warning("STT/TTS-Startup-Config konnte nicht geladen werden: %s", _exc2)

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

    # ── Telegram Polling Bot ──────────────────────────
    from modules.telegram.bot import init_telegram_bot
    telegram_bot = init_telegram_bot(app)
    app.state.telegram_bot = telegram_bot
    await telegram_bot.start()

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
            async def serve_index():
                response = FileResponse(str(_frontend_dir / "index.html"))
                response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"
                return response

            app.mount("/static", StaticFiles(directory=str(_fdir)), name="static")
            app.mount("/", StaticFiles(directory=str(_fdir), html=True), name="frontend")
            logger.info("Frontend served from: %s", _fdir)
            break

    logger.info("═" * 60)
    logger.info("  Kumio bereit! Module: %d", len(registry.list_modules()))
    logger.info("═" * 60)

    yield

    # ── Shutdown ──────────────────────────────────────
    logger.info("Kumio wird heruntergefahren…")
    
    # Telegram Bot stoppen
    await telegram_bot.stop()
    
    await monitor.stop()
    monitor_task.cancel()
    await scheduler.stop()
    scheduler_task.cancel()

    from core.redis_client import get_redis
    redis = get_redis()
    await redis.close()

    logger.info("Kumio beendet.")


# ── FastAPI App ───────────────────────────────────────
app = FastAPI(
    title="Kumio",
    description="Modularer IT-Operations-AI-Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cache Prevention Middleware ───────────────────────
@app.middleware("http")
async def add_no_cache_header(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response

# ── Core-Routen ──────────────────────────────────────
app.include_router(chat_router)
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

# ── Health Endpoint ──────────────────────────────────
# NOTE: Must be registered BEFORE the catch-all static mount
@app.get("/health")
async def health():
    """Basis Health-Check."""
    return {
        "status": "ok",
        "service": "kumio",
        "version": "1.0.0",
    }

