"""
Ninko Core Configuration – Pydantic BaseSettings.
Nur Core-Konfiguration, keine Modul-spezifischen Einstellungen.
"""

from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Zentrale Konfiguration für den Ninko Core."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM Backend ────────────────────────────────────
    LLM_BACKEND: Literal["ollama", "lmstudio", "openai_compatible", "litellm"] = "lmstudio"
    # LM Studio / OpenAI-kompatibler Provider (Standard)
    LMSTUDIO_BASE_URL: str = "http://192.168.1.100:1234/v1"
    LMSTUDIO_MODEL: str = "local-model"
    # Ollama – nur noch als Legacy-Fallback für lokale Entwicklung
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_MODEL: str = "qwen2.5:4b"
    # OpenAI-kompatibel (OpenRouter, Groq, Together, etc.)
    OPENAI_BASE_URL: str = "https://openrouter.ai/api/v1"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "anthropic/claude-sonnet-4"
    # LiteLLM Proxy (self-hosted, requires API key)
    LITELLM_BASE_URL: str = "http://litellm:4000/v1"
    LITELLM_MODEL: str = "gpt-4"
    LITELLM_API_KEY: str = ""
    # Globales Embedding-Modell (einheitlich für ChromaDB)
    EMBED_MODEL: str = "nomic-ai/nomic-embed-text-v1.5-GGUF"

    # ── ChromaDB ───────────────────────────────────────
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000

    # ── Redis ──────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379/0"

    # ── Vault ──────────────────────────────────────────
    VAULT_ADDR: str = "http://vault:8200"
    VAULT_TOKEN: str = ""
    VAULT_FALLBACK: Literal["sqlite", "none"] = "sqlite"
    SQLITE_SECRETS_KEY: str = ""

    # ── LLM Inference ──────────────────────────────────
    LLM_TEMPERATURE: float = 0.1
    # ── Context / RAG ──────────────────────────────────
    MAX_CONTEXT_TOKENS: int = 4096
    CONTEXT_RESET_THRESHOLD: float = 0.75
    RAG_TOP_K: int = 5
    MAX_OUTPUT_TOKENS: int = 16384

    # ── General ────────────────────────────────────────
    LOG_LEVEL: str = "INFO"
    LANGUAGE: str = "de"
    TIMEZONE: str = "Europe/Berlin"
    LLM_VERIFY_SSL: bool = True  # False = self-signed Zertifikate erlauben

    # ── API Security ───────────────────────────────────
    API_AUTH_ENABLED: bool = False
    API_KEY_ADMIN: str = ""
    API_KEY_WRITE: str = ""
    API_KEY_READ: str = ""
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = ""
    SESSION_SECRET: str = "change-me-in-production"
    SESSION_TTL_HOURS: int = 24
    SESSION_COOKIE_NAME: str = "ninko_session"
    SESSION_COOKIE_SECURE: bool = False

    # ── API Rate Limiting ──────────────────────────────
    API_RATE_LIMIT_ENABLED: bool = True
    API_RATE_LIMIT_PER_MINUTE: int = 120
    API_RATE_LIMIT_BURST: int = 30

    # ── Upload Security ────────────────────────────────
    TRANSCRIPTION_MAX_UPLOAD_BYTES: int = 15 * 1024 * 1024
    TRANSCRIPTION_ALLOWED_MIME: str = (
        "audio/webm,audio/ogg,audio/mpeg,audio/mp3,audio/wav,audio/x-wav,audio/mp4"
    )
    TRANSCRIPTION_ALLOWED_EXTENSIONS: str = ".webm,.ogg,.mp3,.wav,.m4a,.mp4"
    BRANDING_MAX_UPLOAD_BYTES: int = 5 * 1024 * 1024

    # ── CORS ───────────────────────────────────────────
    CORS_ALLOW_ORIGINS: str = "http://localhost:8000,http://127.0.0.1:8000"
    CORS_ALLOW_METHODS: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    CORS_ALLOW_HEADERS: str = "Authorization,Content-Type,X-API-Key"
    CORS_ALLOW_CREDENTIALS: bool = True

    # ── Safeguard ──────────────────────────────────────
    SAFEGUARD_TIMEOUT_SECONDS: float = 8.0

    # ── Monitoring ─────────────────────────────────────
    MONITOR_INTERVAL_SECONDS: int = 300
    MONITOR_AUTO_REMEDIATE: bool = False
    AGENT_TIMEOUT_SECONDS: int = 1800
    AGENT_JIT_THRESHOLD: int = 6
    AGENT_JIT_MAX_TOOLS: int = 8
    AGENT_MEMORIZE_COOLDOWN_SECS: float = 60.0

    # ── TTS (Piper) ────────────────────────────────────
    TTS_ENABLED: bool = False
    PIPER_BINARY: str = "piper"
    VOICES_DIR: str = "/app/data/voices"
    TTS_DEFAULT_LANG: str = "de"
    TTS_DEFAULT_VOICE: str = "thorsten-medium"
    TTS_SAMPLE_RATE: int = 22050

    # ── STT ─────────────────────────────────────────────
    STT_PROVIDER: Literal["whisper", "openai_compatible"] = "whisper"
    # Whisper (built-in)
    WHISPER_MODEL_SIZE: str = "base"
    WHISPER_DEVICE: str = "cpu"
    WHISPER_COMPUTE_TYPE: str = "int8"
    WHISPER_LANGUAGE: str = "de"
    # OpenAI-compatible STT (Groq, OpenAI, etc.)
    STT_API_URL: str = ""
    STT_API_KEY: str = ""
    STT_MODEL: str = "whisper-large-v3"
    # Gemeinsam
    STT_SPELLCHECK: bool = False
    STT_CONFIDENCE_THRESHOLD: float = -1.0  # avg_logprob unter diesem Wert = unsicher

    # ── OCR / Vision ───────────────────────────────────
    OCR_PROVIDER: Literal["python", "llm_vision"] = "python"
    OCR_PYTHON_ENGINE: Literal["pytesseract"] = "pytesseract"
    OCR_LANGUAGE: str = "deu+eng"
    OCR_VISION_API_URL: str = ""
    OCR_VISION_API_KEY: str = ""
    OCR_VISION_MODEL: str = ""
    OCR_VISION_PROMPT: str = (
        "Extract all readable text from this image. "
        "Return plain text only, preserving line breaks where possible."
    )


# Singleton-Instanz
_settings: CoreSettings | None = None


def get_settings() -> CoreSettings:
    """Gibt die globale Settings-Instanz zurück (lazy init)."""
    global _settings
    if _settings is None:
        _settings = CoreSettings()
    return _settings
