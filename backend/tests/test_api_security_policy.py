from __future__ import annotations

from core.api_security_policy import extract_module_id_from_path, required_role_for_request
from core.auth import ROLE_ADMIN, ROLE_READ, ROLE_WRITE


def test_unknown_core_api_reads_require_auth() -> None:
    sensitive_reads = [
        "/api/chat/ui-history",
        "/api/chat/history/session-1",
        "/api/audit/tools",
        "/api/metrics/tokens",
        "/api/knowledge-graph/entities",
        "/api/skills/example",
        "/api/images/example.png",
    ]

    for path in sensitive_reads:
        assert required_role_for_request(path, "GET") == ROLE_READ


def test_unknown_core_api_writes_require_write_role() -> None:
    assert required_role_for_request("/api/custom-core-ish/action", "POST") == ROLE_WRITE


def test_explicit_public_paths_stay_public() -> None:
    assert required_role_for_request("/health", "GET") is None
    assert required_role_for_request("/api/auth/login", "POST") is None
    assert required_role_for_request("/api/auth/me", "GET") is None
    assert required_role_for_request("/api/themes/active", "GET") is None
    assert required_role_for_request("/api/settings/branding", "GET") is None
    assert required_role_for_request("/api/settings/branding/assets/logo.png", "GET") is None


def test_admin_and_write_prefixes_keep_expected_roles() -> None:
    assert required_role_for_request("/api/plugins/installed", "GET") == ROLE_ADMIN
    assert required_role_for_request("/api/settings/llm", "PUT") == ROLE_ADMIN
    assert required_role_for_request("/api/connections/linux_server", "POST") == ROLE_WRITE
    assert required_role_for_request("/api/workflows/", "GET") == ROLE_READ


def test_module_path_extraction_ignores_core_prefixes() -> None:
    assert extract_module_id_from_path("/api/chat/ui-history") is None
    assert extract_module_id_from_path("/api/metrics/tokens") is None
    assert extract_module_id_from_path("/api/linux_server/info") == "linux_server"
