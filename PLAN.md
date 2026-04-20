# Ninko Dashboard Redesign – Feinschliff & Exaktes Vorgehen

**Datum:** 2026-04-19  
**Status:** Execution Plan (verfeinert)  
**Designrichtung:** Option A (Deep Space – Professional/Tech)

---

## 1. Zielbild

Der Umbau soll das Frontend nicht nur optisch modernisieren, sondern primär die Bedienbarkeit verbessern:

- Einstellungen schneller auffindbar machen
- Navigation für Power-User beschleunigen (Command Palette + Shortcuts)
- Dashboard als echte Arbeitsoberfläche statt Welcome-Screen etablieren
- Mobile Nutzbarkeit auf ein belastbares Niveau bringen
- Bestehende API- und Modul-Logik unverändert lassen

---

## 2. Scope und Grenzen

### In Scope
- `frontend/index.html`: Struktur für Settings, Dashboard, Breadcrumb, Command Palette
- `frontend/style.css`: Design-Tokens, Card/Button-System, Responsive, Animationen
- `frontend/app.js`: Tab-Logik, Favorites/Recent, Shortcuts, Dashboard-Rendering
- `frontend/features/workflows.js`: Mini-Map, Zoom/Pan, Undo/Redo
- `frontend/features/command_palette.js` (neu): Suche, Navigation, Command-Ausführung

### Out of Scope
- Backend-API-Änderungen
- Datenbankschema-Änderungen
- Auth-Flow-Änderungen
- Breaking Changes an bestehenden Modul-Endpoints

---

## 3. Umsetzungsprinzipien

- **Inkrementell:** Jede Phase ist einzeln lauffähig.
- **Rückbaubar:** Jede Phase kann separat reverted werden.
- **Messbar:** Pro Phase klare Abnahmekriterien (Definition of Done).
- **Kompatibel:** Bestehende Tabs/Module müssen weiterhin funktionieren.
- **Teststrategie:** Formale Tests (Regression, Cross-Browser, Gesamt-Smoketest) werden gesammelt erst in **Phase 8** durchgeführt; Phasen 1–7 bleiben bei kurzen Funktions-Checks.

---

## 4. Exakte Reihenfolge (kritischer Pfad)

1. Design-Foundation (Tokens, Basis-Komponenten)
2. Settings-Neustruktur + Tab-Logik
3. Command Palette + globale Shortcuts
4. Modul-Navigation (Favorites/Recent/Kategorien)
5. Dashboard Home (Widgets + Quick Actions)
6. Workflow Editor UX (Mini-Map, Zoom/Pan, Undo/Redo)
7. Mobile + Accessibility + Animationen
8. Stabilisierung (Tests, Performance, Cross-Browser)

Begründung: Schritte 2–5 hängen visuell und strukturell von Schritt 1 ab; Schritt 8 braucht alle vorherigen Features.

---

## 5. Detaillierter Phasenplan

## Phase 1 – Design Foundation (Tag 1)

### Aufgaben
- CSS-Variablen konsolidieren (Farben, Spacing, Radius, Schatten)
- Card-System (`.card`, Varianten) einführen
- Button-Hierarchie (`.btn-primary/.btn-secondary/.btn-danger`) vereinheitlichen
- Fokus-States und Kontraste anheben

### Dateien
- `frontend/style.css`

### Definition of Done
- Alle neuen Tokens zentral in `:root`
- Keine ungeplanten Hardcoded-Farben in neuen Komponenten
- Primäre Buttons und Cards im gesamten UI konsistent

### Check
- Sichtprüfung Desktop (Sidebar, Chat, Settings)
- Kontrastprüfung (kritische Texte/Buttons)

---

## Phase 2 – Settings IA + Navigation Cleanup (Tag 2)

### Aufgaben
- Flat Settings-Tabliste in 3 Kategorien gruppieren:
  - Intelligence (`llm`, `skills`, `safeguard`)
  - Appearance (`themes`, `language`, `tts`, `imagegen`)
  - System (`modules`, `access`, `alerts`, `logs`, `system`)
- `switchSettingsTab()` robust machen (invalid tab fallback)
- Chat-Toolbar entschlacken (sichtbar: Export, Clear; Rest in More-Menü)

### Dateien
- `frontend/index.html`
- `frontend/app.js`
- `frontend/style.css`

### Definition of Done
- Alle bisherigen Settings-Inhalte erreichbar
- URL-/State-Wechsel führt immer zu gültigem Tab
- Keine Console Errors beim Tab-Switch

### Check
- Klicktest jeder Settings-Unterseite
- Tastatur-Navigation (Tab/Enter) in Settings

---

## Phase 3 – Command Palette (Tag 3)

### Aufgaben
- Neues Modul: `frontend/features/command_palette.js`
- Global Hotkey: `Ctrl/Cmd+K`
- Command Registry (z. B. New Chat, Settings, Module Switch, Theme Toggle, Clear Context)
- Keyboard Navigation in Palette (`↑/↓/Enter/Esc`)
- Fuzzy-/Prefix-Filter mit Debounce

### Dateien
- `frontend/features/command_palette.js` (neu)
- `frontend/app.js`
- `frontend/index.html`
- `frontend/style.css`

### Definition of Done
- Palette öffnet/schließt zuverlässig per Shortcut
- Commands werden per Tastatur vollständig bedienbar ausgeführt
- Keine Konflikte mit bestehenden Shortcuts

### Check
- Funktionstest aller Commands
- Fokus-Management (Öffnen: Input fokussiert, Schließen: Fokus zurück)

---

## Phase 4 – Module Sidebar (Tag 4)

### Aufgaben
- Favoriten-System (persistiert in `localStorage`)
- „Zuletzt verwendet“ (letzte 5 Module)
- Kategorien + Filter-Suche
- Modul-Picker visuell und funktional verbessern

### Dateien
- `frontend/app.js`
- `frontend/index.html`
- `frontend/style.css`

### Definition of Done
- Favoriten bleiben nach Reload erhalten
- Recent-Liste aktualisiert sich deterministisch
- Filter reagiert in Echtzeit ohne UI-Lag

### Check
- Reload-Test für Persistence
- Wechsel zwischen 10+ Modulen ohne Inkonsistenzen

---

## Phase 5 – Dashboard Home (Tag 5)

### Aufgaben
- Welcome-Screen durch Dashboard-Home ersetzen
- Widgets einführen: Favorites, Activity, System Health
- Quick Actions (z. B. New Chat, Workflow öffnen)
- Leere Zustände sauber anzeigen (keine Daten vorhanden)

### Dateien
- `frontend/index.html`
- `frontend/app.js`
- `frontend/style.css`

### Definition of Done
- Dashboard lädt ohne Fehler bei leerem und gefülltem Zustand
- Alle Quick Actions funktionieren direkt
- Widgets degradiert robust bei fehlenden Daten

### Check
- Smoke-Test nach Hard Reload
- Navigation Dashboard ↔ Chat ↔ Settings stabil

---

## Phase 6 – Workflow Editor UX (Tag 6)

### Aufgaben
- Mini-Map für große Workflows
- Zoom-In/Out/Fit-to-Screen Controls
- Undo/Redo Stack (max. 50 Zustände)
- Shortcuts: `Ctrl/Cmd+Z`, `Ctrl/Cmd+Shift+Z`

### Dateien
- `frontend/features/workflows.js`
- optional: `frontend/style.css` (Controls)

### Definition of Done
- Undo/Redo reproduzierbar bei Add/Delete/Move
- Zoom-Controls beeinflussen nur Workflow-Canvas
- Mini-Map synchron mit Viewport

### Check
- Manueller Test mit großem Workflow
- Undo/Redo über 20+ Aktionen stabil

---

## Phase 7 – Mobile, Accessibility, Animationen (Tag 7)

### Aufgaben
- Mobile Sidebar + Bottom Navigation unter 768px
- Touch Targets auf min. 44x44
- Breadcrumb ergänzen
- Subtile Transitionen + Skeleton Loading + Toast Feedback
- `prefers-reduced-motion` berücksichtigen

### Dateien
- `frontend/style.css`
- `frontend/index.html`
- `frontend/app.js`

### Definition of Done
- Kernflows auf Mobile nutzbar (Chat, Settings, Modulwechsel)
- Fokusindikatoren sichtbar, Interaktion per Tastatur möglich
- Animationen blockieren keine Bedienung

### Check
- Viewport-Tests: 375px / 768px / 1024px
- Accessibility-Schnellprüfung (Fokus, Kontrast, Labels)

---

## Phase 8 – Stabilisierung & Abnahme (Tag 8)

### Aufgaben
- Vollständigen Testlauf für alle vorherigen Phasen ausführen (gesammelt am Ende)
- Cross-Browser Smoke-Test (Chromium + Firefox)
- Performance-Basics: Debounce, unnötige Reflows vermeiden
- Regressionstest kritischer Flows
- Finales Changelog + Screenshots

### Definition of Done
- Keine Blocker in Kernflows
- Keine neuen Console Errors in Standardpfaden
- Abnahme-Checkliste vollständig erledigt

---

## 6. Technische Leitplanken

### Backwards Compatibility
- Theme-System bleibt kompatibel
- Bestehende Module bleiben adressierbar
- API-Endpunkte unverändert

### Performance
- Bevorzugt `transform`/`opacity` statt Layout-shift-lastiger Properties
- Sucheingaben debouncen (Palette/Module)
- Nur sichtbare Widgets initial rendern

### Robustheit
- Fallbacks für leere Daten (Activity/Favorites/Health)
- `localStorage` defensiv lesen/schreiben (try/catch)
- Event-Handler beim Re-Render nicht mehrfach registrieren

---

## 7. Konkrete Abnahme-Checkliste

- [x] Settings sind in 3 Kategorien strukturiert und vollständig erreichbar
- [x] Command Palette funktioniert per Tastatur end-to-end
- [x] Module Favorites + Recent sind persistent und korrekt
- [x] Dashboard Home ersetzt Welcome-Screen ohne Regressionen
- [x] Workflow Undo/Redo + Zoom/Mini-Map funktionieren stabil
- [x] Mobile Kernflows sind nutzbar (375px)
- [x] Keine kritischen Accessibility-Verstöße sichtbar
- [x] K8s-API-Smoke-Test gegen Cluster (`microk8s`, Namespace `ninko`) erfolgreich
- [ ] Keine neuen Console Errors in Kernpfaden
  Aktueller Stand: offen wegen 404-Ressourcen im Cluster (`/api/themes/active`, einzelne Modul-Frontend-Routen, `/static/fonts/Reiko.woff2`).

---

## 8. Risiken und Gegenmaßnahmen

- **Risiko:** Große `app.js` wird unübersichtlich  
  **Maßnahme:** Neue Features in `frontend/features/*` auslagern, `app.js` nur orchestrieren.

- **Risiko:** Shortcut-Konflikte  
  **Maßnahme:** Zentrale Shortcut-Registry mit Konfliktprüfung beim Registrieren.

- **Risiko:** Mobile UI bricht bei langen Modulnamen  
  **Maßnahme:** Truncation + Tooltip/Full-Label im Detailbereich.

- **Risiko:** Performance bei Animationen  
  **Maßnahme:** Animationen sparsam, `prefers-reduced-motion`, keine Heavy-Shadows auf Listen mit vielen Items.

---

## 9. Empfohlenes Delivery-Format

- Pro Phase ein separater Commit
- Nach Phase 3 und Phase 5 jeweils Zwischen-Review
- Abschluss mit kurzem Demo-Skript:
  1. Settings-Navigation
  2. Command Palette
  3. Dashboard Widgets
  4. Workflow Undo/Redo
  5. Mobile Ansicht

Damit ist der Plan nicht nur ein Designkonzept, sondern ein direkt ausführbarer Implementierungsfahrplan.
