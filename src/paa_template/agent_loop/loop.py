"""Provider-neutral Agent Loop."""

from collections.abc import Iterable, Iterator, Mapping
import re
from typing import Any

from paa_template.types import CompletionRequest, AgentLoopRequest, AgentLoopStreamEvent, Message, ToolDefinition
from paa_template.types.contracts import normalize_tool_definition
from paa_template.types.context import DEFAULT_CONTEXT_LIMITS, context_cost, model_limit


def _safe_model_error(data: Mapping[str, Any]) -> dict[str, str]:
    code = data.get("code")
    if code == "model_unavailable":
        return {"code": code, "message": "The selected model is unavailable through the selected provider."}
    if code == "capability_unsupported":
        capability = data.get("capability")
        if isinstance(capability, str) and re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_.-]{0,63}", capability):
            return {"code": code, "capability": capability, "message": "The selected model does not support the requested capability."}
    return {"code": "provider_error", "message": "Model provider failed."}


def _source_id_for_tool(name: str, tools: tuple[ToolDefinition, ...]) -> str:
    configured = next((tool for tool in tools if tool.name == name and tool.source), None)
    if configured and configured.source:
        return configured.source.strip()
    match = re.match(r"^([a-z0-9]+)[_:-]", name.strip(), re.IGNORECASE)
    return match.group(1) if match else "internal"


def _serialize_tool_output(value: Any) -> str:
    if isinstance(value, str):
        return value
    import json

    try:
        return json.dumps(value, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(value)


class AgentLoop:
    def __init__(self, model_adapter: Any, tools: Iterable[ToolDefinition] = (), context_limits: Mapping[str, Mapping[str, int]] | None = None) -> None:
        self.model_adapter = model_adapter
        self.tools = tuple(tool for tool in (normalize_tool_definition(item) for item in tools) if tool is not None)
        adapter_limits = getattr(model_adapter, "context_limits", None)
        self.context_limits = context_limits if context_limits is not None else adapter_limits if adapter_limits is not None else DEFAULT_CONTEXT_LIMITS

    def run(self, request: AgentLoopRequest) -> Iterator[AgentLoopStreamEvent]:
        if set(request.auth_context) - {"actor", "authentication_id", "authenticated_at", "expires_at", "correlation_id"}:
            yield AgentLoopStreamEvent("error", {"code": "auth_error", "message": "Authentication context was rejected."})
            return
        if not request.metadata.correlation_id.strip():
            yield AgentLoopStreamEvent("error", {"code": "provider_error", "message": "Missing correlation_id."})
            return
        actor = request.auth_context.get("actor")
        if not isinstance(actor, Mapping) or not actor.get("id") or request.auth_context.get("correlation_id") != request.metadata.correlation_id:
            yield AgentLoopStreamEvent("error", {"code": "unauthorized", "message": "Missing or invalid authenticated actor context."})
            return
        if not request.model.strip():
            yield AgentLoopStreamEvent("error", {"code": "invalid_request", "message": "Missing selected model."})
            return
        if not request.provider.strip():
            yield AgentLoopStreamEvent("error", {"code": "invalid_request", "message": "Missing selected provider."})
            return
        limit = model_limit(self.context_limits, request.provider, request.model)
        if limit is None:
            yield AgentLoopStreamEvent("error", {"code": "context_limit_unknown", "message": "No safe context limit for selected provider and model."})
            return

        messages = request.messages
        if request.context_summary is not None:
            summary = request.context_summary
            if summary.get("source") != "gateway" or summary.get("method") != "deterministic" or not isinstance(summary.get("text"), str):
                yield AgentLoopStreamEvent("error", {"code": "invalid_request", "message": "Invalid context summary."})
                return
            label = "Gateway-derived context from omitted turns (not a new owner request): " + summary["text"]
            messages = (Message("user", label),) + messages
        if context_cost(messages, self.tools) > limit:
            yield AgentLoopStreamEvent("error", {"code": "context_overflow", "message": "Selected model context window exceeded."})
            return

        completion = CompletionRequest(messages=messages, tools=self.tools, stream=True, model=request.model, provider=request.provider)
        try:
            for chunk in self.model_adapter.stream(completion):
                if chunk.type == "text-delta":
                    content = chunk.delta.get("content", "")
                    if content:
                        yield AgentLoopStreamEvent("text-delta", {"content": content})
                elif chunk.type == "tool-call":
                    data = dict(chunk.delta)
                    normalized = dict(data)
                    if not normalized.get("source_id"):
                        name = data.get("name")
                        function = data.get("function")
                        if not isinstance(name, str) and isinstance(function, Mapping):
                            name = function.get("name")
                        normalized["source_id"] = _source_id_for_tool(name if isinstance(name, str) else "", self.tools)
                    call = normalized.get("function") if isinstance(normalized.get("function"), Mapping) else normalized
                    name = call.get("name") if isinstance(call, Mapping) else None
                    if isinstance(name, str):
                        from paa_template.types.contracts import normalize_tool_call

                        parsed = normalize_tool_call(normalized)
                        if parsed is not None:
                            normalized.update({"id": parsed.id, "name": parsed.name, "arguments": parsed.arguments})
                    yield AgentLoopStreamEvent("tool-call", normalized)
                elif chunk.type == "tool-result":
                    data = dict(chunk.delta)
                    if "output" in data:
                        data["output"] = _serialize_tool_output(data["output"])
                    yield AgentLoopStreamEvent("tool-result", data)
                elif chunk.type == "error":
                    yield AgentLoopStreamEvent("error", _safe_model_error(chunk.delta))
                    return
                elif chunk.type == "done":
                    yield AgentLoopStreamEvent("done", {"finish_reason": chunk.delta.get("finish_reason", "stop")})
        except Exception:  # adapters must not leak provider diagnostics to clients
            yield AgentLoopStreamEvent("error", {"code": "provider_error", "message": "Model provider failed."})
