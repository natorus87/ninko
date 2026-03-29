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

## Frontend Design Guidelines

All module tabs must follow these rules. They are enforced in the template since v0.7.1.

---

### Colors — CSS Variables Only

Never hardcode colors. Always use semantic CSS custom properties:

| Token | Purpose |
|-------|---------|
| `var(--bg-primary)` / `--bg-secondary` / `--bg-card` | Backgrounds (page, panel, card) |
| `var(--text-primary)` / `--text-secondary` / `--text-muted` | Text hierarchy |
| `var(--border-color)` / `--border-active` | Borders and dividers |
| `var(--accent-blue)` | Primary interaction / active state |
| `var(--accent-green)` | Success / running state |
| `var(--accent-red)` | Error / failing state |
| `var(--accent-yellow)` | Warning / degraded state |
| `var(--accent-orange)` | Pending / caution state |
| `var(--primary-color)` | Primary CTA buttons |

```css
/* ✓ Correct */
color: var(--text-primary);
border-color: var(--accent-blue);

/* ✗ Wrong */
color: #ffffff;
border-color: #4a9eff;
```

---

### Icons — Inline SVG Only, No Emoji as Icons

Emoji cannot be themed, sized consistently, or made accessible. Use inline SVG with `currentColor`.

```html
<!-- ✓ Correct: inline SVG, currentColor, aria-hidden on decorative icons -->
<svg viewBox="0 0 24 24" width="20" height="20" fill="none"
     stroke="currentColor" stroke-width="2"
     stroke-linecap="round" stroke-linejoin="round"
     aria-hidden="true">
    <polyline points="20 6 9 17 4 12"/>
</svg>

<!-- ✗ Wrong: emoji as icon -->
🔄 Aktualisieren
✅ Running
```

Emoji is only acceptable inside free-form text labels, not as structural icons.

Define reusable SVG strings as module-level constants in `tab.js` to avoid repetition.

---

### Buttons — Accessibility Requirements

Every `<button>` element must have:

1. **`type="button"`** — prevents accidental form submission
2. **`aria-label`** — required on icon-only buttons (no visible text label)
3. **Touch target ≥ 44px** — use `.btn` class which satisfies this automatically

```html
<!-- ✓ Text button -->
<button type="button" class="btn btn-refresh" data-action="template-refresh">
    <svg ...></svg> Aktualisieren
</button>

<!-- ✓ Icon-only button — needs aria-label -->
<button type="button" class="btn btn-icon" aria-label="Export als CSV"
        data-action="template-export">
    <svg ...></svg>
</button>

<!-- ✗ Missing type, missing aria-label -->
<button onclick="fn()">🔄</button>
```

Available button classes: `.btn`, `.btn-primary`, `.btn-outline`, `.btn-sm`, `.btn-danger`, `.btn-refresh`, `.btn-icon`, `.btn-icon-sm`.

---

### CSS Transitions — No `transition: all`

`transition: all` animates layout-affecting properties (width, height, padding) and causes layout reflows on every interaction.

```css
/* ✓ Correct — enumerate paint-safe props only */
transition: color 0.15s, background-color 0.15s, border-color 0.15s,
            box-shadow 0.15s, transform 0.15s, opacity 0.15s;

/* ✗ Wrong */
transition: all 0.15s;
```

This applies to both CSS in `tab.html` and any `el.style.transition` set in `tab.js`.

---

### Status Cards

Use the shared `.status-card` pattern for metric headers:

```html
<div class="k8s-cluster-status">
    <!-- neutral -->
    <div class="status-card">
        <span class="status-icon"><svg ...></svg></span>
        <span class="status-value" style="font-variant-numeric:tabular-nums" id="my-stat">-</span>
        <span class="status-label">Label</span>
    </div>
    <!-- positive -->
    <div class="status-card running"> ... </div>
    <!-- negative -->
    <div class="status-card failing"> ... </div>
    <!-- cautionary -->
    <div class="status-card warning"> ... </div>
</div>
```

Always add `font-variant-numeric: tabular-nums` to numeric `.status-value` elements so numbers don't jump horizontally during updates.

---

### Status Badges

```html
<span class="status-badge status-ok">Running</span>
<span class="status-badge status-warning">Degraded</span>
<span class="status-badge status-error">Failed</span>
<span class="status-badge status-new">New</span>
<span class="status-badge status-processing">Processing</span>
<span class="status-badge status-pending">Pending</span>
```

---

### State Classes — Always Show Feedback

Never leave a container blank after an async operation. Always render one of these states:

```html
<!-- Loading -->
<p class="empty-state">Lade…</p>

<!-- Empty result -->
<p class="empty-state">Keine Einträge gefunden.</p>

<!-- Error -->
<p class="empty-state text-error">Fehler beim Laden der Daten.</p>
```

---

### Section Structure

```html
<div class="k8s-section">
    <h3 class="section-title" style="text-wrap:balance">Section Title</h3>
    <!-- content: .nodes-grid / .agents-grid / .data-table -->
</div>
```

Add `text-wrap: balance` to `h2`/`h3` headings to prevent orphaned single words on the last line.

---

### Controls Toolbar

Standard layout for the connection selector + action buttons row:

```html
<div style="display:flex; gap:1rem; align-items:center; flex-wrap:wrap; margin-bottom:1.5rem;">
    <!-- connection selector, filter dropdowns, action buttons -->
</div>
```

`flex-wrap: wrap` ensures the toolbar doesn't overflow at narrow widths.

---

### Dropdowns — No Native `<select>` for Primary Controls

Use the `cl-select` div pattern for connection selectors and filter dropdowns. It renders correctly in both dark and light mode. Native `<select>` is only acceptable for inline form fields inside Settings forms where `.form-select` handles the theming.

---

### Safe HTML Generation in JavaScript

Always escape user-supplied values before inserting into `innerHTML`:

```js
function esc(s) {
    const d = document.createElement('div');
    d.textContent = String(s ?? '');
    return d.innerHTML;
}

// ✓ Safe
container.innerHTML = `<div>${esc(item.name)}</div>`;

// ✗ XSS risk
container.innerHTML = `<div>${item.name}</div>`;
```

Use `data-action` attributes for event delegation — never inline `onclick="..."` in JS-generated HTML strings.

---

### CSS Scoping

All `<style>` rules in `tab.html` **must be scoped** to the tab's root ID to avoid leaking into other tabs:

```css
/* ✓ Scoped */
#mymodule-tab-content .my-class { ... }

/* ✗ Global — leaks into other tabs */
.my-class { ... }
```

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
