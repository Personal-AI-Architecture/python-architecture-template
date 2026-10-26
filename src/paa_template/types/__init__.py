"""Canonical PAA message, tool, Agent Loop, and stream types."""

from .contracts import (
    CanonicalMessage,
    CompletionRequest,
    AgentLoopRequest,
    AgentLoopRequestMetadata,
    AgentLoopStreamEvent,
    GatewayStreamEvent,
    Message,
    ToolCall,
    ToolDefinition,
    normalize_tool_call,
    normalize_tool_definition,
)

__all__ = [
    "CanonicalMessage",
    "CompletionRequest",
    "AgentLoopRequest",
    "AgentLoopRequestMetadata",
    "AgentLoopStreamEvent",
    "GatewayStreamEvent",
    "Message",
    "ToolCall",
    "ToolDefinition",
    "normalize_tool_call",
    "normalize_tool_definition",
]
