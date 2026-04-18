# PLAN

---

## Aktueller Stand

### Was live und stabil ist

- **Workflows**: Alle 8 Node-Typen (trigger, agent, condition, loop, parallel, subflow, variable, end) vollständig implementiert und verifiziert
- **Agent-Generierung**: Timeout-Handling (30s), robustes JSON-Parsing, Fallbacks, Tests
- **Scripting-MVP**: CRUD, Execute, History im Cluster verifiziert
- **Frontend**: Workflows, Agents, Scripting modularisiert
- **Tests**: pytest mit Smoke-, Integrations- und E2E-Tests für alle kritischen Pfade
- **API-Doku**: Umfassend in `backend/API.md`
- **K8s-Verifikation**: Wiederverwendbare Blaupausen in `.claude/`

---

## Offene Erweiterungen (Optional / Zukunft)

Die folgenden Punkte sind nicht Teil der aktuellen Stabilisierungsphase, sondern für zukünftige Releases geplant:

### Scripting-Ausbau

- Scheduling (Cron-ähnliche Ausführung)
- Artifacts (Datei-Upload/Download für Scripts)
- Multi-File-Support (Script-Projekte statt Single-File)
- Erweitertes Sicherheitskonzept (Sandboxing, Ressourcenlimits)

#### Neues Feature: „Script als Tool“ für Ninko-Orchestrator

**Ziel:** Scripts im Dashboard als Tool markierbar machen, damit der Orchestrator sie gezielt nutzen kann.

**Warum sinnvoll:**
- Reduziert wiederholte Prompt-Arbeit für Standard-Automationen
- Macht tenant-spezifische Betriebslogik wiederverwendbar
- Verbindet Scripting-UI direkt mit KI-gestützter Ausführung

**MVP-Scope (Phase 1):**
- Toggle im Scripting-Editor: `Als Tool verfügbar`
- Optionale Tool-Metadaten je Script:
  - Tool-Name (stabil, slug)
  - Kurzbeschreibung (für Tool-Auswahl)
  - Eingabe-Schema (JSON/Pydantic-light, optional)
- Tool-Registry pro Tenant aus den aktivierten Scripts
- Orchestrator darf nur `tool_enabled=true` Scripts als Tool aufrufen
- Read-only Tool-Invocation-Log (wer/was/wann, Dauer, Status)

**Backend-Änderungen:**
- `modules/scripting/schemas.py`:
  - Felder ergänzen: `tool_enabled`, `tool_name`, `tool_description`, `tool_input_schema`
- `modules/scripting/routes.py`:
  - CRUD erweitert um Tool-Felder
  - Validierung: eindeutiger `tool_name` je Tenant
  - Nur erlaubte Zeichen im `tool_name` (slug)
- Neue interne Tool-Bridge (z. B. `agents/script_tools.py`):
  - Liest aktivierte Scripts tenant-scoped
  - Führt Script mit validiertem Input aus
  - Standardisierte Fehler-/Timeout-Responses für Orchestrator
- Optionaler Cache + Invalidation bei Script-Update/Delete

**Frontend-Änderungen:**
- Scripting-Editor:
  - Toggle „Als Tool verfügbar“
  - Felder für Name/Beschreibung/Input-Schema sichtbar bei aktivem Toggle
- Script-Karten:
  - Badge „Tool aktiv“
  - Quick-Hinweis, ob für KI nutzbar

**Security/Guardrails:**
- Feature-Flag: `SCRIPT_TOOLS_ENABLED` (Default: off)
- Harte Timeout-/Ressourcenlimits behalten
- Tenant-Isolation strikt (keine tenant-fremden Tools)
- Optional: Allowlist für Script-Tools pro Rolle/Modul

**Akzeptanzkriterien (DoD):**
- Aktiviertes Script wird in Tool-Registry sichtbar und aufrufbar
- Nicht aktivierte Scripts sind nie durch Orchestrator aufrufbar
- Falsches Input-Schema liefert klaren Validation-Fehler
- Tool-Aufrufe erscheinen in Logs/History nachvollziehbar
- E2E-Test: Chat-Anfrage -> Tool-Aufruf -> Script-Output -> Antwort

**Offene Architekturentscheidung:**
- Dynamische Tool-Injection pro Request vs. statische Tool-Registry mit Cache
  - Empfehlung: statische Registry + Cache-Invalidation (robuster, einfacher zu debuggen)

### Frontend-Vervollständigung

- Chat-Modul extrahieren
- Settings-Modul extrahieren
- Themes-Modul extrahieren
- SafeGuard-Modul extrahieren

### Ideen aus AIfred-Intelligence (2026-04-17)

Analyse von [github.com/Peuqui/AIfred-Intelligence](https://github.com/Peuqui/AIfred-Intelligence) — verwertbare Konzepte für Ninko:

**5-Level Tool Permission Tiers** *(Aufwand: Mittel | Mehrwert: Hoch)*
Ergänzung zum LLM-Classifier: Jedes Tool deklariert statisch einen Tier (READONLY / COMMUNICATE / WRITE_DATA / WRITE_SYSTEM / ADMIN). Deterministisch, kein 8s-Timeout. Hybrid: statische Tiers + LLM-Classifier als Override für Grenzfälle.
- Ninko hat `_TOOL_READONLY` — das Konzept auf 5 Stufen erweitern
- Besonders relevant wenn externe Channels (Email, Discord) hinzukommen

**Chat als HTML exportieren** *(Aufwand: Klein | Mehrwert: Mittel)*
Standalone HTML mit inlinen Fonts, offline lesbar. Nützlich für Incident-Reports, Audit-Trails, Weitergabe an Nicht-Nutzer.

#### Priorität: Langfristig / Strategisch

**Message Hub (externe Channels)** *(Aufwand: Groß | Mehrwert: Hoch)*
Email (IMAP IDLE), Discord Bot, Telegram als Background-Worker. SQLite-Routing-Tabelle mappt Channel + Channel-ID auf Sessions. Auto-Restart mit Exponential Backoff.
- Ninko würde damit direkt in nativen IT-Ops-Kommunikationskanälen erreichbar
- Alerts könnten bidirektional antworten
- Voraussetzung: 5-Level Permission Tiers (externe Requests bekommen reduzierten Tier)

### Weitere Features

- Piper TTS im K8s-Image (bei Bedarf)
- Workflow-Versionierung erweitern (Audit-Log, visuelles Debugging)
- Python-Script als Workflow-Node (Script-Node ist bereits implementiert)

---

## Archiv

Die vollständige Historie der Stabilisierungsphase mit allen technischen Details, Verifikationen und abgeschlossenen Punkten befindet sich im Git-History.
