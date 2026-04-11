"""
Ninko Settings API – Runtime-Konfiguration für LLM, Module, K8s-Cluster.
Persistenz via Redis (Hash-basiert). Secrets via Vault.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException, UploadFile, File

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
    BrandingSettings,
    BrandingSettingsResponse,
)
from core.config import get_settings
from core.redis_client import get_redis
from agents.base_agent import _t

logger = logging.getLogger("ninko.api.settings")
router = APIRouter(prefix="/api/settings", tags=["Settings"])

# Gemeinsame Exception-Typen für Settings-Operationen (Redis-Lese/Schreib-Fehler,
# Deserialisierung, Import-Fehler bei optionalen Modulen)
_SETTINGS_RECOVERABLE_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    KeyError,
    OSError,
    ImportError,
    json.JSONDecodeError,
)

REDIS_KEY_LLM = "ninko:settings:llm"
REDIS_KEY_MODULES = "ninko:settings:modules"
REDIS_KEY_K8S_CLUSTERS = "ninko:settings:k8s_clusters"
REDIS_KEY_LLM_PROVIDERS = "ninko:settings:llm_providers"
REDIS_KEY_BRANDING = "ninko:settings:branding"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BRANDING_DIR = (
    Path("/app/data/branding")
    if Path("/app/data").exists()
    else (_REPO_ROOT / "data" / "branding")
)
_BRANDING_DIR.mkdir(parents=True, exist_ok=True)
_BRANDING_ALLOWED_MIME = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/gif",
    "image/svg+xml",
}
_BRANDING_ALLOWED_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


def _sanitize_llm_payload(data: dict, source: str) -> LlmSettingsResponse:
    """Entfernt Secrets aus LLM-Responses und liefert *_set Flag."""
    clean = dict(data or {})
    secret = (clean.get("api_key") or "").strip()
    clean["api_key"] = ""
    clean["api_key_set"] = bool(secret)
    clean["source"] = source
    return LlmSettingsResponse(**clean)


def _sanitize_provider(provider: dict) -> dict:
    """Entfernt Provider-Secrets aus Read-Responses."""
    clean = dict(provider)
    secret = (clean.get("api_key") or "").strip()
    clean["api_key"] = ""
    clean["api_key_set"] = bool(secret)
    return clean


def _branding_defaults() -> dict:
    return BrandingSettings().model_dump()


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
        return _sanitize_llm_payload(data, source="redis")

    # Fallback auf Env/Defaults
    cfg = get_settings()
    if cfg.LLM_BACKEND == "ollama":
        base_url = cfg.OLLAMA_BASE_URL
        model = cfg.OLLAMA_MODEL
    elif cfg.LLM_BACKEND == "openai_compatible":
        base_url = cfg.OPENAI_BASE_URL
        model = cfg.OPENAI_MODEL
    elif cfg.LLM_BACKEND == "litellm":
        base_url = cfg.LITELLM_BASE_URL
        model = cfg.LITELLM_MODEL
    else:
        base_url = cfg.LMSTUDIO_BASE_URL
        model = cfg.LMSTUDIO_MODEL
    return _sanitize_llm_payload(
        {
            "backend": cfg.LLM_BACKEND,
            "base_url": base_url,
            "model": model,
            "api_key": (
                cfg.OPENAI_API_KEY
                if cfg.LLM_BACKEND == "openai_compatible"
                else (cfg.LITELLM_API_KEY if cfg.LLM_BACKEND == "litellm" else "")
            ),
        },
        source="default",
    )


@router.put("/llm", response_model=LlmSettingsResponse)
async def update_llm_settings(body: LlmSettings) -> LlmSettingsResponse:
    """LLM-Konfiguration aktualisieren und LLM-Factory neu initialisieren."""
    redis = get_redis()
    payload = body.model_dump()
    api_key_value = payload.get("api_key")
    # Expliziter Check für None oder leeren/whitespace String (nicht nur falsy)
    if api_key_value is None or (
        isinstance(api_key_value, str) and api_key_value.strip() == ""
    ):
        existing_raw = await redis.connection.get(REDIS_KEY_LLM)
        if existing_raw:
            try:
                existing = json.loads(existing_raw)
                if existing.get("api_key"):
                    payload["api_key"] = existing["api_key"]
            except _SETTINGS_RECOVERABLE_EXCEPTIONS as exc:
                logger.warning(
                    "API-Key aus bestehenden LLM-Settings konnte nicht gelesen werden: %s",
                    exc,
                )

    await redis.connection.set(REDIS_KEY_LLM, json.dumps(payload))
    logger.info(
        "LLM-Settings aktualisiert: backend=%s, model=%s", body.backend, body.model
    )

    # LLM-Factory neu initialisieren
    _reconfigure_llm(LlmSettings(**payload))

    return _sanitize_llm_payload(payload, source="redis")


# ── Global Embedding Model (einheitlich für ChromaDB) ──

REDIS_KEY_EMBED_MODEL = "ninko:settings:embed_model"


@router.get("/llm/embed-model")
async def get_embed_model() -> dict:
    """Globales Embedding-Modell abrufen."""
    redis = get_redis()
    stored = await redis.connection.get(REDIS_KEY_EMBED_MODEL)
    model = (
        stored
        if isinstance(stored, str)
        else (stored.decode() if stored else get_settings().EMBED_MODEL)
    )
    return {"embed_model": model}


@router.put("/llm/embed-model")
async def set_embed_model(body: dict) -> dict:
    """Globales Embedding-Modell setzen. Achtung: Vorhandene ChromaDB-Einträge wurden mit dem alten Modell erzeugt."""
    model = body.get("embed_model", "").strip()
    if not model:
        raise HTTPException(
            status_code=400,
            detail=_t(
                de="embed_model darf nicht leer sein.",
                en="embed_model cannot be empty.",
                fr="embed_model ne peut pas être vide.",
                es="embed_model no puede estar vacío.",
                it="embed_model non può essere vuoto.",
                nl="embed_model mag niet leeg zijn.",
                pl="embed_model nie może być pusty.",
                pt="embed_model não pode estar vazio.",
                ja="embed_modelは空にできません。",
                zh="embed_model不能为空。",
            ),
        )

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
    elif settings.backend == "litellm":
        os.environ["LITELLM_BASE_URL"] = settings.base_url
        os.environ["LITELLM_MODEL"] = settings.model
        if settings.api_key:
            os.environ["LITELLM_API_KEY"] = settings.api_key
    else:
        os.environ["LMSTUDIO_BASE_URL"] = settings.base_url
        os.environ["LMSTUDIO_MODEL"] = settings.model

    # Context-Window-Cache leeren bei Backend-Wechsel
    from core.llm_factory import invalidate_context_window_cache

    invalidate_context_window_cache()

    # Settings-Singleton zurücksetzen damit neue Werte geladen werden
    import core.config

    core.config._settings = None
    logger.info(
        "LLM-Factory wird beim nächsten Aufruf neu initialisiert: backend=%s",
        settings.backend,
    )


# ═══════════════════════════════════════════════════════
#  Branding Settings
# ═══════════════════════════════════════════════════════


@router.get("/branding", response_model=BrandingSettingsResponse)
async def get_branding_settings() -> BrandingSettingsResponse:
    """Dashboard-Branding abrufen (Redis → Default)."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_BRANDING)
    defaults = _branding_defaults()
    if raw:
        try:
            data = json.loads(raw)
            merged = {**defaults, **(data or {})}
            return BrandingSettingsResponse(**merged, source="redis")
        except _SETTINGS_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning(
                "Branding-Settings aus Redis konnten nicht geladen werden, Defaults verwendet: %s",
                exc,
            )
    return BrandingSettingsResponse(**defaults, source="default")


@router.put("/branding", response_model=BrandingSettingsResponse)
async def update_branding_settings(body: BrandingSettings) -> BrandingSettingsResponse:
    """Dashboard-Branding persistieren."""
    redis = get_redis()
    payload = body.model_dump()
    await redis.connection.set(REDIS_KEY_BRANDING, json.dumps(payload))
    logger.info(
        "Branding-Settings aktualisiert: brand_name=%s",
        payload.get("brand_name", "Ninko"),
    )
    return BrandingSettingsResponse(**payload, source="redis")


@router.post("/branding/reset", response_model=BrandingSettingsResponse)
async def reset_branding_settings() -> BrandingSettingsResponse:
    """Branding auf Defaults zurücksetzen."""
    redis = get_redis()
    payload = _branding_defaults()
    await redis.connection.set(REDIS_KEY_BRANDING, json.dumps(payload))
    logger.info("Branding-Settings auf Defaults zurückgesetzt.")
    return BrandingSettingsResponse(**payload, source="redis")


@router.post("/branding/upload")
async def upload_branding_asset(file: UploadFile = File(...)) -> dict:
    """Branding-Bild hochladen und persistieren."""
    cfg = get_settings()
    max_bytes = int(cfg.BRANDING_MAX_UPLOAD_BYTES)

    # Chunked reading für DoS-Schutz (nicht alles auf einmal in Memory)
    chunk_size = 1024 * 1024  # 1MB chunks
    raw = b""
    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break
        raw += chunk
        if len(raw) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=_t(
                    de="Datei zu groß.",
                    en="File too large.",
                    fr="Fichier trop volumineux.",
                    es="Archivo demasiado grande.",
                    it="File troppo grande.",
                    nl="Bestand te groot.",
                    pl="Plik zbyt duży.",
                    pt="Arquivo muito grande.",
                    ja="ファイルが大きすぎます。",
                    zh="文件太大。",
                ),
            )

    if not raw:
        raise HTTPException(
            status_code=400,
            detail=_t(
                de="Leere Datei.",
                en="Empty file.",
                fr="Fichier vide.",
                es="Archivo vacío.",
                it="File vuoto.",
                nl="Leeg bestand.",
                pl="Pusty plik.",
                pt="Arquivo vazio.",
                ja="空のファイル。",
                zh="空文件。",
            ),
        )

    filename = file.filename or "asset.bin"
    ext = Path(filename).suffix.lower()
    if ext not in _BRANDING_ALLOWED_EXT:
        raise HTTPException(
            status_code=415,
            detail=_t(
                de=f"Dateiendung '{ext or '<none>'}' nicht erlaubt.",
                en=f"File extension '{ext or '<none>'}' not allowed.",
                fr=f"Extension de fichier '{ext or '<none>'}' non autorisée.",
                es=f"Extensión de archivo '{ext or '<none>'}' no permitida.",
                it=f"Estensione file '{ext or '<none>'}' non consentita.",
                nl=f"Bestandsextensie '{ext or '<none>'}' niet toegestaan.",
                pl=f"Rozszerzenie pliku '{ext or '<none>'}' niedozwolone.",
                pt=f"Extensão de arquivo '{ext or '<none>'}' não permitida.",
                ja=f"ファイル拡張子 '{ext or '<none>'}' は許可されていません。",
                zh=f"不允许的文件扩展名 '{ext or '<none>'}'。",
            ),
        )

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime and mime not in _BRANDING_ALLOWED_MIME:
        raise HTTPException(
            status_code=415,
            detail=_t(
                de=f"MIME-Type '{mime}' nicht erlaubt.",
                en=f"MIME type '{mime}' not allowed.",
                fr=f"Type MIME '{mime}' non autorisé.",
                es=f"Tipo MIME '{mime}' no permitido.",
                it=f"Tipo MIME '{mime}' non consentito.",
                nl=f"MIME-type '{mime}' niet toegestaan.",
                pl=f"Typ MIME '{mime}' niedozwolony.",
                pt=f"Tipo MIME '{mime}' não permitido.",
                ja=f"MIMEタイプ '{mime}' は許可されていません。",
                zh=f"不允许的MIME类型 '{mime}'。",
            ),
        )

    safe_name = f"{uuid.uuid4().hex}{ext}"
    target = _BRANDING_DIR / safe_name
    target.write_bytes(raw)
    return {
        "filename": safe_name,
        "url": f"/api/settings/branding/assets/{safe_name}",
        "size": len(raw),
    }


@router.get("/branding/assets/{filename}")
async def get_branding_asset(filename: str) -> "FileResponse":
    """Branding-Asset aus persistentem Storage ausliefern."""
    from fastapi.responses import FileResponse

    if ".." in filename or "/" in filename:
        raise HTTPException(
            status_code=400,
            detail=_t(
                de="Ungültiger Dateiname",
                en="Invalid filename",
                fr="Nom de fichier invalide",
                es="Nombre de archivo inválido",
                it="Nome file non valido",
                nl="Ongeldige bestandsnaam",
                pl="Nieprawidłowa nazwa pliku",
                pt="Nome de arquivo inválido",
                ja="無効なファイル名",
                zh="无效的文件名",
            ),
        )
    path = _BRANDING_DIR / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=_t(
                de="Datei nicht gefunden",
                en="File not found",
                fr="Fichier non trouvé",
                es="Archivo no encontrado",
                it="File non trovato",
                nl="Bestand niet gevonden",
                pl="Plik nie znaleziono",
                pt="Arquivo não encontrado",
                ja="ファイルが見つかりません",
                zh="文件未找到",
            ),
        )

    media_type = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".svg": "image/svg+xml",
    }.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type, filename=filename)


@router.delete("/branding/assets/{filename}")
async def delete_branding_asset(filename: str) -> dict:
    """Branding-Asset löschen und ggf. referenzierte URLs im Branding leeren."""
    if ".." in filename or "/" in filename:
        raise HTTPException(
            status_code=400,
            detail=_t(
                de="Ungültiger Dateiname",
                en="Invalid filename",
                fr="Nom de fichier invalide",
                es="Nombre de archivo inválido",
                it="Nome file non valido",
                nl="Ongeldige bestandsnaam",
                pl="Nieprawidłowa nazwa pliku",
                pt="Nome de arquivo inválido",
                ja="無効なファイル名",
                zh="无效的文件名",
            ),
        )
    path = _BRANDING_DIR / filename
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=_t(
                de="Datei nicht gefunden",
                en="File not found",
                fr="Fichier non trouvé",
                es="Archivo no encontrado",
                it="File non trovato",
                nl="Bestand niet gevonden",
                pl="Plik nie znaleziono",
                pt="Arquivo não encontrado",
                ja="ファイルが見つかりません",
                zh="文件未找到",
            ),
        )

    try:
        path.unlink()
    except OSError:
        raise HTTPException(
            status_code=500,
            detail=_t(
                de="Datei konnte nicht gelöscht werden",
                en="File could not be deleted",
                fr="Le fichier n'a pas pu être supprimé",
                es="El archivo no pudo ser eliminado",
                it="Il file non poteva essere eliminato",
                nl="Bestand kon niet worden verwijderd",
                pl="Plik nie mógł zostać usunięty",
                pt="O arquivo não pôde ser excluído",
                ja="ファイルを削除できませんでした",
                zh="无法删除文件",
            ),
        )

    # Falls URL im Branding verwendet wurde, zurück auf Defaults/Fallback setzen
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_BRANDING)
    if raw:
        try:
            data = json.loads(raw) or {}
            asset_url = f"/api/settings/branding/assets/{filename}"
            changed = False
            if data.get("logo_url") == asset_url:
                data["logo_url"] = _branding_defaults()["logo_url"]
                changed = True
            if data.get("welcome_image_url") == asset_url:
                data["welcome_image_url"] = _branding_defaults()["welcome_image_url"]
                changed = True
            if data.get("login_image_url") == asset_url:
                data["login_image_url"] = _branding_defaults()["login_image_url"]
                changed = True
            if changed:
                await redis.connection.set(REDIS_KEY_BRANDING, json.dumps(data))
        except _SETTINGS_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning(
                "Branding-Settings nach Asset-Löschung konnten nicht aktualisiert werden: %s",
                exc,
            )

    return {"deleted": True, "filename": filename}


# ═══════════════════════════════════════════════════════
#  Language Settings
# ═══════════════════════════════════════════════════════

REDIS_KEY_LANGUAGE = "ninko:settings:language"
SUPPORTED_LANGUAGES = {"de", "en", "fr", "es", "it", "nl", "pl", "pt", "ja", "zh"}


@router.get("/language")
async def get_language() -> dict:
    """Aktuelle Sprache aus Redis (Fallback: ENV/Default 'de')."""
    redis = get_redis()
    stored = await redis.connection.get(REDIS_KEY_LANGUAGE)
    # redis-py mit decode_responses=True liefert bereits str, sonst bytes
    lang = (
        stored
        if isinstance(stored, str)
        else (stored.decode() if stored else get_settings().LANGUAGE)
    )
    return {"language": lang}


@router.put("/language")
async def set_language(body: dict) -> dict:
    """Sprache in Redis speichern und sofort in ENV übernehmen."""
    lang = body.get("language", "de")
    if lang not in SUPPORTED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language: {lang}. Supported: {SUPPORTED_LANGUAGES}",
        )

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

        result.append(
            ModuleSettingsItem(
                name=mod.name,
                display_name=mod.display_name,
                enabled=enabled,
                description=mod.description,
                version=mod.version,
                connection=connection,
            )
        )

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
    env_key = f"NINKO_MODULE_{module_name.upper()}"
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
        "proxmox": [
            "PROXMOX_HOST",
            "PROXMOX_USER",
            "PROXMOX_TOKEN_ID",
            "PROXMOX_VERIFY_SSL",
        ],
        "glpi": ["GLPI_BASE_URL"],
        "kubernetes": [],
        "pihole": ["PIHOLE_URL"],
        "ionos": [],
        "fritzbox": ["FRITZBOX_HOST", "FRITZBOX_USER"],
        "email": [
            "EMAIL_IMAP_SERVER",
            "EMAIL_IMAP_PORT",
            "EMAIL_SMTP_SERVER",
            "EMAIL_SMTP_PORT",
            "EMAIL_ADDRESS",
            "EMAIL_AUTH_TYPE",
            "EMAIL_CLIENT_ID",
            "EMAIL_TENANT_ID",
        ],
        "docker": ["DOCKER_HOST", "DOCKER_PORT", "DOCKER_TLS", "DOCKER_API_VERSION"],
        "linux_server": ["LINUX_SERVER_HOST", "LINUX_SERVER_PORT", "LINUX_SERVER_USER"],
        "wordpress": ["WORDPRESS_URL", "WORDPRESS_USERNAME"],
        "checkmk": ["CHECKMK_URL", "CHECKMK_SITE", "CHECKMK_API_USERNAME"],
        "synology": ["SYNOLOGY_URL", "SYNOLOGY_USERNAME"],
        "redmine": ["REDMINE_URL", "REDMINE_VERIFY_SSL"],
        "openproject": ["OPENPROJECT_HOST"],
        "confluence": ["CONFLUENCE_URL", "CONFLUENCE_EMAIL"],
        "jira": ["JIRA_URL", "JIRA_EMAIL"],
        "zabbix": ["ZABBIX_URL", "ZABBIX_USER"],
        "netbox": ["NETBOX_URL"],
        "gitlab": ["GITLAB_URL"],
        "github": [],
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
        "checkmk": ["CHECKMK_API_PASSWORD", "CHECKMK_API_TOKEN"],
        "synology": ["SYNOLOGY_PASSWORD", "SYNOLOGY_API_KEY"],
        "redmine": ["REDMINE_API_KEY"],
        "openproject": ["OPENPROJECT_API_KEY"],
        "confluence": ["CONFLUENCE_API_KEY"],
        "jira": ["JIRA_API_KEY"],
        "zabbix": ["ZABBIX_PASSWORD"],
        "netbox": ["NETBOX_TOKEN"],
        "gitlab": ["GITLAB_TOKEN"],
        "github": ["GITHUB_TOKEN"],
    }.get(module_name, [])


def _apply_module_connection(module_name: str, connection: dict) -> None:
    """Setzt Connection-Parameter als Env-Variablen."""
    for key, value in connection.items():
        if (
            key
            and value
            and not key.endswith("SECRET")
            and not key.endswith("TOKEN")
            and not key.endswith("KEY")
        ):
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
        default = providers[0]  # Fallback: erster Provider
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

    # SSL-Verify-Flag in Env schreiben (wird von llm_factory beim nächsten get_llm() gelesen)
    verify_ssl = bool(default.get("verify_ssl", True))
    import os

    os.environ["LLM_VERIFY_SSL"] = "true" if verify_ssl else "false"

    # Context-Window Override: wenn manuell gesetzt, direkt in Cache schreiben
    ctx_override = int(default.get("context_window") or 0)
    if ctx_override > 0:
        from core.llm_factory import invalidate_context_window_cache

        invalidate_context_window_cache(override=ctx_override)
        logger.info(
            "LLM-Factory auf Standard-Provider umgestellt: %s (%s, %s) — Context-Window Override: %d",
            default.get("name"),
            settings.backend,
            settings.model,
            ctx_override,
        )
    else:
        logger.info(
            "LLM-Factory auf Standard-Provider umgestellt: %s (%s, %s)",
            default.get("name"),
            settings.backend,
            settings.model,
        )


@router.get("/llm/providers")
async def list_llm_providers() -> list:
    """Alle konfigurierten LLM-Provider auflisten."""
    redis = get_redis()
    providers = await _load_providers(redis)
    return [_sanitize_provider(p) for p in providers]


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
        raise HTTPException(
            status_code=404,
            detail=_t(
                de=f"Provider '{provider_id}' nicht gefunden",
                en=f"Provider '{provider_id}' not found",
                fr=f"Provider '{provider_id}' non trouvé",
                es=f"Provider '{provider_id}' no encontrado",
                it=f"Provider '{provider_id}' non trovato",
                nl=f"Provider '{provider_id}' niet gevonden",
                pl=f"Provider '{provider_id}' nie znaleziono",
                pt=f"Provider '{provider_id}' não encontrado",
                ja=f"Provider '{provider_id}' が見つかりません",
                zh=f"未找到 Provider '{provider_id}'",
            ),
        )

    if body.is_default:
        for p in providers:
            p["is_default"] = False

    incoming = body.model_dump()
    if not incoming.get("api_key") and providers[idx].get("api_key"):
        # Leeres Feld im UI bedeutet "bestehenden Key beibehalten"
        incoming["api_key"] = providers[idx]["api_key"]

    providers[idx] = {**providers[idx], **incoming, "id": provider_id}
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
        raise HTTPException(
            status_code=404,
            detail=_t(
                de=f"Provider '{provider_id}' nicht gefunden",
                en=f"Provider '{provider_id}' not found",
                fr=f"Provider '{provider_id}' non trouvé",
                es=f"Provider '{provider_id}' no encontrado",
                it=f"Provider '{provider_id}' non trovato",
                nl=f"Provider '{provider_id}' niet gevonden",
                pl=f"Provider '{provider_id}' nie znaleziono",
                pt=f"Provider '{provider_id}' não encontrado",
                ja=f"Provider '{provider_id}' が見つかりません",
                zh=f"未找到 Provider '{provider_id}'",
            ),
        )

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
        raise HTTPException(
            status_code=404,
            detail=_t(
                de=f"Provider '{provider_id}' nicht gefunden",
                en=f"Provider '{provider_id}' not found",
                fr=f"Provider '{provider_id}' non trouvé",
                es=f"Provider '{provider_id}' no encontrado",
                it=f"Provider '{provider_id}' non trovato",
                nl=f"Provider '{provider_id}' niet gevonden",
                pl=f"Provider '{provider_id}' nie znaleziono",
                pt=f"Provider '{provider_id}' não encontrado",
                ja=f"Provider '{provider_id}' が見つかりません",
                zh=f"未找到 Provider '{provider_id}'",
            ),
        )

    base_url = provider.get("base_url", "")
    backend = provider.get("backend", "ollama")
    api_key = provider.get("api_key", "")

    # Test-URL bestimmen (korrekte Substring-Entfernung, nicht char-based rstrip)
    base_url_clean = base_url.rstrip("/")
    if base_url_clean.endswith("/v1"):
        base_url_clean = base_url_clean[:-3]
    if backend == "ollama":
        test_url = base_url_clean + "/api/tags"
    else:
        test_url = base_url_clean + "/v1/models"

    headers = {}
    if backend in ("openai_compatible", "litellm") and api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    verify_ssl = bool(provider.get("verify_ssl", True))
    logger.debug(
        "Provider-Test: id=%s backend=%s url=%s verify_ssl_raw=%r verify_ssl_bool=%r",
        provider_id,
        backend,
        test_url,
        provider.get("verify_ssl"),
        verify_ssl,
    )
    status = "unreachable"
    error = None
    try:
        async with httpx.AsyncClient(timeout=5.0, verify=verify_ssl) as client:
            resp = await client.get(test_url, headers=headers)
            if resp.status_code < 500:
                status = "connected"
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        error = str(exc)[:200]

    # Status in Redis aktualisieren
    idx = next((i for i, p in enumerate(providers) if p["id"] == provider_id), None)
    if idx is not None:
        providers[idx]["status"] = status
        await _save_providers(redis, providers)

    return {"id": provider_id, "status": status, "error": error}


@router.get("/llm/context-window")
async def get_context_window() -> dict:
    """Aktuelles Context-Window des geladenen Modells zurückgeben.

    Gibt zuerst einen manuell konfigurierten Override zurück (aus dem aktiven Provider),
    andernfalls den gecachten Wert aus der API-Abfrage (oder den Fallback 32768).
    """
    from core.llm_factory import (
        get_model_context_window,
        _cached_context_window,
        _DEFAULT_CONTEXT_WINDOW,
    )

    redis = get_redis()
    providers = await _load_providers(redis)
    default = next(
        (p for p in providers if p.get("is_default")),
        providers[0] if providers else None,
    )
    override = int((default or {}).get("context_window") or 0)
    if override > 0:
        return {"context_window": override, "source": "manual"}
    cached = _cached_context_window
    if cached:
        return {"context_window": cached, "source": "api"}
    # Noch nicht gecacht → jetzt abfragen
    window = await get_model_context_window()
    return {"context_window": window, "source": "api"}


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
        raise HTTPException(
            status_code=404,
            detail=_t(
                de=f"Provider '{provider_id}' nicht gefunden",
                en=f"Provider '{provider_id}' not found",
                fr=f"Provider '{provider_id}' non trouvé",
                es=f"Provider '{provider_id}' no encontrado",
                it=f"Provider '{provider_id}' non trovato",
                nl=f"Provider '{provider_id}' niet gevonden",
                pl=f"Provider '{provider_id}' nie znaleziono",
                pt=f"Provider '{provider_id}' não encontrado",
                ja=f"Provider '{provider_id}' が見つかりません",
                zh=f"未找到 Provider '{provider_id}'",
            ),
        )
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
            clusters = [
                K8sClusterInfo(
                    name="local",
                    context="current-context",
                    is_default=True,
                    has_kubeconfig=True,
                )
            ]
        except _SETTINGS_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning(
                "Kubeconfig aus Umgebungsvariablen konnte nicht geladen werden: %s", exc
            )

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
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as exc:
        raise HTTPException(
            status_code=400,
            detail=_t(
                de=f"Ungültige Kubeconfig: {exc}",
                en=f"Invalid kubeconfig: {exc}",
                fr=f"Kubeconfig invalide: {exc}",
                es=f"Kubeconfig inválida: {exc}",
                it=f"Kubeconfig non valida: {exc}",
                nl=f"Ongeldige kubeconfig: {exc}",
                pl=f"Nieprawidłowy kubeconfig: {exc}",
                pt=f"Kubeconfig inválido: {exc}",
                ja=f"無効な kubeconfig: {exc}",
                zh=f"无效的 kubeconfig: {exc}",
            ),
        )

    # In Vault speichern
    from core.vault import get_vault

    vault = get_vault()
    await vault.set_secret(
        f"K8S_KUBECONFIG_{body.name.upper()}", body.kubeconfig_base64
    )

    # Cluster-Metadata in Redis
    raw = await redis.connection.get(REDIS_KEY_K8S_CLUSTERS)
    clusters: list[dict] = json.loads(raw) if raw else []

    # Duplikat-Check
    if any(c["name"] == body.name for c in clusters):
        raise HTTPException(
            status_code=409,
            detail=_t(
                de=f"Cluster '{body.name}' existiert bereits",
                en=f"Cluster '{body.name}' already exists",
                fr=f"Cluster '{body.name}' existe déjà",
                es=f"Cluster '{body.name}' ya existe",
                it=f"Cluster '{body.name}' già esistente",
                nl=f"Cluster '{body.name}' bestaat al",
                pl=f"Klaster '{body.name}' już istnieje",
                pt=f"Cluster '{body.name}' já existe",
                ja=f"クラスター '{body.name}' は既に存在します",
                zh=f"集群 '{body.name}' 已存在",
            ),
        )

    # is_default: alle anderen auf False setzen
    if body.is_default:
        for c in clusters:
            c["is_default"] = False

    clusters.append(
        {
            "name": body.name,
            "context": body.context,
            "is_default": body.is_default or len(clusters) == 0,
        }
    )

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
        raise HTTPException(
            status_code=404,
            detail=_t(
                de=f"Cluster '{cluster_name}' nicht gefunden",
                en=f"Cluster '{cluster_name}' not found",
                fr=f"Cluster '{cluster_name}' non trouvé",
                es=f"Cluster '{cluster_name}' no encontrado",
                it=f"Cluster '{cluster_name}' non trovato",
                nl=f"Cluster '{cluster_name}' niet gevonden",
                pl=f"Klaster '{cluster_name}' nie znaleziono",
                pt=f"Cluster '{cluster_name}' não encontrado",
                ja=f"クラスター '{cluster_name}' が見つかりません",
                zh=f"未找到集群 '{cluster_name}'",
            ),
        )

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

REDIS_KEY_TTS = "ninko:settings:tts"


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
    allowed = {
        "TTS_ENABLED",
        "PIPER_BINARY",
        "VOICES_DIR",
        "TTS_DEFAULT_LANG",
        "TTS_DEFAULT_VOICE",
        "TTS_SAMPLE_RATE",
    }
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
    except _SETTINGS_RECOVERABLE_EXCEPTIONS as exc:
        logger.warning(
            "TTS-Service-Singleton konnte nicht zurückgesetzt werden: %s", exc
        )

    logger.info("TTS-Settings aktualisiert: %s", data)
    return {"status": "saved", **data}


# ═══════════════════════════════════════════════════════
#  STT Settings
# ═══════════════════════════════════════════════════════

REDIS_KEY_STT = "ninko:settings:stt"
_STT_ALLOWED = {
    "STT_PROVIDER",
    "WHISPER_MODEL_SIZE",
    "WHISPER_DEVICE",
    "WHISPER_COMPUTE_TYPE",
    "WHISPER_LANGUAGE",
    "STT_API_URL",
    "STT_API_KEY",
    "STT_MODEL",
    "STT_SPELLCHECK",
    "STT_CONFIDENCE_THRESHOLD",
}

REDIS_KEY_OCR = "ninko:settings:ocr"
_OCR_ALLOWED = {
    "OCR_PROVIDER",
    "OCR_PYTHON_ENGINE",
    "OCR_LANGUAGE",
    "OCR_VISION_API_URL",
    "OCR_VISION_API_KEY",
    "OCR_VISION_MODEL",
    "OCR_VISION_PROMPT",
}


@router.get("/stt")
async def get_stt_settings() -> dict:
    """STT-Konfiguration abrufen (Redis → Env → Default)."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_STT)
    if raw:
        data = json.loads(raw)
        key = (data.get("STT_API_KEY") or "").strip()
        data["STT_API_KEY"] = ""
        data["STT_API_KEY_SET"] = bool(key)
        return {"source": "redis", **data}

    cfg = get_settings()
    return {
        "source": "default",
        "STT_PROVIDER": cfg.STT_PROVIDER,
        "WHISPER_MODEL_SIZE": cfg.WHISPER_MODEL_SIZE,
        "WHISPER_DEVICE": cfg.WHISPER_DEVICE,
        "WHISPER_COMPUTE_TYPE": cfg.WHISPER_COMPUTE_TYPE,
        "WHISPER_LANGUAGE": cfg.WHISPER_LANGUAGE,
        "STT_API_URL": cfg.STT_API_URL,
        "STT_API_KEY": "",
        "STT_API_KEY_SET": bool((cfg.STT_API_KEY or "").strip()),
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
        except _SETTINGS_RECOVERABLE_EXCEPTIONS as exc:
            logger.warning("Whisper-Cache konnte nicht invalidiert werden: %s", exc)

    logger.info(
        "STT-Settings aktualisiert: %s",
        {k: v for k, v in data.items() if "KEY" not in k},
    )
    return {"status": "saved", **{k: v for k, v in data.items() if "KEY" not in k}}


# ═══════════════════════════════════════════════════════
#  OCR Settings
# ═══════════════════════════════════════════════════════


@router.get("/ocr")
async def get_ocr_settings() -> dict:
    """OCR/Vision-Konfiguration abrufen (Redis → Env → Default)."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_OCR)
    if raw:
        data = json.loads(raw)
        key = (data.get("OCR_VISION_API_KEY") or "").strip()
        data["OCR_VISION_API_KEY"] = ""
        data["OCR_VISION_API_KEY_SET"] = bool(key)
        return {"source": "redis", **data}

    cfg = get_settings()
    return {
        "source": "default",
        "OCR_PROVIDER": cfg.OCR_PROVIDER,
        "OCR_PYTHON_ENGINE": cfg.OCR_PYTHON_ENGINE,
        "OCR_LANGUAGE": cfg.OCR_LANGUAGE,
        "OCR_VISION_API_URL": cfg.OCR_VISION_API_URL,
        "OCR_VISION_API_KEY": "",
        "OCR_VISION_API_KEY_SET": bool((cfg.OCR_VISION_API_KEY or "").strip()),
        "OCR_VISION_MODEL": cfg.OCR_VISION_MODEL,
        "OCR_VISION_PROMPT": cfg.OCR_VISION_PROMPT,
    }


@router.put("/ocr")
async def update_ocr_settings(body: dict) -> dict:
    """OCR/Vision-Konfiguration in Redis speichern und sofort in ENV übernehmen."""
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_OCR)
    current_data = json.loads(raw) if raw else {}

    incoming = {k: v for k, v in body.items() if k in _OCR_ALLOWED}
    data = {**current_data, **incoming}

    provider = str(data.get("OCR_PROVIDER", "python")).strip().lower()
    if provider not in {"python", "llm_vision"}:
        raise HTTPException(status_code=400, detail="Ungültiger OCR_PROVIDER.")
    data["OCR_PROVIDER"] = provider

    engine = str(data.get("OCR_PYTHON_ENGINE", "pytesseract")).strip().lower()
    if engine not in {"pytesseract"}:
        raise HTTPException(status_code=400, detail="Ungültiger OCR_PYTHON_ENGINE.")
    data["OCR_PYTHON_ENGINE"] = engine

    # Maskiertes Feld im Frontend soll bestehenden Key beibehalten.
    # Nur ein expliziter leerer String löscht den Key.
    if "OCR_VISION_API_KEY" not in incoming:
        if "OCR_VISION_API_KEY" in current_data:
            data["OCR_VISION_API_KEY"] = current_data.get("OCR_VISION_API_KEY", "")
    else:
        data["OCR_VISION_API_KEY"] = str(incoming.get("OCR_VISION_API_KEY", "")).strip()

    data["OCR_LANGUAGE"] = str(data.get("OCR_LANGUAGE", "deu+eng")).strip() or "deu+eng"
    data["OCR_VISION_API_URL"] = str(data.get("OCR_VISION_API_URL", "")).strip()
    data["OCR_VISION_MODEL"] = str(data.get("OCR_VISION_MODEL", "")).strip()
    data["OCR_VISION_PROMPT"] = str(data.get("OCR_VISION_PROMPT", "")).strip() or (
        "Extract all readable text from this image. "
        "Return plain text only, preserving line breaks where possible."
    )

    await redis.connection.set(REDIS_KEY_OCR, json.dumps(data))

    for key, value in data.items():
        os.environ[key] = str(value).lower() if isinstance(value, bool) else str(value)
    import core.config

    core.config._settings = None

    logger.info(
        "OCR-Settings aktualisiert: %s",
        {k: v for k, v in data.items() if "KEY" not in k},
    )
    return {
        "status": "saved",
        **{k: v for k, v in data.items() if "KEY" not in k},
        "OCR_VISION_API_KEY_SET": bool((data.get("OCR_VISION_API_KEY") or "").strip()),
    }


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
        raise HTTPException(
            status_code=404,
            detail=_t(
                de=f"Cluster '{cluster_name}' nicht gefunden",
                en=f"Cluster '{cluster_name}' not found",
                fr=f"Cluster '{cluster_name}' non trouvé",
                es=f"Cluster '{cluster_name}' no encontrado",
                it=f"Cluster '{cluster_name}' non trovato",
                nl=f"Cluster '{cluster_name}' niet gevonden",
                pl=f"Klaster '{cluster_name}' nie znaleziono",
                pt=f"Cluster '{cluster_name}' não encontrado",
                ja=f"クラスター '{cluster_name}' が見つかりません",
                zh=f"未找到集群 '{cluster_name}'",
            ),
        )

    await redis.connection.set(REDIS_KEY_K8S_CLUSTERS, json.dumps(clusters))

    return {"name": cluster_name, "is_default": True, "status": "ok"}
