# Ninko Module: Telegram Bot (💬)

Das Telegram Modul ermöglicht den passiven Zugriff auf Ninko über den Telegram-Messenger.

Das Modul selbst fügt dem Agenten **keine neuen Tools** zum Arbeiten hinzu (`get_tools = []`), sondern startet einen global verknüpften Background-Worker (Polling Loop), der Telegram-Nachrichten auffängt und an den internen Orchestrator weiterleitet.

## Konfiguration (Connections)

Anstelle von klassischen `.env`-Variablen nutzt der Telegram-Bot das globale Connection-System.

1. Wähle im Ninko Backend (`⚙ Einstellungen -> Telegram`).
2. Lass das Feld Umgebung / Daten z.B. auf `prod` oder `local`.

### Geheimnisse (Vault)
- **Bot Token** (`TELEGRAM_BOT_TOKEN`): Erzeugt vom BotFather (z.B. `123456789:ABCDEF...`).
Der laufende Bot wertet diesen Token sicher via HashiCorp Vault aus.

## Architektur & Chat Memory
- **Polling Loop:** Ninko loggt sich asynchron über die Methode `getUpdates` bei Telegram ein. Es ist kein Webhook erforderlich. Dies ist ideal, falls Ninko tief im Intranet hinter Firewalls läuft.
- **Persistent Memory:** Ninko bindet die Chat-Historie (das Gedächtnis des LLMs) direkt an die `user_id` deines Telegram-Accounts (im Redis-Key `ninko:chat:telegram_<userid>`). Dies unterscheidet sich vom Web-GUI (wo Sessions meist ephemer sind).

## Native Kommandos
Sollte die KI einmal "hängen", halluzinieren, oder falsche alte Angaben in ihre nächste Antwort verschleppen, kannst du die Historie direkt im Chat löschen:

Tippe dazu einfach einen dieser Befehle in den Telegram-Chat mit dem Bot ein:
- `/start`
- `/clear`
- `/reset`

Dies löscht das serverseitige Redis-Gedächtnis und Ninko beginnt den Chat kontextuell wieder von Null.

## Pairing & Zugriff (DM Policy)
Standardmäßig ist der Zugriff geschützt. Es gibt drei Wege, Nutzer zu autorisieren:

1. **Pairing (empfohlen)**
   - Nutzer schreibt dem Bot: `/pair`
   - Bot antwortet mit einem 6‑stelligen Code (z. B. `13MZF8`)
   - Ein bereits autorisierter Admin bestätigt im Telegram‑Chat:
     - `/pair 13MZF8`

2. **Allowlist (direkt)**
   - In der Telegram‑Connection `allow_from` auf die **User‑ID** setzen
   - `allow_from` kann eine Liste oder Komma‑Liste sein (z. B. `1260743556,987654321`)
   - Optional: `dm_policy=allowlist` erzwingen

3. **Open DM (nur temporär)**
   - `dm_policy=open` erlaubt jedem DM‑Kontakt
   - Nur für Tests oder initiales Setup empfohlen

### Chat‑ID anzeigen
Der Bot zeigt die Chat‑ID immer an (auch vor Pairing):
- `/chatid`

### Wichtige Hinweise
- **`allow_from` nutzt User‑IDs**, nicht Chat‑IDs.
- Für Gruppen gilt zusätzlich `allowed_chat_ids` (Legacy‑Allowlist).
- Pairing‑Codes sind standardmäßig 1 Stunde gültig.

## Beispiel-Prompt (Chat)
Alle Funktionen aller installierten Module stehen dir mobil sofort in der Hosentasche zur Verfügung:
- *"Zeige mir alle Kubernetes-Pods, die crashen!"*
- *"Restarte bitte VM 104 in Proxmox."*
- *"Wie ist meine Fritzbox-IP?"*
