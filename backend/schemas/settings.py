"""
Ninko Settings – Pydantic-Modelle für Konfiguration.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


LLMBackend = Literal["ollama", "lmstudio", "mlx_server", "openai_compatible", "litellm"]


def normalize_llm_backend(value: str) -> str:
    """Normalize persisted/UI backend aliases before Pydantic Literal validation."""
    normalized = str(value or "").strip().lower().replace("-", "_")
    return "mlx_server" if normalized == "mlx" else normalized


# ── LLM Settings (Legacy – Einzelprovider) ───────────

class LlmSettings(BaseModel):
    """LLM/AI Provider Konfiguration (Legacy Single-Provider)."""
    backend: LLMBackend = "ollama"
    base_url: str = "http://ollama:11434"
    model: str = "llama3.2:3b"
    api_key: str = ""

    @field_validator("backend", mode="before")
    @classmethod
    def _normalize_backend(cls, value: str) -> str:
        return normalize_llm_backend(value)


class LlmSettingsResponse(LlmSettings):
    """Antwort mit Source-Info."""
    source: str = "default"  # "default" | "redis"
    api_key_set: bool = False


# ── LLM Multi-Provider ───────────────────────────────

class LLMProvider(BaseModel):
    """Ein konfigurierbarer LLM-Provider."""
    id: str = ""
    name: str
    backend: LLMBackend = "ollama"
    base_url: str = "http://ollama:11434"
    model: str = "llama3.2:3b"
    api_key: str = ""
    is_default: bool = False
    status: Literal["unknown", "connected", "unreachable"] = "unknown"
    created_at: Optional[str] = None
    # Manuelles Context-Window Override (0 = auto-detect)
    context_window: int = 0
    # SSL-Zertifikat-Verifizierung (False = self-signed Certs erlauben)
    verify_ssl: bool = True

    @field_validator("backend", mode="before")
    @classmethod
    def _normalize_backend(cls, value: str) -> str:
        return normalize_llm_backend(value)


class LLMProviderCreate(BaseModel):
    """Payload zum Erstellen/Ändern eines Providers."""
    name: str = Field(..., min_length=1, max_length=128)
    backend: LLMBackend = "ollama"
    base_url: str = "http://ollama:11434"
    model: str = "llama3.2:3b"
    api_key: str = ""
    is_default: bool = False
    # Manuelles Context-Window Override (0 = auto-detect via /v1/models)
    context_window: int = 0
    # SSL-Zertifikat-Verifizierung (False = self-signed Certs erlauben)
    verify_ssl: bool = True

    @field_validator("backend", mode="before")
    @classmethod
    def _normalize_backend(cls, value: str) -> str:
        return normalize_llm_backend(value)


# ── Module Settings ──────────────────────────────────

class ModuleSettingsItem(BaseModel):
    """Einzelne Modul-Konfiguration."""
    name: str
    display_name: str = ""
    enabled: bool = False
    description: str = ""
    version: str = ""
    connection: dict = Field(default_factory=dict)
    # connection keys per module:
    #   proxmox: host, user, token_id, verify_ssl
    #   glpi: base_url
    #   kubernetes: (managed via k8s clusters)


class ModuleToggleRequest(BaseModel):
    """Modul aktivieren/deaktivieren + Verbindungseinstellungen."""
    enabled: bool
    connection: dict = Field(default_factory=dict)


# ── Kubernetes Cluster Settings ──────────────────────

class K8sClusterInfo(BaseModel):
    """Cluster-Info ohne Kubeconfig (Read-Only)."""
    name: str
    context: str = ""
    is_default: bool = False
    has_kubeconfig: bool = False


class K8sClusterCreate(BaseModel):
    """Neuen Cluster anlegen."""
    name: str = Field(..., min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    context: str = ""
    kubeconfig_base64: str = Field(..., min_length=10)
    is_default: bool = False


class K8sClusterListResponse(BaseModel):
    """Liste aller konfigurierten Cluster."""
    clusters: list[K8sClusterInfo] = Field(default_factory=list)
    total: int = 0


# ── Branding Settings ─────────────────────────────────

class BrandingSettings(BaseModel):
    brand_name: str = "Ninko"
    page_title: str = "Ninko"
    logo_url: str = "/static/images/logo_icon.png"
    welcome_mode: Literal["image", "text", "off"] = "image"
    welcome_title: str = "Ninko"
    welcome_text: str = ""
    welcome_image_url: str = "/static/images/logo_dashboard_new.png?v=3"
    welcome_show_eyes: bool = True
    show_quick_actions: bool = True
    login_title: str = "Ninko Login"
    login_subtitle: str = "Bitte mit dem Admin-Account anmelden."
    login_help_url: str = "https://github.com/natorus87/ninko/blob/main/DOCS.md"
    login_head_mode: Literal["image", "text", "off"] = "image"
    login_image_url: str = "/static/images/logo_dashboard_new.png?v=3"
    login_show_eyes: bool = True
    login_background_style: Literal["aurora", "gradient", "minimal"] = "aurora"
    login_card_style: Literal["glass", "solid"] = "glass"


class BrandingSettingsResponse(BrandingSettings):
    source: str = "default"  # "default" | "redis"


# ── Background Settings ───────────────────────────────

_HEX_COLOR = r"^#[0-9a-fA-F]{6}$"


class BackgroundSettings(BaseModel):
    """Basisfarben des App-Hintergrunds (Settings → Themes → Hintergrundfarben)."""
    preset: str = Field(default="default", pattern=r"^[a-z0-9_-]{1,32}$")
    tint: str = Field(default="#070b24", pattern=_HEX_COLOR)
    accent1: str = Field(default="#6d28d9", pattern=_HEX_COLOR)
    accent2: str = Field(default="#007aff", pattern=_HEX_COLOR)


class BackgroundSettingsResponse(BackgroundSettings):
    source: str = "default"  # "default" | "redis"


# ── Generic Mutation / Status Responses ───────────────

class MutationResponse(BaseModel):
    """Standard response for simple state-mutating endpoints."""
    status: str = "ok"
    success: bool = True


# ── Embedding Model / Provider Responses ──────────────

class EmbedModelResponse(BaseModel):
    """Response for global embedding model settings."""
    embed_model: str


class EmbedModelUpdateResponse(EmbedModelResponse):
    """Response after updating the global embedding model."""
    status: str = "saved"


class EmbedProviderConfig(BaseModel):
    """Embedding-Provider-Konfiguration."""
    use_custom: bool = False
    backend: str = "lmstudio"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


class EmbedProviderResponse(EmbedProviderConfig):
    """Response after fetching/updating the embedding provider."""
    status: str = "saved"


# ── LLM Provider Management Responses ────────────────

class LlmProviderListResponse(BaseModel):
    """Response of list_llm_providers (sanitized)."""
    providers: list[dict] = Field(default_factory=list)
    total: int = 0


class LlmProviderCreateResponse(BaseModel):
    """Response after creating a new LLM provider."""
    id: str
    status: str = "created"


class LlmProviderUpdateResponse(BaseModel):
    """Response after updating an existing LLM provider."""
    id: str
    status: str = "updated"


class LlmProviderDeleteResponse(BaseModel):
    """Response after deleting an LLM provider."""
    id: str
    deleted: bool = True


class LlmProviderTestResponse(BaseModel):
    """Result of an LLM provider connectivity test."""
    id: str
    status: str  # "connected" | "unreachable"
    error: Optional[str] = None


class LlmProviderDiscoveryResponse(BaseModel):
    """Default / context-window discovery payload."""
    context_window: int
    source: str  # "manual" | "api" | "default"


class LlmProviderDefaultResponse(BaseModel):
    """Response after setting the default LLM provider."""
    provider_id: str
    is_default: bool = True


# ── Language / Routing Responses ─────────────────────

class LanguageResponse(BaseModel):
    """Current language setting."""
    language: str


class LanguageUpdateResponse(LanguageResponse):
    """Response after language change."""
    status: str = "saved"


class RoutingModeResponse(BaseModel):
    """Current routing mode (function calling)."""
    function_calling_enabled: bool
    tool_choice: str
    source: str = "default"


class FunctionCallingSmokeTestResponse(BaseModel):
    """Smoke-test result for function-calling support."""
    supported: bool
    error: Optional[str] = None
    recommendation: Optional[str] = None


# ── K8s Cluster Responses ─────────────────────────────

class K8sClusterCreateResponse(BaseModel):
    """Response after creating a new k8s cluster."""
    name: str
    status: str = "ok"


class K8sClusterDeleteResponse(BaseModel):
    """Response after deleting a k8s cluster."""
    name: str
    deleted: bool = True


class K8sClusterDefaultResponse(BaseModel):
    """Response after setting a cluster as default."""
    name: str
    is_default: bool = True
    status: str = "ok"


# ── Module Settings Responses ─────────────────────────

class ModuleUpdateResponse(BaseModel):
    """Response after updating a module's enabled flag and connection."""
    module: str
    enabled: bool
    status: str = "ok"
    restart_required: bool = False


# ── TTS / STT / OCR Responses ─────────────────────────

class TtsSettingsResponse(BaseModel):
    """TTS configuration response."""
    source: str = "default"
    TTS_ENABLED: bool = False
    PIPER_BINARY: str = ""
    VOICES_DIR: str = ""
    TTS_DEFAULT_LANG: str = ""
    TTS_DEFAULT_VOICE: str = ""
    TTS_SAMPLE_RATE: Optional[int] = None


class TtsSettingsUpdateResponse(TtsSettingsResponse):
    """Response after updating TTS settings."""
    status: str = "saved"


class SttSettingsResponse(BaseModel):
    """STT configuration response (secrets masked)."""
    source: str = "default"
    STT_PROVIDER: str = ""
    WHISPER_MODEL_SIZE: str = ""
    WHISPER_DEVICE: str = ""
    WHISPER_COMPUTE_TYPE: str = ""
    WHISPER_LANGUAGE: str = ""
    STT_API_URL: str = ""
    STT_API_KEY: str = ""
    STT_API_KEY_SET: bool = False
    STT_MODEL: str = ""
    STT_SPELLCHECK: bool = False
    STT_CONFIDENCE_THRESHOLD: float = 0.0


class SttSettingsUpdateResponse(BaseModel):
    """Response after updating STT settings (secrets masked)."""
    status: str = "saved"
    STT_PROVIDER: str = ""
    WHISPER_MODEL_SIZE: str = ""
    WHISPER_DEVICE: str = ""
    WHISPER_COMPUTE_TYPE: str = ""
    WHISPER_LANGUAGE: str = ""
    STT_API_URL: str = ""
    STT_API_KEY: str = ""
    STT_API_KEY_SET: bool = False
    STT_MODEL: str = ""
    STT_SPELLCHECK: bool = False
    STT_CONFIDENCE_THRESHOLD: float = 0.0


class OcrSettingsResponse(BaseModel):
    """OCR/Vision configuration response (secrets masked)."""
    source: str = "default"
    OCR_PROVIDER: str = ""
    OCR_PYTHON_ENGINE: str = ""
    OCR_LANGUAGE: str = ""
    OCR_VISION_API_URL: str = ""
    OCR_VISION_API_KEY: str = ""
    OCR_VISION_API_KEY_SET: bool = False
    OCR_VISION_MODEL: str = ""
    OCR_VISION_PROMPT: str = ""


class OcrSettingsUpdateResponse(OcrSettingsResponse):
    """Response after updating OCR settings."""
    status: str = "saved"


# ── Branding Asset Responses ──────────────────────────

class BrandingAssetUploadResponse(BaseModel):
    """Response after uploading a branding asset."""
    filename: str
    url: str
    size: int


class BrandingAssetDeleteResponse(BaseModel):
    """Response after deleting a branding asset."""
    deleted: bool
    filename: str
