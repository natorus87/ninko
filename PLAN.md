# Plan: Core-Agent-, Routes- und Safeguard-Pruefung

## Ziel

Core-Agent-Module, zentrale API-Routes und der Safeguard-Mechanismus wurden auf Funktionalitaet, Logikfehler, Integrationsprobleme und Sicherheitsrisiken geprueft. Dieses Dokument ersetzt den alten Plan und haelt den aktuellen Befund, die bereits umgesetzten Fixes, offene Risiken und sinnvolle naechste Tests fest.

## Gepruefte Bereiche

- `backend/api/routes_chat.py`
- `backend/api/routes_agents.py`
- `backend/api/routes_safeguard.py`
- `backend/api/routes_safeguard_profiles.py`
- `backend/api/routes_modules.py`
- `backend/api/routes_routing.py`
- `backend/api/routes_subagent.py`
- `backend/api/routes_workflows.py`
- `backend/api/routes_secrets.py`
- `backend/agents/base_agent.py`
- `backend/agents/orchestrator.py`
- `backend/agents/core_tools.py`
- `backend/agents/alert_tools.py`
- `backend/agents/script_tools.py`
- `backend/agents/middleware/execution.py`
- `backend/main.py`
- `backend/core/safeguard.py`
- `backend/core/safeguard_profiles.py`
- `backend/core/tool_registry.py`
- `backend/core/operation_journal.py`
- `backend/core/api_security_policy.py`
- `backend/modules/message_hub/workers/email_worker.py`

## Architekturueberblick

### Chat-Datenfluss

1. `POST /api/chat/` nimmt `ChatRequest` entgegen.
2. Session-ID wird tenant-gescoped: `tenant_id:session_id`.
3. User-Message-Safeguard laeuft vor Routing, ausser `confirmed=true`.
4. Chat-History wird aus Redis geladen.
5. `OrchestratorAgent.route()` entscheidet per Function Calling oder Fallback.
6. Modul-Agenten werden ueber `BaseAgent.invoke()` ausgefuehrt.
7. Tool-Level-Safeguard kann vor Tool-Execution pausieren.
8. Pending Tool-Call wird in Redis unter `ninko:safeguard_tool_pending:{tenant:session}` gespeichert.
9. `confirmed=true` resumiert ueber `orchestrator.resume_tool_execution()`.
10. Antwort, Audit und Operation Journal werden geschrieben.

### Safeguard-Datenfluss

- User-Message-Safeguard: `SafeguardMiddleware.check()`.
- Tool-Call-Safeguard: `SafeguardMiddleware.check_tool_call()`.
- Profilauflösung: Chat-Profil > Agent-Profil > Legacy-Agent-Toggle > globales Profil > `moderate`.
- Bekannte Tools werden deterministisch ueber `ToolRegistry` und `ToolTier` klassifiziert.
- Unbekannte Tools fallen auf LLM-Klassifikation zurueck.
- Classifier-Ausfall ist standardmaessig fail-safe, ausser ein Profil setzt `fail_open=True`.

### Tool-Tiers

- `READONLY`: keine Bestaetigung.
- `COMMUNICATE`: externe Kommunikation, Audit auch ohne Bestaetigung.
- `WRITE_DATA`: Daten werden erstellt/geaendert.
- `WRITE_SYSTEM`: System-/Infrastrukturzustand wird geaendert.
- `ADMIN`: destruktiv oder irreversibel.

## Behobene Probleme

### 1. Agent-Routen wurden durch `/{agent_id}` verschattet

- Datei: `backend/api/routes_agents.py`
- Problem: `GET /api/agents/templates` und `GET /api/agents/cards` standen hinter `GET /api/agents/{agent_id}`.
- Auswirkung: FastAPI interpretierte `templates` und `cards` als Agent-IDs; die Endpunkte konnten 404 liefern.
- Schweregrad: Mittel
- Fix: Statische GET-Routen vor `/{agent_id}` verschoben.
- Verifikation: Statischer Route-Order-Check bestanden.

### 2. Tool-Safeguard-Pending im Chat-Journal war ungescoped

- Datei: `backend/api/routes_chat.py`
- Problem: Im JSON-Pfad wurde ein Tool-Safeguard-Pending mit `body.session_id` ins Operation Journal geschrieben, waehrend Resume/Lookup `tenant:session` nutzt.
- Auswirkung: Falsche Pending-Zuordnung, fehlerhafte Journal-/Audit-Korrelation, moegliche Tenant-Kollisionen.
- Schweregrad: Hoch
- Fix: `session_id=scoped_session_id`.
- Verifikation: Statischer Scoping-Check bestanden.

### 3. Chat-spezifische Safeguard-Profile wurden falsch gescoped

- Datei: `backend/api/routes_safeguard.py`
- Problem: Profil-API schrieb `ninko:safeguard:profile:chat:{session}`, der Chat-Safeguard las aber `ninko:safeguard:profile:chat:{tenant}:{session}`.
- Auswirkung: Chat-Profile wirkten im Chat nicht zuverlaessig und konnten tenant-uebergreifend kollidieren.
- Schweregrad: Hoch
- Fix: `GET/POST/DELETE /api/safeguard/chats/{session_id}/profile` nutzen jetzt dieselbe Tenant-Session-ID wie `routes_chat.py`.
- Verifikation: Statischer Scoping-Check bestanden.

### 4. Legacy-Per-Agent-Safeguard-Toggle wurde ignoriert

- Datei: `backend/core/safeguard.py`
- Problem: `enable_for_agent()` / `disable_for_agent()` speicherten `safeguard_enabled`, aber `resolve_profile()` wertete diesen Wert nicht aus.
- Auswirkung: API meldete Erfolg, der Agent blieb aber faktisch auf globalem Profil.
- Schweregrad: Hoch
- Fix: `resolve_profile()` wertet Legacy-Toggle nach Agent-Profil und vor Global-Profil aus.
- Verhalten:
  - `safeguard_enabled=False` -> `disabled`
  - `safeguard_enabled=True` bei global `disabled` -> `moderate`
- Verifikation: Statischer Check bestanden.

### 5. Core-Tools fehlten in der Tool-Registry

- Datei: `backend/core/tool_registry.py`
- Problem: Mehrere echte `@tool`-Funktionen waren nicht explizit registriert, u.a.:
  - `execute_cli_command`
  - `call_module_agent`
  - `create_task`
  - `stop_task`
  - `configure_routing`
  - `get_routing_info`
  - `wait`
  - `speak`
  - `generate_pdf_report`
  - `kg_find_related`
  - `kg_find_path`
  - `kg_analyze_dependencies`
  - `kg_record_incident`
  - `record_alert`
  - `resolve_alert`
  - `run_script_tool`
  - `list_script_tools`
- Auswirkung: Unbekannte Tools fielen auf LLM-Klassifikation zurueck. Das ist fail-safe, aber langsam, fragil und bei Classifier-Ausfall stoerend.
- Schweregrad: Mittel
- Fix: Fehlende Core-Tools mit expliziten Tiers registriert.
- Verifikation: Tool-Coverage-Check: keine echten `@tool`-Funktionen mehr unregistriert, ausser Template-Beispiele.

### 6. `read_*`-Tools wurden nicht als read-only erkannt

- Datei: `backend/core/tool_registry.py`
- Problem: `_infer_readonly()` kannte `read_` nicht.
- Auswirkung: `read_mcp_server_resource` wurde konservativ als schreibend eingestuft.
- Schweregrad: Mittel
- Fix: `read_` in Readonly-Prefixes aufgenommen.
- Verifikation: `read_mcp_server_resource` klassifiziert jetzt als `READONLY`.

### 7. Alte `_infer_tier()`-Aufrufe konnten Runtime-Fehler ausloesen

- Datei: `backend/core/tool_registry.py`
- Problem: `ToolSpec.from_metadata()` und `get_or_infer_tool_spec()` riefen `_infer_tier()` mit alter Signatur auf.
- Auswirkung: Bei Nutzung dieser Hilfen waere `TypeError` moeglich.
- Schweregrad: Mittel
- Fix: Aufrufe auf aktuelle Signatur angepasst:
  - `_infer_tier(meta.name, meta.readonly, meta.destructive)`
  - `_infer_tier(name, _infer_readonly(name), _infer_destructive(name))`
- Verifikation: Direkter Runtime-Check gegen `ToolSpec.from_metadata()` und `get_or_infer_tool_spec()` bestanden.

### 8. Email-Worker crashte bei fehlendem Vault-Secret

- Datei: `backend/modules/message_hub/workers/email_worker.py`
- Problem: `vault.get_secret()` kann `None` liefern. Dieser Wert wurde direkt an `imaplib.login()` uebergeben.
- Auswirkung: Wiederholter Worker-Crash mit `AttributeError: 'NoneType' object has no attribute 'replace'`.
- Schweregrad: Mittel
- Fix:
  - Fehlende Secrets werden auf `""` normalisiert.
  - Unvollstaendige IMAP-Konfigurationen werden vor dem Verbindungsaufbau erkannt.
  - Nicht unterstuetzte Auth-Typen werden kontrolliert als "nicht konfiguriert" behandelt.
- Verifikation:
  - Container-Compile bestanden.
  - Kubernetes-Log-Nachlauf zeigt kontrollierte Meldung `IMAP-Verbindung unvollständig konfiguriert`.
  - Keine `email-Worker Fehler` / `NoneType`-Crashes mehr im Nachlauf.

### 9. HTTPX-INFO-Logs konnten Secrets in URLs offenlegen

- Datei: `backend/main.py`
- Problem: `httpx` loggte vollstaendige Request-URLs auf INFO-Level. Bei URL-basierten APIs koennen darin Tokens stehen.
- Auswirkung: Credential-Leak in Container- und Redis-Logs.
- Schweregrad: Hoch
- Fix:
  - Zentraler `SecretRedactionFilter` fuer Console- und Redis-Loghandler.
  - Redaction fuer Telegram-Bot-URLs, bekannte Secret-Query-Parameter und Bearer-Tokens.
  - `httpx` und `httpcore` auf `WARNING` gesetzt, damit erfolgreiche Request-URLs nicht auf INFO erscheinen.
- Verifikation:
  - Isolierter Redaction-Test bestanden.
  - Kubernetes-Log-Nachlauf zeigt keine `HTTP Request:`-INFO-Zeilen und keine Telegram-Bot-URL-Leaks mehr.

## Verifikation

### Erfolgreich

```bash
python3 -m compileall -q backend/agents backend/api backend/core
```

Weitere erfolgreiche statische Checks:

- Agent-Route-Order-Check.
- Chat-Tool-Pending-Scoping-Check.
- Safeguard-Chat-Profil-Scoping-Check.
- Legacy-Agent-Toggle-Resolution-Check.
- Tool-Registry-Tier-Check.
- Tool-Coverage-Check fuer echte `@tool`-Funktionen.
- Readlike-Tool-Tier-Check.
- Email-Worker-Config-Guard-Check.
- Log-Redaction-Pattern-Check.

### Deployment-Verifikation

Das Backend wurde neu gebaut, gepusht und in Kubernetes ausgerollt.

Image-Digest:

```text
docker.io/natorus87/ninko-backend@sha256:dd7a0f1124e88b4691d048bd623e63dea920361a7c025afee40d32bb79af8f7d
```

Erfolgreiche Checks im Deployment:

- `kubectl rollout status deployment/ninko-backend -n ninko --timeout=180s`
- Pod `1/1 Running`, Restart-Count `0`
- In-Container-Compile fuer `/app/main.py` und `/app/modules/message_hub/workers/email_worker.py`
- Marker-Check fuer Email-Worker-Fix und Log-Redaction-Fix
- `GET /health` im Pod liefert `200` mit `{"status":"ok","service":"ninko","version":"1.3.4"}`
- Log-Nachlauf ueber mehrere Worker-Zyklen:
  - keine `NoneType`-Crashes
  - keine `email-Worker Fehler`
  - keine `HTTP Request:`-INFO-Logs
  - keine Telegram-Bot-URL-Leaks

### Nicht erfolgreich ausfuehrbar

Pytest konnte in der aktuellen lokalen Umgebung nicht laufen, weil `fastapi` fehlt.

Betroffene Kommandos:

```bash
pytest -q backend/tests/test_api_security_policy.py backend/tests/test_chat_streaming.py backend/tests/test_agents_integration.py
.venv/bin/python -m pytest -q backend/tests/test_api_security_policy.py backend/tests/test_chat_streaming.py backend/tests/test_agents_integration.py
```

Fehler:

```text
ModuleNotFoundError: No module named 'fastapi'
```

Bewertung: Das ist ein Environment-/Dependency-Problem, kein durch die aktuellen Fixes verursachter Testfehler. Die Tests scheitern bereits bei Collection.

## Offene Risiken

### 1. Authentifizierte API-/E2E-Verifikation fehlt noch

Deployment-Smoke-Checks sind sauber, aber authentifizierte Funktionsfluesse wurden noch nicht vollstaendig gegen das laufende System ausgefuehrt.

Noch zu pruefen:

- `POST /api/chat/` mit destruktiver Anfrage.
- `confirmed=true` Resume fuer Tool-Level-Safeguard.
- `POST /api/safeguard/chats/{session}/profile` und anschliessender Chat mit derselben Session.
- Tool-Safeguard bei Modul-Agenten.
- SSE-Pfad und JSON-Pfad im Vergleich.

### 2. Plugin-/Custom-Tool-Tiers bleiben ein Hardening-Thema

Die Registry deckt vorhandene Tools ab. Fuer zukuenftige Plugins bleibt aber ein architekturelles Risiko:

- Plugin-Code kann Tool-Namen und `TOOL_REGISTRY_OVERRIDES` beeinflussen.
- Falsche `readonly=True`-Overrides koennten ein Tool zu niedrig einstufen.

Empfehlung:

- Plugin-Installationspfad sollte Tool-Tiers validieren.
- Riskante Prefixes wie `delete_`, `restart_`, `execute_`, `run_`, `send_` sollten nicht per Plugin-Override auf `READONLY` herabgestuft werden duerfen, ausser eine Admin-Whitelist erlaubt es explizit.

### 3. `wait` ist aktuell `READONLY`

`wait` veraendert keinen externen Zustand, kann aber Agent-Laufzeit blockieren.

Aktuelle Einstufung:

- `READONLY`

Alternative:

- `WRITE_SYSTEM` oder dediziertes Rate-/Timeout-Limit, falls Blockierung als operatives Risiko bewertet wird.

### 4. User-Message-Safeguard prueft nur Initialmessage

Bekannter Architekturpunkt:

- Pipeline-Substeps werden nicht als neue User-Messages durch den User-Message-Safeguard geschickt.
- Tool-Level-Safeguard schuetzt bekannte Tool-Calls, aber Plan-/Task-Strings koennen weiterhin Prompt-Injection-artige Inhalte enthalten.

Empfehlung:

- Pipeline-Engine sollte fuer risikoreiche Step-Tasks optional `SafeguardMiddleware.check()` auf Step-Text ausfuehren.
- Mindestens Tests fuer Pipeline-Step-Bestaetigungen ergaenzen.

## Empfohlene Regressionstests

### Agent Routes

- `GET /api/agents/templates` liefert Templates und wird nicht als Agent-ID interpretiert.
- `GET /api/agents/cards` liefert Modul-Cards und wird nicht als Agent-ID interpretiert.

### Chat Safeguard

- Destruktive User-Message erzeugt `confirmation_required=True`.
- `confirmed=true` ohne Pending faellt nicht in falschen Resume-Pfad.
- Tool-Level-Safeguard erzeugt Pending unter `tenant:session`.
- Resume liest denselben Pending-Key und raeumt ihn danach auf.
- JSON- und SSE-Pfad verhalten sich gleich.

### Safeguard Profile

- Chat-Profil wird unter gescopter Session gespeichert.
- `resolve_profile(session_id="tenant:abc")` findet das ueber API gesetzte Profil fuer `abc`.
- `DELETE /api/safeguard/chats/{session}/profile` entfernt den gescopten Key.

### Per-Agent Safeguard

- `POST /api/safeguard/agents/{id}/disable` fuehrt bei `resolve_profile(agent_id=id)` zu `disabled`.
- `POST /api/safeguard/agents/{id}/enable` bei global `disabled` fuehrt zu `moderate`.
- Explizites Agent-Profil hat Vorrang vor Legacy-Toggle.

### Tool Registry

- Alle echten `@tool`-Funktionen sind registriert oder durch Discovery registrierbar.
- `execute_cli_command` ist `WRITE_SYSTEM`.
- `call_module_agent` ist `WRITE_SYSTEM`.
- `create_task` ist `WRITE_DATA`.
- `stop_task` ist `WRITE_SYSTEM`.
- `record_alert` und `resolve_alert` sind `WRITE_DATA`.
- `read_mcp_server_resource` ist `READONLY`.
- `ToolSpec.from_metadata()` und `get_or_infer_tool_spec()` werfen keinen `TypeError`.

## Naechste Schritte

1. Backend-Testumgebung reparieren:

```bash
cd backend
pip install -r requirements.txt
```

oder die vorgesehene Projekt-Testumgebung verwenden.

2. Regressionstests aus dem Abschnitt oben ergaenzen.

3. Relevante Tests laufen lassen:

```bash
pytest -q backend/tests/test_api_security_policy.py backend/tests/test_chat_streaming.py backend/tests/test_agents_integration.py
```

4. Danach einen echten lokalen Smoke-Test mit Redis/FastAPI durchfuehren:

```bash
docker compose up -d
```

5. Optionales Hardening fuer Plugin-Tool-Tiers planen.

## Aktueller Code-Stand

Geaenderte Dateien:

- `backend/api/routes_agents.py`
- `backend/api/routes_chat.py`
- `backend/api/routes_safeguard.py`
- `backend/main.py`
- `backend/core/safeguard.py`
- `backend/core/tool_registry.py`
- `backend/modules/message_hub/workers/email_worker.py`

Status:

- Konkrete gefundene Bugs sind behoben.
- Compile-, statische Verifikationen und Deployment-Smoke-Checks sind sauber.
- Authentifizierte E2E-Regressionstests bleiben offen.
- Pytest lokal bleibt wegen fehlender Dependencies offen.

## Commit-/Deployment-Abschluss

Stand vor Commit:

- Deployment erfolgreich auf `natorus87/ninko-backend:latest`.
- Aktiver Kubernetes-Image-Digest:

```text
docker.io/natorus87/ninko-backend@sha256:dd7a0f1124e88b4691d048bd623e63dea920361a7c025afee40d32bb79af8f7d
```

- Pod-Status: `1/1 Running`, Restart-Count `0`.
- Healthcheck im Pod: `GET /health` -> `200`.
- Log-Nachlauf: keine `NoneType`-Crashes, keine `email-Worker Fehler`, keine `HTTP Request:`-INFO-Logs und keine Telegram-Bot-URL-Leaks.
- Lokaler Diff-Check: `git diff --check` sauber.

Dieser Stand wird als ein zusammenhaengender Fix-Commit festgehalten.
