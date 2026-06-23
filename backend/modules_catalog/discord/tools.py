"""Discord module — LangGraph @tool functions."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

import httpx
from langchain_core.tools import tool

from core.connections import ConnectionManager
from core.vault import get_vault
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.discord.tools")

DISCORD_API_BASE = "https://discord.com/api/v10"


async def _get_discord_config(connection_id: str = "") -> dict:
    """Load Discord config and secrets from ConnectionManager."""
    if connection_id:
        conn = await ConnectionManager.get_connection("discord", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Discord-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Discord connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Discord avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión Discord con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Discord con ID '{connection_id}' non trovata.",
                    nl=f"Discord-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Discord z ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Discord com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のDiscord接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Discord连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("discord")

    if conn:
        vault = get_vault()
        token = conn.vault_keys.get("DISCORD_BOT_TOKEN")
        bot_token = (
            await vault.get_secret(token) if token else conn.config.get("bot_token", "")
        )
        guild_id = conn.config.get("guild_id", "")
        return {"bot_token": bot_token, "guild_id": guild_id}

    bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
    guild_id = os.environ.get("DISCORD_GUILD_ID", "")

    if not bot_token:
        raise ValueError(
            _t(
                de="Keine Discord-Verbindung konfiguriert. Bitte Discord-Bot-Token in den Einstellungen setzen.",
                en="No Discord connection configured. Please set Discord bot token in settings.",
                fr="Aucune connexion Discord configurée. Veuillez définir le token du bot Discord dans les paramètres.",
                es="No hay conexión Discord configurada. Por favor configure el token del bot de Discord en la configuración.",
                it="Nessuna connessione Discord configurata. Per favore imposta il token del bot Discord nelle impostazioni.",
                nl="Geen Discord-verbinding geconfigureerd. Stel alstublieft het Discord-bot-token in in de instellingen.",
                pl="Nie skonfigurowano połączenia Discord. Ustaw token bota Discord w ustawieniach.",
                pt="Nenhuma conexão Discord configurada. Por favor, defina o token do bot Discord nas configurações.",
                ja="Discord接続が設定されていません。設定でDiscordボットのトークンを設定してください。",
                zh="未配置Discord连接。请在设置中设置Discord机器人令牌。",
            )
        )

    return {"bot_token": bot_token, "guild_id": guild_id}


async def _discord_request(
    method: str,
    endpoint: str,
    bot_token: str,
    json_data: dict | None = None,
) -> Any:
    """Make a request to Discord API."""
    url = f"{DISCORD_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        if method == "GET":
            resp = await client.get(url, headers=headers)
        elif method == "POST":
            resp = await client.post(url, headers=headers, json=json_data)
        elif method == "PUT":
            resp = await client.put(url, headers=headers, json=json_data)
        elif method == "PATCH":
            resp = await client.patch(url, headers=headers, json=json_data)
        elif method == "DELETE":
            resp = await client.delete(url, headers=headers)
        else:
            raise ValueError(f"Unsupported method: {method}")

        if resp.status_code == 204:
            return {}
        if resp.status_code >= 400:
            error = resp.json()
            raise ValueError(f"Discord API error: {error.get('message', resp.text)}")

        return resp.json()


@tool
async def get_discord_guild_info(connection_id: str = "") -> Dict:
    """
    Get Discord server (guild) information.
    Use this tool to get the server name, member count, and other details.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]
        guild_id = config["guild_id"]

        if not guild_id:
            return {"error": "No guild_id configured"}

        result = await _discord_request("GET", f"/guilds/{guild_id}", bot_token)

        return {
            "name": result.get("name", ""),
            "id": result.get("id", ""),
            "member_count": result.get("member_count", 0),
            "owner_id": result.get("owner_id", ""),
            "verification_level": result.get("verification_level", 0),
        }

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to get Discord guild info: %s", e)
        return {"error": str(e)}


@tool
async def list_discord_channels(connection_id: str = "") -> List[Dict]:
    """
    List all channels in the Discord server.
    Use this tool to see available text, voice, and category channels.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]
        guild_id = config["guild_id"]

        if not guild_id:
            return [{"error": "No guild_id configured"}]

        result = await _discord_request(
            "GET", f"/guilds/{guild_id}/channels", bot_token
        )

        channels = []
        for ch in result:
            channels.append(
                {
                    "id": ch.get("id", ""),
                    "name": ch.get("name", ""),
                    "type": ch.get("type", 0),
                    "position": ch.get("position", 0),
                    "parent_id": ch.get("parent_id", ""),
                }
            )

        return channels

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to list Discord channels: %s", e)
        return [{"error": str(e)}]


@tool
async def list_discord_members(connection_id: str = "", limit: int = 100) -> List[Dict]:
    """
    List members in the Discord server.
    Use this tool to see server members.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]
        guild_id = config["guild_id"]

        if not guild_id:
            return [{"error": "No guild_id configured"}]

        result = await _discord_request(
            "GET",
            f"/guilds/{guild_id}/members?limit={limit}",
            bot_token,
        )

        members = []
        for m in result:
            user = m.get("user", {})
            members.append(
                {
                    "id": user.get("id", ""),
                    "username": user.get("username", ""),
                    "global_name": user.get("global_name", ""),
                    "nick": m.get("nick", ""),
                    "roles": m.get("roles", []),
                }
            )

        return members

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to list Discord members: %s", e)
        return [{"error": str(e)}]


@tool
async def send_discord_message(
    channel_id: str,
    content: str,
    connection_id: str = "",
) -> str:
    """
    Send a message to a Discord channel.
    Use this tool to send text messages to Discord channels.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]

        await _discord_request(
            "POST",
            f"/channels/{channel_id}/messages",
            bot_token,
            json_data={"content": content},
        )

        return _t(
            de=f"Nachricht gesendet an Discord-Kanal {channel_id}",
            en=f"Message sent to Discord channel {channel_id}",
            fr=f"Message envoyé au canal Discord {channel_id}",
            es=f"Mensaje enviado al canal de Discord {channel_id}",
            it=f"Messaggio inviato al canale Discord {channel_id}",
            nl=f"Bericht verzonden naar Discord-kanaal {channel_id}",
            pl=f"Wysłano wiadomość do kanału Discord {channel_id}",
            pt=f"Mensagem enviada para o canal Discord {channel_id}",
            ja=f"Discordチャンネル {channel_id} にメッセージを送信しました",
            zh=f"消息已发送到Discord频道 {channel_id}",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to send Discord message: %s", e)
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
async def create_discord_channel(
    name: str,
    channel_type: str = "text",
    topic: str = "",
    connection_id: str = "",
) -> str:
    """
    Create a new channel in the Discord server.
    Use this tool to create text, voice, or category channels.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]
        guild_id = config["guild_id"]

        if not guild_id:
            return _t(
                de="Keine guild_id konfiguriert",
                en="No guild_id configured",
                fr="Aucun guild_id configuré",
                es="No hay guild_id configurado",
                it="Nessun guild_id configurato",
                nl="Geen guild_id geconfigureerd",
                pl="Nie skonfigurowano guild_id",
                pt="Nenhum guild_id configurado",
                ja="guild_idが設定されていません",
                zh="未配置guild_id",
            )

        channel_type_map = {
            "text": 0,
            "voice": 2,
            "category": 4,
        }
        ch_type = channel_type_map.get(channel_type.lower(), 0)

        json_data = {"name": name, "type": ch_type}
        if topic and ch_type == 0:
            json_data["topic"] = topic

        result = await _discord_request(
            "POST",
            f"/guilds/{guild_id}/channels",
            bot_token,
            json_data=json_data,
        )

        return _t(
            de=f"Discord-Kanal '{name}' erstellt (ID: {result.get('id')})",
            en=f"Discord channel '{name}' created (ID: {result.get('id')})",
            fr=f"Canal Discord '{name}' créé (ID: {result.get('id')})",
            es=f"Canal de Discord '{name}' creado (ID: {result.get('id')})",
            it=f"Canale Discord '{name}' creato (ID: {result.get('id')})",
            nl=f"Discord-kanaal '{name}' aangemaakt (ID: {result.get('id')})",
            pl=f"Kanał Discord '{name}' utworzony (ID: {result.get('id')})",
            pt=f"Canal Discord '{name}' criado (ID: {result.get('id')})",
            ja=f"Discordチャンネル '{name}' が作成されました (ID: {result.get('id')})",
            zh=f"Discord频道 '{name}' 已创建 (ID: {result.get('id')})",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to create Discord channel: %s", e)
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
async def get_discord_channel_messages(
    channel_id: str,
    limit: int = 10,
    connection_id: str = "",
) -> List[Dict]:
    """
    Get recent messages from a Discord channel.
    Use this tool to read message history from a channel.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]

        result = await _discord_request(
            "GET",
            f"/channels/{channel_id}/messages?limit={limit}",
            bot_token,
        )

        messages = []
        for msg in result:
            author = msg.get("author", {})
            messages.append(
                {
                    "id": msg.get("id", ""),
                    "content": msg.get("content", ""),
                    "author": author.get("username", ""),
                    "timestamp": msg.get("timestamp", ""),
                }
            )

        return messages

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to get Discord messages: %s", e)
        return [{"error": str(e)}]


@tool
async def search_discord_messages(
    channel_id: str,
    query: str,
    limit: int = 10,
    connection_id: str = "",
) -> List[Dict]:
    """
    Search for messages in a Discord channel.
    Use this tool to find specific messages.
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]

        messages = await _discord_request(
            "GET",
            f"/channels/{channel_id}/messages?limit=100",
            bot_token,
        )

        matching = [
            m for m in messages if query.lower() in m.get("content", "").lower()
        ][:limit]

        results = []
        for msg in matching:
            author = msg.get("author", {})
            results.append(
                {
                    "id": msg.get("id", ""),
                    "content": msg.get("content", ""),
                    "author": author.get("username", ""),
                    "timestamp": msg.get("timestamp", ""),
                }
            )

        return results

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to search Discord messages: %s", e)
        return [{"error": str(e)}]


@tool
async def delete_discord_channel(
    channel_id: str,
    connection_id: str = "",
) -> str:
    """
    Delete a Discord channel.
    Use this tool to remove a channel (requires appropriate permissions).
    """
    try:
        config = await _get_discord_config(connection_id)
        bot_token = config["bot_token"]

        await _discord_request("DELETE", f"/channels/{channel_id}", bot_token)

        return _t(
            de=f"Discord-Kanal {channel_id} gelöscht",
            en=f"Discord channel {channel_id} deleted",
            fr=f"Canal Discord {channel_id} supprimé",
            es=f"Canal de Discord {channel_id} eliminado",
            it=f"Canale Discord {channel_id} eliminato",
            nl=f"Discord-kanaal {channel_id} verwijderd",
            pl=f"Kanał Discord {channel_id} usunięty",
            pt=f"Canal Discord {channel_id} excluído",
            ja=f"Discordチャンネル {channel_id} が削除されました",
            zh=f"Discord频道 {channel_id} 已删除",
        )

    except (RuntimeError, ValueError, TypeError, KeyError, httpx.HTTPError) as e:
        logger.error("Failed to delete Discord channel: %s", e)
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
