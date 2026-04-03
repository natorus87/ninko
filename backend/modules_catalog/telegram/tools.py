"""
Telegram Tools — enables sending messages from other agents.
"""

from __future__ import annotations

import logging

import httpx
from langchain_core.tools import tool

from agents.base_agent import _t
from .formatter import format_for_telegram

logger = logging.getLogger("ninko.modules.telegram.tools")


@tool
async def send_telegram_message(message: str, chat_id: str = "") -> str:
    """
    Sends a Telegram message to a user or group.
    Use this tool when the user requests a notification via Telegram
    or when a result should be proactively delivered via Telegram.

    Args:
        message: The text to send (Markdown allowed).
        chat_id: Telegram chat ID (optional). If not provided, the
                 default chat ID from Telegram connection settings is used.
    """
    from core.connections import ConnectionManager
    from core.vault import get_vault

    conn = await ConnectionManager.get_default_connection("telegram")
    if not conn:
        return _t(
            de="Fehler: Keine Telegram-Verbindung konfiguriert. Bitte zuerst in den Einstellungen einrichten.",
            en="Error: No Telegram connection configured. Please set one up in settings first.",
            fr="Erreur: Aucune connexion Telegram configurée. Veuillez d'abord la configurer dans les paramètres.",
            es="Error: No hay conexión de Telegram configurada. Por favor configúrala primero en la configuración.",
            it="Errore: Nessuna connessione Telegram configurata. Per favore configurala prima nelle impostazioni.",
            nl="Fout: Geen Telegram-verbinding geconfigureerd. Stel deze eerst in in de instellingen.",
            pl="Błąd: Nie skonfigurowano połączenia Telegram. Najpierw skonfiguruj je w ustawieniach.",
            pt="Erro: Nenhuma conexão Telegram configurada. Por favor configure-a primeiro nas configurações.",
            ja="エラー：Telegram接続が設定されていません。まず設定でセットアップしてください。",
            zh="错误：未配置Telegram连接。请先在设置中进行配置。",
        )

    vault = get_vault()
    bot_token = ""
    if "TELEGRAM_BOT_TOKEN" in conn.vault_keys:
        bot_token = await vault.get_secret(conn.vault_keys["TELEGRAM_BOT_TOKEN"])

    if not bot_token:
        return _t(
            de="Fehler: Kein Telegram Bot Token konfiguriert.",
            en="Error: No Telegram Bot Token configured.",
            fr="Erreur: Aucun token de bot Telegram configuré.",
            es="Error: No hay token de bot de Telegram configurado.",
            it="Errore: Nessun token bot Telegram configurato.",
            nl="Fout: Geen Telegram-bot-token geconfigureerd.",
            pl="Błąd: Nie skonfigurowano tokena bota Telegram.",
            pt="Erro: Nenhum token de bot do Telegram configurado.",
            ja="エラー：Telegram Botトークンが設定されていません。",
            zh="错误：未配置Telegram机器人令牌。",
        )

    # Chat-ID: parameter > connection config
    target_chat_id = chat_id.strip() or conn.config.get("default_chat_id", "")
    if not target_chat_id:
        return _t(
            de="Fehler: Keine Chat-ID angegeben und keine Standard-Chat-ID in den "
            "Telegram-Verbindungseinstellungen hinterlegt (Feld: 'default_chat_id').",
            en="Error: No chat ID provided and no default chat ID configured in "
            "Telegram connection settings (field: 'default_chat_id').",
            fr="Erreur: Aucune ID de chat fournie et aucune ID de chat par défaut configurée dans "
            "les paramètres de connexion Telegram (champ: 'default_chat_id').",
            es="Error: No se proporcionó ID de chat y no hay ID de chat predeterminada configurada en "
            "la configuración de conexión de Telegram (campo: 'default_chat_id').",
            it="Errore: Nessun ID chat fornito e nessun ID chat predefinito configurato nelle "
            "impostazioni di connessione Telegram (campo: 'default_chat_id').",
            nl="Fout: Geen chat-ID opgegeven en geen standaard chat-ID geconfigureerd in de "
            "Telegram-verbindingsinstellingen (veld: 'default_chat_id').",
            pl="Błąd: Nie podano identyfikatora czatu i nie skonfigurowano domyślnego identyfikatora czatu w "
            "ustawieniach połączenia Telegram (pole: 'default_chat_id').",
            pt="Erro: Nenhum ID de chat fornecido e nenhum ID de chat padrão configurado nas "
            "configurações de conexão do Telegram (campo: 'default_chat_id').",
            ja="エラー：チャットIDが指定されておらず、Telegram接続設定（フィールド：'default_chat_id'）にもデフォルトチャットIDが設定されていません。",
            zh="错误：未提供聊天ID，也未在Telegram连接设置（字段：'default_chat_id'）中配置默认聊天ID。",
        )

    # Convert Markdown → Telegram HTML
    html_message = format_for_telegram(message)

    # Send message — with HTML, fallback to plain text
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{bot_token}/sendMessage",
            json={
                "chat_id": target_chat_id,
                "text": html_message,
                "parse_mode": "HTML",
            },
        )

        if resp.status_code == 200 and resp.json().get("ok"):
            logger.info("Telegram message sent to chat %s", target_chat_id)
            return _t(
                de=f"✅ Telegram-Nachricht erfolgreich gesendet an Chat {target_chat_id}.",
                en=f"✅ Telegram message sent successfully to chat {target_chat_id}.",
                fr=f"✅ Message Telegram envoyé avec succès au chat {target_chat_id}.",
                es=f"✅ Mensaje de Telegram enviado con éxito al chat {target_chat_id}.",
                it=f"✅ Messaggio Telegram inviato con successo alla chat {target_chat_id}.",
                nl=f"✅ Telegram-bericht succesvol verzonden naar chat {target_chat_id}.",
                pl=f"✅ Wiadomość Telegram wysłana pomyślnie do czatu {target_chat_id}.",
                pt=f"✅ Mensagem do Telegram enviada com sucesso para o chat {target_chat_id}.",
                ja=f"✅ Telegramメッセージをチャット {target_chat_id} に送信しました。",
                zh=f"✅ Telegram消息已成功发送到聊天 {target_chat_id}。",
            )

        # HTML error → plain text fallback
        if resp.status_code == 400:
            resp2 = await client.post(
                f"https://api.telegram.org/bot{bot_token}/sendMessage",
                json={"chat_id": target_chat_id, "text": message},
            )
            if resp2.status_code == 200 and resp2.json().get("ok"):
                logger.info("Telegram message (plain) sent to chat %s", target_chat_id)
                return _t(
                    de=f"✅ Telegram-Nachricht gesendet (ohne HTML-Formatierung) an Chat {target_chat_id}.",
                    en=f"✅ Telegram message sent (without HTML formatting) to chat {target_chat_id}.",
                    fr=f"✅ Message Telegram envoyé (sans formatage HTML) au chat {target_chat_id}.",
                    es=f"✅ Mensaje de Telegram enviado (sin formato HTML) al chat {target_chat_id}.",
                    it=f"✅ Messaggio Telegram inviato (senza formattazione HTML) alla chat {target_chat_id}.",
                    nl=f"✅ Telegram-bericht verzonden (zonder HTML-opmaak) naar chat {target_chat_id}.",
                    pl=f"✅ Wiadomość Telegram wysłana (bez formatowania HTML) do czatu {target_chat_id}.",
                    pt=f"✅ Mensagem do Telegram enviada (sem formatação HTML) para o chat {target_chat_id}.",
                    ja=f"✅ Telegramメッセージ（HTMLフォーマットなし）をチャット {target_chat_id} に送信しました。",
                    zh=f"✅ Telegram消息（无HTML格式）已发送到聊天 {target_chat_id}。",
                )

        detail = resp.json().get("description", resp.text[:150])
        logger.error("Telegram sendMessage error: %s", detail)
        return _t(
            de=f"Fehler beim Senden der Telegram-Nachricht: {detail}",
            en=f"Error sending Telegram message: {detail}",
            fr=f"Erreur lors de l'envoi du message Telegram: {detail}",
            es=f"Error al enviar mensaje de Telegram: {detail}",
            it=f"Errore nell'invio del messaggio Telegram: {detail}",
            nl=f"Fout bij het verzenden van Telegram-bericht: {detail}",
            pl=f"Błąd podczas wysyłania wiadomości Telegram: {detail}",
            pt=f"Erro ao enviar mensagem do Telegram: {detail}",
            ja=f"Telegramメッセージの送信中にエラーが発生しました: {detail}",
            zh=f"发送Telegram消息时出错: {detail}",
        )
