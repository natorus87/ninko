# Kumio Module: Email (SMTP/IMAP)

Dieses Modul befähigt Kumio dazu, als vollwertiger E-Mail Client zu agieren. Der Agent kann Posteingänge lesen, E-Mails durchsuchen, E-Mails verschieben, löschen und natürlich neue E-Mails via SMTP (inkl. HTML und Dateianhängen) versenden.

## Architektur & Protokolle

- **Empfang (IMAP)**: Das Modul nutzt SSL (Standardport 993) via `imaplib`, um Posteingänge zu scannen. Der LLM Agent kann komplexe Suchfilter anwenden (z.B. `UNSEEN FROM "Chef"`).
- **Versand (SMTP)**: Das Modul nutzt STARTTLS (Standardport 587) via `smtplib`, um E-Mails zu versenden. Standardmäßig wird der Plain-Text aus dem LLM als HTML formatiert.
- **Authentifizierung**:
  - **Basic Auth**: Klassische App-Passwörter (z.B. bei GMX, Gmail, alten Exchange-Servern).
  - **OAuth 2.0 (MSAL)**: Moderne, sichere Authentifizierung für Microsoft 365 / Exchange Online via Client Credentials Flow (App Registrations).

## Konfiguration (Dashboard)

Unter **Einstellungen -> Module -> Email** kannst du beliebig viele "Postfächer" als Verbindungen hinterlegen.

### Felder

- **IMAP Server / Port**: z.B. `imap.gmx.net` und `993`.
- **SMTP Server / Port**: z.B. `mail.gmx.net` und `587`.
- **E-Mail Adresse**: Die primäre Sende- und Login-Adresse (z.B. `bot@deinedomain.de`).
- **Auth-Typ**: Wähle zwischen `basic` (App-Passwort) und `oauth2` (Microsoft 365).
- **Passwort / Client Secret**: Bei Basic Auth trägst du hier das App-Passwort ein. Bei OAuth2 trägst du hier das _Client Secret_ der Azure App Registration ein! Dieses Feld wird sicher als Secret in HashiCorp Vault gespeichert.

### Speziell für Microsoft 365 (OAuth 2.0)

Microsoft deaktiviert Basic Auth für IMAP zunehmend. Kumio bietet nativen Microsoft Authentication Library (MSAL) Support.

1. Erstelle eine **App Registration** im [Azure Portal](https://portal.azure.com/).
2. Unter "API-Berechtigungen" (API Permissions) füge folgende **Microsoft Graph** Berechtigungen hinzu (als *Application Permissions* für den daemon-artigen Client Credentials Flow, oder *Delegated* falls gewünscht):
   - `Mail.ReadWrite`
   - `Mail.Send`
3. Gewähre den **Admin Consent** für dein Tenant.
4. Unter "Zertifikate & Geheimnisse" (Certificates & Secrets) erstelle ein neues **Client Secret**.
5. Trage in Kumio ein:
   - **Client ID**: Die Anwendungs-ID (Application ID) deiner App Registration.
   - **Tenant ID**: Deine Verzeichnis-ID (oder einfach `common` für Multitenant).
   - **Passwort / Client Secret**: Der _Wert_ des im Azure Portal generierten Client Secrets.

## Funktionen (Tools)

Der `EmailAgent` greift auf folgende Tools zu:

*   `send_email(to, subject, body, cc, bcc, is_html, attachments, connection_id)`: E-Mail via SMTP senden, optional mit Dateianhängen.
    - `attachments`: Liste von absoluten Dateipfaden auf dem Server (z.B. `['/app/data/uploads/email/bericht.pdf']`). Fehlende Dateien werden übersprungen und geloggt.
    - Text-Dateien (`.txt`, `.log`, `.csv` etc.) werden inline angehängt; Binärdateien (PDF, Bilder etc.) werden automatisch Base64-kodiert.
    - MIME-Typ wird automatisch über `mimetypes.guess_type()` erkannt; unbekannte Typen fallen auf `application/octet-stream` zurück.
    - Bei Anhängen wird `MIMEMultipart` verwendet, ohne Anhängen die leichtere `EmailMessage`-Struktur.
*   `read_emails(folder, limit, query)`: Fetch auf den IMAP-Posteingang. Erwartet standardmäßige IMAP-Suchstrings.
*   `move_email(uid, source_folder, dest_folder)`: Kopiert eine Mail in einen neuen Ordner und flaggt das Original als \Deleted.
*   `delete_email(uid, folder, hard_delete)`: Verschiebt die Mail standardmäßig in den Papierkorb ("Trash") oder löscht sie direkt (*expunge*).

## Datei-Upload (für Anhänge)

Über `POST /api/email/upload` (multipart/form-data, Feldname `file`) können Dateien hochgeladen werden, die anschließend als E-Mail-Anhang verwendet werden können.

| Parameter | Wert |
|---|---|
| **Maximale Größe** | 25 MB pro Datei |
| **Speicherort** | `/app/data/uploads/email/` (Docker-Volume: `./data/uploads/email/`) |
| **Dateiname** | UUID-basiert zur Kollisionsvermeidung, Original-Erweiterung beibehalten |

**Antwort** (200 OK):
```json
{
  "status": "ok",
  "file_path": "/app/data/uploads/email/a1b2c3d4e5f6.pdf",
  "original_name": "bericht.pdf",
  "size": 245760
}
```

**Fehler**:
- `400`: Kein Dateiname angegeben
- `413`: Datei überschreitet 25 MB Limit

Der zurückgegebene `file_path` wird direkt im `attachments`-Parameter von `send_email` verwendet. Fehlende Pfade werden vom Tool mit einem Warning-Log übersprungen – die E-Mail geht trotzdem raus.

## Beispiel-Prompts

*   *"Lies mir die letzten 5 ungelesenen E-Mails aus dem Posteingang vor."*
*   *"Sende eine E-Mail an admin@firma.de und informiere ihn, dass das Backup des Proxmox-Servers fehlgeschlagen ist."*
*   *"Verschiebe alle E-Mails von 'newsletter@spam.com' in den Ordner 'Papierkorb'."*
*   *"Gibt es neue Server-Alerts per E-Mail aus der letzten Nacht?"*
*   *"Sende den Bericht /app/data/uploads/email/bericht.pdf als Anhang an die Geschäftsleitung."*
