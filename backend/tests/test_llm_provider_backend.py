from __future__ import annotations

import os

from api.routes_settings import _apply_default_provider
from core.config import get_settings
from core.llm_factory import get_llm_generation
from schemas.settings import LLMProviderCreate, LlmSettings


def test_mlx_backend_aliases_are_accepted() -> None:
    assert LlmSettings(backend="mlx-server").backend == "mlx_server"
    assert LLMProviderCreate(
        name="MLX",
        backend="mlx",
        base_url="http://mlx-server:8080/v1",
        model="qwen3",
    ).backend == "mlx_server"


def test_apply_default_provider_switches_runtime_to_mlx_server(monkeypatch) -> None:
    monkeypatch.setenv("API_AUTH_ENABLED", "false")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("BOOTSTRAP_ADMIN_PASSWORD", "test-password")

    import core.config

    core.config._settings = None
    before_generation = get_llm_generation()

    _apply_default_provider(
        [
            {
                "id": "lmstudio",
                "name": "LM Studio",
                "backend": "lmstudio",
                "base_url": "http://lmstudio:1234/v1",
                "model": "old-model",
                "is_default": False,
            },
            {
                "id": "mlx",
                "name": "MLX Server",
                "backend": "mlx-server",
                "base_url": "http://mlx-server:8080/v1",
                "model": "qwen3",
                "is_default": True,
            },
        ]
    )

    settings = get_settings()
    assert os.environ["LLM_BACKEND"] == "mlx_server"
    assert settings.LLM_BACKEND == "mlx_server"
    assert settings.MLX_BASE_URL == "http://mlx-server:8080/v1"
    assert settings.MLX_MODEL == "qwen3"
    assert get_llm_generation() > before_generation

    core.config._settings = None
