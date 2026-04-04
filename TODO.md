# Ninko – Offene TODOs

Stand: 2026-04-04

---

## Jetzt (P0)

### Audit-Findings (2026-04-04)
- [x] **Unsichere Auth-Defaults härten (Bootstrap nur einmalig + Passwortwechsel erzwingen)**
  - Dateien: `backend/core/config.py`, `backend/main.py`, `docker-compose.yml`
  - Problem: Default-Fallback `BOOTSTRAP_ADMIN_PASSWORD=admin` ist für Erststart praktisch, aber dauerhaft ein Risiko.
  - Ziel: Erststart-Flow mit einmaligem Bootstrap-Token oder Pflicht-Passwortwechsel beim ersten Login; kein statischer Default in Produktion.
  - Status 2026-04-04:
    - `password_change_required` im Session-Token/`/api/auth/me` ergänzt
    - neuer Endpoint: `POST /api/auth/change-password`
    - API-Sperre bis Passwortwechsel (nur `/api/auth/me`, `/api/auth/change-password`, `/api/auth/logout` erlaubt)
    - Login-Flow in `frontend/login.html` erzwingt Passwortwechsel vor Dashboard-Zugriff

- [x] **Catalog-Module auf konsistente Exception-Strategie umstellen**
  - Dateien: `backend/modules_catalog/netbox/*`, `backend/modules_catalog/zabbix/*`, `backend/modules_catalog/gitlab/*`, `backend/modules_catalog/discord/routes.py`
  - Problem: Breite `except Exception`-Blöcke verbergen Fehlerursachen und erschweren sichere Fehlerbehandlung.
  - Ziel: spezifische Exception-Gruppen + standardisierte API-Fehlerantworten.
  - Status 2026-04-04:
    - Catch-Alls (`except Exception`) in den betroffenen Routen/Health-Checks entfernt
    - Fehlerbehandlung auf spezifische Exception-Gruppen vereinheitlicht

- [x] **Catalog-Manifeste standardisieren (Core `ModuleManifest` statt Custom-Stub)**
  - Dateien: `backend/modules_catalog/netbox/manifest.py`, `backend/modules_catalog/zabbix/manifest.py`, `backend/modules_catalog/gitlab/manifest.py`
  - Problem: Inkonsistente Manifest-Struktur (`api_prefix`, `dashboard_tab`, Health-Check-Referenzen) gegenüber Template/Core.
  - Ziel: 1:1 auf `core.module_registry.ModuleManifest` migrieren.
  - Status 2026-04-04:
    - Manifeste auf `core.module_registry.ModuleManifest` migriert
    - konsistente Felder (`display_name`, `env_prefix`, `required_secrets`, `api_prefix`, `dashboard_tab`) ergänzt
    - gemeinsames Antwortschema für diese Modul-Routen über `backend/core/schemas.py:ApiResponse` bereitgestellt

- [x] **Legacy-Testskripte reparieren (aktuell nicht lauffähig)**
  - Dateien: `backend/test_services.py`, `backend/test_monitor.py`, `test_pihole.py`
  - Problem:
    - `NoneType`-Crash wenn keine FritzBox-Connection vorhanden (`conn_data is None`)
    - veralteter Importpfad in `test_pihole.py` (`modules.pihole.tools` nicht vorhanden)
  - Ziel: robuste Precondition-Checks + korrekte Modulpfade + klare Skip-Meldungen statt Crash.
  - Status 2026-04-04:
    - FritzBox-Tests prüfen Connection/Secret/Host vor Verwendung und skippen sauber
    - `test_pihole.py` nutzt robusten Fallback-Import (`modules` → `modules_catalog`) und skippt bei fehlender Konfiguration

- [x] **CI-Qualitätsgates ergänzen**
  - Dateien: `.github/workflows/*` (neu/erweitern)
  - Problem: Fehler wie `except Exception`-Regressionen und Manifest-Inkonsistenzen fallen erst spät auf.
  - Ziel: automatische Checks für `compileall`, verbotene Patterns (z. B. `except Exception` in Produktivmodulen), und einfache Modul-Integritätsprüfung.
  - Status 2026-04-04:
    - neuer Workflow `.github/workflows/ci-quality.yml` ergänzt
    - Gates: `compileall` (backend), Pattern-Guard gegen broad catch-alls, Modul-Integritätscheck (Pflichtdateien) 

### Security
- [x] **API-Authentifizierung/Autorisierung auf Core-Routern einführen**
  - Dateien: `backend/main.py` (alle `app.include_router(...)`), `backend/api/routes_*.py`
  - Risiko: Unautorisierter Zugriff auf Admin-/Write-Endpunkte
  - Ziel: Zentrales AuthN/AuthZ-Konzept (API-Key/JWT + Rollen), Default-deny auf mutierenden Endpunkten

- [x] **Plugin-Upload + Hot-Load absichern**
  - Dateien: `backend/api/routes_plugins.py`, `backend/core/module_registry.py`
  - Risiko: RCE-Kette über `/api/plugins/upload` und `/api/plugins/install-from-repo/{module_name}`
  - Ziel: Admin-only, Signatur/Allowlist, optional Build-Phase statt Runtime-Import

- [x] **Secret-Leaks aus Settings-Read-APIs entfernen**
  - Dateien: `backend/api/routes_settings.py`, `backend/schemas/settings.py`
  - Risiko: `api_key` / `STT_API_KEY` im Response
  - Ziel: nur Maskierung bzw. `*_set` Flags, Secrets ausschließlich Vault

- [x] **Safeguard-Adminoperationen absichern**
  - Datei: `backend/api/routes_safeguard.py`
  - Risiko: Safeguard kann ohne Auth global deaktiviert werden
  - Ziel: privilegierte Rollen + vollständiges Audit

### Core Routing/Builder UX
- [x] **Agent-/Workflow-Builder End-to-End testen (Chat-Flow)**
  - Hintergrund: Für Builder-Intents wurde ein deterministischer Fast-Path ergänzt
  - Ziel: Verifizieren, dass bei "erstelle Agent/Workflow" wirklich erstellt wird (nicht nur Anleitung)

---

## Kurzfristig (P1)

### Security
- [x] **CORS auf konkrete Origins einschränken**
  - Datei: `backend/main.py:321-327`
  - Aktuell: `allow_origins=["*"]`

- [x] **Rate-Limiting für API-Endpunkte einführen**
  - Risiko: DoS, Brute-Force
  - Ziel: SlowAPI oder Token-Bucket

- [x] **TLS-Verify in Modulen standardmäßig aktivieren**
  - Dateien: `backend/modules_catalog/glpi/*`, `backend/modules_catalog/opnsense/*`
  - Aktuell: `verify=False`

- [x] **WebSocket/Logs/Secrets-Endpunkte absichern**
  - Dateien: `backend/api/routes_ws.py`, `backend/api/routes_logs.py`, `backend/api/routes_secrets.py`
  - Ziel: Rollenmodell (read-only vs admin), Scrubbing sensibler Logs

- [x] **Transcription-Upload limitieren**
  - Datei: `backend/api/routes_transcription.py`
  - Ziel: Request-Größenlimit + MIME/Duration-Validierung + Streaming/Chunking

- [x] **Safeguard-Timeout konfigurierbar machen**
  - Datei: `backend/main.py:193`
  - Aktuell: hardcoded `8.0`

### Code-Qualität
- [x] **Breite `except Exception`-Nutzung reduzieren**
  - Stand: `0x` in `backend/` (`rg -n "except Exception" backend`)
  - Ergebnis: Catch-Alls auf spezifische Exception-Gruppen umgestellt (Core, API, Module, Catalog, Tests)

- [x] **Magic Numbers in `base_agent.py` reduzieren**
  - `_JIT_THRESHOLD = 6`, `_JIT_MAX_TOOLS = 8` nach `core/config.py` verlagert
  - Neue zentrale Settings: `AGENT_JIT_THRESHOLD`, `AGENT_JIT_MAX_TOOLS`, `AGENT_MEMORIZE_COOLDOWN_SECS`

- [x] **Rückgabetypen (`-> None`) und Typisierung erweitern**
  - Stand: alle einzeiligen Funktionssignaturen in `backend/` mit Return-Type-Hints versehen
  - Ergebnis: konsistente Return-Typannotation über Core/API/Module/Catalog/Tests

- [x] **Logging-Konvention vereinheitlichen**
  - Stand: `0x` Logger-f-strings in `backend/`
  - Ergebnis: parameterisiertes Logging (`%s`) aktiv

- [x] **Modul-Template-Placeholders standardisieren (nicht entfernen)**
  - Pfad: `backend/modules_catalog/_template/`
  - Ergebnis: `REQUIRED`-Marker ergänzt, Placeholder-Policy in README dokumentiert, Frontend-Template auf delegierte `data-action` Events umgestellt (kein inline `onclick`)

---

## Produkt & Features (P2)

### Infrastruktur & Deployment
- [x] **HTTPS für `ninko.conbro.local`**
  - Traefik IngressRoute mit selbstsigniertem Zertifikat
  - Aktiviert `getUserMedia` und `crypto.randomUUID()` ohne Browser-Flag

- [x] **Whisper-Modell-Upgrade testen (`base` → `small`)**
  - API-Benchmark ergänzt: `POST /api/transcription/whisper/benchmark?models=base,small`
  - Ergebnis liefert je Modell: Text, `avg_confidence`, Laufzeit und `recommended_model`

### TTS/STT
- [x] **Stimmen-Katalog aus HuggingFace**
  - Endpoint ergänzt: `GET /api/tts/voices/catalog?lang=de`
  - Enthält `installed`-Flag und optionalen Sprachfilter
  - HF-Tree-API mit TTL-Cache (10 Minuten)

- [x] **Piper-Binary Auto-Update**
  - Endpoint umgesetzt: `GET /api/tts/piper/version`
  - Liefert `local_version`, `latest_tag/latest_version`, `update_available`

### Module
- [x] **OPNsense: erweiterte Write-Operationen**
  - Interface-Einstellungen (IP, Subnet, aktivieren/deaktivieren)
  - DHCP-Server (Range, DNS, Gateway)
  - Virtual IPs (CARP, Proxy ARP)

- [x] **Tasmota: Multi-Device-Management**
  - Gruppen/Broadcast
  - Geräte-Liste via MQTT Discovery
  - Gruppenverwaltung

### Frontend & UX
- [x] **Fallback-UX für Tab-JS ohne i18n**
  - Template-Tab auf englische Standardtexte umgestellt (`Loading...`, `Refresh`, `No entries found`)
  - JS-Fallback `_tmplT(key, fallback)` ergänzt (falls i18n-Key fehlt oder i18n nicht geladen ist)
  - Globaler Frontend-Helper `tf(key, fallback)` in `frontend/app.js`

### Sicherheit & Betrieb
- [x] **Rollback-Mechanismen für destruktive Aktionen**
  - Neues Operations-Journal: `backend/core/operation_journal.py`
  - API: `GET /api/operations/transactions`, `GET /api/operations/transactions/{id}`
  - Rollback-Handling: `/rollback-note` und `/rollback-complete`
  - Chat-Integration: Safeguard-confirmed `DESTRUCTIVE`/`STATE_CHANGING` Aktionen erzeugen/aktualisieren Transaktions-Einträge

- [x] **Hardware-Sicherungen für kritische Infrastruktur**
  - Runbook ergänzt: `HARDWARE_SAFETY.md`
  - Baseline enthält: Management-Netz-Trennung, Break-glass-Konsole, Immutable Backups, Dual-Control, Recovery-Checklist

### Doku & Tests
- [x] **E2E-Tests für kritische Pfade**
  - Safeguard-Workflows
  - Modul-Integrationen
  - Workflow-Engine

- [x] **Modul-READMEs vervollständigen**
  - README ergänzt für: `checkmk`, `docker`, `homeassistant`, `linux_server`, `opnsense`, `qdrant`, `tasmota`, `teams`, `wordpress`

---

## Backlog (Langfristig)

- [x] **GLPI: OCR für Ticket-Bilder**
  - Tool ergänzt: `get_ticket_image_ocr(ticket_id: int, attachment_id: int, connection_id: str = "")`
  - Lädt Bild aus GLPI-Ticket-Anhang und extrahiert Text
  - Globale OCR-Settings in UI ergänzt (Provider `python` oder `llm_vision`)
  - Docker/Deps ergänzt: `tesseract-ocr`, `tesseract-ocr-deu`, `pytesseract`, `Pillow`

- [x] **Slack-Modul**
- [x] **Discord-Modul**
- [x] **Zabbix-Modul**
- [x] **Netbox-Modul**
- [x] **GitLab-Modul**
- [ ] **Multi-Tenancy**
  - Status 2026-04-04: **RBAC-Basis umgesetzt** (Backend)
  - Umgesetzt:
    - Benutzer-/Gruppen-/Rollenverwaltung via `/api/auth/*` (CRUD)
    - Modulrechte pro Rolle (`module_permissions` mit `read`/`write`)
    - Session-Token enthält effektive Rechte (Rolle + Modul-ACL)
    - Middleware-Enforcement für Modul-API-Routen (`/api/<modul>/*`)
    - Bootstrap-Admin wird beim Startup in RBAC synchronisiert
  - Noch offen:
    - GUI für Benutzer-/Gruppen-/Rollenverwaltung (erledigt)
    - Harte Tenant-Datentrennung (Mandanten-ID in Datenpfaden/Queries)
    - Mandanten-spezifische Ressourcen-Isolation (Memory, Workflows, Connections, Logs)
  - Status 2026-04-04 (Schritt 2b, Teil 1): **Tenant-Scoping gestartet**
  - Umgesetzt:
    - Session-Token erweitert um `tenant_id` (`tid`)
    - RBAC-User erweitert um `tenant_id` (Login liefert tenant-aware Session)
    - Chat-History tenant-scoped (`tenant:session_id`)
    - UI-Chat-History tenant-scoped (`ninko:ui:history:{tenant}`)
    - Workflow-Storage tenant-scoped (`ninko:workflows:{tenant}`, `ninko:workflow:runs:{tenant}:...`)
  - Noch offen in Schritt 2b:
    - Tenant-Scoping für weitere Ressourcen (Connections, Memory, Operations-Log, Agent-Pool)
    - Tenant-aware UI-Filter/Führung im Access-Tab
- [x] **Plugin-Marketplace mit Versionierung**
  - Plugin-Metadaten in Redis ergänzt (`ninko:plugins:metadata`): `source`, `repo_id`, `repo_url`, `repo_version`, `installed_at`, `updated_at`
  - Neuer Endpoint: `GET /api/plugins/installed` (inkl. Versions-/Herkunftsinfos)
  - Marketplace-Update-Liste erweitert um `installed_source`/`installed_updated_at`
- [ ] **Advanced Workflow-Engine** (Parallel Execution, Retries, Sub-Workflows, Versionierung)
- [ ] **Knowledge Graph & RAG-Optimierung**
- [ ] **Mobile App (PWA)**

---

## Rename: Kumio → Ninko

- [x] **Offene String-Reste bereinigen**
  - Bildmarker standardisiert auf `[NINKO_IMAGE:url]` in Orchestrator + Image-Gen-Modul
  - Telegram/Web-Renderer auf `NINKO_IMAGE` umgestellt (mit Backward-Compat für alte `KUMIO_IMAGE`-Marker)
  - Entwicklungsdoku von `KUMIO_` Resten bereinigt

| Datei | Zu ändern |
|---|---|
| `frontend/app.js` | erledigt (`NINKO_IMAGE`, kompatibel zu Alt-Markern) |
| `backend/modules_catalog/telegram/bot.py` | erledigt (`NINKO_IMAGE`, kompatibel zu Alt-Markern) |
| `backend/modules/image_gen/tools.py` | erledigt (`NINKO_IMAGE`) |
| `backend/modules/image_gen/agent.py` | erledigt (`NINKO_IMAGE`) |
| `backend/agents/orchestrator.py` | erledigt (`NINKO_IMAGE`) |
| `DEVELOPMENT.md` | erledigt (KUMIO-Rest entfernt) |
| `backend/modules_catalog/_template/README.md` | bereits auf `ninko-backend` |

Hinweis:
- `CHANGELOG.md` und `.git/logs/` als Historie nicht anfassen.
- `frontend/i18n/*.json` existieren im Repository.

---

## Erledigt

- [x] **Theme-System mit Vorlagen + Custom-Editor + Repo-Import (2026-04-03)**
  - Backend: `routes_themes.py`, `theme_manager.py`, `schemas/theme.py`, built-in Themes
  - Frontend: Settings → Themes, Aktivierung, Token-Editor (`tokens_dark`/`tokens_light`), Repo-Installation
  - Runtime: CSS-Tokens werden beim Start und beim Light/Dark-Wechsel angewendet

- [x] **Core-Module-Bugfixes & Hardening (2026-04-03)**
  - `codelab`: Chat-Button-Bug (`app.sendMessage` → `Ninko.sendMessage`) behoben
  - `codelab`: Code-Ausführung gehärtet (isolierter Python-Mode, Limits, restriktive Env, sauberes Timeout-Kill)
  - `web_search`: XSS-Risiko im Tab-Rendering reduziert (HTML-Escaping)
  - `web_search`/`codelab`: interne Exception-Details nicht mehr an Clients geleakt

- [x] **K8s Namespace Migration: `kumio` → `ninko` (2026-04-03)**
  - Deployment/Service/Ingress/PVC/ConfigMap auf `ninko`
  - Image: `natorus87/ninko-backend:latest`
  - Deploy-Doku aktualisiert

- [x] **Synology-Modul implementiert**
  - Modulstruktur + Catalog + Frontend + Settings/Safeguard/Tool-Labels integriert

- [x] **Neue Netzwerk-Module implementiert (2026-04-03)**
  - Cisco, MikroTik, Netgear, Ubiquiti
  - Modulstruktur + Catalog + Frontend + Settings/Safeguard/Tool-Labels integriert

- [x] **Neue PM/Collab-Module implementiert (2026-04-03)**
  - OpenProject, Nextcloud, Slack
  - Modulstruktur + Catalog + Frontend + Settings/Safeguard/Tool-Labels integriert

- [x] **Redmine-Modul implementiert**
  - Modulstruktur + Catalog + Frontend + Settings/Safeguard/Tool-Labels integriert
  - AlphaNodes HRM + Reporting API-Endpunkte (inkl. spezifischer Tools) ergänzt

- [x] **Confluence-Modul implementiert**
  - Modulstruktur + Catalog + Frontend + Settings/Safeguard/Tool-Labels integriert

- [x] **Jira-Modul implementiert**
  - Modulstruktur + Catalog + Frontend + Settings/Safeguard/Tool-Labels integriert

- [x] **GLPI-Modul erweitert**
  - Neue Tools: get_ticket_attachments, get_ticket_followups, get_ticket_solutions
  - _TOOL_READONLY und _TOOL_LABELS integriert

- [x] **Audit-Checks (Info)**
  - Keine SQL-Injection-Risiken gefunden
  - Keine `shell=True`-Subprocesses
  - Secrets via Vault/SQLite
  - Redis-Key-Namenskonvention konsistent
