# Ninko – Abgeschlossene Aufgaben

Stand: 2026-04-03

---

## OPNsense-Modul: Write-Operationen ✅ *2026-04-02*

### Implementierte Funktionen
- [x] `create_opnsense_firewall_rule` - Firewall-Regel erstellen
- [x] `delete_opnsense_firewall_rule` - Firewall-Regel löschen
- [x] `create_opnsense_nat_rule` - NAT-Regel erstellen
- [x] `delete_opnsense_nat_rule` - NAT-Regel löschen

### Technische Umsetzung
- **Tools**: 4 neue LangGraph-Tools in `backend/modules_catalog/opnsense/tools.py`
- **Agent**: System-Prompt aktualisiert mit neuen Fähigkeiten und Sicherheitshinweisen
- **Safeguard**: Automatische STATE_CHANGING-Klassifizierung (kein Read-Only)
- **API**: REST-Endpoints für alle Write-Operationen
- **Frontend**: Buttons im Dashboard für Regel-Erstellung
- **Routing**: Neue Keywords für bessere Modul-Erkennung

### Dateien geändert
- `backend/modules_catalog/opnsense/tools.py` (+156 Zeilen)
- `backend/modules_catalog/opnsense/agent.py` (+10 Zeilen)
- `backend/modules_catalog/opnsense/routes.py` (+88 Zeilen)
- `backend/modules_catalog/opnsense/manifest.py` (+4 Keywords)
- `backend/modules_catalog/opnsense/frontend/tab.js` (+22 Zeilen)
- `backend/core/safeguard.py` (keine Änderungen nötig - Tools nicht in Read-Only)

---

## Safeguard-Middleware: Audit-Logging & Cleanup ✅ *2026-04-02*

### Implementierte Funktionen
- [x] Audit-Log für Safeguard-Events (`ninko:safeguard_audit`)
- [x] `_paused_sg_agents` Cleanup (Background-Task alle 60s)
- [x] Dynamische LLM-Provider-Wechsel für Safeguard
- [x] Tasmota Safeguard: Write-Operationen verifiziert
- [x] Custom Policy pro Agent

### Dateien geändert
- `backend/core/safeguard.py` (+120 Zeilen für Audit-Log, Cleanup, Provider-Wechsel)
- `backend/api/routes_safeguard_audit.py` (neu)
- `backend/core/agent_config_store.py` (+Policy-Unterstützung)

---

## TTS & STT – Verbesserungen ✅ *2026-03-14*

### TTS im Web-Dashboard
- [x] TTS-Tab in Core-Einstellungen
- [x] Stimmen-Download & Verwaltung
- [x] Live-Vorschau mit Audio-Player
- [x] API: `GET /api/tts/voices`, `POST /api/tts/synthesize`

### TTS für Module
- [x] Voice-Reply-Config für Telegram/Teams
- [x] Per-Verbindung Stimme überschreibt System-Default

### STT Qualitätssicherung
- [x] Transkriptions-Confidence mit Nachfrage
- [x] Rechtschreibkorrektur nach STT
- [x] Sprache auto-erkennen + weitergeben

---

## Skills & Agenten ✅ *2026-03-20*

- [x] Skills GUI (Übersicht, Editor, Agent-Editor-Integration)
- [x] 6 neue built-in Skills
- [x] API: `GET/POST/PUT/DELETE /api/skills/`

---

## Workflow-Editor & Run-Dashboard ✅ *2026-03-26*

- [x] Live-Canvas für Workflow-Runs
- [x] Status-Overlays (pending/running/succeeded/failed)
- [x] Inline Inspector für Step-Details
- [x] Palette-Buttons mit Icons und Farben
- [x] Bugfixes: Inspector-Titel, Beschreibung-Speicherung

---

## Kubernetes-Modul: Write-Operationen ✅ *2026-03-26*

- [x] `apply_manifest` - YAML-String anwenden
- [x] `delete_resource` - Ressource löschen
- [x] `get_resource_yaml` - Live-YAML abrufen
- [x] `create_namespace` - Namespace anlegen
- [x] `list_deployments` - Deployments auflisten
- [x] Agent-Prompt für direkte Nutzung

---

## Multilingual Migration ✅ *2026-04-02*

Alle 15 Catalog-Module multilingual-konform:
- [x] System-Prompts → `_t(de, en)`
- [x] Tool Docstrings → English
- [x] Log Messages → English
- [x] Error Responses → `_t(de, en)`

Module: kubernetes, proxmox, pihole, fritzbox, homeassistant, ionos, glpi, email, docker, linux_server, wordpress, telegram, teams, opnsense, tasmota, qdrant

---

## Bug Fixes & Code-Qualität ✅ *2026-03-20*

- [x] LLM Provider-Wechsel wirkt sofort
- [x] index.html Browser-Cache
- [x] CodeLab JavaScript (nodejs in Dockerfile)
- [x] LLM Settings erster Load
- [x] `_RE_THINK` als Modul-Konstante
- [x] `decode('utf-8', errors='replace')` für CLI-Output
- [x] Tier-2-Fehlerformat mit "Fehler:" Präfix
- [x] `orchestrator.route()` 3-Werte-Unpacking

---

## Infrastruktur & Deployment ✅ *2026-04-03*

- [x] K8s Manifests bereinigt (`k8s/` vs `k8s-conbro/`)
- [x] Piper TTS in Docker-Compose aktiviert
- [x] K8s Namespace Migration: `kumio` → `ninko`
- [x] deploy.sh: single image push, namespace `ninko`
- [x] CLAUDE.md aktualisiert

---

## Neue Module ✅ *2026-03-28*

- [x] OPNsense-Modul (Firewall-Management)
- [x] Tasmota-Modul (IoT-Gerät-Steuerung)

---

## Dokumentation

- [x] CLAUDE.md mit detaillierter Architektur
- [x] AGENTS.md mit Projekt-Überblick
- [x] TODO.md mit Fortschrittsverfolgung
- [x] DONE.md mit abgeschlossenen Aufgaben

---

## Core-Agent: Wait-Tool ✅ *2026-04-02*

### Implementiertes Tool
- [x] `wait(seconds: int, reason: str = "")` - Dynamisches Warten

### Technische Umsetzung
- **Funktionalität**: Blockiert den Agenten-Thread für 1-60 Sekunden
- **Sicherheit**: Validierung der Wartezeit (1-60 Sekunden)
- **Logging**: Protokolliert Wartezeiten mit optionalem Grund
- **Fehlerbehandlung**: Fängt CancelledError und andere Ausnahmen ab
- **Integration**: In Orchestrator-Agent und Core-Tools-Exporte hinzugefügt

### Use Cases
- Warten auf asynchrone Prozesse
- Bewusste Pausen zwischen Aufgaben
- Simulation von Wartezeiten für Tests
- Rate-Limiting bei API-Aufrufen

### Dateien geändert
- `backend/agents/core_tools.py` (+52 Zeilen)
- `backend/agents/orchestrator.py` (+2 Importe, +1 Tool-Referenz)

### Beispiel-Nutzung
```
# Warte 5 Sekunden auf Datenbank-Synchronisation
Aktion: wait
Aktion Input: {"seconds": 5, "reason": "Datenbank-Synchronisation"}
```

---

## Nächste Schritte (Backlog)

---

## Nächste Schritte (Backlog)

- [ ] HTTPS für `ninko.conbro.local` via Traefik
- [ ] Whisper-Modell-Upgrade: `base` → `small`
- [ ] K8s Namespace Migration: `kumio` → `ninko`
- [ ] OPNsense: Interface/DHCP konfigurieren
- [ ] Frontend Tab-JS → English fallback
- [ ] Rollback-Mechanismen für destruktive Aktionen
- [ ] Hardware-Sicherungen für kritische Infrastruktur
