"""
Ninko Safeguard Middleware — model-agnostic safety classifier.

Integrates into routes_chat.py before the 4-tier orchestrator routing:

    safeguard = request.app.state.safeguard
    if safeguard and not body.confirmed:
        result = await safeguard.check(body.message)
        if result.requires_confirmation:
            await status_bus.done(body.session_id)
            return ChatResponse(confirmation_required=True, safeguard=result.to_dict(), ...)

Three-stage evaluation per message:
  1. Disabled check   — returns SAFE immediately, no LLM call.
  2. Keyword pre-filter — instant result for unambiguous short messages.
  3. LLM classifier   — full JSON classification with robust parser.

On any error (timeout, parse failure) → fail-safe: requires_confirmation=True.
"""

from __future__ import annotations

import json
import re
import logging
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from openai import AsyncOpenAI

if TYPE_CHECKING:
    from core.agent_config_store import AgentConfigStore

logger = logging.getLogger("ninko.core.safeguard")


# ─── Compiled regex constants ─────────────────────────────────────────────────

# Strips <think>...</think> blocks emitted by reasoning models (Qwen3.5, DeepSeek-R1)
_RE_THINK    = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
# Strips markdown code fences the model may wrap around JSON
_RE_MD_FENCE = re.compile(r"```(?:json)?\s*|\s*```")
# Extracts the first {...} block when JSON is embedded in prose
_RE_JSON_OBJ = re.compile(r"\{[^{}]+\}", re.DOTALL)


# ─── LLM classifier prompt ────────────────────────────────────────────────────

SAFEGUARD_SYSTEM_PROMPT = """You are a strict safety classifier for an IT automation platform.
Your ONLY job is to classify user requests. You NEVER execute actions yourself.

## CATEGORIES

**DESTRUCTIVE** — irreversible operations that cause permanent data loss or removal:
- Delete, remove, drop, wipe, purge, truncate, destroy, kill, terminate, erase, clear, shred, nuke
- kubectl delete, rm -rf, DROP TABLE, pvremove, format disk
- German: lösche, entferne, vernichte, leere, bereinige, tilge

**STATE_CHANGING** — creates, modifies, or reconfigures resources (may be reversible):
- Create, deploy, install, start, launch, run, apply, add, enable, disable
- Update, modify, patch, overwrite, reset, change, edit, set, scale, restart, configure, migrate, rotate, revoke
- German: erstelle, ändere, aktualisiere, skaliere, starte, installiere, deploye, konfiguriere, migriere

**SAFE** — read-only queries, informational, status, help, explanations:
- Get, list, show, describe, status, logs, explain, how-to, what-is, check, monitor, search, find
- German: zeige, liste, beschreibe, erkläre, prüfe, was ist, wie viele

## OUTPUT FORMAT
Respond with ONLY a single JSON object — no explanation, no markdown, no preamble.

{"violation": 0 or 1, "category": "SAFE" | "DESTRUCTIVE" | "STATE_CHANGING", "rationale": "one sentence"}

- violation=1 → confirmation required before execution
- violation=0 → safe to execute directly

## RULES
- DESTRUCTIVE and STATE_CHANGING always produce violation=1
- SAFE always produces violation=0
- Pronouns in context ("delete it", "lösche ihn", "restart that") inherit the action category
  of the referenced resource — treat them as DESTRUCTIVE or STATE_CHANGING accordingly
- Pure confirmation words ("yes", "ja", "ok", "confirm") without a new action → SAFE
- Conversational messages ("hello", "thanks", "what can you do") → SAFE
- How-to questions ("how do I create...") → SAFE (question, not execution request)

## EXAMPLES

Input: "delete all pods in production namespace"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Requests deletion of all production pods — irreversible."}

Input: "drop the database users table"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Irreversible deletion of a database table."}

Input: "rm -rf /var/log on the linux server"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Recursive file deletion — irreversible data loss."}

Input: "lösche den nginx-test-pod"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Requests deletion of a Kubernetes pod."}

Input: "lösche ihn wieder"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Pronoun refers to a previously created resource — deletion is irreversible."}

Input: "entferne den alten Cronjob"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Requests removal of a Kubernetes CronJob."}

Input: "scale deployment frontend to 3 replicas"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Modifies deployment replica count."}

Input: "erstelle einen nginx test pod in kubernetes"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Creates a new pod resource in the cluster."}

Input: "create a deployment with 3 replicas"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Creates a new Kubernetes deployment."}

Input: "update the database password in all configmaps"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Modifies credentials across multiple resources."}

Input: "restart the proxmox node"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Reboots a host — causes downtime."}

Input: "disable the pi-hole blocking"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Changes DNS blocking state."}

Input: "rotate the Kubernetes service account token"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Rotates a credential — existing token becomes invalid."}

Input: "apply the updated ingress manifest"
Output: {"violation": 1, "category": "STATE_CHANGING", "rationale": "Applies a manifest that modifies cluster state."}

Input: "show me all nodes in the cluster"
Output: {"violation": 0, "category": "SAFE", "rationale": "Read-only cluster query."}

Input: "what is the CPU usage of my proxmox host?"
Output: {"violation": 0, "category": "SAFE", "rationale": "Informational query — no action."}

Input: "list all GLPI tickets with status open"
Output: {"violation": 0, "category": "SAFE", "rationale": "Read-only ticket query."}

Input: "get the logs of pod nginx-test-pod"
Output: {"violation": 0, "category": "SAFE", "rationale": "Read-only log retrieval."}

Input: "how do I create a kubernetes deployment?"
Output: {"violation": 0, "category": "SAFE", "rationale": "How-to question — no action executed."}

Input: "wipe the ceph pool data"
Output: {"violation": 1, "category": "DESTRUCTIVE", "rationale": "Irreversible deletion of entire storage pool."}

Classify the user input now. Respond ONLY with the JSON object."""


# ─── Category and result types ────────────────────────────────────────────────

class ActionCategory(str, Enum):
    SAFE           = "SAFE"
    DESTRUCTIVE    = "DESTRUCTIVE"
    STATE_CHANGING = "STATE_CHANGING"
    UNKNOWN        = "UNKNOWN"   # Only on parse/classifier failure


@dataclass
class SafeguardResult:
    requires_confirmation: bool
    category: ActionCategory
    rationale: str
    raw_response: str = ""

    def to_dict(self) -> dict:
        return {
            "requires_confirmation": self.requires_confirmation,
            "category": self.category.value,
            "rationale": self.rationale,
        }


# ─── Keyword pre-filter ───────────────────────────────────────────────────────
#
# Each entry is (keyword, word_boundary_required).
# word_boundary=True  → matched only as a whole word (re \b) to avoid
#                        false positives from substrings.
# word_boundary=False → substring match (sufficient for longer stems).

_DESTRUCTIVE_TERMS: tuple[tuple[str, bool], ...] = (
    # ── German (DE) ──────────────────────────────────────────────────────────
    ("lösch",          False),  # lösche/löschen/löscht/löschst
    ("entfern",        False),  # entferne/entfernen/entfernt
    ("vernicht",       False),  # vernichte/vernichten
    ("bereinig",       False),  # bereinige/bereinigen
    ("tilg",           False),  # tilge/tilgen
    ("leere ",         True),   # leere den Cache — not "Leere" as noun
    # ── English (EN) ─────────────────────────────────────────────────────────
    ("delete",         False),
    ("remove",         False),
    ("destroy",        False),
    ("wipe",           False),
    ("purge",          False),
    ("truncate",       False),
    ("shred",          False),
    ("erase",          False),
    ("nuke",           False),
    ("terminate",      False),
    # ── French (FR) ──────────────────────────────────────────────────────────
    ("supprim",        False),  # supprime/supprimer/supprimez/suppriment
    ("efface",         False),  # efface/effacer/effacez
    ("enlève",         False),  # enlève/enlever
    ("enlever",        False),
    ("détru",          False),  # détruis/détruit/détruire
    ("effac",          False),  # effacer stem
    ("vider",          False),  # vider (empty/clear)
    ("vide ",          True),   # vide le cache — not "évident"
    # ── Spanish (ES) ─────────────────────────────────────────────────────────
    ("elimin",         False),  # elimina/eliminar/elimine/eliminad
    ("borrar",         False),  # borrar
    ("borra ",         True),   # borra el pod — not "aborra"
    ("destruy",        False),  # destruye/destruyendo/destruir
    ("destruir",       False),
    ("suprimir",       False),
    ("vaciar",         False),  # vaciar (empty)
    ("vacía ",         True),   # vacía el disco
    # ── Italian (IT) ─────────────────────────────────────────────────────────
    ("cancell",        False),  # cancella/cancellare/cancellato
    ("rimuovi",        False),
    ("rimuover",       False),
    ("svuota",         False),  # svuota/svuotare
    ("distrug",        False),  # distruggi/distruggere
    # ── Portuguese (PT) ──────────────────────────────────────────────────────
    ("apagar",         False),  # apagar
    ("apaga ",         True),   # apaga o pod
    ("destrói",        False),
    ("destruir",       False),
    ("limpar",         False),
    ("limpa ",         True),   # limpa o cache
    # ── Dutch (NL) ───────────────────────────────────────────────────────────
    ("verwijder",      False),  # verwijder/verwijderen/verwijderd
    ("verniet",        False),  # vernietig/vernietigen
    ("wissen",         False),  # wissen (erase)
    ("wis ",           True),   # wis de data — not "wist"
    ("leegmak",        False),  # leegmaken
    # ── Polish (PL) ──────────────────────────────────────────────────────────
    ("usuń",           False),  # usuń (delete, imperative)
    ("skasuj",         False),  # skasuj (delete/wipe)
    ("zniszcz",        False),  # zniszcz (destroy)
    ("wyczyść",        False),  # wyczyść (clear/wipe)
    ("usuwa",          False),  # usuwa (deletes)
    # ── Chinese (ZH) ─────────────────────────────────────────────────────────
    ("删除",            False),  # shānchú — delete
    ("清除",            False),  # qīngchú — clear/purge
    ("移除",            False),  # yíchú — remove
    ("销毁",            False),  # xiāohuǐ — destroy
    ("格式化",           False),  # géshìhuà — format
    ("清空",            False),  # qīngkōng — empty/wipe
    # ── Japanese (JA) ────────────────────────────────────────────────────────
    ("削除",            False),  # sakujo — delete
    ("消去",            False),  # shōkyo — erase
    ("消して",           False),  # keshite — delete (te-form)
    ("削除して",         False),  # sakujo shite — please delete
    # ── CLI / SQL / IaC patterns ──────────────────────────────────────────────
    ("rm -",           False),  # rm -rf / rm -r
    ("drop ",          True),   # DROP TABLE — not "dropdown"
    # "del" intentionally omitted: common article in ES/IT/FR ("del pod" = "of the pod")
    ("kill ",          True),   # kill pod — not "skill"
    ("kubectl delete", False),
    ("pvremove",       False),
    ("wipefs",         False),
    ("mkfs",           False),
    ("format ",        True),   # format disk — not "format string"
    ("terraform destroy", False),
)

_STATE_TERMS: tuple[tuple[str, bool], ...] = (
    # ── German (DE) — create ─────────────────────────────────────────────────
    ("erstell",        False),  # erstelle/erstellen/erstellt
    ("anlegen",        False),
    ("lege an",        False),
    ("deploye",        False),
    ("installier",     False),
    ("starte ",        True),   # starte den Pod — not "Neustart"
    ("hochfahren",     False),
    ("fahre hoch",     False),
    # German — modify
    ("ändere",         False),
    ("ändert",         False),
    ("ändern",         False),
    ("aktualisier",    False),
    ("skalier",        False),
    ("konfiguriere",   False),
    ("konfigurieren",  False),
    ("bearbeite",      False),
    ("migriere",       False),
    ("neustart",       False),
    ("neustarten",     False),
    ("zurücksetzen",   False),
    ("deaktiviere",    False),
    ("aktiviere",      False),
    ("rotiere",        False),  # rotiere das Zertifikat
    ("widerrufe",      False),  # widerrufe den Token
    # ── English (EN) — create / deploy ───────────────────────────────────────
    ("create",         False),
    ("deploy",         False),
    ("install",        False),
    ("launch",         False),
    ("provision",      False),
    ("enable",         False),
    ("disable",        False),
    # English — modify
    ("update",         False),
    ("upgrade",        False),
    ("patch",          False),
    ("modify",         False),
    ("configure",      False),
    ("reconfigure",    False),
    ("overwrite",      False),
    ("migrate",        False),
    ("scale",          False),
    ("resize",         False),
    ("rotate",         False),
    ("revoke",         False),
    ("apply",          False),
    ("edit",           False),
    ("restart",        False),
    ("reboot",         False),
    ("reset",          False),
    ("add ",           True),
    ("set ",           True),
    # ── French (FR) — create ─────────────────────────────────────────────────
    ("créer",          False),  # créer
    ("crée ",          True),   # crée un pod — not "recréer"
    ("déploi",         False),  # déploie/déployer/déployez
    ("lancer",         False),
    ("lance ",         True),   # lance l'app
    ("activer",        False),
    ("active ",        True),   # active le module
    ("désactiver",     False),
    ("désactive",      False),
    # French — modify
    ("modifier",       False),
    ("modifie",        False),
    ("configurer",     False),
    ("configure",      False),
    ("mettre à jour",  False),  # mets à jour / mettre à jour
    ("mets à jour",    False),
    ("mise à jour",    False),
    ("redémarr",       False),  # redémarre/redémarrer
    ("redémarrage",    False),
    ("migrer",         False),
    # ── Spanish (ES) — create ────────────────────────────────────────────────
    ("crear",          False),
    ("crea ",          True),   # crea un pod — not "recrear"
    ("desplegar",      False),
    ("despleg",        False),  # despliega/desplegar
    ("lanzar",         False),
    ("lanza ",         True),
    ("activar",        False),
    ("activa ",        True),
    ("desactivar",     False),
    ("desactiva",      False),
    # Spanish — modify
    ("actualizar",     False),
    ("actualiz",       False),
    ("configurar",     False),
    ("modificar",      False),
    ("modific",        False),
    ("reiniciar",      False),
    ("reinici",        False),
    ("escalar",        False),
    ("aplicar",        False),
    ("migrar",         False),
    # ── Italian (IT) — create ────────────────────────────────────────────────
    ("creare",         False),
    ("crea ",          True),   # crea un pod
    ("distribuire",    False),
    ("avviare",        False),
    ("avvia ",         True),
    ("attivare",       False),
    ("attiva ",        True),
    ("disattivare",    False),
    ("disattiva",      False),
    # Italian — modify
    ("aggiornare",     False),
    ("aggior",         False),  # aggiorna/aggiornare
    ("configurare",    False),
    ("modificare",     False),
    ("modifica ",      True),
    ("riavviare",      False),
    ("riavvia",        False),
    ("migrare",        False),
    # ── Portuguese (PT) — create ─────────────────────────────────────────────
    ("criar",          False),
    ("cria ",          True),   # cria um pod
    ("implantar",      False),
    ("implementar",    False),
    ("lançar",         False),
    ("lança ",         True),
    ("ativar",         False),
    ("ativa ",         True),
    ("desativar",      False),
    ("desativa",       False),
    # Portuguese — modify
    ("atualizar",      False),
    ("atualiz",        False),
    ("configurar",     False),
    ("modificar",      False),
    ("reiniciar",      False),
    ("migrar",         False),
    # ── Dutch (NL) — create ──────────────────────────────────────────────────
    ("aanmaken",       False),
    ("maak aan",       False),
    ("maak ",          True),   # maak een pod aan — "maak aan" may be non-contiguous
    ("implementeren",  False),
    ("implementeer",   False),
    ("installeren",    False),
    ("installeer",     False),
    ("activeren",      False),
    ("activeer",       False),
    ("deactiveren",    False),
    ("deactiveer",     False),
    # Dutch — modify
    ("bijwerken",      False),
    ("configureren",   False),
    ("configureer",    False),
    ("wijzigen",       False),
    ("wijzig ",        True),
    ("herstarten",     False),
    ("herstart",       False),
    ("migreren",       False),
    # ── Polish (PL) — create ─────────────────────────────────────────────────
    ("utwórz",         False),  # create
    ("wdróż",          False),  # deploy
    ("zainstaluj",     False),  # install
    ("uruchom",        False),  # start/run
    ("włącz",          False),  # enable
    ("wyłącz",         False),  # disable
    # Polish — modify
    ("zaktualizuj",    False),
    ("skonfiguruj",    False),
    ("zmodyfiku",      False),
    ("zrestartuj",     False),
    ("zmigruj",        False),
    # ── Chinese (ZH) — create ────────────────────────────────────────────────
    ("创建",             False),  # chuàngjiàn — create
    ("部署",             False),  # bùshǔ — deploy
    ("安装",             False),  # ānzhuāng — install
    ("启动",             False),  # qǐdòng — start
    ("启用",             False),  # qǐyòng — enable
    ("禁用",             False),  # jìnyòng — disable
    # Chinese — modify
    ("更新",             False),  # gēngxīn — update
    ("配置",             False),  # pèizhì — configure
    ("修改",             False),  # xiūgǎi — modify
    ("重启",             False),  # chóngqǐ — restart
    ("扩展",             False),  # kuòzhǎn — scale out
    ("缩减",             False),  # suōjiǎn — scale in
    ("应用",             False),  # yīngyòng — apply
    ("编辑",             False),  # biānjí — edit
    ("迁移",             False),  # qiānyí — migrate
    # ── Japanese (JA) — create ───────────────────────────────────────────────
    ("作成",             False),  # sakusei — create
    ("デプロイ",          False),  # depuroi — deploy
    ("インストール",       False),  # insutōru — install
    ("起動",             False),  # kidō — start
    ("有効化",            False),  # yūkōka — enable
    ("無効化",            False),  # mukōka — disable
    # Japanese — modify
    ("更新",             False),  # kōshin — update
    ("設定",             False),  # settei — configure/set
    ("変更",             False),  # henkō — change/modify
    ("再起動",            False),  # saikidō — restart
    ("スケール",          False),  # sukēru — scale
    ("適用",             False),  # tekiyō — apply
    ("移行",             False),  # ikō — migrate
    # ── CLI / IaC patterns ───────────────────────────────────────────────────
    ("kubectl apply",  False),
    ("kubectl create", False),
    ("kubectl patch",  False),
    ("kubectl edit",   False),
    ("kubectl scale",  False),
    ("kubectl label",  False),
    ("kubectl annotate", False),
    ("kubectl taint",  False),
    ("helm install",   False),
    ("helm upgrade",   False),
    ("helm uninstall", False),
    ("terraform apply",False),
    ("ansible-playbook", False),
)

# Unambiguously read-only patterns — return SAFE without any LLM call.
# Checked against start and interior of the lowercased message.
_SAFE_PATTERNS: tuple[str, ...] = (
    # English
    "show ", "list", "get ", "describe ", "status",
    "logs ",                            # trailing space avoids matching "/var/log"
    "what ", "how ", "which ", "explain", "help", "search", "find ", "check ", "monitor",
    # German
    "zeige ", "zeig ", "liste", "was ", "wie ", "welche", "wieviel", "wie viele",
    "erkläre", "hilfe", "suche", "finde ", "prüfe ",
    # French
    "montre ", "affiche ", "liste ", "décris ", "statut", "qu'est-ce", "comment ", "vérif",
    # Spanish
    "muestra ", "lista ", "describe ", "estado", "qué es", "cómo ", "verif",
    # Italian
    "mostra ", "elenca ", "descrivi ", "stato", "cos'è", "come ", "controlla ",
    # Portuguese
    "mostra ", "lista ", "descreve ", "estado", "o que é", "como ", "verifica ",
    # Dutch
    "toon ", "lijst", "beschrijf ", "status", "wat is", "hoe ", "controleer ",
    # Polish
    "pokaż ", "wylistuj ", "opisz ", "status", "co to", "jak ", "sprawdź ",
    # Chinese
    "显示", "列出", "查看", "状态", "检查", "描述", "获取",
    # Japanese
    "表示", "一覧", "確認", "ステータス", "調べ", "教えて", "状態",
)


# ─── Tool-level: always-safe tools (skip LLM classifier) ─────────────────────
#
# These tools are either purely read-only or represent benign meta-operations
# (memory, agent creation, pipeline coordination). Checking them against the
# LLM classifier would add latency without security benefit.

_TOOL_READONLY: frozenset[str] = frozenset({
    # Memory / knowledge operations
    "recall_memory", "remember_fact", "forget_fact", "confirm_forget",
    # Orchestration / meta
    "create_custom_agent", "install_skill",
    "create_linear_workflow", "execute_workflow", "run_pipeline",
    "generate_image",
    # Search
    "perform_web_search",
    # Kubernetes read-only
    "get_cluster_status", "get_all_pods", "get_failing_pods",
    "list_namespaces", "list_services", "get_recent_events",
    "get_resource_yaml", "get_pod_logs",
    "list_ingresses", "list_pvcs", "list_deployments", "get_deployment_status",
    # Proxmox read-only
    "get_nodes", "get_node_status", "list_all_vms", "list_vms",
    "get_vm_status", "get_vm_config", "get_recent_tasks",
    # PiHole read-only
    "get_pihole_summary", "get_query_log", "get_top_domains", "get_top_clients",
    "get_blocklists", "get_pihole_system", "get_custom_dns_records",
    "get_cname_records", "get_dhcp_leases", "get_system_messages",
    # FritzBox read-only
    "get_fritz_system_info", "get_fritz_devices", "get_fritz_wan_status",
    "get_fritz_bandwidth", "get_fritz_wlan_status", "get_fritz_smarthome_devices",
    "get_fritz_call_list",
    # Home Assistant read-only
    "ha_get_entity_state", "ha_list_entities", "ha_find_device", "ha_get_entity_details",
    # IONOS DNS read-only
    "get_ionos_zones", "get_ionos_records",
    # Email read-only
    "read_emails",
    # GLPI read-only
    "get_ticket", "search_tickets", "search_users", "list_groups",
    "list_categories", "get_ticket_stats",
    # WordPress read-only
    "get_site_info", "get_updates_info", "list_plugins", "search_plugins",
    "list_posts", "get_post", "list_pages", "get_page",
    "list_tags", "list_users", "get_current_user", "get_site_settings", "list_media",
    # Docker read-only
    "list_containers", "inspect_container", "get_container_logs",
    "get_container_stats", "list_images", "list_volumes",
    "get_docker_info", "get_docker_version", "get_docker_disk_usage",
    # Linux Server read-only
    "get_system_info", "get_disk_usage", "get_top_processes",
    "get_journal", "get_logfile", "read_file", "list_directory",
    "get_network_info", "check_port", "check_last_logins",
    # OPNsense read-only
    "get_opnsense_system_status", "get_opnsense_interfaces", "get_opnsense_gateways",
    "get_opnsense_firewall_rules", "get_opnsense_nat_rules", "get_opnsense_services",
    "get_opnsense_dhcp_leases", "get_opnsense_logs",
    # Tasmota read-only
    "get_tasmota_status", "get_tasmota_power", "get_tasmota_sensors", "get_tasmota_wifi_info",
    # Qdrant read-only
    "search_knowledge", "list_knowledge_collections", "get_collection_stats",
    # Codelab read-only
    "get_available_languages",
})


def _keyword_prefilter(text: str) -> SafeguardResult | None:
    """
    Fast-path classifier that skips the LLM call for short, unambiguous messages.

    Priority order:
      1. Safe pattern match  → SAFE (violation=0)
      2. Destructive keyword → DESTRUCTIVE (violation=1)
      3. State-changing keyword → STATE_CHANGING (violation=1)
      4. No match → None (fall through to LLM classifier)
    """
    lower = text.lower().strip()
    spaced = f" {lower} "   # wrap for word-boundary substring matching

    # 1. Clearly read-only — no confirmation needed
    for pat in _SAFE_PATTERNS:
        if lower.startswith(pat) or pat in spaced:
            return SafeguardResult(
                requires_confirmation=False,
                category=ActionCategory.SAFE,
                rationale="Read-only keyword detected — safe to execute directly.",
            )

    # 2. Destructive keywords
    for kw, need_wb in _DESTRUCTIVE_TERMS:
        if need_wb:
            hit = bool(re.search(rf"\b{re.escape(kw.strip())}\b", lower))
        else:
            hit = kw in lower
        if hit:
            return SafeguardResult(
                requires_confirmation=True,
                category=ActionCategory.DESTRUCTIVE,
                rationale=f"Destructive keyword '{kw.strip()}' detected — confirmation required.",
            )

    # 3. State-changing keywords
    for kw, need_wb in _STATE_TERMS:
        if need_wb:
            hit = bool(re.search(rf"\b{re.escape(kw.strip())}\b", lower))
        else:
            hit = kw in lower
        if hit:
            return SafeguardResult(
                requires_confirmation=True,
                category=ActionCategory.STATE_CHANGING,
                rationale=f"State-changing keyword '{kw.strip()}' detected — confirmation required.",
            )

    return None


# ─── Safeguard middleware ─────────────────────────────────────────────────────

class SafeguardMiddleware:
    """
    Model-agnostic safeguard with global and per-agent state.

    Evaluation order per message:
      1. If safeguard is disabled  → SAFE, no LLM call.
      2. Keyword pre-filter        → instant result (no LLM call).
      3. LLM classifier            → JSON response, robust parser.

    Per-agent config (Redis via AgentConfigStore) takes priority over
    the global toggle.
    """

    def __init__(
        self,
        client: AsyncOpenAI,
        model: str,
        policy: str | None = None,
        timeout: float = 8.0,
        enabled: bool = True,
        agent_store: "AgentConfigStore | None" = None,
    ) -> None:
        self.client      = client
        self.model       = model
        self.policy      = policy or SAFEGUARD_SYSTEM_PROMPT
        self.timeout     = timeout
        self.enabled     = enabled
        self.agent_store = agent_store

    # ── Global toggle ──────────────────────────────────────────────────────────

    def enable(self) -> None:
        self.enabled = True
        logger.info("[Safeguard] Globally enabled.")

    def disable(self) -> None:
        self.enabled = False
        logger.warning("[Safeguard] Globally DISABLED — autonomous mode active.")

    # ── Per-agent toggle ───────────────────────────────────────────────────────

    async def enable_for_agent(self, agent_id: str) -> None:
        if self.agent_store:
            await self.agent_store.set_safeguard(agent_id, enabled=True)
        logger.info("[Safeguard] Enabled for agent '%s'.", agent_id)

    async def disable_for_agent(self, agent_id: str) -> None:
        if self.agent_store:
            await self.agent_store.set_safeguard(agent_id, enabled=False)
        logger.warning("[Safeguard] DISABLED for agent '%s' — autonomous mode.", agent_id)

    async def _is_enabled_for(self, agent_id: str | None) -> bool:
        """Per-agent config takes priority over the global toggle."""
        if agent_id and self.agent_store:
            state = await self.agent_store.get_safeguard(agent_id)
            if state is not None:
                return state
        return self.enabled

    # ── Main entry point ───────────────────────────────────────────────────────

    async def check(self, user_input: str, agent_id: str | None = None) -> SafeguardResult:
        """
        Classify a user message.

        Stage 1 — disabled:  returns SAFE immediately.
        Stage 2 — prefilter: keyword match on messages < 200 chars.
        Stage 3 — LLM:       full classifier call.

        Always returns a SafeguardResult — never raises.
        """
        if not await self._is_enabled_for(agent_id):
            return SafeguardResult(
                requires_confirmation=False,
                category=ActionCategory.SAFE,
                rationale="Safeguard disabled — autonomous mode active.",
            )

        # Pre-filter: fast path for short, unambiguous messages
        if len(user_input) < 200:
            prefilter_result = _keyword_prefilter(user_input)
            if prefilter_result is not None:
                return prefilter_result

        # LLM classifier
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": self.policy},
                    {"role": "user",   "content": user_input},
                ],
                temperature=0.0,
                max_tokens=150,
                timeout=self.timeout,
            )
            raw = response.choices[0].message.content.strip()
            return self._parse(raw)

        except Exception as exc:
            logger.warning(
                "[Safeguard] Classifier call failed: %s — fail-safe: confirmation required.", exc,
            )
            return SafeguardResult(
                requires_confirmation=True,
                category=ActionCategory.UNKNOWN,
                rationale=f"Classifier unreachable ({type(exc).__name__}) — confirmation required as fallback.",
                raw_response=str(exc),
            )

    # ── Tool-call classifier ───────────────────────────────────────────────────

    async def check_tool_call(
        self,
        tool_name: str,
        tool_args: dict,
    ) -> SafeguardResult:
        """
        Klassifiziert einen einzelnen Tool-Aufruf, bevor er ausgeführt wird.

        Fast-path: bekannte read-only Tools → SAFE sofort, kein LLM-Call.
        Routing-Tools (call_module_agent, execute_cli_command): relevantes Argument
        wird extrahiert und durch check() geleitet.
        Alle anderen Tools: tool_name + Argument-Vorschau → check().

        Beachte: Safeguard-Deaktivierung (global/per-agent) wird durch check() gehandhabt.
        """
        # Known safe tools — no LLM call needed
        if tool_name in _TOOL_READONLY:
            return SafeguardResult(
                requires_confirmation=False,
                category=ActionCategory.SAFE,
                rationale=f"Read-only / benign tool '{tool_name}' — safe to execute.",
            )

        # For call_module_agent: the "message" arg describes the action
        if tool_name == "call_module_agent":
            text = tool_args.get("message", tool_name)
            return await self.check(text)

        # For execute_cli_command: the command itself
        if tool_name == "execute_cli_command":
            text = tool_args.get("command", tool_name)
            return await self.check(text)

        # Generic fallback: tool_name + short args preview
        args_preview = str(tool_args)[:300] if tool_args else ""
        text = f"{tool_name}: {args_preview}" if args_preview else tool_name
        return await self.check(text)

    # ── Response parser ────────────────────────────────────────────────────────

    def _parse(self, raw: str) -> SafeguardResult:
        """
        Parse the LLM classifier response robustly.

        Handles:
        - <think>...</think> blocks from reasoning models (Qwen3.5, DeepSeek-R1)
        - Markdown code fences (```json ... ```)
        - JSON embedded inside prose (regex extraction fallback)
        - Missing, null, or unexpected field values
        - Enforces category/violation consistency (DESTRUCTIVE/STATE → violation=1,
          SAFE → violation=0) regardless of what the model outputs
        """
        # Strip thinking blocks
        cleaned = _RE_THINK.sub("", raw).strip()
        # Strip markdown fences
        cleaned = _RE_MD_FENCE.sub("", cleaned).strip()
        # If JSON is not at the start, extract first {...} block
        if not cleaned.startswith("{"):
            m = _RE_JSON_OBJ.search(cleaned)
            cleaned = m.group(0) if m else cleaned

        try:
            data         = json.loads(cleaned)
            violation    = int(data.get("violation", 1))
            category_raw = str(data.get("category", "UNKNOWN")).upper()
            rationale    = str(data.get("rationale", "No rationale provided."))

            try:
                category = ActionCategory(category_raw)
            except ValueError:
                category = ActionCategory.UNKNOWN

            # Enforce consistency regardless of what the model output
            if category in (ActionCategory.DESTRUCTIVE, ActionCategory.STATE_CHANGING):
                violation = 1
            elif category == ActionCategory.SAFE:
                violation = 0

            return SafeguardResult(
                requires_confirmation=bool(violation),
                category=category,
                rationale=rationale,
                raw_response=raw,
            )

        except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
            logger.warning("[Safeguard] Parse error: %s | raw='%.200s'", exc, raw)
            return SafeguardResult(
                requires_confirmation=True,
                category=ActionCategory.UNKNOWN,
                rationale="Parse error — confirmation required as fallback.",
                raw_response=raw,
            )


# ─── Bot confirmation helper ──────────────────────────────────────────────────

# Redis key for pending bot messages (Telegram / Teams), TTL 300s
SAFEGUARD_PENDING_KEY = "ninko:safeguard_pending:{session_id}"

# Words accepted as confirmation in bot channels (single-word or short replies only)
_CONFIRMATION_WORDS: frozenset[str] = frozenset({
    # German
    "ja", "jo", "jep", "jup", "jawohl", "klar", "natürlich",
    "bestätige", "bestätigen", "bestätigt",
    "weiter", "ausführen", "durchführen",
    "ok", "okay",
    # English
    "yes", "yep", "yup", "y", "sure", "absolutely",
    "confirm", "confirmed", "proceed", "continue", "run", "go",
})


def is_bot_confirmation(text: str) -> bool:
    """
    Returns True if the text is a confirmation response for a pending
    safeguard action in a bot channel (Telegram, Teams).

    Only matches short replies (≤ 3 words) to avoid false positives from
    regular messages that happen to contain a confirmation word mid-sentence.
    """
    normalized = text.strip().lower().rstrip("!. ")
    if len(normalized.split()) > 3:
        return False
    return normalized in _CONFIRMATION_WORDS
