"""Regression tests for Telegram bot response cleanup helpers."""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path

_BOT_PATH = Path(__file__).resolve().parents[1] / "modules_catalog" / "telegram" / "bot.py"

sys.modules.setdefault("core", types.ModuleType("core"))
redis_client = types.ModuleType("core.redis_client")
redis_client.get_redis = lambda: None
sys.modules["core.redis_client"] = redis_client

agents = types.ModuleType("agents")
base_agent = types.ModuleType("agents.base_agent")
base_agent._t = lambda de, en=None, **_: de
sys.modules.setdefault("agents", agents)
sys.modules["agents.base_agent"] = base_agent

fastapi = types.ModuleType("fastapi")
fastapi.FastAPI = type("FastAPI", (), {})
sys.modules["fastapi"] = fastapi

formatter = types.ModuleType("telegram_bot_formatter")
formatter.format_for_telegram = lambda text: text
sys.modules["telegram_bot.formatter"] = formatter

_SPEC = importlib.util.spec_from_file_location(
    "telegram_bot",
    _BOT_PATH,
    submodule_search_locations=[str(_BOT_PATH.parent)],
)
assert _SPEC and _SPEC.loader
_BOT = importlib.util.module_from_spec(_SPEC)
sys.modules["telegram_bot"] = _BOT
_SPEC.loader.exec_module(_BOT)
_strip_pipeline_headers = _BOT._strip_pipeline_headers


def test_strip_pipeline_headers_removes_module_footer() -> None:
    response = "Cluster sieht gesund aus.\n\n_via kubernetes_"

    assert _strip_pipeline_headers(response) == "Cluster sieht gesund aus."
