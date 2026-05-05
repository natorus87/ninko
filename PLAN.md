# Core Agent Review – Bugs & Verbesserungen

**Erstellt:** 2026-05-05
**Reviewer:** Sisyphus
**Scope:** Core Agent Logik und Komponenten

---

## 🔴 KRITISCHE BUGS (Status: ✅ ERLEDIGT)

### 1. JIT Tool Injection Fallback eliminiert den Sinn der Optimierung
- **Datei:** `backend/agents/base_agent.py:680`
- **Problem:** `_select_tools_for_request()` gibt bei `< 3` relevanten Tools ALLE Tools zurück.
- **Fix:** Fallback bei `== 0` Treffern auf `tools[:jit_max_tools]` beschränkt statt alle Tools zurückzugeben.
- **Status:** ✅ ERLEDIGT

### 2. Gateway `stream_run()` kann endlos blockieren
- **Datei:** `backend/core/gateway.py:151-168`
- **Problem:** Endlosschleife wenn Run abstürzt ohne `None` in Queue zu legen.
- **Fix:** `empty_polls` Counter mit `_STREAM_MAX_EMPTY_POLLS = 1200` (10min Max) hinzugefügt. Bricht Stream nach max. Leerpolls ab.
- **Status:** ✅ ERLEDIGT

### 3. `_tool_args` Dict wächst unbounded
- **Datei:** `backend/agents/base_agent.py:118`
- **Problem:** Tracking-Dicts werden nur in `on_tool_end` geleert, nicht bei Fehlern.
- **Fix:** `on_tool_error`-Handler hinzugefügt, `_cleanup_run()`-Methode extrahiert, `_evict_oldest_if_full()` mit `_MAX_PENDING = 500` Obergrenze.
- **Status:** ✅ ERLEDIGT

---

## 🟡 SIGNIFIKANTE PROBLEME (Status: ✅ ERLEDIGT)

### 4. Hardcoded Timeout statt konfigurierbarer
- **Datei:** `backend/agents/middleware/execution.py:18`
- **Problem:** `_AGENT_TIMEOUT_SECS = 600` ist hardcoded, während `base_agent.py:441-449` einen konfigurierbaren `_get_agent_timeout_seconds()` hat, der `AGENT_TIMEOUT_SECONDS` aus der Config liest.
- **Fix:** `_get_timeout()` Helper mit Config-Lese und Fallback hinzugefügt. `post_process()` nutzt nun denselben konfigurierbaren Timeout.
- **Status:** ✅ ERLEDIGT

### 5. Session-Lock-Cleanup nur bei Aufruf
- **Datei:** `backend/agents/base_agent.py:406-419`
- **Problem:** `_get_safeguard_session_lock()` räumt abgelaufene Locks nur auf, wenn ein neuer Lock angefordert wird.
- **Fix:** `_MAX_SAFEGUARD_LOCKS = 1000` Obergrenze hinzugefügt. Cleanup wird jetzt auch bei Erreichen der Obergrenze ausgelöst.
- **Status:** ✅ ERLEDIGT

### 6. Routing-Map `invalidate_routing_map()` ist No-Op
- **Datei:** `backend/agents/orchestrator.py:552-554`
- **Problem:** `_invalidate_routing_cache()` tut nichts.
- **Fix:** `self._routing_dirty = True` gesetzt.
- **Status:** ✅ ERLEDIGT

### 7. `is_readonly()` gibt `False` für unregistrierte Tools zurück
- **Datei:** `backend/core/tool_registry.py:526-529`
- **Problem:** Falsches Verhalten bei nicht-registrierten Tools.
- **Fix:** Rückgabetyp auf `bool | None` geändert. Gibt `None` für unregistrierte Tools zurück.
- **Status:** ✅ ERLEDIGT

### 8. Memory Singleton nicht Thread-Safe
- **Datei:** `backend/core/memory.py:298-303`
- **Problem:** `get_memory()` prüft `if _memory is None` ohne Lock.
- **Fix:** Double-Checked Locking mit `threading.Lock()` implementiert.
- **Status:** ✅ ERLEDIGT

---

## 🔵 VERBESSERUNGSVORSCHLÄGE (Status: ✅ ERLEDIGT)

### 9. Duplizierte Lock-Logik (sync vs async)
- **Datei:** `backend/agents/base_agent.py:396-438`
- **Fix:** `_get_safeguard_session_lock_async` als Dead Code entfernt (wurde nirgends aufgerufen).
- **Status:** ✅ ERLEDIGT

### 10. `_StatusEmitter` Readonly-Heuristik ist fragil
- **Datei:** `backend/agents/base_agent.py:194-204`
- **Fix:** `tool_registry.is_readonly()` als primäre Quelle, Prefix-Heuristik nur als Fallback bei unregistrierten Tools.
- **Status:** ✅ ERLEDIGT

### 11. Secrets im Audit-Event
- **Datei:** `backend/agents/base_agent.py:144`
- **Fix:** Args vor Emit durch `sanitize_tool_output()` sanisiert.
- **Status:** ✅ ERLEDIGT

### 12. Kein Retry-Logic für ChromaDB
- **Datei:** `backend/core/memory.py`
- **Fix:** `_run_with_retry()` mit exponentiellem Backoff (3 Versuche, 0.5s/1s/2s) für `store()`, `search()`, `delete()`.
- **Status:** ✅ ERLEDIGT

### 13. Gateway präventive Eviction fehlt
- **Datei:** `backend/core/gateway.py:56-131`
- **Fix:** Graceful Degradation – ältesten laufenden Run canceln statt RuntimeError werfen. Warning-Log für Operatoren.
- **Status:** ✅ ERLEDIGT

### 14. `execute_cli_command` Allowlist enthält gefährliche Befehle
- **Datei:** `backend/agents/core_tools.py:100-126`
- **Fix:** `curl`, `wget`, `nmap` in separate `_NETWORK_COMMANDS`-Kategorie verschoben. Explizite Fehlermeldung bei Versuch der Nutzung.
- **Status:** ✅ ERLEDIGT

---

## ZUSAMMENFASSUNG

**14 von 14 Problemen behoben.**

| Kategorie | Anzahl | Status |
|-----------|--------|--------|
| Kritische Bugs | 3 | ✅ ERLEDIGT |
| Signifikante Probleme | 5 | ✅ ERLEDIGT |
| Verbesserungen | 6 | ✅ ERLEDIGT |