"""Zabbix module exports."""

from modules_catalog.zabbix.manifest import module_manifest
from modules_catalog.zabbix.agent import agent
from modules_catalog.zabbix.routes import router

__all__ = ["module_manifest", "agent", "router"]
