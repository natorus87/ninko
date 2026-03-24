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

## Beispiel-Prompt (Chat)
Alle Funktionen aller installierten Module stehen dir mobil sofort in der Hosentasche zur Verfügung:
- *"Zeige mir alle Kubernetes-Pods, die crashen!"*
- *"Restarte bitte VM 104 in Proxmox."*
- *"Wie ist meine Fritzbox-IP?"*
