"""Configuration loading for the Python template."""

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class RuntimeConfiguration:
    memory_root: str
    provider_adapter: str
    auth_mode: str
    tool_sources: tuple[str, ...]


def load_runtime_configuration(config: Mapping[str, Any] | None = None) -> RuntimeConfiguration:
    source = config or {}
    defaults = source.get("default", source)
    if not isinstance(defaults, Mapping):
        raise ValueError("Runtime configuration must be an object.")
    memory_root = defaults.get("memory_root", ".paa-memory")
    provider_adapter = defaults.get("provider_adapter", "mock")
    auth_mode = defaults.get("auth_mode", "enforced")
    tool_sources = defaults.get("tool_sources", ())
    if not isinstance(memory_root, str) or not isinstance(provider_adapter, str) or not isinstance(auth_mode, str):
        raise ValueError("Runtime configuration scalar fields must be strings.")
    if not isinstance(tool_sources, (list, tuple)) or not all(isinstance(item, str) for item in tool_sources):
        raise ValueError("tool_sources must be a list of strings.")
    return RuntimeConfiguration(memory_root, provider_adapter, auth_mode, tuple(tool_sources))
