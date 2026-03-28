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
import time
import uuid
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
_CACHE_TTL = 300  # 5 Minuten


# ─── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _parse_github_url(url: str) -> tuple[str, str] | None:
    """Extrahiert (owner, repo) aus einer GitHub-URL."""
    m = re.search(r'github\.com[:/]([^/]+)/([^/.\s]+?)(?:\.git)?\s*$', url.strip())
    return (m.group(1), m.group(2)) if m else None


def _version_tuple(v: str) -> tuple[int, ...]:
    try:
        return tuple(int(x) for x in v.strip().lstrip("v").split("."))
    except Exception:
        return (0,)


def _extract_manifest_info(content: str) -> dict[str, str]:
    """Extrahiert key-Felder aus einer manifest.py per Regex."""
    def get(field: str) -> str:
        match = re.search(rf'{field}\s*=\s*["\']([^"\']+)["\']', content)
        return match.group(1) if match else ""
    return {
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


async def _load_repos() -> list[dict[str, Any]]:
    """Lädt die Repo-Liste aus Redis. Gibt Default zurück wenn leer."""
    redis = get_redis()
    raw = await redis.connection.get(_REDIS_REPOS_KEY)
    if raw:
        repos = json.loads(raw)
        if repos:
            return repos
    return list(_DEFAULT_REPOS)


async def _save_repos(repos: list[dict[str, Any]]) -> None:
    redis = get_redis()
    await redis.connection.set(_REDIS_REPOS_KEY, json.dumps(repos))
    _marketplace_cache.clear()


def _mask_repo(repo: dict[str, Any]) -> dict[str, Any]:
    """Gibt Repo-Dict ohne Token zurück, aber mit token_set-Flag."""
    return {k: v for k, v in repo.items() if k != "github_token"} | {
        "github_token_set": bool(repo.get("github_token"))
    }


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
    """Lädt ein GitHub-Verzeichnis rekursiv in ein ZIP herunter."""
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}?ref={branch}"
    resp = await client.get(url, headers=headers)
    resp.raise_for_status()
    for item in resp.json():
        if item["type"] == "file":
            file_resp = await client.get(item["download_url"])
            file_resp.raise_for_status()
            zf.writestr(f"{zip_prefix}/{item['name']}", file_resp.content)
        elif item["type"] == "dir":
            await _download_dir_to_zip(
                client, owner, repo, item["path"], branch, headers,
                zf, f"{zip_prefix}/{item['name']}"
            )


def _build_module_list(
    all_modules: list[dict[str, str]],
    registry: Any,
    plugins_dir: Path,
) -> dict[str, Any]:
    """Teilt Repo-Module in: nicht installiert vs. installiertes Plugin (mit Update-Info)."""
    installed_map: dict[str, str] = {m.name: m.version for m in registry.list_all_modules()}
    new_modules: list[dict[str, Any]] = []
    updates: list[dict[str, Any]] = []

    for mod in all_modules:
        name = mod["name"]
        repo_version = mod.get("version", "")
        if name not in installed_map:
            new_modules.append(mod)
        elif (plugins_dir / name).is_dir():
            installed_version = installed_map[name]
            updates.append({
                **mod,
                "installed_version": installed_version,
                "update_available": _version_tuple(repo_version) > _version_tuple(installed_version),
            })
    return {"modules": new_modules, "updates": updates}

_MAX_UNCOMPRESSED_SIZE = 100 * 1024 * 1024  # 100 MB
_DANGEROUS_REQ_PATTERNS = (
    "--index-url", "--extra-index-url", "-e git+", "-e svn+", "-e hg+",
    "file://", "--trusted-host", "--find-links",
)


async def install_requirements_if_exist(plugin_dir: Path) -> bool:
    """Sucht nach einer requirements.txt im Plugin und führt ggf. pip install aus."""
    req_file = plugin_dir / "requirements.txt"
    if not req_file.is_file():
        return True

    # Validate requirements.txt for dangerous patterns
    req_content = req_file.read_text(encoding="utf-8", errors="replace")
    for pattern in _DANGEROUS_REQ_PATTERNS:
        if pattern in req_content:
            logger.error("requirements.txt enthält unerlaubtes Muster: %s", pattern)
            return False

    logger.info("Installiere Abhängigkeiten für Plugin aus: %s", req_file)
    try:
        proc = await asyncio.create_subprocess_exec(
            "pip", "install", "-r", str(req_file),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error("pip install fehlgeschlagen:\n%s", stderr.decode())
            return False
            
        logger.info("Abhängigkeiten erfolgreich installiert:\n%s", stdout.decode())
        return True
    except Exception as e:
        logger.error("Ausnahme bei der Installation der Abhängigkeiten: %s", e)
        return False

@router.post("/upload")
async def upload_plugin(request: Request, file: UploadFile = File(...)) -> JSONResponse:
    """
    Nimmt ein ZIP-Archiv entgegen, entpackt es unter `backend/plugins/<name>` 
    und lädt es per Hot-Load in den Speicher.
    """
    if not file.filename or not file.filename.endswith(".zip"):
        raise HTTPException(status_code=400, detail="Es muss eine ZIP-Datei hochgeladen werden.")
        
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
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            members = zip_ref.infolist()
            total_size = sum(m.file_size for m in members)
            if total_size > _MAX_UNCOMPRESSED_SIZE:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP-Archiv zu groß: {total_size // (1024*1024)} MB (max. 100 MB unkomprimiert).",
                )
            for member in members:
                if member.is_symlink():
                    raise HTTPException(
                        status_code=400,
                        detail="ZIP-Archiv enthält symbolische Links (nicht erlaubt).",
                    )
                if ".." in member.filename or member.filename.startswith("/"):
                    raise HTTPException(
                        status_code=400,
                        detail=f"ZIP-Archiv enthält ungültigen Pfad: {member.filename}",
                    )
            zip_ref.extractall(extract_dir)
            
        # Wir erwarten, dass im ZIP genau EINER Ordner liegt (das Plugin-Package, z.B. 'mein_plugin')
        contents = list(extract_dir.iterdir())
        if len(contents) != 1 or not contents[0].is_dir():
            raise HTTPException(status_code=400, detail="Das ZIP-Archiv muss exakt EINEN Root-Ordner (das Plugin-Verzeichnis) enthalten.")
            
        plugin_source_dir = contents[0]
        plugin_name = plugin_source_dir.name
        
        # Sicherheits-Check: Befindet sich __init__.py darin?
        if not (plugin_source_dir / "__init__.py").exists():
            raise HTTPException(status_code=400, detail="Keine __init__.py im Root-Verzeichnis des Plugins gefunden (Ungültiges Modul).")
            
        plugin_target_dir = plugins_dir / plugin_name
        
        # Wenn Plugin schon existiert, ersternfernen
        if plugin_target_dir.exists():
            shutil.rmtree(plugin_target_dir)
            
        # Modul an den Zielort verschieben
        shutil.move(str(plugin_source_dir), str(plugin_target_dir))
        
        # 3. Pip Requirements installieren
        success = await install_requirements_if_exist(plugin_target_dir)
        if not success:
            shutil.rmtree(plugin_target_dir) # Rollback
            raise HTTPException(status_code=500, detail="Abhängigkeiten (requirements.txt) konnten nicht installiert werden. Details im Log.")
            
        # 4. Hot-Loading in Memory
        registry = request.app.state.registry
        loaded = await registry.hot_load_plugin(plugin_name, request.app)
        
        if not loaded:
            raise HTTPException(status_code=500, detail="Plugin in den Ordner entpackt, aber Import durch ModuleRegistry fehlgeschlagen.")
            
        return JSONResponse(status_code=201, content={"message": f"Plugin '{plugin_name}' erfolgreich installiert und geladen.", "plugin_name": plugin_name})
        
    except HTTPException:
        raise
    except Exception as e:
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
        raise HTTPException(status_code=400, detail="Ungültige oder fehlende GitHub-URL.")

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
        repo["repo_url"] = url
    if "branch" in body:
        repo["branch"] = (body["branch"] or "main").strip()
    if "modules_path" in body:
        repo["modules_path"] = (body["modules_path"] or "backend/modules_catalog").strip()

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
        raise HTTPException(status_code=403, detail="Das Official-Repo kann nicht gelöscht werden.")
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
        return JSONResponse(content={"modules": [], "updates": [], "error": "Repo nicht gefunden."})

    parsed = _parse_github_url(repo_cfg["repo_url"])
    if not parsed:
        return JSONResponse(content={"modules": [], "updates": [], "error": "Ungültige GitHub-URL."})

    registry = request.app.state.registry
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"

    cache_key = f"{repo_cfg['repo_url']}:{repo_cfg['branch']}:{repo_cfg['modules_path']}"
    cached = _marketplace_cache.get(cache_key)
    if cached and time.time() - cached["ts"] < _CACHE_TTL:
        return JSONResponse(content=_build_module_list(cached["modules"], registry, plugins_dir))

    owner, repo_name = parsed
    branch = repo_cfg.get("branch", "main")
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
                    _marketplace_cache[cache_key] = {"ts": time.time(), "modules": all_modules}
                    return JSONResponse(content=_build_module_list(all_modules, registry, plugins_dir))
                except Exception:
                    pass  # fall through to API

            # 2. Fallback: GitHub API (subject to rate limit)
            tree_url = f"https://api.github.com/repos/{owner}/{repo_name}/git/trees/{branch}?recursive=1"
            resp = await client.get(tree_url, headers=headers)
            if resp.status_code == 404:
                return JSONResponse(content={"modules": [], "updates": [], "error": f"Branch '{branch}' oder Repo nicht gefunden."})
            if resp.status_code == 401:
                return JSONResponse(content={"modules": [], "updates": [], "error": "Zugriff verweigert – Token ungültig."})
            if resp.status_code == 403:
                if resp.headers.get("X-RateLimit-Remaining") == "0":
                    return JSONResponse(content={"modules": [], "updates": [], "error": "GitHub API Rate Limit erreicht (60 req/h ohne Token). Bitte ein GitHub Token in den Repo-Einstellungen hinterlegen."})
                return JSONResponse(content={"modules": [], "updates": [], "error": "GitHub Zugriff verweigert. Bei privaten Repos bitte Token hinterlegen."})
            resp.raise_for_status()

            tree = resp.json().get("tree", [])
            prefix = modules_path.rstrip("/") + "/"
            dirs = sorted({
                item["path"][len(prefix):].split("/")[0]
                for item in tree
                if item["path"].startswith(prefix)
                and item["path"][len(prefix):].count("/") == 0
                and item["type"] == "tree"
                and not item["path"][len(prefix):].startswith("_")
            })
            all_modules = []

            async def _fetch_manifest(mod_name: str) -> dict[str, str]:
                raw_url = f"{raw_base}/{modules_path}/{mod_name}/manifest.py"
                try:
                    m_resp = await client.get(raw_url, timeout=10.0)
                    if m_resp.status_code == 200:
                        return _extract_manifest_info(m_resp.text)
                except Exception:
                    pass
                return {"display_name": mod_name, "description": "", "version": "", "author": ""}

            manifests = await asyncio.gather(*[_fetch_manifest(n) for n in dirs])
            for mod_name, info in zip(dirs, manifests):
                all_modules.append({
                    "name": mod_name,
                    "display_name": info.get("display_name") or mod_name,
                    "description": info.get("description") or "",
                    "version": info.get("version") or "",
                    "author": info.get("author") or "",
                })

            _marketplace_cache[cache_key] = {"ts": time.time(), "modules": all_modules}
            return JSONResponse(content=_build_module_list(all_modules, registry, plugins_dir))

    except httpx.TimeoutException:
        return JSONResponse(content={"modules": [], "updates": [], "error": "Timeout beim Abruf."})
    except Exception as e:
        logger.error("Marketplace fetch Fehler [%s]: %s", repo_id, e, exc_info=True)
        return JSONResponse(content={"modules": [], "updates": [], "error": f"Fehler: {e}"})


@router.post("/install-from-repo/{module_name}")
async def install_from_repo(
    request: Request,
    module_name: str,
    repo_id: str = Query(default=_OFFICIAL_REPO_ID),
) -> JSONResponse:
    """Lädt ein Modul aus dem angegebenen Repo herunter und installiert es als Plugin."""
    if not re.fullmatch(r'[a-zA-Z0-9_]+', module_name):
        raise HTTPException(status_code=400, detail="Ungültiger Modulname.")

    repos = await _load_repos()
    repo_cfg = next((r for r in repos if r["id"] == repo_id), None)
    if not repo_cfg:
        raise HTTPException(status_code=404, detail=f"Repo '{repo_id}' nicht gefunden.")

    parsed = _parse_github_url(repo_cfg["repo_url"])
    if not parsed:
        raise HTTPException(status_code=400, detail="Ungültige GitHub-URL in der Repo-Konfiguration.")

    owner, repo_name = parsed
    branch = repo_cfg.get("branch", "main")
    modules_path = repo_cfg.get("modules_path", "backend/modules_catalog")
    headers = _github_headers(repo_cfg.get("github_token", ""))

    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = Path(mkdtemp())

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            check_url = (
                f"https://api.github.com/repos/{owner}/{repo_name}/contents/"
                f"{modules_path}/{module_name}?ref={branch}"
            )
            check_resp = await client.get(check_url, headers=headers)
            if check_resp.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Modul '{module_name}' nicht im Repo gefunden.")
            check_resp.raise_for_status()

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                await _download_dir_to_zip(
                    client, owner, repo_name,
                    f"{modules_path}/{module_name}",
                    branch, headers, zf, module_name,
                )

        zip_path = temp_dir / f"{module_name}.zip"
        zip_path.write_bytes(zip_buffer.getvalue())

        extract_dir = temp_dir / "extracted"
        with zipfile.ZipFile(zip_path, "r") as zip_ref:
            total_size = sum(m.file_size for m in zip_ref.infolist())
            if total_size > _MAX_UNCOMPRESSED_SIZE:
                raise HTTPException(status_code=400, detail="Modul zu groß (max. 100 MB).")
            zip_ref.extractall(extract_dir)

        contents = list(extract_dir.iterdir())
        if len(contents) != 1 or not contents[0].is_dir():
            raise HTTPException(status_code=500, detail="Unerwartete ZIP-Struktur beim Download.")

        plugin_source_dir = contents[0]
        if not (plugin_source_dir / "__init__.py").exists():
            raise HTTPException(status_code=400, detail="Kein __init__.py im Modul gefunden.")

        plugin_target_dir = plugins_dir / module_name
        if plugin_target_dir.exists():
            shutil.rmtree(plugin_target_dir)
        shutil.move(str(plugin_source_dir), str(plugin_target_dir))

        success = await install_requirements_if_exist(plugin_target_dir)
        if not success:
            shutil.rmtree(plugin_target_dir)
            raise HTTPException(status_code=500, detail="requirements.txt konnte nicht installiert werden.")

        registry = request.app.state.registry
        loaded = await registry.hot_load_plugin(module_name, request.app)
        if not loaded:
            raise HTTPException(status_code=500, detail="Modul heruntergeladen, aber Import fehlgeschlagen.")

        _marketplace_cache.clear()
        return JSONResponse(status_code=201, content={
            "message": f"Modul '{module_name}' erfolgreich installiert.",
            "module_name": module_name,
        })

    except HTTPException:
        raise
    except httpx.TimeoutException:
        raise HTTPException(status_code=408, detail="Timeout beim Download vom Repository.")
    except Exception as e:
        logger.error("install_from_repo Fehler [%s/%s]: %s", repo_id, module_name, e, exc_info=True)
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
    if not re.fullmatch(r'[a-zA-Z0-9_\-]+', plugin_name):
        raise HTTPException(status_code=400, detail="Ungültiger Plugin-Name.")
    registry = request.app.state.registry
    plugins_dir = Path(__file__).resolve().parent.parent / "plugins"
    target_dir = plugins_dir / plugin_name
    
    if not target_dir.exists() or not target_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Plugin '{plugin_name}' existiert nicht.")
        
    try:
        shutil.rmtree(target_dir)
        registry.remove_plugin(plugin_name)
        return JSONResponse(content={"message": f"Plugin '{plugin_name}' deinstalliert. Die Änderungen werden beim nächsten Neustart vollständig aktiv."})
    except Exception as e:
        logger.error("Fehler beim Löschen des Plugins %s: %s", plugin_name, e)
        raise HTTPException(status_code=500, detail="Fehler beim Löschen der Plugin-Dateien.")
