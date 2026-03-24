# Kumio – Anwenderdokumentation (DOCS)

Willkommen zur Anwenderdokumentation von Kumio. Dieses Dokument beschreibt die Funktionalitäten des Dashboards, die Konfiguration der Module, das Management von LLM-Einstellungen sowie das Einrichten von Verbindungen (Connections).

---

## 1. Modul-Verbindungen (Connections) verwalten

Kumio verfolgt das Konzept der **Multi-Connections**. Das bedeutet, dass ein einziges Modul (z. B. Kubernetes oder Proxmox) gleichzeitig mehrere Umgebungen (Prod, Staging, Dev, Lab) ansteuern kann.

### Eine neue Verbindung anlegen
1. Klicke im Kumio-Dashboard oben rechts auf das **Zahnrad-Symbol** (Einstellungen).
2. Wähle das gewünschte Modul in der linken Navigationsleiste aus (z. B. `kubernetes`, `proxmox`, `pihole` oder `ionos`).
3. Klicke auf den Tab **Verbindungen (Connections)**.
4. Fülle die Felder aus:
    - **Name**: Ein aussagekräftiger Name (z.B. "Prod Cluster Frankfurt").
    - **Umgebung**: Wähle aus dem Dropdown (z.B. `prod`, `staging`, `dev`, `lab`, `local`). Diese Angabe hilft dem AI Orchestrator, Risiken (wie destruktive Aktionen) besser abzuschätzen.
    - **Nicht-Geheime Konfiguration**: z. B. URLs oder Optionen.
    - **Geheimnisse (Vault)**: Passwörter oder API-Keys. Diese Felder werden bei der Anzeige im Frontend immer leer sein (aus Sicherheitsgründen), selbst wenn ein Schlüssel hinterlegt ist.
5. **Als Standard setzen**: Wenn aktiviert, greift Kumio automatisch auf diese Verbindung zurück, sofern im Chat nicht explizit etwas anderes gefordert wird.
6. Klicke auf **Speichern**.

*(Hinweis: Leere Passwortfelder überschreiben niemals bereits gespeicherte Passwörter).*

### Fehlerbehebung bei Verbindungen
- **Profil lässt sich nicht speichern/löschen**: Überprüfe, ob es eine Diskrepanz zwischen erlaubten Umgebungen gibt. Falls eine Umgebung gewählt wird, die das Backend nicht unterstützt (z.B. ein altes "Lab"-Flag vor dem Update), schlägt das Speichern fehl.
- **Mehrere gleiche Profile erscheinen**: Ein bekannter Bug bei schnellem Doppelklicken auf "Speichern" wurde behoben. Falls dennoch Duplikate auftreten, können diese bedenkenlos über den Löschen-Button entfernt werden. Vault-Secrets werden dabei sauber abgeräumt.

---

## 2. LLM Backend & Multi-Provider System

Kumio nutzt Large Language Models (LLMs) für die Autonomie der Agenten. Seit dem neuesten Update unterstützt Kumio **Multiple LLM Provider**. Das erlaubt es, verschiedene Server (Ollama, LM Studio, OpenAI) gleichzeitig zu konfigurieren und als Standard-Backend zu wählen.

### Einen Provider hinzufügen
1. Gehe in die **Einstellungen** und wähle **LLM Providers**.
2. Klicke auf **Provider hinzufügen**.
3. **Backend**: Wähle `ollama` (lokal), `lmstudio` (lokal/externer Server) oder `openai` (Cloud).
4. **Base URL**:
    - Für Ollama der interne Docker-Hostname (z.B. `http://ollama:11434`).
    - Für LM Studio deine Maschinen-IP (z.B. `http://192.168.1.100:1234/v1`). Das `/v1` wird bei Bedarf automatisch ergänzt.
5. **Standard-Modell**: Der exakte Name des LLMs (z.B. `llama3.2:3b` oder `nomic-embed-text` für Embeddings).
6. **Standard-Provider**: Aktiviere den Schalter "Als Standard setzen", damit alle Agenten primär diesen Provider nutzen.

*Hinweis: Wenn du einen neuen Standard-Provider wählst oder einen Bearbeitest, rekonfiguriert Kumio die KI-Factory im Hintergrund sofort. Ein Neustart ist nicht erforderlich.*

---

## 3. Multilingual Support (i18n)

Kumio unterstützt 10 Sprachen out-of-the-box (u.a. Deutsch, Englisch, Französisch, Spanisch, Japanisch). Sowohl das User-Interface als auch die Antworten der KI-Agenten passen sich automatisch an die gewählte Sprache an.

### Sprache ändern
1. Klicke im Kumio-Dashboard in den **Einstellungen** auf den Tab **Sprache**.
2. Wähle deine gewünschte Sprache per Klick auf die entsprechende Flagge.
3. Die Benutzeroberfläche wechselt **sofort** (ohne Seiten-Reload) in die neue Sprache. Die Einstellung wird zudem im Backend gespeichert, sodass künftige Antworten der KI in der neuen Sprache generiert werden.

---

## 4. Nutzung der AI Module im Chat

Der Kumio Orchestrator delegiert Aufgaben automatisch an das richtige Modul, basierend auf deinen Eingaben. Hier sind einige Module und ihre typischen Befehle:

### Kubernetes (☸)
- *Modul für Cluster-Verwaltung, Pods und Deployments.*
- **Beispiele**: 
  - "Zeige mir alle failing Pods im Namespace production"
  - "Starte den Pod payment-api-xyz im Namespace default neu"

### Proxmox (🖥)
- *Modul für VM- und Container-Management.*
- **Beispiele**: 
  - "Liste alle VMs auf Node pve-01"
  - "Starte die VM 105"

### Pi-hole (🛡️)
- *Modul für lokales DNS und Adblocking.*
- **Authentifizierung**: Erfordert das Pi-hole Weboberflächen-Passwort, gespeichert als Connection-Secret.
- **Beispiele**: 
  - "Sperre die Domain example.com im Pi-hole"
  - "Zeige mir die Netzwerk-Statistiken für heute"

### IONOS (🌐)
- *Modul für öffentliche DNS-Zoneverwaltung bei IONOS Hosting.*
- **Authentifizierung**: Erfordert einen API-Key im Format `prefix.secret`.
- **Beispiele**: 
  - "Welche DNS Zones haben wir bei IONOS?"
  - "Lege einen neuen A-Record für dev.meine-domain.de an, der auf 10.0.0.5 zeigt"

### FritzBox (📶)
- *Modul zur Verwaltung des Heimnetzwerks.*
- **Beispiele**: 
  - "Wie ist meine externe IP-Adresse?"
  - "Schalte das Gast-WLAN ein."

### Telegram Bot (💬)
- *Ermöglicht den Zugriff auf Kumio über den Telegram-Messenger.*
- **Verbindung**: Der Bot-Token wird in den globalen Einstellungen unter `telegram` (als Connection) hinterlegt.
- **Besonderheiten**: 
  - Die Chat-Historie (Memory) bleibt im Gegensatz zum Web-Interface über längere Zeit in der Kumio-Datenbank gespeichert.
  - Sende `/start`, `/clear` oder `/reset` direkt im Telegram-Chat, um dein lokales Chat-Gedächtnis zu löschen, falls die KI sich wiederholt oder in einem alten Kontext feststeckt.

### Web Search (🔍)
- *Modul für aktuelle Web-Informationen über eine lokale SearXNG-Instanz.*
- **Konfiguration**: Keine UI-Connection nötig. SearXNG-URL wird per Env-Var `SEARXNG_URL` gesetzt (docker-compose: automatisch; k8s: in `deployment.yaml` konfiguriert).
- **Beispiele**:
  - "Was kostet Bitcoin gerade in Euro?"
  - "Aktuelle Nachrichten zu Kubernetes 1.30"
  - "Suche im Web nach dem Changelog von Redis 8"
- **Hinweis**: Das Modul leitet Anfragen nur weiter, wenn sie eindeutige Web-Such-Schlüsselwörter enthalten (z.B. "suche", "googeln", "aktuelle news", "was kostet"). Allgemeine Fragen beantwortet der Orchestrator direkt aus dem LLM-Wissen.

### GLPI Helpdesk (🎫)
- *Modul zur Ticket-Verwaltung.*
- **Beispiele**: 
  - "Erstelle ein Incident-Ticket für den ausgefallenen Server"
  - "Was ist der Status von Ticket #1234?"

---

## 5. Langzeitgedächtnis (Semantic Memory)

Kumio besitzt ein **persistentes Langzeitgedächtnis** auf Basis von ChromaDB-Embeddings. Im Gegensatz zum einfachen Chat-Verlauf (kurzfristig in Redis) überlebt dieses Wissen Container-Neustarts und neue Chat-Sessions.

### Automatisches Merken
Nach jeder Antwort prüft Kumio im Hintergrund automatisch, ob das Gespräch dauerhaft relevante Informationen enthält (z. B. Nutzerpräferenzen, bekannte IPs, gelöste Probleme). Wenn ja, wird der Fakt still gespeichert – ohne Verzögerung für dich.

### Manuelles Merken
Du kannst Kumio aktiv anweisen, etwas zu speichern:
```
"Merke dir: Der Pi-hole läuft auf 192.168.1.10"
"Bitte merke dir, dass ich im Team Infrastruktur arbeite"
"Kumio, speichere: Produktions-Cluster läuft auf Node k3s-prod-01"
```

### Erinnerungen abrufen
```
"Was weißt du über unsere Infrastruktur?"
"Weißt du noch, welche IP der Pi-hole hatte?"
"Erinnerst du dich an meinen Namen?"
```

### Erinnerungen löschen (zweistufig / sicher)
Das Löschen von Erinnerungen läuft **immer zweistufig** ab, um versehentliches Löschen zu verhindern:

1. **Schritt 1 – Vorschau**: Sage Kumio, was vergessen werden soll:
   ```
   "Vergiss, dass der Pi-hole auf 192.168.1.10 läuft"
   ```
   Kumio zeigt dir die gefundenen Kandidaten mit Inhalt und ID an – **löscht aber noch nichts**.

2. **Schritt 2 – Bestätigung**: Kumio fragt dich zur Bestätigung. Antworte:
   ```
   "Ja, lösch das" oder "alle löschen"
   ```
   Erst dann werden die Einträge dauerhaft entfernt.

## 4. Agenten, Workflows & Logs

Zusätzlich zu den Modulen bietet Kumio fortschrittliche Werkzeuge zur Automatisierung und Überwachung.

### 4.1 Eigene Agenten (Aufgaben) 🤖
Im Tab **Agenten** kannst du spezialisierte AI-Personas erstellen:
1. Vergebe einen **Namen** und eine **Beschreibung**.
2. Definiere den **System-Prompt** (z.B. "Du bist ein Sicherheits-Analyst für Kubernetes Logs").
3. Wähle den **LLM-Provider** aus deinen konfigurierten Providern.
4. **Module auswählen**: Bestimme, auf welche Tools (Kubernetes, Pi-hole etc.) dieser Agent Zugriff hat.
5. **Sequence Builder**: Definiere eine geordnete Abfolge von Modul-Schritten, die der Agent bei Aktivierung ausführen soll.

### 4.2 Workflows (DAG Automatisierung) ⚙️
Im Tab **Workflows** kannst du komplexe Automatisierungsketten visuell gestalten:
1. **Nodes hinzufügen**: Nutze Trigger (Manuell, Zeitplan/Cron), Agent-Tasks oder Logik-Elemente (Conditions, Loops).
2. **Nodes verbinden**: Ziehe eine Verbindung von einem Ausgangs-Dot (unten) zum Ziel-Node.
3. **Konfiguration**: Klicke einen Node an, um im Inspector (rechts) Details wie Cron-Intervalle oder Agent-Zuweisungen festzulegen.
4. **Monitoring**: Im **Run-Dashboard** siehst du live, welche Schritte gerade ausgeführt wurden, inklusive Erfolg oder Fehlermeldungen.

### 5.3 Zentrales Logging 📜
Im Tab **Logs** laufen alle System- und Modul-Informationen in Echtzeit zusammen:
- **Filter**: Filter nach Log-Level (INFO, WARN, ERROR, CRIT), Kategorie oder Zeitbereich.
- **Volltextsuche**: Suche gezielt nach bestimmten Events oder Meldungen.
- **Detail-Ansicht**: Klicke auf eine Zeile, um den vollständigen Traceback oder Meta-Daten zu sehen.
- **Export**: Lade Logs als CSV oder JSON für externe Analysen herunter.

---

## 6. Chat-Interface

### AI-Avatar
Das Chat-Interface verwendet durchgehend das **Kumio-Logo** (`chat_logo.png`) als Avatar für alle AI-Nachrichten – sowohl bei regulären Antworten als auch beim Lade-Indikator (Typing-Bubble). Der User-Avatar ist ein neutrales Personen-Icon.

### Typing-Indikator
Während Kumio eine Antwort berechnet, erscheint eine kompakte Bubble mit drei animierten Punkten direkt unterhalb des letzten User-Beitrags. Die Bubble schließt nach Eingang der Antwort automatisch.

---

## 6. Sicherheit und Best Practices

1. **Vorsicht bei destruktiven Aktionen:** Insbesondere das Löschen von VMs (Proxmox) oder DNS-Records (IONOS) ohne manuelles Review kann zu Ausfallzeiten führen. Formulierungen im Chat immer präzise halten.
2. **Arbeiten mit Environments:** Teile Modulen idealerweise explizit mit, auf welcher Connection sie arbeiten sollen: "Starte die VM 105 auf der Verbindung 'Prod Cluster'".
3. **Vault & Logs:** Alle sensiblen Daten liegen verschlüsselt im Vault. Beachte, dass Kumio Logs speichert. Geheime API-Keys werden automatisch maskiert, aber achte dennoch darauf, keine sensiblen Daten direkt im System-Prompt von Agenten zu hinterlegen.
4. **Monitoring:** Nutze den Logs-Tab regelmäßig, um Fehler in automatisierten Workflows frühzeitig zu erkennen.
5. **Zugriff (Kubernetes):** Nach einem regulären Kubernetes-Rollout mit Traefik erreichst du Kumio unter `http://kumio.conbro.local`.

