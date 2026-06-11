from __future__ import annotations

from core.redaction import SECRET_KEYS, is_sensitive_key, mask_dict, redact_text


def test_secret_keys_is_frozenset() -> None:
    assert isinstance(SECRET_KEYS, frozenset)


def test_secret_keys_contains_password_token_secret() -> None:
    for key in ("password", "token", "secret", "api_key", "apikey"):
        assert key in SECRET_KEYS, f"missing canonical secret key: {key}"


def test_secret_keys_contains_plan_baseline() -> None:
    for key in (
        "password", "token", "api_key", "secret", "apikey", "api_token",
        "authorization", "vault_key", "private_key", "access_key",
    ):
        assert key in SECRET_KEYS, f"missing PLAN.md baseline key: {key}"


def test_secret_keys_contains_legacy_carryover() -> None:
    for key in ("bearer", "auth", "credential", "passwd", "client_secret",
                "secret_key", "auth_token", "access_token", "private"):
        assert key in SECRET_KEYS, f"missing legacy carry-over key: {key}"


def test_is_sensitive_key_matches_known_keys() -> None:
    assert is_sensitive_key("password")
    assert is_sensitive_key("API_KEY")
    assert is_sensitive_key("Authorization")
    assert is_sensitive_key("private_key")
    assert is_sensitive_key("vault_key")
    assert is_sensitive_key("client_secret")


def test_is_sensitive_key_handles_dash_and_space_normalization() -> None:
    assert is_sensitive_key("api-key")
    assert is_sensitive_key("Api Key")
    assert is_sensitive_key("PRIVATE-KEY")


def test_is_sensitive_key_rejects_unrelated_keys() -> None:
    assert not is_sensitive_key("name")
    assert not is_sensitive_key("user_id")
    assert not is_sensitive_key("description")
    assert not is_sensitive_key("label")
    assert not is_sensitive_key("")


def test_is_sensitive_key_handles_non_string_keys() -> None:
    assert not is_sensitive_key(None)
    assert not is_sensitive_key(42)
    assert not is_sensitive_key(["password"])


def test_mask_dict_masks_top_level_sensitive_keys() -> None:
    result = mask_dict({"api_key": "sk-abc", "host": "example.com"})
    assert result == {"api_key": "***", "host": "example.com"}


def test_mask_dict_recurses_into_nested_dicts() -> None:
    result = mask_dict({
        "config": {"password": "hunter2", "host": "example.com"},
    })
    assert result == {
        "config": {"password": "***", "host": "example.com"},
    }


def test_mask_dict_recurses_into_lists() -> None:
    result = mask_dict([
        {"token": "abc"},
        {"safe": "value"},
    ])
    assert result == [{"token": "***"}, {"safe": "value"}]


def test_mask_dict_preserves_non_dict_primitives() -> None:
    assert mask_dict("hello") == "hello"
    assert mask_dict(42) == 42
    assert mask_dict(None) is None
    assert mask_dict(True) is True


def test_mask_dict_stops_at_max_depth() -> None:
    nested: dict = {}
    current = nested
    for i in range(10):
        current["api_key"] = "x"
        if i < 9:
            current["next"] = {}
            current = current["next"]
    result = mask_dict(nested)
    current = result
    masked_count = 0
    for _ in range(10):
        if current.get("api_key") == "***":
            masked_count += 1
        if "next" not in current:
            break
        current = current["next"]
    assert masked_count == 6
    assert current.get("api_key") == "x"


def test_mask_dict_does_not_mutate_input() -> None:
    original = {"api_key": "secret", "data": {"password": "hunter2"}}
    snapshot = {"api_key": "secret", "data": {"password": "hunter2"}}
    mask_dict(original)
    assert original == snapshot


def test_mask_dict_handles_empty_input() -> None:
    assert mask_dict({}) == {}
    assert mask_dict([]) == []


def test_redact_text_masks_json_style_assignment() -> None:
    assert redact_text('"password": "hunter2"') == '"password": "***"'


def test_redact_text_masks_key_equals_value() -> None:
    assert redact_text("password=hunter2") == "password=***"


def test_redact_text_masks_key_colon_value_no_quotes() -> None:
    assert redact_text("password: hunter2") == "password: ***"


def test_redact_text_is_case_insensitive() -> None:
    assert redact_text('"PASSWORD": "hunter2"') == '"PASSWORD": "***"'
    assert redact_text("Bearer=abc") == "Bearer=***"


def test_redact_text_respects_limit_parameter() -> None:
    text = "safe content " * 150 + '"password": "hunter2"'
    out = redact_text(text, limit=2000)
    assert '"password": "***"' in out
    assert len(out) <= 2000


def test_redact_text_preserves_safe_content() -> None:
    safe = "user logged in from 192.168.1.1 with id 42"
    assert redact_text(safe) == safe


def test_redact_text_handles_empty_input() -> None:
    assert redact_text("") == ""


def test_redact_text_masks_multiple_secrets_in_one_string() -> None:
    text = '"password": "hunter2" "api_key": "sk-abc" "name": "alice"'
    out = redact_text(text)
    assert '"password": "***"' in out
    assert '"api_key": "***"' in out
    assert '"name": "alice"' in out
