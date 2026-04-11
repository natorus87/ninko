# Plan: Alert-State-Tracking & Deduplication System

## TL;DR

> **Neues Core-Feature:** Redis-basiertes Alert-State-Tracking mit 4 neuen Tools zur Verhinderung von Duplicate-Notifications.
>
> **Problem gelöst:** Kubernetes Pod-Failure → Restart-Versuche → Email an Ticket-System → Workflow läuft wieder an → **KEINE** erneute Email dank Alert-State-Prüfung.
>
> **Deliverables:**
> - 4 neue Core-Tools: `check_alert_state`, `record_alert`, `resolve_alert`, `should_notify`
> - Redis-basierte State-Machine mit TTL-Support
> - Integration mit Knowledge Graph für Incident-Historie
> - Beispiel-Workflow für Kubernetes-Auto-Remediation
>
> **Estimated Effort:** Medium (4-6 Stunden)
> **Parallel Execution:** YES - 3 Waves
> **Critical Path:** Core Tools → Tests → Integration → Final QA

---

## Context

### Original Request

User möchte folgenden Workflow automatisieren:
1. Ninko überwacht Kubernetes Cluster
2. Pod-Failure wird erkannt
3. Mehrere Restart-Versuche schlagen fehl
4. Email wird an Ticket-System gesendet
5. Workflow läuft periodisch wieder an
6. **Problem:** Ohne Deduplication würden 100+ Emails über Tage gesendet

### Current Gap Analysis

**Was Ninko schon hat:**
- `remember_fact` / `recall_memory` → Speichert Fakten in ChromaDB (semantisch)
- `store_incident` → Speichert Incidents mit Kategorie
- Redis → Persistenter State für Workflows
- Knowledge Graph → Incident-Entities mit Beziehungen

**Was fehlt:**
- Keine strukturierte Alert-ID-basierte Deduplication
- Kein Zeit-basiertes "nicht erneut alarmieren" (z.B. 24h Cooldown)
- Kein Status-Management (active → acknowledged → resolved)
- Keine atomare "check-and-set" Operation vor dem Senden

### Metis Review

**Identified Gaps (addressed in this plan):**
1. Alert-ID-Schema muss deterministisch sein (module:resource:type)
2. Redis ist besser geeignet als ChromaDB für State-Tracking (schneller Key-Value Lookup)
3. TTL-Support für automatisches Cleanup vergessener Alerts
4. Integration mit `kg_record_incident()` für Langzeitanalyse

---

## Work Objectives

### Core Objective
Implementieren eines robusten Alert-State-Tracking-Systems mit deterministischer Deduplication, Zeit-basierter Unterdrückung und automatischer Resolution-Erkennung.

### Concrete Deliverables
- `backend/agents/alert_state_tools.py` - 4 neue Core-Tools
- Redis Key-Schema: `ninko:alerts:active:{alert_id}`, `ninko:alerts:history:{alert_id}`
- Integration in `orchestrator.py` Tool-Registry
- Beispiel-Skill: `kubernetes-smart-alerts` mit Deduplication-Pattern
- Frontend-Anzeige für aktive Alerts (optional)
- Tests: Unit + Integration + E2E

### Definition of Done
- [ ] `check_alert_state("k8s:nginx:pod-xyz:CrashLoopBackOff")` gibt korrekten Status zurück
- [ ] `should_notify()` verhindert Duplicates innerhalb 24h
- [ ] `resolve_alert()` markiert Alerts als gelöst
- [ ] Kubernetes-Workflow nutzt neue Tools
- [ ] Alle Tests passieren
- [ ] Dokumentation aktualisiert

### Must Have
- Alert-State in Redis mit JSON-Metadaten
- Deterministische Alert-ID-Generierung
- Zeit-basierte Cooldown-Logik
- Automatische TTL-Cleanup (7 Tage)
- Rückwärtskompatibilität (keine Breaking Changes)

### Must NOT Have (Guardrails)
- Keine Änderungen an bestehenden Memory/ChromaDB-Systemen
- Keine neuen externen Dependencies
- Keine UI-Changes in Phase 1 (nur Backend)
- Keine Breaking Changes in Tool-APIs

---

## Verification Strategy

### Test Decision
- **Infrastructure exists:** YES (Redis, pytest)
- **Automated tests:** YES (Tests-after)
- **Framework:** pytest + pytest-asyncio
- **Coverage:** Unit-Tests für Tools, Integration-Tests für Workflow

### QA Policy
Jeder Task enthält Agent-Executed QA Scenarios:
- **Backend:** curl-API-Calls zur Verifikation
- **Redis:** redis-cli Befehle zur State-Prüfung
- **Integration:** End-to-End Workflow-Test

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - Core Tools):
├── Task 1: AlertStateManager Klasse in Redis
├── Task 2: check_alert_state Tool
├── Task 3: record_alert Tool
├── Task 4: resolve_alert Tool
├── Task 5: should_notify Tool
└── Task 6: Tool-Registry in orchestrator.py

Wave 2 (Integration & Tests):
├── Task 7: Unit-Tests für alle Tools
├── Task 8: Integration-Test mit Redis
├── Task 9: Kubernetes-Workflow-Beispiel
├── Task 10: Skill-Dokumentation erstellen
└── Task 11: CHANGELOG.md aktualisieren

Wave 3 (Final Verification):
├── Task F1: Plan Compliance Audit (oracle)
├── Task F2: Code Quality Review (unspecified-high)
├── Task F3: Real Manual QA (unspecified-high)
└── Task F4: Scope Fidelity Check (deep)
```

### Dependency Matrix
- **1-6:** - → 7-11, 2
- **7:** 1-6 → 8, 3
- **8:** 7 → 9, 10, 4
- **9:** 8 → 5
- **10:** 1-6 → 5
- **11:** 1-10 → F1-F4
- **F1-F4:** 1-11 → User-Approval

---

## TODOs

- [ ] 1. AlertStateManager Klasse erstellen

  **What to do:**
  - Erstelle `backend/core/alert_state.py`
  - Implementiere `AlertStateManager` mit Redis-Backend
  - Methoden: `get_state(alert_id)`, `set_state(alert_id, data, ttl)`, `delete_state(alert_id)`, `list_active_alerts()`
  - JSON-Schema für Alert-Metadaten: `{alert_id, module, severity, summary, ticket_id, first_seen, last_notified, status, notify_count}`
  - TTL-Handling: 7 Tage Standard

  **Must NOT do:**
  - Keine ChromaDB-Abhängigkeit (nur Redis)
  - Keine komplexen Queries (nur Key-Value)

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None
  - Reason: Einfache Redis-Wrapper-Klasse, keine komplexe Logik

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1 (mit Tasks 2-6)
  - **Blocks:** Task 2, 3, 4, 5
  - **Blocked By:** None

  **References:**
  - `backend/core/redis_client.py` - Redis-Connection-Pool
  - `backend/core/connections.py` - Beispiel für Redis-basierte CRUD-Operationen
  - Redis JSON Dokumentation: https://redis.io/docs/data-types/json/

  **Acceptance Criteria:**
  - [ ] `AlertStateManager` kann Alerts speichern und wieder abrufen
  - [ ] TTL funktioniert (Alerts werden nach 7 Tagen automatisch gelöscht)
  - [ ] `list_active_alerts()` gibt alle aktiven Alerts zurück

  **QA Scenarios:**

  ```
  Scenario: Alert speichern und abrufen
    Tool: Bash (python)
    Preconditions: Redis läuft, AlertStateManager instanziiert
    Steps:
      1. Run: python -c "
           from core.alert_state import AlertStateManager
           mgr = AlertStateManager()
           await mgr.set_state('test:alert:1', {'module': 'k8s', 'severity': 'critical'}, ttl=3600)
           state = await mgr.get_state('test:alert:1')
           print(state)
         "
    Expected Result: JSON mit module=k8s, severity=critical wird ausgegeben
    Evidence: .sisyphus/evidence/task-1-store-alert.txt

  Scenario: TTL Cleanup
    Tool: Bash (redis-cli)
    Preconditions: Alert mit TTL=1 Sekunde gespeichert
    Steps:
      1. redis-cli SET ninko:alerts:active:ttl:test '{"test": true}' EX 1
      2. sleep 2
      3. redis-cli GET ninko:alerts:active:ttl:test
    Expected Result: (nil) - Key wurde gelöscht
    Evidence: .sisyphus/evidence/task-1-ttl-cleanup.txt
  ```

  **Commit:** YES
  - Message: `feat(core): Add AlertStateManager for Redis-based alert tracking`
  - Files: `backend/core/alert_state.py`
  - Pre-commit: `python -m pytest backend/test_alert_state.py -v` (wenn Tests in Task 7)

- [ ] 2. check_alert_state Tool implementieren

  **What to do:**
  - In `backend/agents/alert_state_tools.py` (neue Datei)
  - Tool-Dekorator: `@tool`
  - Parameter: `alert_id: str`
  - Returns: `{"exists": bool, "state": dict | null, "first_seen": str, "last_notified": str, "notify_count": int}`
  - Verwendet `AlertStateManager` aus Task 1
  - Dokumentation im Docstring (deutsch + englisch)

  **Must NOT do:**
  - Keine Seiteneffekte (nur lesen, nicht schreiben)
  - Keine komplexe Logik (nur State-Lookup)

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None
  - Reason: Einfacher Wrapper um AlertStateManager

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1
  - **Blocks:** Task 3, 5
  - **Blocked By:** Task 1

  **References:**
  - `backend/agents/core_tools.py:1289` - remember_fact als Template
  - `backend/agents/base_agent.py` - Tool-Registration Pattern

  **Acceptance Criteria:**
  - [ ] Tool ist registriert und aufrufbar
  - [ ] Gibt korrektes JSON-Format zurück
  - [ ] Existierende Alerts werden gefunden
  - [ ] Nicht-existierende Alerts geben `exists: false`

  **QA Scenarios:**

  ```
  Scenario: Bestehenden Alert prüfen
    Tool: Bash (curl)
    Preconditions: Alert-State-Manager läuft, Test-Alert existiert
    Steps:
      1. curl -X POST http://localhost:8000/api/tools/check_alert_state \
           -H "Content-Type: application/json" \
           -d '{"alert_id": "k8s:nginx:test:CrashLoopBackOff"}'
    Expected Result: {"exists": true, "state": {...}, "notify_count": 1}
    Evidence: .sisyphus/evidence/task-2-check-existing.json

  Scenario: Nicht-existenten Alert prüfen
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/tools/check_alert_state \
           -H "Content-Type: application/json" \
           -d '{"alert_id": "k8s:doesnotexist"}'
    Expected Result: {"exists": false, "state": null}
    Evidence: .sisyphus/evidence/task-2-check-missing.json
  ```

  **Commit:** YES (gruppiert mit Task 3, 4, 5)

- [ ] 3. record_alert Tool implementieren

  **What to do:**
  - In `backend/agents/alert_state_tools.py`
  - Parameter: `alert_id: str, module: str, severity: str, summary: str, ticket_id: str = ""`
  - Speichert Alert in Redis mit Timestamp
  - Setzt `status` auf `"active"`
  - Initialisiert `notify_count` auf 1
  - Setzt `first_seen` und `last_notified` auf aktuelle Zeit
  - TTL: 7 Tage (604800 Sekunden)

  **Must NOT do:**
  - Keine Duplicate-Prüfung hier (nur speichern)
  - Keine Notification (nur State-Management)

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1
  - **Blocks:** Task 5
  - **Blocked By:** Task 1

  **References:**
  - `backend/core/memory.py:46` - store() Methode als Template

  **Acceptance Criteria:**
  - [ ] Alert wird korrekt in Redis gespeichert
  - [ ] TTL wird gesetzt
  - [ ] Alle Metadaten sind im JSON enthalten

  **QA Scenarios:**

  ```
  Scenario: Alert aufzeichnen
    Tool: Bash (curl + redis-cli)
    Steps:
      1. curl -X POST http://localhost:8000/api/tools/record_alert \
           -H "Content-Type: application/json" \
           -d '{
             "alert_id": "k8s:nginx:test:CrashLoopBackOff",
             "module": "kubernetes",
             "severity": "critical",
             "summary": "Pod nginx-test crashed",
             "ticket_id": "GLPI-12345"
           }'
      2. redis-cli GET ninko:alerts:active:k8s:nginx:test:CrashLoopBackOff
    Expected Result: Redis enthält JSON mit allen Feldern + first_seen, last_notified, notify_count=1
    Evidence: .sisyphus/evidence/task-3-record-alert.txt
  ```

  **Commit:** YES (gruppiert)

- [ ] 4. resolve_alert Tool implementieren

  **What to do:**
  - In `backend/agents/alert_state_tools.py`
  - Parameter: `alert_id: str, resolution: str = ""`
  - Ändert `status` auf `"resolved"`
  - Archiviert Alert in `ninko:alerts:history:{alert_id}` (optional, für Historie)
  - Löscht aus `ninko:alerts:active:{alert_id}`
  - Optional: Call `kg_record_incident()` für Knowledge Graph

  **Must NOT do:**
  - Keine Fehler werfen wenn Alert nicht existiert (idempotent)

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1
  - **Blocks:** Task 9
  - **Blocked By:** Task 1

  **References:**
  - `backend/agents/core_tools.py:1408` - confirm_forget als Template für 2-Step

  **Acceptance Criteria:**
  - [ ] Alert wird aus "active" gelöscht
  - [ ] Optional: Wird in "history" archiviert
  - [ ] Idempotent: Kein Fehler bei nicht-existentem Alert

  **QA Scenarios:**

  ```
  Scenario: Alert resolven
    Tool: Bash (redis-cli)
    Preconditions: Alert existiert in ninko:alerts:active:test
    Steps:
      1. redis-cli GET ninko:alerts:active:k8s:nginx:test:CrashLoopBackOff
      2. curl -X POST http://localhost:8000/api/tools/resolve_alert \
           -d '{"alert_id": "k8s:nginx:test:CrashLoopBackOff", "resolution": "Pod restarted successfully"}'
      3. redis-cli GET ninko:alerts:active:k8s:nginx:test:CrashLoopBackOff
    Expected Result: 
      - Schritt 1: JSON mit active-Status
      - Schritt 3: (nil) - Alert gelöscht
    Evidence: .sisyphus/evidence/task-4-resolve.txt
  ```

  **Commit:** YES (gruppiert)

- [ ] 5. should_notify Tool implementieren

  **What to do:**
  - In `backend/agents/alert_state_tools.py`
  - Parameter: `alert_id: str, min_interval_hours: int = 24`
  - Logik:
    1. `check_alert_state(alert_id)` aufrufen
    2. Wenn nicht existiert → return `{"should_notify": true, "reason": "new_alert"}`
    3. Wenn existiert:
       - Prüfe `last_notified` vs. aktuelle Zeit
       - Wenn `delta > min_interval_hours` → return `{"should_notify": true, "reason": "reminder", "hours_since_last": X}`
       - Sonst → return `{"should_notify": false, "reason": "too_soon", "next_eligible": "timestamp"}`
  - Erhöht `notify_count` wenn Notification erlaubt

  **Must NOT do:**
  - Keine direkte Notification (nur Entscheidung)
  - Keine State-Änderung wenn `should_notify: false`

  **Recommended Agent Profile:**
  - **Category:** `unspecified-high` (hat Logik)
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1
  - **Blocks:** Task 9
  - **Blocked By:** Task 2, 3

  **References:**
  - `backend/agents/core_tools.py:1650` - wait Tool als einfache Logik-Referenz

  **Acceptance Criteria:**
  - [ ] Neue Alerts → `should_notify: true`
  - [ ] Bestehende Alerts < 24h → `should_notify: false`
  - [ ] Bestehende Alerts > 24h → `should_notify: true` (reminder)
  - [ ] `notify_count` wird erhöht bei erlaubter Notification

  **QA Scenarios:**

  ```
  Scenario: Neuer Alert - Notification erlaubt
    Tool: Bash (curl)
    Steps:
      1. curl -X POST http://localhost:8000/api/tools/should_notify \
           -d '{"alert_id": "k8s:new:test:Error", "min_interval_hours": 24}'
    Expected Result: {"should_notify": true, "reason": "new_alert"}
    Evidence: .sisyphus/evidence/task-5-new-alert.json

  Scenario: Zu früh - Notification blockiert
    Tool: Bash (curl)
    Preconditions: Alert wurde vor 1h erstellt
    Steps:
      1. curl -X POST http://localhost:8000/api/tools/should_notify \
           -d '{"alert_id": "k8s:existing:test:Error", "min_interval_hours": 24}'
    Expected Result: {"should_notify": false, "reason": "too_soon", "next_eligible": "..."}
    Evidence: .sisyphus/evidence/task-5-too-soon.json
  ```

  **Commit:** YES (gruppiert)

- [ ] 6. Tool-Registry in orchestrator.py

  **What to do:**
  - In `backend/agents/orchestrator.py`
  - Importiere neue Tools aus `alert_state_tools.py`
  - Füge zu `self._tools` Liste hinzu
  - Aktualisiere System-Prompt mit neuen Tools (kurze Beschreibung)
  - Stelle sicher dass Tools in Tier-2/3/4 Routing verfügbar sind

  **Must NOT do:**
  - Keine Änderungen am Routing-Algorithmus
  - Keine Breaking Changes in bestehenden Tool-Registrierungen

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 1
  - **Blocks:** Task 7, 9
  - **Blocked By:** Task 2, 3, 4, 5

  **References:**
  - `backend/agents/orchestrator.py:301` - Tool-Import Beispiel
  - `backend/agents/orchestrator.py:270` - System-Prompt Tools-Liste

  **Acceptance Criteria:**
  - [ ] Alle 4 Tools sind importiert
  - [ ] Tools sind in `self._tools` enthalten
  - [ ] System-Prompt erwähnt neue Tools

  **QA Scenarios:**

  ```
  Scenario: Tools sind registriert
    Tool: Bash (curl)
    Steps:
      1. curl http://localhost:8000/api/agents/orchestrator/tools
    Expected Result: Liste enthält check_alert_state, record_alert, resolve_alert, should_notify
    Evidence: .sisyphus/evidence/task-6-tools-registered.json
  ```

  **Commit:** YES (gruppiert mit Tasks 1-5 als "feat(alerts): Add alert state tracking tools")

- [ ] 7. Unit-Tests für alle Tools

  **What to do:**
  - Erstelle `backend/test_alert_state.py`
  - Tests für `AlertStateManager`:
    - `test_set_and_get_state`
    - `test_ttl_expiration`
    - `test_list_active_alerts`
    - `test_delete_state`
  - Tests für Tools (mit Mock/Fixture):
    - `test_check_alert_state_existing`
    - `test_check_alert_state_missing`
    - `test_record_alert_success`
    - `test_resolve_alert_success`
    - `test_resolve_alert_idempotent`
    - `test_should_notify_new_alert`
    - `test_should_notify_too_soon`
    - `test_should_notify_reminder_after_24h`

  **Must NOT do:**
  - Keine Integration mit echtem Redis (Mock/Fixture)

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 2
  - **Blocks:** Task 8
  - **Blocked By:** Task 1-6

  **References:**
  - `backend/test_services.py` - Beispiel für Test-Struktur
  - `backend/test_monitor.py` - Async-Test-Beispiele

  **Acceptance Criteria:**
  - [ ] Alle Tests passieren (`pytest backend/test_alert_state.py -v`)
  - [ ] 100% der Tool-Methoden sind abgedeckt
  - [ ] Edge Cases (TTL, Idempotenz) sind getestet

  **QA Scenarios:**

  ```
  Scenario: Alle Tests passieren
    Tool: Bash
    Steps:
      1. cd /home/sb/github/ninko/backend && python -m pytest test_alert_state.py -v
    Expected Result: 10+ tests, alle PASSED
    Evidence: .sisyphus/evidence/task-7-tests-pass.txt
  ```

  **Commit:** YES
  - Message: `test(alerts): Add comprehensive unit tests for alert state tools`

- [ ] 8. Integration-Test mit Redis

  **What to do:**
  - Integration-Test in `test_alert_state.py` oder separate Datei
  - Nutzt echten Redis (Docker Compose Stack)
  - Testet vollen Flow:
    1. `record_alert` → Redis prüfen
    2. `check_alert_state` → State verifizieren
    3. `should_notify` → false (zu früh)
    4. `should_notify` mit manipuliertem `last_notified` (24h zurück) → true
    5. `resolve_alert` → Redis prüfen (gelöscht)

  **Must NOT do:**
  - Keine Mocks (echte Redis-Integration)

  **Recommended Agent Profile:**
  - **Category:** `unspecified-high`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 2
  - **Blocks:** Task 9
  - **Blocked By:** Task 7

  **Acceptance Criteria:**
  - [ ] Integration-Test läuft gegen laufenden Redis
  - [ ] E2E-Flow funktioniert
  - [ ] Redis-State ist korrekt nach jedem Schritt

  **QA Scenarios:**

  ```
  Scenario: Integration-Test
    Tool: Bash
    Preconditions: Docker Compose Stack läuft
    Steps:
      1. cd /home/sb/github/ninko && docker compose up -d redis
      2. cd backend && python -m pytest test_alert_state_integration.py -v
    Expected Result: Integration-Test PASSED
    Evidence: .sisyphus/evidence/task-8-integration.txt
  ```

  **Commit:** YES
  - Message: `test(alerts): Add Redis integration tests`

- [ ] 9. Kubernetes-Workflow-Beispiel

  **What to do:**
  - Erstelle `backend/skills/kubernetes-smart-alerts/SKILL.md`
  - Dokumentiert Best Practice für Alert-Deduplication
  - Enthält Workflow-Beispiel:
    1. Pod-Failure erkennen
    2. `check_alert_state(pod_id)`
    3. Wenn neu: Restart-Versuche
    4. Wenn Restart fehlschlägt: `should_notify()`
    5. Wenn erlaubt: Email senden + `record_alert()`
    6. Wenn Pod wieder läuft: `resolve_alert()`

  **Must NOT do:**
  - Keine Änderungen am Kubernetes-Modul (nur Dokumentation)

  **Recommended Agent Profile:**
  - **Category:** `writing`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 2
  - **Blocks:** None (Dokumentation)
  - **Blocked By:** Task 1-6

  **References:**
  - `backend/skills/kubernetes-incident-response/SKILL.md` - Bestehende Skill-Struktur

  **Acceptance Criteria:**
  - [ ] SKILL.md mit YAML Frontmatter (name, description, modules)
  - [ ] Workflow-Beispiel enthalten
  - [ ] Integration mit Alert-State-Tools dokumentiert

  **QA Scenarios:**

  ```
  Scenario: Skill ist valide
    Tool: Bash
    Steps:
      1. cat backend/skills/kubernetes-smart-alerts/SKILL.md
      2. Prüfe YAML Frontmatter
    Expected Result: Datei existiert, Frontmatter korrekt
    Evidence: .sisyphus/evidence/task-9-skill.md
  ```

  **Commit:** YES
  - Message: `docs(skills): Add kubernetes-smart-alerts skill with deduplication pattern`

- [ ] 10. Skill-Dokumentation erstellen

  **What to do:**
  - Füge neuen Skill zu `backend/skills/catalog.json` hinzu
  - Stelle sicher dass Skill im Marketplace sichtbar ist
  - Kurze Beschreibung der Alert-Deduplication-Funktionalität

  **Must NOT do:**
  - Keine Code-Änderungen (nur JSON)

  **Recommended Agent Profile:**
  - **Category:** `quick`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 2
  - **Blocked By:** Task 9

  **Acceptance Criteria:**
  - [ ] Skill in catalog.json eingetragen
  - [ ] JSON ist valide

  **QA Scenarios:**

  ```
  Scenario: Skill im Katalog
    Tool: Bash (jq)
    Steps:
      1. jq '.skills[] | select(.name == "kubernetes-smart-alerts")' backend/skills/catalog.json
    Expected Result: JSON-Objekt des Skills wird angezeigt
    Evidence: .sisyphus/evidence/task-10-catalog.json
  ```

  **Commit:** YES (gruppiert mit Task 9)

- [ ] 11. CHANGELOG.md aktualisieren

  **What to do:**
  - Füge Eintrag zu v1.2.1 oder v1.3.0 hinzu
  - Liste neue Features:
    - Alert-State-Tracking System
    - 4 neue Core-Tools
    - Redis-basierte Deduplication
    - Kubernetes-Smart-Alerts Skill

  **Must NOT do:**
  - Keine Breaking Changes erwähnen (es gibt keine)

  **Recommended Agent Profile:**
  - **Category:** `writing`
  - **Skills:** None

  **Parallelization:**
  - **Can Run In Parallel:** YES
  - **Parallel Group:** Wave 2
  - **Blocked By:** Task 1-10

  **References:**
  - `CHANGELOG.md` - Bestehende Einträge als Template

  **Acceptance Criteria:**
  - [ ] Neue Version in CHANGELOG.md
  - [ ] Alle Features dokumentiert

  **Commit:** YES
  - Message: `docs(changelog): Add alert state tracking to v1.2.1`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. Verify:
  - AlertStateManager exists in `backend/core/alert_state.py`
  - 4 Tools in `backend/agents/alert_state_tools.py`
  - Tools registered in orchestrator
  - Tests exist and pass
  - Documentation updated
  Output: `Deliverables [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  - Run `cd backend && ruff check .` → No errors
  - Run `cd backend && ruff format --check .` → No formatting issues
  - Run type checker if available
  - Check for AI slop (excessive comments, over-abstraction)
  Output: `Lint [PASS/FAIL] | Format [PASS/FAIL] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  - Start Docker Compose Stack
  - Run Integration-Tests
  - Manuell testen:
    1. `record_alert` → Prüfe Redis
    2. `check_alert_state` → Verify
    3. `should_notify` → false (zu früh)
    4. `resolve_alert` → Verify deletion
  Output: `Manual QA [PASS/FAIL] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  - Compare implemented vs. plan
  - Verify no scope creep (z.B. keine UI-Changes)
  - Check commit messages follow convention
  Output: `Scope [CLEAN/N issues] | Commits [OK/NOK] | VERDICT`

---

## Commit Strategy

| Task | Commit Message | Files |
|------|----------------|-------|
| 1-6 | `feat(alerts): Add alert state tracking tools` | `backend/core/alert_state.py`, `backend/agents/alert_state_tools.py`, `backend/agents/orchestrator.py` |
| 7 | `test(alerts): Add unit tests for alert state tools` | `backend/test_alert_state.py` |
| 8 | `test(alerts): Add Redis integration tests` | `backend/test_alert_state_integration.py` |
| 9-10 | `docs(skills): Add kubernetes-smart-alerts skill` | `backend/skills/kubernetes-smart-alerts/SKILL.md`, `backend/skills/catalog.json` |
| 11 | `docs(changelog): Add alert state tracking` | `CHANGELOG.md` |

---

## Success Criteria

### Verification Commands
```bash
# 1. Tests laufen
cd /home/sb/github/ninko/backend && python -m pytest test_alert_state.py -v

# 2. Integration-Test
cd /home/sb/github/ninko/backend && python -m pytest test_alert_state_integration.py -v

# 3. Redis State-Check
redis-cli KEYS "ninko:alerts:*"

# 4. Linting
cd /home/sb/github/ninko/backend && ruff check agents/alert_state_tools.py core/alert_state.py

# 5. Docker Build (nach Changes)
cd /home/sb/github/ninko && docker compose build backend
```

### Final Checklist
- [ ] `check_alert_state` funktioniert
- [ ] `record_alert` speichert in Redis
- [ ] `resolve_alert` löscht aus active
- [ ] `should_notify` verhindert Duplicates
- [ ] Alle Unit-Tests passieren
- [ ] Integration-Test passiert
- [ ] Skill-Dokumentation vorhanden
- [ ] CHANGELOG aktualisiert
- [ ] Docker Build erfolgreich
- [ ] Keine Breaking Changes

---

## Post-Implementation

Nach erfolgreicher Implementation kann der User folgenden Workflow in Kubernetes nutzen:

```python
# 1. Pod-Failure erkannt
alert_id = f"k8s:{namespace}:{deployment}:{pod_name}:{failure_reason}"

# 2. Prüfe ob schon gemeldet
state = await check_alert_state(alert_id)
if state["exists"]:
    # Bereits bekannt - nur loggen
    logger.info(f"Alert {alert_id} already tracked")
else:
    # Neuer Alert - versuche Restart
    for attempt in range(3):
        result = await restart_deployment(deployment)
        if result.success:
            break
    else:
        # Alle Versuche fehlgeschlagen
        if await should_notify(alert_id, min_interval_hours=24):
            # Sende Email (nur wenn erlaubt)
            ticket = await send_email_to_glpi(summary, ...)
            # Speichere Alert
            await record_alert(
                alert_id=alert_id,
                module="kubernetes",
                severity="critical",
                summary=summary,
                ticket_id=ticket["id"]
            )
        else:
            logger.info(f"Notification suppressed for {alert_id} - too soon")

# 3. Später: Pod wieder healthy
await resolve_alert(alert_id, resolution="Pod recovered")
```

**Ergebnis:** Keine 100 Emails - nur eine pro Alert (plus 24h-Reminders wenn gewünscht).
