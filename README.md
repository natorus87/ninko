# Kumio – KI-Agenten-Plattform für IT-Automation

```
┌─────────────────────────────────────────────────────────────┐
│                     Kumio Dashboard                      │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌────────────┐  │
│  │   Chat   │  │    ☸     │  │   🖥     │  │    🎫      │  │
│  │  (Core)  │  │   K8s    │  │ Proxmox  │  │   GLPI     │  │
│  └──────────┘  └──────────┘  └──────────┘  └────────────┘  │
│        │              │            │              │          │
│  ┌─────┴──────────────┴────────────┴──────────────┴──────┐  │
│  │                   Orchestrator Agent                   │  │
│  │            (Routing via Module Registry)               │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌───────────────────────┴───────────────────────────────┐  │
│  │                   Module Registry                      │  │
│  │     discover_and_load() → Register Agents, Routes     │  │
│  └───────────────────────┬───────────────────────────────┘  │
│                          │                                   │
│  ┌──────────┬────────────┼────────────┬──────────────────┐  │
│  │  Ollama  │  ChromaDB  │   Redis    │      Vault       │  │
│  │  (LLM)   │ (Memory)  │  (Cache)   │    (Secrets)     │  │
│  └──────────┘────────────┘────────────┘──────────────────┘  │
└─────────────────────────────────────────────────────────────┘

Module-Verzeichnis:
  modules/
  ├── kubernetes/    ← Auto-Discovery
  ├── proxmox/       ← Auto-Discovery
  ├── glpi/          ← Auto-Discovery
  ├── telegram/      ← Auto-Discovery
  ├── email/         ← Auto-Discovery
  ├── codelab/       ← Auto-Discovery
  ├── qdrant/        ← Auto-Discovery
  └── <dein_modul>/  ← Einfach Ordner anlegen!
```

## Inhaltsverzeichnis

- [Systemvoraussetzungen](#systemvoraussetzungen)
- [Setup in 5 Schritten](#setup-in-5-schritten)
- [Architektur](#architektur)
- [Module](#module)
- [Eigenes Modul entwickeln](#eigenes-modul-entwickeln)
- [Beispiel-Chateingaben](#beispiel-chateingaben)
- [Proxmox API-Token erstellen](#proxmox-api-token-erstellen)
- [Sicherheitshinweise](#sicherheitshinweise)
- [Production-Härtung](#production-härtung)

---

## Systemvoraussetzungen

| Komponente          | Minimum              | Empfohlen            |
|---------------------|----------------------|----------------------|
| Kubernetes          | 1.27+                | 1.29+                |
| GPU-Node            | NVIDIA GPU (4GB+)    | NVIDIA GPU (8GB+)    |
| NVIDIA GPU Operator | Installiert           | Installiert          |
| kubectl             | 1.27+                | 1.29+                |
| Kustomize           | 5.0+                 | In kubectl integriert|
| RAM (Cluster)       | 8 GB                 | 16 GB+               |
| Storage             | 20 GB PV             | 50 GB+ PV            |

### Software-Abhängigkeiten

- **Ollama / LM Studio / OpenAI** – Flexible LLM-Backends (Multi-Provider Support)
- **ChromaDB (0.4.24)** – Vektor-Datenbank für Semantic Memory
- **Redis** – Working Memory, PubSub-Events und Capped Logs
- **Vault** (oder SQLite-Fallback) – Secrets-Management
- **Traefik Ingress** (lokal) – Routing für Kubernetes (kumio.conbro.local)

---

## Setup in 5 Schritten

### 1. Repository klonen

```bash
git clone https://github.com/natorus87/kumio.git
cd kumio
```

### 2. GPU-Node labeln

```bash
kubectl label node <GPU-NODE-NAME> gpu=true
```

### 3. Namespace und Secrets vorbereiten

```bash
# Namespace erstellen
kubectl apply -f k8s/namespace.yaml

# Secret-Werte anpassen
cp .env.example .env
# Editiere .env mit deinen Werten

# Secrets erstellen (Werte in k8s/backend/secret.yaml eintragen)
# Oder via Vault nach dem Deployment konfigurieren
```

### 4. Backend-Image bauen und pushen

```bash
cd backend
docker build -t your-registry/kumio-backend:latest .
docker push your-registry/kumio-backend:latest
```

### 5. Deployment via Kustomize

```bash
kubectl apply -k k8s/
```

Prüfe den Status:

```bash
kubectl -n kumio get pods -w
```
Das Dashboard ist nach erfolgreichem Deployment über Traefik Ingress unter `http://kumio.conbro.local` erreichbar (DNS/Hosts-Eintrag für `kumio.conbro.local` auf die Ingress-IP setzen).

---

## Architektur

### Kernprinzip: Modulare Architektur

Kumio besteht aus einem **unveränderlichen Core** und beliebig vielen **austauschbaren Modulen**.

**Grundregel:** Der Core-Code wird **niemals** für ein neues Modul angepasst. Ein Modul bringt alles mit, was es braucht, und registriert sich selbst. Um ein neues Modul hinzuzufügen, genügt es, einen neuen Ordner unter `modules/` anzulegen – der Rest passiert automatisch.

### Core-Komponenten

| Komponente          | Beschreibung                                          |
|---------------------|-------------------------------------------------------|
| `config.py`         | Pydantic BaseSettings für Core-Konfiguration          |
| `module_registry.py`| Auto-Discovery und Verwaltung aller Module            |
| `memory.py`         | ChromaDB Semantic Memory (Incidents, Runbooks, **Langzeitgedächtnis**)  |
| `redis_client.py`   | Redis Working Memory + PubSub-Events                  |
| `vault.py`          | Secrets Store (Vault oder SQLite-Fallback)            |
| `context_manager.py`| Context Budget Management + Token-Reset               |
| `llm_factory.py`    | Backend-Factory: Ollama / LM Studio / Multi-Provider |
| `workflow_engine.py`| Asynchrone DAG-Execution für komplexe Abläufe         |
| `log_handler.py`    | Zentraler RedisLogHandler für Echtzeit-Einsicht      |
| `scheduler_agent.py`| Autonome Aufgabenplanung (CronJobs, Workflows)       |

### Agenten

| Agent               | Rolle                                                 |
|---------------------|-------------------------------------------------------|
| `BaseAgent`         | Abstrakte Basis – alle Agenten erben hiervon. Beinhaltet Auto-Memorize (ChromaDB) nach jeder Antwort. |
| `OrchestratorAgent` | Routing via ModuleRegistry (keine hardcodierten Namen). Besitzt Memory-Tools: `remember_fact`, `recall_memory`, `forget_fact`, `confirm_forget`. |
| `MonitorAgent`      | Background-Monitoring, Health-Checks aller Module     |
| `TaskAgent`         | Benutzerdefinierte Aufgaben-Spezialisten (Agenten-Tab)|

### Modul-Kommunikation

Module dürfen sich **niemals** direkt importieren. Kommunikation läuft über:

1. **Redis PubSub Events** – Asynchrone Benachrichtigungen zwischen Modulen
2. **Semantic Memory** – Geteiltes Wissen (Incidents, Runbooks)
3. **Orchestrator** – Explizite Delegation via Chat

---

## Module

### Kubernetes (☸)

- Cluster-Status, Pod-Management, Deployment-Skalierung
- Automatische Remediation (CrashLoopBackOff, OOMKilled, etc.)
- Geordnete Restart-Sequenzen mit Dependency-Handling

### Proxmox (🖥)

- VM- und LXC-Container-Management
- Node-Status mit CPU/RAM-Monitoring
- Sicherheits-Bestätigung bei destruktiven Aktionen

### GLPI Helpdesk (🎫)

- Ticket-Erstellung und -Verwaltung
- Automatische Incident-Tickets bei Kubernetes-Alarmen
- SLA-Tracking und Statistiken

### FritzBox (📶)

- Verwaltung von Smart-Home Geräten (DECT)
- Abfragen von Netzwerk- und WAN-Status (externe IP, Bandbreite)
- WLAN-Gastzugang steuern

### Telegram Bot (💬)

- Remote-Zugriff auf Kumio direkt via Telegram Messenger
- Benachrichtigungen bei aktiven Alarmen und Incidents
- Statusabfragen per Chat von unterwegs
### Geplante Abläufe, Automatisierung & UI (⚙️)

- **Workflow-Editor**: Visuelles Design von Automatisierungsketten (Trigger → Agent → Condition).
- **Zentrale Logs**: Echtzeit-Aggregation aller System- und Modul-Logs.
- **Benutzerdefinierte Agenten**: Erstelle Spezialisten mit eigenem System-Prompt und gezielter Tool-Auswahl.
- **Multilingual UI (i18n)**: Die Oberfläche und alle KI-Antworten unterstützen nahtlos 10 Sprachen (u.a. Deutsch, Englisch, Französisch, Spanisch, Niederländisch, Japanisch), direkt umschaltbar in den Einstellungen.

---

## Eigenes Modul entwickeln

### Schritt-für-Schritt: Beispiel-Modul "CheckMK"

#### 1. Verzeichnis anlegen

```bash
mkdir -p backend/modules/checkmk/frontend
```

#### 2. Manifest erstellen (`manifest.py`)

```python
from backend.core.module_registry import ModuleManifest


async def check_checkmk_health() -> dict:
    """Health-Check für CheckMK-Verbindung."""
    try:
        # Deine Health-Check-Logik
        return {"status": "ok", "detail": "CheckMK erreichbar"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


module_manifest = ModuleManifest(
    name="checkmk",
    display_name="CheckMK",
    description="CheckMK Monitoring Integration",
    version="1.0.0",
    author="Dein Name",
    enabled_by_default=True,
    env_prefix="CHECKMK_",
    required_secrets=["CHECKMK_API_SECRET"],
    optional_secrets=[],
    routing_keywords=[
        "checkmk", "monitoring", "host", "service",
        "alarm", "downtime", "acknowledge"
    ],
    api_prefix="/api/checkmk",
    dashboard_tab={"id": "checkmk", "label": "CheckMK", "icon": "📊"},
    health_check=check_checkmk_health,
)
```

#### 3. Tools implementieren (`tools.py`)

```python
from langchain_core.tools import tool


@tool
async def get_host_status(hostname: str) -> dict:
    """Gibt den Status eines CheckMK-Hosts zurück."""
    # Deine Implementierung
    pass


@tool
async def list_alerts() -> list:
    """Listet aktive Alarme in CheckMK auf."""
    pass
```

#### 4. Agent erstellen (`agent.py`)

```python
from backend.agents.base_agent import BaseAgent
from backend.modules.checkmk.tools import get_host_status, list_alerts


class CheckmkAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="checkmk",
            system_prompt=(
                "Du bist der CheckMK-Spezialist von Kumio. "
                "Du überwachst Hosts und Services via CheckMK."
            ),
            tools=[get_host_status, list_alerts],
        )
```

#### 5. Routes erstellen (`routes.py`)

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def checkmk_status():
    return {"status": "ok"}
```

#### 6. Frontend (`frontend/tab.html` + `tab.js`)

#### 7. `__init__.py`

```python
from backend.modules.checkmk.manifest import module_manifest
from backend.modules.checkmk.agent import CheckmkAgent
from backend.modules.checkmk.routes import router

agent = CheckmkAgent()
```

#### 8. Aktivieren

```env
KUMIO_MODULE_CHECKMK=true
```

**Fertig!** Kumio erkennt das neue Modul automatisch beim nächsten Start.

---

## Beispiel-Chateingaben

### Kubernetes

```
"Zeige mir alle failing Pods im Namespace production"
"Starte den Pod backend-api-7f8d9 im Namespace default neu"
"Skaliere das Deployment frontend auf 5 Replicas"
"Was ist der Status des Clusters?"
"Führe einen Rollout-Restart für das Deployment payment-service durch"
```

### Proxmox

```
"Liste alle VMs auf Node pve-01"
"Starte die VM 105 auf Node pve-01"
"Wie ist der Status von Node pve-02?"
"Zeige mir die letzten Tasks auf pve-01"
"Die VM 200 hängt – kannst du sie zurücksetzen?"
```

### GLPI Helpdesk

```
"Erstelle ein Ticket: Server backup-srv antwortet nicht, Priorität hoch"
"Zeige mir alle offenen Tickets mit Priorität hoch"
"Was ist der Status von Ticket #1234?"
"Füge eine Notiz zu Ticket #567 hinzu: Problem wurde durch Neustart behoben"
"Schließe Ticket #890 mit der Lösung: Festplatte wurde getauscht"
```

### FritzBox

```
"Wie ist meine externe IP-Adresse?"
"Wie ist die aktuelle Download-Rate?"
"Schalte das Gast-WLAN ein."
"Zeige mir alle verbundenen Smart-Home Geräte an."
```

### Telegram Bot

(Wird im Hintergrund als Interface genutzt, Befehle innerhalb von Telegram:)
```
/start oder /clear - Löscht deine bisherige Chat-Historie und setzt das Gedächtnis von Kumio zurück.
"Zeige mir den aktuellen Status des Kubernetes Clusters"
```

### Automatisierung & System
```
"Liste alle konfigurierten Workflows auf"
"Starte den Workflow 'Nightly-Backup'"
"Zeige mir die letzten Error-Logs der letzten 15 Minuten"
"Welche Agenten sind aktuell aktiv?"
```

### Langzeitgedächtnis
```
"Merke dir: Der Pi-hole läuft auf 192.168.1.10"
"Weißt du noch, welche IP der Pi-hole hat?"
"Vergiss, dass der Pi-hole auf 192.168.1.10 läuft"
"Was weißt du über unsere Infrastruktur?"
```

---

## Proxmox API-Token erstellen

### 1. In Proxmox Web-UI einloggen

Navigiere zu **Datacenter → Permissions → API Tokens**.

### 2. Token erstellen

- **User**: `root@pam` (oder einen dedizierten User)
- **Token ID**: `kumio`
- **Privilege Separation**: Deaktivieren (für vollen Zugriff) oder spezifische Rechte vergeben

### 3. Token-Werte notieren

Nach der Erstellung bekommst du:
- **Token ID**: `root@pam!kumio`
- **Secret**: `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`

### 4. In Kumio konfigurieren

```env
PROXMOX_HOST=192.168.1.10
PROXMOX_USER=root@pam
PROXMOX_TOKEN_ID=kumio
# Token Secret im Vault speichern:
# Vault-Path: secret/kumio/PROXMOX_TOKEN_SECRET
```

### 5. Minimale Rechte (Production)

Erstelle einen dedizierten User mit nur den nötigen Rechten:

```
PVEVMAdmin  → VM-Management
PVEAuditor  → Lese-Zugriff auf Nodes
```

---

## Sicherheitshinweise

### Secrets-Management

- **Niemals** Secrets in `.env` Dateien auf dem Cluster speichern
- Nutze **HashiCorp Vault** für alle sensiblen Daten
- SQLite-Fallback nur für Entwicklungsumgebungen
- `SQLITE_SECRETS_KEY` muss ein starker Schlüssel sein

### Destruktive Aktionen

- `PROXMOX_CONFIRM_DESTRUCTIVE=true` ist Standard – destruktive Aktionen erfordern Chat-Bestätigung
- `MONITOR_AUTO_REMEDIATE=false` ist Standard – automatische Remediation muss explizit aktiviert werden
- Alle Eingriffe werden als Incidents im Semantic Memory protokolliert

### Netzwerk

- Kumio sollte **nur im internen Netzwerk** erreichbar sein
- Ingress mit TLS terminieren (Let's Encrypt oder internes CA)
- RBAC: ServiceAccount mit minimalen Cluster-Rechten

### LLM-Sicherheit

- Alle LLM-Aufrufe laufen **lokal** (Ollama/LM Studio) – keine Daten verlassen das Netzwerk
- Context-Reset verhindert Token-Overflow und Prompt-Injection-Eskalation

---

## Production-Härtung

### 1. Resource Limits

Alle Deployments sollten CPU/Memory Requests und Limits haben:

```yaml
resources:
  requests:
    memory: "512Mi"
    cpu: "250m"
  limits:
    memory: "2Gi"
    cpu: "1000m"
```

### 2. Network Policies

Beschränke die Kommunikation zwischen Pods:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: kumio-backend-policy
  namespace: kumio
spec:
  podSelector:
    matchLabels:
      app: kumio-backend
  ingress:
    - from:
        - podSelector:
            matchLabels:
              app: kumio-ingress
  egress:
    - to:
        - podSelector: {}
```

### 3. Pod Security Standards

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
```

### 4. Backup

- ChromaDB PVC regelmäßig sichern (Semantic Memory)
- Vault-Backend sichern
- Redis ist ephemeral – kein Backup nötig

### 5. Monitoring

- Prometheus-Metriken für alle Pods
- Alert-Rules für Pod-Restarts und Resource-Exhaustion
- `MONITOR_INTERVAL_SECONDS` auf 60 senken für kritische Umgebungen

### 6. High Availability

- Backend-Deployment auf 2+ Replicas skalieren
- Redis Sentinel oder Redis Cluster
- ChromaDB mit persistentem Storage

---

## Lizenz

Intern – Kumio IT-Operations Platform

