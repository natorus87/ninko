"""
Licium module — Pydantic schemas für API-Requests und -Responses.
"""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class LiciumNote(BaseModel):
    id: str
    title: str
    type: str  # "note" | "folder"
    parent_id: Optional[str] = None
    content_markdown: Optional[str] = None
    position: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    children: Optional[list["LiciumNote"]] = None


class LiciumSearchResult(BaseModel):
    note_id: str
    chunk_content: str
    similarity: Optional[float] = None
    title: Optional[str] = None


class WikiMeta(BaseModel):
    root_folder_id: Optional[str] = None
    meta_folder_id: Optional[str] = None
    sources_folder_id: Optional[str] = None
    wiki_folder_id: Optional[str] = None
    queries_folder_id: Optional[str] = None
    index_note_id: Optional[str] = None
    log_note_id: Optional[str] = None
    initialized: bool = False


class IngestRequest(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source_url: Optional[str] = None
    connection_id: str = ""


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1)
    connection_id: str = ""
