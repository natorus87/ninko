---
name: wordpress-publishing
description: WordPress Beitrag erstellen veröffentlichen Seite Kategorie Tag SEO Medien Status Entwurf
modules: [wordpress]
---

## WordPress Publishing Workflow

### Beitrags-Typen
| Typ | Wann | Tool |
|---|---|---|
| Post (Beitrag) | Blog, News, Ankündigungen | `create_post()` |
| Page (Seite) | Statische Inhalte, Impressum | `create_page()` |
| Custom Post Type | Produkte, Events (falls installiert) | `create_post(post_type=...)` |

### Status-Workflow
```
draft → pending → publish    (Normalfall)
draft → future               (geplante Veröffentlichung mit date)
publish → private            (nur eingeloggte Nutzer sehen)
```

### SEO-Best-Practices
- **Titel**: Keyword am Anfang, max 60 Zeichen
- **Slug**: automatisch aus Titel, ggf. manuell kürzen (nur Kleinbuchstaben, Bindestriche)
- **Excerpt**: erste 150 Zeichen = Meta-Description
- **Alt-Text** für Bilder immer setzen

### `create_post` Parameter
```python
title       # Pflicht
content     # HTML oder Gutenberg-Blöcke
status      # "draft" (Standard), "publish", "private"
categories  # IDs oder Namen (erst `list_categories()` aufrufen)
tags        # Strings, werden auto-angelegt
excerpt     # Kurze Zusammenfassung (für SEO)
date        # ISO 8601 für geplante Posts
```

### Häufige Fehler
| Fehler | Ursache | Fix |
|---|---|---|
| 404 bei REST-API | Permalinks auf "Standard" | Einstellungen → Permalinks → Beitragsname |
| `rest_forbidden` | Nutzer hat keine Rechte | WordPress-Rolle: Autor oder höher |
| Kategorien leer | Falsche ID | `list_categories()` aufrufen, IDs prüfen |

### Reihenfolge
1. `list_categories()` → verfügbare Kategorien prüfen
2. Content formulieren (HTML erlaubt: `<h2>`, `<p>`, `<ul>`, `<strong>`)
3. `create_post()` mit `status="draft"` → ID merken
4. Auf Wunsch `status="publish"` setzen
