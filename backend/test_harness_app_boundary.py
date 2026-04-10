"""
CI test: enforce harness/app boundary.

RULES:
    1. ninko.harness.* MUST NOT import from ninko.app.*
    2. ninko.harness.* MUST NOT import from modules or modules_catalog
    3. ninko.app.* MAY import from ninko.harness.*
"""

from __future__ import annotations

import ast
import logging
import sys
from pathlib import Path

logger = logging.getLogger("test.harness_boundary")

BACKEND_DIR = Path(__file__).parent
HARNESS_DIR = BACKEND_DIR / "ninko" / "harness"
APP_DIR = BACKEND_DIR / "ninko" / "app"
FORBIDDEN_PREFIXES = ("ninko.app.", "modules.", "modules_catalog.", "api.")


def _extract_imports(filepath: Path) -> list[str]:
    source = filepath.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(filepath))
    imports: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)

    return imports


def _check_harness_boundary() -> list[str]:
    violations: list[str] = []

    if not HARNESS_DIR.exists():
        return violations

    for py_file in HARNESS_DIR.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        imports = _extract_imports(py_file)
        rel_path = py_file.relative_to(BACKEND_DIR)

        for imp in imports:
            for forbidden in FORBIDDEN_PREFIXES:
                if imp.startswith(forbidden):
                    violations.append(
                        f"{rel_path}: imports '{imp}' (harness must not import from {forbidden})"
                    )

    return violations


def main() -> int:
    logger.info("Checking harness/app boundary...")
    violations = _check_harness_boundary()

    if violations:
        logger.error("BOUNDARY VIOLATIONS FOUND:")
        for v in violations:
            logger.error("  %s", v)
        return 1

    logger.info("OK: No harness/app boundary violations.")
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    sys.exit(main())
