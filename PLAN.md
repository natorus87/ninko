# Plan: Claude Code Inspirierte Ninko-Verbesserungen

Erstellt: 2026-04-08

## Übersicht

Drei Features inspiriert von Claude Code's Architektur:

1. **Multi-Agent Parallelisierung** — Pipeline-Steps parallel ausführen statt rein sequenziell
2. **Verbesserter Safeguard** — Confidence-Score im Prefilter, Latenz-Metriken, kein unnötiger LLM-Call
3. **Skill-Marketplace** — Remote Skill-Repositories analog zum Modul-Marketplace

---

## Feature 1: Multi-Agent Parallelisierung

### Problem

`run_pipeline()` in [backend/agents/core_tools.py](backend/agents/core_tools.py) (Zeile 859) ist rein sequenziell:
```python
for i, step in enumerate(steps):
    result, _ = await agent.invoke(...)
    context = result  # nächster Step wartet immer
```

Bei unabhängigen Schritten (z.B. "prüfe K8s UND prüfe Pi-hole gleichzeitig") warten Steps unnötig aufeinander.

### Lösung A: `depends_on` in `run_pipeline`

Steps bekommen ein optionales `depends_on: list[int]` Feld (0-basierte Indizes).

**Neue Logik:**
1. Neue Hilfsfunktion `_build_execution_groups(steps)` — topologische Sortierung → `list[list[int]]`
2. Gruppen sequenziell ausführen, Steps innerhalb einer Gruppe via `asyncio.gather()` parallel
3. Context-Merging: Fan-in-Schritt erhält alle Ergebnisse seiner Dependencies zusammengeführt
4. Ohne `depends_on` → bisheriges sequentielles Verhalten (vollständig rückwärtskompatibel)

```python
# Beispiel: K8s + Pi-hole parallel, dann GLPI mit beiden Ergebnissen
steps = [
  {"module": "kubernetes", "task": "Prüfe alle Pods auf Fehler"},
  {"module": "pihole",     "task": "Lade DNS-Fehler-Log", "depends_on": []},
  {"module": "glpi",       "task": "Erstelle Incident", "depends_on": [0, 1]}
]
# Ergebnis: Steps 0+1 laufen parallel, Step 2 wartet auf beide
```

### Lösung B: Neues Tool `run_parallel_pipeline`

Explizites Tool für den Orchestrator mit klarer Fan-out/Fan-in Struktur:

```python
async def run_parallel_pipeline(groups: list[list[dict]]) -> str:
    """
    Führt Gruppen von Steps parallel aus.
    Steps innerhalb einer Gruppe laufen gleichzeitig via asyncio.gather().
    Gruppen werden sequenziell ausgeführt (Output Gruppe N → Input Gruppe N+1).

    Beispiel:
      groups=[
        [{"module": "kubernetes", "task": "Lade Pods"},
         {"module": "pihole",     "task": "Lade DNS-Stats"}],
        [{"module": "glpi", "task": "Erstelle Incident mit K8s+DNS-Ergebnissen"}]
      ]
    """
```

### Geänderte Dateien

| Datei | Änderung |
|-------|---------|
| [backend/agents/core_tools.py](backend/agents/core_tools.py) | `_build_execution_groups()` + `run_pipeline()` erweitern + `run_parallel_pipeline()` neu |
| [backend/agents/orchestrator.py](backend/agents/orchestrator.py) | Tool-Import + System-Prompt mit `run_parallel_pipeline` Hinweis |
| [backend/core/status_bus.py](backend/core/status_bus.py) | Concurrent-Safety prüfen (parallele `emit()` Calls) |

---

## Feature 2: Verbesserter Safeguard

### Problem

- LLM-Call bei **jeder** Nachricht → Latenz 200–800ms extra
- Keyword-Prefilter greift nur bei Messages ≤ 200 Zeichen (Längen-Limit)
- Keine Latenz-Metriken → Performanceprobleme nicht diagnostizierbar
- Kein "Confidence"-Konzept — Prefilter ist binary hit/miss

### Lösung A: Confidence-Score im Prefilter

`_check_keyword_prefilter()` in [backend/core/safeguard.py](backend/core/safeguard.py) wird erweitert um einen Score:

```python
@dataclass
class PrefilterResult:
    hit: bool
    category: ActionCategory | None
    confidence: float  # 0.0–1.0
```

**Schwellenwerte:**

| Confidence | Aktion |
|-----------|--------|
| ≥ 0.95 | LLM überspringen — sofortiges Ergebnis (z.B. "rm -rf", "kubectl delete --all") |
| ≥ 0.70 | LLM-Call mit verkürztem Prompt (`max_tokens=50`, schneller) |
| < 0.70 | Aktueller Full-LLM-Path |

**Längen-Limit entfernen:** Prefilter aktuell auf Messages ≤ 200 Chars begrenzt — entfernen, Prefilter immer zuerst laufen lassen.

### Lösung B: Latenz-Tracking

Neue Felder in `SafeguardResult` ([backend/core/safeguard.py](backend/core/safeguard.py)):

```python
@dataclass
class SafeguardResult:
    requires_confirmation: bool
    category: ActionCategory
    rationale: str
    raw_response: str = ""
    profile_id: str = ""
    auto_decided: bool = False
    auto_decision: str = ""
    latency_ms: float = 0.0     # NEU: Dauer des gesamten Checks
    path_used: str = ""          # NEU: "prefilter_safe" | "prefilter_block" | "llm"
```

Latenz in Redis speichern (`ninko:safeguard:latency`, Capped-List, max 100 Einträge) für Metriken.

### Lösung C: Metriken-Endpoint

Neuer Endpoint in [backend/api/routes_safeguard_audit.py](backend/api/routes_safeguard_audit.py):

```
GET /api/safeguard/metrics
→ {
    "p50_ms": 12.3,
    "p95_ms": 245.1,
    "p99_ms": 612.8,
    "path_breakdown": {
      "prefilter_safe": 423,
      "prefilter_block": 12,
      "llm": 89
    },
    "total_checks": 524
  }
```

### Geänderte Dateien

| Datei | Änderung |
|-------|---------|
| [backend/core/safeguard.py](backend/core/safeguard.py) | `PrefilterResult` Dataclass, Confidence-Score, Längen-Limit entfernen, Latenz-Tracking |
| [backend/api/routes_safeguard_audit.py](backend/api/routes_safeguard_audit.py) | `GET /api/safeguard/metrics` Endpoint |

---

## Feature 3: Skill-Marketplace

### Problem

Skills sind nur lokal (`backend/skills/` oder `data/skills/`). Kein Entdecken, kein Community-Sharing, keine Remote-Repos.

### Lösung: Remote Skill-Repositories (analog Modul-Marketplace)

Das bestehende Modul-Marketplace-System als Blaupause — gleiche Mechanik mit `catalog.json` + HTTP-Download.

### Architektur

**Redis Key:** `ninko:settings:skill_repos` — Liste von Repo-Dicts:
```json
[
  {
    "id": "official",
    "name": "Ninko Official Skills",
    "catalog_url": "https://raw.githubusercontent.com/natorus87/ninko/main/backend/skills/catalog.json",
    "builtin": true
  }
]
```

**Neue Datei `backend/skills/catalog.json`** (Skill-Katalog für Built-in Skills):
```json
{
  "skills": [
    {
      "name": "kubernetes-incident-response",
      "description": "Systematische Diagnose von K8s Pod-Fehlern, CrashLoopBackOff, OOMKilled",
      "modules": ["kubernetes"],
      "skill_url": "https://raw.githubusercontent.com/natorus87/ninko/main/backend/skills/kubernetes-incident-response/SKILL.md",
      "version": "1.0.0",
      "author": "natorus87",
      "tags": ["kubernetes", "incident", "ops"]
    }
  ]
}
```

### Neues Backend-Modul `backend/core/skill_marketplace.py`

```python
class SkillMarketplace:
    async def get_repos(self) -> list[dict]
    async def add_repo(self, repo: dict) -> None
    async def remove_repo(self, repo_id: str) -> None
    async def fetch_catalog(self, catalog_url: str) -> list[dict]
    async def fetch_all_catalogs(self) -> list[dict]     # aggregiert alle Repos
    async def install_from_remote(self, skill_url: str, name: str, modules: list[str]) -> Path
```

### Neue API-Endpoints (in [backend/api/routes_skills.py](backend/api/routes_skills.py) ergänzen)

```
GET  /api/skills/marketplace              → Aggregierter Katalog aller konfigurierten Repos
POST /api/skills/marketplace/install      → { name, skill_url, modules } → installiert in data/skills/
GET  /api/skills/repos                    → Konfigurierte Repos auflisten
POST /api/skills/repos                    → Neues Repo hinzufügen
DELETE /api/skills/repos/{id}             → Repo entfernen (builtin=true → 403)
```

### Frontend-Erweiterung ([frontend/app.js](frontend/app.js))

Im Agenten-Tab → Skills-Panel:
- Neuer Sub-Tab **"Marketplace"** neben "Installiert"
- Card-Grid: Name, Description, Tags, Modules, Install-Button
- Install → Spinner → Toast (Erfolg/Fehler)
- "Repos verwalten"-Button → Modal mit URL-Add/Remove

### Geänderte Dateien

| Datei | Änderung |
|-------|---------|
| `backend/core/skill_marketplace.py` | Neues Modul (Fetch + Install + Repo-Verwaltung) |
| [backend/api/routes_skills.py](backend/api/routes_skills.py) | Marketplace + Repo Endpoints ergänzen |
| `backend/skills/catalog.json` | Neue Datei — Built-in Skill Katalog |
| [backend/main.py](backend/main.py) | SkillMarketplace beim Startup initialisieren |
| [frontend/app.js](frontend/app.js) | Marketplace Sub-Tab im Skills-Panel |

---

## Umsetzungsreihenfolge

### Phase 1: Multi-Agent Parallelisierung
Risikoarm, rückwärtskompatibel, sofortiger Performance-Gewinn bei Multi-Modul-Tasks.

- [x] `_build_execution_groups()` implementieren
- [x] `run_pipeline()` mit `depends_on` Support erweitern
- [x] `run_parallel_pipeline()` als neues Tool
- [x] Orchestrator-System-Prompt aktualisieren (`run_parallel_pipeline` erwähnen)

### Phase 2: Safeguard-Verbesserungen
Konservativ, kein Architektur-Risiko, direkt messbare Latenzverbesserung.

- [x] `PrefilterResult` Dataclass + Confidence-Score Logik
- [x] Längen-Limit (200 chars) im Prefilter entfernen
- [x] `latency_ms` + `path_used` in `SafeguardResult`
- [x] Redis Latenz-Capped-List + `GET /api/safeguard/metrics`

### Phase 3: Skill-Marketplace
Größte User-facing Änderung, benötigt Frontend + Backend.

- [x] `backend/skills/catalog.json` erstellen (alle Built-in Skills eintragen)
- [x] `SkillMarketplace` Klasse implementieren
- [x] API-Endpoints in `routes_skills.py`
- [x] `main.py` Startup-Init
- [x] Frontend Marketplace-Panel

---

## Verifikation

**Feature 1:**
- `run_pipeline` mit Steps `[{kubernetes}, {pihole, depends_on:[]}, {glpi, depends_on:[0,1]}]` → Timing-Logs prüfen, Steps 0+1 müssen gleichzeitig starten
- Ohne `depends_on` → identisches Verhalten wie bisher (Regression-Test)

**Feature 2:**
- `"rm -rf /var/data"` → `path_used="prefilter_block"`, `latency_ms < 5`
- `GET /api/safeguard/metrics` → gibt sinnvolle p50/p95 zurück

**Feature 3:** ✅ **Implementiert & Bereit**
- `GET /api/skills/marketplace` → liefert Built-in Skills aus `catalog.json` (13 Skills)
- `POST /api/skills/marketplace/install` → Skill landet in `data/skills/`, ist danach über `GET /api/skills/` sichtbar
- Frontend: Sub-Tabs "Installiert", "Marketplace", "Repos" verfügbar
- `_esc()` Alias für HTML-Escaping hinzugefügt

---

## Status

**Alle drei Phasen abgeschlossen am 2026-04-08**

| Phase | Feature | Status |
|-------|---------|--------|
| 1 | Multi-Agent Parallelisierung | ✅ Fertig |
| 2 | Safeguard-Verbesserungen | ✅ Fertig |
| 3 | Skill-Marketplace | ✅ Fertig |
