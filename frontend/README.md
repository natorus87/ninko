# Ninko Frontend

Single-page Vanilla JavaScript application serving as the dashboard for the Ninko IT-Operations AI platform.

## Operational Sync (Apr 2026)

- First-login password change uses an in-app modal (same window), no browser `prompt()`.
- Login/session flow is aligned with backend middleware to avoid API `401/403` loops after password changes.
- WebSocket `403` entries can still appear in logs during reconnect races; one accepted connection is expected after app bootstrap.
- Logout button (sidebar top-right) and "Einstellungen" sidebar nav item removed — both replaced by the bottom user account menu.
- Plugin dashboard init: all catalog modules register via `Ninko._pluginTabs['id'] = TabObject` at the end of `tab.js`. This is the canonical plugin pattern. `getTabObject()` in `app.js` checks `_pluginTabs` as a fallback after the hardcoded map.

## Overview

The frontend is a modular, SPA-like interface built with vanilla JavaScript (no frameworks). It communicates with the FastAPI backend via REST and WebSocket APIs.

## Architecture

### Entry Point
- **index.html** — Main HTML structure with all tab panels, forms, and layout containers

### Core Application
- **app.js** (~3.7k Zeilen) — Der Kern des globalen `Ninko`-Objekts:
  - Init/Boot, i18n-Loader, SVG-Icon-Library
  - Navigation/Tabs, Route-Persistence, Settings-Shell
  - Der komplette **Chat** (WS-Streaming, Tool-/Trace-Events, Markdown-Rendering,
    TTS-Wiedergabe, History, Export, Context-Indicator)
  - WebSocket, Command-Palette-Hooks, Resizing/Textarea-Utilities
  - Geteilte Helfer (`_escapeHtml`, `_escapeAttr`, `_esc`, `_ic`) und der State, den die Features nutzen
  - Kleine init-nahe Reste: Legacy-LLM-Settings, Language, Memory/Secrets

### Feature-Module (`features/*.js`)

Früher war `app.js` ein ~8.400-Zeilen-Monolith. Große, klar abgegrenzte Panels
wurden in **Feature-Module** ausgelagert (Stand: 18 Module). Muster:

```js
(function () {
    'use strict';
    const XyzFeature = {
        async loadXyz() { /* … this.* verweist auf das Ninko-Objekt … */ },
    };
    if (typeof window.Ninko !== 'undefined') {
        Object.assign(window.Ninko, XyzFeature);   // Methoden auf Ninko mergen
    } else {
        window.XyzFeature = XyzFeature;
    }
})();
```

**Warum das funktioniert (wichtige Konventionen):**
- Alle Feature-Methoden greifen über `this.` auf andere Methoden, geteilte Helfer
  (`this._escapeHtml`) und State (`this._rbacUsers`) zu. Nach dem `Object.assign`
  liegen sie alle auf demselben `window.Ninko`-Objekt — die Aufrufe bleiben gültig.
- **State kann in app.js bleiben**, auch wenn die zugehörigen Methoden im Feature
  liegen: die Property-Deklaration (z.B. `_themes: []` im Init-Bereich) landet auf
  Ninko und ist für die Feature-Methoden via `this.` erreichbar. State, der *im*
  extrahierten Block deklariert ist (z.B. `_alertsCache`), wandert mit ins Feature.
- **Ladereihenfolge:** Feature-Scripts stehen in `index.html` **nach** `app.js`
  (das `window.Ninko` definiert). Der Boot läuft über `DOMContentLoaded` — das
  feuert erst nach allen synchronen Script-Tags, daher sind auch init-kritische
  Methoden (`initSafeguard`, `applyBranding`) zum Init-Zeitpunkt bereits gemergt.

**Module und Inhalt:**

| Datei | Inhalt |
|---|---|
| `agents.js` | Agenten-CRUD, Templates, KI-Generierung, Skills-Verwaltung |
| `workflows.js` | Visueller Workflow-Editor (Canvas, Nodes, Edges, Run-Dashboard) |
| `scripting.js` | Python-Scripting-Panel |
| `command_palette.js` | Befehls-Palette (Cmd/Ctrl+K) |
| `tasks.js` | Geplante Aufgaben (Editor, CRUD, Aktionen) |
| `marketplace.js` | Modul-Marketplace (Repo-Verwaltung, Modul-Install) |
| `rbac.js` | Benutzer-/Gruppen-/Rollenverwaltung, API-Tokens, Modulrechte |
| `module_settings.js` | Modul-Aktivierung + Connection-CRUD (`ACTION_FIELDS`-Formulardefs) |
| `safeguard.js` | SafeGuard-Profile, Picker, Bestätigungs-Flow, Settings-Panel |
| `themes.js` | Theme-Katalog, Custom-Editor, Theme-Repos |
| `speech_settings.js` | STT (Whisper), OCR (Vision), TTS (Piper) |
| `llm_provider.js` | LLM-Provider-CRUD, Embedding-Provider, Function-Calling-Routing |
| `image_gen.js` | Bildgenerierungs-Provider |
| `alerts.js` | Alert-Management (Laden, Tabelle, Auflösen, WS-Live-Update) |
| `branding.js` | Dashboard-/Login-Branding, Asset-Upload, Live-Vorschau |
| `background_settings.js` | Hintergrundfarben (Presets, Farb-Picker, Persistenz) |
| `plugins.js` | Plugin-Verwaltung (ZIP-Upload, Deinstallation, Einzel-/Bulk-Update) |
| `logs.js` | Log-Viewer (Polling, Filter, Detail-Panel, CSV-/JSON-Export) |

**Einen weiteren Block extrahieren** (falls `app.js` weiter verkleinert wird):
1. Zusammenhängenden Methodenblock per String-Match an den Methodengrenzen isolieren
   (Sektions-Kommentare sind teils irreführend — Nachbarschaft aktiv prüfen).
2. Geteilte Helfer (`_escapeHtml`) und State, der auch außerhalb genutzt wird, in
   app.js **belassen** (via `this.` erreichbar).
3. Methoden mit +4 Indent ins `XyzFeature`-Objekt-Literal setzen, IIFE-Wrapper drum.
4. Block aus app.js entfernen, Naht auf eine Leerzeile normalisieren.
5. `<script>`-Tag nach app.js in `index.html`, `app.js?v=`-Cache-Version bumpen.
6. Per Playwright-Smoke-Test des betroffenen Panels verifizieren (Methoden auf
   `Ninko` vorhanden, Panel lädt, State befüllt, keine Konsolen-Fehler).

### Styling
- **style.css** — CSS custom properties design system with dark/light themes

### Assets
- **images/** — Logo, icons (PNG/SVG)
- **i18n/** — Translation JSON files (de, en, fr, es, it, nl, pl, pt, ja, zh)

## Features

### Chat Interface
- Real-time messaging via WebSocket streaming
- Voice input (microphone recording → transcription)
- Text-to-Speech response playback
- Chat history with localStorage fallback
- Module picker (force routing to specific module)
- Safeguard confirmation system for destructive actions

### Navigation
- **Chat** — Main conversation interface
- **Automatisierung** — Sub-tabs: Tasks, Agents, Workflows
- **Module** — Dynamic module dashboards (Kubernetes, Proxmox, GLPI, Pi-hole, etc.)
- **Settings** — LLM providers, module config, language, TTS, logs
- **Themes** — Presets, custom token editor, GitHub theme repos/install

### Visual Workflow Editor
- Drag-and-drop node canvas (Trigger, Agent, Condition, Loop, Variable, End)
- SVG-based edge connections
- Node inspector panel for configuration
- Run dashboard with live execution status

### Internationalization
- Dynamic language loading from `/static/i18n/{lang}.json`
- Fallback chain: requested → German → English

## Key Technical Details

### Theme System
CSS custom properties in `:root` for dark mode, `.light-mode` class overrides for light mode.
Additional active-theme token overrides are applied at runtime to `document.documentElement.style` from `/api/themes/active`.

### Module Loading
Modules are loaded dynamically from `/api/modules/{name}/frontend/tab.js` and appended to the DOM as IIFE scripts.

### API Communication
- REST: `fetch()` for CRUD operations
- Streaming: Server-Sent Events (`EventSource`) for live chat status
- WebSocket: Real-time connection status indicator

### Storage
- **sessionStorage** — Current chat session ID
- **localStorage** — Theme preference, language, chat history cache

## Development Notes

### Adding a New Module Tab
1. Backend provides `module_manifest.dashboard_tab` with `id`, `label`, `icon`
2. Frontend fetches `/api/modules/{name}/frontend/tab.html` and `.js`
3. Tab JS must export a `TabObj` with `init()` function (IIFE pattern)

### Styling Conventions
- Use CSS custom properties for colors (`var(--accent-blue)`)
- Avoid hardcoded colors; use semantic naming
- SVG icons use `currentColor` for theme adaptability
- **No `transition: all`** — enumerate only paint-safe properties: `color, background-color, border-color, box-shadow, transform, opacity`
- **Touch targets** — minimum 44×44px for interactive elements; small icon buttons use `::before { inset: -6px }` to extend tap area without changing visual size

### Accessibility
- **Focus rings**: global `:focus-visible` ring (`2px solid var(--accent-blue)`) — never use `outline: none` without a replacement
- **Skip link**: `.skip-link` at top of `<body>` allows keyboard users to jump to `#main-content`
- **ARIA labels**: all icon-only buttons carry `aria-label` attributes
- **Reduced motion**: `@media (prefers-reduced-motion: reduce)` block at end of `style.css` disables all decorative animations
- **Light mode contrast**: `--text-muted` is `#6b7a8d` (4.6:1 on white, WCAG AA)

### Voice Input Requirements
- Requires HTTPS (or localhost)
- Uses MediaRecorder API with WebM/OGG fallback

## File Structure

```
frontend/
├── index.html          # Main HTML entry
├── app.js             # Core application logic
├── style.css          # Design system & themes
├── favicon.ico
├── welcome_illustration.png
├── images/            # Static assets
│   ├── logo*.png
│   ├── chat_fox.png
│   └── gear_icon.png
└── i18n/              # Translations
    ├── de.json
    ├── en.json
    └── ... (10 languages)
```
