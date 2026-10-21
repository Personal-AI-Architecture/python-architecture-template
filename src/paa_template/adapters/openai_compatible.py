"""OpenAI-compatible provider transport.

This module is the only place where provider-native `/chat/completions`
terminology and credentials belong. The Agent Loop receives canonical PAA
types from this boundary.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

from paa_template.types import CompletionRequest
from .mock import ModelStreamChunk


@dataclass(frozen=True)
class OpenAICompatibleAdapter:
    api_base_url: str
    api_key: str | None = None
    model: str = "default"
    transport: Callable[[str, dict[str, Any], dict[str, str]], Iterator[dict[str, Any]]] | None = None
    name: str = "openai-compatible"

    def stream(self, request: CompletionRequest) -> Iterator[ModelStreamChunk]:
        if self.transport is None:
            raise RuntimeError("OpenAI-compatible adapter requires an injected transport in this template.")

        payload = {
            "model": request.model or self.model,
            "messages": [message_to_provider(message) for message in request.messages],
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        for chunk in self.transport(f"{self.api_base_url.rstrip('/')}/chat/completions", payload, headers):
            yield ModelStreamChunk(type=chunk.get("type", "text-delta"), delta=dict(chunk.get("delta", {})))


def message_to_provider(message: Any) -> dict[str, Any]:
    """Translate a canonical message at the provider boundary only."""

    output = {"role": message.role, "content": message.content}
    if message.tool_calls:
        output["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        output["tool_call_id"] = message.tool_call_id
    return output
