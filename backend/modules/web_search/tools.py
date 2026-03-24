"""
Web Search Modul – Tools für SearXNG.
"""

import os
import httpx
import logging
from typing import List, Dict, Any
from langchain.tools import tool

logger = logging.getLogger("kumio.modules.web_search")

@tool
async def perform_web_search(query: str, connection_id: str = "") -> List[Dict[str, Any]]:
    """
    Führt eine Websuche über SearXNG aus.
    Verwende diese Funktion, wenn der Benutzer nach aktuellen Informationen im Internet sucht.
    Gibt eine Liste von Suchergebnissen (Titel, URL, Inhalt) zurück.
    """
    # Lese SEARXNG_URL aus Environment (wird in docker-compose.yml gesetzt). 
    # Fallback für lokale Entwicklung außerhalb Docker.
    searxng_url = os.getenv("SEARXNG_URL", "http://localhost:8080").rstrip("/")
    search_endpoint = f"{searxng_url}/search"
    
    logger.info(f"Führe Web-Suche durch: '{query}' via {search_endpoint}")
    
    params = {
        "q": query,
        "format": "json"
    }
    
    headers = {
        "X-Forwarded-For": "127.0.0.1",
        "X-Real-IP": "127.0.0.1",
        "Host": "localhost"
    }
    
    try:
        async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
            response = await client.get(search_endpoint, params=params)
            response.raise_for_status()
            
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                logger.warning(f"Keine Suchergebnisse gefunden für Query: {query}")
                return [{"title": "Web Search", "url": "", "content": "Keine Ergebnisse gefunden."}]
                
            formatted_results = []
            # Gebe maximal die Top 5 Ergebnisse zurück, um den Kontext nicht zu sprengen
            for result in results[:5]:
                formatted_results.append({
                    "title": result.get("title", ""),
                    "url": result.get("url", ""),
                    "content": result.get("content", "")
                })
                
            return formatted_results
            
    except httpx.TimeoutException:
        logger.error(f"Timeout bei Web-Suche nach '{query}'")
        return [{"title": "Error", "url": "", "content": "Zeitüberschreitung bei der Kommunikation mit dem Such-Backend (SearXNG)."}]
    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP Fehler bei Web-Suche: {e.response.status_code} - {e.response.text}")
        return [{"title": "Error", "url": "", "content": f"Such-Backend meldete einen HTTP Fehler: {e.response.status_code}."}]
    except Exception as e:
        logger.exception("Unerwarteter Fehler bei der Web-Suche")
        return [{"title": "Error", "url": "", "content": f"Interner Fehler bei der Web-Suche: {e}"}]
