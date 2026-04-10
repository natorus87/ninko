# Ninko – Open Issues & Review Tracker

**Last updated:** 2026-04-10  
**Full Review Report:** [`.claude/reports/full-review-2026-04-10.md`](./.claude/reports/full-review-2026-04-10.md)

> **Status Overview:**
> - 🔴 0 CRITICAL open ✅
> - 🟡 0 HIGH open ✅
> - 🟠 20 MEDIUM open
> - 🟢 12 LOW open

---

## 🔴 CRITICAL – Open Issues

*Alle 7 CRITICAL Issues wurden am 2026-04-10 behoben. Siehe Completed-Tabelle.*


---

## 🟡 HIGH – Open Issues

*Alle 14 HIGH Issues wurden am 2026-04-10 behoben. Siehe Completed-Tabelle.*


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
| 2026-04-10 | on_llm_end `except Exception: pass` → logger.warning | ✅ FIXED |
| 2026-04-10 | LLM-Agent Cleanup bei Provider-Wechsel (aclose() vor create_react_agent) | ✅ FIXED |
| 2026-04-10 | Unbekannte Message-Rollen nach Compaction — logger.warning | ✅ FIXED |
| 2026-04-10 | `_memorize_cooldowns` LRU-Schutz: max 5000 Einträge, 500 älteste entfernt | ✅ FIXED |
| 2026-04-10 | routes_settings.py: `_SETTINGS_RECOVERABLE_EXCEPTIONS` Konstante + 6× logger.warning | ✅ FIXED |
| 2026-04-10 | core_tools.py: `_background_tasks` Limit 1000, cancel oldest | ✅ FIXED |
| 2026-04-10 | ocr_service.py: `Image.open()` → `with Image.open(...) as img:` | ✅ FIXED |
| 2026-04-10 | telegram/bot.py: answerCallbackQuery silent pass → logger.debug | ✅ FIXED |
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
| 🟡 HIGH | 0 | 0 | 0 | 0 | 0 | **0** |
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
