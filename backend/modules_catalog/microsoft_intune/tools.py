"""
Microsoft Intune Module — LangGraph @tool functions.
Microsoft Intune MDM via Microsoft Graph API.
"""

from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp
from langchain_core.tools import tool

from agents.base_agent import _t
from core.connections import ConnectionManager
from core.vault import get_vault

logger = logging.getLogger("ninko.modules.microsoft_intune.tools")

GRAPH_URL = "https://graph.microsoft.com/beta"


async def _get_token(connection_id: str = "") -> str:
    """Get access token using client credentials flow."""
    if connection_id:
        conn = await ConnectionManager.get_connection("microsoft_intune", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Intune-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Intune connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Intune avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión Intune con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Intune con ID '{connection_id}' non trovata.",
                    nl=f"Intune-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Intune z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Intune com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のIntune接続が見つかりません。",
                    zh=f"未找到ID为 '{connection_id}' 的Intune连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("microsoft_intune")

    if conn:
        tenant_id = conn.config.get("tenant_id", "")
        client_id = conn.config.get("client_id", "")
        vault = get_vault()
        client_secret = None
        secret_path = conn.vault_keys.get("INTUNE_CLIENT_SECRET")
        if secret_path:
            client_secret = await vault.get_secret(secret_path)
        if not client_secret:
            client_secret = os.environ.get("INTUNE_CLIENT_SECRET", "")
    else:
        tenant_id = os.environ.get("INTUNE_TENANT_ID", "")
        client_id = os.environ.get("INTUNE_CLIENT_ID", "")
        vault = get_vault()
        client_secret = await vault.get_secret("INTUNE_CLIENT_SECRET")

    if not tenant_id or not client_id or not client_secret:
        raise ValueError(
            _t(
                de="Keine Intune-Verbindung konfiguriert.",
                en="No Intune connection configured.",
                fr="Aucune connexion Intune configurée.",
                es="No hay conexión Intune configurada.",
                it="Nessuna connessione Intune configurata.",
                nl="Geen Intune-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia Intune.",
                pt="Nenhuma conexão Intune configurada.",
                ja="Intune接続が設定されていません。",
                zh="未配置Intune连接。",
            )
        )

    token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": "https://graph.microsoft.com/.default",
        "grant_type": "client_credentials",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(token_url, data=payload) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


async def _graph_request(
    method: str, path: str, token: str, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to Microsoft Graph."""
    url = f"{GRAPH_URL}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        async with session.request(method, url, json=json) as resp:
            if resp.status == 204:
                return {"status": "OK"}
            resp.raise_for_status()
            return await resp.json()


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_intune_devices(connection_id: str = "") -> str:
    """
    List managed devices in Intune.
    Use this to get all enrolled devices.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceManagement/managedDevices?$top=50",
            token,
        )
        devices = data.get("value", [])
        if not devices:
            return _t(
                de="Keine Geräte gefunden",
                en="No devices found",
                fr="Aucun appareil trouvé",
                es="No se encontraron dispositivos",
                it="Nessun dispositivo trovato",
                nl="Geen apparaten gevonden",
                pl="Nie znaleziono urządzeń",
                pt="Nenhum dispositivo encontrado",
                ja="デバイスが見つかりません",
                zh="未找到设备",
            )

        lines = [
            "📱 "
            + _t(
                de="Verwaltete Geräte",
                en="Managed devices",
                fr="Appareils gérés",
                es="Dispositivos administrados",
                it="Dispositivi gestiti",
                nl="Beheerde apparaten",
                pl="Zarządzane urządzenia",
                pt="Dispositivos gerenciados",
                ja="管理対象デバイス",
                zh="托管设备",
            )
        ]
        for d in devices[:15]:
            os = d.get("operatingSystem", "-")
            os_ver = d.get("osVersion", "")
            compliant = "✅" if d.get("complianceState") == "Compliant" else "❌"
            lines.append(f"  {compliant} {d.get('deviceName', '-')} ({os} {os_ver})")

        total = len(devices)
        lines.append(
            f"\n✓ {total} "
            + _t(
                de="Geräte (zeige nur erste 15)",
                en="devices (showing first 15)",
                fr="appareils (affichage des 15 premiers)",
                es="dispositivos (mostrando los primeros 15)",
                it="dispositivi (visualizzazione primi 15)",
                nl="apparaten (toont eerste 15)",
                pl="urządzeń (wyświetlanie pierwszych 15)",
                pt="dispositivos (mostrando os primeiros 15)",
                ja="デバイス（最初の15件を表示）",
                zh="设备（显示前15个）",
            )
        )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_intune_devices failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def get_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Get details for a specific managed device.
    Use this to see full device information.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Nie znaleziono urządzenia: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        d = devices[0]
        lines = [
            "📱 "
            + _t(
                de="Gerätedetails",
                en="Device details",
                fr="Détails de l'appareil",
                es="Detalles del dispositivo",
                it="Dettagli del dispositivo",
                nl="Apparaatdetails",
                pl="Szczegóły urządzenia",
                pt="Detalhes do dispositivo",
                ja="デバイスの詳細",
                zh="设备详情",
            )
        ]
        lines.append(f"  {d.get('deviceName', '-')}")
        lines.append(f"  OS: {d.get('operatingSystem', '-')} {d.get('osVersion', '')}")
        lines.append(f"  📋 {d.get('userDisplayName', '-')}")
        lines.append(f"  Compliance: {d.get('complianceState', 'unknown')}")
        lines.append(
            f"  "
            + _t(
                de="Letzte Sync",
                en="Last sync",
                fr="Dernière sync",
                es="Última sync",
                it="Ultima sync",
                nl="Laatste sync",
                pl="Ostatnia sync",
                pt="Última sincronização",
                ja="最終同期",
                zh="最后同步",
            )
            + f": {d.get('lastSyncDateTime', '-')[:19]}"
        )
        lines.append(
            f"  "
            + _t(
                de="Jailbreak",
                en="Jailbreak",
                fr="Jailbreak",
                es="Jailbreak",
                it="Jailbreak",
                nl="Jailbreak",
                pl="Jailbreak",
                pt="Jailbreak",
                ja="ジェイルブレイク",
                zh="越狱",
            )
            + f": {'" + _t(de="Ja", en="Yes", fr="Oui", es="Sí", it="Sì", nl="Ja", pl="Tak", pt="Sim", ja="はい", zh="是") + "' if d.get('jailBreakDetectedState') else '" + _t(de="Nein", en="No", fr="Non", es="No", it="No", nl="Nee", pl="Nie", pt="Não", ja="いいえ", zh="否") + "'}"
        )
        lines.append(
            f"  "
            + _t(
                de="Verwaltet",
                en="Managed",
                fr="Géré",
                es="Administrado",
                it="Gestito",
                nl="Beheerd",
                pl="Zarządzany",
                pt="Gerenciado",
                ja="管理対象",
                zh="已管理",
            )
            + f": {'" + _t(de="Ja", en="Yes", fr="Oui", es="Sí", it="Sì", nl="Ja", pl="Tak", pt="Sim", ja="はい", zh="是") + "' if d.get('isManaged') else '" + _t(de="Nein", en="No", fr="Non", es="No", it="No", nl="Nee", pl="Nie", pt="Não", ja="いいえ", zh="否") + "'}"
        )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_intune_device failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def list_intune_policies(connection_id: str = "") -> str:
    """
    List device configuration policies.
    Use this to see all configuration policies.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceManagement/deviceConfigurations?$top=20",
            token,
        )
        policies = data.get("value", [])
        if not policies:
            return _t(
                de="Keine Richtlinien gefunden",
                en="No policies found",
                fr="Aucune politique trouvée",
                es="No se encontraron políticas",
                it="Nessun criterio trovato",
                nl="Geen beleid gevonden",
                pl="Nie znaleziono zasad",
                pt="Nenhuma política encontrada",
                ja="ポリシーが見つかりません",
                zh="未找到策略",
            )

        lines = [
            "📋 "
            + _t(
                de="Konfigurationsrichtlinien",
                en="Configuration policies",
                fr="Stratégies de configuration",
                es="Directivas de configuración",
                it="Criteri di configurazione",
                nl="Configuratiebeleid",
                pl="Zasady konfiguracji",
                pt="Políticas de configuração",
                ja="構成ポリシー",
                zh="配置策略",
            )
        ]
        for p in policies[:15]:
            plat = p.get("platform", "-")
            lines.append(f"  • {p.get('name', '-')} ({plat})")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_intune_policies failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def list_intune_compliance_policies(connection_id: str = "") -> str:
    """
    List device compliance policies.
    Use this to see compliance requirements.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceManagement/deviceCompliancePolicies?$top=20",
            token,
        )
        policies = data.get("value", [])
        if not policies:
            return _t(
                de="Keine Compliance-Richtlinien",
                en="No compliance policies",
                fr="Aucune politique de conformité",
                es="No hay políticas de cumplimiento",
                it="Nessun criterio di conformità",
                nl="Geen nalevingsbeleid",
                pl="Brak zasad zgodności",
                pt="Nenhuma política de conformidade",
                ja="コンプライアンスポリシーが見つかりません",
                zh="未找到合规策略",
            )

        lines = [
            "✅ "
            + _t(
                de="Compliance-Richtlinien",
                en="Compliance policies",
                fr="Politiques de conformité",
                es="Políticas de cumplimiento",
                it="Criteri di conformità",
                nl="Nalevingsbeleid",
                pl="Zasady zgodności",
                pt="Políticas de conformidade",
                ja="コンプライアンスポリシー",
                zh="合规策略",
            )
        ]
        for p in policies[:15]:
            plat = p.get("platform", "-")
            lines.append(f"  • {p.get('name', '-')} ({plat})")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_intune_compliance_policies failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def list_intune_apps(connection_id: str = "") -> str:
    """
    List managed apps in Intune.
    Use this to see deployed applications.
    """
    try:
        token = await _get_token(connection_id)
        data = await _graph_request(
            "GET",
            "/deviceAppManagement/mobileApps?$top=20",
            token,
        )
        apps = data.get("value", [])
        if not apps:
            return _t(
                de="Keine Apps gefunden",
                en="No apps found",
                fr="Aucune application trouvée",
                es="No se encontraron aplicaciones",
                it="Nessuna app trovata",
                nl="Geen apps gevonden",
                pl="Nie znaleziono aplikacji",
                pt="Nenhum aplicativo encontrado",
                ja="アプリが見つかりません",
                zh="未找到应用",
            )

        lines = [
            "📦 "
            + _t(
                de="Verwaltete Apps",
                en="Managed apps",
                fr="Applications gérées",
                es="Aplicaciones administradas",
                it="App gestite",
                nl="Beheerde apps",
                pl="Zarządzane aplikacje",
                pt="Aplicativos gerenciados",
                ja="管理対象アプリ",
                zh="托管应用",
            )
        ]
        for a in apps[:15]:
            pub = a.get("publisher", "")
            lines.append(f"  • {a.get('displayName', '-')}")
            if pub:
                lines.append(f"    {pub}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_intune_apps failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def get_intune_device_compliance(
    device_name: str, connection_id: str = ""
) -> str:
    """
    Get compliance status for a device.
    Use this to check if a device meets compliance requirements.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Nie znaleziono urządzenia: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        d = devices[0]
        status = d.get("complianceState", "unknown")
        is_compliant = status == "Compliant"

        lines = [
            "✅ "
            + _t(
                de="Compliance-Status",
                en="Compliance status",
                fr="État de conformité",
                es="Estado de cumplimiento",
                it="Stato di conformità",
                nl="Nalevingsstatus",
                pl="Stan zgodności",
                pt="Status de conformidade",
                ja="コンプライアンス状態",
                zh="合规状态",
            )
        ]
        lines.append(f"  {device_name}: {status}")
        if is_compliant:
            lines.append(
                _t(
                    de="  ✓ Gerät ist konform",
                    en="  ✓ Device is compliant",
                    fr="  ✓ L'appareil est conforme",
                    es="  ✓ El dispositivo es conforme",
                    it="  ✓ Il dispositivo è conforme",
                    nl="  ✓ Apparaat voldoet",
                    pl="  ✓ Urządzenie jest zgodne",
                    pt="  ✓ Dispositivo está em conformidade",
                    ja="  ✓ デバイスは準拠しています",
                    zh="  ✓ 设备符合要求",
                )
            )
        else:
            lines.append(
                _t(
                    de="  ✗ Gerät ist nicht konform",
                    en="  ✗ Device is not compliant",
                    fr="  ✗ L'appareil n'est pas conforme",
                    es="  ✗ El dispositivo no es conforme",
                    it="  ✗ Il dispositivo non è conforme",
                    nl="  ✗ Apparaat voldoet niet",
                    pl="  ✗ Urządzenie nie jest zgodne",
                    pt="  ✗ Dispositivo não está em conformidade",
                    ja="  ✗ デバイスは準拠していません",
                    zh="  ✗ 设备不符合要求",
                )
            )

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_intune_device_compliance failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


# ═══════════════════════════════════════════════════════
# Write/Action tools
# ═══════════════════════════════════════════════════════


@tool
async def wipe_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Wipe a managed device (factory reset).
    Use this to wipe a lost or stolen device.
    NOTE: This permanently erases all data!
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Nie znaleziono urządzenia: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        device_id = devices[0]["id"]
        await _graph_request(
            "POST",
            f"/deviceManagement/managedDevices/{device_id}/wipe",
            token,
        )
        return _t(
            de=f"✅ Wipe eingeleitet für: {device_name}",
            en=f"✅ Wipe initiated for: {device_name}",
            fr=f"✅ Wipe initiée pour: {device_name}",
            es=f"✅ Wipe iniciado para: {device_name}",
            it=f"✅ Wipe avviato per: {device_name}",
            nl=f"✅ Wipe geïnitieerd voor: {device_name}",
            pl=f"✅ Wipe zainicjowany dla: {device_name}",
            pt=f"✅ Wipe iniciado para: {device_name}",
            ja=f"✅ {device_name} のワイプを開始しました",
            zh=f"✅ 已为 {device_name} 启动擦除",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("wipe_intune_device failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def retire_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Retire a managed device (remove from management).
    Use this to remove a device from Intune management.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Nie znaleziono urządzenia: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        device_id = devices[0]["id"]
        await _graph_request(
            "POST",
            f"/deviceManagement/managedDevices/{device_id}/retire",
            token,
        )
        return _t(
            de=f"✅ Gerät entfernt aus Management: {device_name}",
            en=f"✅ Device retired: {device_name}",
            fr=f"✅ Appareil retiré: {device_name}",
            es=f"✅ Dispositivo jubilado: {device_name}",
            it=f"✅ Dispositivo ritirato: {device_name}",
            nl=f"✅ Apparaat buiten gebruik gesteld: {device_name}",
            pl=f"✅ Urządzenie wycofane: {device_name}",
            pt=f"✅ Dispositivo aposentado: {device_name}",
            ja=f"✅ {device_name} をリタイアしました",
            zh=f"✅ 设备已退役: {device_name}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("retire_intune_device failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def sync_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Trigger a remote sync on a managed device.
    Use this to force a device to check in with Intune.
    German: Gerät synchronisieren or Intune Sync.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Nie znaleziono urządzenia: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        device_id = devices[0]["id"]
        await _graph_request(
            "POST",
            f"/deviceManagement/managedDevices/{device_id}/syncDevice",
            token,
        )
        return _t(
            de=f"✅ Sync eingeleitet für: {device_name}",
            en=f"✅ Sync initiated for: {device_name}",
            fr=f"✅ Sync initiée pour: {device_name}",
            es=f"✅ Sync iniciada para: {device_name}",
            it=f"✅ Sincronizzazione avviata per: {device_name}",
            nl=f"✅ Sync geïnitieerd voor: {device_name}",
            pl=f"✅ Sync zainicjowany dla: {device_name}",
            pt=f"✅ Sincronização iniciada para: {device_name}",
            ja=f"✅ {device_name} の同期を開始しました",
            zh=f"✅ 已为 {device_name} 启动同步",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("sync_intune_device failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )


@tool
async def locate_intune_device(device_name: str, connection_id: str = "") -> str:
    """
    Get the location of a managed device.
    Use this to locate a lost device.
    """
    try:
        token = await _get_token(connection_id)
        search = (
            f"/deviceManagement/managedDevices?$filter=deviceName eq '{device_name}'"
        )
        data = await _graph_request("GET", search, token)
        devices = data.get("value", [])
        if not devices:
            return _t(
                de=f"Gerät nicht gefunden: {device_name}",
                en=f"Device not found: {device_name}",
                fr=f"Appareil non trouvé: {device_name}",
                es=f"Dispositivo no encontrado: {device_name}",
                it=f"Dispositivo non trovato: {device_name}",
                nl=f"Apparaat niet gevonden: {device_name}",
                pl=f"Nie znaleziono urządzenia: {device_name}",
                pt=f"Dispositivo não encontrado: {device_name}",
                ja=f"デバイスが見つかりません: {device_name}",
                zh=f"未找到设备: {device_name}",
            )

        d = devices[0]
        loc = d.get("location") or _t(
            de="unbekannt",
            en="unknown",
            fr="inconnu",
            es="desconocido",
            it="sconosciuto",
            nl="onbekend",
            pl="nieznany",
            pt="desconhecido",
            ja="不明",
            zh="未知",
        )
        lines = [
            "📍 "
            + _t(
                de="Gerätestandort",
                en="Device location",
                fr="Emplacement de l'appareil",
                es="Ubicación del dispositivo",
                it="Posizione del dispositivo",
                nl="Apparaatlocatie",
                pl="Lokalizacja urządzenia",
                pt="Localização do dispositivo",
                ja="デバイスの場所",
                zh="设备位置",
            )
        ]
        lines.append(f"  {device_name}: {loc}")
        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("locate_intune_device failed: %s", e)
        return _t(
            de=f"Fehler: {e}",
            en=f"Error: {e}",
            fr=f"Erreur: {e}",
            es=f"Error: {e}",
            it=f"Errore: {e}",
            nl=f"Fout: {e}",
            pl=f"Błąd: {e}",
            pt=f"Erro: {e}",
            ja=f"エラー: {e}",
            zh=f"错误: {e}",
        )
