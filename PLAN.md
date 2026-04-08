# Plan: Alert-State-Tracking & Deduplication System

## TL;DR

> **Neues Core-Feature:** Redis-basiertes Alert-State-Tracking mit Deduplication im Monitor-Agent und LLM-Tools für Workflows.
>
> **Problem gelöst:** Monitor-Agent (`run_cycle`) erzeugt bei jedem Intervall identische Alerts/Incidents ohne Prüfung ob bereits gemeldet. Bei 60s-Intervall = 1440 Duplikate/Tag. Dasselbe gilt für periodische Scheduler-Tasks mit Remediation-Workflows.
>
> **Scope:** Alle Module — Kubernetes, Proxmox, Linux, Docker, OPNsense, etc. — jedes Modul kann durch die Kombination `module:resource:reason` einen determinstischen Alert generieren.
>
> **Deliverables:**
> - `backend/core/alert_state.py` — `AlertStateManager` mit atomarem `check_and_record` (Redis `SET NX EX`)
> - 3 neue Core-Tools: `check_alert_state`, `record_alert`, `resolve_alert`
> - Monitor-Agent Deduplication (programmatisch, kein LLM-Call)
> - Safeguard-Registrierung der read-only Tools
> - Generischer Skill: `smart-alerts` mit Beispiel-Patterns für K8s, Proxmox, Linux
>
> **Effort:** Medium (3-4 Stunden)
> **Critical Path:** AlertStateManager → Monitor-Integration → Tools → Tests → Generische Skills

---

## Context

### Original Request

User möchte folgende Workflows automatisieren:
1. Ninko überwacht verschiedene Systeme (Monitor-Agent / Scheduler)
   - Kubernetes: Pod-Failure, Deployment nicht ready
   - Proxmox: VMs stopped/crashed
   - Linux: Disk space, CPU, Memory
   - Docker: Container exited, health-check failed
   - OPNsense: Service stopped, Firewall alert
   - Pi-hole: Gravity update failed
   - etc.
2. Fehler wird erkannt
3. Automatische Remediation-Versuche schlagen fehl (oder sind nicht konfiguriert)
4. Email/Ticket wird gesendet → Incident erstellt
5. Workflow läuft periodisch wieder an
6. **Problem:** Ohne Deduplication werden bei jedem Zyklus neue Alerts + Incidents erzeugt

### Aktuelle Architektur (Code-Analyse)

**Monitor-Agent** (`backend/agents/monitor_agent.py:88-123`):
```python
# run_cycle() — KEIN Dedup-Check:
for module_name, status in health.items():
    if status.get("status") == "error":
        alert = { "type": "alert", "module": module_name, ... }
        await self._redis.publish_event(alert)       # Jedes Mal
        await self._memory.store_incident(...)        # Jedes Mal neue UUID
```

**Scheduler-Agent** (`backend/agents/scheduler_agent.py:114-247`):
- Führt Tasks via `orchestrator.route()` aus
- Workflows können Module-Agents aufrufen
- Kein Alert-Tracking — gleiche Remediation läuft endlos

**Semantic Memory** (`backend/core/memory.py:124-137`):
- `store_incident()` speichert in ChromaDB mit neuer UUID
- Kein Key-basiertes Lookup, nur semantische Suche
- Ungeeignet für deterministische Deduplication

**Redis Client** (`backend/core/redis_client.py`):
- `publish_event()` — fire-and-forget, kein State
- `cache_set/get` — einfaches Key-Value, aber kein Alert-Schema
- `connection` Property gibt raw `aioredis.Redis` zurück — direkte `SET NX EX` möglich

**Was fehlt:**
- Kein strukturiertes Alert-State-Tracking (active/resolved)
- Keine deterministische Alert-ID (Module + Resource + Reason)
- Kein zeitbasierter Cooldown für Notifications
- Keine atomare "check-and-set" Operation vor dem Senden

### Design-Entscheidungen

1. **Redis statt ChromaDB** — deterministisches Key-Value Lookup, nicht semantische Suche. Alert-IDs sind bekannt, nicht "ähnlich".
2. **Atomares `SET NX EX`** — Race-Condition-frei. Wenn zwei Zyklen gleichzeitig prüfen, gewinnt nur einer.
3. **Monitor-Agent nutzt AlertStateManager direkt** — programmatisch, kein LLM-Call. Das ist der primäre Consumer.
4. **LLM-Tools für Workflows** — `check_alert_state`, `record_alert`, `resolve_alert` als `@tool` für Tier-4 Pipelines und Scheduler-Workflows.
5. **Alert-ID wird programmatisch generiert** — `AlertStateManager.make_id(module, resource, reason)` statt LLM-generierte Strings.
6. **Module-agnostisch** — Alert-Schema ist unabhängig vom spezifischen Modul. Jedes Modul definiert seine eigenen Resource/Reason-Werte.

---

## Work Objectives

### Concrete Deliverables
- `backend/core/alert_state.py` — AlertStateManager Klasse
- `backend/agents/alert_tools.py` — 3 LLM-Tools (`@tool`)
- Patch: `backend/agents/monitor_agent.py` — Deduplication in `run_cycle()`
- Patch: `backend/agents/orchestrator.py` — Tool-Import + Registration
- Patch: `backend/core/safeguard.py` — `check_alert_state` in `_TOOL_READONLY`
- `backend/skills/smart-alerts/SKILL.md` — Generisches Skill mit Multi-Module-Patterns
- `backend/test_alert_state.py` — Unit + Integration Tests

### Definition of Done
- [ ] Monitor-Agent erzeugt keine Duplikate mehr (gleicher Modul-Fehler = 1 Alert)
- [ ] `check_alert_state("kubernetes:nginx-deployment:crashloopbackoff")` gibt korrekten Status zurück
- [ ] Alerts funktionieren für K8s, Proxmox, Linux, Docker, OPNsense gleichermassen
- [ ] `resolve_alert()` markiert Alerts als gelöst + archiviert
- [ ] Alerts haben 7-Tage TTL (automatisches Cleanup)
- [ ] Read-only Tools in `_TOOL_READONLY` registriert
- [ ] Alle Tests passieren
- [ ] Docker Build erfolgreich

### Guardrails
- Keine Änderungen an ChromaDB/Memory-System
- Keine neuen externen Dependencies
- Keine UI-Changes (nur Backend)
- Keine Breaking Changes in bestehenden Tool-APIs
- Monitor-Agent Dedup ist programmatisch — kein LLM-Call im Hot-Path

---

## Redis Key-Schema

```
ninko:alerts:active:{alert_id}    → JSON, TTL 7d (604800s)
ninko:alerts:history:{alert_id}   → JSON, TTL 30d (optional)
ninko:alerts:notify:{alert_id}    → empty, TTL = cooldown (z.B. 24h)
```

**Alert-ID Konvention:** `{module}:{resource}:{reason}` (lowercase, sanitized)

**Beispiele pro Modul:**
- Kubernetes: `kubernetes:nginx-deployment:crashloopbackoff`
- Proxmox: `proxmox:vm-100:stopped`
- Linux: `linux:server-prod:disk-usage-high`
- Docker: `docker:api-container:exited`
- OPNsense: `opnsense:firewall-service:stopped`
- Pi-hole: `pihole:gravity:update-failed`

**Generiert via** `AlertStateManager.make_id(module, resource, reason)` — lowercase, Sonderzeichen entfernt

**Active-Alert JSON:**
```json
{
  "alert_id": "kubernetes:nginx-deployment:crashloopbackoff",
  "module": "kubernetes",
  "resource": "nginx-deployment",
  "reason": "crashloopbackoff",
  "severity": "critical",
  "summary": "Pod nginx-deployment crashed",
  "ticket_id": "",
  "status": "active",
  "first_seen": "2026-04-08T10:00:00Z",
  "last_seen": "2026-04-08T12:00:00Z",
  "last_notified": "2026-04-08T10:00:00Z",
  "notify_count": 1
}
```

**Notification-Cooldown via `ninko:alerts:notify:{alert_id}`:**
- `SET ... NX EX {cooldown_seconds}` — atomar
- Wenn Key existiert → Cooldown aktiv → nicht erneut notifizieren
- Wenn Key nicht existiert → SET gelingt → Notification erlaubt

---

## Execution

### Task 1: AlertStateManager erstellen

**Datei:** `backend/core/alert_state.py`

**Implementierung:**
```python
class AlertStateManager:
    ACTIVE_PREFIX = "ninko:alerts:active:"
    HISTORY_PREFIX = "ninko:alerts:history:"
    NOTIFY_PREFIX = "ninko:alerts:notify:"
    DEFAULT_TTL = 604800      # 7 Tage
    HISTORY_TTL = 2592000     # 30 Tage
    DEFAULT_COOLDOWN = 86400  # 24 Stunden

    @staticmethod
    def make_id(module: str, resource: str, reason: str) -> str:
        """Deterministische Alert-ID: lowercase, nur alphanumerisch + Bindestrich."""

    async def get_state(self, alert_id: str) -> dict | None:
        """Gibt den aktiven Alert zurück oder None."""

    async def is_active(self, alert_id: str) -> bool:
        """Schneller Existenz-Check (Redis EXISTS)."""

    async def record(self, alert_id: str, *, module: str, severity: str,
                     summary: str, resource: str = "", reason: str = "",
                     ticket_id: str = "") -> dict:
        """Speichert oder aktualisiert einen Alert. Atomar via SET NX für Erstanlage."""

    async def resolve(self, alert_id: str, resolution: str = "") -> bool:
        """Verschiebt Alert von active -> history. Idempotent."""

    async def should_notify(self, alert_id: str, cooldown_seconds: int = DEFAULT_COOLDOWN) -> bool:
        """Atomarer Cooldown-Check via SET NX EX. True = darf notifizieren."""

    async def list_active(self, module: str | None = None) -> list[dict]:
        """Alle aktiven Alerts (optional gefiltert nach Modul)."""
```

**Akzeptanzkriterien:**
- [ ] `make_id("kubernetes", "nginx-deployment", "CrashLoopBackOff")` → `"kubernetes:nginx-deployment:crashloopbackoff"`
- [ ] `record()` erstellt Alert mit allen Metadaten + TTL
- [ ] `is_active()` gibt `True` für existierenden Alert
- [ ] `should_notify()` gibt `True` beim ersten Mal, `False` innerhalb Cooldown
- [ ] `resolve()` löscht aus active, archiviert in history
- [ ] `list_active()` gibt alle aktiven Alerts zurück

---

### Task 2: Monitor-Agent Deduplication

**Datei:** `backend/agents/monitor_agent.py`

**Änderungen:**
1. Import `AlertStateManager` + Singleton in `__init__`
2. In `run_cycle()`, vor `publish_event`:

```python
# Neu: Dedup-Check
alert_id = AlertStateManager.make_id(
    module=module_name,
    resource=module_name,  # Health-Check hat keine feinere Resource
    reason=status.get("detail", "error")[:50],
)

if await self._alert_mgr.is_active(alert_id):
    # Alert bereits getrackt — nur last_seen aktualisieren
    await self._alert_mgr.record(
        alert_id, module=module_name, severity="critical",
        summary=f"Health-Check fehlgeschlagen: {module_name}",
    )
    logger.debug("Alert %s bereits aktiv, überspringe.", alert_id)
    continue

# Neuer Alert — normal weiterverarbeiten
await self._alert_mgr.record(
    alert_id, module=module_name, severity="critical",
    summary=f"Health-Check fehlgeschlagen: {module_name}",
)
await self._redis.publish_event(alert)
await self._memory.store_incident(...)
```

3. Nach der Health-Check-Schleife: aktive Alerts prüfen ob Module wieder OK sind → auto-resolve:

```python
# Auto-Resolve: Module die wieder OK sind
active_alerts = await self._alert_mgr.list_active(module=None)
for active in active_alerts:
    m = active.get("module", "")
    if m in results and results[m].get("status") != "error":
        await self._alert_mgr.resolve(active["alert_id"], resolution="Health-Check OK")
        logger.info("Alert %s auto-resolved.", active["alert_id"])
```

**Wichtig:** `_attempt_remediation()` soll NICHT durch Dedup blockiert werden — Remediation-Versuche sollen weiterlaufen. Nur `publish_event` + `store_incident` werden dedupliziert.

**Akzeptanzkriterien:**
- [ ] Erster Fehler eines Moduls → Alert + PubSub + Incident (wie bisher)
- [ ] Folge-Zyklen mit gleichem Fehler → kein neuer PubSub, kein neuer Incident
- [ ] Modul wird wieder OK → Alert auto-resolved

---

### Task 3: LLM-Tools implementieren

**Datei:** `backend/agents/alert_tools.py` (neue Datei)

3 Tools als `@tool` dekorierte async Funktionen:

**Tool 1: `check_alert_state`**
```python
@tool
async def check_alert_state(alert_id: str) -> str:
    """
    Prueft den Status eines Alerts anhand seiner ID.
    Gibt zurueck ob der Alert aktiv ist, wann er zuerst gesehen wurde,
    und wie oft bereits benachrichtigt wurde.
    Parameter: alert_id — z.B. 'kubernetes:nginx-deployment:crashloopbackoff'
    """
```
- Rein lesend, keine Seiteneffekte
- Returns: JSON-String mit `exists`, `state`, `first_seen`, `notify_count`

**Tool 2: `record_alert`**
```python
@tool
async def record_alert(
    alert_id: str, module: str, severity: str, summary: str,
    ticket_id: str = "",
) -> str:
    """
    Zeichnet einen neuen Alert auf oder aktualisiert einen bestehenden.
    Verwende dieses Tool um ein erkanntes Problem zu dokumentieren,
    bevor eine Benachrichtigung gesendet wird.
    """
```
- Schreibend — NICHT in `_TOOL_READONLY`
- Prüft Cooldown intern: gibt `should_notify: true/false` im Response mit zurück
- Returns: JSON-String mit Alert-State + `should_notify` Flag

**Tool 3: `resolve_alert`**
```python
@tool
async def resolve_alert(alert_id: str, resolution: str = "") -> str:
    """
    Markiert einen Alert als gelöst. Der Alert wird aus den aktiven Alerts entfernt
    und in die Historie verschoben. Idempotent — kein Fehler wenn Alert nicht existiert.
    """
```
- Schreibend — NICHT in `_TOOL_READONLY`
- Returns: JSON-String mit `resolved: true/false`, `was_active: true/false`

---

### Task 4: Orchestrator + Safeguard Integration

**Datei:** `backend/agents/orchestrator.py`

**Änderungen:**
1. Import der 3 Tools aus `agents.alert_tools`:
```python
from agents.alert_tools import (
    check_alert_state,
    record_alert,
    resolve_alert,
)
```

2. Tools zur `tools=[...]` Liste in `__init__` hinzufügen

**Datei:** `backend/core/safeguard.py`

**Änderungen:**
- `check_alert_state` zu `_TOOL_READONLY` hinzufügen (read-only)
- `record_alert` und `resolve_alert` NICHT hinzufügen (schreibend)

**Akzeptanzkriterien:**
- [ ] Alle 3 Tools sind im Orchestrator registriert
- [ ] `check_alert_state` ist in `_TOOL_READONLY`

---

### Task 5: Tests

**Datei:** `backend/test_alert_state.py`

**Unit-Tests (mit Mock-Redis):**
- `test_make_id_deterministic` — gleiche Inputs = gleiche ID
- `test_make_id_sanitization` — Sonderzeichen werden entfernt
- `test_record_new_alert` — Alert wird korrekt gespeichert
- `test_record_existing_alert_updates_last_seen` — last_seen wird aktualisiert
- `test_is_active_true` / `test_is_active_false`
- `test_resolve_active_alert` — verschiebt von active zu history
- `test_resolve_nonexistent_idempotent` — kein Fehler
- `test_should_notify_first_time` — True (kein Cooldown-Key)
- `test_should_notify_within_cooldown` — False
- `test_list_active_all` / `test_list_active_filtered`

**Integration-Test (gegen laufenden Redis):**
- Full-Flow: `record` → `is_active` → `should_notify(True)` → `should_notify(False)` → `resolve` → `is_active(False)`

---

### Task 6: Generischer Smart-Alerts Skill

**Datei:** `backend/skills/smart-alerts/SKILL.md`

**Frontmatter:**
```yaml
---
name: smart-alerts
description: Alert-Deduplication für alle Module - Kubernetes Pod-Failures Proxmox VMs Docker Container Linux Systemfehler Benachrichtigung Cooldown Remediation
modules: [kubernetes, proxmox, linux, docker, opnsense, pihole, email]
---
```

**Inhalt — Generische Patterns:**

1. **Kubernetes Deployment Failure**
   - Alert-ID: `kubernetes:{deployment_name}:{reason}` (Deployment-Level, nicht Pod-Instance!)
   - `{reason}` = `CrashLoopBackOff`, `ImagePullBackOff`, `NotReady`, etc.
   - Workflow: check → remediation (rolling restart) → notify if `should_notify` → resolve on recovery

2. **Proxmox VM Stopped**
   - Alert-ID: `proxmox:vm-{vmid}:stopped`
   - Workflow: check VM status → attempt restart → notify → resolve when running

3. **Linux Server — Disk Usage**
   - Alert-ID: `linux:server-{hostname}:disk-usage-{threshold}` (z.B. `disk-usage-90`)
   - Workflow: check usage → cleanup attempts → notify → resolve when below threshold

4. **Docker Container Exit**
   - Alert-ID: `docker:container-{name}:{exit_code}`
   - Workflow: check container status → restart → notify → resolve when healthy

5. **OPNsense Service Down**
   - Alert-ID: `opnsense:service-{name}:stopped`
   - Workflow: check service → restart attempt → notify → resolve when running

6. **Pi-hole Gravity Update Failed**
   - Alert-ID: `pihole:gravity:update-failed`
   - Workflow: check gravity status → attempt update → notify → resolve

**Gemeinsames Pattern:**
```
1. Erkennung (Monitor oder Scheduler)
2. check_alert_state(alert_id) — existiert bereits?
3. if new: record_alert(...) mit Cooldown-Check
4. if should_notify: Email/Ticket versenden
5. Remediation-Versuch starten (parallel, nicht blockierend)
6. Auf Recovery warten → resolve_alert()
```

**Referenz:** `backend/skills/kubernetes-incident-response/SKILL.md` — bestehendes Skill-Format

---

### Task 7: REST-API Endpoint für aktive Alerts (Frontend Phase)

**Datei:** `backend/api/routes_alerts.py` (neue Datei)

**Endpoints:**
```
GET  /api/alerts           → Liste aller aktiven Alerts
POST /api/alerts/{id}/resolve  → Manuelles Resolven aus dem Dashboard
```

**Response-Format (GET /api/alerts):**
```json
{
  "alerts": [
    {
      "alert_id": "kubernetes:nginx-deployment:crashloopbackoff",
      "module": "kubernetes",
      "severity": "critical",
      "summary": "Pod nginx crashed",
      "status": "active",
      "first_seen": "2026-04-08T10:00:00Z",
      "last_seen": "2026-04-08T12:00:00Z",
      "notify_count": 3
    }
  ],
  "total": 1
}
```

**Router-Registrierung:** In `main.py` — `app.include_router(alerts_router)` vor dem StaticFiles-Mount.

---

### Task 8: Frontend — Settings-Panel "Alerts"

**Datei:** `frontend/index.html`

Neuen Alert-Tab in `#subnav-settings` + `#settings-panel-alerts` mit Tabelle.

**Datei:** `frontend/app.js`

- `_alertsCache: []` — in-memory Store
- `loadAlerts()` — fetcht `GET /api/alerts`, renders Tabelle
- `resolveAlert(alertId)` — `POST /api/alerts/{id}/resolve`
- `_handleWsAlert()` — WebSocket live-update Handler

**Datei:** `frontend/style.css`

CSS-Klassen für `.alerts-table`, `.alert-severity-*` Badges, etc.

---

### Task 9: Frontend i18n

**Dateien:** `frontend/i18n/*.json` (alle 10 Sprachen)

Alert-bezogene Keys: `alerts.title`, `alerts.critical`, `alerts.warning`, etc.

---

## Commit-Strategie

| Commit | Message | Dateien |
|--------|---------|---------|
| 1 | `feat(core): Add AlertStateManager for Redis-based alert tracking` | `backend/core/alert_state.py` |
| 2 | `feat(monitor): Add alert deduplication to health-check cycle` | `backend/agents/monitor_agent.py` |
| 3 | `feat(tools): Add alert state tools for workflow deduplication` | `backend/agents/alert_tools.py`, `backend/agents/orchestrator.py`, `backend/core/safeguard.py` |
| 4 | `test(alerts): Add unit and integration tests` | `backend/test_alert_state.py` |
| 5 | `docs(skills): Add generic smart-alerts skill` | `backend/skills/smart-alerts/SKILL.md` |
| 6 | `feat(api): Add REST endpoints for alert management` | `backend/api/routes_alerts.py`, `backend/main.py` |
| 7 | `feat(frontend): Add alerts table to Settings panel` | `frontend/index.html`, `frontend/app.js`, `frontend/style.css`, `frontend/i18n/*.json` |

---

## Verifikation

```bash
# 1. Unit-Tests
cd /home/sb/github/ninko/backend && python -m pytest test_alert_state.py -v

# 2. Linting
cd /home/sb/github/ninko/backend && ruff check core/alert_state.py agents/alert_tools.py

# 3. Docker Build
cd /home/sb/github/ninko && docker compose build backend

# 4. Manueller Redis-Check (nach einem Monitor-Zyklus)
redis-cli KEYS "ninko:alerts:*"
```

---

## Was dieser Plan NICHT macht

- **Kein Kubernetes-spezifischer Skill** — der `smart-alerts` Skill ist modul-agnostisch mit Beispielen für alle unterstützten Module
- **Keine REST-API Endpoints für LLM-Tools** — `@tool`-Funktionen sind LangChain-Tools, keine HTTP-Endpoints
- **Keine separate Notification-Queue** — Cooldown-Management ist atomar via Redis `SET NX EX`
