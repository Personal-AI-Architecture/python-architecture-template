"""Small in-memory memory boundary used by the reference template."""

from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
import json
import os
import tempfile


@dataclass
class MemoryStore:
    memory_root: str = ".paa-memory"
    entries: list[dict[str, Any]] = field(default_factory=list)

    def read_preferences(self) -> dict[str, str] | None:
        path = Path(self.memory_root) / "preferences.json"
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        if not isinstance(value, dict) or not isinstance(value.get("model"), str) or not isinstance(value.get("active_provider_profile"), str):
            raise ValueError("Invalid owner preferences in Memory.")
        return value

    def write_preferences(self, model: str, provider: str) -> None:
        if not model or not provider:
            raise ValueError("Model and provider preferences are required.")
        directory = Path(self.memory_root)
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, prefix="preferences-", suffix=".tmp", delete=False) as temporary:
            json.dump({"model": model, "active_provider_profile": provider}, temporary)
        try:
            os.replace(temporary.name, directory / "preferences.json")
        finally:
            if os.path.exists(temporary.name):
                os.unlink(temporary.name)

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
            "preferences": self.read_preferences(),
        }
