# Ninko Module: IONOS DNS (🌐)

Dieses Modul ermöglicht die Verwaltung öffentlicher DNS-Zonen und Einträge über die **IONOS Hosting Developer API**.

> **Achtung**: Dieses Modul nutzt die *Hosting* API (`api.hosting.ionos.com`), nicht die IONOS *Cloud* API.

## Konfiguration (Connections)

Über das Ninko Backend (`⚙ Einstellungen -> IONOS DNS`) können Verbindungen (API-Keys) angelegt werden.

### Geheimnisse (Vault)
- **API Key** (`IONOS_API_KEY`): Dein IONOS Developer API Key.

## API Key Format
Der API-Key muss exakt das Format `prefix.secret` (zwei Teile, getrennt durch einen Punkt) haben.
1. Melde dich im IONOS Developer Portal (developer.hosting.ionos.de) an.
2. Erstelle einen neuen API-Schlüssel.
3. Kopiere den gesamten String inklusive des Punktes. Ninko kümmert sich um die Kodierung und fehlerhafte Typographie (wie em-dashes `—`), falls du den Key unsauber kopiert haben solltest.

## Features & Tools

Der AI Orchestrator nutzt folgende Funktionen:
- `get_ionos_zones`: Ruft eine Liste aller DNS-Zonen auf, die im Account vorhanden sind.
- `get_ionos_records`: Listet alle DNS-Records (A, AAAA, CNAME, TXT, MX) einer spezifischen Zone auf.
- `add_ionos_record`: Fügt einen neuen DNS-Eintrag hinzu.
- `update_ionos_record`: Verändert Werte (Content, TTL, Prio) eines bestehenden Eintrags.
- `delete_ionos_record`: Löscht einen DNS-Record sicher.

*Hinweis für Entwickler*: Die API benötigt für den Lesevorgang von Records den GET-Aufruf auf `/zones/{id}` (inkl. embedded Records), da `/zones/{id}/records` fälschlicherweise `401 Unauthorized` liefert, wenn keine spezielle Support-Rolle existiert. Ninko handelt dies transparent.

## Beispiel-Prompt (Chat)

- *"Welche DNS Zones haben wir bei IONOS?"*
- *"Zeige mir alle A-Records für die Zone `meine-domain.de`."*
- *"Lege einen neuen A-Record für `dev.meine-domain.de` an, der auf `10.0.0.5` zeigt."*
- *"Lösche bitte den TXT-Record `_acme-challenge` aus dem DNS."*
