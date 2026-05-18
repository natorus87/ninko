"""
Agent Browser Modul – Tools (Subprocess-Wrapper für `agent-browser` CLI).

Konzept:
- `agent-browser` ist ein Rust-CLI (siehe https://agent-browser.dev), das einen
  Chromium-Daemon via CDP steuert. Die Binary muss im Image installiert sein.
- Jedes Tool spawnt die CLI via asyncio.create_subprocess_exec (kein Shell),
  sammelt stdout/stderr und gibt einen für den LLM-Agent verträglichen String
  zurück.
- Sessions werden über `--session <name>` getrennt. Default: "default".
- Outputs werden auf 200 Zeilen gekürzt; offensichtliche Geheimnisse (Passwort-
  Felder, Bearer-Token, API-Keys) werden redacted, bevor sie in den LLM-Kontext
  zurückwandern.

Sicherheitsmaßnahmen:
- argv-Aufruf: positional user-args stehen IMMER hinter einem `--`-Trenner,
  damit ein "selector" wie `--profile=/etc/passwd` nicht als Flag geparst wird.
- Minimales subprocess env: weder OPENAI/ANTHROPIC-Keys noch DB-URLs werden
  an Chromium / Rust-CLI weitergereicht.
- Concurrency-Cap (default 3) gegen LLM-getriebene Subprocess-Floods.
- URL-Validierung: nur http(s), und IPs aus loopback/link-local/multicast/
  unspecified werden geblockt (deckt 127.0.0.1, ::1, 169.254.169.254 ab).
  RFC1918-Adressen bleiben erlaubt — das ist genau der Use-Case (interne
  IT-Tools testen).
- Session-Name: strenge Whitelist gegen argv-Injection.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
import shutil
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

from langchain.tools import tool

logger = logging.getLogger("ninko.modules.agent_browser")

# ── Konfiguration ─────────────────────────────────────────────────────────

_BIN = "agent-browser"
_DEFAULT_TIMEOUT = 60.0
_OPEN_TIMEOUT = 90.0
_CLOSE_TIMEOUT = 15.0
_MAX_LINES = 200
_SCREENSHOT_DIR = Path(
    os.getenv("NINKO_AGENT_BROWSER_SCREENSHOT_DIR", "/tmp/ninko-agent-browser-screenshots")
)
_SCREENSHOT_TTL_SECONDS = int(
    os.getenv("NINKO_AGENT_BROWSER_SCREENSHOT_TTL", str(24 * 3600))
)
_GC_THROTTLE_SECONDS = 600.0

_CHECK_SESSION = "ninko-check"
_DEFAULT_SESSION = "default"

_SESSION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MAX_CONCURRENT = max(1, int(os.getenv("NINKO_AGENT_BROWSER_MAX_CONCURRENT", "3")))

_ALLOWED_URL_SCHEMES = frozenset({"http", "https"})
_BLOCKED_HOSTNAMES = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata",
})

# ── Subprocess-Env (minimal, ohne Ninko-Secrets) ──────────────────────────

def _minimal_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": os.environ.get("HOME", "/tmp"),
        "LANG": os.environ.get("LANG", "C.UTF-8"),
        "LC_ALL": os.environ.get("LC_ALL", "C.UTF-8"),
    }
    for key in ("NINKO_AGENT_BROWSER_CHROMIUM", "DISPLAY", "XDG_RUNTIME_DIR"):
        if (val := os.environ.get(key)) is not None:
            env[key] = val
    return env


# ── Concurrency-Limit (lazy, weil Modul-Import außerhalb Event-Loop) ──────

_semaphore: asyncio.Semaphore | None = None


def _get_semaphore() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(_MAX_CONCURRENT)
    return _semaphore


# ── Validierung ───────────────────────────────────────────────────────────

def _validate_session(session: str) -> str:
    """Akzeptiert nur sichere Session-Namen (verhindert Argument-Injection)."""
    if not session or not _SESSION_RE.match(session):
        raise ValueError(
            f"invalid session name: {session!r} "
            "(allowed: [A-Za-z0-9_.-], max 64 chars)"
        )
    return session


async def _validate_url(url: str) -> str:
    """
    Erlaubt nur http(s) URLs und blockiert eindeutig gefährliche Ziele
    (loopback, link-local inkl. 169.254.169.254 Cloud-Metadata,
    multicast, unspecified).

    Private RFC1918-Netze bleiben erlaubt — das ist der Zweck des Moduls
    (interne IT-Tools wie Grafana, Wazuh testen). Wer strikte Trennung
    will, setzt NINKO_AGENT_BROWSER_BLOCK_PRIVATE=true.
    """
    block_private = os.getenv("NINKO_AGENT_BROWSER_BLOCK_PRIVATE", "false").lower() == "true"

    parsed = urlparse(url)
    if parsed.scheme.lower() not in _ALLOWED_URL_SCHEMES:
        raise ValueError(f"unsupported URL scheme: {parsed.scheme!r} (only http/https)")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL must have a hostname")
    if host in _BLOCKED_HOSTNAMES:
        raise ValueError(f"blocked hostname: {host}")

    # Hostnamen können IPs sein → direkt prüfen. Sonst DNS auflösen.
    try:
        ip_candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [
            ipaddress.ip_address(host)
        ]
    except ValueError:
        try:
            loop = asyncio.get_running_loop()
            infos = await loop.getaddrinfo(host, None)
        except socket.gaierror as exc:
            raise ValueError(f"cannot resolve host {host}: {exc}") from exc
        ip_candidates = []
        for _family, _type, _proto, _canon, sockaddr in infos:
            try:
                ip_candidates.append(ipaddress.ip_address(sockaddr[0]))
            except (ValueError, IndexError):
                continue

    if not ip_candidates:
        raise ValueError(f"no usable IP for host {host}")

    for ip in ip_candidates:
        if (
            ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_unspecified
            or ip.is_reserved
        ):
            raise ValueError(f"blocked address {ip} for host {host}")
        if block_private and ip.is_private:
            raise ValueError(f"blocked private address {ip} for host {host}")

    return url


# ── Output-Hygiene ────────────────────────────────────────────────────────

def _truncate(text: str) -> str:
    lines = text.splitlines()
    if len(lines) <= _MAX_LINES:
        return text.rstrip()
    kept = lines[:_MAX_LINES]
    kept.append(f"[… {len(lines) - _MAX_LINES} weitere Zeilen gekürzt]")
    return "\n".join(kept)


_REDACTION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r'(type\s*=\s*["\']?password["\']?[^>]*?value\s*=\s*["\'])([^"\'>]+)', re.I),
        r"\1<REDACTED>",
    ),
    (re.compile(r"\b(Bearer\s+)[A-Za-z0-9._\-+/=]+", re.I), r"\1<REDACTED>"),
    (
        re.compile(r"\b(sk-[A-Za-z0-9_-]{20,}|xox[bpoars]-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})\b"),
        "<REDACTED>",
    ),
    (re.compile(r"(?i)(api[_-]?key|secret|token|passwd|password)\s*[:=]\s*([^\s,;\"'<>]{6,})"), r"\1=<REDACTED>"),
)


def _redact(text: str) -> str:
    for pat, repl in _REDACTION_PATTERNS:
        text = pat.sub(repl, text)
    return text


# ── Screenshot-GC (throttled, opportunistisch) ────────────────────────────

_last_gc: float = 0.0


def _maybe_gc_screenshots() -> None:
    global _last_gc
    now = time.time()
    if now - _last_gc < _GC_THROTTLE_SECONDS:
        return
    _last_gc = now
    if not _SCREENSHOT_DIR.is_dir():
        return
    for p in _SCREENSHOT_DIR.glob("*.png"):
        try:
            if now - p.stat().st_mtime > _SCREENSHOT_TTL_SECONDS:
                p.unlink()
        except OSError:
            continue


# ── Subprocess-Helper ─────────────────────────────────────────────────────

def _build_cmd(
    global_flags: list[str],
    verb: str,
    *positional: str,
) -> list[str]:
    """
    Baut das argv-Array. Positional user-Args landen HINTER `--`, damit der
    Rust-Argparse-Layer Selektor-Strings wie `--profile=...` nicht als Flag
    interpretiert.
    """
    cmd: list[str] = [_BIN, *global_flags, verb]
    if positional:
        cmd.append("--")
        cmd.extend(positional)
    return cmd


async def _run(cmd: list[str], timeout: float = _DEFAULT_TIMEOUT) -> str:
    """Führt agent-browser aus. Wirft RuntimeError bei Fehler."""
    if shutil.which(_BIN) is None:
        raise RuntimeError(
            f"`{_BIN}` not installed in container. "
            "Rebuild image with `npm install -g agent-browser`."
        )

    # Nie das volle argv loggen — verb-args können Passwörter (type/fill) sein.
    logger.debug("agent-browser exec: %s verb=%s (argc=%d)", _BIN, _safe_verb(cmd), len(cmd))

    sem = _get_semaphore()
    async with sem:
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=_minimal_env(),
            )
        except OSError as exc:
            raise RuntimeError(f"failed to spawn {_BIN}: {exc}") from exc

        try:
            stdout_b, stderr_b = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError as exc:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"agent-browser timeout after {timeout}s for verb {_safe_verb(cmd)}"
            ) from exc

    stdout = (stdout_b or b"").decode(errors="replace")
    stderr = (stderr_b or b"").decode(errors="replace")

    if proc.returncode != 0:
        err = stderr.strip() or stdout.strip()
        # stderr kann redirected page content enthalten → redacten.
        raise RuntimeError(
            f"agent-browser exit {proc.returncode}: {_redact(err)[:400]}"
        )

    return stdout


def _safe_verb(cmd: list[str]) -> str:
    """Extrahiert das Verb aus einem cmd-Array für sicheres Logging."""
    skip_next = False
    for arg in cmd[1:]:
        if skip_next:
            skip_next = False
            continue
        if arg in {"--session", "--profile", "--proxy", "--timeout", "--load"}:
            skip_next = True
            continue
        if arg.startswith("--") or arg == "--":
            continue
        return arg
    return "?"


def _session_flags(session: str) -> list[str]:
    return ["--session", _validate_session(session)]


# ── READONLY ──────────────────────────────────────────────────────────────


@tool
async def check_website(url: str) -> str:
    """
    Quick health check for a website.

    Opens the URL in an isolated browser session, waits for network idle,
    grabs an accessibility snapshot to confirm the page rendered, and closes
    the session. Use this to verify that an IT tool or web UI is up and
    responsive without leaving a persistent session behind.

    Args:
        url: Full URL (https://...) to check.

    Returns:
        Snapshot summary (truncated, secrets redacted) or an error message.
    """
    try:
        validated_url = await _validate_url(url)
    except ValueError as exc:
        return f"FAIL — {url}\n\n{exc}"

    session_flags = _session_flags(_CHECK_SESSION)
    try:
        await _run(
            _build_cmd(session_flags, "open", validated_url) + ["--load", "networkidle"],
            timeout=_OPEN_TIMEOUT,
        )
        snapshot = await _run(_build_cmd(session_flags, "snapshot"))
        return f"OK — {validated_url}\n\n{_redact(_truncate(snapshot))}"
    except RuntimeError as exc:
        return f"FAIL — {validated_url}\n\n{exc}"
    finally:
        try:
            await _run(_build_cmd(session_flags, "close"), timeout=_CLOSE_TIMEOUT)
        except RuntimeError as cleanup_err:
            logger.warning(
                "agent-browser cleanup failed for session %s: %s",
                _CHECK_SESSION,
                cleanup_err,
            )


@tool
async def take_snapshot(session: str = _DEFAULT_SESSION) -> str:
    """
    Return the accessibility tree (with @refs) of the current page in a session.

    Use this to discover clickable / interactive elements before calling
    `click_element` or `type_text` with the returned `@e<n>` refs. Password
    fields and obvious tokens are redacted before returning.

    Args:
        session: Session name. Defaults to "default".
    """
    try:
        out = await _run(_build_cmd(_session_flags(session), "snapshot"))
        return _redact(_truncate(out)) or "(empty snapshot)"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


@tool
async def get_element_text(selector: str, session: str = _DEFAULT_SESSION) -> str:
    """
    Return the text content of an element.

    Args:
        selector: Element ref from snapshot (e.g. "@e2") or CSS selector.
        session: Session name. Defaults to "default".
    """
    try:
        out = await _run(_build_cmd(_session_flags(session), "get", "text", selector))
        return _redact(_truncate(out)) or "(empty)"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


@tool
async def take_screenshot(
    session: str = _DEFAULT_SESSION, full_page: bool = False
) -> str:
    """
    Capture a PNG screenshot of the current page. Returns the host file path.

    Args:
        session: Session name. Defaults to "default".
        full_page: If True, capture the entire scrollable page.
    """
    try:
        _validate_session(session)
        _SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
        _maybe_gc_screenshots()
        out_path = _SCREENSHOT_DIR / f"{session}-{time.time_ns()}.png"
        cmd = _build_cmd(_session_flags(session), "screenshot", str(out_path))
        if full_page:
            cmd.append("--full")
        await _run(cmd)
        return f"Screenshot saved: {out_path}"
    except (RuntimeError, ValueError, OSError) as exc:
        return f"ERROR: {exc}"


@tool
async def wait_for_element(
    selector: str,
    session: str = _DEFAULT_SESSION,
    timeout_ms: int | None = None,
) -> str:
    """
    Wait until an element is present / visible.

    Args:
        selector: Element ref or CSS selector.
        session: Session name. Defaults to "default".
        timeout_ms: Optional wait timeout in milliseconds.
    """
    cmd = _build_cmd(_session_flags(session), "wait", selector)
    if timeout_ms is not None:
        cmd.extend(["--timeout", str(int(timeout_ms))])
    try:
        out = await _run(cmd)
        return _truncate(out) or f"OK — {selector} present"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


@tool
async def list_browser_sessions() -> str:
    """
    List active browser sessions managed by the agent-browser daemon.
    """
    try:
        # No user-controlled args → no `--` separator needed.
        out = await _run([_BIN, "session", "list"])
        return _truncate(out) or "(no sessions)"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


# ── WRITE_SYSTEM ──────────────────────────────────────────────────────────


@tool
async def open_browser_session(url: str, session: str = _DEFAULT_SESSION) -> str:
    """
    Open a URL in a named (persistent) browser session.

    The session keeps cookies and DOM state across subsequent tool calls.
    Call `close_browser_session` when done to free resources.

    Args:
        url: Full URL (https://...) to open.
        session: Session name. Defaults to "default".
    """
    try:
        validated_url = await _validate_url(url)
        await _run(
            _build_cmd(_session_flags(session), "open", validated_url) + ["--load", "networkidle"],
            timeout=_OPEN_TIMEOUT,
        )
        return f"OK — session '{session}' opened {validated_url}"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


@tool
async def click_element(selector: str, session: str = _DEFAULT_SESSION) -> str:
    """
    Click an element identified by an accessibility ref or CSS selector.

    Args:
        selector: Element ref from `take_snapshot` (e.g. "@e2") or CSS selector.
        session: Session name. Defaults to "default".
    """
    try:
        out = await _run(_build_cmd(_session_flags(session), "click", selector))
        return _truncate(out) or f"OK — clicked {selector}"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


@tool
async def type_text(
    selector: str,
    text: str,
    session: str = _DEFAULT_SESSION,
    clear: bool = False,
) -> str:
    """
    Type text into an input element.

    Args:
        selector: Element ref from snapshot (e.g. "@e2") or CSS selector.
        text: Text to type.
        session: Session name. Defaults to "default".
        clear: If True, clear the field first (uses `fill` instead of `type`).
    """
    try:
        verb = "fill" if clear else "type"
        out = await _run(_build_cmd(_session_flags(session), verb, selector, text))
        return _truncate(out) or f"OK — {verb} into {selector}"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"


@tool
async def close_browser_session(session: str = _DEFAULT_SESSION) -> str:
    """
    Close a browser session and free its resources.
    """
    try:
        await _run(_build_cmd(_session_flags(session), "close"), timeout=_CLOSE_TIMEOUT)
        return f"OK — session '{session}' closed"
    except (RuntimeError, ValueError) as exc:
        return f"ERROR: {exc}"
