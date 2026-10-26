"""Adapter-local typing helpers kept out of the Agent Loop boundary."""

from typing import Protocol


class RuntimeLike(Protocol):
    provider_adapter: str
