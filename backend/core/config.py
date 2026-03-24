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
    LLM_BACKEND: Literal["ollama", "lmstudio", "openai_compatible"] = "lmstudio"
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

    # ── Monitoring ─────────────────────────────────────
    MONITOR_INTERVAL_SECONDS: int = 300
    MONITOR_AUTO_REMEDIATE: bool = False

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


# Singleton-Instanz
_settings: CoreSettings | None = None


def get_settings() -> CoreSettings:
    """Gibt die globale Settings-Instanz zurück (lazy init)."""
    global _settings
    if _settings is None:
        _settings = CoreSettings()
    return _settings
