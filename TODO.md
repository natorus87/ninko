# Ninko – Open Issues & Review Tracker

**Last updated:** 2026-04-10  
**Full Review Report:** [`.claude/reports/full-review-2026-04-10.md`](./.claude/reports/full-review-2026-04-10.md)

> **Status Overview:**
> - 🔴 0 CRITICAL open ✅
> - 🟡 14 HIGH open (code quality, concurrency, NEW: resource leaks)
> - 🟠 20 MEDIUM open
> - 🟢 12 LOW open

---

## 🔴 CRITICAL – Open Issues

*Alle 7 CRITICAL Issues wurden am 2026-04-10 behoben. Siehe Completed-Tabelle.*


---

## 🟡 HIGH – Open Issues

### Code Quality – Exception Handling

- [ ] **Breite Exception-Handler ermöglichen Silent Failures**
  - Files: `backend/api/routes_plugins.py:575-583`, `backend/main.py:66-74, 167-176`
  - Problem: Multi-Exception-Tupel mit 7+ Typen → maskiert echte Bugs
  - Action: `_COMMON_STARTUP_EXCEPTIONS` Konstante + spezifisches Logging

- [ ] **Broad `try/except Exception` in routes_subagent.py (NEW)**
  - File: `backend/api/routes_subagent.py:97-114`
  - Problem: Outer try/except um subagent step loading – swallowed errors
  - Action: Targeted exceptions + logging

- [ ] **Broad catch in DataAnalysisSubagent (NEW)**
  - File: `backend/agents/data_analysis_subagent.py:377-383`
  - Problem: Broad catch um StepTrackingHandler – masks root causes
  - Action: Replace with specific exceptions

- [ ] **Broad `except Exception` in on_llm_end (NEW)**
  - File: `backend/agents/base_agent.py:596-618`
  - Problem: Token-tracking errors swallowed silently
  - Action: Log errors instead of silent pass

- [ ] **Silent Exception-Handling ohne Logging (6 Stellen)**
  - Files: `base_agent.py`, `data_analysis_subagent.py`, `metrics.py`, `routes_subagent.py`, `openproject/tools.py`, `telegram/bot.py`
  - Problem: `except Exception: pass` → Datenverlust unmerklich
  - Action: `logger.warning()` für jeden silent `pass`

- [ ] **79 Zeilen duplizierten Exception-Code**
  - Files: `routes_plugins.py:575-583`, `core_tools.py:247-258, 294-296, 304-312`
  - Problem: Identische Exception-Handler mehrfach wiederholt
  - Action: Refactor zu `core/exceptions.py` mit zentralen Exception-Sets

- [ ] **Bare `except Exception:` in Auth Path**
  - File: `backend/main.py:666`
  - Problem: `_is_active_user_api_token` gibt False bei Exception zurück, ohne Logging
  - Action: Spezifische Exceptions catchen + `logger.exception()` hinzufügen

- [ ] **Silent Exception in Update Check**
  - File: `backend/api/routes_plugins.py:332-333`
  - Problem: `except Exception: return {"update_available": False}` ohne Logging
  - Action: `logger.exception()` hinzufügen

- [ ] **Silent `pass` in Exception Handlers (8 Stellen)**
  - Files: `routes_settings.py:148,273,519,1118,1315,1418`, `telegram/bot.py:646-647`, `knowledge_graph/manifest.py:29-30`
  - Problem: Fehler werden stillschweigend ignoriert
  - Action: Mindestens `logger.warning()` hinzufügen

### Agent Logic

- [ ] **Alter LLM-Agent wird bei Provider-Wechsel nicht aufgeräumt**
  - File: `backend/agents/base_agent.py:906-908`
  - Problem: HTTP-Connection/Stream bleibt offen bei Provider-Wechsel
  - Action: `if hasattr(self._agent, 'cleanup'): await self._agent.cleanup()`

- [ ] **Keine Validation der Message-Rollen nach Compaction**
  - File: `backend/agents/base_agent.py:1092-1106`
  - Problem: Unbekannte `role`-Werte werden still ignoriert
  - Action: `logger.warning("Unknown message role: %s — skipping", role)`

### Concurrency

- [ ] **Keine Bounds-Checking auf `_background_tasks`**
  - File: `backend/agents/core_tools.py:708-710`
  - Problem: Wächst unkontrolliert bei vielen `create_dag_workflow()`-Calls
  - Action: Limit auf 1000 Tasks + Cancel des ältesten

- [ ] **`_memorize_cooldowns` wächst unbegrenzt**
  - File: `backend/agents/base_agent.py:1200-1210`
  - Problem: `(agent_name, session_id)` Keys werden nie gelöscht
  - Action: LRU-Dict mit max_size=5000

- [ ] **`UnboundLocalError` möglich bei Subagent-Fehler**
  - File: `backend/agents/orchestrator.py:1876-1877`
  - Problem: `response` nicht definiert wenn `subagent.invoke()` wirft
  - Action: Exception in `except` abfangen mit Fallback-Response

### Resource Management

- [ ] **Memory-Leak: `_safeguard_session_locks` wächst unbegrenzt (NEW)**
  - File: `backend/core/safeguard.py:653-670`
  - Problem: Globales Dict ohne TTL/Cleanup – wächst unbegrenzt
  - Action: TTL-basiertes Cleanup implementieren (24h)

- [ ] **Untracked `asyncio.create_task` (NEW)**
  - File: `backend/agents/base_agent.py:~572-575`
  - Problem: `emit_tool_event()` als Task gestartet ohne Tracking
  - Action: Task in `_background_tasks` aufnehmen + add_done_callback

- [ ] **Unclosed Resource: `Image.open()` (NEW)**
  - File: `backend/core/ocr_service.py:72`
  - Problem: `Image.open(io.BytesIO(...))` ohne Context Manager
  - Action: `with Image.open(...) as img:` verwenden


---

## 🟠 MEDIUM – Open Issues

### Code Quality

- [ ] **LOW: Unused Imports** (`shutil`, `uuid` in routes_plugins.py)
- [ ] **LOW: Inline Comments zu vage** (safeguard.py:392-395)
- [ ] **LOW: Konstanten sollten Enums sein** (main.py:598-621)
- [ ] **LOW: Redundante Null-Checks** (main.py:656-660)
- [ ] **LOW: Missing Type Hints** (core_tools.py:56-88, fritzbox/tools.py:202)
- [ ] **LOW: Test Files use `print()` instead of logging** (44× in 11 Dateien)

### DeerFlow-Inspired Patterns (Medium Priority)

- [ ] **Debounced Memory-Queue** – Batch-Processing statt Task-Flood
  - Problem: Task-Flood bei schnellen Chats + stumme Background-Task-Exceptions
  - Action: Singleton-Queue dedupliziert Updates pro `session_id`
  - Ref: `deerflow/agents/memory/queue.py`

- [ ] **Tool Error Handling Middleware** – GraphBubbleUp Preservation
  - Problem: Tool-Exceptions crashen den Graph
  - Action: Convert exceptions to error ToolMessages
  - Ref: `deerflow/agents/middlewares/tool_error_handling_middleware.py`

- [ ] **Redis Distributed Lock** – K8s Multi-Instance Race Conditions
  - Problem: asyncio.Lock nicht verteilt über K8s-Pods
  - Action: `SET NX PX 5000` atomares Distributed Lock
  - Ref: `deerflow/utils/redis_lock.py`

- [ ] **LRU/TTL-Dict** – Session-State Memory-Leak Fix
  - Problem: `_safeguard_session_locks`, `_paused_sg_agents` wachsen unbegrenzt
  - Action: `_TTLDict(maxsize=1000, ttl=3600)`
  - Ref: `deerflow/utils/ttl_dict.py`

- [ ] **System-Message Deduplizierungs-Guard** nach Compaction
  - Problem: Doppelte `role="system"` nach Compaction-Zyklen
  - Action: `_seen_system_contents: set[str]` als Guard
  - Ref: `deerflow/agents/thread_state.py`

### Langfristig (Architektur)

- [ ] **Middleware-Stack Architektur** – 12+ Middlewares mit Ordering
  - Problem: Monolithische ~300-Zeilen `invoke()`-Methode
  - Action: Middleware-Klassen mit strikter Ordering-Enforcement
  - Ref: `deerflow/agents/lead_agent/agent.py:198-270`
  - Aufwand: Groß (eigener Branch)

- [ ] **Harness/App Split** – Enforced Boundary für Package-Publishing
  - Problem: Core und App-Code vermischt
  - Action: `ninko.harness.*` vs `app.*` mit CI-Tests
  - Ref: `deerflow/` vs `backend/app/`
  - Aufwand: Groß (Repository-Restrukturierung)

- [ ] **Gateway Mode** – Embedded Runtime ohne separatem Server
  - Problem: Separate LangGraph Server Prozess nötig
  - Action: Embed runtime via `RunManager` + `StreamBridge`
  - Ref: `deerflow/runtime/`, `deerflow/gateway/routers/threads.py`
  - Aufwand: Groß (Alternatives Deployment)

---

## 🟢 LOW – Deferred / Nice-to-Have

- [ ] Inconsistent Timeout Values → weitere Timeouts in CoreSettings verschieben
- [ ] `_MAX_UNCOMPRESSED_SIZE` in CoreSettings verschieben (routes_plugins.py)
- [ ] Telegram Bot Background Task Tracking → vereinfachen

---

## ✅ Recently Completed (Last 7 Days)

| Date | Issue | Status |
|------|-------|--------|
| 2026-04-10 | GitHub-Token Verschlüsselung (CWE-256) via Fernet/SESSION_SECRET | ✅ FIXED |
| 2026-04-10 | Skills/Soul/Memory Grenzen in Modul-Docstrings dokumentiert | ✅ FIXED |
| 2026-04-10 | `_safeguard_session_locks` Memory-Leak — TTL 24h Cleanup | ✅ FIXED |
| 2026-04-10 | `_paused_sg_agents` Memory-Leak — TTL 300s Cleanup | ✅ FIXED |
| 2026-04-10 | Doppelte System-Messages nach Compaction — `_seen_system_contents` Guard | ✅ FIXED |
| 2026-04-10 | DataAnalysisSubagent Tuple-Fehler — defensiver Unpack mit Fallback | ✅ FIXED |
| 2026-04-10 | Background-Task Exceptions — `_log_bg_task_exception` Callback (3 Stellen) | ✅ FIXED |
| 2026-04-10 | 4 von 5 CRITICAL Security Issues bereits sicher | ✅ |
| 2026-04-10 | Safeguard LLM Timeout blockiert jeden Request | ✅ FIXED |
| 2026-04-10 | Chat-History Memory-Leak (unbegrenztes Wachstum) | ✅ FIXED |
| 2026-04-10 | Redis hgetall() Scale-Problem | ✅ FIXED |
| 2026-04-10 | Frontend Script-Injection via Dynamic Module Loading | ✅ FIXED |
| 2026-04-10 | while True Loops ohne Exit-Condition (GLPI Agent) | ✅ FIXED |
| 2026-04-10 | Magic Numbers zentralisiert in core/config.py | ✅ FIXED |
| 2026-04-10 | Background Task Tracking in Telegram Bot | ✅ FIXED (verifiziert: `_track_task()` in bot.py) |
| 2026-04-10 | MCP Registry Subprocess Resource Leak | ✅ FIXED (verifiziert: `communicate()` in mcp_registry.py:282) |
| 2026-04-10 | Race Condition in `agent_pool.register()` | ✅ FIXED (verifiziert: `async with self._register_lock:` in agent_pool.py:286) |
| 2026-04-07 | Synology Agent duplicate class definition | ✅ FIXED |
| 2026-04-07 | image_gen __init__.py bereinigt | ✅ FIXED |
| 2026-04-07 | slack tools.py – unused import entfernt | ✅ FIXED |

---

## 📊 Priority Matrix (Post-Review 2026-04-10)

| Priorität | Sicherheit | Backend | Performance | Frontend | Architektur | Total |
|-----------|-----------|---------|------------|----------|------------|-------|
| 🔴 CRITICAL | 0 | 0 | 0 | 0 | 0 | **0** |
| 🟡 HIGH | 6 | 8 | 0 | 0 | 0 | **14** |
| 🟠 MEDIUM | 0 | 4 | 0 | 0 | 3 | **7** |
| 🟢 LOW | 0 | 3 | 0 | 0 | 0 | **3** |

**Total Open: 31 Issues** (3 False-Positives entfernt, da bereits gefixt im Code)

---

## 🆕 Full Review 2026-04-10 – New Findings

**Review durchgeführt:** 4 parallele Explore-Agents
**Ergebnis:** Keine kritischen Security-Lücken ✅, aber 3 neue HIGH-Priority Issues

### NEW: Memory & Resource Leaks

| Datei | Zeile | Problem | Severity |
|-------|-------|---------|----------|
| `backend/core/safeguard.py` | 653-670 | `_safeguard_session_locks` wächst unbegrenzt | HIGH |
| `backend/agents/base_agent.py` | ~572-575 | `asyncio.create_task` ohne Task-Tracking | HIGH |
| `backend/core/ocr_service.py` | 72 | `Image.open()` ohne Context Manager | HIGH |

### NEW: Exception Handling

| Datei | Zeile | Problem | Severity |
|-------|-------|---------|----------|
| `backend/api/routes_subagent.py` | 97-114 | Broad try/except swallowing step-load errors | HIGH |
| `backend/agents/data_analysis_subagent.py` | 377-383 | Broad catch masks subagent errors | HIGH |
| `backend/agents/base_agent.py` | 596-618 | Token-tracking errors swallowed | HIGH |

### Security Scan (Clean) ✅

- ✅ Kein `pickle.loads` / `yaml.load` ohne Loader
- ✅ Kein `subprocess` mit `shell=True`
- ✅ Keine SQL-Injection via f-strings
- ✅ Keine hardcodierten Secrets
- ℹ️ `"password"`/`"api_key"` sind Config-Keys, keine harten Secrets

---

## 🔥 DeerFlow Killer Features (Recommended Priority Order)

1. **LoopDetectionMiddleware** 🔥 HIGH – Hash-basierte Repetitions-Erkennung
2. **DanglingToolCallMiddleware** 🔥 HIGH – Unterbrochene Tool-Calls reparieren
3. **GuardrailMiddleware** 🔥 HIGH – Pre-Tool-Call Authorization
4. **LLMErrorHandlingMiddleware** 🔥 HIGH – Sophisticated Error Classification
5. **Virtual Path System** 🔥 HIGH – Tool-Isolation mit Path Masking

Details + Referenzen: [Full Review Report](./.claude/reports/full-review-2026-04-10.md)

---

## 📝 Historical Archive

Older completed items (pre-2026-04-07) were moved to [CHANGELOG.md](./CHANGELOG.md).
