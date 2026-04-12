"""
Template Module — LangGraph @tool functions.

Dieses Template zeigt das empfohlene Muster für neue Ninko-Module:

  ToolResponse   – einheitliches Return-Format {success, data, error, meta}
  ToolParams     – Pydantic-Basis für Parameter-Validierung
  ToolError      – Exception für kontrollierte Fehler (kein Stack-Trace)

Kurzreferenz:
  ToolResponse.ok(data, **meta)  → success=True,  LLM sieht data als String
  ToolResponse.fail("msg")       → success=False, LLM sieht "Error: msg"
  raise ToolError("msg")         → early-exit ohne Stack-Trace-Logging

Error-Codes (Konvention):
  ERR_NOT_CONFIGURED  – keine Verbindung hinterlegt
  ERR_NOT_FOUND       – angefordertes Objekt existiert nicht
  ERR_PERMISSION      – API antwortet mit 401/403
  ERR_TIMEOUT         – Anfrage hat Timeout überschritten
  ERR_INVALID_INPUT   – Parameterwert ungültig (Validation)
"""

from __future__ import annotations

import logging
import os

from langchain_core.tools import tool
from pydantic import Field

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.tool_schema import ToolError, ToolParams, ToolResponse
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.template.tools")

# Optional: registriert Default-Metadaten automatisch für neue Module.
# Die Registry liest diese Literale direkt aus tools.py, ohne das Modul zu importieren.
TOOL_REGISTRY_DEFAULTS = {
    "required_bins": (),
    "required_envs": (),
}

TOOL_REGISTRY_OVERRIDES = {
    "beispiel_tool": {"readonly": True},
    "lade_daten": {"readonly": True},
}

# ── Error-Code-Konstanten ──────────────────────────────────────────────────────
ERR_NOT_CONFIGURED = "ERR_NOT_CONFIGURED"
ERR_NOT_FOUND = "ERR_NOT_FOUND"
ERR_PERMISSION = "ERR_PERMISSION"
ERR_TIMEOUT = "ERR_TIMEOUT"
ERR_INVALID_INPUT = "ERR_INVALID_INPUT"


# ── Parameter-Schemas (Pydantic) ───────────────────────────────────────────────
# Erbe von ToolParams für connection_id + str_strip_whitespace + extra="forbid".

class BeispielParams(ToolParams):
    """Parameter für beispiel_tool."""
    parameter: str = Field(..., min_length=1, description="Der Eingabewert")


class LadeDatenParams(ToolParams):
    """Parameter für lade_daten."""
    limit: int = Field(default=50, ge=1, le=500, description="Max. Anzahl Einträge")
    status: str = Field(default="active", description="Filter: active | archived | all")


async def _get_api_client(connection_id: str = "") -> dict:
    """
    Helper: loads config and secrets from ConnectionManager.

    Best-practice pattern:
    1. ConnectionManager first (UI connections from Redis + Vault)
    2. Fallback to env vars (e.g. TEMPLATE_URL, TEMPLATE_API_KEY)
    3. ValueError only if nothing is configured
    """
    # REQUIRED: replace module id "template" and key names "TEMPLATE_*" in copied modules.
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
# Tool-Metadaten optional direkt hier definieren:
# TOOL_REGISTRY_DEFAULTS / TOOL_REGISTRY_OVERRIDES
# ═══════════════════════════════════════════════════════


@tool
async def beispiel_tool(parameter: str, connection_id: str = "") -> str:
    """
    Run a simple example operation against the API.
    Use this tool when the user asks for an example or a test.

    Args:
        parameter: The input value to process (required, non-empty).
        connection_id: Optional connection ID (uses default if omitted).
    """
    # Optional: Parameter über ToolParams validieren
    try:
        params = BeispielParams(parameter=parameter, connection_id=connection_id)
    except Exception as e:
        return str(ToolResponse.fail(f"{ERR_INVALID_INPUT}: {e}"))

    try:
        client = await _get_api_client(params.connection_id)
        logger.info("beispiel_tool called with parameter=%s", params.parameter)
        result = f"Example tool executed with parameter '{params.parameter}' (source: {client['base_url']})."
        return str(ToolResponse.ok(result))
    except ToolError as e:
        return str(ToolResponse.fail(str(e)))
    except ValueError as e:
        logger.error("beispiel_tool failed: %s", e)
        return str(ToolResponse.fail(
            _t(
                de=f"{ERR_NOT_CONFIGURED}: Prüfe die Verbindungskonfiguration.",
                en=f"{ERR_NOT_CONFIGURED}: Check connection configuration.",
                fr=f"{ERR_NOT_CONFIGURED}: Vérifiez la configuration de la connexion.",
                es=f"{ERR_NOT_CONFIGURED}: Verifique la configuración de conexión.",
                it=f"{ERR_NOT_CONFIGURED}: Controlla la configurazione della connessione.",
                nl=f"{ERR_NOT_CONFIGURED}: Controleer de verbindingsconfiguratie.",
                pl=f"{ERR_NOT_CONFIGURED}: Sprawdź konfigurację połączenia.",
                pt=f"{ERR_NOT_CONFIGURED}: Verifique a configuração da conexão.",
                ja=f"{ERR_NOT_CONFIGURED}: 接続設定を確認してください。",
                zh=f"{ERR_NOT_CONFIGURED}: 请检查连接配置。",
            )
        ))


@tool
async def lade_daten(limit: int = 50, status: str = "active", connection_id: str = "") -> str:
    """
    Load items from the API with optional filters.
    Use this when the user asks for data, lists, or reports.

    Args:
        limit: Maximum number of items to return (1–500, default 50).
        status: Filter by status — active | archived | all.
        connection_id: Optional connection ID (uses default if omitted).
    """
    try:
        params = LadeDatenParams(limit=limit, status=status, connection_id=connection_id)
    except Exception as e:
        return str(ToolResponse.fail(f"{ERR_INVALID_INPUT}: {e}"))

    try:
        client = await _get_api_client(params.connection_id)
        logger.info("lade_daten called limit=%d status=%s", params.limit, params.status)

        # Beispiel-Ergebnis mit meta-Feldern (count, source)
        items = list(range(1, params.limit + 1))[:3]  # Platzhalter
        return str(ToolResponse.ok(
            {"items": items, "status_filter": params.status, "source": client["base_url"]},
            count=len(items),
            limit=params.limit,
        ))
    except ToolError as e:
        return str(ToolResponse.fail(str(e)))
    except ValueError as e:
        logger.error("lade_daten failed: %s", e)
        return str(ToolResponse.fail(f"{ERR_NOT_CONFIGURED}: {e}"))
