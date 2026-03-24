"""
CodeLab Modul – Tools für Code-Ausführung in der Sandbox.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import tempfile
import time
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger("kumio.modules.codelab")

# Unterstützte Sprachen mit Ausführungs-Kommandos
_LANGUAGES: dict[str, dict] = {
    "python": {
        "binary": "python3",
        "ext": ".py",
        "cmd": lambda f: ["python3", "-u", f],
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

    # Code in temporäre Datei schreiben
    with tempfile.NamedTemporaryFile(
        suffix=cfg["ext"],
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    try:
        cmd = cfg["cmd"](tmp_path)
        t_start = time.perf_counter()

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
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

        # Ausgabe begrenzen (max 20 KB)
        if len(stdout) > 20_000:
            stdout = stdout[:20_000] + "\n… (Ausgabe gekürzt)"
        if len(stderr) > 5_000:
            stderr = stderr[:5_000] + "\n… (Fehlerausgabe gekürzt)"

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
    finally:
        Path(tmp_path).unlink(missing_ok=True)


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
