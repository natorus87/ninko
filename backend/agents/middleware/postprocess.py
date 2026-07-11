"""Post-processing middleware: response extraction and memory storage."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ToolMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MEMORIZE_COOLDOWN_SECS = 120
_MEMORIZE_MIN_LENGTH = 80

# Modules whose AI answers are augmented with a structured Markdown table when
# the model returns a short reply but tools delivered structured data. Keep in
# sync with PLAN.md Phase 3/4 (migrated high-risk modules).
_TABLE_AUGMENT_MODULES: frozenset[str] = frozenset(
    {
        "kubernetes",
        "proxmox",
        "docker",
        "linux_server",
        "checkmk",
        "opnsense",
        "zabbix",
    }
)


class ResponseExtractionMiddleware(BaseMiddleware):
    """Extract the final user-facing response from agent execution results."""

    name = "response_extraction"
    priority = 500

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """No-op pre-processing hook."""
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        """Populate ``ctx.response`` from AI messages or tool fallbacks."""
        if not ctx.result:
            return

        all_msgs = ctx.result.get("messages", [])
        ai_msgs = [m for m in all_msgs if isinstance(m, AIMessage) and m.content]
        tool_msgs = [m for m in all_msgs if isinstance(m, ToolMessage) and m.content]
        wants_json = _wants_json_response(ctx.message)

        # Prefer tool outputs that contain images (data URLs or markers)
        if tool_msgs:
            for msg in reversed(tool_msgs):
                tool_text = _extract_text(msg.content)
                if "data:image/" in tool_text:
                    ctx.response = tool_text
                    logger.debug(
                        "Agent '%s': using tool image output as response.",
                        ctx.agent_name,
                    )
                    return
                if "[NINKO_IMAGE:" in tool_text or "/api/images/" in tool_text:
                    ctx.response = tool_text
                    logger.debug(
                        "Agent '%s': using tool image marker as response.",
                        ctx.agent_name,
                    )
                    return

        if ai_msgs:
            raw = _extract_text(ai_msgs[-1].content)
            response = _strip_thinking(raw)
            response = _strip_tool_plan_narration(response)
            if response:
                if ctx.agent_name == "web_search" and tool_msgs:
                    web_details = _format_web_search_tool_fallback(
                        _extract_text(tool_msgs[-1].content)
                    )
                    if web_details and _is_unhelpful_web_search_response(response):
                        ctx.response = web_details
                        logger.debug(
                            "Agent '%s': replacing unhelpful AI text with web search "
                            "results.",
                            ctx.agent_name,
                        )
                        return
                if (
                    ctx.agent_name in _TABLE_AUGMENT_MODULES
                    and tool_msgs
                    and not _contains_markdown_table(response)
                    and not wants_json
                ):
                    details = _first_table_details(tool_msgs, agent_name=ctx.agent_name)
                    if details:
                        ctx.response = f"{response.rstrip()}\n\n{details}"
                        logger.debug(
                            "Agent '%s': Tool-Details als Markdown-Tabelle ergänzt.",
                            ctx.agent_name,
                        )
                        return
                ctx.response = response
                logger.debug("Agent '%s' Antwort: %s…", ctx.agent_name, response[:100])
                return

        if tool_msgs:
            raw_tool = _extract_text(tool_msgs[-1].content)
            tool_name = str(getattr(tool_msgs[-1], "name", "") or "")
            if ctx.agent_name == "web_search":
                ctx.response = _format_web_search_tool_fallback(raw_tool) or raw_tool
            elif ctx.agent_name == "kubernetes" and not wants_json:
                ctx.response = (
                    _format_kubernetes_tool_fallback(raw_tool, tool_name=tool_name)
                    or _format_tool_fallback(
                        raw_tool, tool_name=tool_name, agent_name=ctx.agent_name
                    )
                )
            else:
                ctx.response = _format_tool_fallback(
                    raw_tool,
                    tool_name=tool_name,
                    agent_name=ctx.agent_name,
                    prefer_json=wants_json,
                )
            logger.debug(
                "Agent '%s': kein AI-Text, nutze letztes Tool-Ergebnis als Antwort.",
                ctx.agent_name,
            )
        else:
            ctx.response = "Keine Antwort generiert."


class MemoryStorageMiddleware(BaseMiddleware):
    """Persist sufficiently useful responses into long-term memory."""

    name = "memory_storage"
    priority = 510

    def __init__(
        self,
        auto_memorize_fn: Any = None,
        excluded_agents: set[str] | None = None,
        cooldowns: dict[tuple[str, str], float] | None = None,
        background_tasks: set[asyncio.Task] | None = None,
    ):
        """Initialize memory storage dependencies and runtime state."""
        self._auto_memorize = auto_memorize_fn
        self._excluded = excluded_agents if excluded_agents is not None else set()
        self._cooldowns = cooldowns if cooldowns is not None else {}
        self._bg_tasks = (
            background_tasks if background_tasks is not None else set()
        )

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """No-op pre-processing hook."""
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        """Schedule memory extraction for long enough final responses."""
        if (
            not ctx.response
            or len(ctx.response) < _MEMORIZE_MIN_LENGTH
            or ctx.agent_name in self._excluded
            or not self._auto_memorize
        ):
            return

        now = asyncio.get_running_loop().time()
        key = (ctx.agent_name, ctx.session_id or "__no_session__")
        last = self._cooldowns.get(key, 0.0)

        if (now - last) < _MEMORIZE_COOLDOWN_SECS:
            return

        if len(self._cooldowns) > 5000:
            oldest = sorted(self._cooldowns, key=lambda k: self._cooldowns[k])
            for k in oldest[:500]:
                self._cooldowns.pop(k, None)

        self._cooldowns[key] = now

        async def _run_with_log() -> None:
            """Führt _auto_memorize aus und loggt Exceptions explizit,
            damit 'Task exception was never retrieved' nicht mehr auftritt."""
            try:
                await self._auto_memorize(ctx.message, ctx.response)
            except asyncio.CancelledError:
                # Cancel ist kein Crash — normaler Shutdown
                raise
            except Exception as exc:
                # Alle anderen Exceptions (z.B. APIConnectionError) werden
                # geloggt statt unbehandelt gelassen.
                logger.warning(
                    "[Memory] Auto-Memorize Background-Task crashed: %s: %s",
                    type(exc).__name__,
                    exc,
                )

        task = asyncio.create_task(_run_with_log())
        self._bg_tasks.add(task)
        task.add_done_callback(self._bg_tasks.discard)


def _extract_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)


def _strip_thinking(text: str) -> str:
    import re

    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    return cleaned


_NARRATION_VERB_RE = re.compile(
    r"\b(?:i will|i['’]ll|i am going to|let me|first,? i will|"
    r"ich werde|ich rufe|ich prüfe zunächst)\b",
    re.IGNORECASE,
)
_TOOL_MENTION_RE = re.compile(
    # Englisch: Verb vor dem Tool-Namen ("call get_cluster_status").
    r"\b(?:call|invoke|use|using|checking)\b(?:(?!\.).){0,40}?\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b"
    # Deutsch: Verb steht bei "werde X aufrufen" satzfinal nach dem Tool-Namen.
    r"|\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b(?:(?!\.).){0,40}?\b(?:aufrufen|aufgerufen|nutzen|nutzt)\b"
    r"|\btool[s]?\b",
    re.IGNORECASE,
)
# Marker darf am Zeilenanfang stehen ODER direkt (auch ohne Leerzeichen) auf
# Satzende-Interpunktion folgen — deckt den beobachteten "…overview.✅ Status…"-Fall
# ab, bei dem das Modell keine Trennung zwischen Narration und Antwort einfügt.
_CONTENT_START_RE = re.compile(r"(?:^|\n\s*|(?<=[.!?]))(?:#{1,6}\s|[✅⚠️❌]|\|.+\|)")


def _strip_tool_plan_narration(response: str) -> str:
    """Strips a leading "I will call X to check Y…" plan narration, if present.

    Some completions leak the model's tool-calling plan as prose into the
    final (no-more-tool_calls) message instead of only the user-facing
    answer — the leaked prose sometimes runs directly into the real content
    with no separating whitespace (e.g. "…overview.✅ Status …"). Only
    strips when the response *starts* with narration language AND the
    prefix mentions tools repeatedly, to avoid touching legitimate replies
    that happen to open with an unrelated "I will …" sentence.
    """
    if not response:
        return response
    head = response[:400]
    if not (_NARRATION_VERB_RE.search(head) and _TOOL_MENTION_RE.search(head)):
        return response
    match = _CONTENT_START_RE.search(response)
    if not match or match.start() == 0:
        return response
    prefix, remainder = response[: match.start()], response[match.start() :].lstrip()
    if len(remainder) < 20:
        return response
    if len(_TOOL_MENTION_RE.findall(prefix)) < 2:
        return response
    logger.debug("Stripped tool-plan narration prefix (%d chars).", len(prefix))
    return remainder


def _is_unhelpful_web_search_response(response: str) -> bool:
    text = response.casefold().strip()
    patterns = (
        "ich suche",
        "ich werde jetzt",
        "ich recherchiere",
        "i will search",
        "i'll search",
        "i am searching",
        "let me search",
    )
    return any(pattern in text for pattern in patterns)


def _looks_like_python_struct(text: str) -> bool:
    s = text.lstrip()
    if s in ("[]", "{}"):
        return True
    return s.startswith(("[{", "[(", "{'", "{\"", "[{'", "[{\"")) or (
        s.startswith("[") and "'" in s[:50]
    )


def _format_tool_fallback(
    raw: str,
    tool_name: str = "",
    agent_name: str = "",
    prefer_json: bool = False,
) -> str:
    """Wandelt rohen Tool-Output (oft Python-Repr) in lesbares Markdown.

    Strategie:
    1. Strukturiertes ``list[dict]`` / ``dict`` → Markdown-Tabelle (PLAN Phase 5).
    2. Schon Markdown im Rohtext → unveraendert durchreichen.
    3. Parseable Struktur ohne Tabellen-Form → JSON-Code-Block als letzter Ausweg.
    4. Plain Text → generischer Code-Block.
    """
    raw = raw.strip()
    if not raw:
        return "Keine Antwort generiert."

    data = _parse_structured_tool_output(raw) if _looks_like_python_struct(raw) else None
    if data is not None:
        if prefer_json:
            return _format_json_block(data)
        table = _format_structured_as_table(
            data,
            tool_name=tool_name,
            agent_name=agent_name,
        )
        if table:
            return table
        try:
            return _format_json_block(data)
        except (TypeError, ValueError):
            pass

    if any(token in raw for token in ("\n", "**", "##", "- ", "| ", "```")):
        return raw

    return f"```\n{raw}\n```"


def _wants_json_response(message: str) -> bool:
    """Detect explicit user requests for JSON output."""
    text = message.casefold()
    if "json" not in text:
        return False
    indicators = (
        "json",
        "als json",
        "in json",
        "im json",
        "json format",
        "json-format",
        "json output",
        "raw json",
        "return json",
        "give me json",
        "gib mir json",
        "zeige json",
        "liefere json",
    )
    return any(indicator in text for indicator in indicators)


def _format_json_block(data: Any) -> str:
    """Render parsed structured data as a JSON code block."""
    pretty = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    return f"```json\n{pretty}\n```"


def _format_web_search_tool_fallback(raw: str) -> str:
    """Render web search tool output as concise Markdown with source URLs."""
    data = _parse_structured_tool_output(raw)
    if not isinstance(data, list):
        return ""

    entries = [item for item in data if isinstance(item, dict)]
    if not entries:
        return ""

    lines: list[str] = []
    for item in entries[:5]:
        title = str(item.get("title") or "Quelle").strip()
        url = str(item.get("url") or "").strip()
        content = str(item.get("content") or "").strip()

        if title.casefold() == "error":
            return content or "Websuche fehlgeschlagen."
        if title.casefold() == "web search" and not url:
            return content or "Keine Ergebnisse gefunden."

        headline = f"- **{title}**"
        if url:
            headline += f" — {url}"
        lines.append(headline)
        if content:
            lines.append(f"  {content}")

    return "\n".join(lines).strip()


def _contains_markdown_table(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines()]
    for idx, line in enumerate(lines[:-1]):
        if "|" not in line:
            continue
        separator = lines[idx + 1]
        if "|" in separator and set(separator.replace("|", "").strip()) <= {"-", ":", " "}:
            return True
    return False


def _parse_structured_tool_output(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        return None

    if raw.startswith("```"):
        lines = raw.splitlines()
        if len(lines) >= 2:
            body_lines = lines[1:-1] if lines[-1].strip().startswith("```") else lines[1:]
            raw = "\n".join(body_lines).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError, MemoryError, RecursionError):
        return None


# Modul-qualifizierte Spalten-Hints. Tool-Namen sind moduluebergreifend nicht
# eindeutig (z.B. ``list_services`` existiert in Kubernetes UND Linux Server) —
# deshalb wird zusaetzlich nach Agent-Name geschluesselt.
_PREFERRED_COLUMNS_BY_AGENT_TOOL: dict[str, dict[str, list[str]]] = {
    "kubernetes": {
        "list_nodes": ["name", "status", "roles", "version", "internal_ip", "os_image", "age"],
        "get_all_pods": ["namespace", "name", "ready", "status", "restarts", "age", "node"],
        "get_failing_pods": ["namespace", "name", "ready", "status", "restarts", "issues", "age"],
        "list_namespaces": ["name", "status", "labels"],
        "list_deployments": ["namespace", "name", "ready", "up_to_date", "available", "age"],
        "list_services": ["namespace", "name", "type", "cluster_ip", "external_ip", "ports", "age"],
        "list_ingresses": ["namespace", "name", "hosts", "address", "ports", "age"],
        "list_pvcs": ["namespace", "name", "status", "volume", "capacity", "storage_class", "age"],
        "list_hpas": [
            "namespace",
            "name",
            "reference",
            "targets",
            "min_pods",
            "max_pods",
            "replicas",
        ],
    },
    "docker": {
        "list_containers": ["name", "image", "status", "ports", "created"],
        "list_images": ["repository", "tag", "image_id", "created", "size"],
        "list_volumes": ["name", "driver", "mountpoint", "size"],
    },
    "proxmox": {
        "list_all_vms": ["vmid", "name", "status", "node", "cpu", "mem", "uptime"],
        "list_vms": ["vmid", "name", "status", "node", "cpu", "mem", "uptime"],
        "list_containers_lxc": ["vmid", "name", "status", "node", "cpu", "mem"],
        "get_nodes": ["node", "status", "cpu", "mem", "uptime"],
    },
    "linux_server": {
        "get_top_processes": ["pid", "user", "cpu", "memory", "command"],
        "list_services": ["name", "load", "active", "sub", "description"],
        "get_disk_usage": ["filesystem", "size", "used", "available", "use_percent", "mountpoint"],
    },
    "opnsense": {
        "get_opnsense_interfaces": ["name", "device", "status", "ipv4", "ipv6"],
        "get_opnsense_firewall_rules": [
            "sequence", "interface", "action", "source", "destination", "description",
        ],
        "get_opnsense_dhcp_leases": ["address", "hwaddr", "hostname", "starts", "ends"],
    },
    "checkmk": {
        "checkmk_get_hosts": ["host_name", "state", "num_services", "address"],
        "checkmk_get_services": ["host_name", "service_description", "state", "plugin_output"],
        "checkmk_get_alerts": ["host", "service", "state", "summary", "time"],
    },
}


def _preferred_columns_for(agent_name: str, tool_name: str) -> list[str]:
    """Lookup module-qualified column hints; empty list when none configured."""
    if not tool_name:
        return []
    agent_map = _PREFERRED_COLUMNS_BY_AGENT_TOOL.get(agent_name, {})
    return agent_map.get(tool_name, [])


def _build_table_details(raw: str, tool_name: str, agent_name: str) -> str:
    """Render tool output as a Markdown table for AI-augmentation flows.

    Kubernetes keeps its bespoke summary card via ``_format_kubernetes_tool_fallback``;
    all other migrated high-risk modules use the generic structured renderer.
    Returns an empty string when nothing tabular can be produced.
    """
    if agent_name == "kubernetes":
        return _format_kubernetes_tool_fallback(raw, tool_name=tool_name)
    data = _parse_structured_tool_output(raw)
    if data is None:
        return ""
    return _format_structured_as_table(data, tool_name=tool_name, agent_name=agent_name)


def _first_table_details(tool_msgs: list[ToolMessage], agent_name: str) -> str:
    """Return the latest tabular tool details, skipping non-tabular outputs."""
    for msg in reversed(tool_msgs):
        tool_text = _extract_text(msg.content)
        tool_name = str(getattr(msg, "name", "") or "")
        details = _build_table_details(
            tool_text,
            tool_name=tool_name,
            agent_name=agent_name,
        )
        if details and "|" in details:
            return details
    return ""


def _format_kubernetes_tool_fallback(raw: str, tool_name: str = "") -> str:
    """Kubernetes-specific fallback.

    Falls back to the generic table for the common cases; only the
    ``get_cluster_status`` summary card stays bespoke.
    """
    data = _parse_structured_tool_output(raw)
    if data is None:
        return ""

    if isinstance(data, dict) and (
        tool_name == "get_cluster_status"
        or {"nodes", "namespaces", "total_pods"}.issubset(data)
    ):
        failing = int(data.get("failing_pods") or 0)
        status = "✅ Gesund" if failing == 0 else "⚠️ Prüfen"
        rows = [
            ("Status", status),
            ("Nodes", data.get("nodes", "n/a")),
            ("Namespaces", data.get("namespaces", "n/a")),
            ("Pods gesamt", data.get("total_pods", "n/a")),
            ("Pods running", data.get("running_pods", "n/a")),
            ("Pods fehlerhaft", data.get("failing_pods", "n/a")),
            ("Deployments", data.get("deployments", "n/a")),
        ]
        return _markdown_table(["Metrik", "Wert"], rows)

    return _format_structured_as_table(data, tool_name=tool_name, agent_name="kubernetes")


def _format_structured_as_table(data: Any, tool_name: str = "", agent_name: str = "") -> str:
    """Render a parsed list/dict tool output as a Markdown table.

    Returns an empty string when the structure cannot be rendered (e.g.
    primitive scalar, mixed-shape lists). Callers then fall back to a JSON
    code block.
    """
    if isinstance(data, dict):
        if not data:
            return ""
        rows = [(str(key), _format_cell(value)) for key, value in data.items()]
        return _markdown_table(["Feld", "Wert"], rows)

    if isinstance(data, list):
        if not data:
            return "Keine Einträge gefunden."
        if not all(isinstance(item, dict) for item in data):
            return ""
        preferred = _preferred_columns_for(agent_name, tool_name)
        columns = [col for col in preferred if any(col in item for item in data)]
        if not columns:
            columns = _derive_columns(data)
        if not columns:
            return ""
        rows = [[_format_cell(item.get(col, "")) for col in columns] for item in data]
        headers = [_humanize_header(col) for col in columns]
        return _markdown_table(headers, rows)

    return ""


def _derive_columns(items: list[dict]) -> list[str]:
    """Derive column order from list-of-dict items.

    Order: well-known columns first (in a sensible reading order), then any
    remaining keys in insertion order. Returns up to 8 columns. The preferred
    list is only a *hint* for ordering — every column actually present is
    surfaced.
    """
    preferred = [
        "namespace",
        "name",
        "status",
        "ready",
        "state",
        "type",
        "version",
        "address",
        "internal_ip",
        "ports",
        "restarts",
        "age",
        "node",
    ]
    seen: list[str] = []
    for col in preferred:
        if col not in seen and any(col in item for item in items):
            seen.append(col)
    for item in items:
        for key in item:
            if key not in seen:
                seen.append(key)
            if len(seen) >= 8:
                return seen[:8]
    return seen[:8]


def _humanize_header(key: str) -> str:
    labels = {
        "internal_ip": "Internal IP",
        "os_image": "OS",
        "up_to_date": "Up-to-date",
        "cluster_ip": "Cluster IP",
        "external_ip": "External IP",
        "storage_class": "StorageClass",
        "min_pods": "Min",
        "max_pods": "Max",
    }
    return labels.get(key, key.replace("_", " ").title())


def _format_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(_format_cell(item) for item in value)
    if isinstance(value, dict):
        if not value:
            return ""
        return ", ".join(f"{key}={_format_cell(val)}" for key, val in value.items())
    text = str(value)
    return text.replace("\n", " ").replace("|", "\\|")


def _markdown_table(headers: list[str], rows: list[Any]) -> str:
    normalized_rows = [row if isinstance(row, (list, tuple)) else [row] for row in rows]
    header_line = "| " + " | ".join(_format_cell(header) for header in headers) + " |"
    separator = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(_format_cell(cell) for cell in row) + " |"
        for row in normalized_rows
    ]
    return "\n".join([header_line, separator, *body])
