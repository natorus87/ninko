from __future__ import annotations

import pytest

from core import status_bus
from core.auth import get_current_tenant_id, reset_current_tenant_id, set_current_tenant_id
from core.connections import ConnectionManager


@pytest.fixture
def session_id_token():
    saved = status_bus._session_id_var.get()
    try:
        yield
    finally:
        if saved:
            status_bus.set_session_id(saved)
        else:
            status_bus.set_session_id("")


def test_explicit_tenant_id_wins_over_auth_context() -> None:
    auth_token = set_current_tenant_id("customer-a")
    try:
        assert ConnectionManager._effective_tenant_id("customer-b") == "customer-b"
    finally:
        reset_current_tenant_id(auth_token)


def test_auth_context_wins_over_session_prefix() -> None:
    auth_token = set_current_tenant_id("customer-a")
    status_bus.set_session_id("customer-b:session-xyz")
    try:
        assert ConnectionManager._effective_tenant_id("") == "customer-a"
    finally:
        reset_current_tenant_id(auth_token)
        status_bus.set_session_id("")


def test_auth_context_wins_over_default_fallback() -> None:
    auth_token = set_current_tenant_id("customer-a")
    try:
        assert ConnectionManager._effective_tenant_id("") == "customer-a"
    finally:
        reset_current_tenant_id(auth_token)


def test_session_prefix_used_when_auth_context_empty() -> None:
    status_bus.set_session_id("customer-x:abc-123")
    try:
        assert get_current_tenant_id() is None
        assert ConnectionManager._effective_tenant_id("") == "customer-x"
    finally:
        status_bus.set_session_id("")


def test_default_fallback_when_nothing_set() -> None:
    status_bus.set_session_id("")
    try:
        assert get_current_tenant_id() is None
        assert ConnectionManager._effective_tenant_id("") == "default"
    finally:
        status_bus.set_session_id("")


def test_session_id_without_colon_yields_default() -> None:
    status_bus.set_session_id("plain-session-id")
    try:
        assert ConnectionManager._effective_tenant_id("") == "default"
    finally:
        status_bus.set_session_id("")


def test_explicit_tenant_id_is_normalized_to_lower_stripped() -> None:
    assert ConnectionManager._effective_tenant_id("  Customer-A  ") == "customer-a"


def test_auth_tenant_id_is_normalized_to_lower_stripped() -> None:
    auth_token = set_current_tenant_id("  Customer-A  ")
    try:
        assert ConnectionManager._effective_tenant_id("") == "customer-a"
    finally:
        reset_current_tenant_id(auth_token)


def test_explicit_whitespace_only_falls_through_to_auth() -> None:
    auth_token = set_current_tenant_id("customer-a")
    try:
        assert ConnectionManager._effective_tenant_id("   ") == "customer-a"
    finally:
        reset_current_tenant_id(auth_token)


def test_auth_context_mixed_case_is_lowercased() -> None:
    auth_token = set_current_tenant_id("Customer-A")
    try:
        assert ConnectionManager._effective_tenant_id("") == "customer-a"
    finally:
        reset_current_tenant_id(auth_token)
