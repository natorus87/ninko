"""
Kumio Settings API – Runtime-Konfiguration für LLM, Module, K8s-Cluster.
Persistenz via Redis (Hash-basiert). Secrets via Vault.
"""

from __future__ import annotations

import base64
import json
import logging
import os

from fastapi import APIRouter, Request, HTTPException

from schemas.settings import (
    LlmSettings,
    LlmSettingsResponse,
    LLMProvider,
    LLMProviderCreate,
    ModuleSettingsItem,
    ModuleToggleRequest,
    K8sClusterInfo,
    K8sClusterCreate,
    K8sClusterListResponse,
)
from core.config import get_settings
from core.redis_client import get_redis

logger = logging.getLogger("kumio.api.settings")
router = APIRouter(prefix="/api/settings", tags=["Settings"])

REDIS_KEY_LLM = "kumio:settings:llm"
REDIS_KEY_MODULES = "kumio:settings:modules"
REDIS_KEY_K8S_CLUSTERS = "kumio:settings:k8s_clusters"
REDIS_KEY_LLM_PROVIDERS = "kumio:settings:llm_providers"


# ═══════════════════════════════════════════════════════
#  LLM Settings
# ═══════════════════════════════════════════════════════

@router.get("/llm", response_model=LlmSettingsResponse)
async def get_llm_settings() -> LlmSettingsResponse:
    """Aktuelle LLM-Konfiguration abrufen (Redis → Env → Default)."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_LLM)

    if raw:
        data = json.loads(raw)
        return LlmSettingsResponse(**data, source="redis")

    # Fallback auf Env/Defaults
    cfg = get_settings()
    if cfg.LLM_BACKEND == "ollama":
        base_url = cfg.OLLAMA_BASE_URL
        model = cfg.OLLAMA_MODEL
    elif cfg.LLM_BACKEND == "openai_compatible":
        base_url = cfg.OPENAI_BASE_URL
        model = cfg.OPENAI_MODEL
    else:
        base_url = cfg.LMSTUDIO_BASE_URL
        model = cfg.LMSTUDIO_MODEL
    return LlmSettingsResponse(
        backend=cfg.LLM_BACKEND,
        base_url=base_url,
        model=model,
        source="default",
    )


@router.put("/llm", response_model=LlmSettingsResponse)
async def update_llm_settings(body: LlmSettings) -> LlmSettingsResponse:
    """LLM-Konfiguration aktualisieren und LLM-Factory neu initialisieren."""
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_LLM, body.model_dump_json())
    logger.info("LLM-Settings aktualisiert: backend=%s, model=%s", body.backend, body.model)

    # LLM-Factory neu initialisieren
    _reconfigure_llm(body)

    return LlmSettingsResponse(**body.model_dump(), source="redis")


# ── Global Embedding Model (einheitlich für ChromaDB) ──

REDIS_KEY_EMBED_MODEL = "kumio:settings:embed_model"


@router.get("/llm/embed-model")
async def get_embed_model() -> dict:
    """Globales Embedding-Modell abrufen."""
    redis = get_redis()
    stored = await redis.connection.get(REDIS_KEY_EMBED_MODEL)
    model = stored if isinstance(stored, str) else (stored.decode() if stored else get_settings().EMBED_MODEL)
    return {"embed_model": model}


@router.put("/llm/embed-model")
async def set_embed_model(body: dict) -> dict:
    """Globales Embedding-Modell setzen. Achtung: Vorhandene ChromaDB-Einträge wurden mit dem alten Modell erzeugt."""
    model = body.get("embed_model", "").strip()
    if not model:
        raise HTTPException(status_code=400, detail="embed_model darf nicht leer sein.")

    redis = get_redis()
    await redis.connection.set(REDIS_KEY_EMBED_MODEL, model)

    # Sofort in Env übernehmen
    os.environ["EMBED_MODEL"] = model
    import core.config
    core.config._settings = None

    logger.info("Globales Embedding-Modell geändert zu: %s", model)
    return {"embed_model": model, "status": "saved"}


def _reconfigure_llm(settings: LlmSettings) -> None:
    """Setzt die effektiven LLM-Settings in den Env-Variablen (für llm_factory)."""
    os.environ["LLM_BACKEND"] = settings.backend
    if settings.backend == "ollama":
        os.environ["OLLAMA_BASE_URL"] = settings.base_url
        os.environ["OLLAMA_MODEL"] = settings.model
    elif settings.backend == "openai_compatible":
        os.environ["OPENAI_BASE_URL"] = settings.base_url
        os.environ["OPENAI_MODEL"] = settings.model
        if settings.api_key:
            os.environ["OPENAI_API_KEY"] = settings.api_key
    else:
        os.environ["LMSTUDIO_BASE_URL"] = settings.base_url
        os.environ["LMSTUDIO_MODEL"] = settings.model

    # Context-Window-Cache leeren bei Backend-Wechsel
    from core.llm_factory import invalidate_context_window_cache
    invalidate_context_window_cache()

    # Settings-Singleton zurücksetzen damit neue Werte geladen werden
    import core.config
    core.config._settings = None
    logger.info("LLM-Factory wird beim nächsten Aufruf neu initialisiert: backend=%s", settings.backend)


# ═══════════════════════════════════════════════════════
#  Language Settings
# ═══════════════════════════════════════════════════════

REDIS_KEY_LANGUAGE = "kumio:settings:language"
SUPPORTED_LANGUAGES = {"de", "en", "fr", "es", "it", "nl", "pl", "pt", "ja", "zh"}


@router.get("/language")
async def get_language() -> dict:
    """Aktuelle Sprache aus Redis (Fallback: ENV/Default 'de')."""
    redis = get_redis()
    stored = await redis.connection.get(REDIS_KEY_LANGUAGE)
    # redis-py mit decode_responses=True liefert bereits str, sonst bytes
    lang = stored if isinstance(stored, str) else (stored.decode() if stored else get_settings().LANGUAGE)
    return {"language": lang}


@router.put("/language")
async def set_language(body: dict) -> dict:
    """Sprache in Redis speichern und sofort in ENV übernehmen."""
    lang = body.get("language", "de")
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"Unsupported language: {lang}. Supported: {SUPPORTED_LANGUAGES}")

    redis = get_redis()
    await redis.connection.set(REDIS_KEY_LANGUAGE, lang)

    # ENV direkt setzen damit get_settings() sofort die neue Sprache liefert
    os.environ["LANGUAGE"] = lang
    import core.config
    core.config._settings = None

    logger.info("Sprache geändert zu: %s", lang)
    return {"language": lang, "status": "saved"}


# ═══════════════════════════════════════════════════════
#  Module Settings
# ═══════════════════════════════════════════════════════


@router.get("/modules", response_model=list[ModuleSettingsItem])
async def get_module_settings(request: Request) -> list[ModuleSettingsItem]:
    """Alle Module (inkl. deaktivierter) mit Konfiguration."""
    redis = get_redis()
    registry = request.app.state.registry

    # Gespeicherte Modul-Overrides laden
    raw = await redis.connection.get(REDIS_KEY_MODULES)
    overrides: dict = json.loads(raw) if raw else {}

    # Alle bekannten Module aus dem Registry (enabled + discovered-disabled)
    all_modules = registry.list_all_modules()

    result = []
    for mod in all_modules:
        override = overrides.get(mod.name, {})
        enabled = override.get("enabled", registry.is_enabled(mod.name))

        # Connection-Parameter: aus Override oder Env
        connection = override.get("connection", {})
        if not connection and mod.env_prefix:
            connection = _get_env_connection(mod.name, mod.env_prefix)

        result.append(ModuleSettingsItem(
            name=mod.name,
            display_name=mod.display_name,
            enabled=enabled,
            description=mod.description,
            version=mod.version,
            connection=connection,
        ))

    return result


@router.put("/modules/{module_name}")
async def update_module_settings(
    request: Request, module_name: str, body: ModuleToggleRequest
) -> dict:
    """Modul aktivieren/deaktivieren und Verbindungseinstellungen speichern."""
    redis = get_redis()

    # Overrides laden
    raw = await redis.connection.get(REDIS_KEY_MODULES)
    overrides: dict = json.loads(raw) if raw else {}

    # ── Merge-Strategie: Bestehende Verbindungseinstellungen laden ──────────
    # Damit Passwort-Felder (die im Frontend leer bleiben) nicht gelöscht werden,
    # mergen wir neue Werte ÜBER die alten, anstatt sie zu ersetzen.
    existing_connection: dict = overrides.get(module_name, {}).get("connection", {})
    merged_connection = {**existing_connection}
    for key, value in body.connection.items():
        if value:  # Nur nicht-leere Werte übernehmen
            merged_connection[key] = value

    overrides[module_name] = {
        "enabled": body.enabled,
        "connection": merged_connection,
    }
    await redis.connection.set(REDIS_KEY_MODULES, json.dumps(overrides))

    # Connection-Secrets in Vault speichern
    secret_keys = _get_secret_keys(module_name)
    if secret_keys and body.connection:
        from core.vault import get_vault
        vault = get_vault()
        for key in secret_keys:
            value = body.connection.get(key, "")
            if value:
                await vault.set_secret(key, value)
                logger.info("Secret gespeichert: %s", key)

    # Env-Variablen setzen für Connection-Params
    _apply_module_connection(module_name, merged_connection)

    # Modul-Status aktualisieren
    env_key = f"KUMIO_MODULE_{module_name.upper()}"
    os.environ[env_key] = "true" if body.enabled else "false"

    logger.info(
        "Modul '%s' %s, Connection: %d Parameter",
        module_name,
        "aktiviert" if body.enabled else "deaktiviert",
        len(merged_connection),
    )

    return {
        "module": module_name,
        "enabled": body.enabled,
        "status": "ok",
        "restart_required": body.enabled,
    }


def _get_env_connection(module_name: str, prefix: str) -> dict:
    """Liest aktuelle Connection-Parameter aus Env-Variablen."""
    params = {}
    mappings = {
        "proxmox": ["PROXMOX_HOST", "PROXMOX_USER", "PROXMOX_TOKEN_ID", "PROXMOX_VERIFY_SSL"],
        "glpi": ["GLPI_BASE_URL"],
        "kubernetes": [],
        "pihole": ["PIHOLE_URL"],
        "ionos": [],
        "fritzbox": ["FRITZBOX_HOST", "FRITZBOX_USER"],
        "email": ["EMAIL_IMAP_SERVER", "EMAIL_IMAP_PORT", "EMAIL_SMTP_SERVER", "EMAIL_SMTP_PORT", "EMAIL_ADDRESS", "EMAIL_AUTH_TYPE", "EMAIL_CLIENT_ID", "EMAIL_TENANT_ID"],
        "docker": ["DOCKER_HOST", "DOCKER_PORT", "DOCKER_TLS", "DOCKER_API_VERSION"],
        "linux_server": ["LINUX_SERVER_HOST", "LINUX_SERVER_PORT", "LINUX_SERVER_USER"],
        "wordpress": ["WORDPRESS_URL", "WORDPRESS_USERNAME"],
    }
    for key in mappings.get(module_name, []):
        val = os.environ.get(key, "")
        if val:
            params[key] = val
    return params


def _get_secret_keys(module_name: str) -> list[str]:
    """Gibt die Secret-Keys für ein Modul zurück."""
    return {
        "proxmox": ["PROXMOX_TOKEN_SECRET"],
        "glpi": ["GLPI_APP_TOKEN", "GLPI_USER_TOKEN"],
        "kubernetes": [],
        "pihole": ["PIHOLE_PASSWORD"],
        "ionos": ["IONOS_API_KEY"],
        "fritzbox": ["FRITZBOX_PASSWORD"],
        "email": ["EMAIL_SECRET"],
        "docker": ["DOCKER_TLS_CERT", "DOCKER_TLS_KEY"],
        "linux_server": ["LINUX_SERVER_PASSWORD", "LINUX_SERVER_SSH_KEY"],
        "wordpress": ["WORDPRESS_APP_PASSWORD"],
    }.get(module_name, [])


def _apply_module_connection(module_name: str, connection: dict) -> None:
    """Setzt Connection-Parameter als Env-Variablen."""
    for key, value in connection.items():
        if key and value and not key.endswith("SECRET") and not key.endswith("TOKEN") and not key.endswith("KEY"):
            os.environ[key] = str(value)


# ═══════════════════════════════════════════════════════
#  LLM Multi-Provider Management
# ═══════════════════════════════════════════════════════

async def _load_providers(redis) -> list[dict]:
    raw = await redis.connection.get(REDIS_KEY_LLM_PROVIDERS)
    return json.loads(raw) if raw else []


async def _save_providers(redis, providers: list[dict]) -> None:
    await redis.connection.set(REDIS_KEY_LLM_PROVIDERS, json.dumps(providers))


def _apply_default_provider(providers: list[dict]) -> None:
    """Findet den Standard-Provider und konfiguriert die LLM-Factory entsprechend."""
    default = next((p for p in providers if p.get("is_default")), None)
    if not default and providers:
        default = providers[0]        # Fallback: erster Provider
    if not default:
        return

    # LlmSettings aus dem Provider-Dict bauen
    settings = LlmSettings(
        backend=default.get("backend", "ollama"),
        base_url=default.get("base_url", "http://ollama:11434"),
        model=default.get("model", "llama3.2:3b"),
        api_key=default.get("api_key", ""),
    )
    _reconfigure_llm(settings)
    logger.info(
        "LLM-Factory auf Standard-Provider umgestellt: %s (%s, %s)",
        default.get("name"), settings.backend, settings.model,
    )


@router.get("/llm/providers")
async def list_llm_providers() -> list:
    """Alle konfigurierten LLM-Provider auflisten."""
    redis = get_redis()
    providers = await _load_providers(redis)
    return providers


@router.post("/llm/providers", status_code=201)
async def create_llm_provider(body: LLMProviderCreate) -> dict:
    """Neuen LLM-Provider anlegen."""
    import uuid
    from datetime import datetime, timezone
    redis = get_redis()
    providers = await _load_providers(redis)

    now = datetime.now(timezone.utc).isoformat()
    new_provider = LLMProvider(
        **body.model_dump(),
        id=str(uuid.uuid4()),
        status="unknown",
        created_at=now,
    )

    # is_default: alle anderen deaktivieren
    if body.is_default:
        for p in providers:
            p["is_default"] = False
    elif not providers:
        new_provider.is_default = True  # Erster Provider ist immer Standard

    providers.append(new_provider.model_dump())
    await _save_providers(redis, providers)
    # Wenn neuer Provider als Standard gesetzt → LLM-Factory neu konfigurieren
    if new_provider.is_default:
        _apply_default_provider(providers)
    logger.info("LLM-Provider erstellt: %s (%s)", new_provider.name, new_provider.id)
    return {"id": new_provider.id, "status": "created"}


@router.put("/llm/providers/{provider_id}")
async def update_llm_provider(provider_id: str, body: LLMProviderCreate) -> dict:
    """LLM-Provider bearbeiten."""
    redis = get_redis()
    providers = await _load_providers(redis)
    idx = next((i for i, p in enumerate(providers) if p["id"] == provider_id), None)
    if idx is None:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' nicht gefunden")

    if body.is_default:
        for p in providers:
            p["is_default"] = False

    providers[idx] = {**providers[idx], **body.model_dump(), "id": provider_id}
    await _save_providers(redis, providers)
    # Falls dieser oder ein anderer Provider zum Standard wurde → LLM-Factory neu
    _apply_default_provider(providers)
    logger.info("LLM-Provider aktualisiert: %s", provider_id)
    return {"id": provider_id, "status": "updated"}


@router.delete("/llm/providers/{provider_id}")
async def delete_llm_provider(provider_id: str) -> dict:
    """LLM-Provider löschen."""
    redis = get_redis()
    providers = await _load_providers(redis)
    original_len = len(providers)
    removed = [p for p in providers if p["id"] == provider_id]
    providers = [p for p in providers if p["id"] != provider_id]
    if len(providers) == original_len:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' nicht gefunden")

    # Neuen Standard setzen falls gelöschter Standard war
    if removed and removed[0].get("is_default") and providers:
        providers[0]["is_default"] = True

    await _save_providers(redis, providers)
    # Neuen Standard anwenden (falls sich der Default geändert hat)
    _apply_default_provider(providers)
    logger.info("LLM-Provider gelöscht: %s", provider_id)
    return {"id": provider_id, "deleted": True}


@router.post("/llm/providers/{provider_id}/test")
async def test_llm_provider(provider_id: str) -> dict:
    """Verbindungstest für einen LLM-Provider."""
    import httpx
    redis = get_redis()
    providers = await _load_providers(redis)
    provider = next((p for p in providers if p["id"] == provider_id), None)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' nicht gefunden")

    base_url = provider.get("base_url", "")
    backend = provider.get("backend", "ollama")
    api_key = provider.get("api_key", "")

    # Test-URL bestimmen
    if backend == "ollama":
        test_url = base_url.rstrip("/") + "/api/tags"
    else:
        test_url = base_url.rstrip("/").rstrip("/v1") + "/v1/models"

    headers = {}
    if backend == "openai_compatible" and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    status = "unreachable"
    error = None
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(test_url, headers=headers)
            if resp.status_code < 500:
                status = "connected"
    except Exception as exc:
        error = str(exc)[:200]

    # Status in Redis aktualisieren
    idx = next((i for i, p in enumerate(providers) if p["id"] == provider_id), None)
    if idx is not None:
        providers[idx]["status"] = status
        await _save_providers(redis, providers)

    return {"id": provider_id, "status": status, "error": error}


@router.put("/llm/default")
async def set_default_llm_provider(body: dict) -> dict:
    """Standard-LLM-Provider setzen."""
    provider_id = body.get("provider_id", "")
    redis = get_redis()
    providers = await _load_providers(redis)
    found = False
    for p in providers:
        if p["id"] == provider_id:
            p["is_default"] = True
            found = True
        else:
            p["is_default"] = False
    if not found:
        raise HTTPException(status_code=404, detail=f"Provider '{provider_id}' nicht gefunden")
    await _save_providers(redis, providers)
    # LLM-Factory auf neuen Standard umstellen
    _apply_default_provider(providers)
    return {"provider_id": provider_id, "is_default": True}


# ═══════════════════════════════════════════════════════
#  Kubernetes Cluster Settings
# ═══════════════════════════════════════════════════════

@router.get("/k8s/clusters", response_model=K8sClusterListResponse)
async def list_k8s_clusters() -> K8sClusterListResponse:
    """Alle konfigurierten Kubernetes-Cluster auflisten."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_K8S_CLUSTERS)
    clusters_data: list[dict] = json.loads(raw) if raw else []

    clusters = [
        K8sClusterInfo(
            name=c["name"],
            context=c.get("context", ""),
            is_default=c.get("is_default", False),
            has_kubeconfig=True,
        )
        for c in clusters_data
    ]

    # Wenn keine Cluster konfiguriert, aber ein lokaler Kubeconfig existiert
    if not clusters:
        try:
            from kubernetes import config as k8s_config
            k8s_config.load_kube_config()
            clusters = [K8sClusterInfo(
                name="local",
                context="current-context",
                is_default=True,
                has_kubeconfig=True,
            )]
        except Exception:
            pass

    return K8sClusterListResponse(clusters=clusters, total=len(clusters))


@router.post("/k8s/clusters", status_code=201)
async def add_k8s_cluster(body: K8sClusterCreate) -> dict:
    """Neuen Kubernetes-Cluster hinzufügen."""
    redis = get_redis()

    # Kubeconfig-Validierung
    try:
        kubeconfig_bytes = base64.b64decode(body.kubeconfig_base64)
        kubeconfig_str = kubeconfig_bytes.decode("utf-8")
        if "apiVersion" not in kubeconfig_str:
            raise ValueError("Ungültige Kubeconfig")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Ungültige Kubeconfig: {exc}")

    # In Vault speichern
    from core.vault import get_vault
    vault = get_vault()
    await vault.set_secret(f"K8S_KUBECONFIG_{body.name.upper()}", body.kubeconfig_base64)

    # Cluster-Metadata in Redis
    raw = await redis.connection.get(REDIS_KEY_K8S_CLUSTERS)
    clusters: list[dict] = json.loads(raw) if raw else []

    # Duplikat-Check
    if any(c["name"] == body.name for c in clusters):
        raise HTTPException(status_code=409, detail=f"Cluster '{body.name}' existiert bereits")

    # is_default: alle anderen auf False setzen
    if body.is_default:
        for c in clusters:
            c["is_default"] = False

    clusters.append({
        "name": body.name,
        "context": body.context,
        "is_default": body.is_default or len(clusters) == 0,
    })

    await redis.connection.set(REDIS_KEY_K8S_CLUSTERS, json.dumps(clusters))
    logger.info("K8s-Cluster hinzugefügt: %s", body.name)

    return {"name": body.name, "status": "ok"}


@router.delete("/k8s/clusters/{cluster_name}")
async def delete_k8s_cluster(cluster_name: str) -> dict:
    """Kubernetes-Cluster entfernen."""
    redis = get_redis()

    raw = await redis.connection.get(REDIS_KEY_K8S_CLUSTERS)
    clusters: list[dict] = json.loads(raw) if raw else []

    original_len = len(clusters)
    clusters = [c for c in clusters if c["name"] != cluster_name]

    if len(clusters) == original_len:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_name}' nicht gefunden")

    # Secret löschen
    from core.vault import get_vault
    vault = get_vault()
    await vault.delete_secret(f"K8S_KUBECONFIG_{cluster_name.upper()}")

    # Neuen Default setzen wenn nötig
    if clusters and not any(c.get("is_default") for c in clusters):
        clusters[0]["is_default"] = True

    await redis.connection.set(REDIS_KEY_K8S_CLUSTERS, json.dumps(clusters))
    logger.info("K8s-Cluster entfernt: %s", cluster_name)

    return {"name": cluster_name, "deleted": True}


# ═══════════════════════════════════════════════════════
#  TTS Settings
# ═══════════════════════════════════════════════════════

REDIS_KEY_TTS = "kumio:settings:tts"


@router.get("/tts")
async def get_tts_settings() -> dict:
    """TTS-Konfiguration abrufen (Redis → Env → Default)."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_TTS)
    if raw:
        return {"source": "redis", **json.loads(raw)}

    cfg = get_settings()
    return {
        "source": "default",
        "TTS_ENABLED": cfg.TTS_ENABLED,
        "PIPER_BINARY": cfg.PIPER_BINARY,
        "VOICES_DIR": cfg.VOICES_DIR,
        "TTS_DEFAULT_LANG": cfg.TTS_DEFAULT_LANG,
        "TTS_DEFAULT_VOICE": cfg.TTS_DEFAULT_VOICE,
    }


@router.put("/tts")
async def update_tts_settings(body: dict) -> dict:
    """TTS-Konfiguration in Redis speichern und sofort in ENV übernehmen."""
    allowed = {"TTS_ENABLED", "PIPER_BINARY", "VOICES_DIR", "TTS_DEFAULT_LANG", "TTS_DEFAULT_VOICE", "TTS_SAMPLE_RATE"}
    data = {k: v for k, v in body.items() if k in allowed}

    redis = get_redis()
    await redis.connection.set(REDIS_KEY_TTS, json.dumps(data))

    # Sofort in Env übernehmen damit get_settings() aktuell ist
    for key, value in data.items():
        os.environ[key] = str(value).lower() if isinstance(value, bool) else str(value)
    import core.config
    core.config._settings = None

    # PiperService-Singleton zurücksetzen damit neues Binary genutzt wird
    try:
        import core.tts as _tts_mod
        _tts_mod._service = None
    except Exception:
        pass

    logger.info("TTS-Settings aktualisiert: %s", data)
    return {"status": "saved", **data}


# ═══════════════════════════════════════════════════════
#  STT Settings
# ═══════════════════════════════════════════════════════

REDIS_KEY_STT = "kumio:settings:stt"
_STT_ALLOWED = {
    "STT_PROVIDER",
    "WHISPER_MODEL_SIZE", "WHISPER_DEVICE", "WHISPER_COMPUTE_TYPE", "WHISPER_LANGUAGE",
    "STT_API_URL", "STT_API_KEY", "STT_MODEL",
    "STT_SPELLCHECK", "STT_CONFIDENCE_THRESHOLD",
}


@router.get("/stt")
async def get_stt_settings() -> dict:
    """STT-Konfiguration abrufen (Redis → Env → Default)."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_STT)
    if raw:
        return {"source": "redis", **json.loads(raw)}

    cfg = get_settings()
    return {
        "source": "default",
        "STT_PROVIDER": cfg.STT_PROVIDER,
        "WHISPER_MODEL_SIZE": cfg.WHISPER_MODEL_SIZE,
        "WHISPER_DEVICE": cfg.WHISPER_DEVICE,
        "WHISPER_COMPUTE_TYPE": cfg.WHISPER_COMPUTE_TYPE,
        "WHISPER_LANGUAGE": cfg.WHISPER_LANGUAGE,
        "STT_API_URL": cfg.STT_API_URL,
        "STT_API_KEY": cfg.STT_API_KEY,
        "STT_MODEL": cfg.STT_MODEL,
        "STT_SPELLCHECK": cfg.STT_SPELLCHECK,
        "STT_CONFIDENCE_THRESHOLD": cfg.STT_CONFIDENCE_THRESHOLD,
    }


@router.put("/stt")
async def update_stt_settings(body: dict) -> dict:
    """STT-Konfiguration in Redis speichern und sofort in ENV übernehmen."""
    data = {k: v for k, v in body.items() if k in _STT_ALLOWED}

    redis = get_redis()
    await redis.connection.set(REDIS_KEY_STT, json.dumps(data))

    # Sofort in Env übernehmen
    old_model_size = os.getenv("WHISPER_MODEL_SIZE", "base")
    old_device = os.getenv("WHISPER_DEVICE", "cpu")
    old_compute = os.getenv("WHISPER_COMPUTE_TYPE", "int8")

    for key, value in data.items():
        os.environ[key] = str(value).lower() if isinstance(value, bool) else str(value)
    import core.config
    core.config._settings = None

    # Whisper-Cache invalidieren wenn sich Modell-Parameter geändert haben
    if (
        data.get("WHISPER_MODEL_SIZE", old_model_size) != old_model_size
        or data.get("WHISPER_DEVICE", old_device) != old_device
        or data.get("WHISPER_COMPUTE_TYPE", old_compute) != old_compute
    ):
        try:
            from api.routes_transcription import invalidate_whisper_cache
            invalidate_whisper_cache()
        except Exception:
            pass

    logger.info("STT-Settings aktualisiert: %s", {k: v for k, v in data.items() if "KEY" not in k})
    return {"status": "saved", **{k: v for k, v in data.items() if "KEY" not in k}}


@router.put("/k8s/clusters/{cluster_name}/default")
async def set_default_k8s_cluster(cluster_name: str) -> dict:
    """Setzt einen Cluster als Default."""
    redis = get_redis()

    raw = await redis.connection.get(REDIS_KEY_K8S_CLUSTERS)
    clusters: list[dict] = json.loads(raw) if raw else []

    found = False
    for c in clusters:
        if c["name"] == cluster_name:
            c["is_default"] = True
            found = True
        else:
            c["is_default"] = False

    if not found:
        raise HTTPException(status_code=404, detail=f"Cluster '{cluster_name}' nicht gefunden")

    await redis.connection.set(REDIS_KEY_K8S_CLUSTERS, json.dumps(clusters))

    return {"name": cluster_name, "is_default": True, "status": "ok"}
