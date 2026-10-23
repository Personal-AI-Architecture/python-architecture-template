"""Provider-neutral Agent Loop."""

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from paa_template.types import CompletionRequest, EngineRequest, EngineStreamEvent, Message, ToolDefinition
from paa_template.types.contracts import normalize_tool_definition
from paa_template.types.context import DEFAULT_CONTEXT_LIMITS, context_cost, model_limit


class AgentLoop:
    def __init__(self, model_adapter: Any, tools: Iterable[ToolDefinition] = (), context_limits: Mapping[str, Mapping[str, int]] | None = None) -> None:
        self.model_adapter = model_adapter
        self.tools = tuple(tool for tool in (normalize_tool_definition(item) for item in tools) if tool is not None)
        adapter_limits = getattr(model_adapter, "context_limits", None)
        self.context_limits = context_limits if context_limits is not None else adapter_limits if adapter_limits is not None else DEFAULT_CONTEXT_LIMITS

    def run(self, request: EngineRequest) -> Iterator[EngineStreamEvent]:
        if not request.metadata.correlation_id.strip():
            yield EngineStreamEvent("error", {"code": "provider_error", "message": "Missing correlation_id."})
            return
        actor = request.auth_context.get("actor")
        if not isinstance(actor, Mapping) or not actor.get("id") or request.auth_context.get("correlation_id") != request.metadata.correlation_id:
            yield EngineStreamEvent("error", {"code": "unauthorized", "message": "Missing or invalid authenticated actor context."})
            return
        if not request.model.strip():
            yield EngineStreamEvent("error", {"code": "invalid_request", "message": "Missing selected model."})
            return
        if not request.provider.strip():
            yield EngineStreamEvent("error", {"code": "invalid_request", "message": "Missing selected provider."})
            return
        limit = model_limit(self.context_limits, request.provider, request.model)
        if limit is None:
            yield EngineStreamEvent("error", {"code": "context_limit_unknown", "message": "No safe context limit for selected provider and model."})
            return

        messages = request.messages
        if request.context_summary is not None:
            summary = request.context_summary
            if summary.get("source") != "gateway" or summary.get("method") != "deterministic" or not isinstance(summary.get("text"), str):
                yield EngineStreamEvent("error", {"code": "invalid_request", "message": "Invalid context summary."})
                return
            label = "Gateway-derived context from omitted turns (not a new owner request): " + summary["text"]
            messages = (Message("user", label),) + messages
        if context_cost(messages, self.tools) > limit:
            yield EngineStreamEvent("error", {"code": "context_overflow", "message": "Selected model context window exceeded."})
            return

        completion = CompletionRequest(messages=messages, tools=self.tools, stream=True, model=request.model, provider=request.provider)
        try:
            for chunk in self.model_adapter.stream(completion):
                if chunk.type == "text-delta":
                    content = chunk.delta.get("content", "")
                    if content:
                        yield EngineStreamEvent("text-delta", {"content": content})
                elif chunk.type == "tool-call":
                    yield EngineStreamEvent("tool-call", dict(chunk.delta))
                elif chunk.type == "tool-result":
                    yield EngineStreamEvent("tool-result", dict(chunk.delta))
                elif chunk.type == "error":
                    yield EngineStreamEvent("error", dict(chunk.delta))
                elif chunk.type == "done":
                    yield EngineStreamEvent("done", {"finish_reason": chunk.delta.get("finish_reason", "stop")})
        except Exception:  # adapters must not leak provider diagnostics to clients
            yield EngineStreamEvent("error", {"code": "provider_error", "message": "Model provider failed."})
