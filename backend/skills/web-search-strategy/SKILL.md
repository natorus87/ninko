---
name: web-search-strategy
description: Websuche Recherche Suchanfrage optimieren aktuelle Informationen Preis Nachrichten Fakten prüfen
modules: [web_search]
---

## Effektive Suchstrategien

### Wann suchen?
- Aktuelle Ereignisse, Preise, Kurse (Trainingsdaten veraltet)
- Spezifische Produkt-/Software-Versionen
- Offizielle Dokumentation, RFCs, CVEs
- Personen, Unternehmen, aktuelle Stellungnahmen

### Query-Optimierung
| Ziel | Statt | Besser |
|---|---|---|
| Aktuelle Preise | "Bitcoin Preis" | "Bitcoin EUR Kurs aktuell" |
| Fehler lösen | "Kubernetes Error" | "kubernetes CrashLoopBackOff OOMKilled lösung 2024" |
| Offizielle Doku | "Python asyncio" | "Python asyncio site:docs.python.org" |
| CVE/Sicherheit | "Log4j Sicherheit" | "CVE-2021-44228 Log4Shell patch" |

### Einmal suchen – nie loopen
- `perform_web_search()` **genau einmal** aufrufen pro Anfrage
- Ergebnis analysieren und direkt antworten
- Bei 0 Ergebnissen: Query reformulieren (andere Keywords), **nicht** erneut mit gleichem Query suchen

### Ergebnis-Qualität bewerten
- **Hoch vertrauen**: offizielle Domains (.gov, .org, vendor-domains), Datum aktuell
- **Mittleres Vertrauen**: bekannte Nachrichtenseiten, Stack Overflow, GitHub
- **Niedrig vertrauen**: einzelne Blogs ohne Datum, Social Media
- Widersprüchliche Quellen → mehrere nennen, Unsicherheit transparent machen

### Antwort-Format
```
Laut [Quelle] vom [Datum]:
<Zusammenfassung der gefundenen Information>

Quelle: <URL>
```
