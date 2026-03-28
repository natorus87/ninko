"""
WordPress Modul – Spezialist-Agent für WordPress-Verwaltung.
"""

from __future__ import annotations

from agents.base_agent import BaseAgent
from .tools import (
    get_site_info,
    get_updates_info,
    list_plugins,
    search_plugins,
    install_plugin,
    activate_plugin,
    deactivate_plugin,
    update_plugin,
    delete_plugin,
    list_pages,
    get_page,
    create_page,
    update_page,
    delete_page,
    list_posts,
    get_post,
    create_post,
    update_post,
    delete_post,
    list_categories,
    create_category,
    list_tags,
    create_tag,
    list_users,
    get_current_user,
    get_site_settings,
    update_site_settings,
    list_media,
)

WORDPRESS_SYSTEM_PROMPT = """Du bist der WordPress-Spezialist von Ninko.

Deine Fähigkeiten:
- **Site-Info**: WordPress-Version, Einstellungen, Updates prüfen
- **Plugin-Management**: Plugins auflisten, suchen, installieren, aktivieren, deaktivieren, aktualisieren, löschen
- **Seiten-Management**: Seiten auflisten, erstellen, bearbeiten, löschen
- **Beitrags-Management**: Blog-Beiträge auflisten, erstellen, bearbeiten, löschen
- **Kategorien & Tags**: Kategorien und Tags verwalten
- **Benutzer-Management**: Benutzer auflisten, eigene Berechtigungen prüfen
- **Einstellungen**: Site-Titel, Untertitel, Sprache ändern
- **Medien**: Hochgeladene Dateien auflisten

WICHTIG – SOFORT HANDELN:
- Wenn der User dich bittet etwas zu erstellen, ändern oder löschen, MACH ES SOFORT über die passenden Tools!
- Erkläre dem User NIEMALS wie er es manuell im Dashboard machen kann – das ist deine Aufgabe!
- Nutze `update_page` um Seiten zu bearbeiten, `update_post` um Beiträge zu ändern, `create_page` um Seiten zu erstellen etc.
- Der User kommt zu DICH weil er es NICHT selbst machen will. Handle!

WICHTIGE LIMITATIONEN:
- Du kannst KEINE Themes installieren, ändern oder gestalten. Bei Anfragen zum Redesign/Neugestaltung erkläre kurz warum und biete Alternativen (z.B. manuell im WP-Admin unter Design → Themes).
- Du bist KEIN Webdesigner. Halte Antworten kurz und präzise – maximal 8 Zeilen. KEINE langen Tabellen mit Site-Infos wenn der User nicht explizit danach fragt.

Verhaltensregeln:
- Sei kurz und präzise (max. 8 Zeilen pro Antwort)
- Bei Seiten/Beiträgen: Inhalte in HTML akzeptieren
- Plugin-Slugs im Format 'ordner/datei' (z.B. 'akismet/akismet')
- Bei destruktiven Aktionen (delete_plugin, delete_page mit force=true, delete_post mit force=true) IMMER Bestätigung einholen
- Seiten/Beiträge standardmäßig als 'draft' erstellen, nicht als 'publish'

WordPress REST API Besonderheiten:
- Seiten-IDs und Beitrag-IDs sind numerisch
- Plugin-Slugs: 'ordner/hauptdatei' ohne .php
- Kategorie/Tag-IDs sind numerisch
- Status-Werte: 'publish', 'draft', 'pending', 'private', 'trash'
- Application Passwords werden unter Benutzer → Profil → Application Passwords erstellt"""


class WordPressAgent(BaseAgent):
    """WordPress-Spezialist mit allen WP-Management-Tools."""

    def __init__(self) -> None:
        super().__init__(
            name="wordpress",
            system_prompt=WORDPRESS_SYSTEM_PROMPT,
            tools=[
                # Site
                get_site_info,
                get_updates_info,
                # Plugins
                list_plugins,
                search_plugins,
                install_plugin,
                activate_plugin,
                deactivate_plugin,
                update_plugin,
                delete_plugin,
                # Pages
                list_pages,
                get_page,
                create_page,
                update_page,
                delete_page,
                # Posts
                list_posts,
                get_post,
                create_post,
                update_post,
                delete_post,
                # Categories & Tags
                list_categories,
                create_category,
                list_tags,
                create_tag,
                # Users
                list_users,
                get_current_user,
                # Settings
                get_site_settings,
                update_site_settings,
                # Media
                list_media,
            ],
        )

    def _select_tools_for_request(self, message: str):  # type: ignore[override]
        """WordPress: IMMER alle Tools verfügbar – JIT-Filterung deaktiviert."""
        return self.tools
