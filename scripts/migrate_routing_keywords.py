#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

_backend_root = Path(__file__).resolve().parents[1] / "backend"
sys.path.insert(0, str(_backend_root))


_REQUIRED_TERMS: dict[str, set[str]] = {
    "checkmk": {
        "host", "service", "alert", "monitor", "problem", "downtime",
        "status", "critical", "warning", "pending",
    },
    "docker": {
        "container", "image", "volume", "docker", "compose", "registry",
        "pull", "build", "push",
    },
    "fritzbox": {
        "router", "wlan", "wifi", "smart home", "dect", "telephony",
        "bandwidth", "dsl", "wan", "external ip", "fritz",
    },
    "github": {
        "github", "repository", "repo", "pull request", "issue", "workflow",
        "actions", "release",
    },
    "glpi": {
        "ticket", "incident", "helpdesk", "sla", "follow",
    },
    "homeassistant": {
        "home assistant", "smart home", "light", "switch", "heating",
        "sensor", "entity", "ha ",
    },
    "kubernetes": {
        "pod", "deployment", "namespace", "cluster", "kubectl",
        "service", "ingress", "configmap", "secret", "pvc", "helm",
        "logs", "restart", "scale",
    },
    "mikrotik": {
        "routeros", "router", "switch", "wireguard", "wireless", "firewall",
    },
    "pihole": {
        "dns", "blocking", "blocklist", "whitelist", "blacklist",
        "query log", "gravity", "dhcp", "cache",
    },
    "proxmox": {
        "vm", "lxc", "virtual machine", "snapshot", "backup", "node",
        "proxmox",
    },
    "synology": {
        "nas", "storage", "raid", "backup", "dsm", "diskstation",
        "synology", "package",
    },
    "telegram": {
        "telegram", "bot", "chat", "message", "voice", "group", "channel",
    },
}

_COVERAGE_THRESHOLD = 0.65


def parse_manifest(module_dir: Path) -> dict | None:
    manifest_py = module_dir / "manifest.py"
    manifest_path = manifest_py if manifest_py.exists() else module_dir / "__init__.py"

    if not manifest_path.exists():
        return None

    source = manifest_path.read_text()
    tree = ast.parse(source, filename=str(manifest_path))

    name = description = None
    routing_keywords: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "module_manifest":
                    call = node.value
                    if isinstance(call, ast.Call):
                        for kw in call.keywords:
                            if kw.arg == "name" and isinstance(kw.value, ast.Constant):
                                name = kw.value.value
                            elif kw.arg == "description" and isinstance(kw.value, ast.Constant):
                                description = kw.value.value
                            elif kw.arg == "routing_keywords" and isinstance(kw.value, ast.List):
                                routing_keywords = [
                                    elt.value
                                    for elt in kw.value.elts
                                    if isinstance(elt, ast.Constant)
                                ]

    if name is None:
        return None

    return {
        "name": name,
        "description": description or "",
        "routing_keywords": routing_keywords,
        "path": manifest_path,
    }


def check_coverage(description: str, required: set[str]) -> tuple[int, int, list[str]]:
    desc_lower = description.lower()
    covered = 0
    missing = []
    for term in required:
        if term.lower() in desc_lower:
            covered += 1
        else:
            missing.append(term)
    return covered, len(required), missing


def build_enriched_description(
    current_desc: str,
    routing_keywords: list[str],
    required: set[str],
) -> str:
    covered, total, missing = check_coverage(current_desc, required)
    if covered >= total * _COVERAGE_THRESHOLD:
        return current_desc

    extra_terms: list[str] = []
    for kw in routing_keywords:
        kw_clean = kw.strip().lower()
        if kw_clean and kw_clean not in current_desc.lower() and kw_clean not in extra_terms:
            if len(kw_clean.split()) <= 3:
                extra_terms.append(kw_clean)

    for term in missing:
        if term.lower() not in current_desc.lower() and term.lower() not in extra_terms:
            if len(term.split()) <= 2:
                extra_terms.append(term)

    if not extra_terms:
        return current_desc

    if len(current_desc) < 180:
        top_terms = extra_terms[:5]
        separator = ", " if "," not in current_desc[-30:] else "; "
        return f"{current_desc}{separator}{', '.join(top_terms)}."

    return current_desc


def apply_fix(manifest_path: Path, new_desc: str) -> None:
    source = manifest_path.read_text()
    lines = source.split("\n")
    new_lines = []
    i = 0
    while i < len(lines):
        line = lines[i]
        in_manifest = "module_manifest" in "".join(lines[max(0, i - 5) : i + 1])
        is_multiline_desc = re.match(r"\s+description\s*=\s*\(", line)
        is_singleline_desc = re.match(r'\s+description\s*=', line) and '"' in line

        if is_multiline_desc and in_manifest:
            j = i + 1
            paren_depth = 1
            while j < len(lines) and paren_depth > 0:
                paren_depth += lines[j].count("(") - lines[j].count(")")
                j += 1
            indent = re.match(r"\s*", line).group()
            new_lines.append(f'{indent}description=(\n{indent}    {new_desc!r}\n{indent})')
            i = j
        elif is_singleline_desc and in_manifest:
            indent = re.match(r"\s*", line).group()
            new_lines.append(f"{indent}description=({new_desc!r})")
            i += 1
        else:
            new_lines.append(line)
            i += 1

    manifest_path.write_text("\n".join(new_lines))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    catalog_dir = _backend_root / "modules_catalog"
    if not catalog_dir.is_dir():
        print(f"modules_catalog not found at {catalog_dir}", file=sys.stderr)
        return 1

    modules = sorted(
        d for d in catalog_dir.iterdir() if d.is_dir() and not d.name.startswith("_")
    )

    total = ok = changed = 0
    diffs: list[str] = []

    for module_dir in modules:
        data = parse_manifest(module_dir)
        if data is None:
            continue

        total += 1
        module_name = data["name"]
        current_desc = data["description"]
        routing_keywords = data["routing_keywords"]
        required = _REQUIRED_TERMS.get(module_name, set())

        if not required:
            ok += 1
            if args.verbose:
                print(f"skip {module_name}: no rule")
            continue

        covered, total_terms, missing = check_coverage(current_desc, required)
        ratio = covered / total_terms if total_terms > 0 else 1.0

        if ratio >= _COVERAGE_THRESHOLD:
            ok += 1
            if args.verbose:
                print(f"pass {module_name}: {covered}/{total_terms} ({ratio:.0%})")
            continue

        new_desc = build_enriched_description(current_desc, routing_keywords, required)
        if new_desc != current_desc:
            changed += 1
            diffs.append(
                f"  {module_name}: {covered}/{total_terms}, MISSING: {missing[:3]}\n"
                f"  OLD: {current_desc!r}\n"
                f"  NEW: {new_desc!r}"
            )
            if args.apply:
                apply_fix(data["path"], new_desc)
                if args.verbose:
                    print(f"fixed {module_name}")

    print(f"Total: {total} | Pass: {ok} | Changed: {changed}")
    if diffs:
        print("\n" + "\n".join(diffs))

    if args.check:
        return 1 if changed > 0 else 0

    if not args.apply and changed > 0:
        print("Run with --apply to write changes, or --check to verify.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
