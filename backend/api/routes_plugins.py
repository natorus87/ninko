"""
Ninko Plugin API – Dynamische Installation und Deinstallation von Modulen (ZIP).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import zipfile
from pathlib import Path
from tempfile import mkdtemp

from fastapi import APIRouter, Request, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger("ninko.api.plugins")
router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

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
