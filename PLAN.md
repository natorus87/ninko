# Plan: Full Code Review 2026-05-20

**Datum**: 2026-05-20
**Scope**: Backend (Python/FastAPI) + Frontend (Vanilla JS) + Architektur + API + Security
**Reviewer**: Multi-Agent Review (5 Sub-Agenten, Re-Run mit engerem Scope für Backend/Security/Frontend)
**Quelle**: `.claude/reports/full-review-2026-05-20.md`

> **Vorgänger**: Der frühere PLAN.md (Canonical-English-Prompts-Migration, abgeschlossen 2026-05-15) ist umgesetzt — siehe `.claude/rules/prompt-konventionen.md`. Dieser Plan ersetzt ihn.

---

## Executive Summary

| Bereich | Status | Critical | High | Medium | Low/Info |
|---|---|---:|---:|---:|---:|
| Backend Code | gelb–rot | 3 | 6 | 6 | 6 |
| Security (Vault/Auth/SafeGuard) | rot | 3 | 6 | 5 | 4 |
| Frontend (XSS / Leaks) | rot | 1 | 3 | 4 | 3 |
| Architektur | gelb | 0 (1×Problematic) | 3 | 4 | – |
| API Contracts | gelb | 0 | 7 | 30+ | 20+ |
| **Total** | **rot** | **7** | **25+** | **49+** | **33+** |

**Deployment-blockierend** (P0, vor jedem nächsten Release fixen): 7 Critical + DOMPurify-Whitelist.

### Aktueller Arbeitsstand — 2026-05-24

Der P0-Block wurde schrittweise gegen den Code geprüft und umgesetzt.

| ID | Status | Umsetzung |
|---|---|---|
| P0-1 | erledigt | Modul-HTML-Sanitizing entfernt `onclick`/Inline-Handler, setzt `FORBID_ATTR`, begrenzt URI-Schemas und fällt ohne DOMPurify geschlossen aus. |
| P0-2 | erledigt | `/api/secrets/*` hat jetzt Router-Level-Admin-Dependency. |
| P0-3 | erledigt | `_StatusEmitter`-Redaction nutzt echte Whitespace-Matcher statt doppelt escapte Regex-Backslashes. |
| P0-4 | erledigt | Nicht entschlüsselbare SQLite-Secrets raisen `InvalidToken` statt still `None` zurückzugeben. |
| P0-5 | erledigt | Vault-Startup-Migration re-encrypted Legacy-SQLite-Secrets von PBKDF2-100k/SHA256-v1 auf den aktuellen PBKDF2-210k-Key. |
| P0-6 | erledigt | Safeguard-Pending wird zuerst in Redis persistiert, Lock-Erzeugung ist `setdefault`-basiert, Resume-Fehlerpfade räumen Pending-State auf. |
| P0-7 stage 1 | erledigt | Startup-Sweeper markiert verwaiste laufende Workflow-Runs nach Backend-Restart als `interrupted`; Workflow-Runs erhalten `updated_at`. |
| P0-7 stage 2 | offen | Vollständiges Resume mit persistiertem `visited`/`queue` bleibt mittelfristiger Folgepunkt. |

Verifikation am 2026-05-24:

```bash
python3 -m compileall -q backend/api/routes_secrets.py backend/agents/base_agent.py backend/core/vault.py backend/core/workflow_engine.py backend/api/routes_workflows.py backend/schemas/workflows.py backend/main.py
node --check frontend/app.js
git diff --check
```

Alle drei Checks waren erfolgreich.

### P1-Fortschritt — 2026-05-24

Zusätzlich zum P0-Block wurden risikoarme P1-Punkte umgesetzt:

| ID | Status | Umsetzung |
|---|---|---|
| P1-1 | erledigt | Pipeline-Fehler geben keine rohen Exception-Strings mehr an den User zurück; fehlgeschlagene Pipeline-Steps zeigen generische Fehlermeldungen. |
| P1-2 | teilweise erledigt | Streaming-`token_queue` hat jetzt `maxsize=1000`; der größere Producer/Consumer-Refactor bleibt offen. |
| P1-4 | erledigt | Agent-Execution-Logs loggen keine Tracebacks/rohen Exception-Strings mehr; bekannte Secret-Patterns werden vor Log-Ausgabe redacted. |
| P1-5 | erledigt | SSE-Fehler-/Cancel-Pfade markieren offene Operation-Journal-Transaktionen als `failed` und räumen Pending-State auf. |
| P1-6 | erledigt | Semantic Route Cache nutzt `MGET` statt N×`GET` für gescannte Cache-Keys. |
| P1-7 | erledigt | `bootstrap_admin` ist bei `API_AUTH_ENABLED=false` nur noch von Loopback-Clients erlaubt. |
| P1-9 | teilweise erledigt | API-Token-Erstellung setzt `Cache-Control: no-store` und `Pragma: no-cache`; `response_model` bleibt offen. |
| P1-11 | erledigt | SQLite-Secret-DB-Pfad kommt aus `DATA_DIR` statt aus hartkodiertem `/app/data`. |

Verifikation für diesen P1-Teil:

```bash
python3 -m compileall -q backend/agents/orchestrator.py backend/agents/middleware/execution.py backend/api/routes_chat.py backend/api/routes_auth.py backend/core/vault.py
node --check frontend/app.js
git diff --check
```

Alle drei Checks waren erfolgreich.

Zusätzliche Test-Verifikation nach Installation der fehlenden lokalen Dependencies:

```bash
API_AUTH_ENABLED=false REDIS_URL=redis://localhost:6379/15 SESSION_SECRET=0123456789abcdef0123456789abcdef SQLITE_SECRETS_KEY=0123456789abcdef0123456789abcdef .venv/bin/python -m pytest -q backend/tests/test_api_security_policy.py backend/tests/test_workflows_integration.py
API_AUTH_ENABLED=false REDIS_URL=redis://localhost:6379/15 SESSION_SECRET=0123456789abcdef0123456789abcdef SQLITE_SECRETS_KEY=0123456789abcdef0123456789abcdef .venv/bin/python -m pytest -q backend/tests/test_chat_streaming.py
```

Ergebnis:

- `backend/tests/test_api_security_policy.py` + `backend/tests/test_workflows_integration.py`: 20 passed
- `backend/tests/test_chat_streaming.py`: 7 passed

Hinweis: Die vorhandene `.venv` nutzt Python 3.14.3; `python3.12-venv` ist lokal nicht installiert. Für die Testfähigkeit wurden die fehlenden Dependencies in `.venv` installiert. Dabei musste `pydantic-settings` in der Test-venv auf `2.14.1` statt des in `backend/requirements.txt` gepinnten `2.7.1` installiert werden, weil die installierte aktuelle LangChain-Community-Version `>=2.10.1` verlangt.

### K8s-Fix — Telegram FRITZ!Box/Tasmota — 2026-05-24

Der auf K8s gemeldete Telegram-Fehler wurde gegen Pod-Logs geprüft und behoben:

| Punkt | Status | Umsetzung |
|---|---|---|
| Safeguard-False-Positive | erledigt | Deutsche Read-only-Anfragen mit `finden` werden im Short-Prefilter als `SAFE` erkannt, sofern keine Schreib-/Löschbegriffe im Text vorkommen. |
| ReAct-Fallback-Crash | erledigt | JIT-Toolauswahl akzeptiert normale Callable-Tools ohne `.name`/`.description` und nutzt robuste Tool-Metadaten-Helper. |
| FRITZ!Box/Tasmota-Fast-Path | erledigt | Explizite Tasmota-Suche über FRITZ!Box ruft die Geräteliste direkt ab und filtert ohne LLM-Routing. |
| Regressionstests | erledigt | `backend/tests/test_k8s_telegram_regressions.py` deckt Safeguard, Callable-Tools und den direkten FRITZ!Box/Tasmota-Fast-Path ab. |
| K8s-Deployment | erledigt | Backend-Image `natorus87/ninko-backend:latest` neu gebaut, gepusht (`sha256:9055335e...`) und `deployment/ninko-backend` im Namespace `ninko` neu ausgerollt. |

Verifikation:

```bash
API_AUTH_ENABLED=false REDIS_URL=redis://localhost:6379/15 SESSION_SECRET=0123456789abcdef0123456789abcdef SQLITE_SECRETS_KEY=0123456789abcdef0123456789abcdef .venv/bin/python -m pytest backend/tests/test_api_security_policy.py backend/tests/test_workflows_integration.py backend/tests/test_chat_streaming.py backend/tests/test_k8s_telegram_regressions.py
kubectl rollout status deployment/ninko-backend -n ninko --timeout=240s
kubectl exec deployment/ninko-backend -n ninko -- python -c "from core.safeguard import SafeguardMiddleware, ActionCategory; m=SafeguardMiddleware.__new__(SafeguardMiddleware); r=m._fast_prefilter_short('Benutze FRITZ!Box, um alle Tasmota Geräte zu finden'); assert r and r['requires_confirmation'] is False and r['category'] is ActionCategory.SAFE"
kubectl exec deployment/ninko-backend -n ninko -- python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status)"
```

Ergebnis: 31 Tests passed, Rollout erfolgreich, neuer Pod `1/1 Running`, Healthcheck `200`.

Hinweis: Zum Zeitpunkt des ersten Fixes war der konfigurierte LLM-Endpunkt zeitweise nicht erreichbar; der FRITZ!Box/Tasmota-Fast-Path umgeht die LLM-Abhängigkeit für genau diese Read-only-Anfrage.

### Telegram/Safeguard-Stabilisierung — 2026-05-25

Nach weiteren Telegram-Ausführungsfehlern wurden die laufenden K8s-Logs und Redis-Provider-Settings geprüft:

| Punkt | Status | Umsetzung |
|---|---|---|
| Embedding-Provider nach Restart | erledigt | Startup stellt jetzt auch `ninko:settings:embed_provider` wieder her; Embeddings gehen auf `http://10.11.12.6:8081/v1` statt versehentlich auf den Chat-Endpoint. |
| ReAct-Fallback-Fehler | erledigt | LLM-Ausfälle im ReAct-Fallback werden abgefangen und als klare User-Antwort zurückgegeben statt als Exception ins Telegram-Modul zu laufen. |
| Telegram-Fehlermeldungen | erledigt | Telegram sendet bei LLM-Verbindungsfehlern/Timeouts konkrete Hinweise statt nur generischem `Fehler bei der Ausführung`. |
| Safeguard-Kontext | erledigt | Telegram-Safeguard-Checks übergeben jetzt `agent_id` und `session_id`, damit Profile/Session-Kontext greifen. |
| K8s-Deployment | erledigt | Backend-Image `natorus87/ninko-backend:latest` neu gebaut, gepusht (`sha256:43d4c517...`) und ausgerollt. |

Verifikation:

```bash
API_AUTH_ENABLED=false REDIS_URL=redis://localhost:6379/15 SESSION_SECRET=0123456789abcdef0123456789abcdef SQLITE_SECRETS_KEY=0123456789abcdef0123456789abcdef .venv/bin/python -m pytest backend/tests/test_api_security_policy.py backend/tests/test_workflows_integration.py backend/tests/test_chat_streaming.py backend/tests/test_k8s_telegram_regressions.py
kubectl rollout status deployment/ninko-backend -n ninko --timeout=240s
kubectl logs ninko-backend-cdbbfb857-nqc8d -n ninko --since=1m | rg "Telegram HTTP Error: 409|Callback confirm|Safeguard.*failed|Classifier call failed|Function Calling LLM call failed|ReAct fallback failed|ERROR|Traceback" || true
```

Ergebnis: 32 Tests passed, Rollout erfolgreich, neuer Pod `1/1 Running`, Healthcheck `200`, Startup-Logs zeigen den wiederhergestellten Embedding-Provider.

---

## P0 — Sofort (deployment-blockierend)

Diese Befunde müssen **vor dem nächsten Deployment** behoben sein. Reihenfolge nach Risiko.

### P0-1 — DOMPurify-Whitelist erlaubt `onclick` → Account-Takeover
- **Datei**: [frontend/app.js:577-582](frontend/app.js#L577)
- **Risiko**: XSS aus jedem Modul-HTML (auch Marketplace/Community). Vollständiger Account-Takeover-Vektor.
- **Fix**:
  ```js
  panel.innerHTML = (typeof DOMPurify !== 'undefined')
      ? DOMPurify.sanitize(html, {
          ADD_ATTR: ['target', 'rel'],
          FORBID_TAGS: ['script', 'iframe', 'style'],
          FORBID_ATTR: ['onclick','onerror','onload','onmouseover','onfocus','onblur','onchange','onsubmit','formaction'],
          ALLOWED_URI_REGEXP: /^(?:(?:https?|mailto):|\/api\/)/i,
        })
      : '';   // Fail-Closed, nie raw-HTML
  ```
- **Followup**: Module sollen `data-action`-Attribute statt inline `onclick` nutzen (Pattern existiert bereits in [frontend/features/agents.js:67-72](frontend/features/agents.js#L67-L72)).

### P0-2 — `/api/secrets/*` komplett ohne Auth/Admin-Guard
- **Datei**: [backend/api/routes_secrets.py:40-95](backend/api/routes_secrets.py#L40-L95) (alle 5 Endpoints: GET /, POST /, GET /{key}, DELETE /{key}, GET /health/check)
- **Risiko**: Unauthentifizierter Angreifer kann Secrets listen, überschreiben, löschen → vollständige Plattform-Kompromittierung.
- **Fix**: Router-Level-Dependency:
  ```python
  router = APIRouter(prefix="/api/secrets", tags=["Secrets"],
                     dependencies=[Depends(require_admin)])
  ```

### P0-3 — Defekte Secret-Redaction im `_StatusEmitter`
- **Datei**: [backend/agents/base_agent.py:191-204](backend/agents/base_agent.py#L191-L204)
- **Risiko**: Regex-Pattern `rf'("{key}"\\s*:\\s*)"[^"]+"'` enthält doppelt-escapte `\\s` — matcht nie. **Tokens/Passwörter werden ungekürzt ins Tool-End-Event ans Frontend gestreamt.**
- **Fix**: `\\s` → `\s` (rf-string mit raw-Backslash ist hier korrekt: ein Backslash genügt).

### P0-4 — Vault: Silent-None bei `InvalidToken` → Auth-Bypass in Modulen
- **Datei**: [backend/core/vault.py:280-288](backend/core/vault.py#L280-L288)
- **Risiko**: `_get_sqlite_secret` gibt bei Decrypt-Fehler `None` zurück statt zu raisen. Module, die `vault.get_secret(...)` ohne None-Check verwenden, gehen mit fehlendem Token weiter (unauth Connections, fehlende Auth-Header).
- **Fix**:
  ```python
  # statt logger.warning + return None:
  raise InvalidToken(
      f"Secret '{key}' kann nicht entschlüsselt werden. "
      "Manuelle Re-Einstellung erforderlich."
  )
  ```

### P0-5 — Vault V1-Crypto: SHA256-Hash ohne Salt
- **Datei**: [backend/core/vault.py:118-121](backend/core/vault.py#L118-L121), [vault.py:186-195](backend/core/vault.py#L186-L195)
- **Risiko**: Bei Backup-Leak ist Offline-Bruteforce gegen V1-Secrets trivial (Rainbow-Tables/Wordlist).
- **Fix**: Startup-Sweep, der alle V1-Secrets aktiv mit aktuellem PBKDF2-Key re-encryptiert. Nach Ablauf einer Migrationsperiode (z. B. 30 Tage) den `_v1_fernet`-Pfad entfernen.

### P0-6 — Race-Condition + State-Loss im Safeguard-Resume
- **Dateien**:
  - [backend/agents/base_agent.py:505-507](backend/agents/base_agent.py#L505-L507) (Lock-Eviction kann gehaltene Locks ersetzen)
  - [backend/agents/base_agent.py:1054-1066](backend/agents/base_agent.py#L1054-L1066) (R-M-W zwischen `_paused_sg_agents` und Redis ohne Atomarität)
- **Risiko**: Pod-Restart zwischen In-Memory-Set und Redis-Set → nicht-resumierbare Tool-Calls oder Resume ins Leere.
- **Fix**:
  - Lock-Akquisition + setdefault-Atomar: `_safeguard_session_locks.setdefault(session_id, asyncio.Lock())`
  - Reihenfolge umdrehen: Redis-Key VOR In-Memory-Dict setzen.
  - Cleanup im Exception-Pfad ergänzen ([base_agent.py:1143-1150](backend/agents/base_agent.py#L1143-L1150)).

### P0-7 — Workflow-Engine ohne Crash-Recovery
- **Datei**: [backend/core/workflow_engine.py](backend/core/workflow_engine.py) (975 LOC)
- **Risiko**: Nach Backend-Crash bleiben `status: running` Workflows in Redis hängen — keine Sweep-Task, keine Resume-Logik, keine Heartbeats. BFS-`visited` ist lokal.
- **Fix** (Stage 1 — Sweeper): Startup-Task in `main.py`:
  ```python
  async def sweep_orphan_workflow_runs() -> None:
      cutoff = datetime.now(UTC) - timedelta(minutes=10)
      # alle Runs mit status=running, last_heartbeat < cutoff → status=interrupted
  ```
- **Fix** (Stage 2 — Resume): `visited` und `queue` nach Redis persistieren; Resume-Pfad implementieren.

---

## P1 — Kurzfristig (High, in dieser Woche)

### Backend / Async / Resource-Leaks

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P1-1 | Blanket `except Exception` mit `str(exc)`-Leak | [orchestrator.py:715-717](backend/agents/orchestrator.py#L715-L717) | Sanitisieren wie `execution.py:309-317` |
| P1-2 | `token_queue` ohne `maxsize`, Busy-Polling 0.05s | [routes_chat.py:118-120](backend/api/routes_chat.py#L118-L120), [routes_chat.py:339](backend/api/routes_chat.py#L339) | `asyncio.Queue(maxsize=1000)` + Producer/Consumer mit Cancellation statt Polling |
| P1-3 | `_queues` (Status-Bus) ohne TTL/Cap, nicht race-frei | [core/status_bus.py:18](backend/core/status_bus.py#L18), [status_bus.py:90-94](backend/core/status_bus.py#L90-L94) | Lock um `get_queue`, TTL-Sweeper auf Session-`last_emit_at` |
| P1-4 | Server-Log enthält ungekürzte Exception-Strings (Tokens) | [middleware/execution.py:309-318](backend/agents/middleware/execution.py#L309-L318) | `_mask_sensitive_args`-Redactor vor `logger.error`, `exc_info=False` |
| P1-5 | SSE-Stream-Handler: kein `current_tx_id`-Cleanup im Error-Pfad | [routes_chat.py:497-509](backend/api/routes_chat.py#L497-L509) | `try/finally` mit Cleanup |
| P1-6 | Cache-Scan O(N) Redis-Roundtrips | [orchestrator.py:554-561](backend/agents/orchestrator.py#L554-L561) | `MGET` statt N×GET; oder eingebauter SCAN+LIMIT |

### Security

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P1-7 | `bootstrap_admin` ungeschützt bei `API_AUTH_ENABLED=False` | [routes_auth.py:495-514](backend/api/routes_auth.py#L495-L514) | IP-Whitelist (Loopback) oder `X-Bootstrap-Token` Env-Secret |
| P1-8 | Prompt-Injection-Prefilter nur EN/DE | [core/safeguard.py:745-775](backend/core/safeguard.py#L745-L775) | FR/ES/IT/PT/NL/PL/ZH/JA-Patterns ergänzen, `detect_prompt_injection=True` als Default in `moderate` |
| P1-9 | API-Token-Response ohne `Cache-Control: no-store` und `response_model` | [routes_auth.py:784-790](backend/api/routes_auth.py#L784-L790) | Header setzen, `token: SecretStr` |
| P1-10 | Audit-Log mit ungeschütztem User-Input → Log-Forging | [safeguard.py:1149-1166](backend/core/safeguard.py#L1149-L1166) | Bei Anzeige escapen; Output-Side dokumentieren |
| P1-11 | `SQLITE_DB_PATH` hartkodiert | [vault.py:49](backend/core/vault.py#L49) | Aus `core.config.get_settings()` |

### Frontend

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P1-12 | Fallback `: html` wenn DOMPurify fehlt → Fail-Open | [app.js:582](frontend/app.js#L582), [app.js:3319](frontend/app.js#L3319) | Fail-Closed: `_escapeHtml(text)` im else-Zweig |
| P1-13 | Marked-Output ohne DOMPurify im else-Zweig | [app.js:3315-3319](frontend/app.js#L3315-L3319) | Wenn DOMPurify fehlt, `_escapeHtml` statt `marked.parse` |
| P1-14 | EventSource ohne `try/finally`-Close | [app.js:1417-1440](frontend/app.js#L1417-L1440) | Zentrale `_activeStream`-Ref, `finally { close() }` |

### API Contracts

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P1-15 | 12× `body: dict` ohne Pydantic-Schema | [routes_settings.py:1492](backend/api/routes_settings.py#L1492) (TTS), [routes_settings.py:1588](backend/api/routes_settings.py#L1588) (STT), [routes_settings.py:1658](backend/api/routes_settings.py#L1658) (OCR), [routes_chat.py:917-945](backend/api/routes_chat.py#L917-L945) (history), [routes_chat.py:959-965](backend/api/routes_chat.py#L959-L965) (ui-history), ua. | Konkrete Pydantic-Modelle; siehe Schema-Vorschläge unten |
| P1-16 | `routes_auth.py`: 24 Endpoints, 0% `response_model` | [routes_auth.py](backend/api/routes_auth.py) | `LoginResponse`, `MeResponse`, `UserSanitized`, `RoleListResponse`, `GroupListResponse`, `ApiTokenCreateResponse` |
| P1-17 | `GET /api/logs` lädt 10k Einträge in Memory | [routes_logs.py:41](backend/api/routes_logs.py#L41) | Server-side filter, cursor-Pagination |
| P1-18 | Sync `subprocess.run` in async Endpoint | [routes_tts.py:125](backend/api/routes_tts.py#L125), [routes_tts.py:168-208](backend/api/routes_tts.py#L168-L208) | `asyncio.create_subprocess_exec` oder `asyncio.to_thread` |

---

## P2 — Mittelfristig (Medium, in den nächsten 2-4 Wochen)

### Backend & Architektur

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P2-1 | Hardcoded Modul-Imports in Core | [orchestrator.py:262](backend/agents/orchestrator.py#L262), [workflow_engine.py:536](backend/core/workflow_engine.py#L536), [script_tools.py:151](backend/agents/script_tools.py#L151) | `registry.get_tool("modul", "tool")` |
| P2-2 | Orchestrator-Monolith 2804 LOC | [orchestrator.py](backend/agents/orchestrator.py) | Split: `routing/{keyword,embedding,function_calling,cache,intent}.py`, Orchestrator als Coordinator ~300 LOC |
| P2-3 | BaseAgent 1250 LOC, Tuple-Return fragil | [base_agent.py](backend/agents/base_agent.py) | `InvokeResult`-Dataclass; Context-Compaction als Middleware; `_StatusEmitter`/`_sg_loop` in eigenes Modul |
| P2-4 | `_paused_sg_agents` Module-Level ohne Cleanup-Task | [base_agent.py:401-402](backend/agents/base_agent.py#L401-L402) | Async-Cleanup-Coroutine in `main.py` Startup |
| P2-5 | Pool-Encapsulation-Bruch (`pool._meta`) | [orchestrator.py:988](backend/agents/orchestrator.py#L988) | Public API auf `DynamicAgentPool` |
| P2-6 | String-Matching auf LangGraph-Errortext | [middleware/execution.py:286-318](backend/agents/middleware/execution.py#L286-L318) | `langgraph.errors.GraphRecursionError` per Typ |
| P2-7 | Vault: 440-LOC-Klasse, Logik-Duplikation | [vault.py](backend/core/vault.py) | `FernetCipher` extrahieren; `VAULT_DISABLE_LEGACY_KEYS`-Flag nach abgeschlossener Migration |
| P2-8 | IP-basierte Login-Rate-Limit-Schicht fehlt | [routes_auth.py:45-73](backend/api/routes_auth.py#L45-L73) | Globaler Bucket pro IP + 401 statt 429 bei unbekanntem Username (gegen Enumeration) |
| P2-9 | Salt-Trennung pro Instance fehlt | [vault.py:101-116](backend/core/vault.py#L101-L116) | `INSTANCE_ID`-Salt beim ersten Start zufällig erzeugen und persistieren |

### Frontend

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P2-10 | WebSocket-Reconnect ohne Timer-Cleanup | [app.js:3506-3510](frontend/app.js#L3506-L3510) | `clearTimeout(this._reconnectTimer)` vor `setTimeout`; `disconnectWebSocket()`-Methode |
| P2-11 | Globale `document`-Listener ohne Remove im SPA-Lebenszyklus | [app.js:194](frontend/app.js#L194), [app.js:317](frontend/app.js#L317), [app.js:325](frontend/app.js#L325), [app.js:403](frontend/app.js#L403), [app.js:413](frontend/app.js#L413), [app.js:1258](frontend/app.js#L1258), [app.js:1262](frontend/app.js#L1262) | Idempotenz-Flag `_listenersBound`; `{once:true}` wo möglich |

### API Contracts

| ID | Befund | Datei | Fix |
|---|---|---|---|
| P2-12 | Schemas ohne `extra="forbid"` (alle 60 Klassen) | `backend/schemas/` | Globaler `NinkoModel`-Mixin: |
| P2-13 | Kein einheitliches Error-Schema | API-weit | `ErrorResponse(error, code, request_id)` + globaler `HTTPException`-Handler |
| P2-14 | Keine standardisierte Pagination | `routes_logs.py`, `routes_safeguard_audit.py`, `routes_audit.py`, `routes_operations.py` | Generischer `Page[T]`-Helper: `items, total, limit, offset, has_more` |
| P2-15 | `routes_alerts.py` leakt `exc`-String in detail | [routes_alerts.py:21-50](backend/api/routes_alerts.py#L21-L50) | Generische Fehlermeldung, exc nur loggen |
| P2-16 | `routes_modules.py` Module-Frontend-Bypass ohne RBAC | [routes_modules.py:96-162](backend/api/routes_modules.py#L96-L162) | Auth-Check ergänzen |
| P2-17 | `ScheduledTaskCreate.cron` ohne `field_validator` | [schemas/scheduler.py:13-25](backend/schemas/scheduler.py#L13-L25) | Validator in Schema, nicht in Route |
| P2-18 | `schemas/secret.py:value` ohne `max_length` | [schemas/secret.py:9](backend/schemas/secret.py#L9) | `max_length=10_000` |
| P2-19 | `schemas/module.py:status: str` (kein Literal) | [schemas/module.py:27](backend/schemas/module.py#L27) | `Literal["ok","error","degraded","unknown"]` |
| P2-20 | `datetime`-Felder als `Optional[str]` | [schemas/agents.py:32-43](backend/schemas/agents.py#L32-L43), [schemas/workflows.py:91-103](backend/schemas/workflows.py#L91-L103) | `datetime` mit ISO-Serializer |
| P2-21 | Knowledge-Graph: `limit` ohne `Query(le=)` | [routes_knowledge_graph.py:129-147](backend/api/routes_knowledge_graph.py#L129-L147) | `limit: int = Query(100, ge=1, le=1000)` |
| P2-22 | Themes: Repo-ID als Query statt Path | [routes_themes.py:312](backend/api/routes_themes.py#L312) | `POST /repos/{repo_id}/themes/{theme_id}/install` |

### Globaler `NinkoModel`-Mixin (P2-12)

```python
# backend/schemas/__init__.py
from pydantic import BaseModel, ConfigDict

class NinkoModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
```
Alle vorhandenen Schemas davon ableiten (60 Klassen).

### Einheitliches Error-Schema (P2-13)

```python
# backend/schemas/errors.py
class ErrorResponse(NinkoModel):
    error: str
    code: str
    request_id: str | None = None

# backend/main.py
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(error=exc.detail, code=f"HTTP_{exc.status_code}",
                              request_id=request.headers.get("x-request-id")).model_dump(),
    )
```

---

## P3 — Langfristig (Low / Refactoring)

| ID | Befund | Datei |
|---|---|---|
| P3-1 | Memory-System ohne Tenant-Isolation in `where_filter` | [core/memory.py](backend/core/memory.py) |
| P3-2 | Skill/Memory-Magic-Numbers (`_MATCH_THRESHOLD=0.12`, `decay_lambda=0.05`) | [skills_manager.py](backend/core/skills_manager.py), [memory.py](backend/core/memory.py) |
| P3-3 | `re.sub` für `<think>...</think>` dupliziert | [orchestrator.py:1208](backend/agents/orchestrator.py#L1208) (vs `base_agent._strip_thinking`) |
| P3-4 | Toter Code: `if TYPE_CHECKING: pass`, ungenutztes `result = {}` | [execution.py:14-15](backend/agents/middleware/execution.py#L14-L15), [execution.py:53-54](backend/agents/middleware/execution.py#L53-L54) |
| P3-5 | Polling-Interval als Magic Number | [routes_chat.py:339](backend/api/routes_chat.py#L339) |
| P3-6 | OpenAPI-Tags inkonsistent (case/number) | API-weit |
| P3-7 | Mix `Optional[X]` vs `X \| None` | API-weit |
| P3-8 | `@router.deprecated(True)` auf Legacy-Toggles | [routes_safeguard.py](backend/api/routes_safeguard.py) |
| P3-9 | `samesite` Cookie-Mismatch beim Logout | [routes_auth.py:347](backend/api/routes_auth.py#L347) |
| P3-10 | `routes_modules.py`: Duplicate Route Decoration | [routes_modules.py:40-41](backend/api/routes_modules.py#L40-L41) |
| P3-11 | `atexit.register` für asyncio-Cleanup macht wenig Sinn | [base_agent.py:401-402](backend/agents/base_agent.py#L401-L402) |
| P3-12 | Drag-Listener auf jedem `_renderAgentSteps` neu | [frontend/features/agents.js:760-776](frontend/features/agents.js#L760-L776) |
| P3-13 | Post-Sanitize `.replace(/<a /g, ...)` fragil | [app.js:3320](frontend/app.js#L3320), [app.js:3473](frontend/app.js#L3473) | DOMPurify `addHook('afterSanitizeAttributes', ...)` |
| P3-14 | `data:image/webp` in `ALLOWED_URI_REGEXP` (Polyglot-Risiko) | [app.js:3319](frontend/app.js#L3319) |
| P3-15 | Magic-Numbers in Konstanten (`_REPLACE_HISTORY_MAX_MESSAGES`, `_MAX_PLUGIN_FILES`, `MAX_LOG_ENTRIES`) | Verschiedene | → `core/config.py` Settings |

---

## Architektur — Top-3 Stärken (nicht anfassen)

1. **Middleware-Chain** ([backend/agents/middleware/](backend/agents/middleware/)) — Priority-Bänder (0-99 System / 100-199 Prompt / 400-499 Execution / 500-599 Post), deterministische Sortierung, Short-Circuit-Semantik, Duplicate-Guard. Vorbild für andere Module.
2. **Skills/Soul/Memory-Trennung** ([core/memory.py](backend/core/memory.py), [core/soul_manager.py](backend/core/soul_manager.py), [core/skills_manager.py](backend/core/skills_manager.py)) — WER/WIE/WAS klar getrennt, in jedem File-Header dokumentiert.
3. **Dynamic Agent Pool** ([core/agent_pool.py](backend/core/agent_pool.py)) — LRU-Eviction (200), Inverted-Token-Index O(token), Tenant-Scoping mit Legacy-Migration, Locks gegen Race-Conditions.

---

## Umsetzungsreihenfolge (empfohlen)

### Sprint 1 — P0-Block (1-2 Tage)
1. **P0-1** DOMPurify `onclick` raus (~10 min)
2. **P0-2** `/api/secrets/*` mit `Depends(require_admin)` (~10 min)
3. **P0-3** Secret-Redaction Regex-Fix (~5 min)
4. **P0-4** Vault Silent-None → raise (~5 min)
5. **P0-6** Safeguard-Resume Race-Fix (~1 h)
6. **P0-7-stage-1** Workflow-Sweeper (~2 h)
7. **P0-5** V1-Crypto Migrationssweep (~2 h)

**Verifikation**: Smoke-Test via `k8s-smoke-test`-Skill nach jedem Fix.

### Sprint 2 — P1-Block (3-5 Tage)
- Backend: Resource-Leaks (Queue/Status-Bus), Log-Redactor, Cache-Scan-Fix
- Security: Bootstrap-IP-Whitelist, Multi-Lang-Injection-Patterns
- Frontend: Fail-Closed DOMPurify-Fallback, EventSource-Cleanup
- API: 12× `body: dict` → Pydantic, `routes_auth.py` response_models, Logs-Pagination, TTS Sync-Subprocess

### Sprint 3 — P2-Block (2-4 Wochen)
- Architektur-Refactors (Orchestrator-Split, BaseAgent-Modularisierung)
- Hardcoded Modul-Imports raus
- `NinkoModel`-Mixin global ausrollen
- Einheitliches Error-Schema + Pagination-Helper

### Backlog — P3
- Niedrige Prio; bei Touch der jeweiligen Datei mitnehmen.

---

## Verifikations-Strategie

Pro Fix:
1. **Unit-Test** schreiben, der den Bug ohne Fix reproduziert (Karpathy-Prinzip 4, siehe `.claude/rules/workflow.md`)
2. **Lokaler Smoke-Test** via `docker compose build backend && docker compose up -d --no-deps backend`
3. **K8s-Smoke-Test** nach Prod-Deploy via `k8s-smoke-test`-Skill

Spezifisch:
- **P0-1 (XSS)**: Modul mit `<button onclick="alert(1)">` versuchen → muss strip
- **P0-2 (Secrets)**: `curl -X GET http://localhost:8000/api/secrets/` ohne Auth → muss 401
- **P0-3 (Redaction)**: Tool mit Token im Output triggern → SSE-Stream darf Token nicht enthalten
- **P0-7 (Workflow)**: Container kill mid-workflow → Sweeper markiert als `interrupted`

---

## Offene Risiken / Nicht im Scope

- **`core/auth.py`**: Constant-Time-Compare bei API-Token-Hashes nicht verifiziert (Out-of-Scope-Hinweis aus M-4 des Security-Audits). → Folge-Review.
- **`routes_safeguard.py`**: Aufruf von `set_active_profile` ohne Admin-Guard möglich? Nicht im Scope geprüft. → Folge-Review.
- **`SECRET_KEY_PATTERN`**: Muss verifizieren, dass `..` und `/` ausgeschlossen sind (Path-Traversal in Vault-Path-Konstruktion). → Quick-Check in [schemas/secret.py](backend/schemas/secret.py).

---

## Memory-Notizen (für künftige Sessions)

Folgende Erkenntnisse sind in `.claude/memory/` zu sichern (separater `/sync-memory`-Lauf empfohlen):

1. **DOMPurify-Whitelist-Falle**: `ADD_ATTR: ['onclick', ...]` ist ein Anti-Pattern — immer `FORBID_ATTR` für `on*`-Handler setzen (feedback_code_style).
2. **Vault-Silent-None ist Auth-Bypass**: Module, die `vault.get_secret()` aufrufen, MÜSSEN None checken — sonst stille Auth-Degradation (project_ninko_gotchas).
3. **Safeguard-Redaction-Regex**: rf-strings + Backslashes sind tricky — `rf"\\s"` ist 2 Zeichen, nicht ein Whitespace-Matcher (project_ninko_gotchas).
4. **Tuple-Return aus `BaseAgent.invoke()`** und `Orchestrator.route()` ist eine wiederkehrende Falle — kandidaten für Dataclass-Refactor (project_ninko_arch).

---

## Quellen

- Vollständiger Review-Report: [.claude/reports/full-review-2026-05-20.md](.claude/reports/full-review-2026-05-20.md)
- Vorgänger (abgeschlossen): Canonical-English-Prompts-Migration (siehe `.claude/rules/prompt-konventionen.md`)
