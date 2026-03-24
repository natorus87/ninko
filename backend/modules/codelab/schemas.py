"""
CodeLab Modul – Pydantic Schemas.
"""

from __future__ import annotations

from pydantic import BaseModel


class ExecuteRequest(BaseModel):
    code: str
    language: str = "python"
    timeout: int = 15


class ExecuteResult(BaseModel):
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0
    duration_ms: float = 0.0
    language: str = ""
    error: str = ""


class ImproveTextRequest(BaseModel):
    text: str
    style: str = "klar"


class ImproveTextResult(BaseModel):
    result: str = ""
    error: str = ""
