#!/usr/bin/env python3
"""Check PAA contract markers and required schema fields."""

from __future__ import annotations

import json
from pathlib import Path

try:
    from .check_paa import contract_errors
except ImportError:  # direct script execution
    from check_paa import contract_errors

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_ROUTES = [
    "/conversations/messages",
    "/conversations",
    "/conversations/{id}",
    "/conversations/{id}/messages",
]
REQUIRED_SCHEMAS = {
    "contracts/schemas/configuration.json": ["memory_root", "provider_adapter", "auth_mode", "tool_sources"],
    "contracts/schemas/identity.json": ["id", "type", "display_name", "status", "created"],
    "contracts/schemas/message.json": ["role", "content"],
    "contracts/schemas/policy.json": ["subject", "resource", "action", "effect"],
    "contracts/schemas/tool-definition.json": ["name", "description", "parameters", "source", "visibility"],
    "contracts/schemas/auth-context.json": ["actor", "authentication_id", "authenticated_at", "correlation_id"],
    "contracts/schemas/authentication-result.json": ["authenticated", "reason", "correlation_id"],
    "contracts/schemas/authorization-request.json": ["actor_id", "resource", "action", "correlation_id"],
    "contracts/schemas/authorization-result.json": ["allowed", "reason", "audit_id", "correlation_id"],
    "contracts/schemas/approval-request.json": ["request_id", "tool_name", "summary", "status", "created_at", "expires_at"],
    "contracts/schemas/approval-decision.json": ["request_id", "decision", "decided_at"],
    "contracts/schemas/audit-record.json": ["id", "occurred_at", "event", "actor_id", "action", "result", "correlation_id"],
}


def check_contracts() -> list[str]:
    errors = contract_errors()
    gateway = (ROOT / "contracts/openapi/gateway-api.yaml").read_text(encoding="utf-8")
    engine = (ROOT / "contracts/openapi/gateway-engine.yaml").read_text(encoding="utf-8")
    model = (ROOT / "contracts/openapi/model-api.yaml").read_text(encoding="utf-8")
    for route in REQUIRED_ROUTES:
        if f"  {route}:" not in gateway:
            errors.append(f"Gateway API path is missing: {route}.")
    if "  /chat:" in gateway or "conversation_id}" in gateway:
        errors.append("Gateway API contains a non-PAA route or path parameter.")
    for marker in ["SendMessageRequest", "ConversationList", "Conversation", "ClientSSEStream"]:
        if f"    {marker}:" not in gateway:
            errors.append(f"Gateway schema is missing: {marker}.")
    for marker in ["/agent-loop/chat:", "AgentLoopRequest:", "RequestMetadata:", "SSEStream:", "auth_context:"]:
        if marker not in engine:
            errors.append(f"Gateway-Agent Loop contract is missing: {marker}.")
    for marker in ["/completions:", "CompletionRequest:", "CompletionStream:"]:
        if marker not in model:
            errors.append(f"Model API contract is missing: {marker}.")
    if "  /model/chat/completions:" in model:
        errors.append("Model API promotes a provider-native route into the PAA contract.")

    for relative, required in REQUIRED_SCHEMAS.items():
        try:
            schema = json.loads((ROOT / relative).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            errors.append(f"{relative} is not valid JSON: {error}")
            continue
        if schema.get("type") != "object":
            errors.append(f"{relative} must define an object schema.")
        for key in required:
            if key not in schema.get("required", []):
                errors.append(f"{relative} is missing required field: {key}.")
    return errors


def main() -> int:
    errors = check_contracts()
    if errors:
        print("Contract check failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("Contract check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
