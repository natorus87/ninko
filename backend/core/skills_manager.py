"""
Ninko Skills Manager – Prozedurales Domänenwissen für Agenten.

Skills sind Markdown-Dateien (SKILL.md) mit YAML-ähnlichem Frontmatter.
Sie werden lazy in den Agenten-Kontext injiziert wenn eine Aufgabe passt.

Verzeichnisse (in Suchreihenfolge):
  1. backend/skills/    – Built-in Skills (im Docker-Image gebacken)
  2. /app/data/skills/  – Runtime/User-Skills (persistentes Volume, survives restarts)

Format einer SKILL.md:
    ---
    name: kubernetes-incident-response
    description: Systematische Diagnose von K8s Pod-Fehlern, CrashLoopBackOff, OOMKilled
    modules: [kubernetes]
    ---

    ## Diagnose-Ablauf
    ...

`modules` kann eine Liste von Modul-Namen sein (nur für diese Agenten injizieren)
oder weggelassen werden / `*` für alle Agenten.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger("ninko.core.skills_manager")

# Maximale Anzahl Skills die pro Request injiziert werden (Token-Budget)
_MAX_INJECTED_SKILLS = 2
# Mindest-Score für Injection (0–1)
_MATCH_THRESHOLD = 0.12


@dataclass
class Skill:
    name: str
    description: str
    modules: list[str]          # [] = alle Agenten
    location: Path
    content: str                # Voller Markdown-Body (ohne Frontmatter)
    keywords: list[str] = field(default_factory=list)  # Aus Description extrahiert


class SkillsManager:
    """
    Lädt SKILL.md-Dateien aus Built-in- und Runtime-Verzeichnissen,
    matched sie gegen eingehende Anfragen und injiziert passende Skills
    als Kontext in den Agenten-Prompt.
    """

    def __init__(self) -> None:
        self._skills: list[Skill] = []
        self._loaded = False

        # Suchpfade: Built-in zuerst, dann persistentes Data-Volume
        base = Path(__file__).resolve().parent.parent
        self._search_paths: list[Path] = [
            base / "skills",            # backend/skills/
            Path("/app/data/skills"),   # Runtime (Docker-Volume)
            base.parent / "data" / "skills",  # Local dev fallback
        ]

    # ──────────────────────────────────────────────────────────────────────
    # Laden
    # ──────────────────────────────────────────────────────────────────────

    def load(self) -> None:
        """Scannt alle Suchpfade und lädt SKILL.md-Dateien."""
        self._skills.clear()
        loaded = 0

        for search_path in self._search_paths:
            if not search_path.exists():
                continue
            for skill_dir in sorted(search_path.iterdir()):
                skill_file = skill_dir / "SKILL.md"
                if skill_dir.is_dir() and skill_file.exists():
                    skill = self._parse_skill(skill_file)
                    if skill:
                        # Vorhandene Skill mit gleichem Namen überschreiben
                        # (Runtime-Skills haben höhere Priorität als Built-in)
                        self._skills = [s for s in self._skills if s.name != skill.name]
                        self._skills.append(skill)
                        loaded += 1

        self._loaded = True
        logger.info("SkillsManager: %d Skills geladen.", loaded)

    def reload(self) -> None:
        """Erzwingt Neu-Laden aller Skills (nach install_skill aufrufen)."""
        self.load()

    # ──────────────────────────────────────────────────────────────────────
    # Parsing
    # ──────────────────────────────────────────────────────────────────────

    def _parse_skill(self, path: Path) -> Skill | None:
        """Parst eine SKILL.md-Datei und gibt ein Skill-Objekt zurück."""
        try:
            raw = path.read_text(encoding="utf-8")
        except Exception as exc:
            logger.warning("SKILL.md konnte nicht gelesen werden (%s): %s", path, exc)
            return None

        # Frontmatter extrahieren (--- ... ---)
        fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)", raw, re.DOTALL)
        if not fm_match:
            logger.warning("SKILL.md ohne Frontmatter übersprungen: %s", path)
            return None

        fm_text, body = fm_match.group(1), fm_match.group(2).strip()

        # Einfaches Key-Value-Parsing (kein pyyaml benötigt)
        meta: dict[str, str | list] = {}
        for line in fm_text.splitlines():
            line = line.strip()
            if ":" in line:
                key, _, val = line.partition(":")
                key = key.strip()
                val = val.strip()
                # Listen: [a, b, c] oder [kubernetes]
                list_match = re.match(r"\[(.*)\]", val)
                if list_match:
                    items = [i.strip().strip("'\"") for i in list_match.group(1).split(",")]
                    meta[key] = [i for i in items if i]
                else:
                    meta[key] = val.strip("'\"")

        name = str(meta.get("name", path.parent.name))
        description = str(meta.get("description", ""))
        modules_raw = meta.get("modules", [])
        if isinstance(modules_raw, str):
            modules = [] if modules_raw in ("*", "") else [modules_raw]
        else:
            modules = [str(m) for m in modules_raw if str(m) not in ("*", "")]

        if not description:
            logger.warning("SKILL.md ohne description übersprungen: %s", path)
            return None

        # Keywords aus Description extrahieren
        keywords = _tokenize(description)

        return Skill(
            name=name,
            description=description,
            modules=modules,
            location=path,
            content=body,
            keywords=keywords,
        )

    # ──────────────────────────────────────────────────────────────────────
    # Matching & Injection
    # ──────────────────────────────────────────────────────────────────────

    def find_matching_skills(self, message: str, agent_name: str) -> list[Skill]:
        """
        Findet passende Skills für eine Anfrage.

        Berücksichtigt:
        - Modul-Filter (modules-Feld)
        - Keyword-Überschneidung zwischen Anfrage und Skill-Description
        - Maximal _MAX_INJECTED_SKILLS zurückgeben
        """
        if not self._loaded:
            self.load()

        if not self._skills:
            return []

        msg_words = set(_tokenize(message))
        if not msg_words:
            return []

        scored: list[tuple[float, Skill]] = []

        for skill in self._skills:
            # Modul-Filter: Skill nur für bestimmte Agenten?
            if skill.modules and agent_name not in skill.modules:
                continue

            # Keyword-Überschneidung
            skill_words = set(skill.keywords)
            common = msg_words & skill_words
            if not common:
                continue

            score = len(common) / max(len(msg_words), 1)
            if score >= _MATCH_THRESHOLD:
                scored.append((score, skill))

        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [s for _, s in scored[:_MAX_INJECTED_SKILLS]]

        if selected:
            logger.debug(
                "SkillsManager: %d passende Skills für Agent '%s': %s",
                len(selected), agent_name, [s.name for s in selected],
            )

        return selected

    def build_injection(self, skills: list[Skill]) -> str:
        """
        Baut den Injektions-Text für den System-Prompt aus einer Liste von Skills.
        """
        if not skills:
            return ""

        parts = ["SKILL-WISSEN (prozedurales Domänenwissen – NUR wenn relevant anwenden):"]
        for skill in skills:
            parts.append(f"\n### Skill: {skill.name}\n{skill.content}")

        return "\n".join(parts)

    # ──────────────────────────────────────────────────────────────────────
    # Installation (persistent)
    # ──────────────────────────────────────────────────────────────────────

    def install_skill(
        self,
        name: str,
        description: str,
        content: str,
        modules: list[str] | None = None,
    ) -> Path:
        """
        Schreibt eine neue SKILL.md in data/skills/ (persistentes Volume).
        Lädt den SkillsManager danach automatisch neu.

        Gibt den Pfad zur erstellten SKILL.md zurück.
        """
        # Persistentes Verzeichnis bevorzugen
        target_base: Path | None = None
        for p in self._search_paths:
            if "data" in str(p):
                target_base = p
                break
        if target_base is None:
            target_base = self._search_paths[-1]

        # Verzeichnis anlegen
        skill_dir = target_base / _slugify(name)
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_file = skill_dir / "SKILL.md"

        # Frontmatter zusammenbauen
        modules_line = ""
        if modules:
            modules_line = f"\nmodules: [{', '.join(modules)}]"

        fm = f"---\nname: {_slugify(name)}\ndescription: {description}{modules_line}\n---\n\n"
        skill_file.write_text(fm + content, encoding="utf-8")

        logger.info("Skill installiert: '%s' → %s", name, skill_file)

        # Hot-Reload
        self.reload()

        return skill_file

    # ──────────────────────────────────────────────────────────────────────
    # Hilfsmethoden
    # ──────────────────────────────────────────────────────────────────────

    def get_catalog(self) -> list[dict]:
        """Gibt den Skills-Katalog als Liste von Dicts zurück (für Status-Anzeige)."""
        if not self._loaded:
            self.load()
        return [
            {
                "name": s.name,
                "description": s.description,
                "modules": s.modules,
                "location": str(s.location),
                "builtin": "data" not in str(s.location),
            }
            for s in self._skills
        ]

    def get_skill(self, name: str) -> Skill | None:
        """Gibt einen einzelnen Skill per Name zurück."""
        if not self._loaded:
            self.load()
        return next((s for s in self._skills if s.name == name), None)

    def get_skill_full(self, name: str) -> dict | None:
        """Gibt einen Skill inkl. vollem Content-Text zurück."""
        s = self.get_skill(name)
        if not s:
            return None
        return {
            "name": s.name,
            "description": s.description,
            "modules": s.modules,
            "content": s.content,
            "location": str(s.location),
            "builtin": "data" not in str(s.location),
        }

    def update_skill(
        self,
        name: str,
        description: str,
        content: str,
        modules: list[str] | None = None,
    ) -> Path:
        """
        Aktualisiert einen bestehenden Skill (nur Runtime-Skills in data/skills/).
        Built-in Skills werden als neue Runtime-Version gespeichert (Override).
        """
        return self.install_skill(name, description, content, modules)

    def delete_skill(self, name: str) -> bool:
        """
        Löscht einen Runtime-Skill aus data/skills/.
        Built-in Skills (in backend/skills/) können nicht gelöscht werden.
        Gibt True bei Erfolg zurück.
        """
        if not self._loaded:
            self.load()

        skill = self.get_skill(name)
        if not skill:
            return False

        # Nur Runtime-Skills (im data/-Pfad) dürfen gelöscht werden
        if "data" not in str(skill.location):
            raise PermissionError(f"Built-in Skill '{name}' kann nicht gelöscht werden.")

        skill_dir = skill.location.parent
        try:
            import shutil
            shutil.rmtree(skill_dir)
            logger.info("Skill gelöscht: '%s' (%s)", name, skill_dir)
        except Exception as exc:
            logger.error("Skill-Löschung fehlgeschlagen (%s): %s", skill_dir, exc)
            return False

        self.reload()
        return True


# ── Hilfsfunktionen ─────────────────────────────────────────────────────────

def _tokenize(text: str) -> list[str]:
    """Zerlegt Text in bereinigte Tokens (mind. 3 Zeichen)."""
    words = re.sub(r"[\W_]+", " ", text.lower()).split()
    return [w for w in words if len(w) >= 3]


def _slugify(name: str) -> str:
    """Konvertiert einen Namen in einen URL-sicheren Verzeichnisnamen."""
    return re.sub(r"[^\w-]", "-", name.lower()).strip("-")


# ── Globaler Singleton ────────────────────────────────────────────────────────

_global_skills_manager: SkillsManager | None = None


def get_skills_manager() -> SkillsManager:
    """Gibt den globalen SkillsManager zurück (ggf. neu erstellen)."""
    global _global_skills_manager
    if _global_skills_manager is None:
        _global_skills_manager = SkillsManager()
    return _global_skills_manager
