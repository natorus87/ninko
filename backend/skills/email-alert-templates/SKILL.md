---
name: email-alert-templates
description: E-Mail senden Alert Benachrichtigung IT-Alarm Vorlage Betreff Format Empfänger Warnung Monitoring
modules: [email]
---

## E-Mail-Formate für IT-Benachrichtigungen

### Betreff-Konventionen
```
[KRITISCH] <System>: <Problem>          → sofortiger Handlungsbedarf
[WARNUNG]  <System>: <Symptom>          → Überwachung nötig
[INFO]     <System>: <Ereignis>         → zur Kenntnis
[GELÖST]   <System>: <Problem behoben>  → Abschluss-Meldung
```

### Alert-E-Mail (Monitoring)
```
Betreff: [KRITISCH] Kubernetes: Pod kumio-backend CrashLoopBackOff

Hallo Team,

PROBLEM: Pod kumio-backend befindet sich seit 10 Minuten im Status CrashLoopBackOff.

DETAILS:
- Namespace: kumio
- Pod: kumio-backend-abc123
- Restarts: 5 in 10 Minuten
- Letzter Fehler: OOMKilled (Speicherlimit überschritten)

MASSNAHME ERFORDERLICH:
- Memory-Limit prüfen und ggf. erhöhen
- kubectl logs <pod> für Details

Automatisch gemeldet von Kumio IT-Operations
```

### Sammel-Bericht (wöchentlich/täglich)
- Betreff: `[BERICHT] Wöchentlicher IT-Status – KW{n}`
- Struktur: Zusammenfassung → Offene Incidents → Geplante Wartungen → Metriken

### send_email Parameter
```
to: Empfänger (Liste oder einzeln)
subject: Betreff (immer Präfix [KRITISCH/WARNUNG/INFO])
body: HTML oder Plaintext
cc: optional für eskalierte Alerts
```

### Eskalations-Kette
1. Warnung → Team-Verteiler
2. Kritisch → Team + Teamleiter (cc)
3. Ausfall > 30 Min → Teamleiter + Management (Direktnachricht)
