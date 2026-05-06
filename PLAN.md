# Ninko Review — Handlungsplan

**Datum**: 2026-05-06
**Status**: 🟢 Green — Alle Security Fixes erledigt

---

## Noch offen

*Keine offenen Items.*

---

## Erledigt ✅

### HIGH-1 — Frontend XSS Fix (~2h)

**Alle 40+ Module tab.js gesichert** gegen XSS via `innerHTML`-Injection:

| Kategorie | Module | Escape-Strategie |
|-----------|--------|-----------------|
| K8s/Pods | `kubernetes` | `_escapeHtml` custom inline |
| IIFE-static | `fritzbox`, `ubiquiti`, `netgear`, `mikrotik`, `cisco`, `nextcloud`, `openproject`, `lenovo_xclarity`, `slack`, `microsoft_entra`, `microsoft_intune`, `hpe_ilo`, `email`, `telegram`, `teams`, `discord`, `homeassistant` | `esc()` helper |
| IIFE-dynamic | `proxmox`, `glpi`, `synology`, `confluence`, `jira`, `redmine`, `zabbix`, `netbox`, `gitlab` | `esc()` helper |
| Custom-object | `checkmk`, `opnsense`, `tasmota`, `ionos` | `esc()` helper |
| Already-safe | `pihole`, `docker`, `linux_server`, `wordpress`, `licium` | Hat bereits Escape-Funktion |
| Reference | `_template/frontend/tab.js` | Dokumentiert Pattern korrekt |

### MED-7 — LLM Output-Format: Markdown-Tabellen (~15min pro Modul)

**Ziel**: Konsistentes Ausgabeformat für alle Listen in allen Modulen.

**Lösung**: Jedem `*_SYSTEM_PROMPT` einen EN `Ausgabe-Format`-Abschnitt hinzufügen (DE nicht nötig - Format-Guidance ist sprachunabhängig):

```
Ausgabe-Format für Übersichten (IMMER):
- Bei Listen (Nodes, Pods, VMs, Services, Deployments, Hosts, etc.): IMMER Markdown-Tabellen
- Beispiel: | Name | Status | Age | Restarts |
           |------|--------|-----|---------|
           | pod-1 | Running | 2d | 0 |
- NICHT als Bullet-Liste, Fließtext oder JSON
- Zahlen immer mit Einheiten (%, GB, MHz)
- Status farblich markieren wenn sinnvoll
```

**Modules die das brauchen** (haben List-Tools):

| Modul | Prompt-Variable | List-Tools |
|-------|---------------|------------|
| `kubernetes` | `K8S_SYSTEM_PROMPT` | list_namespaces, list_pods, list_deployments, list_services, list_ingresses, list_pvcs |
| `proxmox` | `PROXMOX_SYSTEM_PROMPT` | get_nodes, list_all_vms, list_containers |
| `glpi` | `GLPI_SYSTEM_PROMPT_DE/EN` | search_tickets, list_groups, list_categories |
| `checkmk` | `CHECKMK_SYSTEM_PROMPT` | checkmk_get_hosts, checkmk_get_services, checkmk_get_alerts |
| `docker` | `DOCKER_SYSTEM_PROMPT` | list_containers, list_images, list_volumes |
| `pihole` | `PIHOLE_SYSTEM_PROMPT` | get_query_log, get_top_domains, get_top_clients |
| `qdrant` | `QDRANT_SYSTEM_PROMPT` | list_collections, list_entries |
| `synology` | `SYSTEM_PROMPT` | get_storage, list_packages |
| `redmine` | `SYSTEM_PROMPT` | search_tickets, list_groups |
| `netbox` | `SYSTEM_PROMPT` | list_sites, list_devices, list_vlans |
| `github` | `SYSTEM_PROMPT` | list_repos, list_issues, list_pulls |
| `gitlab` | `SYSTEM_PROMPT` | list_projects, list_pipelines, list_mrs |
| `jira` | `SYSTEM_PROMPT` | search_issues, list_projects |
| `confluence` | `SYSTEM_PROMPT` | list_pages, list_spaces |
| `wordpress` | `WORDPRESS_SYSTEM_PROMPT` | list_posts, list_pages, list_plugins |
| `linux_server` | `LINUX_SERVER_SYSTEM_PROMPT` | list_processes, list_services |
| `zabbix` | `SYSTEM_PROMPT` | list_hosts, list_problems |

**Modules die KEIN List-Format brauchen** (keine/kaum Listen):
`telegram`, `teams`, `homeassistant`, `tasmota`, `fritzbox`, `ubiquiti`, `netgear`, `mikrotik`, `cisco`, `nextcloud`, `openproject`, `lenovo_xclarity`, `microsoft_entra`, `microsoft_intune`, `hpe_ilo`, `email`, `discord`, `slack`, `licium`, `mcp_server`, `ionos`, `opnsense`

**Fixe Reihenfolge** (alphabetisch):
1. checkmk
2. confluence
3. docker
4. github
5. gitlab
6. glpi
7. jira
8. kubernetes
9. linux_server
10. netbox
11. pihole
12. proxmox
13. qdrant
14. redmine
15. synology
16. wordpress
17. zabbix

| Task | Status | Datei |
|------|--------|-------|
| SEC-1 | ✅ | `config.py` - SESSION_SECRET Exception in ALLEN Environments |
| SEC-2 | ✅ | `routes_chat.py` - SSE-Stream Auth-Guard |
| SEC-3 | ✅ | `routes_auth.py` - Password-Complexity field_validator |
| SEC-4 | ✅ | `app.js` - DOMPurify FORBID_TAGS style |
| SEC-5 | ✅ | `base_agent.py` - Audit-Event Exception loggen |

### Code Quality Fixes (2026-05-06)

| Task | Status | Datei |
|------|--------|-------|
| MED-1 | ✅ | Exception-Handler enger gefasst |
| MED-2 | ✅ | Secret-Redaction erweitert (bearer, auth, private, credential) |
| MED-3 | ✅ | Blacklist-Fehler loggen statt verschlucken |
| MED-4 | ✅ | CHAT_HISTORY_TTL_SECONDS konfigurierbar |
| MED-5 | ✅ | Pipeline: "Schritt X" Formatierung → Modulname |
| MED-6 | ✅ | Pipeline: Kontext-Weitergabe (aber: keine Injection zw. unabhängigen Steps) |
| LOW-1 | ✅ | atexit Cleanup für globale States |

### Architektur-Errungenschaften ✅

- Vault mit PBKDF2 + SQLite-Fallback ✅
- Module Registry mit Hot-Reload ✅
- CWE-312 Sensitivity Detection in connections.py ✅
- Brute-Force Protection (CWE-307) ✅
- Session Blacklisting (CWE-613) ✅
- DOMPurify für Modul-Frontend Loading ✅
- Trusted-Proxy-Validierung (CWE-918) ✅
- SafeGuard 3-Stage Pipeline ✅

### Entfernt

| Task | Reason |
|------|--------|
| LOW-2 | Message/Agent-Safeguard sind absichtlich getrennt |
| LOW-3 | `_escapeHtml()` existiert bereits in `app.js:6839` |

---

## Know-How: Pipeline Anti-Pattern

**Pipeline Parallel Execution funktioniert NICHT für Kontext-Weitergabe**:
- `_build_execution_groups()` gibt bei `[list(range(n))]` ALLE Steps in einer Gruppe parallel
- `step_results` wird aber erst NACH `asyncio.gather()` gefüllt
- Jeder Step sieht `prior_results = {}` → kein Step kommt an Ergebnisse anderer
- **Lösung**: `return [[i] for i in range(n)]` (sequentiell) wenn Kontext fließen muss

---

## Priorisierung

| Priority | Task | Aufwand |
|----------|------|---------|
| HIGH-1 | Frontend XSS fixen | ~2h |
| MED-7 | LLM Output-Format: Markdown-Tabellen | ~15min pro Modul |
