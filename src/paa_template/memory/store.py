"""Small in-memory memory boundary used by the reference template."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MemoryStore:
    memory_root: str = ".paa-memory"
    entries: list[dict[str, Any]] = field(default_factory=list)

    def record(self, kind: str, value: dict[str, Any]) -> None:
        self.entries.append({"kind": kind, **value})

    def export(self) -> dict[str, Any]:
        conversations = [entry for entry in self.entries if entry["kind"] == "conversation"]
        history = [entry for entry in self.entries if entry["kind"] == "message"]
        return {
            "memory_root": self.memory_root,
            "entries": list(self.entries),
            "conversations": conversations,
            "history": history,
        }
