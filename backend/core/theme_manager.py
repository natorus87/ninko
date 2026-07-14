"""
Theme storage/loader for built-in and custom themes.
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from pydantic import ValidationError

from core.redis_client import get_redis
from schemas.theme import ThemeDefinition, ThemeSummary

logger = logging.getLogger("ninko.core.theme_manager")

REDIS_KEY_THEME_ACTIVE = "ninko:settings:theme_active"

_REPO_ROOT = Path(__file__).resolve().parents[2]
BUILTIN_THEMES_DIR = Path("/app/themes") if Path("/app/themes").exists() else (_REPO_ROOT / "backend" / "themes")
CUSTOM_THEMES_DIR = Path("/app/data/themes") if Path("/app/data").exists() else (_REPO_ROOT / "data" / "themes")
CUSTOM_THEMES_DIR.mkdir(parents=True, exist_ok=True)

_THEME_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")
_CSS_VAR_RE = re.compile(r"^--[a-zA-Z0-9\-_]{1,64}$")


def validate_theme_id(theme_id: str) -> bool:
    return bool(_THEME_ID_RE.fullmatch(theme_id or ""))


def _sanitize_tokens(tokens: dict[str, str] | None) -> dict[str, str]:
    if not isinstance(tokens, dict):
        return {}
    cleaned: dict[str, str] = {}
    for key, value in tokens.items():
        if isinstance(key, str) and isinstance(value, str) and _CSS_VAR_RE.fullmatch(key):
            cleaned[key] = value.strip()[:256]
    return cleaned


def _theme_dir(base: Path, theme_id: str) -> Path:
    return base / theme_id


def _theme_file(base: Path, theme_id: str) -> Path:
    return _theme_dir(base, theme_id) / "theme.json"


def _load_theme_file(path: Path) -> ThemeDefinition | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data["tokens_dark"] = _sanitize_tokens(data.get("tokens_dark", {}))
        data["tokens_light"] = _sanitize_tokens(data.get("tokens_light", {}))
        theme = ThemeDefinition(**data)
        if not validate_theme_id(theme.id):
            return None
        return theme
    except (OSError, json.JSONDecodeError, TypeError, ValueError, ValidationError):
        return None


def _iter_themes(base: Path) -> dict[str, ThemeDefinition]:
    result: dict[str, ThemeDefinition] = {}
    if not base.is_dir():
        return result
    for child in base.iterdir():
        if not child.is_dir():
            continue
        theme = _load_theme_file(child / "theme.json")
        if theme is None:
            continue
        result[theme.id] = theme
    return result


def list_builtin_themes() -> dict[str, ThemeDefinition]:
    return _iter_themes(BUILTIN_THEMES_DIR)


def list_custom_themes() -> dict[str, ThemeDefinition]:
    return _iter_themes(CUSTOM_THEMES_DIR)


def get_all_themes() -> dict[str, ThemeDefinition]:
    all_themes = list_builtin_themes()
    all_themes.update(list_custom_themes())
    return all_themes


async def get_active_theme_id() -> str:
    redis = get_redis()
    raw = await redis.connection.get(REDIS_KEY_THEME_ACTIVE)
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="ignore")
    theme_id = (raw or "default").strip()
    if theme_id in get_all_themes():
        return theme_id
    return "default"


async def set_active_theme_id(theme_id: str) -> None:
    redis = get_redis()
    await redis.connection.set(REDIS_KEY_THEME_ACTIVE, theme_id)


def save_custom_theme(theme: ThemeDefinition) -> ThemeDefinition:
    if not validate_theme_id(theme.id):
        raise ValueError("Invalid theme id.")
    theme.tokens_dark = _sanitize_tokens(theme.tokens_dark)
    theme.tokens_light = _sanitize_tokens(theme.tokens_light)
    d = _theme_dir(CUSTOM_THEMES_DIR, theme.id)
    d.mkdir(parents=True, exist_ok=True)
    _theme_file(CUSTOM_THEMES_DIR, theme.id).write_text(
        json.dumps(theme.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return theme


def delete_custom_theme(theme_id: str) -> bool:
    if not validate_theme_id(theme_id):
        return False
    d = _theme_dir(CUSTOM_THEMES_DIR, theme_id)
    if not d.is_dir():
        return False
    for p in sorted(d.rglob("*"), reverse=True):
        if p.is_file():
            p.unlink(missing_ok=True)
        elif p.is_dir():
            try:
                p.rmdir()
            except OSError:
                pass
    try:
        d.rmdir()
    except OSError:
        pass
    return True


def summarize(theme: ThemeDefinition, *, is_builtin: bool, is_active: bool, source: str) -> ThemeSummary:
    return ThemeSummary(
        id=theme.id,
        name=theme.name,
        description=theme.description,
        version=theme.version,
        author=theme.author,
        preview_url=theme.preview_url,
        is_builtin=is_builtin,
        is_active=is_active,
        source=source,
    )
