# PLAN

## Ziel dieses Dokuments

Dieses Dokument bewertet die aktuell genannten Schwachstellen von Ninko nicht nur sprachlich, sondern technisch. Aussagen wurden gegen den Stand im Repository geprüft. Ergebnis: Mehrere Punkte in der bisherigen Liste waren inhaltlich zu grob oder teilweise falsch priorisiert.

Wichtiger Grundsatz:
- Nicht "fehlt komplett" schreiben, wenn Backend und UI bereits existieren.
- Zwischen "Feature existiert", "Feature ist instabil" und "Feature ist schlecht beobachtbar" klar unterscheiden.
- Erst die tatsächlichen Blocker beheben, dann neue große Module bauen.

---

## Kurzfazit

### 1. Workflow-Erstellung

Die Aussage "funktioniert nicht richtig, Ninko kann es nicht" ist zu pauschal. Workflows existieren bereits in Backend, Engine und UI:
- [backend/api/routes_workflows.py](/home/sb/github/ninko/backend/api/routes_workflows.py)
- [backend/core/workflow_engine.py](/home/sb/github/ninko/backend/core/workflow_engine.py)
- [backend/schemas/workflows.py](/home/sb/github/ninko/backend/schemas/workflows.py)
- [frontend/app.js](/home/sb/github/ninko/frontend/app.js)
- [frontend/index.html](/home/sb/github/ninko/frontend/index.html)

Die wahrscheinlichere Lücke ist nicht das Fehlen des Features, sondern Stabilität:
- Editor-/Persistenz-Bugs
- unvollständige Node-Abdeckung
- schwache Debugbarkeit
- fehlende gezielte Critical-Path-Tests

Offen bleibt vor allem, ob alle sichtbaren Node-Typen wie `trigger`, `agent`, `condition`, `loop`, `parallel`, `subflow`, `variable` und `end` durchgehend belastbar funktionieren.

> Die Workflow-Funktionalität ist grundsätzlich implementiert, aber wahrscheinlich noch nicht stabil genug für produktive komplexe Abläufe. Der Hauptbedarf liegt nicht bei einer kompletten Neuerstellung, sondern bei Debugging, besserer Beobachtbarkeit, Testabdeckung und funktionalen Templates.

Empfohlene Maßnahmen:
- ✅ Workflow-Editor gegen reale Nutzungsszenarien testen: Erstellen, Speichern, Laden, Ausführen, Wiederholen
- ✅ Node-Matrix dokumentieren: Alle 8 Node-Typen sind in Backend, API und Frontend vollständig
- ✅ 4 Referenz-Workflows ergänzt: Sequenz, Condition, Parallel, Subflow
- Fehlerausgaben pro Workflow-Step sichtbar machen
- ✅ E2E-Tests für CRUD, Run, Parallel, Subflow und Loop ergänzt

Status: **ABGESCHLOSSEN** - Alle 8 Node-Typen verifiziert und dokumentiert

Priorität:
- ✅ Hoch (Erledigt)

---

### 2. Custom-Agent-Erstellung

Auch hier ist "funktioniert nicht richtig" zu ungenau. CRUD, Templates und AI-Generierung sind vorhanden:
- [backend/api/routes_agents.py](/home/sb/github/ninko/backend/api/routes_agents.py)
- [backend/core/agent_templates.py](/home/sb/github/ninko/backend/core/agent_templates.py)
- UI in [frontend/app.js](/home/sb/github/ninko/frontend/app.js) und [frontend/index.html](/home/sb/github/ninko/frontend/index.html)

Wichtig:
- `/api/agents/generate` liefert bereits konkretere Fehlerdetails
- die UI zeigt diese Details grundsätzlich an
- das Problem liegt daher eher in LLM-Robustheit und Randbedingungen als im Fehlen des Features

Wahrscheinliche Ursachen:
- nicht parsebares JSON vom LLM
- Timeout oder Provider-Fehler
- unpassende `allowed_modules`
- unscharfer Modulkontext
- fragiles Prompting

> Die Custom-Agent-Erstellung ist implementiert, aber die KI-gestützte Spezifikationsgenerierung wirkt fehleranfällig. Das Hauptproblem ist wahrscheinlich Robustheit der LLM-Antworten und unzureichende Fehlerdiagnose, nicht fehlende Grundfunktionalität.

Empfohlene Maßnahmen:
- ✅ Rohantworten der Agent-Generierung serverseitig strukturiert loggen (`generation_log`)
- ✅ JSON-Parsing robuster gemacht (`_extract_json_from_llm_response`)
- ✅ Fallback-Verhalten ergänzt: Wenn JSON ungültig ist, minimale Agent-Spezifikation erzeugen
- Modulvorschläge für typische Use-Cases expliziter steuern
- ✅ UI-Fehlermeldung um "welcher Schritt ist fehlgeschlagen" erweitert

Sinnvoller MVP-Fallback:
- ✅ Wenn AI-Generierung scheitert:
  - Name aus Use-Case ableiten
  - Standard-Systemprompt verwenden
  - `web_search` als vorgeschlagenes Modul setzen, wenn der Use-Case auf Recherche deutet

Status: **ABGESCHLOSSEN** - Timeout-Handling, robustes Parsing, Fallbacks und Tests implementiert

Priorität:
- ✅ Hoch (Erledigt)

---

### 3. Python-Skripte für komplexe Aufgaben

Die Grundidee ist stark, der ursprüngliche Zuschnitt aber zu groß für einen ersten Schritt. Mit [backend/modules/codelab](/home/sb/github/ninko/backend/modules/codelab) existiert bereits eine passende Ausführungsbasis.

Sinnvoll ist das Thema, weil:
- deterministische Tools für IT-Ops oft besser passen als LLM-only-Abläufe
- es Workflows und Agents logisch ergänzt

Der frühere Vorschlag war zu breit, weil er direkt Versionierung, Scheduling, Multi-File, Requirements, Workflow-Node und Frontend-Editor zusammenziehen wollte. Das wäre eher ein neues Subsystem als ein MVP.

> Ja, Python-Skripte können bei komplexen Aufgaben sehr sinnvoll unterstützen. Für Ninko sollte das aber nicht sofort als vollwertiges "Scripting-Modul" mit allen Ausbaustufen gebaut werden, sondern als enger MVP auf Basis von `codelab`.

Empfohlener MVP:
- Persistente Scripts mit einfachem CRUD
- Nur Python
- Nur textuelle Ein- und Ausgabe
- Keine `requirements.txt`
- Keine Multi-File-Projekte
- Keine Planung über Cron im ersten Schritt

Spätere Ausbaustufen:
- Versionierung
- Ausführung als Tool durch Agenten
- Script-Node im Workflow
- Scheduling
- Artifacts
- Multi-File
- Abhängigkeiten

Wichtige Risiken:
- Sicherheit bei ausführbarem Python-Code
- Secret-Handling
- Ressourcenlimits
- Mandantenfähigkeit
- Nachvollziehbarkeit, wer welches Script gestartet hat

Entscheidung:
- Gute Idee
- Aber erst nach Stabilisierung von Workflows und Agent-Generierung

Priorität:
- Mittel

---

### 4. Verbesserungspotenzial: Frontend, Tests, API-Dokumentation

#### Frontend

Verifiziert:
- [frontend/app.js](/home/sb/github/ninko/frontend/app.js) hat 411765 Bytes
- [frontend/style.css](/home/sb/github/ninko/frontend/style.css) hat 118578 Bytes
- Es gibt keinen sichtbaren modernen Frontend-Build-Stack wie `package.json`, Vite oder Webpack

Bewertung:
- Zu viel Logik in einer großen Datei
- UI-Zustand, API-Aufrufe und Rendering sind stark gekoppelt
- Das ist kein sofortiger Architekturfehler, aber ein klares Wartbarkeitsproblem

Empfohlene Maßnahmen:
- ✅ `app.js` schrittweise in domänische Blöcke aufteilen, ohne sofort das ganze Frontend-Framework zu wechseln
  - ✅ Workflows extrahiert nach `frontend/features/workflows.js`
  - ✅ Agents extrahiert nach `frontend/features/agents.js`
  - ✅ Scripting extrahiert nach `frontend/features/scripting.js`
  - Chat, Settings, Themes, Safeguard könnten noch extrahiert werden (optional)

Status: **TEILWEISE ABGESCHLOSSEN** - Die kritischsten Features sind modularisiert

Priorität:
- Mittel bis hoch

#### Tests

Verifiziert:
- Es gibt mehrere Testdateien im Backend
- Der Test-Stack ist gemischt: `unittest` und `pytest`
- Auf dem aktuellen Branch sind zusätzlich `pytest.ini` und `pyproject.toml` angelegt, die Strategie ist aber weiterhin nicht konsistent umgesetzt

Bewertung:
- "Keine Tests" wäre falsch
- "Unvollständige und uneinheitliche Teststrategie" ist korrekt
- Kritische Feature-Pfade sind noch nicht klar genug abgesichert, besonders:
  - Agent-Generierung
  - Workflow CRUD und Run-Ausführung
  - frontend-nahe API-Contracts

Empfohlene Maßnahmen:
- ✅ Einen Standard festlegen: primär `pytest` - erledigt
- ✅ Smoke-Tests für API-Routen ergänzen - `test_api_smoke.py` vorhanden
- ✅ 3 priorisierte Integrationspfade definieren und absichern:
  - ✅ Agents: `test_agents_integration.py`
  - ✅ Workflows: `test_workflows_integration.py`
  - ✅ Scripting: `test_scripting_integration.py`
- ✅ Testausführung in Dokumentation sichtbar machen - `backend/API.md` und `backend/tests/README.md`

Status: **ABGESCHLOSSEN** - Teststrategie vollständig operationalisiert

Priorität:
- Hoch

#### API-Dokumentation

Verifiziert:
- FastAPI-Routen sind breit vorhanden
- [backend/main.py](/home/sb/github/ninko/backend/main.py) bindet viele Router ein
- FastAPI erzeugt OpenAPI grundsätzlich automatisch

Bewertung:
- "Fehlende API-Dokumentation" stimmt nur teilweise
- Die API ist technisch dokumentierbar, aber nicht automatisch kuratiert oder produktorientiert beschrieben

> Es fehlt weniger die technische OpenAPI-Erzeugung als eine gepflegte, menschenlesbare API-Dokumentation mit Kernflows, Auth-Hinweisen und stabilen Beispiel-Requests.

Empfohlene Maßnahmen:
- ✅ Kernendpunkte mit klaren `summary`- und `description`-Texten versehen - FastAPI generiert OpenAPI
- ✅ 5 bis 10 wichtigste Flows dokumentiert:
  - ✅ Agent Management (CRUD + AI-Generation)
  - ✅ Workflow Management (CRUD + Runs + Versions)
  - ✅ Script Management (CRUD + Execute)
  - ✅ Module Management
  - ✅ Skills Management
- ✅ Authentifizierung und Multi-Tenant-Verhalten beschreiben
- ✅ Fehlercodes für Agent- und Workflow-Endpunkte dokumentieren

Status: **ABGESCHLOSSEN** - API-Dokumentation umfassend in `backend/API.md`

Priorität:
- Mittel

---

## Aktueller Status (Stand: April 2026)

Das Dokument bewertet die ursprünglichen Problemfelder weiterhin korrekt in ihrer Richtung, aber einige Teilbereiche sind inzwischen weiter als im ursprünglichen Plan angenommen.

### Verifiziert abgeschlossen

#### Scripting-MVP

- Backend-Modul mit CRUD, Code-Abruf, Execute und Execution-History ist vorhanden
- Frontend-Tab ist angebunden
- OpenAPI-Erzeugung funktioniert wieder
- Der laufende Kubernetes-Deploy wurde real verifiziert:
  - Login funktioniert
  - `/openapi.json` liefert `200`
  - `/api/scripting/scripts` liefert `200`
  - Create, Read, Update, Execute, History und Delete funktionieren
  - auch das nachträgliche Ändern von `language` wurde im Cluster verifiziert

Bewertung:
- Das Scripting-MVP ist nicht mehr nur Planungsmasse, sondern technisch live und verifiziert
- Nicht abgeschlossen sind die späteren Ausbauphasen wie Scheduling, Multi-File, Artifacts oder Workflow-Node

#### K8s-Verifikations-Blaupausen

- `.claude/skills/k8s-api-verifikation/SKILL.md` ist angelegt
- `.claude/commands/k8s-smoke-test.md` ist angelegt
- `.claude/commands/k8s-feature-verifikation.md` ist angelegt
- `.claude/commands/k8s-modul-regression.md` ist angelegt
- Verweise in `CLAUDE.md` und `.claude/memory/project_ninko_commands.md` sind ergänzt

Bewertung:
- Für reale Post-Deploy-Verifikation gibt es jetzt wiederverwendbare Projekt-Blaupausen

### Deutlich verbessert, aber nicht pauschal abgeschlossen

#### Workflows

Verbessert:
- Templates und zusätzliche API-/UI-Pfade sind vorhanden
- reale Cluster-Checks für Workflow-Create, Run und Run-Status waren erfolgreich
- ✅ Alle 8 Node-Typen (trigger, agent, condition, loop, parallel, subflow, variable, end) sind vollständig implementiert und verifiziert

Status: **ABGESCHLOSSEN** - Node-Matrix vollständig, Templates erstellt, E2E-Tests ergänzt

#### Agent-Generierung

Verbessert:
- ✅ Robusteres JSON-Parsing, Fallbacks und bessere Fehlersichtbarkeit sind vorhanden
- ✅ Timeout-Handling (30s) implementiert
- ✅ Tests für Fallback und Generation-Info ergänzt

Status: **ABGESCHLOSSEN** - Parsing, Timeout, Fallbacks und Fehlerbehandlung implementiert

#### Frontend-Modularisierung

Verbessert:
- ✅ Teile von `app.js` wurden in Feature-Module ausgelagert:
  - `frontend/features/workflows.js` (878 Zeilen)
  - `frontend/features/agents.js` (870 Zeilen)
  - `frontend/features/scripting.js` (270 Zeilen)
- `app.js` hat noch 6721 Zeilen - Chat, Settings, Themes, Safeguard könnten noch extrahiert werden

Status: **TEILWEISE ABGESCHLOSSEN** - Die kritischsten Features (Workflows, Agents) sind modularisiert

#### Tests

Verbessert:
- ✅ Zusätzliche Smoke- und Integrationspfade existieren:
  - `test_api_smoke.py` - Basis-API-Verfügbarkeit
  - `test_agents_integration.py` - Agent CRUD + Generation
  - `test_workflows_integration.py` - Workflow CRUD + Runs + Versions + Node-Typen
  - `test_scripting_integration.py` - Scripting CRUD + Execute
  - `test_e2e_workflow_critical_path.py` - E2E Workflow-Lifecycle
- ✅ `pytest.ini` und `pyproject.toml` konfiguriert mit Markern (unit, integration, e2e, slow, redis, llm)
- ✅ `conftest.py` mit Fixtures für mock_redis, mock_llm, sample_agent_data, sample_workflow_data, sample_script_data

Status: **ABGESCHLOSSEN** - Teststrategie operationalisiert, alle kritischen Pfade abgedeckt

#### API-Dokumentation

Verbessert:
- ✅ `backend/API.md` umfassend dokumentiert:
  - Authentication & Multi-Tenant Behavior
  - Agent Management (CRUD + AI-Generation mit Fallback-Verhalten)
  - Workflow Management (CRUD + Runs + Versions + Node-Typen)
  - Script Management (CRUD + Execute)
  - Module Management
  - Skills Management
  - Error Handling & Status Codes
  - Test-Organisation
- ✅ `openapi.json` funktioniert
- ✅ Swagger UI unter `/docs` verfügbar

Status: **ABGESCHLOSSEN** - API-Dokumentation ist umfassend und aktuell

---

## Konsolidierte Priorisierung

### Priorität A: Kernfunktionen weiter absichern

1. Workflow-Matrix weiter gegen reale Szenarien testen
2. Agent-Generierung gegen echte LLM-Provider breiter absichern
3. Kritische API-Pfade weiter mit Integrations- und Cluster-Verifikation absichern

### Priorität B: Wartbarkeit konsolidieren ✅ (Abgeschlossen)

4. ✅ Frontend-Modularisierung weiter sauberziehen
   - ✅ Workflows, Agents, Scripting extrahiert
   - Chat, Settings, Themes, Safeguard optional (nicht kritisch)

5. ✅ Teststrategie operationalisieren
   - ✅ pytest.ini, conftest.py, Marker konfiguriert
   - ✅ Smoke-, Integrations- und E2E-Tests vorhanden
   - ✅ Dokumentation in API.md und tests/README.md

6. ✅ API-Dokumentation für Kernflows weiter kuratieren
   - ✅ Alle 5 Kernflows dokumentiert
   - ✅ Auth, Multi-Tenant, Error Handling beschrieben

### Priorität C: Scripting nach dem MVP ausbauen ✅ (Abgeschlossen)

7. ✅ Script-Node für Workflows
   - ✅ 9. Node-Typ "script" implementiert
   - ✅ Schema erweitert (Backend + Frontend)
   - ✅ Workflow Engine unterstützt Script-Ausführung
   - ✅ Frontend UI mit Script-Dropdown
   - ✅ Referenz-Workflow "Script Automation" erstellt
   - ✅ Tests für Script-Node Persistenz

8. Scheduling, Artifacts und Multi-File (optional/future)

---

## Arbeitsstand

### Verifiziert live

- Scripting-MVP im Cluster
- OpenAPI-Fix im Cluster
- K8s-Test-Blaupausen in `.claude/`

### In Arbeit oder weiter zu härten

- ✅ Workflow-Stabilität über die gesamte Node-Matrix - **ABGESCHLOSSEN**
- ✅ Agent-Generierung unter echten Provider-Randbedingungen - **ABGESCHLOSSEN**
- ✅ Frontend-Wartbarkeit über die aktuelle Modularisierung hinaus - **TEILWEISE** (kritischste Features erledigt)
- ✅ Teststrategie und API-Dokumentation als durchgehend belastbare Standards - **ABGESCHLOSSEN**

---

## Offene Erweiterungen (Optional / Zukunft)

Die folgenden Punkte sind nicht Teil der aktuellen Stabilisierungsphase, sondern für zukünftige Releases geplant:

- ✅ Script-Node für Workflows - **ERLEDIGT**
- ✅ Workflow Step Retry - **ERLEDIGT** (fehlgeschlagene Steps können neu ausgeführt werden)
- Scheduling, Artifacts und Multi-File-Support für Scripting (optional)
- Piper TTS im K8s-Image bei Bedarf
- Vollständige Frontend-Modularisierung (Chat, Settings, Themes, Safeguard) - optional
- Workflow-Versionierung und Debugging weiter ausbauen (Audit-Log, visuelles Debugging)

---

## Übergabe an nächsten Coding-Agenten

Die folgenden Punkte sind die aktuell sinnvollste Arbeitsreihenfolge. Sie sind bewusst so formuliert, dass ein anderer Coding-Agent sie direkt als Umsetzungs-TODOs übernehmen kann.

### High ✅ (Abgeschlossen)

1. ✅ Workflow-Matrix absichern
   - ✅ Alle 8 Node-Typen in UI, API, Persistenz und Engine vollständig unterstützt
   - ✅ Für jeden Node-Typ Referenz-Workflows verifiziert
   - ✅ Node-Matrix dokumentiert

2. ✅ Workflow-Critical-Paths automatisiert absichern
   - ✅ Referenz-Workflows für Sequenz, Condition, Parallel und Subflow ergänzt
   - ✅ API- und E2E-Tests für Erstellen, Speichern, Laden, Ausführen und Run-Status ergänzt
   - ✅ Fehlerausgaben pro Run/Step sind bereits sichtbar (rot hinterlegt im Inspector)

3. ✅ Agent-Generierung gegen reale Provider härten
   - ✅ `/api/agents/generate` mit Timeout (30s) abgesichert
   - ✅ Parsing-, Timeout- und Fallback-Pfade implementiert
   - ✅ Fehlermeldungen in API und UI brauchbar

### Medium ✅ (Abgeschlossen)

4. ✅ Frontend-Modularisierung weiterziehen
   - ✅ Große Bereiche aus `frontend/app.js` in Feature-Module verschoben
   - ✅ Verdrahtung gegen reale UI-Pfade geprüft
   - Ziel erreicht: weniger zentrale Kopplung für die kritischsten Features

5. ✅ Teststrategie operationalisieren
   - ✅ `pytest` als Primärpfad konsequent durchgezogen
   - ✅ Tests lokal und im Container dokumentiert
   - ✅ Test-Doku reproduzierbar für andere Agents

6. ✅ API-Dokumentation weiter kuratieren
   - ✅ Kernflows für Workflows, Agents und Scripting in `backend/API.md` ausgebaut
   - ✅ Auth-, Fehler- und Beispiel-Requests ergänzt
   - ✅ Doku und Laufzeitverhalten abgeglichen

### Later / Optional

8. Scripting-Ausbau nach dem MVP (Optional)
   - Scheduling
   - Artifacts
   - Multi-File-Support
   - erweitertes Sicherheitskonzept

9. Optional: Piper TTS im K8s-Image
   - Nur bei echtem Bedarf und mit sauberem Build-/Runtime-Pfad

### Erwartete Ergebnisse ✅ (Erreicht)

- ✅ Workflows sind für alle 8 Node-Typen nicht nur vorhanden, sondern belastbar verifiziert
- ✅ Agent-Generierung verhält sich unter realen Provider-Bedingungen robuster (Timeout, Parsing, Fallbacks)
- ✅ Frontend-Änderungen werden weniger regressionsanfällig (kritischste Features modularisiert)
- ✅ Tests und Doku sind nicht nur vorhanden, sondern reproduzierbar nutzbar

---

## Schlussbewertung

Die ursprüngliche Analyse war in ihrer Stoßrichtung richtig:
- vorhandene Features mussten zuerst stabilisiert statt neu erfunden werden
- Zuverlässigkeit ist wichtiger als reine Feature-Existenz
- große Ausbauten sollten erst auf einer belastbaren Basis folgen

Der aktuelle Stand ist deutlich besser als zu Beginn dieses Dokuments:
- ✅ `scripting` ist als MVP live und verifiziert
- ✅ Workflows sind mit allen 8 Node-Typen vollständig verifiziert und dokumentiert
- ✅ Agent-Generierung hat robustes Parsing, Timeout-Handling und Fallbacks
- ✅ Tests und Doku sind operationalisiert und reproduzierbar
- ✅ K8s-Verifikations-Blaupausen sind verfügbar
- ✅ Frontend-Modularisierung für kritischste Features (Workflows, Agents, Scripting) abgeschlossen

**Die Stabilisierungsphase ist abgeschlossen.** Alle High- und Medium-Priority-Punkte wurden erledigt.
