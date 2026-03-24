# Kumio Module: Pi-hole (🛡️)

Dieses Modul integriert das beliebte DNS-Sinkhole **Pi-hole v6** in Kumio, um dir das Verwalten von Blocklisten und Netzwerkanalysen per Chat zu ermöglichen.

## Konfiguration (Connections)

Über das Kumio Backend (`⚙ Einstellungen -> Pi-hole`) können Verbindungen zu verschiedenen Pi-hole-Instanzen verwaltet werden.

### Benötigte Felder
- **URL**: Die URL des Pi-hole Web-Interfaces (z.B. `http://192.168.1.5` oder `http://pihole.local`). Ohne trailing Slash (`/`).
  
### Geheimnisse (Vault)
- **Web-Passwort** (`PIHOLE_PASSWORD`): Das Login-Passwort für die Pi-hole Weboberfläche.

## Auth & Sessions
Die Pi-hole v6 REST API nutzt ein sitzungsbasiertes (Session ID) Authentifizierungsverfahren (`/api/auth`).
Das Modul regelt den Anmeldevorgang automatisch, cacht den Sitzungstoken in Redis für 5 Minuten und erneuert ihn, falls er abläuft oder die API den Fehler `api_seats_exceeded` (429 Too Many Requests, zu viele offene Sessions) wirft.

## Features & Tools

Der AI Orchestrator nutzt folgende Funktionen:
- `get_pihole_summary`: Übersicht der Netzwerkstatistiken (geblockte Anfragen, Prozentwerte, Domänen).
- `get_pihole_recent_blocked`: Listet die zuletzt blockierten Domains und ihre Clients auf.
- `block_domain`: Setzt eine Domain auf die DNS-Sperrliste (Regex oder Exact).
- `unblock_domain`: Hebt die Sperrung einer Domain auf.
- Custom DNS: `get_custom_dns_records`, `add_custom_dns_record` und `remove_custom_dns_record` zur Verwaltung manueller CNAMEs oder lokaler DNS-A-Records.

## Beispiel-Prompt (Chat)

- *"Gib mir einen Status-Bericht zum Pi-hole."*
- *"Welche Domains wurden am häufigsten blockiert?"*
- *"Bitte blockiere die Domain `ads.example.com` sofort."*
- *"Erstelle für das Pi-hole einen internen DNS-A-Record: `dev.local` zeigt auf `10.0.0.5`."*
