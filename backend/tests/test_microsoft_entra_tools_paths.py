from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest


BACKEND_DIR = Path(__file__).resolve().parents[1]
TOOLS_PATH = BACKEND_DIR / "modules_catalog" / "microsoft_entra" / "tools.py"
spec = importlib.util.spec_from_file_location("microsoft_entra_tools_under_test", TOOLS_PATH)
assert spec is not None
assert spec.loader is not None
entra_tools = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = entra_tools
spec.loader.exec_module(entra_tools)


class GraphCapture:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, dict[str, Any] | None]] = []

    async def __call__(
        self,
        method: str,
        path: str,
        token: str,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((method, path, token, json))
        if path.startswith("/groups?"):
            return {"value": [{"id": "group-id-123", "displayName": "Ops"}]}
        if path.startswith("/users/"):
            return {
                "id": "user-object-id-456",
                "displayName": "John Example",
                "userPrincipalName": "john.doe@example.com",
                "accountEnabled": True,
            }
        return {"status": "OK"}


@pytest.fixture
def graph_capture(monkeypatch: pytest.MonkeyPatch) -> GraphCapture:
    capture = GraphCapture()

    async def fake_get_token(connection_id: str = "") -> str:
        return "token-123"

    monkeypatch.setattr(entra_tools, "_get_token", fake_get_token)
    monkeypatch.setattr(entra_tools, "_graph_request", capture)
    return capture


async def test_get_user_details_uses_url_encoded_upn(graph_capture: GraphCapture) -> None:
    result = await entra_tools.get_user_details.ainvoke(
        {"user_principal_name": "john.doe@example.com"}
    )

    assert "john.doe@example.com" in result
    assert graph_capture.calls[0] == (
        "GET",
        "/users/john.doe%40example.com",
        "token-123",
        None,
    )


async def test_disable_user_uses_url_encoded_upn(graph_capture: GraphCapture) -> None:
    await entra_tools.disable_entra_user.ainvoke(
        {"user_principal_name": "john.doe@example.com"}
    )

    assert graph_capture.calls == [
        (
            "PATCH",
            "/users/john.doe%40example.com",
            "token-123",
            {"accountEnabled": False},
        )
    ]


async def test_reset_password_uses_url_encoded_upn(graph_capture: GraphCapture) -> None:
    await entra_tools.reset_entra_user_password.ainvoke(
        {
            "user_principal_name": "john.doe@example.com",
            "new_password": "new-password",
        }
    )

    assert graph_capture.calls == [
        (
            "PATCH",
            "/users/john.doe%40example.com",
            "token-123",
            {
                "passwordProfile": {
                    "forceChangePasswordNextSignIn": False,
                    "password": "new-password",
                }
            },
        )
    ]


async def test_add_user_to_group_resolves_user_object_id_and_escapes_group_filter(
    graph_capture: GraphCapture,
) -> None:
    await entra_tools.add_user_to_group.ainvoke(
        {
            "user_principal_name": "john.doe@example.com",
            "group_name": "Ops's Team",
        }
    )

    assert graph_capture.calls == [
        (
            "GET",
            "/groups?$filter=displayName eq 'Ops''s Team'",
            "token-123",
            None,
        ),
        (
            "GET",
            "/users/john.doe%40example.com",
            "token-123",
            None,
        ),
        (
            "POST",
            "/groups/group-id-123/members/$ref",
            "token-123",
            {
                "@odata.id": (
                    "https://graph.microsoft.com/v1.0/directoryObjects/"
                    "user-object-id-456"
                )
            },
        ),
    ]

