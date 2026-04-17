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
from collections.abc import Callable
from pathlib import Path

from langchain_core.tools import tool

logger = logging.getLogger("ninko.modules.codelab")

# Pfade, die read-only in den bwrap-Namespace gemountet werden.
_BWRAP_RO_BIND_CANDIDATES = [
    "/usr",
    "/bin",
    "/sbin",
    "/lib",
    "/lib64",
    "/lib32",
    "/etc/localtime",
    "/etc/ssl/certs",
    "/etc/ca-certificates",
]


def _build_bwrap_cmd(exec_cmd: list[str], tmp_dir: str, bwrap_bin: str) -> list[str]:
    """
    Wraps exec_cmd mit bubblewrap (bwrap) für Filesystem-Isolation.

    Der Sandbox-Prozess erhält:
    - Read-only Zugriff auf System-Binaries und -Libraries
    - Vollständig isoliertes /tmp (tmpfs)
    - Read/Write-Zugriff nur auf tmp_dir (für das Script)
    - Neuen proc/dev-Namespace
    - Alle Linux-Capabilities gedroppt (--cap-drop all)
    - Keine Sichtbarkeit des Host-Filesystems außerhalb der erlaubten Pfade

    Netzwerk wird bewusst NICHT isoliert, damit IT-Ops-Scripts externe
    Hosts erreichen können. Filesystem-Isolation ist der primäre Schutz.
    """
    args: list[str] = [bwrap_bin]

    # Read-only System-Pfade einbinden (nur wenn vorhanden).
    # Symlinks (z.B. /bin -> usr/bin) werden als Symlink in den Namespace übernommen.
    # Das Symlink-Ziel wird zusätzlich per --ro-bind eingebunden, damit es auch
    # tatsächlich erreichbar ist (os.readlink gibt den Rohwert zurück, der relativ
    # sein kann — der aufgelöste realpath wird direkt gebunden).
    already_bound: set[str] = set()
    for path in _BWRAP_RO_BIND_CANDIDATES:
        if os.path.islink(path):
            raw_target = os.readlink(path)
            # Symlink im Namespace anlegen (mit dem Originalwert, z.B. "usr/bin")
            args += ["--symlink", raw_target, path]
            # Realpath des Ziels einbinden, damit die Auflösung innerhalb des
            # Namespace nicht ins Leere läuft
            real = os.path.realpath(path)
            if real not in already_bound and (os.path.isdir(real) or os.path.isfile(real)):
                args += ["--ro-bind", real, real]
                already_bound.add(real)
        elif os.path.isdir(path) or os.path.isfile(path):
            real = os.path.realpath(path)
            if real not in already_bound:
                args += ["--ro-bind", path, path]
                already_bound.add(real)

    # proc und dev Namespace
    args += ["--proc", "/proc", "--dev", "/dev"]

    # Isoliertes /tmp (tmpfs — kein Zugriff auf Host-/tmp)
    args += ["--tmpfs", "/tmp"]

    # Script-Verzeichnis read/write einbinden
    args += ["--bind", tmp_dir, tmp_dir]

    # Working Directory im Sandbox-Namespace
    args += ["--chdir", tmp_dir]

    # Alle Namespaces außer Netzwerk isolieren.
    # --unshare-pid: bwrap wird PID 1 im neuen Namespace — alle Kindprozesse
    # sterben beim Tod von PID 1 (Kernel-Garantie, stärker als --die-with-parent).
    args += [
        "--unshare-user",
        "--unshare-ipc",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-cgroup",
        "--die-with-parent",
        "--new-session",
    ]

    # Alle Linux-Capabilities droppen — verhindert privilegierte Syscalls
    # (cap_net_raw, cap_sys_ptrace, etc.) aus LLM-generiertem Code.
    args += ["--cap-drop", "all"]

    args += ["--", *exec_cmd]
    return args

# Resource limits loaded from core config


def _get_resource_limits() -> dict[str, int]:
    """Get resource limits from core settings."""
    from core.config import get_settings

    settings = get_settings()
    return {
        "max_code_chars": settings.CODELAB_MAX_CODE_CHARS,
        "max_stdout_chars": settings.CODELAB_MAX_STDOUT_CHARS,
        "max_stderr_chars": settings.CODELAB_MAX_STDERR_CHARS,
        "max_memory_bytes": settings.CODELAB_MAX_MEMORY_BYTES,
        "max_filesize_bytes": settings.CODELAB_MAX_FILESIZE_BYTES,
        "max_nofile": settings.CODELAB_MAX_NOFILE,
        "max_nproc": settings.CODELAB_MAX_NPROC,
    }


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
    return {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": tmp_dir,
        "TMPDIR": tmp_dir,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
        "PYTHONPATH": "",
    }


def _make_preexec(
    timeout: int,
    memory_bytes: int,
    filesize_bytes: int,
    nofile: int,
    nproc: int,
) -> Callable[[], None]:
    """
    Setzt harte Ressourcenlimits pro Ausführung.
    Hinweis: gilt nur auf POSIX-Systemen.
    """

    def _preexec() -> None:
        import resource

        os.setsid()
        cpu = max(1, min(timeout + 1, 60))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
        resource.setrlimit(resource.RLIMIT_FSIZE, (filesize_bytes, filesize_bytes))
        resource.setrlimit(resource.RLIMIT_NOFILE, (nofile, nofile))
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
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

    limits = _get_resource_limits()

    if len(code) > limits["max_code_chars"]:
        return {
            "stdout": "",
            "stderr": f"Code ist zu groß ({len(code)} Zeichen, max {limits['max_code_chars']}).",
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

        inner_cmd = cfg["cmd"](tmp_path)
        _bwrap_candidate = shutil.which("bwrap") if os.name == "posix" else None
        # Nur absoluten Pfad akzeptieren — verhindert Injection via manipuliertem PATH
        bwrap_bin = _bwrap_candidate if (_bwrap_candidate and os.path.isabs(_bwrap_candidate)) else None
        use_bwrap = bwrap_bin is not None
        if use_bwrap:
            cmd = _build_bwrap_cmd(inner_cmd, tmp_dir, bwrap_bin)
            logger.debug("CodeLab: bwrap-Sandbox aktiv für %s", language)
        else:
            cmd = inner_cmd
            logger.warning(
                "CodeLab: bwrap nicht verfügbar — kein Filesystem-Namespace-Schutz! "
                "Scripts laufen mit RLIMIT_*-Limits, aber ohne Filesystem-Isolation."
            )
        t_start = time.perf_counter()
        sandbox_env = _build_sandbox_env(tmp_dir)
        preexec = (
            _make_preexec(
                timeout,
                limits["max_memory_bytes"],
                limits["max_filesize_bytes"],
                limits["max_nofile"],
                limits["max_nproc"],
            )
            if os.name == "posix"
            else None
        )

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
            # Bei bwrap: proc ist der bwrap-Wrapper. Da --unshare-pid aktiv ist,
            # ist bwrap PID 1 im neuen Namespace — der Kernel beendet alle
            # Kindprozesse beim Tod von PID 1. proc.kill() reicht daher aus.
            # Ohne bwrap: os.setsid() im preexec erzeugt eine neue Session;
            # killpg trifft die gesamte Prozessgruppe.
            try:
                if use_bwrap or os.name != "posix":
                    proc.kill()
                else:
                    os.killpg(proc.pid, signal.SIGKILL)
            except (ProcessLookupError, OSError, RuntimeError):
                pass
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

        if len(stdout) > limits["max_stdout_chars"]:
            stdout = stdout[: limits["max_stdout_chars"]] + "\n… (Ausgabe gekürzt)"
        if len(stderr) > limits["max_stderr_chars"]:
            stderr = (
                stderr[: limits["max_stderr_chars"]] + "\n… (Fehlerausgabe gekürzt)"
            )

        logger.info(
            "CodeLab: %s ausgeführt, exit=%d, %.0fms, bwrap=%s",
            language,
            proc.returncode,
            duration_ms,
            use_bwrap,
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
