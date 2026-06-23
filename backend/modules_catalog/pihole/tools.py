"""Pi-hole module — tools for the AI agent. Uses Pi-hole v6 REST API with session-based auth."""

from __future__ import annotations

import logging
import time
import asyncio

import httpx
from langchain_core.tools import tool
from agents.base_agent import _t

logger = logging.getLogger("ninko.modules.pihole.tools")

# ── Session Cache ──────────────────────────────────
_session_cache: dict[str, dict] = {}  # url -> {"sid": str, "expires": float}
_auth_locks: dict[str, asyncio.Lock] = {}
SESSION_TTL = 300  # 5 minutes


async def _get_pihole_config(connection_id: str = "") -> dict:
    """Load Pi-hole connection data from ConnectionManager, env, or Vault."""
    from core.connections import ConnectionManager
    from core.vault import get_vault
    import os
    
    vault = get_vault()

    if connection_id:
        conn = await ConnectionManager.get_default_connection("pihole") if connection_id == "default" else await ConnectionManager.get_connection("pihole", connection_id)
        if not conn:
            raise ValueError(f"Pi-hole connection with ID '{connection_id}' not found.")
            
        url = conn.config.get("url", "").rstrip("/")
        password = ""
        if "password" in conn.vault_keys:
            password = await vault.get_secret(conn.vault_keys["password"]) or ""
            
        return {"url": url, "password": password}

    # Try via ConnectionManager without ID (default)
    conn = await ConnectionManager.get_default_connection("pihole")
    if conn and conn.config.get("url"):
        url = conn.config.get("url", "").rstrip("/")
        password = ""
        if "password" in conn.vault_keys:
            password = await vault.get_secret(conn.vault_keys["password"]) or ""
        return {"url": url, "password": password}

    # FALLBACK: legacy env vars (from routes_settings)
    fallback_url = os.environ.get("PIHOLE_URL", "").rstrip("/")
    
    # If not in env vars, try loading directly from legacy settings in Redis
    if not fallback_url:
        try:
            from core.redis_client import get_redis
            import json
            redis = get_redis()
            raw = await redis.connection.get("ninko:settings:modules")
            if raw:
                overrides = json.loads(raw)
                conn_data = overrides.get("pihole", {}).get("connection", {})
                fallback_url = conn_data.get("PIHOLE_URL", "").rstrip("/")
        except (RuntimeError, ValueError, TypeError, KeyError, OSError):
            pass

    if fallback_url:
        fallback_password = await vault.get_secret("PIHOLE_PASSWORD") or os.environ.get("PIHOLE_PASSWORD", "")
        return {"url": fallback_url, "password": fallback_password}

    raise ValueError(_t(
        de="Keine Standard-Pi-hole-Verbindung konfiguriert (Verbitte den Nutzer im Dashboard unter 'Einstellungen -> Verbindungen' eine Pi-hole Verbindung anzulegen).",
        en="No default Pi-hole connection configured (ask the user to create a Pi-hole connection in the dashboard under 'Settings -> Connections').",
        fr="Aucune connexion Pi-hole par défaut configurée (demandez à l'utilisateur de créer une connexion Pi-hole dans le tableau de bord sous 'Paramètres -> Connexions').",
        es="No hay conexión Pi-hole predeterminada configurada (pida al usuario crear una conexión Pi-hole en el panel bajo 'Configuración -> Conexiones').",
        it="Nessuna connessione Pi-hole predefinita configurata (chiedi all'utente di creare una connessione Pi-hole nel cruscotto sotto 'Impostazioni -> Connessioni').",
        nl="Geen standaard Pi-hole-verbinding geconfigureerd (vraag de gebruiker om een Pi-hole-verbinding aan te maken in het dashboard onder 'Instellingen -> Verbindingen').",
        pl="Nie skonfigurowano domyślnego połączenia Pi-hole (poproś użytkownika o utworzenie połączenia Pi-hole w panelu w sekcji 'Ustawienia -> Połączenia').",
        pt="Nenhuma conexão Pi-hole padrão configurada (peça ao usuário para criar uma conexão Pi-hole no painel em 'Configurações -> Conexões').",
        ja="デフォルトのPi-hole接続が設定されていません（ダッシュボードの「設定→接続」でPi-hole接続を作成するようユーザーに依頼してください）。",
        zh='未配置默认Pi-hole连接（请用户在仪表板中的"设置→连接"下创建Pi-hole连接）。',
    ))


async def _authenticate(base_url: str, password: str) -> str:
    """
    Pi-hole v6 session auth: POST /api/auth → sid.
    Caches the token for SESSION_TTL seconds.
    Handles 429 (api_seats_exceeded) via session cleanup.
    """
    cache_key = base_url
    lock = _auth_locks.setdefault(cache_key, asyncio.Lock())

    async with lock:
        cached = _session_cache.get(cache_key)
        if cached and cached["expires"] > time.time():
            return cached["sid"]

        async with httpx.AsyncClient(timeout=10) as client:
            for attempt in range(3):
                resp = await client.post(
                    f"{base_url}/api/auth",
                    json={"password": password},
                )

                if resp.status_code == 429:
                    body = resp.json() if resp.text else {}
                    hint = body.get("error", {}).get("key", "")
                    logger.warning(
                        "Pi-hole auth 429: %s (attempt %d/3)",
                        hint, attempt + 1,
                    )

                    # If we still have any cached SID (even with TTL expired), try to reuse it.
                    stale = _session_cache.get(cache_key)
                    if hint == "api_seats_exceeded" and stale and stale.get("sid"):
                        return stale["sid"]

                    await asyncio.sleep(2 * (attempt + 1))
                    continue

                if resp.status_code == 401:
                    raise ValueError(_t(
                        de="Pi-hole Auth fehlgeschlagen: falsches Passwort",
                        en="Pi-hole auth failed: wrong password",
                        fr="Échec de l'authentification Pi-hole: mot de passe incorrect",
                        es="Autenticación de Pi-hole fallida: contraseña incorrecta",
                        it="Autenticazione Pi-hole non riuscita: password errata",
                        nl="Pi-hole-authenticatie mislukt: wachtwoord onjuist",
                        pl="Uwierzytelnianie Pi-hole nie powiodło się: nieprawidłowe hasło",
                        pt="Autenticação Pi-hole falhou: senha incorreta",
                        ja="Pi-hole認証に失敗しました：パスワードが正しくありません",
                        zh="Pi-hole认证失败：密码错误",
                    ))

                resp.raise_for_status()
                data = resp.json()

                sid = data.get("session", {}).get("sid", "")
                if not sid:
                    raise ValueError(_t(
                        de="Pi-hole Auth fehlgeschlagen: kein SID erhalten",
                        en="Pi-hole auth failed: no SID received",
                        fr="Échec de l'authentification Pi-hole: aucun SID reçu",
                        es="Autenticación de Pi-hole fallida: no se recibió SID",
                        it="Autenticazione Pi-hole non riuscita: nessun SID ricevuto",
                        nl="Pi-hole-authenticatie mislukt: geen SID ontvangen",
                        pl="Uwierzytelnianie Pi-hole nie powiodło się: nie otrzymano SID",
                        pt="Autenticação Pi-hole falhou: nenhum SID recebido",
                        ja="Pi-hole認証に失敗しました：SIDを受信しませんでした",
                        zh="Pi-hole认证失败：未收到SID",
                    ))

                _session_cache[cache_key] = {
                    "sid": sid,
                    "expires": time.time() + SESSION_TTL,
                }
                logger.info("Pi-hole session created for %s", base_url)
                return sid

    raise ValueError(_t(
        de="Pi-hole Auth fehlgeschlagen: zu viele Versuche (429)",
        en="Pi-hole auth failed: too many attempts (429)",
        fr="Échec de l'authentification Pi-hole: trop de tentatives (429)",
        es="Autenticación de Pi-hole fallida: demasiados intentos (429)",
        it="Autenticazione Pi-hole non riuscita: troppi tentativi (429)",
        nl="Pi-hole-authenticatie mislukt: te veel pogingen (429)",
        pl="Uwierzytelnianie Pi-hole nie powiodło się: zbyt wiele prób (429)",
        pt="Autenticação Pi-hole falhou: muitas tentativas (429)",
        ja="Pi-hole認証に失敗しました：試行回数が多すぎます（429）",
        zh="Pi-hole认证失败：尝试次数过多（429）",
    ))


async def _pihole_request(
    method: str,
    path: str,
    body: dict | None = None,
    params: dict | None = None,
    connection_id: str = "",
) -> dict:
    """
    Authenticated request to the Pi-hole API.
    Re-authenticates on 401.
    """
    config = await _get_pihole_config(connection_id)
    if not config["url"]:
        raise ValueError(_t(
            de="Pi-hole nicht konfiguriert. Bitte URL und Passwort in den Modul-Einstellungen setzen.",
            en="Pi-hole not configured. Please set URL and password in the module settings.",
            fr="Pi-hole non configuré. Veuillez définir l'URL et le mot de passe dans les paramètres du module.",
            es="Pi-hole no configurado. Por favor establezca la URL y la contraseña en la configuración del módulo.",
            it="Pi-hole non configurato. Per favore imposta URL e password nelle impostazioni del modulo.",
            nl="Pi-hole niet geconfigureerd. Stel alstublieft URL en wachtwoord in de module-instellingen in.",
            pl="Pi-hole nie skonfigurowany. Proszę ustawić URL i hasło w ustawieniach modułu.",
            pt="Pi-hole não configurado. Por favor defina a URL e a senha nas configurações do módulo.",
            ja="Pi-holeが設定されていません。モジュール設定でURLとパスワードを設定してください。",
            zh="未配置Pi-hole。请在模块设置中设置URL和密码。",
        ))

    base_url = config["url"]
    sid = await _authenticate(base_url, config["password"])

    url = f"{base_url}/api{path}"
    headers = {"sid": sid}

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.request(
            method, url, headers=headers, json=body, params=params
        )

        # Token expired → re-auth
        if resp.status_code == 401:
            _session_cache.pop(base_url, None)
            sid = await _authenticate(base_url, config["password"])
            headers["sid"] = sid
            resp = await client.request(
                method, url, headers=headers, json=body, params=params
            )

        resp.raise_for_status()

        if resp.text:
            return resp.json()
        return {}


# ── Tools ──────────────────────────────────────────

@tool
async def get_pihole_summary(connection_id: str = "") -> dict:
    """
    Pi-hole summary: blocked queries, percent blocked, total queries, status (enabled/disabled), clients.
    """
    data = await _pihole_request("GET", "/stats/summary", connection_id=connection_id)

    queries = data.get("queries", {})
    clients = data.get("clients", {})

    return {
        "status": "enabled" if data.get("gravity", {}).get("blocking") != "disabled" else "disabled",
        "dns_queries_today": queries.get("total", 0),
        "ads_blocked_today": queries.get("blocked", 0),
        "ads_percentage_today": round(queries.get("percent_blocked", 0), 1),
        "unique_domains": queries.get("unique_domains", 0),
        "queries_forwarded": queries.get("forwarded", 0),
        "queries_cached": queries.get("cached", 0),
        "clients_ever_seen": clients.get("total", 0),
        "unique_clients": clients.get("active", 0),
        "domains_blocked": data.get("gravity", {}).get("domains_being_blocked", 0),
    }


@tool
async def get_query_log(count: int = 100, connection_id: str = "") -> list[dict]:
    """
    Recent DNS queries from the Pi-hole query log.
    Shows domain, client, status (blocked/allowed/cached) and query type.

    Args:
        count: Number of entries (default: 100, max: 500)
    """
    count = min(count, 500)
    data = await _pihole_request("GET", "/queries", params={"length": count}, connection_id=connection_id)

    queries = data.get("queries", [])
    results = []
    for q in queries[:count]:
        results.append({
            "timestamp": q.get("time", 0),
            "type": q.get("type", ""),
            "domain": q.get("domain", ""),
            "client": q.get("client", {}).get("name", q.get("client", {}).get("ip", "")),
            "status": q.get("status", ""),
            "reply_type": q.get("reply", {}).get("type", ""),
            "duration_ms": q.get("reply", {}).get("time", 0),
        })
    return results


@tool
async def get_top_domains(count: int = 10, connection_id: str = "") -> dict:
    """
    Top permitted and blocked domains.

    Args:
        count: Number per category (default: 10)
    """
    data = await _pihole_request("GET", "/stats/top_domains", params={"count": count}, connection_id=connection_id)

    top_permitted = {}
    for entry in data.get("top_domains", []):
        top_permitted[entry.get("domain", "")] = entry.get("count", 0)

    data_blocked = await _pihole_request("GET", "/stats/top_domains", params={"count": count, "blocked": "true"}, connection_id=connection_id)

    top_blocked = {}
    for entry in data_blocked.get("top_domains", []):
        top_blocked[entry.get("domain", "")] = entry.get("count", 0)

    return {
        "top_permitted": top_permitted,
        "top_blocked": top_blocked,
    }


@tool
async def get_top_clients(count: int = 10, connection_id: str = "") -> dict:
    """
    Most active DNS clients (by query count).

    Args:
        count: Number of clients (default: 10)
    """
    data = await _pihole_request("GET", "/stats/top_clients", params={"count": count}, connection_id=connection_id)

    clients = {}
    for entry in data.get("top_clients", []):
        name = entry.get("name", "") or entry.get("ip", "")
        clients[name] = entry.get("count", 0)

    return {"top_clients": clients}


@tool
async def toggle_blocking(enable: bool = True, duration: int = 0, connection_id: str = "") -> str:
    """
    Enable or disable DNS blocking.
    Use for 'Blocking umschalten', 'aktivieren', or 'deaktivieren'.
    When disabling, a duration in seconds can be specified (0 = permanent).

    Args:
        enable: True = enable blocking, False = disable
        duration: Duration of disable in seconds (0 = permanent, only when enable=False)
    """
    body = {"blocking": enable}
    if not enable and duration > 0:
        body["timer"] = duration

    await _pihole_request("POST", "/dns/blocking", body=body, connection_id=connection_id)

    if enable:
        return _t(
            de="DNS-Blocking aktiviert.",
            en="DNS blocking enabled.",
            fr="Blocage DNS activé.",
            es="Bloqueo DNS habilitado.",
            it="Blocco DNS attivato.",
            nl="DNS-blokkering geactiveerd.",
            pl="Blokowanie DNS włączone.",
            pt="Bloqueio DNS ativado.",
            ja="DNSブロッキングが有効になりました。",
            zh="DNS阻止已启用。",
        )
    elif duration > 0:
        return _t(
            de=f"DNS-Blocking für {duration} Sekunden deaktiviert.",
            en=f"DNS blocking disabled for {duration} seconds.",
            fr=f"Blocage DNS désactivé pendant {duration} secondes.",
            es=f"Bloqueo DNS deshabilitado durante {duration} segundos.",
            it=f"Blocco DNS disattivato per {duration} secondi.",
            nl=f"DNS-blokkering gedeactiveerd voor {duration} seconden.",
            pl=f"Blokowanie DNS wyłączone na {duration} sekund.",
            pt=f"Bloqueio DNS desativado por {duration} segundos.",
            ja=f"DNSブロッキングを{duration}秒間無効にしました。",
            zh=f"DNS阻止已禁用 {duration} 秒。",
        )
    else:
        return _t(
            de="DNS-Blocking dauerhaft deaktiviert.",
            en="DNS blocking permanently disabled.",
            fr="Blocage DNS désactivé définitivement.",
            es="Bloqueo DNS deshabilitado permanentemente.",
            it="Blocco DNS disattivato permanentemente.",
            nl="DNS-blokkering permanent gedeactiveerd.",
            pl="Blokowanie DNS trwale wyłączone.",
            pt="Bloqueio DNS desativado permanentemente.",
            ja="DNSブロッキングを完全に無効にしました。",
            zh="DNS阻止已永久禁用。",
        )


@tool
async def get_blocklists(connection_id: str = "") -> list[dict]:
    """
    All configured blocklists (adlists) with status and domain count.
    """
    data = await _pihole_request("GET", "/lists", connection_id=connection_id)

    lists = []
    for entry in data.get("lists", []):
        lists.append({
            "id": entry.get("id", 0),
            "address": entry.get("address", ""),
            "enabled": entry.get("enabled", False),
            "comment": entry.get("comment", ""),
            "number": entry.get("number", 0),
        })
    return lists


@tool
async def add_domain_to_list(
    domain: str,
    list_type: str = "deny",
    kind: str = "exact",
    comment: str = "",
    connection_id: str = "",
) -> str:
    """
    Add a domain to the whitelist or blacklist.

    Args:
        domain: Domain name (e.g. 'example.com')
        list_type: 'allow' (whitelist) or 'deny' (blacklist)
        kind: 'exact' or 'regex'
        comment: Optional comment
    """
    if list_type not in ("allow", "deny"):
        return _t(
            de="Fehler: list_type muss 'allow' oder 'deny' sein.",
            en="Error: list_type must be 'allow' or 'deny'.",
            fr="Erreur: list_type doit être 'allow' ou 'deny'.",
            es="Error: list_type debe ser 'allow' o 'deny'.",
            it="Errore: list_type deve essere 'allow' o 'deny'.",
            nl="Fout: list_type moet 'allow' of 'deny' zijn.",
            pl="Błąd: list_type musi być 'allow' lub 'deny'.",
            pt="Erro: list_type deve ser 'allow' ou 'deny'.",
            ja="エラー: list_typeは'allow'または'deny'である必要があります。",
            zh="错误：list_type必须是'allow'或'deny'。",
        )
    if kind not in ("exact", "regex"):
        return _t(
            de="Fehler: kind muss 'exact' oder 'regex' sein.",
            en="Error: kind must be 'exact' or 'regex'.",
            fr="Erreur: kind doit être 'exact' ou 'regex'.",
            es="Error: kind debe ser 'exact' o 'regex'.",
            it="Errore: kind deve essere 'exact' o 'regex'.",
            nl="Fout: kind moet 'exact' of 'regex' zijn.",
            pl="Błąd: kind musi być 'exact' lub 'regex'.",
            pt="Erro: kind deve ser 'exact' ou 'regex'.",
            ja="エラー: kindは'exact'または'regex'である必要があります。",
            zh="错误：kind必须是'exact'或'regex'。",
        )

    body = {
        "domain": domain,
        "comment": comment or f"Added via Ninko",
    }

    await _pihole_request("POST", f"/domains/{list_type}/{kind}", body=body, connection_id=connection_id)

    label = "Whitelist" if list_type == "allow" else "Blacklist"
    return _t(
        de=f"Domain '{domain}' zur {label} ({kind}) hinzugefügt.",
        en=f"Domain '{domain}' added to {label} ({kind}).",
        fr=f"Domaine '{domain}' ajouté à {label} ({kind}).",
        es=f"Dominio '{domain}' agregado a {label} ({kind}).",
        it=f"Dominio '{domain}' aggiunto a {label} ({kind}).",
        nl=f"Domein '{domain}' toegevoegd aan {label} ({kind}).",
        pl=f"Domena '{domain}' dodana do {label} ({kind}).",
        pt=f"Domínio '{domain}' adicionado a {label} ({kind}).",
        ja=f"ドメイン '{domain}' を {label}（{kind}）に追加しました。",
        zh=f"域名 '{domain}' 已添加到 {label}（{kind}）。",
    )


@tool
async def remove_domain_from_list(
    domain: str,
    list_type: str = "deny",
    kind: str = "exact",
    connection_id: str = "",
) -> str:
    """
    Remove a domain from the whitelist or blacklist.

    Args:
        domain: Domain name
        list_type: 'allow' or 'deny'
        kind: 'exact' or 'regex'
    """
    if list_type not in ("allow", "deny"):
        return _t(
            de="Fehler: list_type muss 'allow' oder 'deny' sein.",
            en="Error: list_type must be 'allow' or 'deny'.",
            fr="Erreur: list_type doit être 'allow' ou 'deny'.",
            es="Error: list_type debe ser 'allow' o 'deny'.",
            it="Errore: list_type deve essere 'allow' o 'deny'.",
            nl="Fout: list_type moet 'allow' of 'deny' zijn.",
            pl="Błąd: list_type musi być 'allow' lub 'deny'.",
            pt="Erro: list_type deve ser 'allow' ou 'deny'.",
            ja="エラー: list_typeは'allow'または'deny'である必要があります。",
            zh="错误：list_type必须是'allow'或'deny'。",
        )
    if kind not in ("exact", "regex"):
        return _t(
            de="Fehler: kind muss 'exact' oder 'regex' sein.",
            en="Error: kind must be 'exact' or 'regex'.",
            fr="Erreur: kind doit être 'exact' ou 'regex'.",
            es="Error: kind debe ser 'exact' o 'regex'.",
            it="Errore: kind deve essere 'exact' o 'regex'.",
            nl="Fout: kind moet 'exact' of 'regex' zijn.",
            pl="Błąd: kind musi być 'exact' lub 'regex'.",
            pt="Erro: kind deve ser 'exact' ou 'regex'.",
            ja="エラー: kindは'exact'または'regex'である必要があります。",
            zh="错误：kind必须是'exact'或'regex'。",
        )

    # Pi-hole v6: DELETE with domain in body or as path
    await _pihole_request("DELETE", f"/domains/{list_type}/{kind}", body={"domain": domain}, connection_id=connection_id)

    label = "Whitelist" if list_type == "allow" else "Blacklist"
    return _t(
        de=f"Domain '{domain}' von der {label} ({kind}) entfernt.",
        en=f"Domain '{domain}' removed from {label} ({kind}).",
        fr=f"Domaine '{domain}' supprimé de {label} ({kind}).",
        es=f"Dominio '{domain}' eliminado de {label} ({kind}).",
        it=f"Dominio '{domain}' rimosso da {label} ({kind}).",
        nl=f"Domein '{domain}' verwijderd van {label} ({kind}).",
        pl=f"Domena '{domain}' usunięta z {label} ({kind}).",
        pt=f"Domínio '{domain}' removido de {label} ({kind}).",
        ja=f"ドメイン '{domain}' を {label}（{kind}）から削除しました。",
        zh=f"域名 '{domain}' 已从 {label}（{kind}）中移除。",
    )


@tool
async def get_pihole_system(connection_id: str = "") -> dict:
    """
    Pi-hole system information: version, uptime, gravity size, memory.
    """
    # Versions
    version_data = await _pihole_request("GET", "/info/version", connection_id=connection_id)
    # System
    try:
        system_data = await _pihole_request("GET", "/info/system", connection_id=connection_id)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
        system_data = {}
    # Gravity
    try:
        gravity_data = await _pihole_request("GET", "/info/gravity", connection_id=connection_id)
    except (RuntimeError, ValueError, TypeError, KeyError, OSError):
        gravity_data = {}

    return {
        "version_core": version_data.get("core", {}).get("version", ""),
        "version_ftl": version_data.get("ftl", {}).get("version", ""),
        "version_web": version_data.get("web", {}).get("version", ""),
        "uptime": system_data.get("uptime", 0),
        "memory_usage": system_data.get("memory", {}).get("ram", {}).get("used_percent", 0),
        "cpu_temp": system_data.get("sensors", {}).get("cpu_temp", None),
        "gravity_size": gravity_data.get("domains_being_blocked", 0),
        "gravity_last_update": gravity_data.get("last_update", {}).get("absolute", ""),
    }


@tool
async def get_custom_dns_records(connection_id: str = "") -> dict:
    """
    Retrieve all local DNS entries (custom DNS hosts) from Pi-hole.
    Returns a dictionary with {Domain: IP}.
    """
    data = await _pihole_request("GET", "/config", connection_id=connection_id)
    hosts = []
    
    if "config" in data and "dns" in data["config"] and "hosts" in data["config"]["dns"]:
        hosts = data["config"]["dns"]["hosts"]
    elif "dns" in data and "hosts" in data["dns"]:
        # Fallback for other API response structures
        hosts = data["dns"]["hosts"]
        
    records = {}
    for entry in hosts:
        parts = str(entry).split(" ", 1)
        if len(parts) == 2:
            ip, domain = parts
            records[domain.strip()] = ip.strip()
            
    return {"custom_dns_records": records}


@tool
async def add_custom_dns_record(domain: str, ip: str, connection_id: str = "") -> str:
    """
    Add a new local DNS entry (custom DNS host).

    Args:
        domain: Domain name (e.g. 'service.local')
        ip: IP address the domain should resolve to (e.g. '192.168.1.100')
    """
    import urllib.parse
    
    # URL-encoded path for PUT request in v6: /api/config/dns/hosts/{IP}%20{domain}
    encoded_entry = urllib.parse.quote(f"{ip} {domain}")
    
    await _pihole_request("PUT", f"/config/dns/hosts/{encoded_entry}", connection_id=connection_id)
    
    return _t(
        de=f"Local DNS Eintrag hinzugefügt: {domain} -> {ip}",
        en=f"Local DNS entry added: {domain} -> {ip}",
        fr=f"Entrée DNS locale ajoutée: {domain} -> {ip}",
        es=f"Entrada DNS local agregada: {domain} -> {ip}",
        it=f"Voce DNS locale aggiunta: {domain} -> {ip}",
        nl=f"Lokale DNS-invoer toegevoegd: {domain} -> {ip}",
        pl=f"Lokalny wpis DNS dodany: {domain} -> {ip}",
        pt=f"Entrada DNS local adicionada: {domain} -> {ip}",
        ja=f"ローカルDNSエントリを追加しました: {domain} -> {ip}",
        zh=f"已添加本地DNS条目: {domain} -> {ip}",
    )


@tool
async def remove_custom_dns_record(domain: str, ip: str, connection_id: str = "") -> str:
    """
    Delete a local DNS entry (custom DNS host) in Pi-hole.
    
    Args:
        domain: Domain name (e.g. 'service.local')
        ip: Assigned IP address of the entry (must match exactly)
    """
    import urllib.parse
    
    encoded_entry = urllib.parse.quote(f"{ip} {domain}")
    
    await _pihole_request("DELETE", f"/config/dns/hosts/{encoded_entry}", connection_id=connection_id)
    
    return _t(
        de=f"Local DNS Eintrag gelöscht: {domain} -> {ip}",
        en=f"Local DNS entry deleted: {domain} -> {ip}",
        fr=f"Entrée DNS locale supprimée: {domain} -> {ip}",
        es=f"Entrada DNS local eliminada: {domain} -> {ip}",
        it=f"Voce DNS locale eliminata: {domain} -> {ip}",
        nl=f"Lokale DNS-invoer verwijderd: {domain} -> {ip}",
        pl=f"Lokalny wpis DNS usunięty: {domain} -> {ip}",
        pt=f"Entrada DNS local removida: {domain} -> {ip}",
        ja=f"ローカルDNSエントリを削除しました: {domain} -> {ip}",
        zh=f"已删除本地DNS条目: {domain} -> {ip}",
    )


@tool
async def get_cname_records(connection_id: str = "") -> dict:
    """
    Retrieve all local CNAME records from Pi-hole.
    Returns a dictionary with {Domain: Target}.
    """
    data = await _pihole_request("GET", "/config", connection_id=connection_id)
    cnames = []
    if "config" in data and "dns" in data["config"] and "cnameRecords" in data["config"]["dns"]:
        cnames = data["config"]["dns"]["cnameRecords"]
    elif "dns" in data and "cnameRecords" in data["dns"]:
        cnames = data["dns"]["cnameRecords"]
        
    records = {}
    for entry in cnames:
        parts = str(entry).split(",", 1)
        if len(parts) == 2:
            records[parts[0].strip()] = parts[1].strip()
            
    return {"cname_records": records}


@tool
async def add_cname_record(domain: str, target: str, connection_id: str = "") -> str:
    """
    Add a new local CNAME record.
    
    Args:
        domain: Domain name (e.g. 'alias.local')
        target: Target the CNAME should point to (e.g. 'server.local')
    """
    import urllib.parse
    encoded_entry = urllib.parse.quote(f"{domain},{target}")
    await _pihole_request("PUT", f"/config/dns/cnameRecords/{encoded_entry}", connection_id=connection_id)
    return _t(
        de=f"CNAME Record hinzugefügt: {domain} -> {target}",
        en=f"CNAME record added: {domain} -> {target}",
        fr=f"Record CNAME ajouté: {domain} -> {target}",
        es=f"Registro CNAME agregado: {domain} -> {target}",
        it=f"Record CNAME aggiunto: {domain} -> {target}",
        nl=f"CNAME-record toegevoegd: {domain} -> {target}",
        pl=f"Rekord CNAME dodany: {domain} -> {target}",
        pt=f"Registro CNAME adicionado: {domain} -> {target}",
        ja=f"CNAMEレコードを追加しました: {domain} -> {target}",
        zh=f"已添加CNAME记录: {domain} -> {target}",
    )


@tool
async def remove_cname_record(domain: str, target: str, connection_id: str = "") -> str:
    """
    Delete a local CNAME record in Pi-hole.
    
    Args:
        domain: Domain name (e.g. 'alias.local')
        target: Assigned target (must match exactly)
    """
    import urllib.parse
    encoded_entry = urllib.parse.quote(f"{domain},{target}")
    await _pihole_request("DELETE", f"/config/dns/cnameRecords/{encoded_entry}", connection_id=connection_id)
    return _t(
        de=f"CNAME Record gelöscht: {domain} -> {target}",
        en=f"CNAME record deleted: {domain} -> {target}",
        fr=f"Record CNAME supprimé: {domain} -> {target}",
        es=f"Registro CNAME eliminado: {domain} -> {target}",
        it=f"Record CNAME eliminato: {domain} -> {target}",
        nl=f"CNAME-record verwijderd: {domain} -> {target}",
        pl=f"Rekord CNAME usunięty: {domain} -> {target}",
        pt=f"Registro CNAME removido: {domain} -> {target}",
        ja=f"CNAMEレコードを削除しました: {domain} -> {target}",
        zh=f"已删除CNAME记录: {domain} -> {target}",
    )


@tool
async def get_dhcp_leases(connection_id: str = "") -> list[dict]:
    """
    Retrieve all active DHCP leases from Pi-hole.
    Returns assigned IP addresses, MAC addresses and hostnames.
    """
    data = await _pihole_request("GET", "/dhcp/leases", connection_id=connection_id)
    return data.get("leases", [])


@tool
async def delete_dhcp_lease(ip: str, connection_id: str = "") -> str:
    """
    Delete an active DHCP lease by IP address.
    
    Args:
        ip: IP address whose lease should be deleted (e.g. '192.168.1.50')
    """
    await _pihole_request("DELETE", f"/dhcp/leases/{ip}", connection_id=connection_id)
    return _t(
        de=f"DHCP Lease für IP {ip} wurde gelöscht.",
        en=f"DHCP lease for IP {ip} has been deleted.",
        fr=f"Lease DHCP pour l'IP {ip} supprimé.",
        es=f"Concesión DHCP para IP {ip} eliminada.",
        it=f"Locazione DHCP per IP {ip} eliminata.",
        nl=f"DHCP-lease voor IP {ip} verwijderd.",
        pl=f"Lease DHCP dla IP {ip} usunięty.",
        pt=f"Concessão DHCP para IP {ip} excluída.",
        ja=f"IP {ip} のDHCPリースを削除しました。",
        zh=f"已删除IP {ip}的DHCP租约。",
    )


@tool
async def update_gravity(connection_id: str = "") -> str:
    """
    Trigger a manual gravity update (download and refresh blocklists).
    This process may take a moment.
    """
    await _pihole_request("POST", "/action/gravity", connection_id=connection_id)
    return _t(
        de="Gravity-Update wurde erfolgreich gestartet.",
        en="Gravity update started successfully.",
        fr="Mise à jour Gravity démarrée avec succès.",
        es="Actualización de Gravity iniciada con éxito.",
        it="Aggiornamento Gravity avviato con successo.",
        nl="Gravity-update succesvol gestart.",
        pl="Aktualizacja Gravity rozpoczęta pomyślnie.",
        pt="Atualização da Gravity iniciada com sucesso.",
        ja="Gravityアップデートが正常に開始されました。",
        zh="Gravity更新已成功启动。",
    )


@tool
async def flush_dns_cache(connection_id: str = "") -> str:
    """
    Restart the DNS service on Pi-hole and flush the DNS cache.
    """
    await _pihole_request("POST", "/action/restartdns", connection_id=connection_id)
    return _t(
        de="DNS Server neu gestartet und Cache geleert.",
        en="DNS server restarted and cache cleared.",
        fr="Serveur DNS redémarré et cache vidé.",
        es="Servidor DNS reiniciado y caché borrado.",
        it="Server DNS riavviato e cache svuotata.",
        nl="DNS-server herstart en cache geleegd.",
        pl="Serwer DNS ponownie uruchomiony i cache wyczyszczony.",
        pt="Servidor DNS reiniciado e cache limpo.",
        ja="DNSサーバーを再起動してキャッシュをクリアしました。",
        zh="DNS服务器已重启，缓存已清除。",
    )


@tool
async def flush_logs(connection_id: str = "") -> str:
    """
    Delete/flush all query logs (FTL/DNS logs) in Pi-hole.
    """
    await _pihole_request("POST", "/action/flush/logs", connection_id=connection_id)
    return _t(
        de="Logs wurden erfolgreich gelöscht.",
        en="Logs deleted successfully.",
        fr="Journaux supprimés avec succès.",
        es="Registros eliminados con éxito.",
        it="Log eliminati con successo.",
        nl="Logboeken succesvol verwijderd.",
        pl="Logi pomyślnie usunięte.",
        pt="Logs excluídos com sucesso.",
        ja="ログが正常に削除されました。",
        zh="日志已成功删除。",
    )


@tool
async def flush_network_table(connection_id: str = "") -> str:
    """
    Flush the network table (ARP cache / known devices) in the Pi-hole database.
    """
    await _pihole_request("POST", "/action/flush/network", connection_id=connection_id)
    return _t(
        de="Netzwerktabelle wurde erfolgreich geleert.",
        en="Network table flushed successfully.",
        fr="Table réseau vidée avec succès.",
        es="Tabla de red vaciada con éxito.",
        it="Tabella di rete svuotata con successo.",
        nl="Netwerktabel succesvol geleegd.",
        pl="Tabela sieci pomyślnie wyczyszczona.",
        pt="Tabela de rede limpa com sucesso.",
        ja="ネットワークテーブルが正常にクリアされました。",
        zh="网络表已成功刷新。",
    )


@tool
async def get_system_messages(connection_id: str = "") -> list[dict]:
    """
    Retrieve all active system warnings and messages (e.g. DNSMASQ_WARN) from Pi-hole.
    Returns message ID, type and message text.
    """
    data = await _pihole_request("GET", "/info/messages", connection_id=connection_id)
    return data.get("messages", [])


@tool
async def dismiss_system_message(message_id: str, connection_id: str = "") -> str:
    """
    Delete/dismiss a specific system warning in Pi-hole by ID.
    
    Args:
        message_id: ID of the message to delete.
    """
    await _pihole_request("DELETE", f"/info/messages/{message_id}", connection_id=connection_id)
    return _t(
        de=f"Systemmeldung mit ID {message_id} wurde gelöscht.",
        en=f"System message with ID {message_id} deleted.",
        fr=f"Message système avec l'ID {message_id} supprimé.",
        es=f"Mensaje del sistema con ID {message_id} eliminado.",
        it=f"Messaggio di sistema con ID {message_id} eliminato.",
        nl=f"Systeembericht met ID {message_id} verwijderd.",
        pl=f"Komunikat systemowy z ID {message_id} usunięty.",
        pt=f"Mensagem do sistema com ID {message_id} excluída.",
        ja=f"ID {message_id} のシステムメッセージを削除しました。",
        zh=f"已删除ID为 {message_id} 的系统消息。",
    )
