# Kumio Module: Template (🧩)

Dieses Verzeichnis dient als strukturierte Vorlage für die Entwicklung brandneuer Kumio Module.
Kopiere einfach den Ordner `_template` und benenne ihn um.

---

## Erste Schritte

1. Ordner `_template` → umbenennen (z.B. `nextcloud`)
2. In allen Dateien `template` / `_template` → durch neuen Namen ersetzen
3. `manifest.py` → alle Parameter anpassen (`name`, `display_name`, `routing_keywords`, `api_prefix`)
4. `required_secrets` im Manifest definieren
5. **Alle unten stehenden Integrationsschritte durchführen** (⚠️ Ohne diese Schritte funktioniert das Modul nicht!)

---

## Pflicht-Dateien pro Modul

```
backend/modules/<name>/
├── __init__.py        # Exports: module_manifest, agent, router
├── manifest.py        # ModuleManifest mit Metadaten
├── agent.py           # BaseAgent Subclass mit Tools
├── tools.py           # @tool Funktionen (LangChain)
├── routes.py          # FastAPI APIRouter (optional)
└── frontend/
    ├── tab.html       # Dashboard-Tab HTML (mit <style>-Block für cl-select)
    └── tab.js         # Dashboard-Tab JavaScript (globales Objekt, kein ES-Modul)
```

---

## ⚠️ Integrationsschritte (PFLICHT nach Modul-Erstellung)

Das Modul-System hat mehrere **hardcoded Stellen** in Core-Dateien, die manuell ergänzt werden müssen:

### 1. `frontend/app.js` — ACTION_FIELDS (Verbindungs-Formular)

Damit das Modul ein Verbindungsformular in den Einstellungen bekommt, trage es in `ACTION_FIELDS` ein:

```js
// frontend/app.js, Zeile ~1490 (ACTION_FIELDS Objekt)
meinmodul: [
    { key: 'url', label: 'Server URL', placeholder: 'https://example.com' },
    { key: 'api_key', label: 'API-Key', placeholder: '••••••', type: 'password', isSecret: true },
],
```

### 2. `frontend/app.js` — getTabObject() (Tab-Initialisierung)

Damit `MeinModulTab.init()` aufgerufen wird, trage das globale JS-Objekt in die Map ein:

```js
// frontend/app.js, Zeile ~330 (getTabObject Funktion)
'meinmodul': typeof MeinModulTab !== 'undefined' ? MeinModulTab : null,
```

### 3. `docker-compose.yml` — Env-Var aktivieren

```yaml
environment:
    KUMIO_MODULE_MEINMODUL: "true"
```

### 4. `k8s/backend/deployment.yaml` — Env-Var aktivieren

```yaml
- name: KUMIO_MODULE_MEINMODUL
  value: "true"
```

### 5. `backend/api/routes_settings.py` — Secret & Env-Registrierung

**Secret-Keys** (für Vault-Speicherung):
```python
# _get_secret_keys(), Zeile ~250
"meinmodul": ["MEINMODUL_API_KEY"],
```

**Env-Connection-Mappings** (Fallback-Env-Variablen):
```python
# _get_env_connection(), Zeile ~230
"meinmodul": ["MEINMODUL_URL"],
```

### 6. `backend/agents/base_agent.py` — _TOOL_LABELS (Status-Spinner)

Damit der Chat-Spinner die richtigen Texte zeigt wenn ein Tool läuft:

```python
# _TOOL_LABELS Dict, nach den letzten Einträgen einfügen:
"beispiel_tool": ("Führe Beispiel aus",  "Running example"),
"lade_daten":    ("Lade Daten",          "Loading data"),
```

---

## Architektur-Prinzipien

- **Keine direkten Cross-Module Aufrufe**: Module sollten absolut unabhängig voneinander existieren. Kommuniziere über Redis PubSub, Semantic Memory, oder den Orchestrator (über Chat).
- **Werkzeuge (Tools)**: Der LLM Agent kann beliebig viele `@tool`-Funktionen aus `tools.py` nutzen. **Die Docstrings sind überlebenswichtig** — das LLM liest sie und entscheidet welches Tool es aufruft.
- **Connection Manager**: Tools rufen `_get_api_client(connection_id)` auf, um Config aus Redis + Vault zu laden. Fallback auf Env-Variablen wenn kein UI-Connection existiert.

---

## Mehrsprachigkeit (DE/EN)

Das System unterstützt DE und EN über die `LANGUAGE`-Env-Variable.

### System-Prompt (`agent.py`)

Nutze `_t(de, en)` aus `base_agent.py` für den System-Prompt:

```python
from agents.base_agent import BaseAgent, _t

SYSTEM_PROMPT = _t(
    de="Du bist der Spezialist für ...",
    en="You are the specialist for ...",
)
```

**NICHT** `"Antworte immer auf Deutsch"` ins System-Prompt schreiben — `base_agent.py` injiziert die Sprachanweisung automatisch aus `LANGUAGE`.

### Tool-Docstrings (`tools.py`)

Tool-Docstrings werden vom LLM zur Tool-Auswahl gelesen. Empfehlung: Beide Sprachen im Docstring angeben:

```python
@tool
async def beispiel_tool(parameter: str, connection_id: str = "") -> str:
    """
    Führt eine Beispielaktion aus. Nutze dieses Tool wenn der User nach X fragt.
    Runs an example action. Use this tool when the user asks about X.
    """
```

### Status-Labels (`base_agent._TOOL_LABELS`)

Für den Lade-Spinner im Chat müssen Tool-Namen in `_TOOL_LABELS` als `(DE, EN)` Tuple eingetragen werden (siehe Integrationsschritt 6).

---

## Dashboard UI (Frontend)

### Kein nativer `<select>`

Native `<select>`-Elemente ignorieren CSS-Variablen im Dark-Theme. Stattdessen `cl-select` div-Pattern verwenden — Vorlage ist in `tab.html` und `tab.js` enthalten.

### Kein ES-Modul-Syntax

**Niemals `import` oder `export`** in `tab.js` — die Datei wird per `<script>`-Tag ohne `type="module"` geladen.

### Tab-Objekt-Pattern

Es gibt zwei Varianten abhängig davon, ob das Modul ein **Core-Modul** (ins Image gebacken) oder ein **Plugin** (per ZIP installiert) ist.

#### Core-Modul (in `backend/modules/`)

Definiere ein globales Objekt und trage es in `app.js:getTabObject()` ein (Integrationsschritt 2):

```js
// tab.js — globales Objekt
const MeinModulTab = {
    async init() { /* ... */ },
    async refresh() { /* ... */ },
    destroy() { /* ... */ },
};
```

#### Plugin (per ZIP installiert, in `backend/plugins/`)

Plugins können `getTabObject()` nicht editieren. Stattdessen im globalen Plugin-Tab-Registry registrieren:

```js
// tab.js — Plugin-Registrierung via Kumio._pluginTabs
const MeinPluginTab = {
    async init() { /* ... */ },
    async refresh() { /* ... */ },
    destroy() { /* ... */ },
};

// Am Ende der tab.js eintragen — Kumio ruft dann init() beim Tab-Wechsel auf:
if (typeof Kumio !== 'undefined') {
    Kumio._pluginTabs['mein_plugin'] = MeinPluginTab;
}
```

Der Tab-ID muss mit dem `dashboard_tab.id` im Manifest übereinstimmen.

### Event-Delegation

Kein `onclick` in HTML-Strings. Stattdessen `data-action` + Listener im Tab-Objekt:

```html
<button data-action="meinmodul-refresh">Aktualisieren</button>
```

```js
_setupEvents() {
    document.getElementById('meinmodul-tab-content')
        ?.addEventListener('click', (e) => {
            const action = e.target.closest('[data-action]')?.dataset.action;
            if (action === 'meinmodul-refresh') this.refresh();
        });
},
```

### Icons

- Modul-Tab-Icon im Manifest: **Emoji** (z.B. `"🧩"`)
- Aktions-Buttons in der UI: **Inline SVG mit `currentColor`** oder Emoji
- Kein FontAwesome, keine externen Icon-Libraries

### `connection_id` bei jedem API-Call

```js
const res = await fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`);
```

---

## `invoke()` Tuple-Return

`BaseAgent.invoke()` gibt `tuple[str, bool]` zurück. Alle Aufrufer müssen entpacken:

```python
# Richtig:
response, _ = await agent.invoke(message, session_id)

# Falsch (ValueError: too many values to unpack):
response = await agent.invoke(message, session_id)
```

---

## Deployment

```bash
# 1. Bauen & lokal starten
docker compose build backend
docker compose up -d --no-deps backend

# 2. Auf Docker Hub
docker tag kumio-backend:latest natorus87/kumio-backend:latest
docker push natorus87/kumio-backend:latest

# 3. Kubernetes Rollout
kubectl rollout restart deployment/kumio-backend -n kumio
kubectl rollout status deployment/kumio-backend -n kumio --timeout=120s
```

> **WICHTIG**: Jede Änderung an Python ODER Frontend-Dateien erfordert einen kompletten Build-Zyklus. Frontend-Dateien sind ins Docker-Image gebacken — `docker restart` reicht NICHT.
