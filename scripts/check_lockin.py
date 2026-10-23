#!/usr/bin/env python3
"""Check that provider and runtime configuration boundaries remain meaningful."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src/paa_template"
REQUIRED_FILES = [
    "src/paa_template/adapters/loader.py",
    "src/paa_template/adapters/mock.py",
    "src/paa_template/adapters/openai_compatible.py",
    "src/paa_template/engine/loop.py",
    "src/paa_template/types/contracts.py",
]
PROVIDER_TOKENS = ["/chat/completions", "api_base_url", "api_key", "openai-compatible"]
FORBIDDEN_METADATA = {"provider", "provider_adapter", "model", "tools", "tool_sources"}


def check_lockin() -> list[str]:
    errors: list[str] = []
    for relative in REQUIRED_FILES:
        if not (ROOT / relative).is_file():
            errors.append(f"Missing required file: {relative}")

    contracts = (SRC / "types/contracts.py").read_text(encoding="utf-8")
    if "class EngineRequestMetadata" not in contracts:
        errors.append("EngineRequestMetadata contract is missing.")
    else:
        tree = ast.parse(contracts)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and node.name == "EngineRequestMetadata":
                fields = {item.target.id for item in node.body if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name)}
                for key in FORBIDDEN_METADATA:
                    if key in fields:
                        errors.append(f"EngineRequestMetadata must not include runtime reconfiguration key: {key}")

    engine = (SRC / "engine/loop.py").read_text(encoding="utf-8")
    if "self.tools" not in engine or "CompletionRequest(messages=messages, tools=self.tools" not in engine:
        errors.append("Agent loop must derive the model request tool list from configured tools.")
    if "request.metadata.provider" in engine or "request.metadata.model" in engine:
        errors.append("Agent loop must not read provider or model overrides from request metadata.")

    for path in SRC.rglob("*.py"):
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("src/paa_template/adapters/"):
            continue
        source = path.read_text(encoding="utf-8")
        for token in PROVIDER_TOKENS:
            if token in source:
                errors.append(f'Provider-specific token "{token}" must stay within src/paa_template/adapters/: {relative}')
    routes = (SRC / "gateway/routes.py").read_text(encoding="utf-8")
    for route in ["/conversations/messages", "/conversations", "/messages"]:
        if route not in routes:
            errors.append(f"Gateway runtime is missing route marker: {route}")
    return errors


def main() -> int:
    errors = check_lockin()
    if errors:
        print("Lock-in check failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Lock-in check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
