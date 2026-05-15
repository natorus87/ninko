"""Post-processing middleware: response extraction and memory storage."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from langchain_core.messages import AIMessage, ToolMessage

from .base import BaseMiddleware, MiddlewareContext, MiddlewareResult

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

_MEMORIZE_COOLDOWN_SECS = 120
_MEMORIZE_MIN_LENGTH = 80


class ResponseExtractionMiddleware(BaseMiddleware):
    name = "response_extraction"
    priority = 500

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
        if not ctx.result:
            return

        all_msgs = ctx.result.get("messages", [])
        ai_msgs = [m for m in all_msgs if isinstance(m, AIMessage) and m.content]
        tool_msgs = [m for m in all_msgs if isinstance(m, ToolMessage) and m.content]

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
            if response:
                if (
                    ctx.agent_name == "kubernetes"
                    and tool_msgs
                    and not _contains_markdown_table(response)
                ):
                    tool_text = _extract_text(tool_msgs[-1].content)
                    tool_name = str(getattr(tool_msgs[-1], "name", "") or "")
                    details = _format_kubernetes_tool_fallback(tool_text, tool_name=tool_name)
                    if details:
                        ctx.response = f"{response.rstrip()}\n\n{details}"
                        logger.debug(
                            "Agent '%s': Kubernetes-Tooldetails als Markdown ergänzt.",
                            ctx.agent_name,
                        )
                        return
                ctx.response = response
                logger.debug("Agent '%s' Antwort: %s…", ctx.agent_name, response[:100])
                return

        if tool_msgs:
            raw_tool = _extract_text(tool_msgs[-1].content)
            tool_name = str(getattr(tool_msgs[-1], "name", "") or "")
            if ctx.agent_name == "kubernetes":
                ctx.response = (
                    _format_kubernetes_tool_fallback(raw_tool, tool_name=tool_name)
                    or _format_tool_fallback(raw_tool)
                )
            else:
                ctx.response = _format_tool_fallback(raw_tool)
            logger.debug(
                "Agent '%s': kein AI-Text, nutze letztes Tool-Ergebnis als Antwort.",
                ctx.agent_name,
            )
        else:
            ctx.response = "Keine Antwort generiert."


class MemoryStorageMiddleware(BaseMiddleware):
    name = "memory_storage"
    priority = 510

    def __init__(
        self,
        auto_memorize_fn: Any = None,
        excluded_agents: set[str] | None = None,
        cooldowns: dict[tuple[str, str], float] | None = None,
        background_tasks: set[asyncio.Task] | None = None,
    ):
        self._auto_memorize = auto_memorize_fn
        self._excluded = excluded_agents if excluded_agents is not None else set()
        self._cooldowns = cooldowns if cooldowns is not None else {}
        self._bg_tasks = (
            background_tasks if background_tasks is not None else set()
        )

    async def pre_process(self, ctx: MiddlewareContext) -> MiddlewareResult:
        return MiddlewareResult()

    async def post_process(self, ctx: MiddlewareContext) -> None:
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
        task = asyncio.create_task(self._auto_memorize(ctx.message, ctx.response))
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


def _looks_like_python_struct(text: str) -> bool:
    s = text.lstrip()
    return s.startswith(("[{", "[(", "{'", "{\"", "[{'", "[{\"")) or (
        s.startswith("[") and "'" in s[:50]
    )


def _format_tool_fallback(raw: str) -> str:
    """Wandelt rohen Tool-Output (oft Python-Repr) in lesbares Markdown.

    LangGraph serialisiert list/dict-Returns via str() — das ergibt Python-Repr
    mit single-quotes, was im Chat haesslich ist. Wir versuchen das als Python-
    Literal zu parsen und als JSON in einen Code-Block zu rendern. Bei Fehlern
    geben wir den Rohtext in einem generischen Code-Block zurueck.
    """
    raw = raw.strip()
    if not raw:
        return "Keine Antwort generiert."

    if _looks_like_python_struct(raw):
        try:
            data = ast.literal_eval(raw)
            pretty = json.dumps(data, indent=2, ensure_ascii=False, default=str)
            return f"```json\n{pretty}\n```"
        except (ValueError, SyntaxError, MemoryError, RecursionError):
            pass

    # Schon Markdown / Text? Heuristik: enthaelt newline oder typisches MD-Zeichen
    if any(token in raw for token in ("\n", "**", "##", "- ", "| ", "```")):
        return raw

    return f"```\n{raw}\n```"


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


def _format_kubernetes_tool_fallback(raw: str, tool_name: str = "") -> str:
    data = _parse_structured_tool_output(raw)
    if data is None:
        return ""

    if isinstance(data, dict):
        return _format_kubernetes_dict(data, tool_name=tool_name)

    if isinstance(data, list):
        return _format_kubernetes_list(data, tool_name=tool_name)

    return ""


def _format_kubernetes_dict(data: dict, tool_name: str = "") -> str:
    if tool_name == "get_cluster_status" or {"nodes", "namespaces", "total_pods"}.issubset(data):
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

    rows = [(str(key), _format_cell(value)) for key, value in data.items()]
    return _markdown_table(["Feld", "Wert"], rows)


def _format_kubernetes_list(data: list, tool_name: str = "") -> str:
    if not data:
        return "Keine Ressourcen gefunden."

    if not all(isinstance(item, dict) for item in data):
        return ""

    columns_by_tool = {
        "list_nodes": ["name", "status", "roles", "version", "internal_ip", "os_image", "age"],
        "get_all_pods": ["namespace", "name", "ready", "status", "restarts", "age", "node"],
        "get_failing_pods": ["namespace", "name", "ready", "status", "restarts", "issues", "age"],
        "list_namespaces": ["name", "status", "labels"],
        "list_deployments": ["namespace", "name", "ready", "up_to_date", "available", "age"],
        "list_services": ["namespace", "name", "type", "cluster_ip", "external_ip", "ports", "age"],
        "list_ingresses": ["namespace", "name", "hosts", "address", "ports", "age"],
        "list_pvcs": ["namespace", "name", "status", "volume", "capacity", "storage_class", "age"],
        "list_hpas": ["namespace", "name", "reference", "targets", "min_pods", "max_pods", "replicas"],
    }
    columns = [col for col in columns_by_tool.get(tool_name, []) if any(col in item for item in data)]
    if not columns:
        columns = _derive_columns(data)

    rows = [[_format_cell(item.get(col, "")) for col in columns] for item in data]
    headers = [_humanize_header(col) for col in columns]
    return _markdown_table(headers, rows)


def _derive_columns(items: list[dict]) -> list[str]:
    preferred = [
        "namespace",
        "name",
        "status",
        "ready",
        "restarts",
        "age",
        "node",
        "version",
        "internal_ip",
        "type",
    ]
    present = []
    for col in preferred:
        if any(col in item for item in items):
            present.append(col)

    if present:
        return present[:8]

    keys: list[str] = []
    for item in items:
        for key in item:
            if key not in keys:
                keys.append(key)
            if len(keys) >= 8:
                return keys
    return keys


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
