# Ninko Frontend

Single-page Vanilla JavaScript application serving as the dashboard for the Ninko IT-Operations AI platform.

## Overview

The frontend is a modular, SPA-like interface built with vanilla JavaScript (no frameworks). It communicates with the FastAPI backend via REST and WebSocket APIs.

## Architecture

### Entry Point
- **index.html** — Main HTML structure with all tab panels, forms, and layout containers

### Core Application
- **app.js** — Main `Ninko` object containing:
  - Chat UI and messaging
  - Module system integration
  - Settings management
  - Agent/Skill/Workflow CRUD
  - Voice input (WebRTC)
  - Text-to-Speech playback
  - Theme switching

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
