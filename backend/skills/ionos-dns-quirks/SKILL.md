---
name: ionos-dns-quirks
description: IONOS DNS API Eigenheiten, Records abrufen, Zone-Abfrage, API-Key Format, ASCII-Encoding-Fehler, SPF-Records, 401 Fehler
modules: [ionos]
---

## IONOS DNS API – Kritische Eigenheiten

### Records abrufen – WICHTIG
`GET /zones/{id}/records` gibt **401** für Standard-API-Keys zurück.
**Stattdessen:** `GET /zones/{id}` verwenden → Records sind in `zone.records[]` eingebettet.

### API-Key Format
- Muss im Format `prefix.secret` sein (zwei Teile getrennt durch `.`).
- Kopierte Keys enthalten manchmal **typografische Em-Dashes** (`—` statt `-`).
- Immer sanitizen: `.replace("—", "-").strip()` vor Verwendung im Header.

### Records anlegen
- `POST /zones/{id}/records` erwartet ein **Array**: `[{...}]` nicht ein Objekt `{...}`.
- Bei Fehler "invalid format": Prüfen ob Array-Wrapper fehlt.

### SPF-Records
- Root-Domain braucht **eigenen TXT-SPF-Record** (nicht nur Subdomain).
- Format: `v=spf1 include:... ~all`

### Typische Fehlerdiagnose
| Fehler | Wahrscheinliche Ursache |
|---|---|
| 401 bei GET /records | Falscher Endpoint → /zones/{id} statt /zones/{id}/records |
| UnicodeEncodeError | Em-Dash im API-Key → sanitizen |
| 422 Unprocessable | POST body ist Objekt statt Array |
| 404 Zone nicht gefunden | Zone-ID falsch oder falsche Domain |
