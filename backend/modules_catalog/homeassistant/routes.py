from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any
import httpx

from .tools import _get_api_client

router = APIRouter()

class ActionRequest(BaseModel):
    action_type: str
    connection_id: str = ""

@router.get("/status")
async def get_homeassistant_status(connection_id: str = "") -> Dict[str, Any]:
    """
    REST endpoint for the UI frontend.
    Returns current statistics or states.
    """
    try:
        client_config = await _get_api_client(connection_id)
        url = f"{client_config['base_url']}/api/config"
        
        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=client_config["headers"], timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
            return {
                "connected": True,
                "url": client_config["base_url"],
                "version": data.get("version"),
                "location_name": data.get("location_name")
            }
    except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
        raise HTTPException(status_code=500, detail=str(exc))

@router.post("/action")
async def trigger_action(req: ActionRequest) -> object:
    """
    REST endpoint for frontend buttons.
    """
    if req.action_type == "test":
        return {"message": "Test action successful from Home Assistant!"}
        
    if req.action_type == "fetch_lights":
        try:
            client_config = await _get_api_client(req.connection_id)
            url = f"{client_config['base_url']}/api/states"
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=client_config["headers"], timeout=10.0)
                response.raise_for_status()
                data = response.json()
                
                # Filter logic for lights
                lights = [item for item in data if item.get("entity_id", "").startswith("light.")]
                return {"message": f"Data fetched successfully. {len(lights)} lights found.", "lights": lights[:10]}
        except (RuntimeError, ValueError, TypeError, KeyError, OSError, ImportError) as exc:
             raise HTTPException(status_code=500, detail=str(exc))

    return {"message": "Unknown action"}
