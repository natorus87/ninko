from __future__ import annotations

import base64
import importlib.util
import sys
import types
from email.mime.multipart import MIMEMultipart
from pathlib import Path

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
EMAIL_PACKAGE_DIR = BACKEND_DIR / "modules_catalog" / "email"
package = types.ModuleType("email_tools_under_test")
package.__path__ = [str(EMAIL_PACKAGE_DIR)]
sys.modules["email_tools_under_test"] = package

TOOLS_PATH = EMAIL_PACKAGE_DIR / "tools.py"
spec = importlib.util.spec_from_file_location("email_tools_under_test.tools", TOOLS_PATH)
assert spec is not None
assert spec.loader is not None
email_tools = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = email_tools
spec.loader.exec_module(email_tools)


def test_xoauth2_uses_control_characters_and_smtp_base64() -> None:
    auth_string = email_tools._xoauth2_auth_string("bot@example.com", "token-123")

    assert auth_string == "user=bot@example.com\x01auth=Bearer token-123\x01\x01"
    assert "\\x01" not in auth_string

    smtp_arg = email_tools._xoauth2_smtp_argument("bot@example.com", "token-123")
    decoded = base64.b64decode(smtp_arg).decode("utf-8")
    assert decoded == auth_string


def test_attach_file_allows_files_inside_upload_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_dir = tmp_path / "uploads" / "email"
    upload_dir.mkdir(parents=True)
    attachment = upload_dir / "report.txt"
    attachment.write_text("hello", encoding="utf-8")
    monkeypatch.setattr(email_tools, "EMAIL_UPLOAD_DIR", upload_dir)
    message = MIMEMultipart()

    assert email_tools._attach_file(message, "report.txt") is True

    attachment_parts = message.get_payload()
    assert len(attachment_parts) == 1
    assert attachment_parts[0].get_filename() == "report.txt"


def test_attach_file_rejects_paths_outside_upload_dir(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_dir = tmp_path / "uploads" / "email"
    upload_dir.mkdir(parents=True)
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(email_tools, "EMAIL_UPLOAD_DIR", upload_dir)

    with pytest.raises(ValueError, match="outside|außerhalb"):
        email_tools._attach_file(MIMEMultipart(), str(outside_file))


def test_attach_file_rejects_symlink_escape(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    upload_dir = tmp_path / "uploads" / "email"
    upload_dir.mkdir(parents=True)
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text("secret", encoding="utf-8")
    symlink = upload_dir / "report.txt"
    symlink.symlink_to(outside_file)
    monkeypatch.setattr(email_tools, "EMAIL_UPLOAD_DIR", upload_dir)

    with pytest.raises(ValueError, match="outside|außerhalb"):
        email_tools._attach_file(MIMEMultipart(), "report.txt")
