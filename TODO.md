# Ninko – Open Issues & Review Tracker

**Last updated:** 2026-04-11 (MEDIUM + LOW Fixes — 29 Issues Completed)

**Full Review Reports:**
- [Full Review 2026-04-11 – FINAL](./.claude/reports/full-review-2026-04-11-final.md) ← **PRODUCTION READY**
- [Full Review 2026-04-11](./.claude/reports/full-review-2026-04-11.md)
- [Full Review 2026-04-10](./.claude/reports/full-review-2026-04-10.md)

> **Status Overview:**
> - 🔴 0 CRITICAL open
> - 🟡 0 HIGH open
> - 🟠 0 MEDIUM open
> - 🟢 0 LOW open

---

## 🔴 CRITICAL – Open Issues

*(alle behoben)*

---

## 🟡 HIGH – Open Issues

*(alle behoben)*

---

## 🟠 MEDIUM – Open Issues

*(alle behoben – siehe Recently Completed)*

---

## 🟢 LOW – Deferred / Nice-to-Have

*(alle behoben – siehe Recently Completed)*

---

## ✅ Recently Completed (Last 7 Days)

| Date | Issue | Status |
|------|-------|--------|
| 2026-04-10 | Middleware-Stack Architektur – 12+ Middlewares mit Ordering | ✅ ON BRANCH |
| 2026-04-10 | Harness/App Split – Package-Boundary + CI Test | ✅ ON BRANCH |
| 2026-04-10 | Gateway Mode – RunManager + StreamBridge | ✅ ON BRANCH |
| 2026-04-10 | LoopDetectionMiddleware – Hash-basierte Repetitions-Erkennung | ✅ ON BRANCH |
| 2026-04-10 | DanglingToolCallMiddleware – Unterbrochene Tool-Calls reparieren | ✅ ON BRANCH |
| 2026-04-10 | GuardrailMiddleware – Pre-Tool-Call Authorization | ✅ ON BRANCH |
| 2026-04-10 | LLMErrorHandlingMiddleware – Sophisticated Error Classification | ✅ ON BRANCH |
| 2026-04-10 | Virtual Path System – Tool-Isolation mit Path Masking | ✅ ON BRANCH |
| 2026-04-10 | Redis Distributed Lock – `SET NX PX` für K8s Multi-Instance | ✅ IMPLEMENTED |
| 2026-04-10 | Debounced Memory-Queue – Batch-Processing mit 30s Debounce | ✅ IMPLEMENTED |
| 2026-04-10 | Tool Error Handling Middleware – Error → ToolMessage Conversion | ✅ IMPLEMENTED |
| 2026-04-10 | `print()` → `logging` in 11 Test-Dateien | ✅ FIXED |
| 2026-04-10 | LRU/TTL-Dict: `_safeguard_session_locks` TTL 24h Cleanup | ✅ FIXED |
| 2026-04-10 | LRU/TTL-Dict: `_paused_sg_agents` TTL 300s Cleanup | ✅ FIXED |
| 2026-04-10 | System-Message Deduplizierung: `_seen_system_contents` Guard | ✅ FIXED |
| 2026-04-10 | on_llm_end `except Exception: pass` → logger.warning | ✅ FIXED |
| 2026-04-10 | LLM-Agent Cleanup bei Provider-Wechsel | ✅ FIXED |
| 2026-04-10 | Unbekannte Message-Rollen nach Compaction | ✅ FIXED |
| 2026-04-10 | `_memorize_cooldowns` LRU-Schutz: max 5000 Einträge | ✅ FIXED |
| 2026-04-10 | routes_settings.py: `_SETTINGS_RECOVERABLE_EXCEPTIONS` | ✅ FIXED |
| 2026-04-10 | core_tools.py: `_background_tasks` Limit 1000 | ✅ FIXED |
| 2026-04-10 | ocr_service.py: `Image.open()` → Context Manager | ✅ FIXED |
| 2026-04-10 | telegram/bot.py: answerCallbackQuery silent → logger.debug | ✅ FIXED |
| 2026-04-10 | GitHub-Token Verschlüsselung (CWE-256) | ✅ FIXED |
| 2026-04-10 | Skills/Soul/Memory Grenzen dokumentiert | ✅ FIXED |
| 2026-04-10 | DataAnalysisSubagent Tuple-Fehler Fix | ✅ FIXED |
| 2026-04-10 | Background-Task Exceptions Callback | ✅ FIXED |
| 2026-04-10 | Safeguard LLM Timeout blockiert jeden Request | ✅ FIXED |
| 2026-04-10 | Chat-History Memory-Leak | ✅ FIXED |
| 2026-04-10 | Redis hgetall() Scale-Problem | ✅ FIXED |
| 2026-04-10 | Frontend Script-Injection via Dynamic Module Loading | ✅ FIXED |
| 2026-04-10 | while True Loops ohne Exit-Condition (GLPI Agent) | ✅ FIXED |
| 2026-04-10 | Magic Numbers zentralisiert in core/config.py | ✅ FIXED |
| 2026-04-10 | Background Task Tracking in Telegram Bot | ✅ FIXED |
| 2026-04-10 | MCP Registry Subprocess Resource Leak | ✅ FIXED |
| 2026-04-10 | Race Condition in `agent_pool.register()` | ✅ FIXED |
| 2026-04-11 | **16 MEDIUM + 13 LOW Issues** – Alle TODO.md Security & Stability Fixes | ✅ **COMPLETED** |
| | `safeguard.py` – Exception-Tuple differentiation (ImportError vs Timeout) | |
| | `main.py` – Monitor/Scheduler add_done_callback error handlers | |
| | `knowledge_graph.py` – Thread-safe Singleton with threading.Lock | |
| | `routes_auth.py` – Brute-force protection (CWE-307) + SameSite=Strict (CWE-614) | |
| | `routes_plugins.py` – ZIP max files limit (CWE-400) | |
| | `tls.py` – SSL verify=false warning (CWE-295) | |
| | `app.js` – XSS fixes: Remove chat history from localStorage, sessionId in memory | |
| | `routes_scheduler.py` – Cron validation with croniter | |
| | `routes_transcription.py` + `image_provider.py` – Rate limiting semaphores | |
| | `glpi/agent.py` – Configurable watcher (GLPI_DEFAULT_WATCHER env var) | |
| | `module_registry.py` – Duplicate routing_keywords warning | |
| | `routes_settings.py` – api_key explicit check + chunked file upload | |
| | `main.py` – Exception-Tuple DRY fix (_MAIN_RECOVERABLE_EXCEPTIONS) | |
| | LOW Issues: HTTP Status, Response structure, Timeouts, Event listeners, SSE ping | |
| 2026-04-11 | Memory Leak: `rate_limit.py` – TTL-Cleanup für `_buckets`/`_locks` | ✅ FIXED |
| 2026-04-11 | Memory Leak: `agent_pool.py` – LRU-Eviction (max 200) + `aclose()` bei Update | ✅ FIXED |
| 2026-04-11 | Background-Task: `main.py` – `_sg_cleanup_loop` Error-Callback + `app.state` | ✅ FIXED |
| 2026-04-11 | CWE-94: `routes_plugins.py` – `pip install` mit `--isolated` + `sys.executable` | ✅ FIXED |
| 2026-04-11 | CWE-16: `config.py` – `API_AUTH_ENABLED` Default auf `True` gesetzt | ✅ FIXED |
| 2026-04-11 | CWE-20: `routes_plugins.py` – `_parse_github_url()` `re.search` → `re.match` | ✅ FIXED |
| 2026-04-11 | `routes_chat.py` – blind except pass → `logger.warning` bei Audit-Fehler | ✅ FIXED |
| 2026-04-11 | `workflow_engine.py` – Race Condition `_run_update_locks` → `setdefault()` | ✅ FIXED |
| 2026-04-11 | `memory.py:88-96` – ChromaDB in `run_in_executor` | ✅ FALSE POSITIVE (bereits korrekt) |
| 2026-04-11 | `routes_plugins.py:46` – `_marketplace_cache` TTL | ✅ FALSE POSITIVE (TTL-Check vorhanden) |
| 2026-04-11 | `config.py:78-79` – Default-Secrets Startup-Validation | ✅ FIXED (vorherige Runde) |
| 2026-04-11 | CWE-312: `connections.py` – Sensitive Field Detection + Warn-Log | ✅ FIXED |
| 2026-04-11 | CWE-78: `mcp_registry.py` – Command + Argument Whitelist-Regex | ✅ FIXED |
| 2026-04-11 | CWE-613: `auth.py`/`routes_auth.py` – Token-Blacklist bei Logout | ✅ FIXED |
| 2026-04-11 | XSS: `app.js` + `index.html` – DOMPurify + `_escapeAttr()` URL-Escaping | ✅ FIXED |
| 2026-04-11 | CWE-326: `vault.py` – PBKDF2 (210k Iterationen) mit transparentem Migration-Layer | ✅ FIXED |
| | - Dual-Key Support: Neu (210k) + Legacy (100k) | |
| | - Automatische Re-Verschlüsselung beim Lesen | |
| | - Kein Breaking Change mehr – abwärtskompatibel | |
| 2026-04-11 | CWE-379: `tls.py` – `/app/data/certs` mit mode=0o700/0o600 | ✅ FIXED |
| 2026-04-11 | CWE-918: `routes_auth.py` – IP-Whitelist für `x-forwarded-proto` | ✅ FIXED |
| 2026-04-07 | Synology Agent duplicate class definition | ✅ FIXED |
| 2026-04-07 | image_gen __init__.py bereinigt | ✅ FIXED |
| 2026-04-07 | slack tools.py – unused import entfernt | ✅ FIXED |

---

## 📊 Priority Matrix (Post-Review 2026-04-11)

| Priorität | Sicherheit | Backend | Performance | Frontend | Architektur | Total |
|-----------|-----------|---------|------------|----------|------------|-------|
| 🔴 CRITICAL | 0 | 0 | 0 | 0 | 0 | **0** |
| 🟡 HIGH | 0 | 0 | 0 | 0 | 0 | **0** |
| 🟠 MEDIUM | 7 | 5 | 0 | 2 | 2 | **16** |
| 🟢 LOW | 1 | 4 | 0 | 1 | 4 | **10** |

**Total Open: 26 Issues**

---

## 📝 Historical Archive

Older completed items (pre-2026-04-07) were moved to [CHANGELOG.md](./CHANGELOG.md).
