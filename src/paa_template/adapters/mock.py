"""Deterministic offline adapter used by tests and local development."""

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

from paa_template.types import CompletionRequest


@dataclass(frozen=True)
class ModelStreamChunk:
    type: str
    delta: dict[str, Any]


class MockAdapter:
    name = "mock"

    def __init__(self, response: str = "mock response") -> None:
        self.response = response

    def stream(self, request: CompletionRequest) -> Iterator[ModelStreamChunk]:
        del request
        yield ModelStreamChunk(type="text-delta", delta={"content": self.response})
        yield ModelStreamChunk(type="done", delta={"finish_reason": "stop"})
