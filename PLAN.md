# Ninko Improvement Backlog — gefilterte Prioritäten

Basierend auf crewAI-Analyse + kritischer Bewertung.
Nur Punkte die echten Mehrwert liefern, keine Architektur-Aufblähung.

---

## Phase 1 — Muss haben

### 1. Tool-Usage Events & Audit Trail

**Warum:** Heute keine Ahnung was wann aufgerufen wurde. "Wer hat Pod X gelöscht?" → unlösbar. Basis für Cost Tracking (Phase 2).

**`core/events.py` — neues Modul:**

```python
from __future__ import annotations
import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

@dataclass
class ToolEvent:
    agent_name: str
    tool_name: str
    args: dict
    session_id: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    duration_ms: float = 0.0
    result_size: int = 0
    error: str | None = None
    is_readonly: bool = False

_listeners: list = []

async def emit(event: ToolEvent) -> None:
    for fn in _listeners:
        try:
            await fn(event)
        except Exception:
            pass

def on_tool_event(fn) -> None:
    _listeners.append(fn)
```

**`core/audit.py` — Redis-Persistenz:**

```python
from core.events import ToolEvent, on_tool_event
from core.redis_client import get_redis

async def _persist(event: ToolEvent) -> None:
    redis = get_redis()
    key = f"ninko:audit:tools:{datetime.utcnow().strftime('%Y-%m-%d')}"
    await redis.connection.lpush(key, json.dumps(vars(event)))
    await redis.connection.ltrim(key, 0, 9999)   # 10k Events/Tag
    await redis.connection.expire(key, 86400 * 7)  # 7 Tage TTL

on_tool_event(_persist)
```

**`agents/base_agent.py` — Callback bei Tool-Execution:**

LangGraph Callbacks (`on_tool_start`/`on_tool_end`) nutzen — analog zum `StepTrackingHandler` im `DataAnalysisSubagent`. Dabei `session_id` aus `status_bus.get_session_id()` lesen (bereits via ContextVar verfügbar).

**API:** `GET /api/audit/tools?date=2026-04-09&agent=kubernetes` → gefilterte Events.

**Dashboard:** Neues Panel in Settings → Logs → "Tool-Audit" Tabelle mit Spalten: Zeit, Agent, Tool, Args (gekürzt), Dauer, Fehler.

**Hinweis:** Redis-Liste ist kein Langzeit-Archiv. Für >30 Tage Retention später Loki/Elasticsearch anschließen — aber das ist kein Blocker für den Start.

---

### 3. Memory: Composite Scoring

**Warum:** Altes Rauschen verdrängt aktuelle wichtige Facts. IT-Ops ist zeitkritisch — "der Server war gestern down" ist relevanter als "vor 3 Monaten".

**Implementierung:**

`core/memory.py` — `SemanticMemory.query()` erweitern:

```python
import math
from datetime import datetime

def _composite_score(
    distance: float,      # ChromaDB: 0.0 = identisch, 2.0 = maximal verschieden
    stored_at_iso: str,
    importance: float = 0.5,
    alpha: float = 0.5,   # Gewicht Semantic Similarity
    beta: float = 0.3,    # Gewicht Recency
    gamma: float = 0.2,   # Gewicht Importance
    decay_lambda: float = 0.05,  # Halbwertszeit ~14 Tage
) -> float:
    semantic = 1.0 - (distance / 2.0)
    try:
        stored = datetime.fromisoformat(stored_at_iso)
        age_days = (datetime.utcnow() - stored).days
    except Exception:
        age_days = 0
    recency = math.exp(-decay_lambda * max(age_days, 0))
    return alpha * semantic + beta * recency + gamma * importance
```

**Query-Anpassung:**

```python
def query(self, text: str, top_k: int = 5, category: str | None = None) -> list[str]:
    # Schritt 1: ChromaDB Top-20 (nicht Top-K) holen
    raw = self._collection.query(
        query_texts=[text],
        n_results=min(top_k * 4, 20),
        include=["documents", "distances", "metadatas"],
    )
    # Schritt 2: Composite Score berechnen
    scored = []
    for doc, dist, meta in zip(raw["documents"][0], raw["distances"][0], raw["metadatas"][0]):
        score = _composite_score(
            distance=dist,
            stored_at_iso=meta.get("stored_at", datetime.utcnow().isoformat()),
            importance=float(meta.get("importance", 0.5)),
        )
        scored.append((score, doc))
    # Schritt 3: Re-rank → Top-K zurückgeben
    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]
```

**Beim Speichern — Metadaten ergänzen:**

```python
collection.add(
    documents=[text],
    metadatas=[{
        "stored_at": datetime.utcnow().isoformat(),
        "importance": importance,  # 0.0–1.0
        "category": category or "general",
    }],
    ids=[uid],
)
```

**Auto-Importance in `_auto_memorize()`:**

LLM-Prompt leicht erweitern um einen Importance-Score mitzugeben:
```
Antworte NUR mit JSON: {"fact": "...", "importance": 0.8}
importance: 1.0 = kritisch (Systemausfall), 0.5 = normal, 0.2 = trivial
```

**Performance-Note:** Re-ranking auf max. 20 Ergebnissen — kein messbarer Overhead. Erst bei >50k Memories relevantes Thema, dann Sharding via Category-Filter.

---

## Phase 2 — Optional (wenn Zeit)

### 4. LLM Cost Tracking

**Warum:** Nur relevant bei Cloud-Providern (OpenRouter, Groq, Heimaker). Bei lokalem Ollama/LM Studio irrelevant. Baut auf Tool-Usage Events (Phase 1, Punkt 2) auf.

**Implementierung:**

Token-Counts kommen aus `response.usage_metadata` (LangChain Standard). In `llm_factory.py` einen Tracking-Wrapper um `get_llm()` legen:

```python
class _TokenTrackingLLM:
    """Wrapper der Token-Usage nach jedem LLM-Call loggt."""
    
    def __init__(self, llm, agent_name: str = ""):
        self._llm = llm
        self._agent_name = agent_name
    
    async def ainvoke(self, messages, **kwargs):
        result = await self._llm.ainvoke(messages, **kwargs)
        usage = getattr(result, "usage_metadata", None)
        if usage and _is_cloud_provider():
            await _record_tokens(self._agent_name, usage)
        return result
```

**Redis:** `ninko:metrics:tokens:YYYY-MM-DD` → Hash mit `{agent_name: {prompt, completion, cost_usd}}`.

**Preise:** Im LLM-Provider Settings-Objekt `cost_per_1k_input` und `cost_per_1k_output` konfigurierbar (Default: 0.0 für lokale Provider).

**API:** `GET /api/metrics/tokens?since=2026-04-01` → Aggregat pro Agent + Gesamtkosten.

---

### 5. AgentCard — nur ModuleManifest-Erweiterung

**Warum:** Bessere Metadaten für Orchestrator-Routing. Nicht die komplette A2A-Spezifikation — nur `agent_capabilities` im Manifest.

**Implementierung:**

`core/module_registry.py` — `ModuleManifest` erweitern:

```python
@dataclass
class ModuleManifest:
    # ...bestehende Felder...
    agent_capabilities: list[str] = field(default_factory=list)
    # Beispiel Kubernetes: ["pod management", "log streaming", "scaling", "namespace monitoring"]
    # Beispiel Jira: ["ticket search", "issue creation", "sprint management", "reporting"]
```

`orchestrator.py` — `_build_module_descriptions()` nutzt `agent_capabilities`:

```python
# Statt nur description + 5 keywords:
desc = manifest.description
caps = ", ".join(manifest.agent_capabilities[:6])
keywords = ", ".join(manifest.routing_keywords[:5])
return f"{name}: {desc}\n  Fähigkeiten: {caps}\n  Keywords: {keywords}"
```

`GET /api/agents/cards` — neuer Endpoint der alle Manifests als strukturierte Cards zurückgibt (für externe Integrationen).

---

## Phase 3 — Später (konkrete Use-Cases)

### OpenProject + Redmine: Management-Report-Workflow

**Use-Case:** Agent analysiert ein Projekt (OpenProject), erstellt Sub-Tasks, spiegelt Tickets nach Redmine, generiert einen Management-Summary als PDF und sendet ihn per E-Mail. Aktualisiert das Gantt basierend auf eingetragenen Zeiten.

**Was heute funktioniert (Tier-4 Pipeline):**
- Sub-Tasks aus Projektbeschreibung vorschlagen → `create_openproject_work_package`
- Tickets in Redmine erstellen → `create_redmine_issue`
- Auslastung Teammitglieder analysieren → `get_redmine_user_hours_report` + `list_openproject_time_entries` (guter DataAnalysisSubagent-Kandidat)
- Bericht per E-Mail senden → `send_email` mit `attachments=[...]`

**Was fehlt — 2 Lücken:**

**Lücke 1: PDF-Generierung**

Keine PDF-Bibliothek im Backend. `send_email` kann PDFs anhängen, aber niemand erstellt sie.

Neues Core-Tool in `agents/core_tools.py`:

```python
@tool
async def generate_pdf_report(
    title: str,
    content_markdown: str,
    output_path: str = "/tmp/ninko-reports/report.pdf",
) -> str:
    """
    Erstellt ein PDF aus Markdown-Inhalt.
    Gibt den absoluten Pfad zur PDF-Datei zurück (für send_email attachments).
    Nutzt weasyprint (Markdown → HTML → PDF).
    """
```

`backend/Dockerfile` — Abhängigkeit hinzufügen:
```dockerfile
RUN pip install weasyprint markdown
# weasyprint braucht auch: apt-get install -y libpango-1.0-0 libpangoft2-1.0-0
```

Output-Verzeichnis: `/tmp/ninko-reports/` — kein PVC nötig, Files leben nur für den Send-Vorgang.

**Lücke 2: OpenProject Gantt-Aktualisierung**

`update_openproject_work_package` kennt nur `status` und `subject`. Gantt braucht `start_date`, `due_date`, `done_ratio`.

Erweiterung in `modules_catalog/openproject/tools.py`:

```python
async def update_openproject_work_package(
    work_package_id: int,
    status: str = "",
    subject: str = "",
    start_date: str = "",   # ISO 8601: "2026-04-10"
    due_date: str = "",     # ISO 8601: "2026-04-30"
    done_ratio: int = -1,   # 0–100, -1 = nicht ändern
    connection_id: str = "",
) -> str:
```

OpenProject berechnet das Gantt-Diagramm aus genau diesen Feldern — ohne sie bleibt das Gantt statisch.

Außerdem `lockVersion` beachten: OpenProject's PATCH-Endpoint erfordert die aktuelle `lockVersion` um Konflikte zu erkennen. Vor dem Update `get_openproject_work_package` aufrufen und `lockVersion` aus der Response lesen.

**Aufwand:** Klein (2–3 Tage). Kein neues Modul — nur Tool-Erweiterungen + Dockerfile-Zeile.

**Kein neues Modul nötig:** Der Workflow läuft als Tier-4 Pipeline. Orchestrator erkennt multi-step (OpenProject + Redmine + Email) → plant Sub-Steps → ruft die jeweiligen Module-Agents auf. Kein separater "Report-Agent" erforderlich.

---

## Entschieden: Weglassen

| Punkt | Grund |
|-------|-------|
| Skills `allowed_tools` | Vermischt Wissen (Skills = SystemMessage) mit Permissions (SafeGuard). Modul-Agenten haben bereits nur ihre eigenen Tools — die Isolation existiert schon. Whitelist würde autonomes Handeln blockieren (Skill sagt "starte Pod neu", Tool ist aber gesperrt). |
| Knowledge Base | Redundant — Skills + Soul + Tools decken das bereits ab. Wer pflegt statische Kubernetes-Docs? |
| Workflow DSL (`@router`/`@listen`) | Zweites Workflow-System neben dem Canvas-Editor. Wartungssplit. |
| Async Context Management | ContextVars in asyncio sind tricky bei concurrent Requests — Context-Bleeding-Risiko. Aktueller expliziter Parameter-Passing funktioniert. |
| Skills Progressive Disclosure | Zu wenig Impact. Kaum ein SKILL.md hat >300 Zeilen. Parser-Aufwand nicht gerechtfertigt. |
| OpenTelemetry | Over-engineering. Erst sinnvoll bei echtem Multi-Tenant-Enterprise-Betrieb mit distributed Tracing zwischen Microservices. |
