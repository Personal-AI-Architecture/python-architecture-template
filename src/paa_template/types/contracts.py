"""PAA-facing data contracts.

Provider payloads may be normalized at the adapter boundary, but the rest of
the runtime only receives these canonical plain-Python shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Mapping, TypeAlias

MessageRole: TypeAlias = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: dict[str, Any]
    invalid_arguments: bool = False


@dataclass(frozen=True)
class Message:
    role: MessageRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


CanonicalMessage: TypeAlias = Message


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]
    source: str | None = None
    category: Literal["always-send", "discoverable"] | None = None
    mutates_state: bool = False
    required_permissions: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineRequestMetadata:
    correlation_id: str
    conversation_id: str | None = None
    trigger: str | None = None
    client_context: dict[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    actor_permissions: tuple[str, ...] = ()
    allowed_tool_sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class EngineRequest:
    messages: tuple[CanonicalMessage, ...]
    metadata: EngineRequestMetadata


@dataclass(frozen=True)
class CompletionRequest:
    messages: tuple[CanonicalMessage, ...]
    tools: tuple[ToolDefinition, ...] = ()
    stream: bool = True
    model: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class EngineStreamEvent:
    event: Literal["text-delta", "tool-call", "tool-result", "done", "error"]
    data: dict[str, Any] = field(default_factory=dict)


GatewayStreamEvent = EngineStreamEvent


def _mapping(value: Any) -> Mapping[str, Any] | None:
    return value if isinstance(value, Mapping) else None


def _parse_arguments(value: Any) -> tuple[dict[str, Any], bool]:
    if isinstance(value, Mapping):
        return dict(value), False
    if isinstance(value, str):
        import json

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}, True
        return (dict(parsed), False) if isinstance(parsed, Mapping) else ({}, True)
    return {}, False


def normalize_tool_definition(value: Any) -> ToolDefinition | None:
    record = _mapping(value)
    if record is None:
        return None
    legacy_function = _mapping(record.get("function"))
    source = legacy_function or record
    name = source.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    parameters = source.get("parameters")
    return ToolDefinition(
        name=name.strip(),
        description=source.get("description", "") if isinstance(source.get("description", ""), str) else "",
        parameters=dict(parameters) if isinstance(parameters, Mapping) else {},
        source=record.get("source") if isinstance(record.get("source"), str) else None,
        category=record.get("category") if record.get("category") in {"always-send", "discoverable"} else None,
        mutates_state=record.get("mutates_state") is True,
        required_permissions=tuple(item for item in record.get("required_permissions", ()) if isinstance(item, str)),
    )


def normalize_tool_call(value: Any) -> ToolCall | None:
    record = _mapping(value)
    if record is None or not isinstance(record.get("id"), str):
        return None
    legacy_function = _mapping(record.get("function"))
    source = legacy_function or record
    name = source.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    arguments, invalid = _parse_arguments(source.get("arguments"))
    return ToolCall(id=record["id"], name=name.strip(), arguments=arguments, invalid_arguments=invalid)
