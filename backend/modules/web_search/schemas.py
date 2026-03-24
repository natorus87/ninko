"""
Web Search Modul – Pydantic Schemas.
"""

from pydantic import BaseModel, Field

class SearchResultModel(BaseModel):
    title: str = Field(description="Suchergebnis Titel")
    url: str = Field(description="URL des Ergebnisses")
    content: str = Field(description="Zusammenfassung oder Inhalt des Suchergebnisses")
