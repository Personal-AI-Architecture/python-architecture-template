"""Provider-neutral Agent Loop."""

from collections.abc import Iterable, Iterator, Mapping
from typing import Any

from paa_template.types import CompletionRequest, EngineRequest, EngineStreamEvent, ToolDefinition
from paa_template.types.contracts import normalize_tool_definition


class AgentLoop:
    def __init__(self, model_adapter: Any, tools: Iterable[ToolDefinition] = ()) -> None:
        self.model_adapter = model_adapter
        self.tools = tuple(tool for tool in (normalize_tool_definition(item) for item in tools) if tool is not None)

    def run(self, request: EngineRequest, actor_headers: Mapping[str, str]) -> Iterator[EngineStreamEvent]:
        if not request.metadata.correlation_id.strip():
            yield EngineStreamEvent("error", {"code": "provider_error", "message": "Missing correlation_id."})
            return
        if not actor_headers.get("X-Actor-ID") or not actor_headers.get("X-Actor-Permissions"):
            yield EngineStreamEvent("error", {"code": "provider_error", "message": "Missing required actor headers."})
            return

        completion = CompletionRequest(messages=request.messages, tools=self.tools, stream=True)
        try:
            for chunk in self.model_adapter.stream(completion):
                if chunk.type == "text-delta":
                    content = chunk.delta.get("content", "")
                    if content:
                        yield EngineStreamEvent("text-delta", {"text": content})
                elif chunk.type == "tool-call":
                    yield EngineStreamEvent("tool-call", dict(chunk.delta))
                elif chunk.type == "tool-result":
                    yield EngineStreamEvent("tool-result", dict(chunk.delta))
                elif chunk.type == "error":
                    yield EngineStreamEvent("error", dict(chunk.delta))
                elif chunk.type == "done":
                    yield EngineStreamEvent("done", {"finish_reason": chunk.delta.get("finish_reason", "stop")})
        except Exception as error:  # adapters must not leak provider diagnostics to clients
            yield EngineStreamEvent("error", {"code": "provider_error", "message": str(error)})
