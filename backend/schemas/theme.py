"""
Theme schemas for UI customization.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ThemeDefinition(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    version: str = "1.0.0"
    author: str = "Ninko"
    preview_url: str = ""
    tokens_dark: dict[str, str] = Field(default_factory=dict)
    tokens_light: dict[str, str] = Field(default_factory=dict)


class ThemeSummary(BaseModel):
    id: str
    name: str
    description: str = ""
    version: str = ""
    author: str = ""
    preview_url: str = ""
    is_builtin: bool = False
    is_active: bool = False
    source: str = "builtin"


class ThemeListResponse(BaseModel):
    themes: list[ThemeSummary] = Field(default_factory=list)
    active_theme_id: str = "default"


class ThemeActiveUpdate(BaseModel):
    theme_id: str


class ThemeRepo(BaseModel):
    id: str = ""
    name: str
    repo_url: str
    branch: str = "main"
    themes_path: str = "backend/themes"
    github_token: str = ""


class ThemeRepoCreate(BaseModel):
    name: str
    repo_url: str
    branch: str = "main"
    themes_path: str = "backend/themes"
    github_token: str = ""
