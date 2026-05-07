# Ninko – Offene Tasks

**Datum**: 2026-05-07
**Letztes Review**: Security Audit + Network Analysis Modul (Mai 2026)

---

## 🔴 Offene Tasks

| # | Task | File | Problem | Aufwand |
|---|------|------|---------|---------|
| 2 | CSP Header `unsafe-inline` Scripts beheben | `main.py` | XSS-Ausnutzung vereinfacht; Nonce-basiert oder `'strict-dynamic'` | 1-2h |
| 21 | `replace_history` ohne Input-Limit | `routes_chat.py:354` | Keine Begrenzung Messages → ChromaDB/Redis-Erschöpfung | 30 min |

---

## 🟢 Network Analysis Modul (2026-05-07)

**Pfad**: `backend/modules/network_analysis/`
**Tools**: `dns_lookup`, `reverse_dns`, `traceroute`, `ping_host`, `get_network_info`
**Routing**: `netzwerkanalyse`, `dns lookup`, `traceroute`, `whois`, `ip-adresse`

### Safeguard Safe-Keywords
`netzwerkanalyse`, `traceroute`, `tracepath`, `dns lookup`, `ip-adresse`, `server-analyse`, `website-analyse`

### MicroK8s NET_RAW Gotcha
Ping/socket-Tools funktionieren via Socket-Fallback ohne ROOT-Capabilities.

---

## 🟢 Nice-to-have

- MOB-2: `<header role="banner">` für Screenreader
- MOB-3: 375px/480px Breakpoint für kleine Tablets
- MOB-4: Touch-Drag/Swipe für Sidebar
- 17 weitere FE-4/FE-5/Bild-URL-Escapes aus altem Plan

---

## Know-How: Pipeline Anti-Pattern

**Pipeline Parallel Execution funktioniert NICHT für Kontext-Weitergabe**:
- `_build_execution_groups()` gibt bei `[list(range(n))]` ALLE Steps in einer Gruppe parallel
- `step_results` wird aber erst NACH `asyncio.gather()` gefüllt
- Jeder Step sieht `prior_results = {}` → kein Step kommt an Ergebnisse anderer
- **Lösung**: `return [[i] for i in range(n)]` (sequentiell) wenn Kontext fließen muss
