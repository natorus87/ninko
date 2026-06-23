"""
Slack Module — LangGraph @tool functions.
Slack API for team communication.
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

logger = logging.getLogger("ninko.modules.slack.tools")

SLACK_API = "https://slack.com/api"


async def _get_token(connection_id: str = "") -> str:
    """Get Slack bot token."""
    if connection_id:
        conn = await ConnectionManager.get_connection("slack", connection_id)
    if not conn:
        raise ValueError(
            _t(
                de=f"Slack-Verbindung mit ID '{connection_id}' nicht gefunden.",
                en=f"Slack connection with ID '{connection_id}' not found.",
                fr=f"Connexion Slack avec l'ID '{connection_id}' non trouvée.",
                es=f"Conexión de Slack con ID '{connection_id}' no encontrada.",
                it=f"Connessione Slack con ID '{connection_id}' non trovata.",
                nl=f"Slack-verbinding met ID '{connection_id}' niet gevonden.",
                pl=f"Połączenie Slack z ID '{connection_id}' nie znaleziono.",
                pt=f"Conexão Slack com ID '{connection_id}' não encontrada.",
                ja=f"Slack接続ID '{connection_id}' が見つかりません。",
                zh=f"未找到ID为 '{connection_id}' 的Slack连接。",
            )
        )
    else:
        conn = await ConnectionManager.get_default_connection("slack")

    if conn:
        token = conn.config.get("token", "")
        if not token:
            vault = get_vault()
            vault_key = conn.vault_keys.get("SLACK_BOT_TOKEN")
            if vault_key:
                token = await vault.get_secret(vault_key)
            if not token:
                token = os.environ.get("SLACK_BOT_TOKEN", "")
    else:
        vault = get_vault()
        token = await vault.get_secret("SLACK_BOT_TOKEN")
        if not token:
            token = os.environ.get("SLACK_BOT_TOKEN", "")

    if not token:
        raise ValueError(
            _t(
                de="Keine Slack-Verbindung konfiguriert.",
                en="No Slack connection configured.",
                fr="Aucune connexion Slack configurée.",
                es="No hay conexión Slack configurada.",
                it="Nessuna connessione Slack configurata.",
                nl="Geen Slack-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia Slack.",
                pt="Nenhuma conexão Slack configurada.",
                ja="Slack接続が設定されていません。",
                zh="未配置Slack连接。",
            )
        )

    return token


async def _slack_request(
    method: str, path: str, token: str, json: Optional[dict] = None
) -> dict:
    """Make authenticated request to Slack API."""
    url = f"{SLACK_API}{path}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(
        headers=headers, timeout=aiohttp.ClientTimeout(total=30)
    ) as session:
        async with session.post(url, json=json) as resp:
            data = await resp.json()
            if not data.get("ok"):
                raise Exception(data.get("error", "Unknown error"))
            return data


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_slack_channels(connection_id: str = "") -> str:
    """
    List channels in Slack workspace.
    Use this to get all public and private channels.
    """
    try:
        token = await _get_token(connection_id)
        data = await _slack_request("POST", "/conversations.list", token, {"limit": 50})
        channels = data.get("channels", [])
        if not channels:
            return _t(
                de="Keine Channels gefunden",
                en="No channels found",
                fr="Aucun canal trouvé",
                es="No se encontraron canales",
                it="Nessun canale trovato",
                nl="Geen kanalen gevonden",
                pl="Nie znaleziono kanałów",
                pt="Nenhum canal encontrado",
                ja="チャンネルが見つかりません",
                zh="未找到频道",
            )

        lines = [
            "💬 "
            + _t(
                de="Channels",
                en="Channels",
                fr="Canaux",
                es="Canales",
                it="Canali",
                nl="Kanalen",
                pl="Kanały",
                pt="Canais",
                ja="チャンネル",
                zh="频道",
            )
        ]
        for ch in channels[:15]:
            is_priv = "🔒" if ch.get("is_private") else "📢"
            archived = "📦" if ch.get("is_archived") else ""
            lines.append(f"  {is_priv}{archived} {ch.get('name', '-')}")

        total = len(channels)
        lines.append(f"\n✓ {total} Channels")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("list_slack_channels failed: %s", e)
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
async def list_slack_users(connection_id: str = "") -> str:
    """
    List users in Slack workspace.
    Use this to see all workspace members.
    """
    try:
        token = await _get_token(connection_id)
        data = await _slack_request("POST", "/users.list", token)
        members = data.get("members", [])
        if not members:
            return _t(
                de="Keine Benutzer gefunden",
                en="No users found",
                fr="Aucun utilisateur trouvé",
                es="No se encontraron usuarios",
                it="Nessun utente trovato",
                nl="Geen gebruikers gevonden",
                pl="Nie znaleziono użytkowników",
                pt="Nenhum usuário encontrado",
                ja="ユーザーが見つかりません",
                zh="未找到用户",
            )

        lines = [
            "👥 "
            + _t(
                de="Benutzer",
                en="Users",
                fr="Utilisateurs",
                es="Usuarios",
                it="Utenti",
                nl="Gebruikers",
                pl="Użytkownicy",
                pt="Usuários",
                ja="ユーザー",
                zh="用户",
            )
        ]
        for u in members[:15]:
            if u.get("is_workflow_bot") or u.get("is_app_user"):
                continue
            name = u.get("profile", {}).get("real_name") or u.get("name", "-")
            status = u.get("profile", {}).get("status_text", "")
            lines.append(f"  👤 {name}")
            if status:
                lines.append(f"     {status}")

        count = len(members)
        lines.append(f"\n✓ {count} Benutzer")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("list_slack_users failed: %s", e)
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
async def get_slack_channel_history(channel_name: str, connection_id: str = "") -> str:
    """
    Get message history from a channel.
    Use this to read recent messages in a channel.
    """
    try:
        token = await _get_token(connection_id)
        ch_data = await _slack_request(
            "POST",
            "/conversations.list",
            token,
            {"limit": 10, "types": "public_channel,private_channel"},
        )
        channels = ch_data.get("channels", [])
        channel = next((c for c in channels if c.get("name") == channel_name), None)
        if not channel:
            return _t(
                de=f"Channel nicht gefunden: {channel_name}",
                en=f"Channel not found: {channel_name}",
                fr=f"Canal non trouvé: {channel_name}",
                es=f"Canal no encontrado: {channel_name}",
                it=f"Canale non trovato: {channel_name}",
                nl=f"Kanaal niet gevonden: {channel_name}",
                pl=f"Kanał nie znaleziony: {channel_name}",
                pt=f"Canal não encontrado: {channel_name}",
                ja=f"チャンネルが見つかりません: {channel_name}",
                zh=f"未找到频道: {channel_name}",
            )

        channel_id = channel["id"]
        messages = await _slack_request(
            "POST",
            "/conversations.history",
            token,
            {"channel": channel_id, "limit": 10},
        )
        msgs = messages.get("messages", [])
        if not msgs:
            return _t(
                de="Keine Nachrichten",
                en="No messages",
                fr="Aucun message",
                es="Sin mensajes",
                it="Nessun messaggio",
                nl="Geen berichten",
                pl="Brak wiadomości",
                pt="Nenhuma mensagem",
                ja="メッセージがありません",
                zh="无消息",
            )

        lines = [
            f"💬 "
            + _t(
                de="Nachrichten in",
                en="Messages in",
                fr="Messages dans",
                es="Mensajes en",
                it="Messaggi in",
                nl="Berichten in",
                pl="Wiadomości w",
                pt="Mensagens em",
                ja="メッセージ",
                zh="消息在",
            )
            + f" #{channel_name}"
        ]
        for m in msgs[:10]:
            user = m.get("user", "unknown")
            text = m.get("text", "")[:100]
            ts = m.get("ts", "")[11:16]
            lines.append(f"  [{ts}] {user}: {text}")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("get_slack_channel_history failed: %s", e)
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
async def search_slack_messages(query: str, connection_id: str = "") -> str:
    """
    Search for messages in Slack.
    Use this to find specific messages.
    """
    try:
        token = await _get_token(connection_id)
        data = await _slack_request(
            "POST", "/search.messages", token, {"query": query, "count": 10}
        )
        matches = data.get("messages", {}).get("matches", [])
        if not matches:
            return _t(
                de=f"Keine Ergebnisse für '{query}'",
                en=f"No results for '{query}'",
                fr=f"Aucun résultat pour '{query}'",
                es=f"No hay resultados para '{query}'",
                it=f"Nessun risultato per '{query}'",
                nl=f"Geen resultaten voor '{query}'",
                pl=f"Brak wyników dla '{query}'",
                pt=f"Nenhum resultado para '{query}'",
                ja=f"'{query}' の結果が見つかりません",
                zh=f"未找到'{query}'的结果",
            )

        lines = [
            f"🔍 "
            + _t(
                de="Suchergebnisse",
                en="Search results",
                fr="Résultats de recherche",
                es="Resultados de búsqueda",
                it="Risultati della ricerca",
                nl="Zoekresultaten",
                pl="Wyniki wyszukiwania",
                pt="Resultados da pesquisa",
                ja="検索結果",
                zh="搜索结果",
            )
            + f" '{query}'"
        ]
        for m in matches[:10]:
            ch = m.get("channel", {}).get("name", "-")
            text = m.get("text", "")[:120]
            user = m.get("username", "-")
            lines.append(f"  #{ch} ({user}): {text}")

        return "\n".join(lines)
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("search_slack_messages failed: %s", e)
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
async def send_slack_message(
    channel: str,
    text: str,
    connection_id: str = "",
) -> str:
    """
    Send a message to a Slack channel.
    Use this to post a message.
    """
    try:
        token = await _get_token(connection_id)
        channel_id = channel.lstrip("#")

        ch_data = await _slack_request(
            "POST", "/conversations.list", token, {"limit": 20}
        )
        channels = ch_data.get("channels", [])
        ch = next((c for c in channels if c.get("name") == channel_id), None)
        if not ch:
            ch_data = await _slack_request(
                "POST",
                "/conversations.list",
                token,
                {"limit": 20, "types": "private_channel"},
            )
            channels = ch_data.get("channels", [])
            ch = next((c for c in channels if c.get("name") == channel_id), None)

        if ch:
            channel_id = ch["id"]
            await _slack_request(
                "POST",
                "/chat.postMessage",
                token,
                {"channel": channel_id, "text": text},
            )
            return _t(
                de=f"✅ Nachricht gesendet an #{channel}",
                en=f"✅ Message sent to #{channel}",
                fr=f"✅ Message envoyé à #{channel}",
                es=f"✅ Mensaje enviado a #{channel}",
                it=f"✅ Messaggio inviato a #{channel}",
                nl=f"✅ Bericht verzonden naar #{channel}",
                pl=f"✅ Wiadomość wysłana do #{channel}",
                pt=f"✅ Mensagem enviada para #{channel}",
                ja=f"✅ メッセージを #{channel} に送信しました",
                zh=f"✅ 消息已发送到 #{channel}",
            )

        return _t(
            de=f"Channel nicht gefunden: {channel}",
            en=f"Channel not found: {channel}",
            fr=f"Canal non trouvé: {channel}",
            es=f"Canal no encontrado: {channel}",
            it=f"Canale non trovato: {channel}",
            nl=f"Kanaal niet gevonden: {channel}",
            pl=f"Kanał nie znaleziony: {channel}",
            pt=f"Canal não encontrado: {channel}",
            ja=f"チャンネルが見つかりません: {channel}",
            zh=f"未找到频道: {channel}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("send_slack_message failed: %s", e)
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
async def send_slack_dm(user_name: str, text: str, connection_id: str = "") -> str:
    """
    Send a direct message to a Slack user.
    Use this to DM a user.
    """
    try:
        token = await _get_token(connection_id)
        user_data = await _slack_request("POST", "/users.list", token)
        members = user_data.get("members", [])
        user = next((u for u in members if u.get("name") == user_name), None)
        if not user:
            return _t(
                de=f"Benutzer nicht gefunden: {user_name}",
                en=f"User not found: {user_name}",
                fr=f"Utilisateur non trouvé: {user_name}",
                es=f"Usuario no encontrado: {user_name}",
                it=f"Utente non trovato: {user_name}",
                nl=f"Gebruiker niet gevonden: {user_name}",
                pl=f"Użytkownik nie znaleziony: {user_name}",
                pt=f"Usuário não encontrado: {user_name}",
                ja=f"ユーザーが見つかりません: {user_name}",
                zh=f"未找到用户: {user_name}",
            )

        user_id = user["id"]
        conv = await _slack_request(
            "POST", "/conversations.open", token, {"users": user_id}
        )
        channel_id = conv.get("channel", {}).get("id")
        if not channel_id:
            return _t(
                de="Konnte DM nicht öffnen",
                en="Could not open DM",
                fr="Impossible d'ouvrir le DM",
                es="No se pudo abrir el DM",
                it="Impossibile aprire il DM",
                nl="Kon DM niet openen",
                pl="Nie można otworzyć DM",
                pt="Não foi possível abrir o DM",
                ja="DMを開けませんでした",
                zh="无法打开私信",
            )

        await _slack_request(
            "POST", "/chat.postMessage", token, {"channel": channel_id, "text": text}
        )
        return _t(
            de=f"✅ DM gesendet an {user_name}",
            en=f"✅ DM sent to {user_name}",
            fr=f"✅ DM envoyé à {user_name}",
            es=f"✅ DM enviado a {user_name}",
            it=f"✅ DM inviato a {user_name}",
            nl=f"✅ DM verzonden naar {user_name}",
            pl=f"✅ DM wysłany do {user_name}",
            pt=f"✅ DM enviado para {user_name}",
            ja=f"✅ {user_name}にDMを送信しました",
            zh=f"✅ 已发送私信给 {user_name}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("send_slack_dm failed: %s", e)
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
async def upload_slack_file(
    channel: str,
    content: str,
    title: str = "",
    connection_id: str = "",
) -> str:
    """
    Upload a file to a Slack channel.
    Use this to share code or text files.
    """
    try:
        token = await _get_token(connection_id)
        ch_data = await _slack_request(
            "POST", "/conversations.list", token, {"limit": 20}
        )
        channels = ch_data.get("channels", [])
        ch = next((c for c in channels if c.get("name") == channel.lstrip("#")), None)
        if not ch:
            return _t(
                de=f"Channel nicht gefunden: {channel}",
                en=f"Channel not found: {channel}",
                fr=f"Canal non trouvé: {channel}",
                es=f"Canal no encontrado: {channel}",
                it=f"Canale non trovato: {channel}",
                nl=f"Kanaal niet gevonden: {channel}",
                pl=f"Kanał nie znaleziony: {channel}",
                pt=f"Canal não encontrado: {channel}",
                ja=f"チャンネルが見つかりません: {channel}",
                zh=f"未找到频道: {channel}",
            )


        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {token}"},
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            FormData = aiohttp.FormData()
            FormData.add_field("channels", ch["id"])
            if title:
                FormData.add_field("title", title)
            FormData.add_field(
                "file",
                content,
                filename=title or "file.txt",
                content_type="text/plain",
            )
            async with session.post(f"{SLACK_API}/files.upload", data=FormData) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    return _t(
                        de=f"Fehler: {data.get('error')}",
                        en=f"Error: {data.get('error')}",
                        fr=f"Erreur: {data.get('error')}",
                        es=f"Error: {data.get('error')}",
                        it=f"Errore: {data.get('error')}",
                        nl=f"Fout: {data.get('error')}",
                        pl=f"Błąd: {data.get('error')}",
                        pt=f"Erro: {data.get('error')}",
                        ja=f"エラー: {data.get('error')}",
                        zh=f"错误: {data.get('error')}",
                    )

        return _t(
            de=f"✅ Datei hochgeladen in #{channel}",
            en=f"✅ File uploaded to #{channel}",
            fr=f"✅ Fichier téléversé vers #{channel}",
            es=f"✅ Archivo subido a #{channel}",
            it=f"✅ File caricato su #{channel}",
            nl=f"✅ Bestand geüpload naar #{channel}",
            pl=f"✅ Plik przesłany do #{channel}",
            pt=f"✅ Arquivo carregado para #{channel}",
            ja=f"✅ ファイルを #{channel} にアップロードしました",
            zh=f"✅ 文件已上传到 #{channel}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("upload_slack_file failed: %s", e)
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
async def create_slack_channel(
    channel_name: str,
    is_private: bool = False,
    connection_id: str = "",
) -> str:
    """
    Create a new channel in Slack.
    Use this to create a new public or private channel.
    """
    try:
        token = await _get_token(connection_id)
        await _slack_request(
            "POST",
            "/conversations.create",
            token,
            {"name": channel_name, "is_private": is_private},
        )
        priv = "private" if is_private else "public"
        return _t(
            de=f"✅ {priv.capitalize()} Channel erstellt: #{channel_name}",
            en=f"✅ {priv.capitalize()} channel created: #{channel_name}",
            fr=f"✅ Canal {priv} créé: #{channel_name}",
            es=f"✅ Canal {priv} creado: #{channel_name}",
            it=f"✅ Canale {priv} creato: #{channel_name}",
            nl=f"✅ {priv.capitalize()} kanaal aangemaakt: #{channel_name}",
            pl=f"✅ Kanał {priv} utworzony: #{channel_name}",
            pt=f"✅ Canal {priv} criado: #{channel_name}",
            ja=f"✅ {priv}チャンネルを作成: #{channel_name}",
            zh=f"✅ {priv}频道已创建: #{channel_name}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("create_slack_channel failed: %s", e)
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
async def invite_user_to_channel(
    channel_name: str,
    user_name: str,
    connection_id: str = "",
) -> str:
    """
    Invite a user to a channel.
    Use this to add a user to a channel.
    """
    try:
        token = await _get_token(connection_id)
        ch_data = await _slack_request(
            "POST", "/conversations.list", token, {"limit": 20}
        )
        channels = ch_data.get("channels", [])
        ch = next((c for c in channels if c.get("name") == channel_name), None)
        if not ch:
            return _t(
                de=f"Channel nicht gefunden: {channel_name}",
                en=f"Channel not found: {channel_name}",
                fr=f"Canal non trouvé: {channel_name}",
                es=f"Canal no encontrado: {channel_name}",
                it=f"Canale non trovato: {channel_name}",
                nl=f"Kanaal niet gevonden: {channel_name}",
                pl=f"Kanał nie znaleziony: {channel_name}",
                pt=f"Canal não encontrado: {channel_name}",
                ja=f"チャンネルが見つかりません: {channel_name}",
                zh=f"未找到频道: {channel_name}",
            )

        user_data = await _slack_request("POST", "/users.list", token)
        members = user_data.get("members", [])
        user = next((u for u in members if u.get("name") == user_name), None)
        if not user:
            return _t(
                de=f"Benutzer nicht gefunden: {user_name}",
                en=f"User not found: {user_name}",
                fr=f"Utilisateur non trouvé: {user_name}",
                es=f"Usuario no encontrado: {user_name}",
                it=f"Utente non trovato: {user_name}",
                nl=f"Gebruiker niet gevonden: {user_name}",
                pl=f"Użytkownik nie znaleziony: {user_name}",
                pt=f"Usuário não encontrado: {user_name}",
                ja=f"ユーザーが見つかりません: {user_name}",
                zh=f"未找到用户: {user_name}",
            )

        channel_id = ch["id"]
        user_id = user["id"]
        await _slack_request(
            "POST",
            "/conversations.invite",
            token,
            {"channel": channel_id, "users": user_id},
        )
        return _t(
            de=f"✅ {user_name} eingeladen in #{channel_name}",
            en=f"✅ {user_name} invited to #{channel_name}",
            fr=f"✅ {user_name} invité dans #{channel_name}",
            es=f"✅ {user_name} invitado a #{channel_name}",
            it=f"✅ {user_name} invitato in #{channel_name}",
            nl=f"✅ {user_name} uitgenodigd voor #{channel_name}",
            pl=f"✅ {user_name} zaproszony do #{channel_name}",
            pt=f"✅ {user_name} convidado para #{channel_name}",
            ja=f"✅ {user_name}を #{channel_name}に招待しました",
            zh=f"✅ 已邀请 {user_name} 到 #{channel_name}",
        )
    except (
        RuntimeError,
        ValueError,
        TypeError,
        KeyError,
        aiohttp.ClientError,
        OSError,
    ) as e:
        logger.error("invite_user_to_channel failed: %s", e)
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
