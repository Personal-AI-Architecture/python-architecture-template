"""Conservative, provider/model-specific working-context accounting."""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Mapping

from .contracts import Message, ToolDefinition


DEFAULT_CONTEXT_LIMITS: dict[str, dict[str, int]] = {"local": {"mock": 8192}}


def model_limit(limits: Mapping[str, Mapping[str, int]], provider: str, model: str) -> int | None:
    limit = limits.get(provider, {}).get(model)
    return limit if isinstance(limit, int) and limit > 0 else None


def context_cost(messages: tuple[Message, ...], tools: tuple[ToolDefinition, ...] = ()) -> int:
    """UTF-8 bytes upper-bound ordinary token counts; reserve response and protocol space."""
    payload = {"messages": [asdict(message) for message in messages], "tools": [asdict(tool) for tool in tools]}
    return len(json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")) + 384


def select_complete_turns(messages: tuple[Message, ...], limit: int, tools: tuple[ToolDefinition, ...] = ()) -> tuple[tuple[Message, ...] | None, int]:
    turns: list[list[Message]] = []
    for message in messages:
        if message.role == "user" or not turns:
            turns.append([])
        turns[-1].append(message)
    selected: list[Message] = []
    kept = 0
    for turn in reversed(turns):
        candidate = tuple(turn + selected)
        if context_cost(candidate, tools) > limit:
            if kept == 0:
                return None, len(turns)
            break
        selected = list(candidate)
        kept += 1
    return tuple(selected), len(turns) - kept
