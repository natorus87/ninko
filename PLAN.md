# Plan: Ninko Agenten-Logik — Code-Review 2026-07-03

**Stand:** 2026-07-03
**Quelle:** Tiefes Review der Agenten-Logik (orchestrator, base_agent, middleware, pipeline_engine, safeguard, tool_permissions, scheduler, agent_pool, sub-agents). Findings verifiziert gegen den echten Code.

> **Fokus:** Agenten-Routing, Safeguard, Tool-Ausführung, Agent-Lifecycle, Pipeline. Nicht Frontend/Deployment.

---

## Executive Summary

| Bereich | Kritisch | Hoch | Mittel | Niedrig |
|---|---|---|---|---|
| Sicherheit (Safeguard-Bypass) | 1 | 5 | 1 | – |
| Robustheit / Lifecycle | 1 (behoben) | 3 | 3 | 3 |
| Korrektheit | – | – | 5 | 2 |
| Wartbarkeit / toter Code | – | 1 (behoben) | 1 | mehrere |

**Gesamtbild:** Funktional reiche, defensiv geschriebene Agenten-Logik. Drei strukturelle Probleme: (1) eine ausbrechbare Safeguard-Bypass-Kette rund um `confirmed`-Propagation und readonly-Inferenz, (2) Lifecycle-Inkonsistenzen zwischen Redis-State und Live-Objekten, (3) toter Code aus der Routing-Migration.

---

## ✅ Bereits behoben (2026-07-03)

- **C1** — `SchedulerAgent.start_loop` fängt jetzt auch unerwartete Exceptions (`scheduler_agent.py`). Loop stirbt nicht mehr permanent.
- **A1** — `execute_cli_command` lehnt Pfad-Argumente ab (`tool_permissions.py`). Basename-Bypass geschlossen.
- **A7** — Fast-Prefilter matcht Safe-Keywords nur am Satzanfang (`safeguard.py`). Kein Substring-False-Negative mehr.
- **D5** — Monitor überlebt `detail: None` (`monitor_agent.py`).
- **C2** — `delete_agent` räumt `ninko:agent_configs` auf (neue `AgentConfigStore.delete_config`) und deaktiviert referenzierende Scheduler-Tasks (`routes_agents.py`).
- **B1 (toter Code)** — `_plan_and_execute_pipeline`, `_route_tier2_module`, `_CORE_ALWAYS_MODULES` entfernt (`orchestrator.py`, −354 Zeilen). Doku angeglichen: `DOCS.md`, `backend/README.md`, Memory-Arch-Notiz. Routing ist jetzt dokumentiert Function-Calling-only.

### ✅ Stufe 2 (Safeguard-Bypass-Kette, 2026-07-04)

- **A3** — `call_module_agent` propagiert `confirmed=True` nur noch, wenn die delegierte Aufgabe von der bestätigten Nachricht gedeckt ist (`_confirmation_covers_task`, `core_tools.py`). Fremde destruktive Delegation im selben Turn erbt die Bestätigung nicht mehr. Verifiziert.
- **A6** — `_infer_readonly` (`tool_registry.py`) wendet die Präfix-Heuristik nicht mehr an, wenn ein Namens-Token ein Mutations-Verb ist (`_MUTATION_VERBS`, exaktes Token-Matching). `get_and_purge_logs`/`check_and_apply_update`/`read_secret_and_rotate` → nicht mehr readonly; `list_installed_packages`/`get_startup_config` bleiben readonly. 12/12 Fälle grün.
- **A4b** — Pipeline-Step erkennt jetzt das `__TOOL_SAFEGUARD__`-Sentinel (`pipeline_engine.py`): pausierter Sub-Agent-State wird bereinigt (`_release_paused_subagent`), Step als FAILED abgebrochen, kein Sentinel-Leak, keine 300s-Session-Blockade.
- **A5b** — Reserved-Name-Blocklist (`_RESERVED_AGENT_NAMES`: orchestrator/monitor/scheduler) in `DynamicAgentPool.register` UND API `create_agent`/`update_agent`. Verhindert Überschreiben von Built-in-Souls.

### ✅ Stufe P1 (Lifecycle/Robustheit, 2026-07-04)

- **C3** — LRU-Eviction entlädt jetzt nur die Live-Instanz; `_meta`/Such-Index bleiben vollständiger Katalog (`agent_pool.py`). Neuer `_rehydrate()` re-instanziiert evictete Agenten bei Zugriff; `find_best_match`/`get_agent_by_id`/`get_by_id` gehen über `_meta` + Rehydrierung. Scheduler-Tasks mit evicted `agent_id` scheitern nicht mehr. Logik verifiziert (Eviction behält Meta, Rehydrierung, echtes LRU).
- **H5** — `_migrate_legacy_key()` migriert `ninko:agents` einmalig beim Start nach `ninko:agents:default` (id-Match kollisionsfrei) und löscht den Legacy-Key → keine unlöschbaren Ghost-Agenten mehr.
- **C5** — Scheduler: `_run_task_guarded()` mit Doppellauf-Schutz (`_running_task_ids`) und hartem `asyncio.wait_for`-Timeout (`TASK_EXECUTION_TIMEOUT_SECONDS=600`); genutzt von `_check_and_run` UND `run_task_now`. Bei Timeout wird `next_run` fortgeschrieben (kein Re-Fire-Storm).
- **C4 (vollständig)** — Alle gemeldeten Lost-Update-RMW abgesichert (prozessweite Locks; wirken in der Single-Process-Deployment):
  - `AgentConfigStore`: atomar über `_config_write_lock` (`_mutate`) — Safeguard-Overrides bleiben erhalten (deckt M8).
  - Agenten-Liste: gemeinsamer `get_agents_redis_lock()` von Pool (`register`) UND API (`create`/`update`/`delete`) auf `ninko:agents:<tenant>` (deckt H4).
  - Workflow-Liste: `_workflows_write_lock` in `create_dag_workflow` + `create_linear_workflow`.
  - Run-Listen: geteilter `get_run_update_lock(tenant, wf)` — genutzt von `execute_workflow` (core_tools) UND der WorkflowEngine (`_ensure_run_entry` war zuvor sogar ganz ohne Lock, jetzt gesichert; `_update_run` nutzt denselben Accessor).
  - Script-Invocation-Log: `_invocations_write_lock` (`script_tools.py`).
  - **Rest (dokumentiert):** Multi-Replica-Betrieb braucht Redis-Level-Atomarität (WATCH/MULTI oder Lua) statt Prozess-Locks — Prozess-Locks wirken nur single-process.

---

### ✅ P0-Design-Entscheidungen (2026-07-04)

- **A2** — Subcommand-/Argument-Whitelisting für write-fähige, read-only gemeinte Allowlist-Kommandos (`tool_permissions.py::_assert_readonly_cli_usage`): `systemctl` nur lesende Subcommands, `journalctl` ohne `--vacuum/--rotate/--flush`, `ip`/`route` ohne `set/add/del/change/…`, `ethtool` ohne Set-Flags, `dpkg` nur Query-Flags, `rpm` nur `-q`. Greift in allen Modi außer `DANGER_FULL_ACCESS`. 16/16 Fälle verifiziert.
- **A4** — Step-weiser Pipeline-Resume (`pipeline_engine.py`): `execute()` hat `confirmed_indices`; das Pre-Flight-Gate pausiert vor dem ersten NOCH NICHT bestätigten `requires_confirmation`-Step; `resume()` bestätigt nur den wartenden Step (akkumuliert im Checkpoint) und pausiert bei weiteren erneut. `routes_chat.py` behandelt den erneuten `AWAITING_CONFIRMATION`-Zustand. Eine Bestätigung autorisiert nie die ganze Pipeline. `resume(auto_confirm=True)` bleibt rückwärtskompatibel (Tests). Neuer Regressionstest `test_stepwise_resume_confirms_one_step_at_a_time`.
- **A5a** — `execute_cli_command` nicht mehr pauschal an alle dynamischen Agenten: nur wenn `module_names` ein Infra-Modul (`_CLI_CAPABLE_MODULES`: linux_server/docker/kubernetes/proxmox) enthält; sonst delegieren sie über `call_module_agent`. Zusätzlich System-Prompt-Längen-Cap (`_MAX_SYSTEM_PROMPT_CHARS=20000`) bei `register`.
- **A5c** — `get_agent_by_id(allow_cross_tenant=False)` als Default: der tenant-übergreifende `endswith`-Fallback greift nur noch für System-Kontexte (Scheduler übergibt explizit `True`). Chat/force_module-Pfade sind damit tenant-isoliert.
- **A8** — bereits entschärft (kein Fix nötig): äußerer `except`/`except CancelledError` (`routes_chat.py`) ruft `_mark_current_tx_failed` → `mark_failed` + `clear_pending_for_session`; mit task-gescoptem A3 ist die Restgefahr durch die 24h-TTL begrenzt.

---

## P4 — Aufräumen — ✅ erledigt (2026-07-04)

- **Entfernt (isoliert toter Code):** `_build_execution_groups` + `_build_execution_groups_legacy` (`core_tools.py`, Logik liegt in `core.pipeline_engine`); die Orchestrator-Stub-Methoden `build_task_sketch`/`get_last_task_sketch`/`resolve_evidence_semantics`/`get_last_evidence_trace`/`_should_show_user_evidence_trace`.
- **`_authorized_sg_tool_calls`** wird jetzt in `cleanup_paused_agents` (`safeguard.py`) für abgelaufene Sessions mit aufgeräumt → kein langsames Speicherwachstum mehr.
- **Bewusst behalten (wie KeywordRouter-Shim), Doku korrigiert:** `find_best_match` + Token-Index — kohäsives Keyword-Matching-Subsystem, das die Hot-Paths `_instantiate`/`_close_live_agent` berührt; im route()-Pfad ungenutzt (Function-Calling-only), aber risikoarm zu behalten falls Keyword-Routing reaktiviert wird. `KeywordRouter` (dokumentierter Shim + Tests) bleibt ebenfalls.
- **`_close_live_agent` `aclose`-Guard:** bewusst behalten — harmloses, konsistentes Defensiv-Muster (auch `LLMProviderMiddleware` nutzt den `hasattr`-Guard); greift, falls `BaseAgent` künftig `aclose` erhält.
- **Inkonsistente Fehler-Rückgabetypen** (String vs. dict vs. JSON-String): als bekannte Schuld dokumentiert — eine projektweite Vereinheitlichung ist ein eigenständiges Refactoring außerhalb dieses Review-Scopes.

---


## P1 — Robustheit & Lifecycle — ✅ vollständig erledigt (2026-07-04)

- **C3, C4, C5, H5** — siehe „✅ Stufe P1" oben.
- **M9** — `sync_agent` Disable-Pfad läuft jetzt unter `self._register_lock` (`agent_pool.py`). Kein „live trotz disabled" mehr.
- **M7** — `_active_subagents` ist jetzt LRU-begrenzt (`OrderedDict`, `_MAX_ACTIVE_SUBAGENTS=200`, Eviction in `_get_or_create_subagent`); `_completed_steps`/`_failed_steps` werden zu Beginn jedes `invoke()` zurückgesetzt (`data_analysis_subagent.py`).
- **M6** — `recursion_limit` von 10000 auf 60 gesenkt (`data_analysis_subagent.py`).
- **M8** — bereits durch C4 erledigt (`AgentConfigStore._mutate` unter `_config_write_lock`).
- **N2** — `load_from_redis` nutzt `scan_iter` statt blockierendem `KEYS` (`agent_pool.py`).
- **N3** — `self._task = asyncio.current_task()` in `start_loop` von Scheduler UND Monitor gesetzt → `stop()`-Cancel wirkt jetzt.

---

## P2 — Korrektheit — ✅ erledigt (2026-07-04)

- **D1** — `run_pipeline` ist jetzt Fail-fast: ein ungültiger Step lehnt die ganze Pipeline mit Fehlermeldung ab, statt still zu filtern (was `depends_on`-Indizes verschob). (`core_tools.py`)
- **D2** — `asyncio.CancelledError` aus `_CORE_TOOL_EXCEPTIONS` entfernt; `wait()` re-raist Cancellation statt sie in einen Fehlerstring zu wandeln → saubere Task-Terminierung bei Disconnect/Shutdown. (`core_tools.py`)
- **D3** — `generate_pdf_report` gehärtet: `output_path` auf festes Verzeichnis (`tmp/ninko-reports`) normalisiert + `.pdf`-Zwang (kein Path Traversal); Deny-All-`url_fetcher` (kein LFI/SSRF via `file:///`); Rendering in `asyncio.to_thread` (kein Event-Loop-Block); Titel via `html.escape` (HTML) bzw. quote-/newline-frei (CSS). (`core_tools.py`)
- **D4/M1** — Scheduler setzt `exec_status` explizit pro Branch; neuer `_response_indicates_error()` erkennt Fehler-Antwortstrings von Agent/Orchestrator (deckt auch N5 downstream). Keine branch-lokale Variable in gemeinsamer Expression mehr. (`scheduler_agent.py`)
- **D6** — Per-Nachricht-Cap vor der Summary von 400 → 2000 Zeichen erhöht (`context_manager.py`), damit IPs/IDs/Configs erhalten bleiben (überlange Nachrichten stutzt `trim_large_messages` bereits vorher). Tokenizer-Genauigkeit (fester `cl100k_base`) bewusst nicht verändert — ein globaler Sicherheitsfaktor würde jede Anfrage betreffen und über-eager kompaktieren (Regressionsrisiko); als Beobachtung notiert.
- **Weitere:**
  - `run_parallel_pipeline` — `depends_on`-Indizes werden jetzt explizit mitgezählt statt rückwärts gerechnet; leere (Zwischen-)Gruppen werden übersprungen. (`core_tools.py`)
  - `create_dag_workflow` — doppelte explizite Node-IDs werden abgelehnt; pro Node eine eigene `full_id` (keine Kollision bei leeren/doppelten IDs). (`core_tools.py`)
  - `record_alert`/`should_notify` — reservierter Cooldown-Slot wird freigegeben (`release_notify_cooldown`), wenn keine ticketbasierte Notification erfolgt → kein fälschlich unterdrückter Folge-Alert. (`alert_tools.py`, `alert_state.py`)
  - `_extract_step_agent_hint` — Substring-Heuristik entfernt; nur explizites `[module:...]`-Prefix routet, sonst Orchestrator. (`core_tools.py`)
  - **N5 (Rest):** `DataAnalysisSubagent` gibt Fehlertext weiterhin als Summary zurück; downstream jetzt durch `_response_indicates_error` im Scheduler abgefangen. Ein sauberes Fehler-Flag im Rückgabewert wäre der tiefere Fix (offen, geringe Priorität).

---

## P3 — Performance — ✅ erledigt (2026-07-04)

- **B3** — Semantic-Routing-Cache ist jetzt größenbegrenzt: ein ZSET-Index (`ninko:toolcall:sem_index`, Cap 500, Score = Zeitstempel) ersetzt den `scan_iter` über alle `sem:*`-Keys. `_route_cache_semantic_get` liest Kandidaten via `zrevrange` (bounded), räumt verwaiste Index-Einträge (abgelaufene Payloads) auf; `_route_cache_semantic_set` trimmt die ältesten Einträge samt Payload. Lookup-Kosten sind damit gedeckelt statt linear im gesamten Keyspace. (`orchestrator.py`)
- **speak** — Kein Base64 mehr im Tool-Return: WAV wird via `core.tts.store_audio()` in einen kurzlebigen Ordner (`tmp/ninko-tts-audio`, 1h-Cleanup) geschrieben; der Tool-Return enthält nur noch einen kompakten Markdown-Link auf den neuen Endpoint `GET /api/tts/audio/{filename}` (auth-frei wie das Image-Serving, mit Path-Traversal-Guard). Kein LLM-Kontext-Bloat mehr. (`core_tools.py`, `core/tts/__init__.py`, `api/routes_tts.py`)

---

## Status

**Alle Prioritäten des Reviews abgeschlossen:** Stufe 1, Stufe 2 (Safeguard-Bypass-Kette), P0-Design-Entscheidungen (A2/A4/A5a/A5c/A8), P1 (Lifecycle/Robustheit), P2 (Korrektheit), P3 (Performance), P4 (Aufräumen).

**Verbleibende, bewusst dokumentierte Schuld (eigenständige Refactorings, kein akutes Risiko):**
- Multi-Replica-Atomarität für Redis-RMW (aktuell Prozess-Locks, wirken single-process).
- Projektweite Vereinheitlichung der Tool-Fehler-Rückgabetypen.
- Tokenizer-Genauigkeit der Kontext-Kompaktierung (fester `cl100k_base`).
- N5: `DataAnalysisSubagent` gibt Fehlertext als Summary zurück (downstream im Scheduler erkannt).
- Optional: `find_best_match`/`KeywordRouter` samt Index vollständig entfernen, falls Keyword-Routing dauerhaft aufgegeben wird.
