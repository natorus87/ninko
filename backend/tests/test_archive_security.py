from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from api.routes_plugins import _extract_zip_members_safely
from api.routes_plugins import _safe_child_path as plugin_safe_child_path
from api.routes_plugins import _validate_repo_subpath
from api.routes_themes import _safe_child_path as theme_safe_child_path
from api.routes_themes import _validate_branch


@pytest.mark.parametrize("safe_child_path", [plugin_safe_child_path, theme_safe_child_path])
def test_safe_child_path_accepts_nested_relative_paths(tmp_path, safe_child_path) -> None:
    target = safe_child_path(tmp_path, "nested/file.txt")

    assert target == (tmp_path / "nested" / "file.txt").resolve()


@pytest.mark.parametrize(
    "relative_path",
    [
        "../outside.py",
        "nested/../../outside.py",
        "/absolute.py",
        "\\absolute.py",
    ],
)
@pytest.mark.parametrize("safe_child_path", [plugin_safe_child_path, theme_safe_child_path])
def test_safe_child_path_rejects_traversal(tmp_path, safe_child_path, relative_path) -> None:
    with pytest.raises(HTTPException):
        safe_child_path(tmp_path, relative_path)


def test_theme_branch_validation_rejects_parent_segments() -> None:
    with pytest.raises(HTTPException):
        _validate_branch("../main")


def test_plugin_repo_subpath_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        _validate_repo_subpath("../backend/modules_catalog")


def test_plugin_repo_subpath_accepts_catalog_path() -> None:
    assert _validate_repo_subpath("/backend/modules_catalog/") == "backend/modules_catalog"


def test_plugin_zip_extraction_rejects_sibling_prefix_traversal(tmp_path) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("../extracted_evil/pwn.py", "print('owned')")
    payload.seek(0)

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(payload, "r") as zf:
        with pytest.raises(HTTPException):
            _extract_zip_members_safely(zf, extract_dir, zf.infolist())

    assert not (tmp_path / "extracted_evil" / "pwn.py").exists()


def test_plugin_zip_extraction_accepts_nested_files(tmp_path) -> None:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as zf:
        zf.writestr("plugin/__init__.py", "")
        zf.writestr("plugin/frontend/tab.js", "window.PluginTab = {};")
    payload.seek(0)

    extract_dir = tmp_path / "extracted"
    with zipfile.ZipFile(payload, "r") as zf:
        _extract_zip_members_safely(zf, extract_dir, zf.infolist())

    assert (extract_dir / "plugin" / "__init__.py").exists()
    assert (extract_dir / "plugin" / "frontend" / "tab.js").read_text() == "window.PluginTab = {};"
