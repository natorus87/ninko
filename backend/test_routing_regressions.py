from __future__ import annotations

from types import SimpleNamespace

from agents.orchestrator import OrchestratorAgent
from core.module_registry import ModuleRegistry
from core.router import KeywordRouter


def _make_orchestrator(routing_map: dict[str, str]) -> OrchestratorAgent:
    agent = object.__new__(OrchestratorAgent)
    agent._routing_map = routing_map
    agent._router = KeywordRouter(routing_map)
    agent._last_routing_confidence = None
    return agent


def test_keyword_scoring_does_not_use_generic_substring_fallback() -> None:
    agent = _make_orchestrator(
        {
            "entwicklungsumgebung": "proxmox",
            "monitoring": "zabbix",
        }
    )

    assert agent._get_module_scores("in mehreren Entwicklungsumgebungen") == {}
    assert agent._get_module_scores("supermonitoringtool") == {}


def test_keyword_scoring_uses_conservative_token_normalization() -> None:
    agent = _make_orchestrator(
        {
            "container": "docker",
            "ausführen": "codelab",
        }
    )

    assert agent._get_module_scores("Logs in Containern anzeigen") == {"docker": 1}
    assert agent._get_module_scores("Containers neu starten") == {"docker": 1}
    assert agent._get_module_scores("Skript auszuführen") == {"codelab": 1}
    assert agent._get_module_scores("Ausführung prüfen") == {"codelab": 1}


def test_module_registry_adds_module_name_aliases() -> None:
    registry = ModuleRegistry()
    registry._modules = {
        "image_gen": SimpleNamespace(
            manifest=SimpleNamespace(routing_keywords=["bild", "grafik"])
        )
    }

    routing_map = registry.get_routing_map()

    assert routing_map["image_gen"] == "image_gen"
    assert routing_map["image gen"] == "image_gen"
    assert routing_map["imagegen"] == "image_gen"


def test_module_name_aliases_receive_name_boost() -> None:
    agent = _make_orchestrator(
        {
            "image gen": "image_gen",
            "bild": "image_gen",
        }
    )

    assert agent._get_module_scores("nutze image gen") == {"image_gen": 5}
    assert agent._get_module_scores("erstelle ein bild") == {"image_gen": 1}


def test_core_keywords_do_not_bypass_module_matches() -> None:
    agent = _make_orchestrator(
        {
            "proxmox": "proxmox",
            "docker": "docker",
            "container": "docker",
        }
    )

    assert agent._detect_module_fast("Ping den Proxmox-Server") == ("proxmox", False)
    assert agent._detect_module_fast("Zeig die Docker-Container-Uptime") == ("docker", False)


def test_core_keywords_without_module_matches_stay_in_core_path() -> None:
    agent = _make_orchestrator({"proxmox": "proxmox"})

    assert agent._detect_module_fast("Ping 10.0.0.1") == (None, False)


def test_plain_und_between_modules_does_not_trigger_compound() -> None:
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "kubernetes": "kubernetes",
        }
    )

    assert agent._detect_module_fast("Vergleiche Docker und Kubernetes") == (None, False)
    assert agent._detect_module_fast("Erkläre Docker und Kubernetes") == (None, False)


def test_explicit_sequence_between_modules_triggers_compound() -> None:
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "kubernetes": "kubernetes",
        }
    )

    assert agent._detect_module_fast("Prüfe Docker und dann Kubernetes") == (None, True)


def test_low_confidence_multi_module_hits_use_react_path() -> None:
    agent = _make_orchestrator(
        {
            "image": "image_gen",
            "volume": "docker",
        }
    )

    assert agent._detect_module_fast("image volume") == (None, False)


def test_clear_score_margin_keeps_strongest_module_fast_path() -> None:
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "image": "image_gen",
        }
    )

    assert agent._detect_module_fast("Docker image") == ("docker", False)


# ── Tippfehler (System-Grenze: kein Fuzzy-Matching) ───────────────────────────


def test_single_char_typo_in_keyword_is_not_matched() -> None:
    """System-Grenze: kein Fuzzy-Matching — ein falscher Buchstabe → kein Treffer."""
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "proxmox": "proxmox",
            "container": "docker",
        }
    )

    assert agent._get_module_scores("dokcer starten") == {}
    assert agent._get_module_scores("proxmoc server prüfen") == {}
    assert agent._get_module_scores("conatiner auflisten") == {}


def test_suffix_normalization_edge_case_kubernets() -> None:
    """Grenzfall: 'kubernets' (fehlendes 'e') landet via Suffix-Strip auf demselben Stem
    wie 'kubernetes' → normalisierter Match. 'kuberneste' (vertauschtes 'e') matcht nicht."""
    agent = _make_orchestrator({"kubernetes": "kubernetes"})

    # "kubernets" → stem "kubernet" == stem "kubernetes" → Match (Normalisierungs-Grenzfall)
    assert agent._get_module_scores("kubernets cluster") == {"kubernetes": 5}
    # "kuberneste" → stem "kubernest" ≠ "kubernet" → kein Match
    assert agent._get_module_scores("kuberneste pods") == {}


# ── Synonyme (System-Grenze: keine Synonym-Expansion) ────────────────────────


def test_semantic_synonym_without_keyword_entry_is_not_matched() -> None:
    """Nur explizit gelistete Keywords treffen — keine implizite Synonym-Expansion."""
    agent = _make_orchestrator(
        {
            "bild": "image_gen",
            "container": "docker",
            "monitoring": "zabbix",
        }
    )

    assert agent._get_module_scores("Erstelle ein Abbild") == {}
    assert agent._get_module_scores("Behälter auflisten") == {}
    assert agent._get_module_scores("Überwachung einrichten") == {}


def test_english_synonym_for_german_keyword_not_matched() -> None:
    """Englische Synonyme für deutsche Keywords werden nicht erkannt."""
    agent = _make_orchestrator({"bild": "image_gen"})

    assert agent._get_module_scores("create a picture") == {}


# ── Duplicate-Keyword-Konflikte ───────────────────────────────────────────────


def test_conflict_keywords_with_equal_scores_go_to_react() -> None:
    """Bekannte Conflict-Keywords (gleiche Scores) → ReAct — kein Modul gewinnt."""
    agent = _make_orchestrator(
        {
            "monitoring": "zabbix",
            "alert": "zabbix",
            "checks": "checkmk",
            "service": "checkmk",
        }
    )

    assert agent._detect_module_fast("monitoring service") == (None, False)


def test_conflict_keyword_with_clear_score_advantage_picks_stronger_module() -> None:
    """Bei Keyword-Konflikt gewinnt das Modul mit klar höherem Score."""
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "container": "docker",
            "image": "docker",
            "bild": "image_gen",
        }
    )

    assert agent._detect_module_fast("docker container image") == ("docker", False)


def test_itsm_ticket_keyword_shared_between_modules_without_margin_goes_to_react() -> None:
    """'ticket' ist ein bekanntes Conflict-Keyword zwischen ITSM-Modulen (Score 1:1 → ReAct)."""
    agent = _make_orchestrator(
        {
            "ticket": "jira",
            "issue": "redmine",
        }
    )

    assert agent._detect_module_fast("ticket issue") == (None, False)


def test_monitoring_keyword_conflict_checkmk_vs_zabbix_react_on_tie() -> None:
    """'monitoring' und 'graph' sind bekannte Konflikte zwischen Checkmk und Zabbix."""
    agent = _make_orchestrator(
        {
            "graph": "dataviz",
            "monitoring": "zabbix",
        }
    )

    assert agent._detect_module_fast("monitoring graph") == (None, False)


# ── History-Fallback ──────────────────────────────────────────────────────────


def test_history_fallback_single_module_delegates_correctly() -> None:
    """Single-Modul in History → bei leerem Current-Score wird zum History-Modul delegiert."""
    agent = _make_orchestrator({"docker": "docker"})

    history = [
        {"role": "user", "content": "Zeig meine Docker-Container"},
        {"role": "assistant", "content": "Hier sind deine Docker-Container."},
    ]

    assert agent._detect_module_fast("und jetzt?", chat_history=history) == ("docker", False)


def test_history_fallback_multi_module_ambiguity_goes_to_react() -> None:
    """Mehrere Module in History → kein eindeutiger Kontext → ReAct."""
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "proxmox": "proxmox",
        }
    )
    history = [
        {"role": "user", "content": "Starte den Docker-Container auf Proxmox"},
        {"role": "assistant", "content": "Container gestartet."},
    ]

    assert agent._detect_module_fast("nochmal", chat_history=history) == (None, False)


def test_history_fallback_not_used_when_current_message_has_scores() -> None:
    """History-Fallback greift nicht, wenn Current-Message bereits Modul-Scores hat."""
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "proxmox": "proxmox",
        }
    )
    history = [{"role": "user", "content": "Zeig Proxmox-VMs"}]

    assert agent._detect_module_fast("Docker-Container auflisten", chat_history=history) == (
        "docker",
        False,
    )


def test_history_fallback_uses_only_last_three_turns() -> None:
    """History-Fallback nutzt nur die letzten 3 Nachrichten (ältere Turns ignoriert)."""
    agent = _make_orchestrator(
        {
            "proxmox": "proxmox",
            "docker": "docker",
        }
    )
    history = [
        {"role": "user", "content": "Proxmox VMs anzeigen"},
        {"role": "assistant", "content": "Hier sind deine VMs."},
        {"role": "user", "content": "Proxmox Snapshots"},
        {"role": "assistant", "content": "Snapshots: ..."},
        {"role": "user", "content": "Docker Container starten"},
    ]
    # Letzte 3: "Proxmox Snapshots" + "Snapshots: ..." + "Docker Container starten"
    # → proxmox UND docker erkannt → Mehrdeutigkeit → ReAct
    assert agent._detect_module_fast("und jetzt stoppen?", chat_history=history) == (None, False)


# ── Confidence-Score-Semantik ─────────────────────────────────────────────────


def test_confidence_is_1_for_unambiguous_single_module() -> None:
    """Single eindeutiger Keyword-Treffer → Confidence 1.0."""
    agent = _make_orchestrator({"docker": "docker"})

    agent._detect_module_fast("Docker-Container auflisten")

    assert agent._router.last_confidence == 1.0


def test_confidence_is_0_5_for_history_fallback() -> None:
    """History-Fallback → Confidence 0.5 (schwache Ableitung aus Kontext)."""
    agent = _make_orchestrator({"docker": "docker"})
    history = [{"role": "user", "content": "Zeig Docker-Container"}]

    agent._detect_module_fast("und jetzt?", chat_history=history)

    assert agent._router.last_confidence == 0.5


def test_confidence_is_none_for_react_path() -> None:
    """Kein Keyword-Treffer → ReAct-Loop → Confidence None."""
    agent = _make_orchestrator({"docker": "docker"})

    agent._detect_module_fast("Was ist das Wetter heute?")

    assert agent._router.last_confidence is None


def test_confidence_is_none_for_ambiguous_multi_module() -> None:
    """Gleicher Score zwischen zwei Modulen → ReAct → Confidence None."""
    agent = _make_orchestrator({"image": "image_gen", "volume": "docker"})

    agent._detect_module_fast("image volume")

    assert agent._router.last_confidence is None


def test_confidence_score_for_confident_multi_module_winner() -> None:
    """Klar führendes Modul (top/(top+second)) → Confidence zwischen 0 und 1."""
    agent = _make_orchestrator(
        {
            "docker": "docker",
            "container": "docker",
            "image": "image_gen",
        }
    )

    agent._detect_module_fast("docker container image")

    # docker-Score = 5+1=6 (docker=5, container=1), image_gen=1 → confidence = 6/(6+1) ≈ 0.86
    assert agent._router.last_confidence is not None
    assert 0.7 < agent._router.last_confidence <= 1.0


def test_confidence_is_none_for_empty_history_content() -> None:
    """History ohne 'content'-Feld → kein Fallback → Confidence None."""
    agent = _make_orchestrator({"docker": "docker"})
    history = [{"role": "user"}, {"role": "assistant"}]

    agent._detect_module_fast("und jetzt?", chat_history=history)

    assert agent._router.last_confidence is None
