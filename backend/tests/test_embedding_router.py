"""Tests für EmbeddingRouter (R11) – nur TF-IDF-Fallback, kein Embedding-Backend nötig."""
from __future__ import annotations

import pytest

from core.embedding_router import EmbeddingRouter, _bow, _cosine_dict, _cosine_vec


# ── Hilfsfunktionen ───────────────────────────────────────────────────────────


def _make_router(descriptions: dict[str, str]) -> EmbeddingRouter:
    router = EmbeddingRouter()
    router._embed_unavailable = True  # TF-IDF-Modus erzwingen
    router.update_module_descriptions(descriptions)
    return router


# ── BOW / Kosinus-Tests ───────────────────────────────────────────────────────


def test_bow_normalizes_to_max_count() -> None:
    result = _bow("docker docker container")
    assert result["docker"] == pytest.approx(1.0)
    assert result["container"] == pytest.approx(0.5)


def test_bow_empty_text_returns_empty() -> None:
    assert _bow("") == {}
    assert _bow("   ") == {}


def test_cosine_dict_identical_vectors_is_1() -> None:
    vec = {"docker": 1.0, "container": 0.5}
    assert _cosine_dict(vec, vec) == pytest.approx(1.0)


def test_cosine_dict_orthogonal_vectors_is_0() -> None:
    a = {"docker": 1.0}
    b = {"kubernetes": 1.0}
    assert _cosine_dict(a, b) == pytest.approx(0.0)


def test_cosine_vec_identical_is_1() -> None:
    vec = [1.0, 0.5, 0.25]
    assert _cosine_vec(vec, vec) == pytest.approx(1.0)


def test_cosine_vec_orthogonal_is_0() -> None:
    a = [1.0, 0.0]
    b = [0.0, 1.0]
    assert _cosine_vec(a, b) == pytest.approx(0.0)


# ── TF-IDF-Fallback-Ranking ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_tfidf_ranks_docker_query_for_docker_module() -> None:
    router = _make_router(
        {
            "docker": "docker container image pull push build run stop",
            "proxmox": "proxmox vm virtual machine cluster node snapshot",
        }
    )
    result = await router.arank("docker container starten", ["docker", "proxmox"])
    assert result is not None
    module, conf = result
    assert module == "docker"
    assert 0.5 < conf <= 0.80


@pytest.mark.asyncio
async def test_tfidf_ranks_vm_query_for_proxmox_module() -> None:
    router = _make_router(
        {
            "docker": "docker container image pull push build run",
            "proxmox": "proxmox vm virtual machine cluster node snapshot",
        }
    )
    result = await router.arank("neue VM auf Proxmox erstellen", ["docker", "proxmox"])
    assert result is not None
    module, conf = result
    assert module == "proxmox"


@pytest.mark.asyncio
async def test_tfidf_returns_none_for_empty_query() -> None:
    router = _make_router({"docker": "docker container"})
    result = await router.arank("   ", ["docker"])
    assert result is None


@pytest.mark.asyncio
async def test_tfidf_returns_none_for_single_candidate() -> None:
    router = _make_router({"docker": "docker container"})
    result = await router.arank("docker starten", ["docker"])
    assert result is None


@pytest.mark.asyncio
async def test_tfidf_returns_none_when_no_overlap_with_any_module() -> None:
    router = _make_router(
        {
            "docker": "docker container image",
            "proxmox": "proxmox vm cluster",
        }
    )
    result = await router.arank("xyz abc qrs", ["docker", "proxmox"])
    assert result is None


@pytest.mark.asyncio
async def test_tfidf_confidence_is_bounded_by_max() -> None:
    from core.embedding_router import _TFIDF_MAX_CONFIDENCE

    router = _make_router(
        {
            "docker": "docker",
            "proxmox": "proxmox",
        }
    )
    result = await router.arank("docker", ["docker", "proxmox"])
    assert result is not None
    _, conf = result
    assert conf <= _TFIDF_MAX_CONFIDENCE


@pytest.mark.asyncio
async def test_tfidf_winner_module_is_consistent_across_calls() -> None:
    router = _make_router(
        {
            "docker": "docker container image run build",
            "proxmox": "proxmox vm node cluster snapshot",
        }
    )
    for _ in range(3):
        result = await router.arank("container image bauen", ["docker", "proxmox"])
        assert result is not None
        assert result[0] == "docker"


# ── update_module_descriptions ────────────────────────────────────────────────


def test_update_clears_stale_vecs() -> None:
    router = EmbeddingRouter()
    router._module_vecs["docker"] = [0.1, 0.2]
    router.update_module_descriptions({"docker": "docker container"})
    assert router._module_vecs == {}


def test_update_builds_bow_for_all_modules() -> None:
    router = EmbeddingRouter()
    router.update_module_descriptions(
        {
            "docker": "docker container image",
            "proxmox": "proxmox vm cluster",
        }
    )
    assert "docker" in router._module_bow
    assert "proxmox" in router._module_bow
    assert "docker" in router._module_bow["docker"]
    assert "proxmox" in router._module_bow["proxmox"]


# ── Embed-Unavailable-Pfad ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_falls_back_to_tfidf_when_embed_unavailable() -> None:
    router = _make_router(
        {
            "docker": "docker container image",
            "proxmox": "proxmox vm cluster",
        }
    )
    assert router._embed_unavailable is True
    result = await router.arank("docker image bauen", ["docker", "proxmox"])
    assert result is not None
    assert result[0] == "docker"
