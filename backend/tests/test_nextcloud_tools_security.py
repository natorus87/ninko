from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
TOOLS_PATH = BACKEND_DIR / "modules_catalog" / "nextcloud" / "tools.py"
spec = importlib.util.spec_from_file_location("nextcloud_tools_under_test", TOOLS_PATH)
assert spec is not None
assert spec.loader is not None
nextcloud_tools = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = nextcloud_tools
spec.loader.exec_module(nextcloud_tools)


class FakeResponse:
    status = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    async def __aenter__(self) -> "FakeResponse":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    def raise_for_status(self) -> None:
        return None

    async def json(self) -> dict[str, Any]:
        return self.payload


class FakeSession:
    last_session_headers: dict[str, str] | None = None
    last_request: tuple[str, str, dict[str, Any] | None] | None = None

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        FakeSession.last_session_headers = kwargs.get("headers")

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None

    def request(self, method: str, url: str, json: dict[str, Any] | None = None) -> FakeResponse:
        FakeSession.last_request = (method, url, json)
        return FakeResponse({"ocs": {"data": {"users": ["alice"]}}})


async def test_ocs_request_forces_json_format_and_accept_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nextcloud_tools.aiohttp, "ClientSession", FakeSession)
    client = {"base_url": "https://cloud.example", "user": "admin", "password": "secret"}

    result = await nextcloud_tools._ocs_request("GET", "/cloud/users", client)

    assert result == {"users": ["alice"]}
    assert FakeSession.last_session_headers is not None
    assert FakeSession.last_session_headers["OCS-APIREQUEST"] == "true"
    assert FakeSession.last_session_headers["Accept"] == "application/json"
    assert FakeSession.last_request == (
        "GET",
        "https://cloud.example/ocs/v2.php/cloud/users?format=json",
        None,
    )


async def test_ocs_request_preserves_existing_query_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(nextcloud_tools.aiohttp, "ClientSession", FakeSession)
    client = {"base_url": "https://cloud.example", "user": "admin", "password": "secret"}

    await nextcloud_tools._ocs_request(
        "GET",
        "/apps/files_sharing/api/v1/shares?path=/&search=report",
        client,
    )

    assert FakeSession.last_request == (
        "GET",
        "https://cloud.example/ocs/v2.php/apps/files_sharing/api/v1/shares"
        "?path=/&search=report&format=json",
        None,
    )


def test_parse_webdav_list_uses_safe_parser_for_normal_xml() -> None:
    xml = """<?xml version="1.0"?>
    <d:multistatus xmlns:d="DAV:">
      <d:response>
        <d:href>/remote.php/dav/files/admin/report.txt</d:href>
        <d:propstat>
          <d:prop><d:getcontentlength>2048</d:getcontentlength></d:prop>
        </d:propstat>
      </d:response>
    </d:multistatus>
    """

    assert nextcloud_tools._parse_webdav_list(xml) == [
        {
            "name": "report.txt",
            "path": "/remote.php/dav/files/admin/report.txt",
            "type": "file",
            "size": 2048,
        }
    ]


def test_parse_webdav_list_rejects_xml_entities() -> None:
    xml = """<?xml version="1.0"?>
    <!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
    <d:multistatus xmlns:d="DAV:">
      <d:response><d:href>&xxe;</d:href><d:propstat /></d:response>
    </d:multistatus>
    """

    assert nextcloud_tools._parse_webdav_list(xml) == []

