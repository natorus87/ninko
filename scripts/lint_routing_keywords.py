#!/usr/bin/env python3
"""Lint Ninko module routing keywords without importing module packages."""

from __future__ import annotations

import argparse
import ast
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

STOPWORDS = {
    "a",
    "an",
    "and",
    "auf",
    "das",
    "der",
    "die",
    "ein",
    "eine",
    "for",
    "im",
    "in",
    "mit",
    "of",
    "oder",
    "the",
    "to",
    "und",
    "zu",
}

# Existing intentionally short product/protocol/vendor terms. New short
# keywords should be added only with a concrete routing reason.
ALLOWED_SHORT_KEYWORDS = {
    ("checkmk", "dow"),
    ("checkmk", "ok"),
    ("cisco", "ios"),
    ("fritzbox", "aha"),
    ("fritzbox", "dsl"),
    ("fritzbox", "ip"),
    ("fritzbox", "wan"),
    ("glpi", "sla"),
    ("homeassistant", "ha"),
    ("hpe_ilo", "bmc"),
    ("hpe_ilo", "hpe"),
    ("hpe_ilo", "ilo"),
    ("jira", "bug"),
    ("kubernetes", "k8s"),
    ("kubernetes", "hpa"),
    ("kubernetes", "job"),
    ("kubernetes", "log"),
    ("kubernetes", "pod"),
    ("kubernetes", "pv"),
    ("kubernetes", "pvc"),
    ("kubernetes", "top"),
    ("linux_server", "apt"),
    ("linux_server", "df"),
    ("linux_server", "ssh"),
    ("linux_server", "top"),
    ("microsoft_intune", "mdm"),
    ("microsoft_intune", "mem"),
    ("proxmox", "lxc"),
    ("proxmox", "pve"),
    ("proxmox", "vm"),
    ("redmine", "bug"),
    ("redmine", "hrm"),
    ("synology", "dsm"),
    ("synology", "nas"),
    ("web_search", "web"),
    ("wordpress", "cms"),
    ("wordpress", "wp"),
}


@dataclass(frozen=True)
class RoutingKeyword:
    """One routing keyword from a module manifest."""

    module: str
    keyword: str
    path: Path


def _constant_string(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _extract_manifest(path: Path) -> tuple[str | None, list[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_name: str | None = None
    routing_keywords: list[str] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for keyword in node.keywords:
            if keyword.arg == "name":
                module_name = _constant_string(keyword.value) or module_name
            elif keyword.arg == "routing_keywords" and isinstance(keyword.value, ast.List):
                routing_keywords = [
                    value
                    for element in keyword.value.elts
                    if (value := _constant_string(element)) is not None
                ]

    return module_name, routing_keywords


def iter_routing_keywords(repo_root: Path) -> Iterable[RoutingKeyword]:
    """Yield routing keywords from built-in and catalog module manifests."""
    manifest_paths = [
        *repo_root.glob("backend/modules/*/manifest.py"),
        *repo_root.glob("backend/modules_catalog/*/manifest.py"),
    ]
    for path in sorted(manifest_paths):
        module_name, keywords = _extract_manifest(path)
        if not module_name:
            continue
        for keyword in keywords:
            yield RoutingKeyword(module=module_name, keyword=keyword, path=path)


def validate_keywords(keywords: Iterable[RoutingKeyword]) -> list[str]:
    """Return validation errors for unsafe or ambiguous routing keywords."""
    errors: list[str] = []
    seen_by_module: set[tuple[str, str]] = set()

    for item in keywords:
        normalized = item.keyword.strip().lower()
        location = f"{item.path}:{item.module}:{item.keyword!r}"

        if not normalized:
            errors.append(f"{location} is empty")
            continue

        module_key = (item.module, normalized)
        if module_key in seen_by_module:
            errors.append(f"{location} duplicates another keyword in the same module")
        seen_by_module.add(module_key)

        if normalized in STOPWORDS:
            errors.append(f"{location} is a stopword")

        if len(normalized) < 4 and module_key not in ALLOWED_SHORT_KEYWORDS:
            errors.append(
                f"{location} is shorter than 4 characters and is not allowlisted"
            )

    return errors


def main() -> int:
    """Run the routing keyword linter CLI."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root to scan.",
    )
    args = parser.parse_args()

    errors = validate_keywords(iter_routing_keywords(args.repo_root))
    if errors:
        print("Routing keyword lint failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Routing keyword lint passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
