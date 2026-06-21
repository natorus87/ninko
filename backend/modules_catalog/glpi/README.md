# Ninko Module: GLPI Helpdesk (🎫)

Dieses Modul integriert die IT-Service-Management (ITSM) Lösung **GLPI** in Ninko. Es ermöglicht dem KI-Agenten, Tickets zu lesen, zu erstellen, zu kommentieren und automatisiert Incidents aufzunehmen.

## Konfiguration (Connections)

Über das Ninko Backend (`⚙ Einstellungen -> GLPI Helpdesk`) können Verbindungen zum GLPI-Server hergestellt werden.

### Benötigte Felder
- **URL**: Die Basis-URL deiner GLPI-Instanz (z.B. `https://glpi.meinedomain.de`). Ninko fügt den `/apirest.php` Pfad automatisch hinzu.

### Geheimnisse (Vault)
- **App Token** (`GLPI_APP_TOKEN`): Wird im GLPI unter `Setup -> General -> API -> Application token` konfiguriert, um die anfragende App (Ninko) zu identifizieren.
- **User Token** (`GLPI_USER_TOKEN`): Wird in den profilbezogenen Einstellungen eines Benutzer-Accounts im GLPI generiert (`Preferences -> API token`). Dieser User führt die Aktionen im Namen des Bots aus.

## GLPI API aktivieren
Damit das Modul funktioniert, muss die REST-API in GLPI aktiviert sein:
1. Gehe in GLPI zu **Setup -> General -> API**.
2. Aktiviere "Enable Rest API".
3. Aktiviere "Login with App-Token".
4. Erstelle ein "API client" Profil oder hinterlege IPs.

## Features & Tools

Der AI Orchestrator nutzt folgende Funktionen:
- `search_tickets`: Ruft eine Liste von Tickets ab (optional gefiltert nach Status, z.B. nur aktive Tickets).
- `get_ticket`: Zeigt den kompletten Inhalt eines spezifischen Tickets.
- `create_ticket`: Erstellt neue Incident- oder Request-Tickets.
- `add_followup`: Fügt einem bestehenden Ticket einen Kommentar hinzu.
- `add_solution`: Fügt einem Ticket eine Lösung hinzu.
- `close_ticket`: Schließt ein Ticket.
- `get_ticket_attachments`: Listet Anhänge eines Tickets.
- `get_ticket_image_ocr`: Führt OCR auf einem Bildanhang aus (z.B. Screenshots).

## OCR / Vision (global)

Die OCR-Engine wird zentral in **Einstellungen -> TTS/STT -> OCR / Vision** konfiguriert:
- `python` (pytesseract lokal)
- OpenAI-kompatible Vision API

Für die Vision API müssen URL, API-Key und Modell gesetzt sein.
Für `python` sind `pytesseract` + `Pillow` sowie das Systempaket `tesseract-ocr` erforderlich.

## Beispiel-Prompt (Chat)

- *"Zeige mir alle offenen Tickets mit hoher Priorität."*
- *"Erstelle ein Incident-Ticket: Server `backup-srv` antwortet nicht."*
- *"Füge eine Notiz zu Ticket #567 hinzu: Problem wurde durch Neustart behoben."*
- *"Schließe Ticket #890 mit der Lösung: Festplatte wurde getauscht."*
