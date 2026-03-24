# Kumio

**Modulare, KI-gestützte IT-Operations-Plattform**

Kumio verbindet einen lokalen LLM mit deiner Infrastruktur. Stelle Fragen im Chat, starte Workflows und lass Agenten eigenständig Aufgaben erledigen — ohne dass Daten dein Netzwerk verlassen.

[![Version](https://img.shields.io/badge/version-0.5.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## Features

- **Chat-Interface** – Natürlichsprachliche Steuerung deiner gesamten IT-Infrastruktur
- **15 integrierte Module** – Kubernetes, Proxmox, GLPI, FritzBox, Pi-hole, Home Assistant, IONOS DNS, Docker, WordPress und mehr
- **4-stufiges Orchestrator-Routing** – Direkt / Modul-Agent / Dynamischer Agent / Pipeline
- **Langzeitgedächtnis** – ChromaDB-backed Semantic Memory über alle Sitzungen hinweg
- **Lokale LLMs** – Ollama, LM Studio oder beliebige OpenAI-kompatible API (kein Cloud-Zwang)
- **Workflow-Engine** – Visueller DAG-Editor für automatisierte Abläufe
- **Dynamische Agenten** – KI erstellt zur Laufzeit spezialisierte Agenten
- **Skills-System** – Wiederverwendbares Prozesswissen als SKILL.md-Dateien
- **TTS/STT** – Piper (lokal) + Whisper für Sprach-Ein- und -Ausgabe
- **Telegram Bot** – Vollständiger Fernzugriff per Messenger inkl. Sprachnachrichten
- **Mehrsprachig** – 10 Sprachen, automatisch per Sprache des Nutzers gewählt
- **Plugin-System** – ZIP-installierbare Module ohne Neustart

---

## Schnellstart (Docker Compose)

### Voraussetzungen

- Docker + Docker Compose
- Ein laufendes LLM-Backend: [Ollama](https://ollama.ai) oder [LM Studio](https://lmstudio.ai)

### 1. Repository klonen

```bash
git clone https://github.com/natorus87/kumio.git
cd kumio
```

### 2. Konfiguration anlegen

```bash
cp .env.example .env
# .env öffnen und SQLITE_SECRETS_KEY setzen:
# python3 -c "import secrets; print(secrets.token_hex(32))"
```

### 3. Stack starten

```bash
docker compose up -d
```

Das Dashboard ist unter **http://localhost:8000** erreichbar.

Beim ersten Start unter **Einstellungen → LLM-Provider** das gewünschte Backend konfigurieren (Ollama, LM Studio oder OpenAI-kompatibel).

---

## Architektur

```
┌──────────────────────────────────────────────────────┐
│                    Kumio Dashboard                   │
│   Chat  │  Kubernetes  │  Proxmox  │  GLPI  │  ...  │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│               Orchestrator Agent                     │
│  Tier 1: Direkt │ Tier 2: Modul │ Tier 3: Dynamisch │
│                    Tier 4: Pipeline                  │
└──────────────────────┬───────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────┐
│                 Module Registry                      │
│        Auto-Discovery · backend/modules/             │
└──────┬──────────┬──────────┬──────────┬─────────────┘
       │          │          │          │
  Kubernetes  Proxmox     GLPI      + 12 weitere Module
       │          │          │
┌──────▼──────────▼──────────▼──────────────────────┐
│  LLM-Factory  │  ChromaDB  │  Redis  │  Vault/SQLite │
│  (Ollama/LMS) │  (Memory)  │ (Cache) │   (Secrets)   │
└──────────────────────────────────────────────────────┘
```

### Kernprinzip

Der Core-Code enthält **keine Modul-Namen**. Jedes Modul registriert sich beim Start selbst über sein `module_manifest`. Um ein neues Modul hinzuzufügen, genügt ein neuer Ordner unter `backend/modules/`.

---

## Module

| Modul | Beschreibung |
|---|---|
| `kubernetes` | Cluster-Management, Pods, Deployments, Logs, Auto-Remediation |
| `proxmox` | VMs, LXC-Container, Backups, Snapshots, Node-Status |
| `glpi` | Helpdesk-Tickets, Assets, ITSM-Workflows |
| `ionos` | DNS-Zonen und Record-Management via IONOS Hosting API |
| `fritzbox` | Netzwerkstatus, externe IP, WLAN, verbundene Geräte |
| `homeassistant` | Smart-Home: Licht, Heizung, Sensoren, Automatisierungen |
| `pihole` | Pi-hole v6: Blocking, Statistiken, Query-Log, Custom DNS |
| `web_search` | SearXNG-basierte Websuche (Bing, Mojeek, Qwant) |
| `telegram` | Bot mit Voice-Transkription und TTS-Antworten |
| `email` | SMTP-Versand und IMAP-Abruf |
| `wordpress` | Posts, Medien, Seiten via WordPress REST API |
| `codelab` | Code-Ausführung und Debugging |
| `docker` | Container-Management via Docker API |
| `linux_server` | Server-Administration via SSH |
| `image_gen` | KI-Bildgenerierung |

Module werden per Umgebungsvariable aktiviert:

```env
KUMIO_MODULE_KUBERNETES=true
KUMIO_MODULE_PROXMOX=true
# usw.
```

---

## Konfiguration

Alle Einstellungen können über die Web-UI unter **Einstellungen** vorgenommen werden. Modul-Verbindungsdaten (API-Keys, Tokens, Passwörter) werden verschlüsselt im SQLite-Vault gespeichert.

### Wichtige Umgebungsvariablen

| Variable | Standard | Beschreibung |
|---|---|---|
| `LLM_BACKEND` | `ollama` | LLM-Provider: `ollama`, `lmstudio`, `openai_compatible` |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama-Endpunkt |
| `VAULT_FALLBACK` | `sqlite` | Secrets-Backend: `sqlite` oder Vault |
| `SQLITE_SECRETS_KEY` | — | Verschlüsselungsschlüssel (Pflicht) |
| `LANGUAGE` | `de` | Standard-Antwortsprache |
| `MAX_OUTPUT_TOKENS` | `16384` | Maximale Antwortlänge in Tokens |

Vollständige Vorlage: [.env.example](.env.example)

---

## Eigenes Modul entwickeln

Jedes Modul besteht aus:

```
backend/modules/meinmodul/
├── __init__.py       ← exportiert module_manifest, agent, router
├── manifest.py       ← ModuleManifest mit routing_keywords
├── agent.py          ← BaseAgent-Subklasse
├── tools.py          ← @tool-Funktionen (LangChain)
├── routes.py         ← FastAPI APIRouter
└── frontend/
    ├── tab.html
    └── tab.js
```

**manifest.py** (Mindestbeispiel):

```python
from backend.core.module_registry import ModuleManifest

module_manifest = ModuleManifest(
    name="meinmodul",
    display_name="Mein Modul",
    description="Beschreibung für LLM-Routing",
    version="1.0.0",
    routing_keywords=["meinmodul", "spezifischer-begriff"],
    api_prefix="/api/meinmodul",
    dashboard_tab={"id": "meinmodul", "label": "Mein Modul", "icon": "🔧"},
    health_check=lambda: {"status": "ok"},
)
```

**agent.py**:

```python
from backend.agents.base_agent import BaseAgent
from backend.modules.meinmodul.tools import mein_tool

class MeinModulAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="meinmodul",
            system_prompt="Du bist Spezialist für Mein Modul.",
            tools=[mein_tool],
        )
```

**Aktivieren**:

```env
KUMIO_MODULE_MEINMODUL=true
```

Kumio erkennt das Modul beim nächsten Start automatisch — kein Core-Code muss angepasst werden.

---

## Deployment (Kubernetes)

Kubernetes-Manifeste liegen unter `k8s/`. Das Produktions-Image ist auf Docker Hub verfügbar.

```bash
# 1. Namespace anlegen
kubectl apply -f k8s/namespace.yaml

# 2. Secret mit eigenem Key anlegen
# k8s/backend/secret.yaml editieren (REPLACE_WITH_YOUR_SQLITE_SECRETS_KEY ersetzen)
kubectl apply -f k8s/backend/secret.yaml

# 3. Deployment ausrollen
kubectl apply -f k8s/backend/
kubectl apply -f k8s/redis/
kubectl apply -f k8s/chromadb/

# Status prüfen
kubectl -n kumio get pods -w
```

### Eigenes Image bauen

```bash
docker compose build backend
docker tag kumio-backend:latest your-registry/kumio-backend:latest
docker push your-registry/kumio-backend:latest
```

> Piper TTS wird nur bei `--build-arg INSTALL_PIPER=true` eingebaut. `docker compose build` erledigt das automatisch.

---

## Entwicklung

```bash
# Stack lokal starten
docker compose up -d

# Nach Python- oder Frontend-Änderungen neu bauen
docker compose build backend && docker compose up -d --no-deps backend

# Tests ausführen
python backend/test_services.py
python backend/test_monitor.py
```

Lokales Backend ohne Docker:

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

---

## Sicherheit

- **Lokale KI**: Alle LLM-Aufrufe bleiben im eigenen Netz (Ollama/LM Studio). Keine Daten gehen an externe Dienste, es sei denn, ein OpenAI-kompatibler externer Provider wird explizit konfiguriert.
- **Secrets**: Verschlüsselt via HashiCorp Vault oder lokalem SQLite-Fallback. Nie im Klartext im Dateisystem.
- **Destruktive Aktionen**: `PROXMOX_CONFIRM_DESTRUCTIVE=true` (Standard) — der Agent fragt vor dem Ausführen nach.
- **Nur internes Netz**: Kumio ist nicht für öffentliche Exposition ausgelegt. Traefik/Nginx mit TLS und ggf. Auth-Middleware vorschalten.
- **`.env` nicht committen**: Die Datei ist in `.gitignore` enthalten. Vorlage: `.env.example`.

---

## Changelog

Siehe [CHANGELOG.md](CHANGELOG.md).

---

## Lizenz

[MIT](LICENSE)
