"""
Teams Tools — enables sending messages from other agents.
"""

from __future__ import annotations

import json
import logging

from langchain_core.tools import tool

from agents.base_agent import _t
from .formatter import format_for_teams

logger = logging.getLogger("ninko.modules.teams.tools")

_LAST_CONV_KEY = "ninko:teams:last_conversation"


@tool
async def send_teams_message(message: str) -> str:
    """
    Send a proactive Teams message to the last active Teams conversation.
    Use this tool when the user requests a notification via Microsoft Teams
    or when a result should be proactively delivered via Teams.

    Args:
        message: The text to send (Markdown allowed).
    """
    from core.redis_client import get_redis
    from .bot import get_teams_access_token

    import httpx

    # Load last known conversation from Redis
    redis = get_redis()
    raw = await redis.connection.get(_LAST_CONV_KEY)
    if not raw:
        return _t(
            de="Fehler: Keine bekannte Teams-Konversation. "
            "Schreibe dem Bot zuerst in Teams, damit eine Zielkonversation gespeichert wird.",
            en="Error: No known Teams conversation. "
            "Write to the bot in Teams first so that a target conversation is saved.",
            fr="Erreur: Aucune conversation Teams connue. "
            "Écrivez d'abord au bot dans Teams afin qu'une conversation cible soit enregistrée.",
            es="Error: No hay conversación de Teams conocida. "
            "Escribe primero al bot en Teams para que se guarde una conversación de destino.",
            it="Errore: Nessuna conversazione Teams nota. "
            "Scrivi prima al bot in Teams in modo che venga salvata una conversazione di destinazione.",
            nl="Fout: Geen bekende Teams-gesprek. "
            "Schrijf eerst naar de bot in Teams zodat een doelgesprek wordt opgeslagen.",
            pl="Błąd: Brak znanej konwersacji Teams. "
            "Najpierw napisz do bota w Teams, aby zapisać konwersację docelową.",
            pt="Erro: Nenhuma conversa Teams conhecida. "
            "Escreva primeiro para o bot no Teams para que uma conversa de destino seja salva.",
            ja="エラー：既知のTeams会話がありません。 "
            "ターゲット会話が保存されるように、まずTeamsでBotに書き込んでください。",
            zh="错误：没有已知的Teams对话。 "
            "请先在Teams中向机器人发送消息，以便保存目标对话。",
        )

    try:
        conv = json.loads(raw)
        service_url = conv["service_url"]
        conversation_id = conv["conversation_id"]
        conv.get("activity_id")
    except (KeyError, json.JSONDecodeError):
        return _t(
            de="Fehler: Gespeicherte Teams-Konversation ist ungültig.",
            en="Error: Stored Teams conversation is invalid.",
            fr="Erreur: La conversation Teams stockée est invalide.",
            es="Error: La conversación de Teams almacenada no es válida.",
            it="Errore: La conversazione Teams memorizzata non è valida.",
            nl="Fout: Opgeslagen Teams-gesprek is ongeldig.",
            pl="Błąd: Zapisana konwersacja Teams jest nieprawidłowa.",
            pt="Erro: Conversa Teams armazenada é inválida.",
            ja="エラー：保存されたTeams会話が無効です。",
            zh="错误：存储的Teams对话无效。",
        )

    token = await get_teams_access_token()
    if not token:
        return _t(
            de="Fehler: Kein Teams Access Token. Bitte App ID und Password in den Einstellungen prüfen.",
            en="Error: No Teams Access Token. Please check App ID and Password in settings.",
            fr="Erreur: Pas de token d'accès Teams. Veuillez vérifier l'ID d'application et le mot de passe dans les paramètres.",
            es="Error: No hay token de acceso de Teams. Por favor verifique el ID de aplicación y la contraseña en la configuración.",
            it="Errore: Nessun token di accesso Teams. Per favore controlla ID app e password nelle impostazioni.",
            nl="Fout: Geen Teams-toegangstoken. Controleer app-ID en wachtwoord in de instellingen.",
            pl="Błąd: Brak tokena dostępu Teams. Sprawdź ID aplikacji i hasło w ustawieniach.",
            pt="Erro: Sem token de acesso do Teams. Por favor verifique o ID do aplicativo e a senha nas configurações.",
            ja="エラー：Teamsアクセストークンがありません。設定でApp IDとパスワードを確認してください。",
            zh="错误：没有Teams访问令牌。请在设置中检查App ID和密码。",
        )

    url = f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "type": "message",
        "textFormat": "markdown",
        "text": format_for_teams(message),
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code in (200, 201, 202):
            logger.info(
                "Teams message sent proactively to conversation %s", conversation_id
            )
            return _t(
                de="✅ Teams-Nachricht erfolgreich gesendet.",
                en="✅ Teams message sent successfully.",
                fr="✅ Message Teams envoyé avec succès.",
                es="✅ Mensaje de Teams enviado con éxito.",
                it="✅ Messaggio Teams inviato con successo.",
                nl="✅ Teams-bericht succesvol verzonden.",
                pl="✅ Wiadomość Teams wysłana pomyślnie.",
                pt="✅ Mensagem do Teams enviada com sucesso.",
                ja="✅ Teamsメッセージが正常に送信されました。",
                zh="✅ Teams消息发送成功。",
            )
        else:
            detail = resp.text[:200]
            logger.error("Teams sendMessage error: %s %s", resp.status_code, detail)
            return _t(
                de=f"Fehler beim Senden der Teams-Nachricht: HTTP {resp.status_code} – {detail}",
                en=f"Error sending Teams message: HTTP {resp.status_code} – {detail}",
                fr=f"Erreur lors de l'envoi du message Teams: HTTP {resp.status_code} – {detail}",
                es=f"Error al enviar mensaje de Teams: HTTP {resp.status_code} – {detail}",
                it=f"Errore nell'invio del messaggio Teams: HTTP {resp.status_code} – {detail}",
                nl=f"Fout bij het verzenden van Teams-bericht: HTTP {resp.status_code} – {detail}",
                pl=f"Błąd podczas wysyłania wiadomości Teams: HTTP {resp.status_code} – {detail}",
                pt=f"Erro ao enviar mensagem do Teams: HTTP {resp.status_code} – {detail}",
                ja=f"Teamsメッセージの送信中にエラーが発生しました：HTTP {resp.status_code} – {detail}",
                zh=f"发送Teams消息时出错：HTTP {resp.status_code} – {detail}",
            )
