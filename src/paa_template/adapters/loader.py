"""Runtime adapter selection."""

from typing import Any

from .mock import MockAdapter
from .openai_compatible import OpenAICompatibleAdapter
from .runtime_types import RuntimeLike


def load_model_adapter(runtime: RuntimeLike, *, openai_compatible: dict[str, Any] | None = None) -> Any:
    provider = runtime.provider_adapter
    if provider in {"mock", "local"}:
        return MockAdapter()
    if provider == "openai-compatible":
        config = openai_compatible or {}
        return OpenAICompatibleAdapter(
            api_base_url=str(config.get("api_base_url", "http://localhost/v1")),
            api_key=config.get("api_key"),
            transport=config.get("transport"),
            provider_profiles=config.get("provider_profiles"),
        )
    raise ValueError(f"Unsupported provider adapter: {provider}")
