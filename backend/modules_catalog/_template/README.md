# Ninko Module: Template (🧩)

This directory is the reference template for new catalog modules.
Copy the `_template` folder, rename it, and follow the checklist below.

---

## Getting Started

1. Copy `_template/` → `backend/modules_catalog/<name>/`
2. Replace every occurrence of `template` / `_template` with the new module name
3. `manifest.py` → adjust `name`, `display_name`, `description`, `routing_keywords`, `api_prefix`, `dashboard_tab`
4. Define `required_secrets` in the manifest
5. **Complete all integration steps below** (⚠️ Without these steps the module will not work in the Marketplace!)

---

## Required Files

```
backend/modules_catalog/<name>/
├── __init__.py        # Exports: module_manifest, agent, router
├── manifest.py        # ModuleManifest with metadata
├── agent.py           # BaseAgent subclass with tools
├── tools.py           # @tool functions (LangChain)
├── routes.py          # FastAPI APIRouter (optional)
└── frontend/
    ├── tab.html       # Dashboard tab HTML
    └── tab.js         # Dashboard tab JS (plugin registration pattern, no ES modules)
```

> **Import rule**: All internal imports must be **relative** (`from .tools import …`).
> Never use absolute imports (`from modules.name.tools import …`) — they break when the
> module is installed as a plugin under `backend/plugins/<name>/`.

---

## ⚠️ Integration Steps (REQUIRED after module creation)

### 1. `backend/modules_catalog/catalog.json` — register in Marketplace

Add the module to the catalog index so the Marketplace can list it **without hitting the GitHub API rate limit**:

```json
{
  "name": "mymodule",
  "display_name": "My Module",
  "description": "Short description used by the LLM for routing.",
  "version": "1.0.0",
  "author": "Ninko Team"
}
```

Add this entry to the `"modules"` array in `backend/modules_catalog/catalog.json` (keep sorted alphabetically).

> Without this entry the module will not appear in the Marketplace module list.

---

### 2. `frontend/app.js` — ACTION_FIELDS (connection form in Settings)

```js
// frontend/app.js — ACTION_FIELDS object
mymodule: [
    { key: 'url', label: 'Server URL', placeholder: 'https://example.com' },
    { key: 'MY_API_KEY', label: 'API Key', placeholder: '••••••', type: 'password', isSecret: true },
],
```

> Without this entry the module shows "Lade Verbindungen…" forever in Settings → Modules.

---

### 3. `backend/api/routes_settings.py` — secret & env registration

**Secret keys** (fields stored in Vault, identified by suffix `_KEY`, `_TOKEN`, `_PASSWORD`, `_SECRET`):
```python
# _get_secret_keys()
"mymodule": ["MY_API_KEY"],
```

**Env fallback** (env vars read when no UI connection is configured):
```python
# _get_env_connection()
"mymodule": ["MYMODULE_URL"],
```

---

### 4. `backend/core/safeguard.py` — _TOOL_READONLY (read-only tools)

Register all **read-only** tools in the `_TOOL_READONLY` frozenset so they skip the safeguard confirmation:

```python
# _TOOL_READONLY frozenset
"get_mymodule_status",
"list_mymodule_items",
```

Rule: `get_*`, `list_*`, `search_*`, `inspect_*`, `check_*` → add here.
`create_*`, `delete_*`, `restart_*`, `set_*` → do NOT add (require confirmation).

---

### 5. `backend/agents/base_agent.py` — _TOOL_LABELS (chat spinner text)

```python
# _TOOL_LABELS dict
"get_mymodule_status": ("Prüfe Status",   "Checking status"),
"list_mymodule_items": ("Lade Einträge",  "Loading items"),
```

---

## tab.js — Plugin Registration Pattern

Catalog modules are **always installed as plugins**. They cannot edit `app.js:getTabObject()`.
Use the `Ninko._pluginTabs` registry instead:

```js
const MyModuleTab = {
    async init() { /* called when tab is first activated */ },
    async refresh() { /* called on manual refresh */ },
    destroy() { /* cleanup on tab switch */ },
};

if (typeof Ninko !== 'undefined') {
    Ninko._pluginTabs['mymodule'] = MyModuleTab;
}
```

The key (`'mymodule'`) must match `dashboard_tab.id` in `manifest.py`.

---

## Architecture Principles

- **Relative imports only**: `from .tools import …`, never `from modules.name.tools import …`
- **No cross-module imports**: Modules must be self-contained. Use Redis PubSub, Semantic Memory, or the Orchestrator for inter-module communication.
- **Tool docstrings matter**: The LLM reads them to decide which tool to call. Be precise.
- **Connection Manager**: `await ConnectionManager.get_default_connection("mymodule")` loads config from Redis + Vault. Falls back to env vars.

---

## Multilingual Support

Use `_t(de, en)` from `base_agent.py` in `agent.py`:

```python
from .tools import my_tool
from agents.base_agent import BaseAgent, _t

SYSTEM_PROMPT = _t(
    de="Du bist der Spezialist für My Module.",
    en="You are the specialist for My Module.",
)
```

Never write `"Antworte immer auf Deutsch"` — language injection is handled automatically by `base_agent.py`.

---

## Deployment (after adding to modules_catalog)

Catalog modules are installed at runtime via the Marketplace — **no image rebuild required**.

```bash
# Commit catalog.json update + module files
git add backend/modules_catalog/<name>/ backend/modules_catalog/catalog.json
git commit -m "feat(<name>): add catalog module"
git push origin main

# Users install via: Settings → Marketplace → [Ninko Official] → Module laden → Installieren
```

> If you also modified core files (`app.js`, `routes_settings.py`, `safeguard.py`, `base_agent.py`),
> a full build cycle is required:
> ```bash
> docker compose build backend && docker compose up -d --no-deps backend
> docker tag ninko-backend:latest natorus87/ninko-backend:latest && docker push natorus87/ninko-backend:latest
> docker tag ninko-backend:latest natorus87/kumio-backend:latest && docker push natorus87/kumio-backend:latest
> kubectl rollout restart deployment/kumio-backend -n kumio
> ```
