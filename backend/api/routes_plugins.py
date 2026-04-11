"""
Ninko Plugin API – Dynamische Installation und Deinstallation von Modulen (ZIP).
Enthält auch den Modul-Marketplace: Module direkt aus einem GitHub-Repository installieren.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import os
import re
import shutil
import sys
import time
import uuid
import tarfile
import zipfile
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import httpx
from fastapi import APIRouter, Request, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse

from core.redis_client import get_redis

logger = logging.getLogger("ninko.api.plugins")
router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

# ─── Marketplace – Multi-Repo ─────────────────────────────────────────────────
_REDIS_REPOS_KEY = "ninko:settings:marketplace_repos"
_OFFICIAL_REPO_ID = "official"
_DEFAULT_REPOS: list[dict[str, str]] = [
    {
        "id": _OFFICIAL_REPO_ID,
        "name": "Ninko Official",
        "repo_url": "https://github.com/natorus87/ninko",
        "branch": "main",
        "modules_path": "backend/modules_catalog",
        "github_token": "",
    }
]
_marketplace_cache: dict[str, Any] = {}
_CACHE_TTL = 0  # Will be loaded from settings dynamically
_REDIS_PLUGIN_META_KEY = "ninko:plugins:metadata"


def _get_cache_ttl() -> int:
    """Get cache TTL from settings (lazy load)."""
    from core.config import get_settings

    return get_settings().PLUGIN_CACHE_TTL_SECONDS


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────


def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extrahiert (owner, repo) aus einer GitHub-URL. Nur https://github.com/ URLs akzeptiert."""
    m = re.match(
        r"https://github\.com/([a-zA-Z0-9_.-]+)/([a-zA-Z0-9_.-]+?)(?:\.git)?$",
        url.strip(),
    )
    return (m.group(1), m.group(2)) if m else None


_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9_./ -]{1,128}$")


def _validate_branch(branch: str) -> str:
    """Validiert und gibt den Branch-Namen zurück (CWE-20).

    GitHub-Branch-Namen erlauben nur alphanumerische Zeichen, Punkte,
    Bindestriche, Schrägstriche und Leerzeichen. Sonderzeichen wie
    `..`, `?`, `#`, `@` sind in Git-Refs unzulässig.

    Raises:
        ValueError: wenn der Branch-Name ungültig ist.
    """
    branch = branch.strip()
    if not branch or not _SAFE_BRANCH_RE.match(branch) or ".." in branch:
        raise ValueError(f"Ungültiger Branch-Name: {branch!r}")
    return branch


def _version_tuple(v: str) -> tuple[int, ...]:
    """Convert version string to tuple for comparison. Returns (0,) for empty/invalid versions."""
    if not v or not isinstance(v, str):
        return (0,)
    try:
        # Remove leading 'v' and split by dots, filter out empty parts
        parts = v.strip().lstrip("v").split(".")
        return tuple(int(x) for x in parts if x.isdigit())
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ):
        return (0,)


def _extract_manifest_info(content: str) -> dict[str, str]:
    """Extrahiert key-Felder aus einer manifest.py per Regex."""

    def get(field: str) -> str:
        # Match: field="value", field = "value", field='value', field = 'value' (with optional comma)
        # Support both single and double quotes
        match = re.search(rf'{field}\s*=\s*["\']([^"\']+)["\']\s*,?', content)
        return match.group(1) if match else ""

    return {
        "name": get("name"),
        "display_name": get("display_name"),
        "description": get("description"),
        "version": get("version"),
        "author": get("author"),
    }


def _github_headers(token: str) -> dict[str, str]:
    h = {"Accept": "application/vnd.github.v3+json"}
    if token:
        h["Authorization"] = f"token {token}"
    return h


def _is_repo_allowed(repo_url: str) -> bool:
    """Optional allowlist via env `NINKO_PLUGIN_REPO_ALLOWLIST` (comma-separated)."""
    raw = os.getenv("NINKO_PLUGIN_REPO_ALLOWLIST", "").strip()
    if not raw:
        return True
    allowed = [entry.strip().lower() for entry in raw.split(",") if entry.strip()]
    if not allowed:
        return True
    url = repo_url.strip().lower()
    return any(
        url == entry or url.startswith(entry.rstrip("/") + "/") for entry in allowed
    )


# ─── Token-Verschlüsselung (CWE-256 Fix) ────────────────────────────────────
# GitHub-Tokens werden verschlüsselt in Redis gespeichert (Fernet AES-128-CBC).
# Schlüssel wird aus SESSION_SECRET abgeleitet — wenn kein Secret gesetzt ist,
# wird der Token zwar gespeichert, aber eine Warnung geloggt.
_TOKEN_PREFIX = "fernet:"


def _get_fernet() -> "Fernet | None":
    """Gibt eine Fernet-Instanz zurück, Schlüssel aus SESSION_SECRET abgeleitet."""
    import hashlib

    from cryptography.fernet import Fernet

    secret = os.getenv("SESSION_SECRET", "").strip()
    if not secret:
        logger.warning(
            "SESSION_SECRET nicht gesetzt — GitHub-Token kann nicht verschlüsselt werden."
        )
        return None
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def _encrypt_token(token: str) -> str:
    """Verschlüsselt einen Token mit Fernet. Gibt Plaintext zurück wenn kein Secret."""
    if not token:
        return token
    fernet = _get_fernet()
    if fernet is None:
        return token
    return _TOKEN_PREFIX + fernet.encrypt(token.encode()).decode()


def _decrypt_token(stored: str) -> str:
    """Entschlüsselt einen Fernet-Token. Gibt Plaintext zurück bei Legacy-Einträgen."""
    if not stored or not stored.startswith(_TOKEN_PREFIX):
        return stored  # Backwards-compatible: Legacy-Plaintext-Token
    from cryptography.fernet import InvalidToken

    fernet = _get_fernet()
    if fernet is None:
        return ""
    try:
        return fernet.decrypt(stored[len(_TOKEN_PREFIX) :].encode()).decode()
    except InvalidToken:
        logger.warning(
            "GitHub-Token konnte nicht entschlüsselt werden — Token gelöscht."
        )
        return ""


async def _load_repos() -> list[dict[str, Any]]:
    """Lädt die Repo-Liste aus Redis. Tokens werden on-the-fly entschlüsselt."""
    redis = get_redis()
    raw = await redis.connection.get(_REDIS_REPOS_KEY)
    if raw:
        repos = json.loads(raw)
        if repos:
            for repo in repos:
                if repo.get("github_token"):
                    repo["github_token"] = _decrypt_token(repo["github_token"])
            return repos
    return list(_DEFAULT_REPOS)


async def _save_repos(repos: list[dict[str, Any]]) -> None:
    """Speichert die Repo-Liste in Redis. Tokens werden vor dem Speichern verschlüsselt."""
    encrypted_repos = []
    for repo in repos:
        repo_copy = dict(repo)
        if repo_copy.get("github_token"):
            repo_copy["github_token"] = _encrypt_token(repo_copy["github_token"])
        encrypted_repos.append(repo_copy)
    redis = get_redis()
    await redis.connection.set(_REDIS_REPOS_KEY, json.dumps(encrypted_repos))
    _marketplace_cache.clear()


def _mask_repo(repo: dict[str, Any]) -> dict[str, Any]:
    """Gibt Repo-Dict ohne Token zurück, aber mit token_set-Flag."""
    return {k: v for k, v in repo.items() if k != "github_token"} | {
        "github_token_set": bool(repo.get("github_token"))
    }


async def _load_plugin_meta() -> dict[str, Any]:
    """Lädt Plugin-Metadaten aus Redis (Hash: plugin_name -> JSON)."""
    redis = get_redis()
    raw = await redis.connection.hgetall(_REDIS_PLUGIN_META_KEY)
    out: dict[str, Any] = {}
    for name, payload in raw.items():
        try:
            out[name] = json.loads(payload)
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            ImportError,
            json.JSONDecodeError,
        ):
            continue
    return out


async def _set_plugin_meta(plugin_name: str, meta: dict[str, Any]) -> None:
    redis = get_redis()
    await redis.connection.hset(_REDIS_PLUGIN_META_KEY, plugin_name, json.dumps(meta))


async def _delete_plugin_meta(plugin_name: str) -> None:
    redis = get_redis()
    await redis.connection.hdel(_REDIS_PLUGIN_META_KEY, plugin_name)


async def _download_dir_to_zip(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    branch: str,
    headers: dict[str, str],
    zf: zipfile.ZipFile,
    zip_prefix: str,
) -> None:
    """Lädt ein GitHub-Verzeichnis ohne API-Rate-Limit herunter.

    Verwendet den Repo-Tarball (github.com/archive) – kein api.github.com-Aufruf,
    daher kein Rate-Limit. Extrahiert nur das gewünschte Unterverzeichnis.
    """
    tarball_url = (
        f"https://github.com/{owner}/{repo}/archive/refs/heads/{branch}.tar.gz"
    )
    resp = await client.get(tarball_url, timeout=120.0, follow_redirects=True)
    if resp.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail=f"Repo '{owner}/{repo}' oder Branch '{branch}' nicht gefunden.",
        )
    resp.raise_for_status()

    prefix = path.rstrip("/") + "/"
    # Tarball root dir is "{repo}-{branch}/"
    tar_root = f"{repo}-{branch}/"

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            # Strip leading "{repo}-{branch}/"
            rel_to_root = (
                member.name[len(tar_root) :]
                if member.name.startswith(tar_root)
                else member.name
            )
            if not rel_to_root.startswith(prefix):
                continue
            rel = rel_to_root[len(prefix) :]
            if not rel:
                continue
            f = tar.extractfile(member)
            if f is None:
                continue
            zf.writestr(f"{zip_prefix}/{rel}", f.read())


def _build_module_list(
    all_modules: list[dict[str, str]],
    registry: Any,
    plugins_dir: Path,
    plugin_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Teilt Repo-Module in: nicht installiert vs. installiertes Plugin (mit Update-Info)."""
    installed_map: dict[str, str] = {
        m.name: m.version for m in registry.list_all_modules()
    }
    new_modules: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []

    for mod in all_modules:
        name = mod["name"]
        repo_version = mod.get("version", "")
        meta = (plugin_meta or {}).get(name, {})
        if name not in installed_map:
            new_modules.append(mod)
        elif (plugins_dir / name).is_dir():
            installed_version = installed_map[name]
            # Debug logging for version comparison
            repo_v_tuple = _version_tuple(repo_version)
            inst_v_tuple = _version_tuple(installed_version)
            is_update = repo_v_tuple > inst_v_tuple
            logger.debug(
                "Module %s: repo=%s (tuple=%s), installed=%s (tuple=%s), update=%s",
                name,
                repo_version,
                repo_v_tuple,
                installed_version,
                inst_v_tuple,
                is_update,
            )
            updates.append(
                {
                    **mod,
                    "installed_version": installed_version,
                    "update_available": is_update,
                    "installed_source": meta.get("source", ""),
                    "installed_updated_at": meta.get("updated_at", 0),
                }
            )
    return {"modules": new_modules, "updates": updates}


@router.get("/installed")
async def list_installed_plugins(request: Request) -> JSONResponse:
    """Listet installierte Plugins inkl. Versionierungs-/Herkunfts-Metadaten."""
    registry = request.app.state.registry
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_meta = await _load_plugin_meta()

    installed_map: dict[str, str] = {
        m.name: m.version for m in registry.list_all_modules()
    }
    installed = []
    for plugin_dir in sorted(plugins_dir.iterdir()):
        if not plugin_dir.is_dir():
            continue
        name = plugin_dir.name
        meta = plugin_meta.get(name, {})
        installed.append(
            {
                "name": name,
                "version": installed_map.get(name, ""),
                "installed_at": meta.get("installed_at", 0),
                "updated_at": meta.get("updated_at", 0),
                "source": meta.get("source", "unknown"),
                "repo_id": meta.get("repo_id", ""),
                "repo_url": meta.get("repo_url", ""),
                "repo_version": meta.get("repo_version", ""),
            }
        )

    return JSONResponse(content={"plugins": installed})


async def _check_module_update_from_repo(
    mod_name: str,
    repo_url: str,
    repo_id: str,
    branch: str,
    modules_path: str,
    installed_version: str,
) -> dict[str, Any]:
    """Fetch latest version of a module from a GitHub repo."""
    parsed = _parse_github_url(repo_url)
    if not parsed:
        return {"update_available": False}
    owner, repo_name = parsed

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"
            manifest_url = f"{raw_base}/{modules_path}/{mod_name}/manifest.py"
            resp = await client.get(manifest_url)
            if resp.status_code != 200:
                return {"update_available": False}
            info = _extract_manifest_info(resp.text)
            repo_version = info.get("version", "")
            return {
                "repo_version": repo_version,
                "update_available": _version_tuple(repo_version)
                > _version_tuple(installed_version),
            }
    except Exception as exc:
        logger.warning("Update check failed for %s: %s", mod_name, exc)
        return {"update_available": False, "check_failed": True}


@router.get("/check-updates")
async def check_plugin_updates(request: Request) -> JSONResponse:
    """Prüft für alle installierten Module (Plugins + Built-in), ob Updates verfügbar sind."""
    registry = request.app.state.registry
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_meta = await _load_plugin_meta()
    repos = await _load_repos()

    installed_map: dict[str, str] = {
        m.name: m.version for m in registry.list_all_modules()
    }
    results = []

    repo_url = "https://github.com/natorus87/ninko"
    branch = "main"
    modules_path = "backend/modules_catalog"

    for name, installed_version in installed_map.items():
        meta = plugin_meta.get(name, {})
        module_repo_url = meta.get("repo_url", repo_url)
        module_repo_id = meta.get("repo_id", _OFFICIAL_REPO_ID)

        if module_repo_url:
            parsed = _parse_github_url(module_repo_url)
            if parsed:
                owner, repo_name = parsed
                for r in repos:
                    if r.get("repo_url") == module_repo_url:
                        branch = r.get("branch", "main")
                        modules_path = r.get("modules_path", "backend/modules_catalog")
                        break

        update_info = await _check_module_update_from_repo(
            name,
            module_repo_url,
            module_repo_id,
            branch,
            modules_path,
            installed_version,
        )

        results.append(
            {
                "name": name,
                "installed_version": installed_version,
                "repo_version": update_info.get("repo_version", ""),
                "update_available": update_info.get("update_available", False),
                "repo_url": module_repo_url,
            }
        )

    return JSONResponse(content={"plugins": results})


_MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # 100 MB
_MAX_PLUGIN_FILES = 500  # Max Anzahl Dateien im ZIP (CWE-400: ZIP-Bomb-Schutz)
_DANGEROUS_REQ_PATTERNS = (
    "--index-url",
    "--extra-index-url",
    "-e git+",
    "-e svn+",
    "-e hg+",
    "file://",
    "--trusted-host",
    "--find-links",
)


async def install_requirements_if_exist(plugin_dir: Path) -> bool:
    """Sucht nach einer requirements.txt im Plugin und führt ggf. pip install aus."""
    req_file = plugin_dir / "requirements.txt"
    if not req_file.is_file():
        return True

    # Validate requirements.txt for dangerous patterns (CWE-20).
    # Normalisiere Whitespace vor dem Check um Bypass via Tabs/Spaces zu verhindern.
    req_content = req_file.read_text(encoding="utf-8", errors="replace")
    req_content_normalized = " ".join(req_content.lower().split())
    for pattern in _DANGEROUS_REQ_PATTERNS:
        if pattern.lower() in req_content_normalized:
            logger.error("requirements.txt enthält unerlaubtes Muster: %s", pattern)
            return False

    logger.info("Installiere Abhängigkeiten für Plugin aus: %s", req_file)
    logger.warning(
        "pip install ohne venv-Isolation: Plugin-Abhängigkeiten werden in den System-Namespace installiert. "
        "Sicherstellen, dass requirements.txt aus vertrauenswürdiger Quelle stammt."
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pip",
            "install",
            "--isolated",
            "--no-cache-dir",
            "-r",
            str(req_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("pip install fehlgeschlagen:\n%s", stderr.decode())
            return False

        logger.info("Abhängigkeiten erfolgreich installiert:\n%s", stdout.decode())
        return True
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as e:
        logger.error("Ausnahme bei der Installation der Abhängigkeiten: %s", e)
        return False


@router.post("/upload")
async def upload_plugin(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """
    Nimmt ein ZIP-Archiv entgegen, entpackt es unter `backend/plugins/<name>`
    und lädt es per Hot-Load in den Speicher.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(
            status_code=400, detail="Es muss eine ZIP-Datei hochgeladen werden."
        )

    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)

    # 1. ZIP in temporäres Verzeichnis speichern
    temp_dir = Path(mkdtemp())
    zip_path = temp_dir / file.filename

    try:
        with open(zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. ZIP-Sicherheitsprüfung und Entpacken
        extract_dir = temp_dir / "extracted"
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            members = zip_ref.infolist()
            # CWE-400: Limit Dateianzahl für ZIP-Bomb-Schutz
            if len(members) > _MAX_PLUGIN_FILES:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP-Archiv enthält zu viele Dateien: {len(members)} (max. {_MAX_PLUGIN_FILES}).",
                )
            total_size = sum(m.file_size for m in members)
            if total_size > _MAX_UNCOMPRESSED_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP-Archiv zu groß: {total_size // (1024 * 1024)} MB (max. 100 MB unkomprimiert).",
                )
            extract_dir_resolved = extract_dir.resolve()
            for member in members:
                if hasattr(member, "is_symlink") and member.is_symlink():
                    raise HTTPException(
                        status_code=400,
                        detail="ZIP-Archiv enthält symbolische Links (nicht erlaubt).",
                    )
                dest_path = (extract_dir / member.filename).resolve()
                if not str(dest_path).startswith(str(extract_dir_resolved)):
                    raise HTTPException(
                        status_code=400,
                        detail="ZIP-Archiv enthält ungültigen Pfad (Path-Traversal verhindert).",
                    )
            zip_ref.extractall(extract_dir)

        # Wir erwarten, dass im ZIP genau EINER Ordner liegt (das Plugin-Package, z.B. 'mein_plugin')
        contents = list(extract_dir.iterdir())
        if len(contents) != 1 or not contents[0].is_dir():
            raise HTTPException(
                status_code=400,
                detail="Das ZIP-Archiv muss exakt EINEN Root-Ordner (das Plugin-Verzeichnis) enthalten.",
            )

        plugin_source_dir = contents[0]
        plugin_name = plugin_source_dir.name
        if not re.fullmatch(r"[a-zA-Z0-9_\-]+", plugin_name):
            raise HTTPException(
                status_code=400, detail="Ungültiger Plugin-Name im ZIP-Root."
            )

        # Sicherheits-Check: Befindet sich __init__.py darin?
        if not (plugin_source_dir / "__init__.py").exists():
            raise HTTPException(
                status_code=400,
                detail="Keine __init__.py im Root-Verzeichnis des Plugins gefunden (Ungültiges Modul).",
            )

        plugin_target_dir = plugins_dir / plugin_name

        # Wenn Plugin schon existiert, ersternfernen
        if plugin_target_dir.exists():
            shutil.rmtree(plugin_target_dir)

        # Modul an den Zielort verschieben
        shutil.move(str(plugin_source_dir), str(plugin_target_dir))

        # 3. Pip Requirements installieren
        success = await install_requirements_if_exist(plugin_target_dir)
        if not success:
            shutil.rmtree(plugin_target_dir)  # Rollback
            raise HTTPException(
                status_code=500,
                detail="Abhängigkeiten (requirements.txt) konnten nicht installiert werden. Details im Log.",
            )

        # 4. Hot-Loading in Memory
        registry = request.app.state.registry
        loaded = await registry.hot_load_plugin(plugin_name, request.app)

        if not loaded:
            raise HTTPException(
                status_code=500,
                detail="Plugin in den Ordner entpackt, aber Import durch ModuleRegistry fehlgeschlagen.",
            )

        now = time.time()
        await _set_plugin_meta(
            plugin_name,
            {
                "source": "upload",
                "repo_id": "",
                "repo_url": "",
                "repo_version": "",
                "installed_at": now,
                "updated_at": now,
            },
        )

        return JSONResponse(
            status_code=201,
            content={
                "message": f"Plugin '{plugin_name}' erfolgreich installiert und geladen.",
                "plugin_name": plugin_name,
            },
        )

    except HTTPException:
        raise
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as e:
        logger.error("Fehler beim Plugin Upload: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Unerwarteter Fehler: {str(e)}")
    finally:
        # Cleanup temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


# ─── Marketplace API ─────────────────────────────────────────────────────────


@router.get("/marketplace/repos")
async def list_repos() -> JSONResponse:
    """Alle konfigurierten Marketplace-Repos (Token maskiert)."""
    repos = await _load_repos()
    return JSONResponse(content={"repos": [_mask_repo(r) for r in repos]})


@router.post("/marketplace/repos")
async def add_repo(request: Request) -> JSONResponse:
    """Neues Repo zur Liste hinzufügen."""
    body = await request.json()
    repo_url = body.get("repo_url", "").strip()
    if not repo_url or not _parse_github_url(repo_url):
        raise HTTPException(
            status_code=400, detail="Ungültige oder fehlende GitHub-URL."
        )
    if not _is_repo_allowed(repo_url):
        raise HTTPException(
            status_code=403, detail="Repository ist nicht in der erlaubten Allowlist."
        )

    repos = await _load_repos()
    new_repo: dict[str, Any] = {
        "id": uuid.uuid4().hex[:10],
        "name": body.get("name", "").strip() or repo_url,
        "repo_url": repo_url,
        "branch": (body.get("branch") or "main").strip(),
        "modules_path": (body.get("modules_path") or "backend/modules_catalog").strip(),
        "github_token": body.get("github_token", "").strip(),
    }
    repos.append(new_repo)
    await _save_repos(repos)
    return JSONResponse(status_code=201, content={"repo": _mask_repo(new_repo)})


@router.put("/marketplace/repos/{repo_id}")
async def update_repo(request: Request, repo_id: str) -> JSONResponse:
    """Repo-Konfiguration aktualisieren."""
    body = await request.json()
    repos = await _load_repos()
    repo = next((r for r in repos if r["id"] == repo_id), None)
    if not repo:
        raise HTTPException(status_code=404, detail="Repo nicht gefunden.")

    if "name" in body and body["name"].strip():
        repo["name"] = body["name"].strip()
    if "repo_url" in body:
        url = body["repo_url"].strip()
        if not _parse_github_url(url):
            raise HTTPException(status_code=400, detail="Ungültige GitHub-URL.")
        if not _is_repo_allowed(url):
            raise HTTPException(
                status_code=403,
                detail="Repository ist nicht in der erlaubten Allowlist.",
            )
        repo["repo_url"] = url
    if "branch" in body:
        repo["branch"] = (body["branch"] or "main").strip()
    if "modules_path" in body:
        repo["modules_path"] = (
            body["modules_path"] or "backend/modules_catalog"
        ).strip()

    token_clear = bool(body.get("github_token_clear"))
    token_value = body.get("github_token", "").strip()
    if token_clear:
        repo["github_token"] = ""
    elif token_value:
        repo["github_token"] = token_value

    await _save_repos(repos)
    return JSONResponse(content={"repo": _mask_repo(repo)})


@router.delete("/marketplace/repos/{repo_id}")
async def delete_repo(repo_id: str) -> JSONResponse:
    """Repo entfernen (Official-Repo kann nicht gelöscht werden)."""
    if repo_id == _OFFICIAL_REPO_ID:
        raise HTTPException(
            status_code=403, detail="Das Official-Repo kann nicht gelöscht werden."
        )
    repos = await _load_repos()
    filtered = [r for r in repos if r["id"] != repo_id]
    if len(filtered) == len(repos):
        raise HTTPException(status_code=404, detail="Repo nicht gefunden.")
    await _save_repos(filtered)
    return JSONResponse(content={"message": "Repo entfernt."})


@router.get("/marketplace/repos/{repo_id}/modules")
async def list_repo_modules(request: Request, repo_id: str) -> JSONResponse:
    """Verfügbare Module aus einem bestimmten Repo (mit Cache, 5 Min)."""
    repos = await _load_repos()
    repo_cfg = next((r for r in repos if r["id"] == repo_id), None)
    if not repo_cfg:
        return JSONResponse(
            content={"modules": [], "updates": [], "error": "Repo nicht gefunden."}
        )

    parsed = _parse_github_url(repo_cfg["repo_url"])
    if not parsed:
        return JSONResponse(
            content={"modules": [], "updates": [], "error": "Ungültige GitHub-URL."}
        )

    registry = request.app.state.registry
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugin_meta = await _load_plugin_meta()

    cache_key = (
        f"{repo_cfg['repo_url']}:{repo_cfg['branch']}:{repo_cfg['modules_path']}"
    )
    cached = _marketplace_cache.get(cache_key)
    if cached and time.time() - cached["ts"] < _get_cache_ttl():
        return JSONResponse(
            content=_build_module_list(
                cached["modules"], registry, plugins_dir, plugin_meta
            )
        )

    owner, repo_name = parsed
    try:
        branch = _validate_branch(repo_cfg.get("branch", "main"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    modules_path = repo_cfg.get("modules_path", "backend/modules_catalog")
    headers = _github_headers(repo_cfg.get("github_token", ""))

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"

            # 1. Try catalog.json via raw.githubusercontent.com — no API rate limit
            catalog_url = f"{raw_base}/{modules_path}/catalog.json"
            cat_resp = await client.get(catalog_url, timeout=10.0)
            if cat_resp.status_code == 200:
                try:
                    all_modules = cat_resp.json().get("modules", [])
                    _marketplace_cache[cache_key] = {
                        "ts": time.time(),
                        "modules": all_modules,
                    }
                    return JSONResponse(
                        content=_build_module_list(
                            all_modules, registry, plugins_dir, plugin_meta
                        )
                    )
                except (
                    RuntimeError,
                    ValueError,
                    TypeError,
                    KeyError,
                    OSError,
                    ImportError,
                    json.JSONDecodeError,
                ):
                    pass  # fall through to API

            # 2. Fallback: GitHub API (subject to rate limit)
            tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
            resp = await client.get(tree_url, headers=headers)
            if resp.status_code == 404:
                return JSONResponse(
                    content={
                        "modules": [],
                        "updates": [],
                        "error": f"Branch '{branch}' oder Repo nicht gefunden.",
                    }
                )
            if resp.status_code == 401:
                return JSONResponse(
                    content={
                        "modules": [],
                        "updates": [],
                        "error": "Zugriff verweigert – Token ungültig.",
                    }
                )
            if resp.status_code == 403:
                if resp.headers.get("X-RateLimit-Remaining") == "0":
                    return JSONResponse(
                        content={
                            "modules": [],
                            "updates": [],
                            "error": "GitHub API Rate Limit erreicht (60 req/h ohne Token). Bitte ein GitHub Token in den Repo-Einstellungen hinterlegen.",
                        }
                    )
                return JSONResponse(
                    content={
                        "modules": [],
                        "updates": [],
                        "error": "GitHub Zugriff verweigert. Bei privaten Repos bitte Token hinterlegen.",
                    }
                )
            resp.raise_for_status()

            tree = resp.json().get("tree", [])
            prefix = modules_path.rstrip("/") + "/"
            dirs = sorted(
                {
                    item["path"][len(prefix) :].split("/")[0]
                    for item in tree
                    if item["path"].startswith(prefix)
                    and item["path"][len(prefix) :].count("/") == 0
                    and item["type"] == "tree"
                    and not item["path"][len(prefix) :].startswith("_")
                }
            )
            all_modules = []

            async def _fetch_manifest(mod_name: str) -> dict[str, str]:
                raw_url = f"{raw_base}/{modules_path}/{mod_name}/manifest.py"
                try:
                    m_resp = await client.get(raw_url, timeout=10.0)
                    if m_resp.status_code == 200:
                        return _extract_manifest_info(m_resp.text)
                except (
                    RuntimeError,
                    ValueError,
                    TypeError,
                    KeyError,
                    OSError,
                    ImportError,
                    json.JSONDecodeError,
                ):
                    pass
                return {
                    "display_name": mod_name,
                    "description": "",
                    "version": "",
                    "author": "",
                }

            manifests = await asyncio.gather(*[_fetch_manifest(n) for n in dirs])
            for mod_name, info in zip(dirs, manifests):
                all_modules.append(
                    {
                        "name": mod_name,
                        "display_name": info.get("display_name") or mod_name,
                        "description": info.get("description") or "",
                        "version": info.get("version") or "",
                        "author": info.get("author") or "",
                    }
                )

            _marketplace_cache[cache_key] = {"ts": time.time(), "modules": all_modules}
            return JSONResponse(
                content=_build_module_list(
                    all_modules, registry, plugins_dir, plugin_meta
                )
            )

    except httpx.TimeoutException:
        return JSONResponse(
            content={"modules": [], "updates": [], "error": "Timeout beim Abruf."}
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as e:
        logger.error("Marketplace fetch Fehler [%s]: %s", repo_id, e, exc_info=True)
        return JSONResponse(
            content={"modules": [], "updates": [], "error": f"Fehler: {e}"}
        )


@router.post("/install-from-repo/{module_name}")
async def install_from_repo(
    request: Request,
    module_name: str,
    repo_id: str = Query(default=_OFFICIAL_REPO_ID),
) -> JSONResponse:
    """Lädt ein Modul aus dem angegebenen Repo herunter und installiert es als Plugin."""
    if not re.fullmatch(r"[a-zA-Z0-9_]+", module_name):
        raise HTTPException(status_code=400, detail="Ungültiger Modulname.")

    repos = await _load_repos()
    repo_cfg = next((r for r in repos if r["id"] == repo_id), None)
    if not repo_cfg:
        raise HTTPException(status_code=404, detail=f"Repo '{repo_id}' nicht gefunden.")

    parsed = _parse_github_url(repo_cfg["repo_url"])
    if not parsed:
        raise HTTPException(
            status_code=400, detail="Ungültige GitHub-URL in der Repo-Konfiguration."
        )
    if not _is_repo_allowed(repo_cfg["repo_url"]):
        raise HTTPException(
            status_code=403, detail="Repository ist nicht in der erlaubten Allowlist."
        )

    owner, repo_name = parsed
    try:
        branch = _validate_branch(repo_cfg.get("branch", "main"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    modules_path = repo_cfg.get("modules_path", "backend/modules_catalog")
    headers = _github_headers(repo_cfg.get("github_token", ""))

    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(mkdtemp())

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Existence check via raw.githubusercontent.com (no API rate limit)
            raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"
            check_resp = await client.get(
                f"{raw_base}/{modules_path}/{module_name}/__init__.py", timeout=10.0
            )
            if check_resp.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Modul '{module_name}' nicht im Repo gefunden.",
                )
            if check_resp.status_code != 200:
                raise HTTPException(
                    status_code=502,
                    detail=f"Zugriff auf Repo fehlgeschlagen (HTTP {check_resp.status_code}).",
                )

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                await _download_dir_to_zip(
                    client,
                    owner,
                    repo_name,
                    f"{modules_path}/{module_name}",
                    branch,
                    headers,
                    zf,
                    module_name,
                )

        zip_path = temp_dir / f"{module_name}.zip"
        zip_path.write_bytes(zip_buffer.getvalue())

        extract_dir = temp_dir / "extracted"
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            members = zip_ref.infolist()
            total_size = sum(m.file_size for m in members)
            if total_size > _MAX_UNCOMPRESSED_SIZE:
                raise HTTPException(
                    status_code=400, detail="Modul zu groß (max. 100 MB)."
                )
            extract_dir_resolved = extract_dir.resolve()
            for member in members:
                if hasattr(member, "is_symlink") and member.is_symlink():
                    raise HTTPException(
                        status_code=400,
                        detail="ZIP-Archiv enthält symbolische Links (nicht erlaubt).",
                    )
                dest_path = (extract_dir / member.filename).resolve()
                if not str(dest_path).startswith(str(extract_dir_resolved)):
                    raise HTTPException(
                        status_code=400,
                        detail="ZIP-Archiv enthält ungültigen Pfad (Path-Traversal verhindert).",
                    )
            zip_ref.extractall(extract_dir)

        contents = list(extract_dir.iterdir())
        if len(contents) != 1 or not contents[0].is_dir():
            raise HTTPException(
                status_code=500, detail="Unerwartete ZIP-Struktur beim Download."
            )

        plugin_source_dir = contents[0]
        if not (plugin_source_dir / "__init__.py").exists():
            raise HTTPException(
                status_code=400, detail="Kein __init__.py im Modul gefunden."
            )

        plugin_target_dir = plugins_dir / module_name
        if plugin_target_dir.exists():
            shutil.rmtree(plugin_target_dir)
        shutil.move(str(plugin_source_dir), str(plugin_target_dir))

        success = await install_requirements_if_exist(plugin_target_dir)
        if not success:
            shutil.rmtree(plugin_target_dir)
            raise HTTPException(
                status_code=500,
                detail="requirements.txt konnte nicht installiert werden.",
            )

        registry = request.app.state.registry
        loaded = await registry.hot_load_plugin(module_name, request.app)
        if not loaded:
            raise HTTPException(
                status_code=500,
                detail="Modul heruntergeladen, aber Import fehlgeschlagen.",
            )

        module_listing = await list_repo_modules(request, repo_id)
        repo_version = ""
        try:
            listing_body = json.loads(module_listing.body.decode("utf-8"))
            merged = (listing_body.get("modules") or []) + (
                listing_body.get("updates") or []
            )
            match = next((m for m in merged if m.get("name") == module_name), None)
            if match:
                repo_version = str(match.get("version", "") or "")
        except (
            RuntimeError,
            ValueError,
            TypeError,
            KeyError,
            OSError,
            ImportError,
            json.JSONDecodeError,
        ):
            repo_version = ""

        now = time.time()
        old_meta = (await _load_plugin_meta()).get(module_name, {})
        await _set_plugin_meta(
            module_name,
            {
                "source": "marketplace",
                "repo_id": repo_id,
                "repo_url": repo_cfg["repo_url"],
                "repo_version": repo_version,
                "installed_at": old_meta.get("installed_at", now),
                "updated_at": now,
            },
        )

        _marketplace_cache.clear()
        return JSONResponse(
            status_code=201,
            content={
                "message": f"Modul '{module_name}' erfolgreich installiert.",
                "module_name": module_name,
                "repo_version": repo_version,
            },
        )

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=408, detail="Timeout beim Download vom Repository."
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as e:
        logger.error(
            "install_from_repo Fehler [%s/%s]: %s",
            repo_id,
            module_name,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail=f"Fehler: {e}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@router.delete("/{plugin_name}")
async def delete_plugin(request: Request, plugin_name: str) -> JSONResponse:
    """
    Deinstalliert ein Plugin vom Dateisystem und entlädt es intern.
    Ein echter Memory-Cleanup erfordert jedoch einen Container-Neustart.
    """
    import re

    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", plugin_name):
        raise HTTPException(status_code=400, detail="Ungültiger Plugin-Name.")
    registry = request.app.state.registry
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    target_dir = plugins_dir / plugin_name

    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(
            status_code=404, detail=f"Plugin '{plugin_name}' existiert nicht."
        )

    try:
        shutil.rmtree(target_dir)
        registry.remove_plugin(plugin_name)
        await _delete_plugin_meta(plugin_name)
        return JSONResponse(
            content={
                "message": f"Plugin '{plugin_name}' deinstalliert. Die Änderungen werden beim nächsten Neustart vollständig aktiv."
            }
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        OSError,
        ImportError,
        json.JSONDecodeError,
    ) as e:
        logger.error("Fehler beim Löschen des Plugins %s: %s", plugin_name, e)
        raise HTTPException(
            status_code=500, detail="Fehler beim Löschen der Plugin-Dateien."
        )


@router.post("/reinstall/{plugin_name}")
async def reinstall_plugin(request: Request, plugin_name: str) -> JSONResponse:
    """
    Re-installiert ein Plugin aus dem ursprünglichen Repository (Update).
    """
    import re

    if not re.fullmatch(r"[a-zA-Z0-9_\-]+", plugin_name):
        raise HTTPException(status_code=400, detail="Ungültiger Plugin-Name.")

    plugin_meta = await _load_plugin_meta()
    meta = plugin_meta.get(plugin_name, {})
    repo_url = meta.get("repo_url", "") or "https://github.com/natorus87/ninko"
    repo_id = meta.get("repo_id", _OFFICIAL_REPO_ID)

    repos = await _load_repos()
    repo_cfg = next(
        (r for r in repos if r.get("id") == repo_id or r.get("repo_url") == repo_url),
        None,
    )
    if not repo_cfg:
        raise HTTPException(
            status_code=404, detail=f"Repository '{repo_id}' nicht gefunden."
        )

    parsed = _parse_github_url(repo_url)
    if not parsed:
        raise HTTPException(status_code=400, detail="Ungültige Repo-URL.")

    owner, repo_name = parsed
    try:
        branch = _validate_branch(repo_cfg.get("branch", "main"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    modules_path = repo_cfg.get("modules_path", "backend/modules_catalog")

    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    plugin_dir = plugins_dir / plugin_name

    if plugin_dir.exists():
        try:
            shutil.rmtree(plugin_dir, ignore_errors=False)
        except Exception as e:
            return JSONResponse(
                content={
                    "detail": f"Plugin '{plugin_name}' konnte nicht gelöscht werden. Bitte PVC bereinigen: kubectl delete pvc backend-data -n ninko (alle Plugin-Daten werden gelöscht)."
                },
                status_code=500,
            )

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            raw_base = f"https://raw.githubusercontent.com/{owner}/{repo_name}/{branch}"
            catalog_url = f"{raw_base}/{modules_path}/{plugin_name}/manifest.py"
            resp = await client.get(catalog_url)
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=404,
                    detail=f"Modul '{plugin_name}' nicht im Repo gefunden.",
                )
            manifest_info = _extract_manifest_info(resp.text)
            repo_version = manifest_info.get("version", "")

            tarball_url = f"https://github.com/{owner}/{repo_name}/archive/refs/heads/{branch}.tar.gz"
            tar_resp = await client.get(
                tarball_url, timeout=60.0, follow_redirects=True
            )
            if tar_resp.status_code != 200:
                raise HTTPException(
                    status_code=404, detail="Konnte Modul nicht herunterladen."
                )

            prefix = f"{modules_path}/{plugin_name}/"
            tar_root = f"{repo_name}-{branch}/"

            extract_dir = Path(mkdtemp())
            with tarfile.open(fileobj=io.BytesIO(tar_resp.content), mode="r:gz") as tar:
                for member in tar.getmembers():
                    if not member.isfile():
                        continue
                    rel_to_root = (
                        member.name[len(tar_root) :]
                        if member.name.startswith(tar_root)
                        else member.name
                    )
                    if not rel_to_root.startswith(prefix):
                        continue
                    rel = rel_to_root[len(prefix) :]
                    if not rel:
                        continue
                    f = tar.extractfile(member)
                    if f is None:
                        continue
                    target_dir = extract_dir / plugin_name
                    target_dir.mkdir(parents=True, exist_ok=True)
                    (target_dir / rel).parent.mkdir(parents=True, exist_ok=True)
                    (target_dir / rel).write_bytes(f.read())

            plugin_source_dir = extract_dir / plugin_name
            if not (plugin_source_dir / "__init__.py").exists():
                raise HTTPException(
                    status_code=400, detail="Kein __init__.py im Modul gefunden."
                )

            if plugin_dir.exists():
                shutil.rmtree(plugin_dir)
            shutil.move(str(plugin_source_dir), str(plugin_dir))

            success = await install_requirements_if_exist(plugin_dir)
            if not success:
                shutil.rmtree(plugin_dir)
                raise HTTPException(
                    status_code=500,
                    detail="requirements.txt konnte nicht installiert werden.",
                )

            registry = request.app.state.registry
            loaded = await registry.hot_load_plugin(plugin_name, request.app)
            if not loaded:
                raise HTTPException(
                    status_code=500,
                    detail="Modul heruntergeladen, aber Import fehlgeschlagen.",
                )

            now = time.time()
            await _set_plugin_meta(
                plugin_name,
                {
                    "source": "marketplace",
                    "repo_id": repo_id,
                    "repo_url": repo_url,
                    "repo_version": repo_version,
                    "installed_at": meta.get("installed_at", now),
                    "updated_at": now,
                },
            )

            _marketplace_cache.clear()

            return JSONResponse(
                content={
                    "message": f"Plugin '{plugin_name}' wurde auf Version {repo_version} aktualisiert."
                }
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Fehler beim Re-Installieren des Plugins %s: %s", plugin_name, e)
        raise HTTPException(status_code=500, detail=f"Update fehlgeschlagen: {e}")
