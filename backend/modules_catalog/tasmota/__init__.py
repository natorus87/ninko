"""Tasmota Modul – Package Init."""

from .manifest import module_manifest
from .agent import TasmotaAgent
from .routes import router

agent = TasmotaAgent()

__all__ = ["module_manifest", "agent", "router"]
