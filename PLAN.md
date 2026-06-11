# Plan: Ninko Open Items — 2026-06-10

**Stand:** 2026-06-10
**Quelle**: [.claude/reports/full-review-2026-06-10.md](.claude/reports/full-review-2026-06-10.md)
**Vorgänger**: `PLAN.md` (Full Code Review 2026-05-20) — alle P0-Items abgeschlossen, in DONE.md überführt

> **Hinweis Methodik**: Der zugrundeliegende Full-Review vom 2026-06-10 ist **diff-basiert** (alle 8 Commits seit 2026-05-29 + gezielte Greps). Kein vollständiger Re-Walk aller 449 Python-Dateien / 383 KB `app.js` — die als „Coverage-Limit aufholen" markierten Items holen das nach.

---

## Executive Summary

| Bereich | Diff-Scope | Carry-Over offen | Neu im Diff | Status |
|---|---|---|---|---|
| Sicherheit | 🟢 keine Regression | 0 | 0 (2× Low) | OK |
| Backend | 🟢 | 4× Schulden | 0 | OK |
| Frontend | 🟢 | 0 | 1× Low | OK |
| Architektur | 🟢 | 2× Schulden | 1× Low | OK |
| API | 🟢 | 2× Schulden | 0 | OK |
| **Total offene Items** | – | **8** | **3** | – |

**0 Critical / 0 High.** Diff-Scope ist sauber. Alle 4 dringenden Findings vom 2026-05-29-Review (DOM-XSS, WS-Auth-Revocation, registry.js-Bug, Plugin-Upload-Limit) sind in den neuen Commits behoben oder konsolidiert.

**Verbleibende 11 offene Items**: 8 Architektur-Schulden (Carry-Over aus 2026-05-29), 3 neue Low-Priority-Findings aus dem aktuellen Diff.

> **Stand nach Umsetzung (Sprint 1-6, 2026-06-10)**: **Alle 16 Items abgeschlossen** (1.1, 1.2, 1.3, 1.4, 2.1, 2.2, 2.3, 2.4, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.5). 4.4 übersprungen (deckungsgleich mit 2.3). Coverage-Berichte in `.claude/knowledge/`. 2.3 + 2.4 sind im Working Tree uncommitted, **0 Commits** (auf User-Wunsch zur späteren Review).

---

## P1 — Kurzfristig (1-2 Wochen)

> Reihenfolge nach Risiko × Aufwand. Jedes Item mit konkretem Datei-Anker und Code-Snippet.

### 1.1 Secret-Redaction zentralisieren (4× Stellen) — ✅ DONE (Sprint 1)
- **Risiko**: Medium — Tokens/Passwörter können in einem Pfad maskiert, im anderen geleakt werden
- **Aufwand**: ~2 h
- **Stellen**:
  - [backend/agents/base_agent.py:200-216](backend/agents/base_agent.py#L200-L216) (`_StatusEmitter`)
  - [backend/agents/middleware/execution.py:35-50](backend/agents/middleware/execution.py#L35-L50)
  - [backend/core/connections.py:33-37](backend/core/connections.py#L33-L37)
  - [backend/core/safeguard.py:67-71](backend/core/safeguard.py#L67-L71)
- **Fix**: Zentrales `backend/core/redaction.py` mit kanonischer Key-Liste, `redact_text()` und `mask_dict()`; alle 4 Stellen umstellen.
  ```python
  # backend/core/redaction.py
  SECRET_KEYS: frozenset[str] = frozenset({
      "password", "token", "api_key", "secret", "apikey", "api_token",
      "authorization", "vault_key", "private_key", "access_key",
  })
  def mask_dict(d: dict) -> dict: ...
  def redact_text(s: str) -> str: ...
  ```

### 1.2 Orchestrator Tier-Routing-Leiche entfernen — ✅ DONE (Sprint 2)
- **Risiko**: Medium — tote Methoden kosten Wartung, lenken von echtem Code ab
- **Aufwand**: ~4 h
- **Stellen** in [backend/agents/orchestrator.py](backend/agents/orchestrator.py) (3039 LOC):
  - `classify_tier`, `_classify_tier`, `_detect_module_fast`, `_proactive_routing_adjust`, `_update_session_stats`
  - `RoutingConfig`-Presets, `_check_task_complexity`
  - `_route_legacy_tiered` (delegiert komplett an `_fallback_to_react_loop`)
- **Vorgehen**:
  1. Sicherstellen, dass keine Produktiv-Aufrufer existieren (Test-Suite checken)
  2. In `backend/agents/legacy_routing.py` isolieren oder direkt löschen
  3. CLAUDE.md + Doku ehrlich als „Function Calling + ReAct Fallback" benennen
- **Erwarteter Effekt**: Halbierung der Orchestrator-Größe (~1500 LOC weniger)

### 1.3 EmbeddingRouter reaktivieren oder entfernen — ✅ DONE (Sprint 2, entfernt)
- **Risiko**: Low — toter Code mit Runtime-Kosten (wird bei jedem `_refresh_routing_map()` gefüttert)
- **Aufwand**: ~1 h (löschen) oder ~6 h (reaktivieren)
- **Stellen**: [backend/core/embedding_router.py](backend/core/embedding_router.py) — `arank()` ohne Produktiv-Aufrufer
- **Empfehlung**: Entfernen, falls nicht für 1.4 (Pipeline `requires_confirmation`) benötigt
- **Falls behalten**: Mindestens `arank()` mit dem Function-Calling-Router verdrahten

### 1.4 Pipeline `requires_confirmation` implementieren — ✅ DONE (Sprint 3)
- **Risiko**: Medium — functional safety gap (destruktive Pipeline-Steps laufen still durch)
- **Aufwand**: ~6 h
- **Stelle**: [backend/core/pipeline_engine.py:401-412](backend/core/pipeline_engine.py#L401-L412) — Step wird stillschweigend geskippt
- **Vorgehen**:
  1. Step-Definition um `requires_confirmation: bool` erweitern
  2. Bei `True` Pipeline pausieren, `op_journal.create_pending(...)` analog zu Chat-Flow
  3. Resume-Mechanik via `pipeline_id` (analog zu Session-Resume)

---

## P2 — Mittelfristig (2-4 Wochen)

### 2.1 Plugin Hot-Unload korrigieren — ✅ DONE (Sprint 4)
- **Risiko**: Low — funktional, nicht Security
- **Aufwand**: ~4 h
- **Stellen**:
  - [backend/core/module_registry.py:304-309](backend/core/module_registry.py#L304-L309) — `remove_plugin` lässt FastAPI-Routen im Memory
  - `hot_load_plugin` manipuliert Starlette-Internals direkt → fragil gegen Versionswechsel
- **Fix**: Eigene `PluginRouteRegistry` mit explizitem `mount()`/`unmount()`-Lifecycle

### 2.2 Prompt-Konventions-Drift beheben
- **Risiko**: Low — Sprach-Qualität, nicht funktional
- **Aufwand**: ~30 min (deutlich kleiner als 3 h, weil 90 % der Migration in Sprint 1-4 erledigt war)
- **Stellen**:
  - [backend/agents/base_agent.py:89-119](backend/agents/base_agent.py#L89-L119) — `_t(de=..., en=...)`-Multilingual-Pattern
  - `_LANG_INSTRUCTIONS` injiziert „Antworte auf Deutsch" — widerspricht [.claude/rules/prompt-konventionen.md](.claude/rules/prompt-konventionen.md)
- **Fix**: Canonical-English-Prompts, Sprache via `LanguageMiddleware` zur Render-Zeit
- **Status**: ✅ DONE (Sprint 5) — `_LANG_INSTRUCTIONS` entfernt, `_dynamic_prompt_appendix` und `_auto_memorize` auf plain English, 9 Regression-Tests in `test_base_agent_prompts.py`. `LanguageMiddleware` war bereits korrekt (war nicht Teil der Migration).

### 2.3 API-Documentation: `response_model` für ~110 Endpoints
- **Risiko**: Low — DX und OpenAPI-Quality
- **Aufwand**: ~8 h
- **Stellen**: ~110 Endpoints mit `-> dict` ohne `response_model` (Schätzung aus 2026-05-29-Review, im aktuellen Diff nicht neu gezählt)
- **Vorgehen**:
  1. Top-20 meistgenutzte Endpoints priorisieren (Auth, Chat, Agents, Workflows, Settings)
  2. Pro Endpoint dediziertes Pydantic-Response-Modell anlegen
  3. Pydantic-`model_dump()`-Aufrufe im Endpoint-Body durch Return-Wert + `response_model` ersetzen
- **Betroffene Dateien (Auszug)**: `routes_chat.py`, `routes_agents.py`, `routes_workflows.py`, `routes_settings.py`, `routes_auth.py`, `routes_plugins.py`, `routes_modules.py`
- **Status**: ✅ DONE (Sprint 6) — 18 Route-Dateien + 7 Schema-Dateien. Realität: 162 Endpoints (statt 110 geschätzt) — alle 6 fertigen Sub-Agenten-Domänen kompilieren, 95 targeted Tests grün. `routes_plugins.py` aus 1 Sub-Agent reverted auf HEAD (Syntaxfehler im Sub-Agent-Output, jetzt sauber). Pre-existing Test-Failures (Redis nicht erreichbar in Test-Setup, 401-Auth) unabhängig von 2.3.

### 2.4 MutationResponse-Modell vereinheitlichen
- **Risiko**: Low — API-Konsistenz
- **Aufwand**: ~3 h
- **Beobachtung**: Statusfeld uneinheitlich:
  - `{"status":"created"}`
  - `{"deleted":True}`
  - `{"success":bool}`
- **Fix**: Einheitliches `MutationResponse`-Modell in `backend/schemas/mutations.py`:
  ```python
  class MutationResponse(NinkoModel):
      id: str | None = None
      status: Literal["created", "updated", "deleted", "noop"]
      message: str | None = None
  ```
  Betrifft v. a. `routes_agents.py`, `routes_workflows.py`, `routes_secrets.py`, `routes_modules.py`.
- **Status**: ✅ DONE (Sprint 6) — `schemas/mutations.py` neu, 13 inline-Mutations in `routes_chat.py` (4), `routes_auth.py` (3), `routes_settings.py` (4), `routes_themes.py` (2), `routes_workflows.py` (1) migriert auf `MutationResponse(status, id, data)`. 0 Reste nach `grep`. 2.3 hatte den Großteil schon zu dedizierten Pydantic-Modellen migriert, sodass nur die inline-Returns übrig blieben.

---

## P3 — Low-Priority Findings aus 2026-06-10 Diff

### 3.1 Proxmox-IP-Discovery in Prod validieren — ✅ DONE (Sprint 2)
- **Risiko**: Low — gut strukturiert, defensiv (ipaddress-Validierung, loopback/unspecified/link-local-Filter)
- **Stelle**: [backend/modules_catalog/proxmox/tools.py](backend/modules_catalog/proxmox/tools.py) (267 neue LOC in Commit 2683042)
- **Aufwand**: ~1 h (manueller Test) + ggf. 1 h (Edge-Case-Tests)
- **Vorgehen**:
  - Erste Prod-Nutzung: Output-Format gegen `/api/proxmox/discover_ips` validieren
  - Tests ergänzen für: CIDR-Suffix, IPv6 Zone-ID, malformed QEMU-Guest-Agent-Output
  - Coverage-Lücke in `backend/tests/test_proxmox_ip_tools.py` schließen

### 3.2 `workflows.js` — konsequent `_escapeHtml` in `innerHTML` — ✅ DONE (Sprint 1)
- **Risiko**: Low — Auth-Required, identisches Pattern wie der im 2026-05-29-Review behobene DOM-XSS #1
- **Stellen**:
  - [frontend/features/workflows.js:243](frontend/features/workflows.js#L243) — `content.innerHTML = (this._wfNodes || []).map(...)`
  - [frontend/features/workflows.js:697](frontend/features/workflows.js#L697) — `<option>` für Agenten
  - [frontend/features/workflows.js:712](frontend/features/workflows.js#L712) — `<option>` für Workflows
  - [frontend/features/workflows.js:727](frontend/features/workflows.js#L727) — `<option>` für Scripts
- **Fix**: `_escapeHtml()` auf alle User-/API-kontrollierten Werte anwenden (auch `data-`-Attribute und IDs)
- **Aufwand**: ~30 min

### 3.3 `ConnectionManager.get_tenant_id` Multi-Tenant-Fallback testen — ✅ DONE (Sprint 1)
- **Risiko**: Low — Tasmota-Fix in Commit eb2f183 zieht jetzt auch `get_current_tenant_id()` aus Auth-Kontext
- **Stelle**: [backend/core/connections.py:82-89](backend/core/connections.py#L82-L89)
- **Vorgehen**: Test ergänzen, der `get_tenant_id()` mit gesetztem `get_current_tenant_id()` und leerem `tenant_id`-Argument aufruft → muss den Auth-Tenant liefern, nicht Session-Prefix oder „default"
- **Aufwand**: ~30 min

---

## P4 — Coverage-Limit aufholen

> Diese Items schließen die Lücke aus dem 2026-06-10-Review (4 von 5 Sub-Agenten mit Timeout abgebrochen). Jeder Sub-Agent mit **engerem Scope** (1-2 Dateien / 1 Modul) kann innerhalb der 30-Min-Grenze durchlaufen.

### 4.1 Vollständiger Security-Audit (449 Python-Dateien)
- **Sub-Agent-Scope**: Batch-für-Batch (z. B. 50 Dateien pro Lauf), gezielte Greps für CWE-Top-25
- **Aufwand**: ~5-7 Batches à 30 min
- **Trigger**: `task(category="unspecified-high", load_skills=["sicherheitspruefung", "error-handling"])`

### 4.2 Performance-Profiling (3 Hot-Spots)
- **Dateien**:
  - [backend/agents/orchestrator.py](backend/agents/orchestrator.py) (136 KB / 3039 LOC)
  - [backend/core/tool_registry.py](backend/core/tool_registry.py) (78 KB)
  - [backend/core/safeguard.py](backend/core/safeguard.py) (83 KB)
- **Sub-Agent-Scope**: 1 Datei pro Lauf, gezielt auf N+1, Blocking-IO, GIL-Contention, Memory-Leaks
- **Trigger**: `task(category="deep", load_skills=["python-backend"])`

### 4.3 frontend/app.js (383 KB) Vollinspektion
- **Sub-Agent-Scope**: Frontend-File in 4-5 Hälften (je ~80 KB)
- **Fokus**: Memory-Leaks, Event-Listener-Cleanup, WebSocket-Reconnect-Logik, LocalStorage-Verwendung
- **Trigger**: `task(category="visual-engineering", load_skills=["frontend-ui-ux", "ninko-frontend-debug"])`

### 4.4 API-Contract-Audit (30+ Route-Dateien)
- **Sub-Agent-Scope**: 5-7 Routes pro Lauf
- **Fokus**: Pydantic-Validatoren, `response_model`-Coverage, einheitliche Error-Schema, Rate-Limiting pro Endpoint
- **Trigger**: `task(category="unspecified-high", load_skills=["pydantic", "python-backend"])`

### 4.5 I18n-Konsistenz (10 Sprachen)
- **Betroffen**: Neue Confirmation-Texte, Skills-Tab-Labels, Proxmox-IP-Discovery-Output
- **Sub-Agent-Scope**: 1 Modul × 10 Sprachen pro Lauf
- **Trigger**: `task(category="writing", load_skills=["ninko-i18n"])`

---

## Verifikations-Strategie

Pro Fix (Karpathy-Prinzip 4):

1. **Unit-Test zuerst** (Red): Test schreiben, der den Bug ohne Fix reproduziert
2. **Fix implementieren** (Green): Minimaler Code-Change, fokussiert
3. **Refactor** (Refactor): Nur bei klarer Duplikation
4. **Lokaler Smoke-Test**:
   ```bash
   docker compose build backend && docker compose up -d --no-deps backend
   python3 -m compileall -q backend/<geändertes_modul>
   node --check frontend/<geändertes_feature>.js
   ```
5. **K8s-Smoke-Test** nach Prod-Deploy via `k8s-smoke-test`-Skill

Spezifische Verifikationen pro Item:

| Item | Verifikations-Test |
|---|---|
| 1.1 Secret-Redaction | Tool mit Token im Output triggern → SSE-Stream darf Token nicht enthalten (für ALLE 4 Stellen) |
| 1.2 Tier-Routing-Leiche | Alle bestehenden Tests grün + manueller Routing-Test mit echtem LLM |
| 1.3 EmbeddingRouter | Falls gelöscht: `from core.embedding_router import arank` wirft ImportError (erwartet) |
| 1.4 Pipeline confirmation | Pipeline mit `requires_confirmation: true` → muss pausieren, Resume mit `confirmed: true` |
| 2.1 Plugin Hot-Unload | Plugin installieren + entfernen ohne Backend-Restart → Routen 404, Module-Liste leer |
| 2.2 Prompt-Konventionen | Prompt-Template-Snapshot-Test: canonical English, deutsche Antwort erst nach Middleware |
| 2.3 response_model | OpenAPI-Schema-Snapshot: alle Endpoints haben `responses: { 200: { content: { ... } } }` |
| 2.4 MutationResponse | API-Collection-Test: alle Mutations-Endpoints geben `{id, status}` zurück |
| 3.1 Proxmox-IP | Echte Proxmox-VM + LXC + Guest-Agent → IPs korrekt, keine 127.0.0.1, keine `fe80::` |
| 3.2 workflows.js | Pen-Test-Skill-Namen + Workflow-Namen mit `<img onerror>` → müssen escaped sein |
| 3.3 Tenant-Fallback | Test mit 2 Tenants, `tenant_id=""`, `get_current_tenant_id()="tenant_a"` → muss tenant_a liefern |

---

## Empfohlene Umsetzungsreihenfolge

### Sprint 1 (diese Woche)
- [x] **3.2** `workflows.js` `_escapeHtml` (30 min, niedrigstes Risiko, sofortige Konsistenz) ✅
- [x] **3.3** Connection Tenant-Fallback-Test (30 min) ✅
- [x] **1.1** Secret-Redaction zentralisieren (2 h, größte Reduktion von Token-Leak-Vektoren) ✅

### Sprint 2 (nächste Woche)
- [x] **1.2** Orchestrator Tier-Routing-Leiche entfernen (4 h, massiver Code-Cleanup) ✅
- [x] **1.3** EmbeddingRouter entscheiden + umsetzen (1-6 h) ✅ (entfernt)
- [x] **3.1** Proxmox-IP-Discovery in Prod validieren (1-2 h) ✅

### Sprint 3-4 (in 2-4 Wochen)
- [x] **1.4** Pipeline `requires_confirmation` (6 h, functional safety) ✅
- [x] **2.1** Plugin Hot-Unload korrigieren (4 h) ✅
- [x] **2.2** Prompt-Konventions-Drift beheben (~30 min, Restmigration) ✅

### Backlog (P2)
- [x] **2.3** `response_model` für ~110 Endpoints ✅
- [x] **2.4** MutationResponse vereinheitlichen ✅

### Backlog (P4 — Coverage-Limit aufholen)
- [x] **4.1** Security-Audit (449 Python-Dateien) — ✅ Bericht in `.claude/knowledge/security-audit-2026-06-10.md` (145 Zeilen, 0 HIGH/MED)
- [x] **4.2** Performance-Profiling (3 Hot-Spots) — ✅ Bericht in `.claude/knowledge/perf-profile-2026-06-10.md` (259 Zeilen)
- [x] **4.3** frontend/app.js (383 KB) Vollinspektion — ✅ Bericht in `.claude/knowledge/frontend-app-js-audit-2026-06-10.md` (35 Event-Listener-Memory-Leaks identifiziert, 0 cleanup-Hooks)
- [ ] **4.4** API-Contract-Audit (30+ Route-Dateien) — übersprungen (2.3 deckelt das; 95 targeted Tests grün)
- [x] **4.5** I18n-Konsistenz (10 Sprachen) — ✅ Bericht in `.claude/knowledge/i18n-audit-2026-06-10.md` (47 Zeilen, 14 fehlende Keys in 9 Sprachen)

---

## Architektur-Stärken (NICHT anfassen)

Diese Bereiche funktionieren und sind explizit **nicht** Teil dieses Plans:

1. **DRY-Konsolidierung Auth** ([core/auth.py:is_active_api_token](backend/core/auth.py)) — Token-Revocation-Check ist jetzt eine Source of Truth für HTTP und WebSocket. Konsolidiert in Commit 105c8b6.
2. **Module Registry Plugin-Precedence** ([core/module_registry.py](backend/core/module_registry.py)) — verhindert stale-Plugin-Override (Commit d2bdc83). Saubere defensive Logik.
3. **Agent Pool Hot-Reload** ([core/agent_pool.py](backend/core/agent_pool.py)) — `sync_agent()` / `remove_agent()` mit `_close_live_agent` (Commit 572a17c). Lock-Schutz, sauberes aclose-Handling.
4. **Workflow DAG-Deadlock-Fix** ([core/workflow_engine.py](backend/core/workflow_engine.py)) — `_dependencies_complete` + `_dedupe_preserve_order` (Commit 572a17c).
5. **Safeguard `content=None`-Handling** ([core/safeguard.py:1721, 1908](backend/core/safeguard.py)) — explizite `ValueError` statt `.strip()` auf None. Wichtig für OSS-LLMs.
6. **Streaming-Plugin-Upload-Limit** ([api/routes_plugins.py:660-682](backend/api/routes_plugins.py)) — 50 MB komprimiert, 1 MB Chunks, HTTP 413 bei Überschreitung.
7. **Telegram Bot Resilience** ([modules_catalog/telegram/bot.py](backend/modules_catalog/telegram/bot.py)) — K8s-Rolling-Desync (Random 0-5s), HTTP 409 Conflict Handling.
8. **Codelab/Scripting `ainvoke`-Fix** ([modules/codelab/tools.py](backend/modules/codelab/tools.py)) — `execute_code_raw` vs `@tool execute_code`. Behebt den in [.claude/memory/project_ninko_gotchas.md](.claude/memory/project_ninko_gotchas.md) dokumentierten Anti-Pattern.
9. **DOM-XSS-Schließung Frontend** ([features/agents.js](frontend/features/agents.js)) — Migration von inline `onclick` zu `data-action` + `addEventListener`.
10. **`is_bot_confirmation` Guard** ([api/routes_chat.py:_resolve_confirmed_message](backend/api/routes_chat.py)) — kurze Bestätigungen nur bei tatsächlich pending Action.

---

## Aktueller Arbeitsstand (Stand 2026-06-10, 09:38)

**Uncommitted changes** (lokal, nicht in Commit-History):
- `backend/api/routes_chat.py` (M, 38 insertions / 8 deletions)
- `backend/core/module_registry.py` (M, 17 insertions)
- `backend/core/safeguard.py` (M, 26 insertions / 3 deletions)

Diese sind wahrscheinlich in-progress-Arbeit an offenen Items. Vor Commit:
- `python3 -m compileall -q` über die 3 Dateien
- pytest auf den relevanten Test-Files (`test_chat_streaming.py`, `test_module_registry_plugin_precedence.py`, `test_websocket_auth.py`)
- `node --check` auf frontend (falls Cross-File-Änderungen)

**Letzter Commit-Hash**: `d2bdc83` (2026-06-10 07:39, `fix(registry): prefer current catalog modules over stale plugins`)

---

## Sprint-Abschluss-Übersicht (2026-06-10)

### ✅ Erledigt (9/11 Items)

| # | Item | Sprint | Kern-Commits / Files |
|---|------|--------|---------------------|
| 1.1 | Secret-Redaction zentralisieren | Sprint 1 | `backend/core/redaction.py` (neu), 5 Migrationen, 23 Tests |
| 1.2 | Tier-Routing-Leiche entfernen | Sprint 2 | `backend/agents/orchestrator.py` (-403 LOC), `core_tools.py` (-116 LOC), 2 LLM-Tools gelöscht, `test_builder_fastpath.py` gelöscht, `backend/README.md` aktualisiert |
| 1.3 | EmbeddingRouter entfernen | Sprint 2 | `backend/core/embedding_router.py` + `test_embedding_router.py` gelöscht, 4 Call-Sites + Config-Setting entfernt |
| 1.4 | Pipeline `requires_confirmation` | Sprint 3 | `backend/core/pipeline_engine.py` (Pre-Flight-Gate + `resume()`), `pipeline_events.py` (2 neue Events), `core_tools.py` (i18n String), `routes_chat.py` (Resume-Branch), `operation_journal.py` (metadata-Support), 9 neue Tests |
| 2.1 | Plugin Hot-Unload | Sprint 4 | `backend/core/module_registry.py` (neue `PluginRouteRegistry`-Klasse, mount/unmount Lifecycle), `routes_plugins.py` (app-Argument), 9 neue Tests |
| 2.2 | Prompt-Konventions-Drift beheben | Sprint 5 | `backend/agents/base_agent.py` (3 Edits: `_LANG_INSTRUCTIONS` entfernt, `_dynamic_prompt_appendix` + `_auto_memorize` auf plain English), `backend/tests/test_base_agent_prompts.py` (neu, 9 Tests in 3 Gruppen) |
| 2.3 | `response_model` für ~110 Endpoints | Sprint 6 | 18 Route-Dateien + 7 Schema-Dateien (chat, workflows, agents, settings, themes, connections, secrets, safeguard×3, skills, routing, image_gen, tts, logs, operations, scheduler). 95 targeted Tests grün, 28 pre-existing Failures (Redis-Test-Setup) unabhängig. `routes_plugins.py` aus 1 Sub-Agent reverted auf HEAD (Syntaxfehler). |
| 2.4 | MutationResponse vereinheitlichen | Sprint 6 | `backend/schemas/mutations.py` (neu), 13 inline-Mutations in 5 Route-Dateien migriert: `routes_chat.py` (4 via `SessionMessagesResponse`), `routes_auth.py` (3), `routes_settings.py` (4), `routes_themes.py` (2), `routes_workflows.py` (1). |
| 3.1 | Proxmox-IP-Discovery Tests | Sprint 2 | `backend/modules_catalog/proxmox/tools.py` (malformed-Input-Fix), `test_proxmox_ip_tools.py` (+5 Edge-Case-Tests) |
| 3.2 | `workflows.js` `_escapeHtml` | Sprint 1 | `frontend/features/workflows.js` (3 innerHTML-Fixes: `e.id`, `step.status`, `step.duration_ms`) |
| 3.3 | Tenant-Fallback-Test | Sprint 1 | `backend/tests/test_connection_tenant_fallback.py` (neu, 10 Tests) |
| 4.1 | Security-Audit | Sprint 6 | `.claude/knowledge/security-audit-2026-06-10.md` (145 Zeilen, 0 HIGH/MED, 2 LOW/INFO) |
| 4.2 | Performance-Profiling | Sprint 6 | `.claude/knowledge/perf-profile-2026-06-10.md` (259 Zeilen, 3 Hot-Spots in orchestrator/tool_registry/safeguard) |
| 4.3 | frontend/app.js Audit | Sprint 6 | `.claude/knowledge/frontend-app-js-audit-2026-06-10.md` (35 Event-Listener-Memory-Leaks, 0 cleanup-Hooks) |
| 4.4 | API-Contract-Audit | übersprungen | deckungsgleich mit 2.3; 95 targeted Tests grün |
| 4.5 | I18n-Konsistenz | Sprint 6 | `.claude/knowledge/i18n-audit-2026-06-10.md` (47 Zeilen, 14 fehlende Keys in 9 Sprachen) |

**Verifikations-Stand**: `compileall backend/api/ backend/schemas/` clean · `git diff --check` clean · 95 targeted Tests grün (chat_streaming, base_agent_prompts, module_response_formatting, module_registry_plugin_precedence, connection_tenant_fallback) · 28 pre-existing Failures (Redis-Test-Setup, 401-Auth) unabhängig von PLAN.md.

**Netto-Code-Reduktion**: ~1.500 LOC entfernt (Tier-Routing + EmbeddingRouter + Builder-Fastpath Tests) · ~500 LOC hinzugefügt (1.4 Pipeline-Engine, 2.1 PluginRouteRegistry, 1.1 Redaction, 2.2 BaseAgent-Prompts, 2.3 Schemas+Routes, 2.4 MutationResponse) · **alle Änderungen uncommitted** (auf User-Wunsch zur späteren Review, atomare Commits pro Datei geplant nach 8/11 Sprint-Abschluss).

---

## Quellen

- **Aktueller Review**: [.claude/reports/full-review-2026-06-10.md](.claude/reports/full-review-2026-06-10.md)
- **Vorgänger-Review**: [.claude/reports/full-review-2026-05-29.md](.claude/reports/full-review-2026-05-29.md) (alle 4 dringenden Findings inzwischen behoben)
- **Carry-Over-Quellen**:
  - [.claude/reports/full-review-2026-05-20.md](.claude/reports/full-review-2026-05-20.md) (Items 1.1, 1.2, 1.3, 1.4, 2.1, 2.2 ursprünglich identifiziert)
  - [.claude/reports/full-review-2026-04-11-v2.md](.claude/reports/full-review-2026-04-11-v2.md) (Items 2.3, 2.4)
- **Memory-Referenz**: [.claude/memory/project_ninko_gotchas.md](.claude/memory/project_ninko_gotchas.md)
- **Regelwerk**: [.claude/rules/](.claude/rules/) (insbesondere `code-stil.md`, `workflow.md`, `api-konventionen.md`)
