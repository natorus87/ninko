---
name: pihole-session-management
description: Pi-hole v6 Session-Authentifizierung, Rate-Limiting, api_seats_exceeded Fehler, 429 Too Many Requests, Sitzungsverwaltung, Token-Caching
modules: [pihole]
---

## Pi-hole v6 API – Wichtige Eigenheiten

### Authentifizierung
- Pi-hole v6 nutzt **session-basierte REST-API** (kein API-Key mehr wie v5).
- Jede Sitzung belegt einen "Seat" — maximale Anzahl konfigurierbar via `webserver.api.max_sessions`.
- Der `_authenticate`-Helper in `tools.py` cacht den Token **5 Minuten** (TTL-basiert).

### 429 – api_seats_exceeded
Wenn `429 api_seats_exceeded` zurückkommt:
1. Alte Sitzungen bereinigen (interner Session-Cleanup im Helper).
2. Exponentielles Backoff: 1s → 2s → 4s (max 3 Versuche).
3. Falls weiterhin Fehler: Pi-hole Webserver-Config prüfen (`max_sessions` erhöhen).

### Rate-Limiting (allgemein)
- Zu viele API-Calls in kurzer Zeit → kurze Pause (1-2s) einlegen.
- Bulk-Operationen (z.B. viele Domains auf Blacklist) immer sequenziell, nicht parallel.

### Typische Diagnose-Sequenz
1. `get_pihole_summary` → Basis-Status (läuft Pi-hole, ist Blocking aktiv?)
2. `get_query_log` → letzte DNS-Anfragen
3. Bei 429: kurz warten, dann erneut versuchen — NICHT sofort weiter-loopen.

### Gravity-Update
`update_gravity` kann 30-60 Sekunden dauern → Timeout-Toleranz einplanen, nicht als Fehler werten.
