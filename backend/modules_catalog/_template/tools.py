"""
Template Module — LangGraph @tool functions.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.template.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """
    Helper: loads config and secrets from ConnectionManager.

    Best-practice pattern:
    1. ConnectionManager first (UI connections from Redis + Vault)
    2. Fallback to env vars (e.g. TEMPLATE_URL, TEMPLATE_API_KEY)
    3. ValueError only if nothing is configured
    """
    # ── 1. ConnectionManager ──
    if connection_id:
        conn = await ConnectionManager.get_connection("template", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Template-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Template connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Template avec l'ID '{connection_id}' non trouvée.",
                    es=f"Conexión de Template con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Template con ID '{connection_id}' non trovata.",
                    nl=f"Template-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Template z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Template com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のTemplate接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Template连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("template")

    if conn:
        base_url = conn.config.get("url", "")
        vault = get_vault()
        api_key = None
        api_key_path = conn.vault_keys.get("TEMPLATE_API_KEY")
        if api_key_path:
            api_key = await vault.get_secret(api_key_path)
        return {"base_url": base_url, "api_key": api_key}

    # ── 2. Env-Fallback ──
    base_url = os.environ.get("TEMPLATE_URL", "")
    api_key = os.environ.get("TEMPLATE_API_KEY", "")

    if not base_url:
        raise ValueError(
            _t(
                de=(
                    "Keine Template-Verbindung konfiguriert. "
                    "Bitte im Dashboard unter Einstellungen → Modul → Zahnrad eine Verbindung anlegen, "
                    "oder die Env-Variablen TEMPLATE_URL / TEMPLATE_API_KEY setzen."
                ),
                en=(
                    "No Template connection configured. "
                    "Please create a connection in Settings → Module → Gear, "
                    "or set the env vars TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
                fr=(
                    "Aucune connexion Template configurée. "
                    "Veuillez créer une connexion dans Paramètres → Module → Engrenage, "
                    "ou définir les variables d'environnement TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
                es=(
                    "No hay conexión de Template configurada. "
                    "Por favor cree una conexión en Configuración → Módulo → Engranaje, "
                    "o establezca las variables de entorno TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
                it=(
                    "Nessuna connessione Template configurata. "
                    "Per favore crea una connessione in Impostazioni → Modulo → Ingranaggio, "
                    "o imposta le variabili di ambiente TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
                nl=(
                    "Geen Template-verbinding geconfigureerd. "
                    "Maak een verbinding aan in Instellingen → Module → Tandwiel, "
                    "of stel de omgevingsvariabelen TEMPLATE_URL / TEMPLATE_API_KEY in."
                ),
                pl=(
                    "Nie skonfigurowano połączenia Template. "
                    "Utwórz połączenie w panelu w sekcji Ustawienia → Moduł → Ikona koła zębatego "
                    "lub ustaw zmienne środowiskowe TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
                pt=(
                    "Nenhuma conexão Template configurada. "
                    "Por favor crie uma conexão em Configurações → Módulo → Engrenagem, "
                    "ou defina as variáveis de ambiente TEMPLATE_URL / TEMPLATE_API_KEY."
                ),
                ja=(
                    "Template接続が設定されていません。 "
                    "ダッシュボードで設定→モジュール→歯車から接続を作成するか、"
                    "環境変数TEMPLATE_URL / TEMPLATE_API_KEYを設定してください。"
                ),
                zh=(
                    "未配置Template连接。 "
                    "请在设置→模块→齿轮下创建连接，"
                    "或设置环境变量TEMPLATE_URL / TEMPLATE_API_KEY。"
                ),
            )
        )

    return {"base_url": base_url, "api_key": api_key}


# ═══════════════════════════════════════════════════════
# Agent Tools (exposed to LLM)
# IMPORTANT: Keep docstrings precise (LLM uses them for tool selection).
# Register read-only tools in safeguard._TOOL_READONLY.
# ═══════════════════════════════════════════════════════


@tool
async def beispiel_tool(parameter: str, connection_id: str = "") -> str:
    """
    Run a simple example operation against the API.
    Use this tool when the user asks for an example or a test.
    """
    try:
        client = await _get_api_client(connection_id)
        logger.info("beispiel_tool called with parameter=%s", parameter)
        return (
            "Example tool executed successfully with parameter "
            f"'{parameter}' (source: {client['base_url']})."
        )
    except ValueError as e:
        logger.error("beispiel_tool failed: %s", e)
        return _t(
            de="Anfrage fehlgeschlagen. Prüfe die Verbindungskonfiguration.",
            en="Request failed. Check connection configuration.",
            fr="La requête a échoué. Vérifiez la configuration de la connexion.",
            es="Solicitud fallida. Verifique la configuración de conexión.",
            it="Richiesta non riuscita. Controlla la configurazione della connessione.",
            nl="Verzoek mislukt. Controleer de verbindingsconfiguratie.",
            pl="Żądanie nie powiodło się. Sprawdź konfigurację połączenia.",
            pt="Solicitação falhou. Verifique a configuração da conexão.",
            ja="リクエストが失敗しました。接続設定を確認してください。",
            zh="请求失败。请检查连接配置。",
        )


@tool
async def lade_daten(connection_id: str = "") -> dict:
    """
    Load sample data from the API.
    Use this when the user asks for data analysis or reports.
    """
    try:
        client = await _get_api_client(connection_id)
        logger.info("lade_daten called")
        return {
            "status": "success",
            "items": [1, 2, 3],
            "source": client["base_url"],
        }
    except ValueError as e:
        logger.error("lade_daten failed: %s", e)
        return {"error": "Request failed. Check connection configuration."}
