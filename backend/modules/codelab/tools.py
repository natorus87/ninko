"""
CodeLab Modul – Tools für Code-Ausführung in der Sandbox.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import tempfile
import time
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.codelab")

_MAX_CODE_CHARS = 100_000
_MAX_STDOUT_CHARS = 20_000
_MAX_STDERR_CHARS = 5_000
_MAX_MEMORY_BYTES = 256 * 1024 * 1024
_MAX_FILESIZE_BYTES = 5 * 1024 * 1024
_MAX_NOFILE = 64
_MAX_NPROC = 16

# Unterstützte Sprachen mit Ausführungs-Kommandos
_LANGUAGES: dict[str, dict] = {
    "python": {
        "binary": "python3",
        "ext": ".py",
        "cmd": lambda f: ["python3", "-I", "-B", "-u", f],
    },
    "bash": {
        "binary": "bash",
        "ext": ".sh",
        "cmd": lambda f: ["bash", f],
    },
    "javascript": {
        "binary": "node",
        "ext": ".js",
        "cmd": lambda f: ["node", f],
    },
    "sh": {
        "binary": "sh",
        "ext": ".sh",
        "cmd": lambda f: ["sh", f],
    },
}


def _available_languages() -> list[str]:
    """Gibt alle installierten Sprachen zurück."""
    result = []
    for lang, cfg in _LANGUAGES.items():
        if shutil.which(cfg["binary"]):
            result.append(lang)
    return result


def _build_sandbox_env(tmp_dir: str) -> dict[str, str]:
    """Erzeugt ein minimales Environment für Subprozesse."""
    safe_path = os.environ.get("PATH", "/usr/bin:/bin")
    return {
        "PATH": safe_path,
        "HOME": tmp_dir,
        "TMPDIR": tmp_dir,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": "",
    }


def _make_preexec(timeout: int) -> object:
    """
    Setzt harte Ressourcenlimits pro Ausführung.
    Hinweis: gilt nur auf POSIX-Systemen.
    """
    def _preexec() -> None:
        import resource

        os.setsid()
        cpu = max(1, min(timeout + 1, 60))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (_MAX_MEMORY_BYTES, _MAX_MEMORY_BYTES))
        resource.setrlimit(resource.RLIMIT_FSIZE, (_MAX_FILESIZE_BYTES, _MAX_FILESIZE_BYTES))
        resource.setrlimit(resource.RLIMIT_NOFILE, (_MAX_NOFILE, _MAX_NOFILE))
        resource.setrlimit(resource.RLIMIT_NPROC, (_MAX_NPROC, _MAX_NPROC))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))

    return _preexec


@tool
async def execute_code(code: str, language: str = "python", timeout: int = 15) -> dict:
    """
    Führt Code in einer isolierten Sandbox aus und gibt stdout, stderr,
    Exit-Code und Ausführungsdauer zurück.

    Args:
        code: Der auszuführende Quellcode.
        language: Programmiersprache (python, bash, javascript, sh).
        timeout: Maximale Laufzeit in Sekunden (Standard: 15, Max: 60).

    Returns:
        Dict mit stdout, stderr, exit_code, duration_ms, language.
    """
    language = language.lower().strip()
    timeout = max(1, min(timeout, 60))
    code = code or ""

    if len(code) > _MAX_CODE_CHARS:
        return {
            "stdout": "",
            "stderr": f"Code ist zu groß ({len(code)} Zeichen, max {_MAX_CODE_CHARS}).",
            "exit_code": 1,
            "duration_ms": 0.0,
            "language": language,
            "error": "Code zu groß.",
        }

    if language not in _LANGUAGES:
        available = _available_languages()
        return {
            "stdout": "",
            "stderr": f"Unbekannte Sprache: '{language}'. Verfügbar: {', '.join(available)}",
            "exit_code": 1,
            "duration_ms": 0.0,
            "language": language,
            "error": f"Sprache '{language}' nicht unterstützt.",
        }

    cfg = _LANGUAGES[language]
    if not shutil.which(cfg["binary"]):
        return {
            "stdout": "",
            "stderr": f"'{cfg['binary']}' ist nicht installiert.",
            "exit_code": 1,
            "duration_ms": 0.0,
            "language": language,
            "error": f"Binary '{cfg['binary']}' nicht gefunden.",
        }

    with tempfile.TemporaryDirectory(prefix="codelab-") as tmp_dir:
        tmp_path = str(Path(tmp_dir) / f"main{cfg['ext']}")
        Path(tmp_path).write_text(code, encoding="utf-8")

        cmd = cfg["cmd"](tmp_path)
        t_start = time.perf_counter()
        sandbox_env = _build_sandbox_env(tmp_dir)
        preexec = _make_preexec(timeout) if os.name == "posix" else None

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=tmp_dir,
            env=sandbox_env,
            preexec_fn=preexec,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, OSError, RuntimeError):
                    proc.kill()
            else:
                proc.kill()
            await proc.communicate()
            return {
                "stdout": "",
                "stderr": f"Timeout nach {timeout}s — Prozess wurde beendet.",
                "exit_code": -1,
                "duration_ms": timeout * 1000.0,
                "language": language,
                "error": "Timeout",
            }

        duration_ms = (time.perf_counter() - t_start) * 1000

        stdout = stdout_bytes.decode("utf-8", errors="replace")
        stderr = stderr_bytes.decode("utf-8", errors="replace")

        if len(stdout) > _MAX_STDOUT_CHARS:
            stdout = stdout[:_MAX_STDOUT_CHARS] + "\n… (Ausgabe gekürzt)"
        if len(stderr) > _MAX_STDERR_CHARS:
            stderr = stderr[:_MAX_STDERR_CHARS] + "\n… (Fehlerausgabe gekürzt)"

        logger.info(
            "CodeLab: %s ausgeführt, exit=%d, %.0fms",
            language, proc.returncode, duration_ms,
        )

        return {
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": proc.returncode,
            "duration_ms": round(duration_ms, 1),
            "language": language,
            "error": "",
        }


@tool
def get_available_languages() -> dict:
    """
    Gibt alle in der Sandbox verfügbaren Programmiersprachen zurück.

    Returns:
        Dict mit verfügbaren Sprachen und ihren Binaries.
    """
    result = {}
    for lang, cfg in _LANGUAGES.items():
        binary = cfg["binary"]
        path = shutil.which(binary)
        result[lang] = {
            "available": path is not None,
            "binary": binary,
            "path": path or "nicht gefunden",
        }
    return result
