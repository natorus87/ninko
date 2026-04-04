"""
Nextcloud Module — LangGraph @tool functions.
Nextcloud WebDAV and OCS API.
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

logger = logging.getLogger("ninko.modules.nextcloud.tools")


async def _get_api_client(connection_id: str = "") -> dict:
    """Get Nextcloud API client."""
    if connection_id:
        conn = await ConnectionManager.get_connection("nextcloud", connection_id)
        if not conn:
            raise ValueError(
                _t(
                    de=f"Nextcloud-Verbindung mit ID '{connection_id}' nicht gefunden.",
                    en=f"Nextcloud connection with ID '{connection_id}' not found.",
                    fr=f"Connexion Nextcloud avec l'ID '{connection_id}' introuvable.",
                    es=f"Conexión Nextcloud con ID '{connection_id}' no encontrada.",
                    it=f"Connessione Nextcloud con ID '{connection_id}' non trovata.",
                    nl=f"Nextcloud-verbinding met ID '{connection_id}' niet gevonden.",
                    pl=f"Połączenie Nextcloud o ID '{connection_id}' nie znaleziono.",
                    pt=f"Conexão Nextcloud com ID '{connection_id}' não encontrada.",
                    ja=f"ID '{connection_id}' のNextcloud接続が見つかりません。",
                    zh=f"未找到ID为'{connection_id}'的Nextcloud连接。",
                )
            )
    else:
        conn = await ConnectionManager.get_default_connection("nextcloud")

    if conn:
        base_url = conn.config.get("url", "")
        user = conn.config.get("user", "")
        vault = get_vault()
        password = None
        password_path = conn.vault_keys.get("NEXTCLOUD_PASSWORD")
        if password_path:
            password = await vault.get_secret(password_path)
        if not password:
            password = os.environ.get("NEXTCLOUD_PASSWORD", "")
        return {"base_url": base_url, "user": user, "password": password}

    base_url = os.environ.get("NEXTCLOUD_HOST", "")
    user = os.environ.get("NEXTCLOUD_USER", "")
    vault = get_vault()
    password = await vault.get_secret("NEXTCLOUD_PASSWORD")

    if not base_url:
        raise ValueError(
            _t(
                de="Keine Nextcloud-Verbindung konfiguriert.",
                en="No Nextcloud connection configured.",
                fr="Aucune connexion Nextcloud configurée.",
                es="No hay conexión Nextcloud configurada.",
                it="Nessuna connessione Nextcloud configurata.",
                nl="Geen Nextcloud-verbinding geconfigureerd.",
                pl="Brak skonfigurowanego połączenia Nextcloud.",
                pt="Nenhuma conexão Nextcloud configurada.",
                ja="Nextcloud接続が設定されていません。",
                zh="未配置Nextcloud连接。",
            )
        )

    return {"base_url": base_url, "user": user, "password": password}


async def _dav_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make WebDAV request to Nextcloud."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/remote.php/dav/files/{client['user']}{path}"

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.request(method, url, json=json) as resp:
            if resp.status in [204, 201]:
                return {"status": "OK"}
            if resp.status == 207:
                text = await resp.text()
                return {"status": "OK", "content": text}
            resp.raise_for_status()
            return await resp.json()


async def _ocs_request(
    method: str, path: str, client: dict, json: Optional[dict] = None
) -> dict:
    """Make OCS request to Nextcloud."""
    base_url = client["base_url"].rstrip("/")
    url = f"{base_url}/ocs/v2.php{path}"
    headers = {
        "OCS-APIREQUEST": "true",
        "Content-Type": "application/json",
    }

    async with aiohttp.ClientSession(
        auth=aiohttp.BasicAuth(client["user"], client["password"]),
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=30),
    ) as session:
        async with session.request(method, url, json=json) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data.get("ocs", {}).get("data", data)


def _parse_webdav_list(xml_content: str) -> list[dict]:
    """Parse WebDAV PROPFIND response."""
    import xml.etree.ElementTree as ET

    files = []
    try:
        root = ET.fromstring(xml_content)
        ns = {"d": "DAV:"}
        for response in root.findall(".//d:response", ns):
            href = response.find("d:href", ns)
            propstat = response.find("d:propstat", ns)
            if href is None or propstat is None:
                continue

            path = href.text or ""
            if path.endswith("/"):
                path = path[:-1]
            name = path.split("/")[-1]

            res_type = propstat.find(".//d:resourcetype/d:collection", ns)
            is_dir = res_type is not None

            prop = propstat.find("d:prop", ns)
            size_el = prop.find("d:getcontentlength", ns) if prop is not None else None
            size = int(size_el.text) if size_el is not None and size_el.text else 0

            files.append(
                {
                    "name": name,
                    "path": path,
                    "type": "folder" if is_dir else "file",
                    "size": size,
                }
            )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.warning("Failed to parse WebDAV response: %s", e)

    return files


# ═══════════════════════════════════════════════════════
# Read-only tools
# ═══════════════════════════════════════════════════════


@tool
async def list_nextcloud_files(path: str = "/", connection_id: str = "") -> str:
    """
    List files and folders in Nextcloud.
    Use this to navigate the file system.
    """
    try:
        client = await _get_api_client(connection_id)
        if not path.startswith("/"):
            path = "/" + path

        data = await _dav_request("PROPFIND", path, client)
        content = data.get("content", "")

        if not content:
            return _t(
                de="Keine Dateien gefunden",
                en="No files found",
                fr="Aucun fichier trouvé",
                es="No se encontraron archivos",
                it="Nessun file trovato",
                nl="Geen bestanden gevonden",
                pl="Nie znaleziono plików",
                pt="Nenhum arquivo encontrado",
                ja="ファイルが見つかりません",
                zh="未找到文件",
            )

        files = _parse_webdav_list(content)
        if not files:
            return _t(
                de="Keine Dateien gefunden",
                en="No files found",
                fr="Aucun fichier trouvé",
                es="No se encontraron archivos",
                it="Nessun file trovato",
                nl="Geen bestanden gevonden",
                pl="Nie znaleziono plików",
                pt="Nenhum arquivo encontrado",
                ja="ファイルが見つかりません",
                zh="未找到文件",
            )

        lines = [
            "📁 "
            + _t(
                de="Dateien",
                en="Files",
                fr="Fichiers",
                es="Archivos",
                it="File",
                nl="Bestanden",
                pl="Pliki",
                pt="Arquivos",
                ja="ファイル",
                zh="文件",
            )
            + f" {path}"
        ]
        for f in files[:20]:
            icon = "📁" if f["type"] == "folder" else "📄"
            size = f.get("size", 0)
            size_str = f" ({size / 1024:.1f} KB)" if size > 0 else ""
            lines.append(f"  {icon} {f['name']}{size_str}")

        total = len(files)
        lines.append(f"\n✓ {total} Einträge")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_nextcloud_files failed: %s", e)
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
async def search_nextcloud_files(query: str, connection_id: str = "") -> str:
    """
    Search for files in Nextcloud.
    Use this to find files by name.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _ocs_request(
            "GET",
            f"/apps/files_sharing/api/v1/shares?path=/&search={query}",
            client,
        )

        if isinstance(data, dict):
            shares = data if isinstance(data, list) else data.get("data", [])
        else:
            shares = []

        if not shares:
            return _t(
                de=f"Keine Dateien gefunden für '{query}'",
                en=f"No files found for '{query}'",
                fr=f"Aucun fichier trouvé pour '{query}'",
                es=f"No se encontraron archivos para '{query}'",
                it=f"Nessun file trovato per '{query}'",
                nl=f"Geen bestanden gevonden voor '{query}'",
                pl=f"Nie znaleziono plików dla '{query}'",
                pt=f"Nenhum arquivo encontrado para '{query}'",
                ja=f"'{query}' のファイルが見つかりません",
                zh=f"未找到'{query}'的文件",
            )

        lines = [
            "🔍 "
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
        for s in shares[:15]:
            name = s.get("name", s.get("path", "-"))
            lines.append(f"  📄 {name}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("search_nextcloud_files failed: %s", e)
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
async def list_nextcloud_users(connection_id: str = "") -> str:
    """
    List users in Nextcloud.
    Use this to see all users.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _ocs_request("GET", "/cloud/users", client)

        users = data.get("users", []) if isinstance(data, dict) else data
        if not users:
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
        for u in users[:20]:
            lines.append(f"  👤 {u}")

        total = len(users)
        lines.append(f"\n✓ {total} Benutzer")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_nextcloud_users failed: %s", e)
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
async def get_nextcloud_user(user_id: str, connection_id: str = "") -> str:
    """
    Get details of a specific user.
    Use this to see user quota and details.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _ocs_request("GET", f"/cloud/users/{user_id}", client)

        lines = [
            "👤 "
            + _t(
                de="Benutzerdetails",
                en="User details",
                fr="Détails utilisateur",
                es="Detalles del usuario",
                it="Dettagli utente",
                nl="Gebruikersdetails",
                pl="Szczegóły użytkownika",
                pt="Detalhes do usuário",
                ja="ユーザー詳細",
                zh="用户详情",
            )
        ]
        lines.append(f"  {user_id}")
        if data.get("display-name"):
            lines.append(f"  Display Name: {data.get('display-name')}")
        if data.get("email"):
            lines.append(f"  Email: {data.get('email')}")
        if data.get("quota"):
            quota = data.get("quota", {})
            used = quota.get("used", 0)
            total = quota.get("total", 0)
            lines.append(
                f"  Quota: {used / 1024 / 1024:.1f} MB / {total / 1024 / 1024:.1f} MB"
            )
        lines.append(f"  Enabled: {data.get('enabled', True)}")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_nextcloud_user failed: %s", e)
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
async def list_nextcloud_shares(connection_id: str = "") -> str:
    """
    List shares in Nextcloud.
    Use this to see all shared files.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _ocs_request("GET", "/apps/files_sharing/api/v1/shares", client)

        shares = data if isinstance(data, list) else data.get("data", [])
        if not shares:
            return _t(
                de="Keine Shares gefunden",
                en="No shares found",
                fr="Aucun partage trouvé",
                es="No se encontraron compartidos",
                it="Nessuna condivisione trovata",
                nl="Geen shares gevonden",
                pl="Nie znaleziono udostępnień",
                pt="Nenhum compartilhamento encontrado",
                ja="Sharesが見つかりません",
                zh="未找到分享",
            )

        lines = [
            "🔗 "
            + _t(
                de="Shares",
                en="Shares",
                fr="Partages",
                es="Compartidos",
                it="Condivisioni",
                nl="Shares",
                pl="Udostępnienia",
                pt="Compartilhamentos",
                ja="シェア",
                zh="分享",
            )
        ]
        for s in shares[:15]:
            name = s.get("name", s.get("path", "-"))
            share_type = s.get("share_type", "link")
            type_icon = "🔗" if share_type == 3 else "👤" if share_type == 0 else "👥"
            lines.append(f"  {type_icon} {name}")

        total = len(shares)
        lines.append(f"\n✓ {total} Shares")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("list_nextcloud_shares failed: %s", e)
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
async def get_nextcloud_storage(connection_id: str = "") -> str:
    """
    Get storage usage statistics.
    Use this to see storage consumption.
    """
    try:
        client = await _get_api_client(connection_id)
        data = await _ocs_request("GET", f"/cloud/users/{client['user']}", client)

        lines = [
            "💾 "
            + _t(
                de="Speicher",
                en="Storage",
                fr="Stockage",
                es="Almacenamiento",
                it="Archiviazione",
                nl="Opslag",
                pl="Magazyn",
                pt="Armazenamento",
                ja="ストレージ",
                zh="存储",
            )
        ]
        if data.get("quota"):
            quota = data.get("quota", {})
            used = quota.get("used", 0)
            total = quota.get("total", -1)
            free = total - used if total > 0 else -1

            lines.append(f"  Used: {used / 1024 / 1024 / 1024:.2f} GB")
            if total > 0:
                lines.append(f"  Total: {total / 1024 / 1024 / 1024:.2f} GB")
                lines.append(f"  Free: {free / 1024 / 1024 / 1024:.2f} GB")
                pct = (used / total) * 100
                lines.append(f"  Usage: {pct:.1f}%")
        else:
            lines.append("  No quota set")

        return "\n".join(lines)
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("get_nextcloud_storage failed: %s", e)
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
async def create_nextcloud_folder(
    name: str, path: str = "/", connection_id: str = ""
) -> str:
    """
    Create a new folder in Nextcloud.
    Use this to create a directory.
    """
    try:
        client = await _get_api_client(connection_id)
        if not path.startswith("/"):
            path = "/" + path
        if not path.endswith("/"):
            path += "/"
        folder_path = f"{path}{name}"

        await _dav_request("MKCOL", folder_path, client)
        return _t(
            de=f"✅ Ordner erstellt: {folder_path}",
            en=f"✅ Folder created: {folder_path}",
            fr=f"✅ Dossier créé: {folder_path}",
            es=f"✅ Carpeta creada: {folder_path}",
            it=f"✅ Cartella creata: {folder_path}",
            nl=f"✅ Map gemaakt: {folder_path}",
            pl=f"✅ Utworzono folder: {folder_path}",
            pt=f"✅ Pasta criada: {folder_path}",
            ja=f"✅ フォルダを作成: {folder_path}",
            zh=f"✅ 已创建文件夹: {folder_path}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("create_nextcloud_folder failed: %s", e)
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
async def upload_nextcloud_file(
    content: str,
    path: str,
    connection_id: str = "",
) -> str:
    """
    Upload a file to Nextcloud.
    Use this to upload text content to a file.
    """
    try:
        client = await _get_api_client(connection_id)
        if not path.startswith("/"):
            path = "/" + path

        import io

        file_obj = io.BytesIO(content.encode("utf-8"))

        base_url = client["base_url"].rstrip("/")
        url = f"{base_url}/remote.php/dav/files/{client['user']}{path}"

        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(client["user"], client["password"]),
            timeout=aiohttp.ClientTimeout(total=30),
        ) as session:
            async with session.put(url, data=file_obj) as resp:
                resp.raise_for_status()

        return _t(
            de=f"✅ Datei hochgeladen: {path}",
            en=f"✅ File uploaded: {path}",
            fr=f"✅ Fichier téléversé: {path}",
            es=f"✅ Archivo subido: {path}",
            it=f"✅ File caricato: {path}",
            nl=f"✅ Bestand geüpload: {path}",
            pl=f"✅ Przesłano plik: {path}",
            pt=f"✅ Arquivo enviado: {path}",
            ja=f"✅ ファイルをアップロード: {path}",
            zh=f"✅ 已上传文件: {path}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("upload_nextcloud_file failed: %s", e)
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
async def delete_nextcloud_file(path: str, connection_id: str = "") -> str:
    """
    Delete a file or folder in Nextcloud.
    Use this to delete a file.
    """
    try:
        client = await _get_api_client(connection_id)
        if not path.startswith("/"):
            path = "/" + path
        if not path.endswith("/"):
            path += "/"

        await _dav_request("DELETE", path, client)
        return _t(
            de=f"✅ Datei gelöscht: {path}",
            en=f"✅ File deleted: {path}",
            fr=f"✅ Fichier supprimé: {path}",
            es=f"✅ Archivo eliminado: {path}",
            it=f"✅ File eliminato: {path}",
            nl=f"✅ Bestand verwijderd: {path}",
            pl=f"✅ Plik usunięty: {path}",
            pt=f"✅ Arquivo excluído: {path}",
            ja=f"✅ ファイルを削除: {path}",
            zh=f"✅ 已删除文件: {path}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("delete_nextcloud_file failed: %s", e)
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
async def create_nextcloud_share(
    path: str,
    share_type: str = "link",
    permissions: int = 1,
    connection_id: str = "",
) -> str:
    """
    Create a share for a file or folder.
    Use this to create a public or user share.
    """
    try:
        client = await _get_api_client(connection_id)
        if not path.startswith("/"):
            path = "/" + path

        share_type_map = {"link": 3, "user": 0, "group": 1}
        stype = share_type_map.get(share_type, 3)

        data = await _ocs_request(
            "POST",
            "/apps/files_sharing/api/v1/shares",
            client,
            json={
                "path": path,
                "shareType": stype,
                "permissions": permissions,
            },
        )

        share_link = data.get("url", "")
        return _t(
            de=f"✅ Share erstellt: {share_link or path}",
            en=f"✅ Share created: {share_link or path}",
            fr=f"✅ Partage créé: {share_link or path}",
            es=f"✅ Compartido creado: {share_link or path}",
            it=f"✅ Condivisione creata: {share_link or path}",
            nl=f"✅ Share gemaakt: {share_link or path}",
            pl=f"✅ Utworzono udostępnienie: {share_link or path}",
            pt=f"✅ Compartilhamento criado: {share_link or path}",
            ja=f"✅ シェアを作成: {share_link or path}",
            zh=f"✅ 已创建分享: {share_link or path}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("create_nextcloud_share failed: %s", e)
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
async def create_nextcloud_user(
    user_id: str,
    password: str,
    email: str = "",
    connection_id: str = "",
) -> str:
    """
    Create a new user in Nextcloud.
    Use this to create a new user account.
    """
    try:
        client = await _get_api_client(connection_id)
        user_data = {"userid": user_id, "password": password}
        if email:
            user_data["email"] = email

        await _ocs_request("POST", "/cloud/users", client, json=user_data)
        return _t(
            de=f"✅ Benutzer erstellt: {user_id}",
            en=f"✅ User created: {user_id}",
            fr=f"✅ Utilisateur créé: {user_id}",
            es=f"✅ Usuario creado: {user_id}",
            it=f"✅ Utente creato: {user_id}",
            nl=f"✅ Gebruiker gemaakt: {user_id}",
            pl=f"✅ Utworzono użytkownika: {user_id}",
            pt=f"✅ Usuário criado: {user_id}",
            ja=f"✅ ユーザーを作成: {user_id}",
            zh=f"✅ 已创建用户: {user_id}",
        )
    except (RuntimeError, ValueError, TypeError, KeyError, aiohttp.ClientError, OSError) as e:
        logger.error("create_nextcloud_user failed: %s", e)
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
