# Ninko – Abgeschlossene Aufgaben

Stand: 2026-04-04

---

## GitLab-Modul ✅ *2026-04-04*

### Implementierte Funktionen
- [x] `get_gitlab_status` — Server-Status und Version
- [x] `list_gitlab_projects` — Projekt-Liste
- [x] `get_gitlab_project` — Projekt-Details
- [x] `list_gitlab_pipelines` — Pipeline-Liste
- [x] `get_gitlab_pipeline` — Pipeline-Details
- [x] `trigger_gitlab_pipeline` — Pipeline starten
- [x] `cancel_gitlab_pipeline` — Pipeline abbrechen
- [x] `retry_gitlab_pipeline` — Pipeline wiederholen
- [x] `list_gitlab_jobs` — Job-Liste
- [x] `get_gitlab_job_log` — Job-Log abrufen
- [x] `list_gitlab_merge_requests` — MR-Liste
- [x] `get_gitlab_merge_request` — MR-Details
- [x] `create_gitlab_merge_request` — MR erstellen
- [x] `accept_gitlab_merge_request` — MR akzeptieren
- [x] `list_gitlab_branches` — Branch-Liste
- [x] `list_gitlab_commits` — Commit-Liste
- [x] `list_gitlab_tags` — Tag-Liste
- [x] `create_gitlab_release` — Release erstellen
- [x] `list_gitlab_variables` — Variablen-Liste
- [x] `create_gitlab_variable` — Variable erstellen
- [x] `delete_gitlab_variable` — Variable löschen
- [x] `get_gitlab_pipeline_schedules` — Schedule-Liste
- [x] `create_gitlab_pipeline_schedule` — Schedule erstellen
- [x] `trigger_gitlab_pipeline_schedule` — Schedule triggern

### Technische Umsetzung
- **Tools**: 24 LangGraph-Tools in `backend/modules_catalog/gitlab/tools.py`
- **Agent**: System-Prompt mit allen 10 Sprachen
- **Routing**: Keywords `gitlab`, `ci`, `cd`, `pipeline`, `merge request`, `repository`, `commit`
- **Frontend**: Dashboard-Tab mit Pipelines und Merge Requests

### Dateien erstellt
- `backend/modules_catalog/gitlab/manifest.py`
- `backend/modules_catalog/gitlab/schemas.py`
- `backend/modules_catalog/gitlab/tools.py`
- `backend/modules_catalog/gitlab/agent.py`
- `backend/modules_catalog/gitlab/routes.py`
- `backend/modules_catalog/gitlab/__init__.py`
- `backend/modules_catalog/gitlab/frontend/tab.html`
- `backend/modules_catalog/gitlab/frontend/tab.js`
- `backend/modules_catalog/gitlab/README.md`

### Dateien geändert
- `backend/modules_catalog/catalog.json`
- `backend/agents/base_agent.py` (Tool-Labels)
- `backend/api/routes_settings.py` (Env-Vars + Secrets)
- `frontend/i18n/*.json` (GitLab-Sektion)

---

## Netbox-Modul ✅ *2026-04-04*

### Implementierte Funktionen
- [x] `get_netbox_status` — Server-Status und Version
- [x] `list_netbox_sites` — Site-Liste
- [x] `get_netbox_site` — Site-Details
- [x] `list_netbox_devices` — Device-Liste
- [x] `get_netbox_device` — Device-Details
- [x] `list_netbox_racks` — Rack-Liste
- [x] `get_netbox_rack` — Rack-Details
- [x] `list_netbox_vlans` — VLAN-Liste
- [x] `list_netbox_prefixes` — Prefix-Liste
- [x] `list_netbox_ip_addresses` — IP-Adressen
- [x] `list_netbox_circuits` — Circuits
- [x] `list_netbox_cables` — Kabel
- [x] `list_netbox_clusters` — Cluster
- [x] `get_netbox_device_interfaces` — Device-Interfaces

### Technische Umsetzung
- **Tools**: 14 LangGraph-Tools in `backend/modules_catalog/netbox/tools.py`
- **Agent**: System-Prompt mit allen 10 Sprachen
- **Routing**: Keywords `netbox`, `dcim`, `ipam`, `device`, `rack`, `vlan`, `ipaddress`, `circuit`
- **Frontend**: Dashboard-Tab mit Sites und Devices

### Dateien erstellt
- `backend/modules_catalog/netbox/manifest.py`
- `backend/modules_catalog/netbox/schemas.py`
- `backend/modules_catalog/netbox/tools.py`
- `backend/modules_catalog/netbox/agent.py`
- `backend/modules_catalog/netbox/routes.py`
- `backend/modules_catalog/netbox/__init__.py`
- `backend/modules_catalog/netbox/frontend/tab.html`
- `backend/modules_catalog/netbox/frontend/tab.js`
- `backend/modules_catalog/netbox/README.md`

### Dateien geändert
- `backend/modules_catalog/catalog.json`
- `backend/agents/base_agent.py` (Tool-Labels)
- `backend/api/routes_settings.py` (Env-Vars + Secrets)
- `frontend/i18n/*.json` (Netbox-Sektion)

---

## Zabbix-Modul ✅ *2026-04-04*

### Implementierte Funktionen
- [x] `get_zabbix_status` — Server-Status und Version
- [x] `list_zabbix_hosts` — Host-Liste
- [x] `get_zabbix_host` — Host-Details
- [x] `list_zabbix_items` — Monitoring-Items
- [x] `list_zabbix_triggers` — Trigger-Liste
- [x] `get_zabbix_problems` — Aktuelle Probleme
- [x] `list_zabbix_graphs` — Graphen-Liste
- [x] `list_zabbix_actions` — Actions/Alerts
- [x] `get_zabbix_history` — Historische Daten
- [x] `get_zabbix_host_group` — Host-Gruppen
- [x] `list_zabbix_templates` — Templates
- [x] `create_zabbix_host` — Host erstellen
- [x] `delete_zabbix_host` — Host löschen

### Technische Umsetzung
- **Tools**: 13 LangGraph-Tools in `backend/modules_catalog/zabbix/tools.py`
- **Agent**: System-Prompt mit allen 10 Sprachen
- **Routing**: Keywords `zabbix`, `monitoring`, `host`, `item`, `trigger`, `alert`, `graph`
- **Frontend**: Dashboard-Tab mit Stats und Problemen-Liste

### Dateien erstellt
- `backend/modules_catalog/zabbix/manifest.py`
- `backend/modules_catalog/zabbix/schemas.py`
- `backend/modules_catalog/zabbix/tools.py`
- `backend/modules_catalog/zabbix/agent.py`
- `backend/modules_catalog/zabbix/routes.py`
- `backend/modules_catalog/zabbix/__init__.py`
- `backend/modules_catalog/zabbix/frontend/tab.html`
- `backend/modules_catalog/zabbix/frontend/tab.js`
- `backend/modules_catalog/zabbix/README.md`

### Dateien geändert
- `backend/modules_catalog/catalog.json`
- `backend/agents/base_agent.py` (Tool-Labels)
- `backend/api/routes_settings.py` (Env-Vars + Secrets)
- `frontend/i18n/*.json` (Zabbix-Sektion)

---

## Discord-Modul ✅ *2026-04-04*

### Implementierte Funktionen
- [x] `get_guild_info` — Server-Informationen abrufen
- [x] `get_channels` — Kanal-Liste (Text/Voice/Category)
- [x] `get_members` — Mitglieder-Liste
- [x] `get_messages` — Nachrichten-History
- [x] `create_channel` — Text/Voice-Kanal erstellen
- [x] `delete_channel` — Kanal löschen
- [x] `send_message` — Nachricht senden
- [x] `search_messages` — Nachrichten durchsuchen

### Technische Umsetzung
- **Tools**: 8 LangGraph-Tools in `backend/modules_catalog/discord/tools.py`
- **Agent**: System-Prompt mit allen 10 Sprachen
- **Routing**: Keywords `discord`, `server`, `guild`, `channel`, `textkanal`
- **Frontend**: Dashboard-Tab mit Kanal-Übersicht

### Dateien erstellt
- `backend/modules_catalog/discord/manifest.py`
- `backend/modules_catalog/discord/schemas.py`
- `backend/modules_catalog/discord/tools.py`
- `backend/modules_catalog/discord/agent.py`
- `backend/modules_catalog/discord/routes.py`
- `backend/modules_catalog/discord/__init__.py`
- `backend/modules_catalog/discord/frontend/tab.html`
- `backend/modules_catalog/discord/frontend/tab.js`
- `backend/modules_catalog/discord/README.md`

### Dateien geändert
- `backend/modules_catalog/catalog.json`
- `backend/agents/base_agent.py` (Tool-Labels)
- `frontend/i18n/*.json` (Discord-Sektion)

---

## Theme-System (Vorlagen + Custom + Repo) ✅ *2026-04-03*

### Implementierte Funktionen
- [x] Theme-Backend mit persistenter Aktivierung (`ninko:settings:theme_active`)
- [x] Custom-Theme CRUD (create/update/delete/duplicate)
- [x] Theme-Repo-Verwaltung (GitHub-Repos hinzufügen/löschen/listen)
- [x] Theme-Installation aus Repo (`install-from-repo`)
- [x] Frontend Settings → Themes (Vorlagen, Editor, Repo-Install)
- [x] Runtime-Anwendung von CSS-Tokens bei Start und Light/Dark-Wechsel

### Dateien geändert
- `backend/schemas/theme.py` (neu)
- `backend/core/theme_manager.py` (neu)
- `backend/api/routes_themes.py` (neu)
- `backend/themes/default/theme.json` (neu)
- `backend/themes/arctic/theme.json` (neu)
- `backend/main.py`
- `frontend/index.html`
- `frontend/app.js`

---

## Core-Module Hardening & Bugfixes ✅ *2026-04-03*

### Implementierte Funktionen
- [x] CodeLab Chat-Weiterleitung repariert (`Ninko.sendMessage`)
- [x] CodeLab-Ausführung gehärtet (isoliertes Python, restriktive Env, RLIMITs, Timeout-Kill-Group)
- [x] WebSearch-Frontend XSS-Schutz für dynamische Tabellenwerte
- [x] Interne Fehlerdetails in `codelab`/`web_search` API-Responses reduziert
- [x] WebSearch Header-Handling verbessert (`Host: localhost` entfernt)

### Dateien geändert
- `backend/modules/codelab/tools.py`
- `backend/modules/codelab/routes.py`
- `backend/modules/codelab/frontend/tab.js`
- `backend/modules/web_search/tools.py`
- `backend/modules/web_search/routes.py`
- `backend/modules/web_search/frontend/tab.js`

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

Alle verfügbaren Catalog-Module multilingual-konform:
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

## Catalog-Erweiterungen ✅ *2026-04-03*

- [x] Netzwerk-Module ergänzt: Cisco, MikroTik, Netgear, Ubiquiti
- [x] Kollaboration/PM ergänzt: OpenProject, Nextcloud, Slack
- [x] Redmine erweitert um AlphaNodes HRM + Reporting API-Endpunkte

---

## Exception-Hardening ✅ *2026-04-03*

- [x] Breite Exception-Handler in Core/Agents reduziert und präzisiert
- [x] Fehlerbehandlung in mehreren Katalog-Modulen vereinheitlicht
- [x] Syntax-/Indentation-Fixes in Pi-hole und MikroTik Modulen

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

- [ ] Whisper-Modell-Upgrade: `base` → `small`
- [ ] OPNsense: Interface/DHCP konfigurieren
- [ ] Frontend Tab-JS → English fallback
- [ ] Rollback-Mechanismen für destruktive Aktionen
- [ ] Hardware-Sicherungen für kritische Infrastruktur
