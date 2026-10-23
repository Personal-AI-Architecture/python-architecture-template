"""OpenAI-compatible provider transport.

This module is the only place where provider-native `/chat/completions`
terminology and credentials belong. The Agent Loop receives canonical PAA
types from this boundary.
"""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
import os
from typing import Any

from paa_template.types import CompletionRequest
from .mock import ModelStreamChunk


@dataclass(frozen=True)
class OpenAICompatibleAdapter:
    api_base_url: str
    api_key: str | None = None
    transport: Callable[[str, dict[str, Any], dict[str, str]], Iterator[dict[str, Any]]] | None = None
    name: str = "openai-compatible"
    provider_profiles: dict[str, dict[str, Any]] | None = None

    @property
    def context_limits(self) -> dict[str, dict[str, int]]:
        return {name: dict(profile.get("model_context_limits", {})) for name, profile in (self.provider_profiles or {}).items()}

    def stream(self, request: CompletionRequest) -> Iterator[ModelStreamChunk]:
        if self.transport is None:
            raise RuntimeError("OpenAI-compatible adapter requires an injected transport in this template.")
        if not request.model or not request.model.strip() or not request.provider.strip():
            raise ValueError("Model API request requires model and provider.")
        profiles = self.provider_profiles or {"local": {"base_url": self.api_base_url, "api_key": self.api_key}}
        profile = profiles.get(request.provider)
        if not isinstance(profile, dict):
            raise ValueError("Unknown selected provider profile.")
        base_url = profile.get("base_url")
        if not isinstance(base_url, str) or not base_url.strip():
            raise ValueError("Selected provider profile has no base URL.")
        key_env = profile.get("api_key_env")
        api_key = os.environ.get(key_env) if isinstance(key_env, str) else (self.api_key if self.provider_profiles is None else None)
        if isinstance(key_env, str) and not api_key:
            raise ValueError("Selected provider profile secret is unavailable.")

        payload = {
            "model": request.model,
            "messages": [message_to_provider(message) for message in request.messages],
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        for chunk in self.transport(f"{base_url.rstrip('/')}/chat/completions", payload, headers):
            yield ModelStreamChunk(type=chunk.get("type", "text-delta"), delta=dict(chunk.get("delta", {})))


def message_to_provider(message: Any) -> dict[str, Any]:
    """Translate a canonical message at the provider boundary only."""

    output = {"role": message.role, "content": list(message.parts)}
    if message.tool_calls:
        output["tool_calls"] = [
            {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": call.arguments}}
            for call in message.tool_calls
        ]
    if message.tool_call_id:
        output["tool_call_id"] = message.tool_call_id
    return output
