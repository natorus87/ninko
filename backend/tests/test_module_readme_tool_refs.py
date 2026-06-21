"""Keep module README tool references aligned with actual @tool names."""

from __future__ import annotations

import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOC_TOKEN = re.compile(r"`([a-zA-Z_][a-zA-Z0-9_]+)`")
NON_TOOL_TOKENS = {
    "allow_from",
    "allowed_chat_ids",
    "api_seats_exceeded",
    "base_url",
    "connection_id",
    "file_path",
    "user_id",
}


def _tool_names(module_dir: Path) -> set[str]:
    tools_path = module_dir / "tools.py"
    if not tools_path.exists():
        return set()
    tree = ast.parse(tools_path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in tree.body:
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        is_tool = False
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Name) and target.id == "tool":
                is_tool = True
            if isinstance(target, ast.Attribute) and target.attr == "tool":
                is_tool = True
        if is_tool:
            names.add(node.name)
    return names


def test_readme_tool_references_exist() -> None:
    module_dirs = [
        *sorted((ROOT / "modules_catalog").glob("*")),
        *sorted((ROOT / "modules").glob("*")),
    ]
    failures: list[str] = []

    for module_dir in module_dirs:
        if not module_dir.is_dir() or module_dir.name.startswith("_"):
            continue
        readme = module_dir / "README.md"
        if not readme.exists():
            continue
        tools = _tool_names(module_dir)
        if not tools:
            continue
        refs = {
            token
            for token in DOC_TOKEN.findall(readme.read_text(encoding="utf-8"))
            if "_" in token and token.casefold() == token
        }
        missing = sorted(ref for ref in refs if ref not in tools and ref not in NON_TOOL_TOKENS)
        if missing:
            failures.append(f"{module_dir.name}: {', '.join(missing)}")

    assert not failures, "Stale README tool references:\n" + "\n".join(failures)
