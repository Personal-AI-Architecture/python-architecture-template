"""Adapter-local typing helpers kept out of the engine boundary."""

from typing import Protocol


class RuntimeLike(Protocol):
    provider_adapter: str
