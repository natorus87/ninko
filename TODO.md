# Ninko – Open TODOs

Last updated: 2026-04-07

---

## NEW: Code Review Findings (2026-04-07)

**Status-Zusammenfassung:**
- ✅ FIXED: 4 Issues behoben
- ⚠️ PARTIALLY_FIXED: 2 Issues teilweise behoben
- ❌ STILL_EXISTS: 13 Issues noch offen
- 🔍 NEW: 1 neues Issue gefunden

### Security Issues (P0)

- [x] **CRITICAL: Replace `subprocess.run(["rm", "-rf", ...])` with `shutil.rmtree()`**
  - Datei: `backend/api/routes_plugins.py:1129-1134`
  - Status: ✅ **FIXED** - Code verwendet jetzt `shutil.rmtree(plugin_dir, ignore_errors=False)` in Zeile 1127
  - Letzte Änderung: 2026-04-07

- [x] **HIGH: CLI Command Argument Validation**
  - Datei: `backend/agents/core_tools.py:187-193`
  - Status: ✅ **FIXED** - `execute_cli_command` nutzt Whitelist-Validierung via `validate_cli_command()` und `create_subprocess_exec` mit Liste (kein Shell-Interpolation)
  - Letzte Änderung: 2026-04-07

- [ ] **MEDIUM: Path Traversal Validation**
  - Datei: `backend/api/routes_plugins.py:485-489`
  - Status: ⚠️ **PARTIALLY_FIXED** - Prüft `".." in member.filename`, aber kein `pathlib.Path.resolve()` für canonical path validation
  - Problem: Encoded Pfade könnten umgangen werden (z.B. `%2e%2e`, Unicode-Äquivalente)
  - Fix: `Path(dest).resolve()` verwenden und prüfen ob Ergebnis im erlaubten Verzeichnis bleibt
  - Code-Beispiel:
    ```python
    dest_path = extracted_dir / member.filename
    canonical_dest = Path(dest_path).resolve()
    if not str(canonical_dest).startswith(str(extracted_dir.resolve())):
        raise HTTPException(status_code=400, detail="Invalid path")
    ```
  - Letzte Änderung: 2026-04-07

### Exception Handling Issues (P1)

- [ ] **HIGH: Bare `except Exception:` in Auth Path**
  - Datei: `backend/main.py:666` (aktualisiert von :655)
  - Status: ❌ **STILL_BROKEN**
  - Problem: `_is_active_user_api_token` gibt False bei Exception zurück, **ohne Logging**
  - Code:
    ```python
    except Exception:
        return False
    ```
  - Risiko: Versteckt Fehlerursachen, erschwert Debugging von Authentifizierungsproblemen
  - Fix: Spezifische Exceptions catchen + `logger.exception()` hinzufügen
  - Letzte Änderung: 2026-04-07

- [ ] **HIGH: Silent Exception in Update Check**
  - Datei: `backend/api/routes_plugins.py:332-333`
  - Status: ❌ **STILL_BROKEN**
  - Problem: `except Exception: return {"update_available": False}` ohne Logging
  - Code:
    ```python
    except Exception:
        return {"update_available": False}
    ```
  - Risiko: Versteckt Netzwerk/Manifest-Fehler, User sieht keine Updates obwohl Fehler vorliegt
  - Fix: `logger.exception()` hinzufügen vor dem Return
  - Letzte Änderung: 2026-04-07

- [ ] **MEDIUM: Silent `pass` in Exception Handlers (9 Stellen)**
  - Status: ❌ **STILL_BROKEN**
  - Dateien und Zeilen:
    1. `backend/api/routes_settings.py:148` - `except (...): pass`
    2. `backend/api/routes_settings.py:273` - `except (...): pass`
    3. `backend/api/routes_settings.py:519` - `except (...): pass`
    4. `backend/api/routes_settings.py:1118` - `except (...): pass`
    5. `backend/api/routes_settings.py:1315` - `except (...): pass`
    6. `backend/api/routes_settings.py:1418` - `except (...): pass`
    7. `backend/modules_catalog/telegram/bot.py:646-647` - `except Exception: pass`
    8. `backend/modules/knowledge_graph/manifest.py:29-30` - `except Exception as exc:` ohne Logging
  - Problem: Fehler werden stillschweigend ignoriert
  - Fix: Mindestens `logger.warning()` oder `logger.exception()` hinzufügen
  - Letzte Änderung: 2026-04-07

### Resource Management (P2)

- [ ] **MEDIUM: Subprocess Resource Leak in MCP Registry**
  - Datei: `backend/core/mcp_registry.py:232-271`
  - Status: ❌ **STILL_LEAKS**
  - Problem: `stdout` Pipe wird nicht geschlossen (nur stdin). Code liest nur stderr, stdout bleibt offen.
  - Code:
    ```python
    finally:
        if process.stdin:
            process.stdin.close()
        # stdout wird nie geschlossen!
        stderr = await process.stderr.read() if process.stderr else b""
    ```
  - Fix: `stdout` schließen oder `process.communicate()` verwenden (wie in `task_registry.py`)
  - Letzte Änderung: 2026-04-07

- [x] **MEDIUM: Subprocess Resource Leak in Task Registry**
  - Datei: `backend/core/task_registry.py:134-165`
  - Status: ✅ **FIXED** - Nutzt `process.communicate()` für sauberes Cleanup
  - Letzte Änderung: 2026-04-07

- [ ] **MEDIUM: Background Task Tracking in Telegram Bot**
  - Datei: `backend/modules_catalog/telegram/bot.py:131, 177, 618`
  - Status: ❌ **NEEDS_ATTENTION**
  - Problem: Tasks werden als "Fire-and-forget" gestartet, kein Tracking, keine Cleanup-Logik bei Shutdown
  - Code-Beispiele:
    ```python
    # Zeile 131
    self.task = asyncio.create_task(self._poll_loop())
    # Zeile 177
    asyncio.create_task(self.handle_update(update, token))
    # Zeile 618
    typing_task = asyncio.create_task(self._keep_typing(token, chat_id))
    ```
  - Risiko: Memory-Leak bei hoher Last oder unkontrolliertes Herunterfahren
  - Fix: Tracking-Set implementieren (wie in `core_tools.py` und `base_agent.py`)
  - Letzte Änderung: 2026-04-07

- [x] **MEDIUM: Background Task Tracking in Core Tools & Base Agent**
  - Dateien: `backend/agents/core_tools.py:704`, `backend/agents/base_agent.py:1113`
  - Status: ✅ **FIXED** - Verwenden `_background_tasks: set[asyncio.Task]` mit `add_done_callback(_background_tasks.discard)`
  - Letzte Änderung: 2026-04-07

- [x] **MEDIUM: HTTP Client Session Management**
  - Dateien: `backend/modules_catalog/ubiquiti/tools.py:103`, `backend/modules_catalog/mikrotik/tools.py:101`, `backend/modules_catalog/linux_server/tools.py:195`
  - Status: ✅ **FIXED** - Alle Module nutzen async context manager (`__aenter__`/`__aexit__`) oder `try/finally`
  - Letzte Änderung: 2026-04-07

### Code Quality (P2)

- [ ] **MEDIUM: Magic Numbers zentralisieren**
  - Status: ⚠️ **PARTIALLY_CENTRALIZED**
  - Bemerkung: `core/config.py` existiert mit `CoreSettings`, aber folgende bleiben inline:
  - Dateien:
    - `backend/agents/core_tools.py:122-123` - `_MAX_OUTPUT_CHARS = 4000`, `_MAX_OUTPUT_LINES = 200`
    - `backend/api/routes_plugins.py:47` - `_CACHE_TTL = 300`
    - `backend/modules/codelab/tools.py:20-26` - 7 Resource limits (`_MAX_CODE_CHARS`, `_MAX_STDOUT_CHARS`, etc.)
  - Fix: Verbleibende Konstanten in `CoreSettings` verschieben
  - Letzte Änderung: 2026-04-07

- [ ] **LOW: Test Files use `print()` instead of logging**
  - Status: ❌ **STILL_EXISTS**
  - Treffer: 44× in 11 Dateien
  - Dateien: `test_services.py`, `test_pihole.py`, `test_monitor.py`, `test_fritz.py`, `test_wan.py`, `test.py`, `test_tts.py`, `test_routing.py`, `test_e2e_critical_paths.py`, `test_wan_tool.py`
  - Letzte Änderung: 2026-04-07

- [ ] **LOW: Inconsistent Timeout Values**
  - Status: ❌ **STILL_EXISTS**
  - Gefundene Werte:
    - `routes_plugins.py`: 120.0, 10.0, 15.0, 60.0, 30.0
    - `mcp_registry.py`: 20.0 (default)
    - `image_provider.py`: 120, 180
    - `telegram/bot.py`: 30, 10, 5, 35 (berechnet)
  - Fix: Zentrale Timeout-Defaults in `core/config.py` definieren
  - Letzte Änderung: 2026-04-07

### Type Annotations (P3)

- [ ] **LOW: Missing/Incomplete Type Hints**
  - Dateien:
    - `backend/agents/core_tools.py:56-88` - `_t()` Funktion ohne type hints
    - `backend/modules_catalog/fritzbox/tools.py:202` - `_exec` returns `object`
  - Status: ❌ **STILL_MISSING**
  - Letzte Änderung: 2026-04-07

### Concurrency (P2)

- [ ] **LOW: `while True:` Loops ohne Exit-Condition**
  - Dateien:
    - `backend/agents/base_agent.py:1188`
    - `backend/main.py:364`
    - `backend/core/mcp_registry.py:302, 415, 457`
    - `backend/modules_catalog/telegram/bot.py:328`
    - `backend/modules_catalog/glpi/agent.py:134`
  - Status: ❌ **STILL_EXISTS**
  - Fix: Exit-Condition oder `asyncio.Event` für graceful shutdown implementieren
  - Letzte Änderung: 2026-04-07

---

## Completed this session (2026-04-07)

### Concurrency Issues (P2)

- [ ] **MEDIUM: Background Task Tracking**
  - Dateien:
    - `backend/agents/core_tools.py:704, 17` - Global set für tasks
    - `backend/agents/base_agent.py:1113, 532` - Auto-memorize tasks
    - `backend/modules_catalog/telegram/bot.py:131, 177, 618`
  - Problem: Tasks werden erstellt aber nicht aufgeräumt (Memory Leak)
  - Fix: Task-Referenzen speichern und bei completion aufräumen

- [ ] **LOW: `while True:` Loops ohne Exit-Condition**
  - Dateien:
    - `backend/agents/base_agent.py:1188`
    - `backend/main.py:364`
    - `backend/core/mcp_registry.py:302, 415, 457`
    - `backend/modules_catalog/telegram/bot.py:328`
    - `backend/modules_catalog/glpi/agent.py:134`
  - Fix: Exit-Condition oder `asyncio.Event` für graceful shutdown

### Type Annotations (P3)

- [ ] **LOW: Missing/Incomplete Type Hints**
  - `backend/agents/core_tools.py:56-88` - `_t()` Funktion ohne type hints
  - `backend/modules_catalog/fritzbox/tools.py:202` - `_exec` returns `object`

---

## Completed this session (2026-04-07)

### Code-Review aller 45 Module – Gefundene & Behobene Fehler
- [x] **KRITISCH: Synology Agent duplicate class definition behoben**
  - Datei: `backend/modules_catalog/synology/agent.py`
  - Problem: `SynologyAgent` wurde zweimal definiert (Zeilen 94-124 und 169-184)
  - Impact: Zweite Definition überschrieb die erste → 15 Tools nicht verfügbar (shutdown, reboot, user management, etc.)
  - Fix: Doppelte Definition entfernt, vollständige Tool-Liste (22 Tools) jetzt aktiv

- [x] **image_gen __init__.py bereinigt**
  - Datei: `backend/modules/image_gen/__init__.py`
  - Problem: Fehlendes `__all__` und `from __future__ import annotations`
  - Fix: `__all__ = ["module_manifest", "agent"]` ergänzt

- [x] **slack tools.py – unused import entfernt**
  - Datei: `backend/modules_catalog/slack/tools.py`
  - Problem: `from multipart import MultipartParam` (Zeile 581) war ungenutzt
  - Fix: Import entfernt (Code verwendet `aiohttp.FormData`)

### Module-Review Summary (45 Module)
| Kategorie | Anzahl | Status |
|-----------|--------|--------|
| Core Module | 3 | Alle OK |
| Catalog Module | 42 | 41 OK, 1 kritisch behoben |
| **Gesamt** | **45** | **Alle jetzt OK** |

---

## Ninko – Offene TODOs

Stand: 2026-04-07

---

## Documentation Sync (English) — 2026-04-04

### Recently completed operational fixes
- [x] Kubernetes runtime migrated from `kumio` namespace to `ninko` namespace with PVC data migration.
- [x] Ingress routing fixed for both hosts: `kumio.conbro.local` and `ninko.conbro.local`.
- [x] Deployment security hardened: explicit auth/session env vars and required secrets in k8s + Helm.
- [x] First-login password change flow fixed (no stale `password_change_required` session lock).
- [x] Legacy connection keys migrated to tenant-aware keys (`ninko:connections:default:<module>`).
- [x] SafeGuard false-positive fixed (`wissen` no longer flagged as destructive).
- [x] Image generation restored (module enabled in k8s + writable storage path fallback).

### Follow-up tasks
- [x] Remove terminated old backend ReplicaSets/pods after rollout grace periods.
- [x] Optionally decommission old `kumio` namespace resources after final acceptance.
- [x] Add a short runbook for namespace migration rollback/recovery.

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
- [x] **GitHub-Modul**
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
- [x] **Advanced Workflow-Engine** (Parallel Execution, Retries, Sub-Workflows, Versionierung)
  - Status 2026-04-04:
    - Workflow-Node-Typen erweitert: `parallel`, `subflow`
    - Retry-Mechanik pro Node (`retries`, `retry_delay_ms`) in Engine umgesetzt
    - Parallel-Batch-Execution für gleichzeitig anstehende Nodes aktiviert
    - Sub-Workflow-Ausführung inkl. separatem Run-Tracking umgesetzt
    - Workflow-Versionierung ergänzt (`version`, Versionshistorie + Restore-Endpoint)
    - Tenant-Scoping in `workflow_engine.py` auf Run-Index/Run-Updates vereinheitlicht
- [x] **Knowledge Graph & RAG-Optimierung**
  - Status 2026-04-07: **Vollständig implementiert**
  - Komponenten:
    - `core/knowledge_graph.py`: NetworkX-basierter Graph mit Entitäten, Beziehungen, Traversal
    - `api/routes_knowledge_graph.py`: CRUD + Queries + Visualisierung (Cytoscape-Format)
    - `backend/skills/knowledge-graph-querying/SKILL.md`: Skill-Dokumentation
    - `agents/core_tools.py`: 4 neue Tools (kg_find_related, kg_find_path, kg_analyze_dependencies, kg_record_incident)
    - `agents/base_agent.py`: Automatische KG-RAG-Injektion im Prompt
  - Features:
    - Entity-Types: module, service, host, configuration, incident, user, tag, runbook, workflow, agent
    - Relations: depends_on, triggers, resolved_by, similar_to, configured_with, manages, part_of, caused_by, has_tag, executed_by
    - Graph-Algorithms: PageRank-Centrality, Louvain-Communities, Path-Finding
    - Smart Extraction: Automatische Entity-Extraktion aus Incidents
    - Hybrid RAG: Kombination ChromaDB (semantisch) + Knowledge Graph (strukturiert)
  - API-Endpunkte: 20+ Endpunkte für CRUD, Queries, Analytics, Import/Export
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
