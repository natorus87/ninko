"""Tests für core/net_guard.py – SSRF-Schutz benutzerkonfigurierter Provider-URLs."""

import pytest

from core.net_guard import BlockedOutboundURLError, assert_safe_outbound_url


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",  # AWS/GCP/Azure Metadata
        "http://169.254.169.254",
        "https://169.254.1.1/v1",  # sonstiges Link-Local
    ],
)
def test_blocks_link_local_and_metadata(url):
    with pytest.raises(BlockedOutboundURLError):
        assert_safe_outbound_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "ftp://example.com/x",
        "gopher://127.0.0.1:6379/",
    ],
)
def test_blocks_non_http_schemes(url):
    with pytest.raises(BlockedOutboundURLError):
        assert_safe_outbound_url(url)


def test_missing_host_rejected():
    with pytest.raises(BlockedOutboundURLError):
        assert_safe_outbound_url("http://")


@pytest.mark.parametrize(
    "url",
    [
        "https://api.openai.com/v1",
        "http://192.168.1.100:1234/v1",  # self-hosted LM Studio – erlaubt (nur Warnung)
        "http://10.0.0.5:11434",  # self-hosted Ollama – erlaubt
        "http://127.0.0.1:1234/v1",  # lokaler Endpunkt – erlaubt
    ],
)
def test_allows_public_and_self_hosted(url):
    # Darf nicht werfen (private/loopback erlaubt für self-hosted, öffentlich sowieso)
    assert_safe_outbound_url(url)


def test_empty_url_is_noop():
    assert_safe_outbound_url("")
    assert_safe_outbound_url("   ")
