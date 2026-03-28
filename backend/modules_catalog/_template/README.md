# Ninko Module: Template (🧩)

This directory serves as a structured template for developing new Ninko modules.
Simply copy the `_template` folder and rename it.

---

## Getting Started

1. Rename folder `_template` (e.g. to `nextcloud`)
2. Replace `template` / `_template` with the new name in all files
3. `manifest.py` → adjust all parameters (`name`, `display_name`, `routing_keywords`, `api_prefix`)
4. Define `required_secrets` in the manifest
5. **Complete all integration steps below** (⚠️ Without these steps the module will not work!)

---

## Required Files per Module

```
backend/modules/<name>/
├── __init__.py        # Exports: module_manifest, agent, router
├── manifest.py        # ModuleManifest with metadata
├── agent.py           # BaseAgent subclass with tools
├── tools.py           # @tool functions (LangChain)
├── routes.py          # FastAPI APIRouter (optional)
└── frontend/
    ├── tab.html       # Dashboard tab HTML (with <style> block for cl-select)
    └── tab.js         # Dashboard tab JavaScript (global object, no ES modules)
```

---

## ⚠️ Integration Steps (REQUIRED after module creation)

The module system has several **hardcoded locations** in core files that must be updated manually:

### 1. `frontend/app.js` — ACTION_FIELDS (connection form)

To give the module a connection form in Settings, add it to `ACTION_FIELDS`:

```js
// frontend/app.js, line ~1490 (ACTION_FIELDS object)
mymodule: [
    { key: 'url', label: 'Server URL', placeholder: 'https://example.com' },
    { key: 'api_key', label: 'API Key', placeholder: '••••••', type: 'password', isSecret: true },
],
```

### 2. `frontend/app.js` — getTabObject() (tab initialization)

For `MyModuleTab.init()` to be called, register the global JS object in the map:

```js
// frontend/app.js, line ~330 (getTabObject function)
'mymodule': typeof MyModuleTab !== 'undefined' ? MyModuleTab : null,
```

### 3. `docker-compose.yml` — enable env var

```yaml
environment:
    NINKO_MODULE_MYMODULE: "true"
```

### 4. `k8s/backend/deployment.yaml` — enable env var

```yaml
- name: NINKO_MODULE_MYMODULE
  value: "true"
```

### 5. `backend/api/routes_settings.py` — secret & env registration

**Secret keys** (for Vault storage):
```python
# _get_secret_keys(), line ~250
"mymodule": ["MYMODULE_API_KEY"],
```

**Env connection mappings** (fallback env variables):
```python
# _get_env_connection(), line ~230
"mymodule": ["MYMODULE_URL"],
```

### 6. `backend/agents/base_agent.py` — _TOOL_LABELS (status spinner)

For the chat spinner to show the correct text while a tool is running:

```python
# _TOOL_LABELS dict, append after the last entries:
"example_tool":  ("Führe Beispiel aus",  "Running example"),
"load_data":     ("Lade Daten",          "Loading data"),
```

---

## Architecture Principles

- **No direct cross-module calls**: Modules must be completely independent of each other. Communicate via Redis PubSub, Semantic Memory, or the Orchestrator (via chat).
- **Tools**: The LLM agent can use any number of `@tool` functions from `tools.py`. **Docstrings are critical** — the LLM reads them to decide which tool to call.
- **Connection Manager**: Tools call `_get_api_client(connection_id)` to load config from Redis + Vault. Falls back to env variables if no UI connection exists.

---

## Multilingual Support (DE/EN)

The system supports DE and EN via the `LANGUAGE` env variable.

### System Prompt (`agent.py`)

Use `_t(de, en)` from `base_agent.py` for the system prompt:

```python
from agents.base_agent import BaseAgent, _t

SYSTEM_PROMPT = _t(
    de="Du bist der Spezialist für ...",
    en="You are the specialist for ...",
)
```

**Never** write `"Antworte immer auf Deutsch"` into the system prompt — `base_agent.py` injects language instructions automatically from the `LANGUAGE` env var.

### Tool Docstrings (`tools.py`)

Tool docstrings are read by the LLM to select the right tool. Recommended: include both languages in the docstring:

```python
@tool
async def example_tool(parameter: str, connection_id: str = "") -> str:
    """
    Führt eine Beispielaktion aus. Nutze dieses Tool wenn der User nach X fragt.
    Runs an example action. Use this tool when the user asks about X.
    """
```

### Status Labels (`base_agent._TOOL_LABELS`)

Tool names must be registered in `_TOOL_LABELS` as `(DE, EN)` tuples for the loading spinner in chat (see integration step 6).

---

## Dashboard UI (Frontend)

### No native `<select>`

Native `<select>` elements ignore CSS variables in dark mode. Use the `cl-select` div pattern instead — the template is included in `tab.html` and `tab.js`.

### No ES module syntax

**Never use `import` or `export`** in `tab.js` — the file is loaded via a `<script>` tag without `type="module"`.

### Tab object pattern

There are two variants depending on whether the module is a **core module** (baked into the image) or a **plugin** (installed via ZIP).

#### Core module (in `backend/modules/`)

Define a global object and register it in `app.js:getTabObject()` (integration step 2):

```js
// tab.js — global object
const MyModuleTab = {
    async init() { /* ... */ },
    async refresh() { /* ... */ },
    destroy() { /* ... */ },
};
```

#### Plugin (installed via ZIP, in `backend/plugins/`)

Plugins cannot edit `getTabObject()`. Register via the global plugin tab registry instead:

```js
// tab.js — plugin registration via Ninko._pluginTabs
const MyPluginTab = {
    async init() { /* ... */ },
    async refresh() { /* ... */ },
    destroy() { /* ... */ },
};

// Add at the end of tab.js — Ninko will call init() when the tab is activated:
if (typeof Ninko !== 'undefined') {
    Ninko._pluginTabs['my_plugin'] = MyPluginTab;
}
```

The tab ID must match the `dashboard_tab.id` in the manifest.

### Event delegation

No `onclick` in HTML strings. Use `data-action` attributes with a listener in the tab object:

```html
<button data-action="mymodule-refresh">Refresh</button>
```

```js
_setupEvents() {
    document.getElementById('mymodule-tab-content')
        ?.addEventListener('click', (e) => {
            const action = e.target.closest('[data-action]')?.dataset.action;
            if (action === 'mymodule-refresh') this.refresh();
        });
},
```

### Icons

- Module tab icon in manifest: **emoji** (e.g. `"🧩"`)
- Action buttons in the UI: **inline SVG with `currentColor`** or emoji
- No FontAwesome, no external icon libraries

### `connection_id` on every API call

```js
const res = await fetch(`${this.API_PREFIX}/status${this.getQueryParams()}`);
```

---

## `invoke()` Tuple Return

`BaseAgent.invoke()` returns `tuple[str, bool]`. All callers must unpack:

```python
# Correct:
response, _ = await agent.invoke(message, session_id)

# Wrong (ValueError: too many values to unpack):
response = await agent.invoke(message, session_id)
```

---

## Deployment

```bash
# 1. Build & start locally
docker compose build backend
docker compose up -d --no-deps backend

# 2. Push to Docker Hub
docker tag ninko-backend:latest natorus87/ninko-backend:latest
docker push natorus87/ninko-backend:latest

# 3. Kubernetes rollout
kubectl rollout restart deployment/ninko-backend -n ninko
kubectl rollout status deployment/ninko-backend -n ninko --timeout=120s
```

> **IMPORTANT**: Every change to Python OR frontend files requires a full build cycle. Frontend files are baked into the Docker image — `docker restart` is NOT sufficient.
