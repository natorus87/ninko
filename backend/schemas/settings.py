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
    login_subtitle: str = "Please sign in with your admin account."
    login_help_url: str = "https://github.com/natorus87/ninko/blob/main/DOCS.md"
    login_head_mode: Literal["image", "text", "off"] = "image"
    login_image_url: str = "/static/images/logo_dashboard_new.png?v=3"
    login_show_eyes: bool = True
    login_background_style: Literal["aurora", "gradient", "minimal"] = "aurora"
    login_card_style: Literal["glass", "solid"] = "glass"


class BrandingSettingsResponse(BrandingSettings):
    source: str = "default"  # "default" | "redis"
