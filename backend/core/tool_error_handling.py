"""
Tool Error Handling Middleware – GraphBubbleUp Preservation.

Konvertiert Tool-Exceptions zu strukturierten Error-ToolMessages,
damit der LangGraph sie graceful behandelt statt abzustürzen.

Pattern (DeerFlow-inspired):
    error_msg = await tool_error_to_message(tool_name, tool_args, exception)
    return ErrorToolMessage(content=error_msg)

Enthält außerdem Outbound Secret Sanitization:
    sanitize_tool_output(text) — bereinigt Tool-Outputs vor Weitergabe ans LLM
    wrap_tools_with_sanitizer(tools) — patcht _run/_arun aller Tools (idempotent)
"""

from __future__ import annotations

import asyncio
import logging
import re
import unicodedata
import inspect
from typing import Any

logger = logging.getLogger("ninko.tool_error_middleware")

# ---------------------------------------------------------------------------
# Outbound Secret Sanitization
# ---------------------------------------------------------------------------

# Regex-Patterns für häufige Secret-Formate.
# WICHTIG: Alle Quantifizierer haben Obergrenzen (ReDoS-Schutz).
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    # Generic high-entropy API keys / tokens (key= / token= / secret= etc.)
    re.compile(
        r"(?i)(?:api[_\-]?key|apikey|access[_\-]?token|auth[_\-]?token|bearer"
        r"|secret[_\-]?key|private[_\-]?key)"
        r"[\s:='\"]+"
        r"([A-Za-z0-9+/\-_.~]{32,512})",
        re.MULTILINE,
    ),
    # Password fields — Mindestlänge 8, Obergrenze 512
    re.compile(
        r"(?i)(?:password|passwd|pwd|pass)[\s:='\"]+"
        r"([^\s'\"]{8,512})",
        re.MULTILINE,
    ),
    # AWS Access Key ID: AKIA…
    re.compile(r"(?i)\b(AKIA[A-Z0-9]{16})\b"),
    # AWS Secret Access Key
    re.compile(
        r"(?i)aws[_\-]?secret[_\-]?access[_\-]?key[\s:='\"]+"
        r"([A-Za-z0-9/+]{40})",
        re.MULTILINE,
    ),
    # GitHub tokens
    re.compile(r"(?i)\b(ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{82})\b"),
    # OpenAI / Anthropic keys
    re.compile(r"(?i)\b(sk-[A-Za-z0-9\-_]{20,512})\b"),
    re.compile(r"(?i)\b(sk-ant-[A-Za-z0-9\-_]{20,512})\b"),
    # Generic Bearer tokens in Authorization headers
    re.compile(
        r"(?i)Authorization:\s*Bearer\s+([A-Za-z0-9\-_.~+/]{20,512})",
        re.MULTILINE,
    ),
    # Connection strings with credentials
    re.compile(
        r"(?i)(?:mongodb|postgres|postgresql|mysql|redis|amqp)(?:\+\w{1,32})?://"
        r"([^:@\s]{1,256}:[^@\s]{1,256})@",
        re.MULTILINE,
    ),
    # GCP API Keys (AIza...)
    re.compile(r"(?i)\b(AIza[A-Za-z0-9\-_]{35,64})\b"),
    # JWT tokens (eyJ...)
    re.compile(
        r"\b(eyJ[A-Za-z0-9_\-]{10,512}\.[A-Za-z0-9_\-]{10,512}\.[A-Za-z0-9_\-]{10,512})\b"
    ),
    # PEM private keys
    re.compile(
        r"(-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----.*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----)",
        re.DOTALL,
    ),
    # Stripe live keys
    re.compile(r"(?i)\b(sk_live_[A-Za-z0-9]{20,512}|rk_live_[A-Za-z0-9]{20,512})\b"),
    # SendGrid API keys
    re.compile(r"(?i)\b(SG\.[A-Za-z0-9\-_]{20,512}\.[A-Za-z0-9\-_]{20,512})\b"),
    # HashiCorp Vault tokens
    re.compile(r"(?i)\b(hvs\.[A-Za-z0-9_\-]{20,512})\b"),
]

# Exfiltrations-Vektoren via externe URLs
_EXFIL_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # Markdown-Bild: ![alt](https://...)
    (
        re.compile(r"!\[[^\]]{0,256}\]\((https?://[^)]{1,2048})\)", re.MULTILINE),
        "Markdown-Bild",
    ),
    # Markdown-Link: [text](https://...)  — externe Links in Tool-Outputs blockieren
    (
        re.compile(r"\[[^\]]{0,256}\]\((https?://[^)]{1,2048})\)", re.MULTILINE),
        "Markdown-Link",
    ),
    # HTML img-Tag
    (
        re.compile(
            r"<img[^>]{0,1024}src=[\"'](https?://[^\"']{1,2048})[\"'][^>]{0,256}>",
            re.MULTILINE | re.IGNORECASE,
        ),
        "HTML-img",
    ),
    # CSS url()
    (
        re.compile(r"url\([\"']?(https?://[^\"')]{1,2048})[\"']?\)", re.MULTILINE | re.IGNORECASE),
        "CSS-url",
    ),
]


def _make_block_fn(label: str):
    """Factory: returns a re.sub replacement function that blocks exfiltration URLs."""
    def _block(m: re.Match[str]) -> str:
        url = m.group(1)
        logger.warning(
            "Outbound-Sanitizer: %s-Exfiltration blockiert: %s…",
            label,
            url[:80],
        )
        return f"[{label} blockiert]"
    return _block


# Pre-built handler list — avoids re-allocating closures on every sanitize_tool_output() call.
_EXFIL_HANDLERS: list[tuple[re.Pattern[str], Any]] = [
    (pattern, _make_block_fn(label)) for pattern, label in _EXFIL_PATTERNS
]


def _replace_secret(m: re.Match[str]) -> str:
    """Ersetzt die captured Gruppe durch [REDACTED], behält Prefix."""
    full = m.group(0)
    secret = m.group(1) if m.lastindex and m.lastindex >= 1 else full
    return full.replace(secret, "[REDACTED]", 1)


def sanitize_tool_output(text: str | None) -> str:
    """Bereinigt Tool-Output bevor er ans LLM zurückgegeben wird.

    Entfernt oder maskiert:
    - API-Keys, Passwörter, Tokens via Regex (ReDoS-sicher, Obergrenzen gesetzt)
    - Exfiltrations-Vektoren: Markdown-Bild/-Link, HTML-img, CSS-url()

    Wendet Unicode-Normalisierung (NFKC) an, um Homoglyphen-Bypässe zu verhindern.

    Args:
        text: Roher Tool-Output. None wird als leerer String behandelt.

    Returns:
        Bereinigter String mit [REDACTED] statt Secrets.
    """
    if not text:
        return text or ""

    # NFKC-Normalisierung: verhindert Unicode-Homoglyphen-Bypässe
    text = unicodedata.normalize("NFKC", text)

    original_len = len(text)
    total_replacements = 0

    # Secret-Patterns
    for pattern in _SECRET_PATTERNS:
        new_text, n = pattern.subn(_replace_secret, text)
        if n:
            total_replacements += n
            text = new_text

    # Exfiltrations-Vektoren blockieren
    for pattern, _block_fn in _EXFIL_HANDLERS:
        text = pattern.sub(_block_fn, text)

    if total_replacements > 0:
        logger.warning(
            "Outbound-Sanitizer: %d Secret(s) in Tool-Output redaktiert "
            "(original %d Bytes → %d Bytes).",
            total_replacements,
            original_len,
            len(text),
        )

    return text


def format_tool_error(tool_name: str, exc: Exception) -> str:
    """Format a tool exception as user-friendly error message.

    Args:
        tool_name: Tool that raised the error.
        exc: The exception.

    Returns:
        Formatted error message for the user.
    """
    error_type = type(exc).__name__
    error_msg = str(exc)

    if not error_msg:
        return f"Error: {tool_name} failed with {error_type}"

    return f"Error in {tool_name}: {error_msg}"


async def safe_tool_invoke(
    tool_fn: Any,
    tool_input: dict[str, Any],
    *,
    tool_name: str = "unknown",
) -> str:
    """Invoke a tool function with error handling.

    Catches exceptions and returns error messages instead of raising.

    Args:
        tool_fn: The tool function to invoke (sync or async).
        tool_input: Arguments to pass to the tool.
        tool_name: Name for error messages.

    Returns:
        Result string or error message string.
    """
    try:
        if asyncio.iscoroutinefunction(tool_fn):
            return await tool_fn(tool_input)
        return tool_fn(tool_input)
    except Exception as exc:
        # Exception-Message durch Sanitizer führen, verhindert Secret-Leakage im Log
        sanitized_exc = sanitize_tool_output(str(exc))
        logger.warning("Tool '%s' error: %s", tool_name, sanitized_exc)
        return sanitize_tool_output(format_tool_error(tool_name, exc))


class ToolErrorHandler:
    """Handles tool errors and converts them to ToolMessage format.

    Can be used as a mixin or wrapper for agents that need
    tool error handling.
    """

    async def handle_tool_error(
        self,
        tool_name: str,
        tool_args: dict[str, Any],
        exception: Exception,
    ) -> dict[str, Any]:
        """Convert a tool exception to error message dict.

        Args:
            tool_name: Name of the tool that failed.
            tool_args: Arguments passed to the tool.
            exception: The exception that was raised.

        Returns:
            Error dict with content and status for ToolMessage.
        """
        error_content = sanitize_tool_output(format_tool_error(tool_name, exception))
        logger.debug("Tool error handled: %s - %s", tool_name, error_content)

        return {
            "content": error_content,
            "status": "error",
            "tool_name": tool_name,
        }

    async def invoke_tool_safe(
        self,
        tool_fn: Any,
        tool_args: dict[str, Any],
        *,
        tool_name: str = "unknown",
    ) -> dict[str, Any]:
        """Invoke a tool with error handling, return dict format.

        Args:
            tool_fn: Tool function to invoke.
            tool_args: Arguments for the tool.
            tool_name: Tool name for error messages.

        Returns:
            Dict with content (result or error) and status.
        """
        try:
            if asyncio.iscoroutinefunction(tool_fn):
                result = await tool_fn(tool_args)
            else:
                result = tool_fn(tool_args)

            return {
                "content": str(result) if result else "",
                "status": "ok",
                "tool_name": tool_name,
            }
        except Exception as exc:
            return await self.handle_tool_error(tool_name, tool_args, exc)


# ---------------------------------------------------------------------------
# Tool-Patching mit integrierter Secret Sanitization
# ---------------------------------------------------------------------------


def wrap_tools_with_sanitizer(tools: list[Any]) -> list[Any]:
    """Patcht die _run/_arun-Methoden jedes Tools mit Secret Sanitization.

    Modifiziert die Tool-Instanzen in-place (kein neues Objekt), damit
    isinstance-Checks von LangGraph/LangChain weiterhin funktionieren.

    Idempotent: Bereits gepatchte Tools werden übersprungen.

    Args:
        tools: Liste von LangChain BaseTool-Instanzen.

    Returns:
        Dieselbe Liste mit gepatchten Tools.
    """
    from langchain_core.tools import BaseTool

    for tool in tools:
        if not isinstance(tool, BaseTool):
            continue

        # Idempotenz-Guard: kein doppeltes Patching
        if getattr(tool, "_sanitizer_applied", False):
            continue

        original_run = tool._run
        original_arun = tool._arun

        def _make_sanitized_run(orig: Any) -> Any:
            sig = inspect.signature(orig)
            has_config = "config" in sig.parameters

            def _sanitized_run(*args: Any, **kwargs: Any) -> Any:
                # LangChain compatibility: newer tool implementations may require
                # keyword-only `config` in _run/_arun. Ensure it is present.
                if has_config and "config" not in kwargs:
                    kwargs["config"] = None
                result = orig(*args, **kwargs)
                return sanitize_tool_output(str(result)) if result is not None else ""
            return _sanitized_run

        def _make_sanitized_arun(orig: Any) -> Any:
            sig = inspect.signature(orig)
            has_config = "config" in sig.parameters

            async def _sanitized_arun(*args: Any, **kwargs: Any) -> Any:
                # LangChain compatibility: newer tool implementations may require
                # keyword-only `config` in _run/_arun. Ensure it is present.
                if has_config and "config" not in kwargs:
                    kwargs["config"] = None
                result = await orig(*args, **kwargs)
                return sanitize_tool_output(str(result)) if result is not None else ""
            return _sanitized_arun

        tool._run = _make_sanitized_run(original_run)  # type: ignore[method-assign]
        tool._arun = _make_sanitized_arun(original_arun)  # type: ignore[method-assign]
        object.__setattr__(tool, "_sanitizer_applied", True)

    return tools
