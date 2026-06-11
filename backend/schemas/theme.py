"""
Theme schemas for UI customization.
"""

from __future__ import annotations

from typing import Any

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


class ThemeItemResponse(BaseModel):
    """Single-theme response (full definition)."""
    theme: dict[str, Any]


class ThemeActiveResponse(BaseModel):
    """Currently active theme."""
    theme_id: str
    theme: dict[str, Any] = Field(default_factory=dict)


class ThemeActivateResponse(BaseModel):
    """Response after activating a theme."""
    theme_id: str
    status: str = "active"


class ThemeDeleteResponse(BaseModel):
    """Response after deleting a custom theme."""
    deleted: bool = True
    theme_id: str


class ThemeDuplicateResponse(BaseModel):
    """Response after duplicating a theme."""
    theme_id: str
    status: str = "created"


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


class ThemeRepoListResponse(BaseModel):
    """List of theme repos (tokens masked)."""
    repos: list[dict[str, Any]] = Field(default_factory=list)


class ThemeRepoAddResponse(BaseModel):
    """Response after adding a new repo."""
    repo: dict[str, Any]


class ThemeRepoUpdateResponse(BaseModel):
    """Response after updating a repo."""
    repo: dict[str, Any]


class ThemeRepoDeleteResponse(BaseModel):
    """Response after deleting a repo."""
    deleted: bool = True


class ThemeRepoThemeSummary(BaseModel):
    """A theme entry from a remote repo."""
    id: str
    name: str
    description: str = ""
    author: str = ""
    version: str = ""


class ThemeRepoThemesResponse(BaseModel):
    """Themes discovered in a remote repo."""
    themes: list[ThemeRepoThemeSummary] = Field(default_factory=list)
    repo_id: str


class ThemeInstallResponse(BaseModel):
    """Response after installing a theme from a repo."""
    installed: bool = True
    theme_id: str
