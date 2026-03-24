"""
Ninko – Soul-Manager.
Verwaltet Soul MDs: die persistente Identität jedes Agenten.

- Ninkos eigene Soul MD wird aus backend/souls/ninko.md geladen (built-in, im Image).
- Agent-Souls werden in Redis gespeichert (ninko:souls) und beim Start geladen.
- Dynamisch erstellte Agenten erhalten beim Register automatisch eine generierte Soul MD.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ninko.core.soul_manager")

REDIS_KEY = "ninko:souls"

# Pfad zu den eingebauten Soul-Dateien (im Docker-Image)
_SOULS_DIR = Path(__file__).resolve().parent.parent / "souls"


class SoulManager:
    """
    Verwaltet Soul MDs aller Agenten.

    Soul MDs definieren Identität, Zweck und Verhaltensgrundsätze eines Agenten.
    Sie werden an den Anfang des System-Prompts injiziert und geben jedem
    Agenten eine konsistente, persistente Persönlichkeit.

    Priorität beim Laden:
    1. Built-in Soul aus backend/souls/<agent_name>.md  (unveränderlich, im Image)
    2. Redis-gespeicherte Soul (überschreibbar, persistent über Container-Neustarts)
    """

    def __init__(self) -> None:
        # agent_name → Soul MD Text
        self._souls: dict[str, str] = {}

    # ──────────────────────────────────────────────────────────────────────
    # Startup / Laden
    # ──────────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """
        Lädt alle built-in Soul MDs aus backend/souls/.
        Wird synchron beim App-Start aufgerufen (vor DynamicAgentPool).
        """
        if not _SOULS_DIR.is_dir():
            logger.debug("Kein souls/-Verzeichnis gefunden – überspringe built-in Souls.")
            return

        loaded = 0
        for soul_file in _SOULS_DIR.glob("*.md"):
            agent_name = soul_file.stem  # Dateiname ohne Endung = Agent-Name
            try:
                content = soul_file.read_text(encoding="utf-8").strip()
                if content:
                    self._souls[agent_name] = content
                    loaded += 1
                    logger.debug("Soul MD geladen: '%s' aus %s", agent_name, soul_file.name)
            except Exception as exc:
                logger.warning("Soul-Datei '%s' konnte nicht geladen werden: %s", soul_file, exc)

        logger.info("SoulManager: %d built-in Soul(s) geladen.", loaded)

    async def load_from_redis(self) -> None:
        """
        Lädt dynamisch erstellte Agent-Souls aus Redis.
        Überschreibt built-in Souls NICHT (built-in haben Vorrang).
        Wird async beim App-Start aufgerufen (nach load()).
        """
        try:
            from core.redis_client import get_redis
            redis = get_redis()
            raw = await redis.connection.get(REDIS_KEY)
            if not raw:
                return

            souls_data: dict[str, str] = json.loads(raw)
            loaded = 0
            for agent_name, content in souls_data.items():
                if agent_name not in self._souls:  # built-in hat Vorrang
                    self._souls[agent_name] = content
                    loaded += 1

            if loaded:
                logger.info("SoulManager: %d Agent-Soul(s) aus Redis geladen.", loaded)
        except Exception as exc:
            logger.warning("SoulManager.load_from_redis fehlgeschlagen: %s", exc)

    # ──────────────────────────────────────────────────────────────────────
    # Zugriff
    # ──────────────────────────────────────────────────────────────────────

    def get_soul(self, agent_name: str) -> str | None:
        """Gibt die Soul MD für einen Agenten zurück, oder None wenn keine existiert."""
        return self._souls.get(agent_name)

    def list_souls(self) -> dict[str, str]:
        """Gibt alle bekannten Souls zurück: {agent_name: soul_md}."""
        return dict(self._souls)

    def has_soul(self, agent_name: str) -> bool:
        """Prüft ob für einen Agenten eine Soul MD existiert."""
        return agent_name in self._souls

    # ──────────────────────────────────────────────────────────────────────
    # Persistenz
    # ──────────────────────────────────────────────────────────────────────

    async def save_soul(self, agent_name: str, content: str) -> None:
        """
        Speichert eine Soul MD in Redis (und im Speicher).
        Built-in Souls (orchestrator, monitor etc.) können überschrieben werden,
        aber nur durch explizite Nutzer-Anweisung.
        """
        self._souls[agent_name] = content

        try:
            from core.redis_client import get_redis
            redis = get_redis()
            raw = await redis.connection.get(REDIS_KEY)
            souls_data: dict[str, str] = json.loads(raw) if raw else {}
            souls_data[agent_name] = content
            await redis.connection.set(REDIS_KEY, json.dumps(souls_data, ensure_ascii=False))
            logger.info("Soul MD für Agent '%s' in Redis gespeichert.", agent_name)
        except Exception as exc:
            logger.warning("Soul MD konnte nicht in Redis gespeichert werden: %s", exc)

    async def delete_soul(self, agent_name: str) -> bool:
        """
        Löscht eine Soul MD aus dem Speicher und Redis.
        Built-in Souls (aus backend/souls/) werden NICHT gelöscht.
        Gibt True zurück wenn tatsächlich gelöscht wurde.
        """
        # Built-in Souls schützen
        built_in_path = _SOULS_DIR / f"{agent_name}.md"
        if built_in_path.exists():
            logger.warning("Built-in Soul '%s' kann nicht gelöscht werden.", agent_name)
            return False

        if agent_name not in self._souls:
            return False

        del self._souls[agent_name]

        try:
            from core.redis_client import get_redis
            redis = get_redis()
            raw = await redis.connection.get(REDIS_KEY)
            if raw:
                souls_data: dict[str, str] = json.loads(raw)
                souls_data.pop(agent_name, None)
                await redis.connection.set(REDIS_KEY, json.dumps(souls_data, ensure_ascii=False))
        except Exception as exc:
            logger.warning("Soul-Löschung in Redis fehlgeschlagen: %s", exc)

        logger.info("Soul MD für Agent '%s' gelöscht.", agent_name)
        return True

    # ──────────────────────────────────────────────────────────────────────
    # Generierung
    # ──────────────────────────────────────────────────────────────────────

    def generate_soul(
        self,
        name: str,
        purpose: str,
        capabilities: list[str] | None = None,
    ) -> str:
        """
        Generiert eine Soul MD für einen neuen dynamischen Agenten anhand einer Vorlage.
        Die Soul MD erbt Ninkos Grundprinzipien und wird auf den Agenten zugeschnitten.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        caps = capabilities or []
        cap_lines = "\n".join(f"- {c}" for c in caps) if caps else "- Aufgabenspezifische Ausführung"

        return f"""# Soul MD – {name}

## Identity
Name: {name}
Erstellt von: Ninko
Erstellt am: {now}
Typ: Dynamisch

## Purpose
{purpose}

## Capabilities
{cap_lines}

## Behavior Guidelines
- Fokus strikt auf den definierten Purpose
- Ergebnisse immer strukturiert an Ninko zurückgeben
- Keine eigenständigen Entscheidungen außerhalb des eigenen Scopes
- Verhalten konsistent mit Ninkos Grundprinzipien

## Constraints
- Keine Aktionen außerhalb der definierten Capabilities
- Keine direkte Kommunikation mit dem Nutzer (außer explizit erlaubt)
- Keine Veränderung anderer Agenten oder des Agenten-Pools

## Escalation Rules
- Aufgabe außerhalb des eigenen Scopes → an Ninko zurückgeben
- Fehler bei der Ausführung → Fehlerbeschreibung + Kontext an Ninko melden
"""

    def generate_module_soul(
        self,
        name: str,
        display_name: str,
        description: str,
        tool_names: list[str],
    ) -> str:
        """
        Generiert eine Soul MD für einen Modul-Agenten basierend auf seinem Manifest.
        Modul-Souls sind statisch (Typ: Statisch) und beschreiben den Spezialisten-Charakter.
        """
        cap_lines = "\n".join(f"- {_tool_name_to_label(t)}" for t in tool_names) if tool_names else "- Modulspezifische Ausführung"

        return f"""# Soul MD – {display_name}

## Identity
Name: {display_name}
Rolle: {display_name}-Spezialist von Ninko
Typ: Statisch (Modul-Agent)

## Purpose
{description}

## Capabilities
{cap_lines}

## Behavior Guidelines
- Fokus strikt auf den definierten Modulbereich
- Ergebnisse immer strukturiert und vollständig zurückgeben
- Bei destruktiven Aktionen: kurze Bestätigung einholen
- Verhalten konsistent mit Ninkos Grundprinzipien

## Constraints
- Keine Aktionen außerhalb der definierten Capabilities
- Keine Veränderung anderer Module oder des Agenten-Pools
- Sicherheitsrelevante Aktionen erfordern Bestätigung

## Escalation Rules
- Aufgabe außerhalb des eigenen Modulbereichs → an Ninko zurückgeben
- Fehler bei der Ausführung → Fehlerbeschreibung + Kontext an Ninko melden
- Sicherheitsrelevante Aktionen → Bestätigung einholen
"""


# ── Hilfsfunktionen ───────────────────────────────────────────────────────

def _tool_name_to_label(tool_name: str) -> str:
    """Wandelt snake_case Tool-Namen in lesbares Label um (z.B. 'get_cluster_status' → 'Cluster-Status abrufen')."""
    return tool_name.replace("_", " ").replace("get ", "").replace("set ", "").strip().title()


# ── Globaler Singleton ────────────────────────────────────────────────────

_global_soul_manager: SoulManager | None = None


def get_soul_manager() -> SoulManager:
    """Gibt den globalen SoulManager zurück (ggf. neu erstellen)."""
    global _global_soul_manager
    if _global_soul_manager is None:
        _global_soul_manager = SoulManager()
    return _global_soul_manager
