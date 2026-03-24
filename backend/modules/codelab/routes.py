"""
CodeLab Modul – FastAPI Router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage

from modules.codelab.schemas import ExecuteRequest, ImproveTextRequest
from modules.codelab.tools import execute_code, get_available_languages

logger = logging.getLogger("ninko.modules.codelab.routes")
router = APIRouter()


def _error(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": str(msg)}, status_code=status)


@router.post("/execute")
async def run_code(req: ExecuteRequest):
    """Führt Code in der Sandbox aus."""
    try:
        result = await execute_code.ainvoke({
            "code": req.code,
            "language": req.language,
            "timeout": req.timeout,
        })
        return result
    except Exception as e:
        logger.exception("Fehler bei Code-Ausführung")
        return _error(str(e), 500)


@router.get("/languages")
async def languages():
    """Gibt verfügbare Sprachen in der Sandbox zurück."""
    try:
        return get_available_languages.invoke({})
    except Exception as e:
        return _error(str(e), 500)


_STYLE_LABELS: dict[str, str] = {
    "klar":      "klarer und präziser",
    "formal":    "formal und professionell",
    "informell": "informell und locker",
    "technisch": "technisch präzise",
    "einfach":   "in einfacher Sprache",
    "kurz":      "kürzer und zusammengefasst",
}


@router.post("/improve-text")
async def improve_text(req: ImproveTextRequest):
    """Verbessert Text per LLM – direkt ohne Chat-Umweg."""
    from core.llm_factory import get_llm

    style_label = _STYLE_LABELS.get(req.style, req.style)
    prompt = (
        f"Formuliere den folgenden Text {style_label} um. "
        f"Gib nur den verbesserten Text zurück, ohne Erklärungen oder Kommentare:\n\n{req.text}"
    )
    try:
        llm = get_llm()
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return {"result": response.content, "error": ""}
    except Exception as e:
        logger.exception("Fehler bei Textverbesserung")
        return _error(str(e), 500)
