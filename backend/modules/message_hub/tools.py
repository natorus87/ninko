"""
Message Hub — LangGraph @tool-Funktionen.

Ermöglicht dem Agenten die Verwaltung der Routing-Tabelle.
"""

from __future__ import annotations

import json
import logging
from typing import Annotated

from langchain_core.tools import tool

from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.message_hub.tools")


@tool
async def list_message_routes(
    channel_type: Annotated[
        str,
        "Optional: Filtert nach Channel-Typ ('telegram', 'discord', 'email'). Leer = alle.",
    ] = "",
) -> str:
    """
    Listet alle aktiven Message-Hub-Routing-Einträge auf.
    Zeigt welche Channels (Telegram Chat-IDs, Discord Channels, Email-Adressen)
    an welche Ninko-Session geroutet werden.
    """
    from .db import list_routes

    routes = await list_routes(channel_type if channel_type else None)
    if not routes:
        return _t(
            de="Keine Routing-Einträge konfiguriert.",
            en="No routing entries configured.",
            fr="Aucune entrée de routage configurée.",
            es="No hay entradas de enrutamiento configuradas.",
            it="Nessuna voce di routing configurata.",
            nl="Geen routeringsitems geconfigureerd.",
            pl="Brak skonfigurowanych wpisów routingu.",
            pt="Nenhuma entrada de roteamento configurada.",
            ja="ルーティングエントリが設定されていません。",
            zh="未配置路由条目。",
        )

    lines = []
    for r in routes:
        status = "✓" if r.enabled else "✗"
        lines.append(
            f"{status} [{r.channel_type}] {r.channel_id} → session:{r.session_id} "
            f"(cap:{r.permission_cap.value}) {('| ' + r.label) if r.label else ''} [ID:{r.id[:8]}]"
        )
    return "\n".join(lines)


@tool
async def create_message_route(
    channel_type: Annotated[str, "Channel-Typ: 'telegram', 'discord' oder 'email'"],
    channel_id: Annotated[
        str,
        "Channel-ID: Telegram Chat-ID (z.B. '123456789'), Discord Channel-ID oder E-Mail-Adresse",
    ],
    session_id: Annotated[
        str,
        "Ninko Session-ID für diesen Channel (neue UUID oder bestehende Session)",
    ],
    permission_cap: Annotated[
        str,
        "Max. erlaubter Tier: READONLY | COMMUNICATE | WRITE_DATA | WRITE_SYSTEM | ADMIN. Standard: WRITE_DATA",
    ] = "WRITE_DATA",
    label: Annotated[str, "Optionaler lesbarer Name (z.B. 'IT-Team Discord #alerts')"] = "",
) -> str:
    """
    Erstellt einen neuen Routing-Eintrag im Message Hub.
    Danach werden Nachrichten von diesem Channel automatisch an die angegebene
    Ninko-Session weitergeleitet.
    """
    from .db import create_route
    from .schemas import PermissionCap, RouteCreate

    # Validierung
    valid_types = {"telegram", "discord", "email"}
    if channel_type not in valid_types:
        return _t(
            de=f"Ungültiger channel_type '{channel_type}'. Erlaubt: {', '.join(valid_types)}",
            en=f"Invalid channel_type '{channel_type}'. Allowed: {', '.join(valid_types)}",
            fr=f"Type de canal invalide '{channel_type}'. Autorisé: {', '.join(valid_types)}",
            es=f"Tipo de canal no válido '{channel_type}'. Permitido: {', '.join(valid_types)}",
            it=f"Tipo di canale non valido '{channel_type}'. Consentito: {', '.join(valid_types)}",
            nl=f"Ongeldig kanaeltype '{channel_type}'. Toegestaan: {', '.join(valid_types)}",
            pl=f"Nieprawidłowy typ kanału '{channel_type}'. Dozwolone: {', '.join(valid_types)}",
            pt=f"Tipo de canal inválido '{channel_type}'. Permitido: {', '.join(valid_types)}",
            ja=f"無効なchannel_type '{channel_type}'。許可: {', '.join(valid_types)}",
            zh=f"无效的channel_type '{channel_type}'。允许: {', '.join(valid_types)}",
        )

    try:
        cap = PermissionCap(permission_cap.upper())
    except ValueError:
        valid_caps = [c.value for c in PermissionCap]
        return _t(
            de=f"Ungültiger permission_cap. Erlaubt: {', '.join(valid_caps)}",
            en=f"Invalid permission_cap. Allowed: {', '.join(valid_caps)}",
            fr=f"Permission_cap invalide. Autorisé: {', '.join(valid_caps)}",
            es=f"permission_cap no válido. Permitido: {', '.join(valid_caps)}",
            it=f"permission_cap non valido. Consentito: {', '.join(valid_caps)}",
            nl=f"Ongeldige permission_cap. Toegestaan: {', '.join(valid_caps)}",
            pl=f"Nieprawidłowy permission_cap. Dozwolone: {', '.join(valid_caps)}",
            pt=f"permission_cap inválido. Permitido: {', '.join(valid_caps)}",
            ja=f"無効なpermission_cap。許可: {', '.join(valid_caps)}",
            zh=f"无效的permission_cap。允许: {', '.join(valid_caps)}",
        )

    entry = await create_route(
        RouteCreate(
            channel_type=channel_type,  # type: ignore[arg-type]
            channel_id=channel_id,
            session_id=session_id,
            permission_cap=cap,
            label=label,
        )
    )
    return _t(
        de=f"Route erstellt: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        en=f"Route created: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        fr=f"Route créée: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        es=f"Ruta creada: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        it=f"Route creata: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        nl=f"Route aangemaakt: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        pl=f"Trasa utworzona: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        pt=f"Rota criada: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        ja=f"ルート作成: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
        zh=f"路由已创建: [{entry.channel_type}] {entry.channel_id} → session:{entry.session_id} (ID:{entry.id[:8]})",
    )


@tool
async def delete_message_route(
    route_id: Annotated[str, "Die Route-ID (mind. die ersten 8 Zeichen) aus list_message_routes"],
) -> str:
    """Löscht einen Routing-Eintrag aus dem Message Hub."""
    from .db import delete_route, list_routes

    # Kurz-ID Suche (first 8 chars)
    route_id = route_id.strip()
    if len(route_id) < 36:
        # Partielle ID → alle Routes durchsuchen
        all_routes = await list_routes()
        matches = [r for r in all_routes if r.id.startswith(route_id)]
        if not matches:
            return _t(
                de=f"Route '{route_id}' nicht gefunden.",
                en=f"Route '{route_id}' not found.",
                fr=f"Route '{route_id}' introuvable.",
                es=f"Ruta '{route_id}' no encontrada.",
                it=f"Route '{route_id}' non trovata.",
                nl=f"Route '{route_id}' niet gevonden.",
                pl=f"Trasa '{route_id}' nie znaleziona.",
                pt=f"Rota '{route_id}' não encontrada.",
                ja=f"ルート '{route_id}' が見つかりません。",
                zh=f"路由 '{route_id}' 未找到。",
            )
        if len(matches) > 1:
            return _t(
                de=f"Mehrdeutige ID '{route_id}' — {len(matches)} Treffer. Bitte längere ID angeben.",
                en=f"Ambiguous ID '{route_id}' — {len(matches)} matches. Please provide a longer ID.",
                fr=f"ID ambiguë '{route_id}' — {len(matches)} correspondances. Fournissez un ID plus long.",
                es=f"ID ambiguo '{route_id}' — {len(matches)} coincidencias. Proporcione un ID más largo.",
                it=f"ID ambiguo '{route_id}' — {len(matches)} corrispondenze. Fornire un ID più lungo.",
                nl=f"Dubbelzinnige ID '{route_id}' — {len(matches)} overeenkomsten. Geef een langer ID.",
                pl=f"Niejednoznaczne ID '{route_id}' — {len(matches)} wyniki. Podaj dłuższe ID.",
                pt=f"ID ambíguo '{route_id}' — {len(matches)} correspondências. Forneça um ID mais longo.",
                ja=f"あいまいなID '{route_id}' — {len(matches)} 件一致。より長いIDを指定してください。",
                zh=f"ID '{route_id}' 不明确 — {len(matches)} 个匹配项。请提供更长的ID。",
            )
        route_id = matches[0].id

    deleted = await delete_route(route_id)
    if not deleted:
        return _t(
            de=f"Route '{route_id}' nicht gefunden.",
            en=f"Route '{route_id}' not found.",
            fr=f"Route '{route_id}' introuvable.",
            es=f"Ruta '{route_id}' no encontrada.",
            it=f"Route '{route_id}' non trovata.",
            nl=f"Route '{route_id}' niet gevonden.",
            pl=f"Trasa '{route_id}' nie znaleziona.",
            pt=f"Rota '{route_id}' não encontrada.",
            ja=f"ルート '{route_id}' が見つかりません。",
            zh=f"路由 '{route_id}' 未找到。",
        )
    return _t(
        de=f"Route '{route_id[:8]}' erfolgreich gelöscht.",
        en=f"Route '{route_id[:8]}' successfully deleted.",
        fr=f"Route '{route_id[:8]}' supprimée avec succès.",
        es=f"Ruta '{route_id[:8]}' eliminada con éxito.",
        it=f"Route '{route_id[:8]}' eliminata con successo.",
        nl=f"Route '{route_id[:8]}' succesvol verwijderd.",
        pl=f"Trasa '{route_id[:8]}' pomyślnie usunięta.",
        pt=f"Rota '{route_id[:8]}' excluída com sucesso.",
        ja=f"ルート '{route_id[:8]}' が正常に削除されました。",
        zh=f"路由 '{route_id[:8]}' 已成功删除。",
    )


@tool
async def get_message_hub_status() -> str:
    """
    Zeigt den aktuellen Status aller Message-Hub-Worker und Routing-Statistiken.
    """
    from .hub import get_message_hub
    from .db import list_routes

    hub = get_message_hub()
    routes = await list_routes()
    active = sum(1 for r in routes if r.enabled)

    if not hub:
        return _t(
            de=f"Message Hub nicht aktiv. Routing-Einträge: {len(routes)} ({active} aktiv).",
            en=f"Message Hub not active. Routing entries: {len(routes)} ({active} active).",
            fr=f"Message Hub inactif. Entrées de routage: {len(routes)} ({active} actives).",
            es=f"Message Hub inactivo. Entradas de enrutamiento: {len(routes)} ({active} activas).",
            it=f"Message Hub non attivo. Voci di routing: {len(routes)} ({active} attive).",
            nl=f"Message Hub niet actief. Routeringsitems: {len(routes)} ({active} actief).",
            pl=f"Message Hub nieaktywny. Wpisy routingu: {len(routes)} ({active} aktywnych).",
            pt=f"Message Hub inativo. Entradas de roteamento: {len(routes)} ({active} ativas).",
            ja=f"Message Hubが非アクティブ。ルーティングエントリ: {len(routes)} ({active} アクティブ)。",
            zh=f"Message Hub未激活。路由条目: {len(routes)} ({active} 活跃)。",
        )

    status = hub.get_status()
    lines = [
        _t(
            de=f"Message Hub — {len(status.workers)} Worker | Routen: {len(routes)} ({active} aktiv)",
            en=f"Message Hub — {len(status.workers)} workers | Routes: {len(routes)} ({active} active)",
            fr=f"Message Hub — {len(status.workers)} workers | Routes: {len(routes)} ({active} actives)",
            es=f"Message Hub — {len(status.workers)} workers | Rutas: {len(routes)} ({active} activas)",
            it=f"Message Hub — {len(status.workers)} worker | Route: {len(routes)} ({active} attive)",
            nl=f"Message Hub — {len(status.workers)} workers | Routes: {len(routes)} ({active} actief)",
            pl=f"Message Hub — {len(status.workers)} workerów | Trasy: {len(routes)} ({active} aktywnych)",
            pt=f"Message Hub — {len(status.workers)} workers | Rotas: {len(routes)} ({active} ativas)",
            ja=f"Message Hub — {len(status.workers)} ワーカー | ルート: {len(routes)} ({active} アクティブ)",
            zh=f"Message Hub — {len(status.workers)} 工作进程 | 路由: {len(routes)} ({active} 活跃)",
        )
    ]
    for w in status.workers:
        state = "▶" if w.running else "■"
        err_info = f" | Fehler: {w.last_error[:60]}" if w.last_error else ""
        retry_info = f" | Retry in {w.next_retry_in:.0f}s" if w.next_retry_in else ""
        lines.append(
            f"  {state} {w.channel_type} (Neustarts: {w.restart_count}){err_info}{retry_info}"
        )
    return "\n".join(lines)
