# Ninko – Open Issues & Review Tracker

**Last updated:** 2026-04-13 (K8s Auth + Middleware + Persistence Verification)

## 🚨 K8s Deployment – Aktuelle Probleme (2026-04-12)

### ✅ BEHOBEN – Chat gibt keine leeren Antworten mehr
**Status:** ✅ Behoben  
**Ursache:** Response-/Memory-Logik lag fälschlich in `pre_process()` statt in `post_process()` und lief nach der Agent-Ausführung nie.  
**Fix:** `ResponseExtractionMiddleware` und `MemoryStorageMiddleware` auf echte `post_process()`-Hooks verschoben; zusätzlich Debug-Logging um `jit_agent.ainvoke()` ergänzt.

### ✅ BEHOBEN – Login funktioniert wieder
**Status:** ✅ Behoben  
**Ursache:** Mehrere Faktoren: Bootstrap-Passwort wurde beim Restart falsch behandelt, bestehende Redis-User behielten alte Hashes, und Unicode-äquivalente Passwort-Eingaben konnten unterschiedlich serialisiert werden.  
**Fix:** `force_password=False` bleibt aktiv, damit Restarts keine Passwörter überschreiben; Passwort-Hashing/Verify normalisieren Eingaben jetzt via Unicode NFC; Redis-Altzustand muss bei geänderten Bootstrap-Passwörtern einmalig bereinigt werden.

### ✅ BEHOBEN – Datenbank-Persistenz konfiguriert
**Status:** ✅ Behoben  
**Ursache:** Der Tracker war veraltet; PVC/Mounts existierten bereits, aber die Kapazität war zu klein und die K8s-/Helm-Werte waren nicht sauber nachgeführt.  
**Fix:** PVC für `/app/data` auf `10Gi` vereinheitlicht und Deployment/Chart verifiziert.

### ✅ BEHOBEN – Secrets-Migration
**Status:** ✅ Alle 10 Secrets migriert (V1 → V3)  
**Module:** IONOS, Pi-hole, Email, Home Assistant, Kubernetes, Linux Server, Proxmox, WordPress, OPNsense

### ✅ BEHOBEN – LLM-Konfiguration
**Status:** ✅ Env-Vars gepatched (Platzhalter → echte Werte)  
**Patch:** `LMSTUDIO_BASE_URL`, `LMSTUDIO_MODEL`, `LMSTUDIO_EMBED_MODEL`

---

**Full Review Reports:**

**Full Review Reports:**
- [Full Review 2026-04-11 v2](./.claude/reports/full-review-2026-04-11-v2.md) ← **AKTUELL**
- [Full Review 2026-04-11 – FINAL](./.claude/reports/full-review-2026-04-11-final.md)
- [Full Review 2026-04-11](./.claude/reports/full-review-2026-04-11.md)
- [Full Review 2026-04-10](./.claude/reports/full-review-2026-04-10.md)

> **Status Overview:**
> - 🔴 0 CRITICAL open
> - 🟡 1 HIGH open
> - 🟠 0 MEDIUM open
> - 🟢 0 LOW/ARCH open

---

## 🔴 CRITICAL – Open Issues

### K8s Deployment-Probleme
| # | Issue | Status |
|---|-------|--------|
| - | Keine offenen Critical K8s-Issues mehr | ✅ CLEAN |

### API-Auth-Lücken (vor Deployment beheben)
| # | Issue | Status |
|---|-------|--------|
| - | Keine weiteren Critical Issues | ✅ CLEAN |

---

## 🟡 HIGH – Open Issues

### K8s/Infrastructure
| # | Issue | Status |
|---|-------|--------|
| K5 | Backup-Strategie für Redis/SQLite definieren | ❌ OPEN |

---

## 🟠 MEDIUM – Open Issues

### Security & Robustheit
| # | Issue | Status |
|---|-------|--------|
| - | Keine offenen Medium Issues mehr | ✅ CLEAN |

---

## 🟢 LOW / Architektur-Schulden

| # | Issue | Status |
|---|-------|--------|
| A1 | **orchestrator.py** ~1800 Zeilen – `route()` God Method; Agent/Workflow-Builder auslagern | ✅ FIXED |
| A2-BUG | **base_agent.py** – Duplikat-Key `add_user_to_group` in `_TOOL_LABELS` → falsches UI-Label | ✅ FIXED |
| A2 | **base_agent.py** – `_TOOL_LABELS` (200+ Einträge) in tool_registry.py integrieren | ✅ FIXED |
| A3 | **agent_pool.py** – LRU-Eviction ist FIFO (`OrderedDict.move_to_end` fehlt) | ✅ FIXED |
| A4 | **agent_pool.py** – `find_best_match()` O(N×M) pro Request → Inverted-Index | ✅ FIXED |
| A5 | **tool_registry.py** – Manuelle Synchronisation; Module sollten Tools selbst registrieren | ✅ FIXED |
| F1 | **app.js:1132** – `h.id` in onclick ohne `_escapeAttr()` (inkonsistent) | ✅ FIXED |

---

## ✅ Recently Completed (Last 7 Days)

| Date | Issue | Status |
|------|-------|--------|
| 2026-04-13 | K1: `postprocess.py` – Response-/Memory-Hooks laufen wieder korrekt in `post_process()` | ✅ FIXED |
| 2026-04-13 | K2: `rbac.py` – Passwort-Hashing/Verify mit Unicode-Normalisierung (`NFC`) verifiziert | ✅ FIXED |
| 2026-04-13 | K2: `main.py` – Bootstrap-Admin bleibt bei `force_password=False` und überschreibt keine Passwörter bei Restart | ✅ VERIFIED |
| 2026-04-13 | K2/K4: K8s-/Helm-Auth – `SESSION_COOKIE_SECURE=false`, `CORS_ALLOW_ORIGINS` konfigurierbar/gesetzt | ✅ FIXED |
| 2026-04-13 | K3/K4: Backend-PVC – `/app/data` in K8s/Helm auf `10Gi` vereinheitlicht | ✅ FIXED |
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
| 2026-04-11 | C1: `routes_skills.py` – State-changing Skill-Endpunkte jetzt mit Admin-Auth | ✅ FIXED |
| 2026-04-11 | C2: `routes_plugins.py` – Plugin-Upload jetzt mit Admin-Auth | ✅ FIXED |
| 2026-04-11 | C3: `routes_plugins.py` – Marketplace-Repo-CRUD jetzt mit Admin-Auth | ✅ FIXED |
| 2026-04-11 | C4: `routes_transcription.py` – Transkriptions-Endpunkte jetzt auth-pflichtig | ✅ FIXED |
| 2026-04-11 | C5: `knowledge_graph.py` – unsicheres `pickle.load()` entfernt, JSON-only Load | ✅ FIXED |
| 2026-04-11 | C6: `routes_image_gen.py` – Image-Generation auth-pflichtig, Provider-Settings admin-only | ✅ FIXED |
| 2026-04-11 | `skills_manager.py` – Runtime-Skills nutzen schreibbaren Fallback `DATA_DIR/runtime_skills` statt fehleranfälligem Legacy-Pfad | ✅ FIXED |
| 2026-04-11 | H1: `auth.py` + `main.py` – gecachter async Auth-Resolver schließt Blacklist-Lücke für HTTP-Requests | ✅ FIXED |
| 2026-04-11 | H2: `mcp_registry.py` – `stdio` spiegelt `auth_token` nicht mehr in Subprocess-ENV | ✅ FIXED |
| 2026-04-11 | H3: `orchestrator.py` + `core_tools.py` – session-scoped Routing-State von Prozess-Globals nach Redis migriert | ✅ FIXED |
| 2026-04-12 | M1: `routes_plugins.py` – Marketplace-Repo-CRUD nutzt jetzt Pydantic-Request-Schemas | ✅ FIXED |
| 2026-04-12 | M2: `routes_plugins.py` – Upload-Fehlerpfad sanitisiert; kaputte ZIPs liefern kontrolliert `400` | ✅ FIXED |
| 2026-04-12 | M3: `vault.py` – blockierende HVAC-Calls laufen jetzt über `run_in_executor` | ✅ FIXED |
| 2026-04-12 | M4: `config.py` – Startup-Validator für Default-`SESSION_SECRET` bereits vorhanden und zur Laufzeit verifiziert | ✅ FIXED |
| 2026-04-12 | M5: `routes_secrets.py` + `schemas/secret.py` – Secret-Keys haben jetzt Längen-/Format-Validierung | ✅ FIXED |
| 2026-04-12 | M6: `proxmox/manifest.py` + `proxmox/tools.py` – kein stillschweigender SSL-Downgrade mehr auf `verify_ssl=False` | ✅ FIXED |
| 2026-04-12 | A2-BUG: `base_agent.py` – `add_user_to_group` Label ist wieder eindeutig und nicht mehr vom Entra-Eintrag überschrieben | ✅ FIXED |
| 2026-04-12 | A1: `orchestrator.py` – `route()` in Forced-/Tier-2-/Module-Invoke-Helfer zerlegt | ✅ FIXED |
| 2026-04-12 | A2: `base_agent.py` – Tool-Status-Labels aus `_TOOL_LABELS` nach `tool_registry.py` zentralisiert | ✅ FIXED |
| 2026-04-12 | A3: `agent_pool.py` – echter LRU-Zugriffs-Refresh via `OrderedDict.move_to_end()` | ✅ FIXED |
| 2026-04-12 | A4: `agent_pool.py` – invertierter Token-Index ersetzt Full-Scan in `find_best_match()` | ✅ FIXED |
| 2026-04-12 | A5: `tool_registry.py` – autodiscovery für `modules_catalog`/`modules`/`plugins`; neue Tools brauchen keinen manuellen Registry-Eintrag mehr | ✅ FIXED |
| 2026-04-12 | F1: `app.js` – Chat-History escaped `h.id`/`title` konsistent vor `innerHTML` | ✅ FIXED |
| 2026-04-12 | **K8s Debug Session** – Secrets-Migration (10/10 V1→V3), LLM-Config gepatched | ✅ DONE |
| 2026-04-12 | `main.py` – `force_password=True` für Bootstrap-Admin (Passwort-Update) | ✅ FIXED |
| 2026-04-07 | Synology Agent duplicate class definition | ✅ FIXED |
| 2026-04-07 | image_gen __init__.py bereinigt | ✅ FIXED |
| 2026-04-07 | slack tools.py – unused import entfernt | ✅ FIXED |

---

## 📊 Priority Matrix (Post-Review 2026-04-11 + K8s Debug 2026-04-12)

| Priorität | Sicherheit | Backend | Performance | Frontend | Architektur | K8s/Infra | Total |
|-----------|-----------|---------|------------|----------|------------|-----------|-------|
| 🔴 CRITICAL | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| 🟡 HIGH | 0 | 0 | 0 | 0 | 0 | 1 | **1** |
| 🟠 MEDIUM | 0 | 0 | 0 | 0 | 0 | 0 | **0** |
| 🟢 LOW | 0 | 0 | 0 | 0 | 0 | 0 | **0** |

**Total Open: 1 Issue**

**Noch offen:**
- K5: Backup-Strategie für Redis/SQLite definieren

---

## 🎯 Tool System – Roadmap

### Umsetzungsreihenfolge

```
Phase 0 (Fundament):
├── core/tool_schema.py – ToolResponse, ToolParams BaseModels  [H1]
└── core/tool_registry.py – Zentrale Registry mit Metadaten    [H2]

Phase 1 (Ökosystem):
├── Template-Update – Schema-Beispiele im _template             [M1]
└── Gating-System – required_bins/env-Checks in ToolMetadata   [M3]
```

---

## 📝 Historical Archive

Older completed items (pre-2026-04-07) were moved to [CHANGELOG.md](./CHANGELOG.md).
