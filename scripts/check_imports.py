#!/usr/bin/env python3
"""Enforce Python component import boundaries with the AST."""

from __future__ import annotations

import ast
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/paa_template"
COMPONENTS = {"auth", "gateway", "agent_loop", "memory", "adapters", "config", "types"}
STDLIB = set(getattr(sys, "stdlib_module_names", ())) | {"__future__"}
ALLOWED = {
    "auth": {"auth", "types"},
    "gateway": {"gateway", "types", "agent_loop", "memory"},
    "agent_loop": {"agent_loop", "types"},
    "memory": {"memory", "types"},
    "adapters": {"adapters", "types"},
    "config": {"config", "types"},
    "types": {"types"},
}


def check_imports() -> list[str]:
    errors: list[str] = []
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC).as_posix()
        owner = relative.split("/", 1)[0]
        if owner not in COMPONENTS:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except SyntaxError as error:
            errors.append(f"Unable to parse {path.relative_to(ROOT)}: {error}")
            continue
        for node in ast.walk(tree):
            imported: str | None = None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported = alias.name
                    if not imported.startswith("paa_template."):
                        if imported.split(".", 1)[0] not in STDLIB:
                            errors.append(f"Forbidden package import in {path.relative_to(ROOT)}: {imported}")
                        continue
                    target = imported.split(".")[1]
                    if target not in ALLOWED[owner]:
                        errors.append(f"Forbidden component coupling in {path.relative_to(ROOT)}: {imported}")
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    target = owner
                    if node.module and node.module.startswith(".."):
                        errors.append(f"Unsupported parent-relative import in {path.relative_to(ROOT)}: {node.module}")
                    elif node.module and node.module.startswith("."):
                        target = node.module.lstrip(".").split(".")[0] or owner
                    if target not in ALLOWED[owner]:
                        errors.append(f"Forbidden component coupling in {path.relative_to(ROOT)}: {node.module}")
                elif node.module and node.module.startswith("paa_template."):
                    target = node.module.split(".")[1]
                    if target not in ALLOWED[owner]:
                        errors.append(f"Forbidden component coupling in {path.relative_to(ROOT)}: {node.module}")
                elif node.module and node.module == "paa_template":
                    errors.append(f"Package-root imports are forbidden inside components: {path.relative_to(ROOT)}")
                elif node.module and node.module.split(".", 1)[0] not in STDLIB:
                    errors.append(f"Forbidden package import in {path.relative_to(ROOT)}: {node.module}")
    return errors


def main() -> int:
    errors = check_imports()
    if errors:
        print("Import boundary check failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Import boundary check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
