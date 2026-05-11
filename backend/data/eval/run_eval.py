#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO_ROOT))


def load_corpus() -> list[dict]:
    path = _REPO_ROOT / "backend" / "data" / "eval" / "eval_corpus.json"
    with open(path) as f:
        return json.load(f)["queries"]


def load_module_descriptions() -> dict[str, str]:
    descriptions = {}
    for base_dir in ["backend/modules", "backend/modules_catalog"]:
        for d in Path(base_dir).iterdir():
            if not d.is_dir():
                continue
            manifest = d / "manifest.py"
            if not manifest.exists():
                continue
            content = manifest.read_text()
            nm = re.search(
                r"^module_manifest\s*=\s*ModuleManifest\s*\((.*)\n\)",
                content,
                re.MULTILINE | re.DOTALL,
            )
            if not nm:
                continue
            body = nm.group(1)
            name_m = re.search(r'name\s*=\s*"([^"]+)"', body)
            desc_m = re.search(
                r'description\s*=\s*\(\s*"([^"]+)"', body, re.DOTALL
            )
            if not desc_m:
                desc_m = re.search(r'description\s*=\s*"([^"]+)"', body)
            if name_m:
                descriptions[name_m.group(1)] = (
                    desc_m.group(1) if desc_m else ""
                )
    return descriptions


def main() -> int:
    corpus = load_corpus()
    descriptions = load_module_descriptions()

    modules_in_corpus = set(q["module"] for q in corpus)
    modules_in_registry = set(descriptions.keys())
    unknown = modules_in_corpus - modules_in_registry

    print(f"Corpus: {len(corpus)} queries, {len(modules_in_corpus)} unique modules")
    print(f"Registry: {len(modules_in_registry)} modules")

    if unknown:
        print(f"\nWARNING: modules in corpus but not in registry: {sorted(unknown)}")

    counts = Counter(q["module"] for q in corpus)
    print("\nQueries per module:")
    for mod, cnt in sorted(counts.items()):
        present = "✓" if mod in modules_in_registry else "✗"
        print(f"  [{present}] {mod}: {cnt}")

    print("\nCorpus modules with empty descriptions:")
    for mod in sorted(modules_in_corpus):
        d = descriptions.get(mod, "")
        if not d.strip():
            print(f"  - {mod}")

    return 0


if __name__ == "__main__":
    sys.exit(main())