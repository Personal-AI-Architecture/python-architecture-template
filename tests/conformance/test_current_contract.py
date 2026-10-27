import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter, OpenAICompatibleAdapter
from paa_template.adapters.mock import ModelStreamChunk
from paa_template.agent_loop import AgentLoop
from paa_template.gateway import Gateway
from paa_template.types import CompletionRequest, AgentLoopRequest, AgentLoopRequestMetadata, Message


HEADERS = {"X-Actor-ID": "owner", "X-Actor-Permissions": "memory:read,memory:write"}
BODY = {"content": [{"type": "text", "text": "hello"}]}


class RecordingAdapter(MockAdapter):
    def __init__(self):
        super().__init__("answer")
        self.requests = []

    def stream(self, request):
        self.requests.append(request)
        yield from super().stream(request)


class ToolTurnAdapter(MockAdapter):
    def stream(self, request):
        if any(message.role == "tool" for message in request.messages):
            yield ModelStreamChunk("text-delta", {"content": "tool answer"})
            yield ModelStreamChunk("done", {"finish_reason": "stop"})
            return
        yield ModelStreamChunk("text-delta", {"content": "checking "})
        yield ModelStreamChunk("tool-call", {"id": "tc-1", "name": "read_file", "arguments": {"path": "README.md"}})
        yield ModelStreamChunk("tool-result", {"id": "tc-1", "output": {"ok": True}})
        yield ModelStreamChunk("text-delta", {"content": "complete"})
        yield ModelStreamChunk("done", {"finish_reason": "stop"})


class CurrentContractTests(unittest.TestCase):
    def test_tool_turn_events_and_persistence_keep_canonical_parts(self):
        from tempfile import TemporaryDirectory
        from paa_template.gateway.routes import ConversationStore

        with TemporaryDirectory() as directory:
            path = f"{directory}/conversations.json"
            gateway = Gateway(AgentLoop(ToolTurnAdapter()), store=ConversationStore(persistence_path=path))
            response = gateway.handle("POST", "/conversations/messages", body=BODY, headers=HEADERS)
            events = list(response.stream)
            tool_call = next(event for event in events if event["event"] == "tool-call")
            tool_result = next(event for event in events if event["event"] == "tool-result")
            self.assertEqual(tool_call["data"]["source_id"], "read")
            self.assertEqual(tool_call["data"]["arguments"], {"path": "README.md"})
            self.assertEqual(tool_result["data"]["output"], '{"ok":true}')

            conversation_id = response.headers["X-Conversation-ID"]
            restarted = Gateway(AgentLoop(ToolTurnAdapter()), store=ConversationStore(persistence_path=path))
            detail = restarted.handle("GET", f"/conversations/{conversation_id}").body
            self.assertEqual([message["role"] for message in detail["messages"]], ["user", "assistant", "tool", "assistant"])
            self.assertEqual(detail["messages"][1]["content"][-1]["source_id"], "read")
            self.assertEqual(detail["messages"][2]["content"][0]["result"], {"ok": True})
    def test_provider_and_model_change_without_restart_and_are_saved(self):
        selected = {"provider": "alpha", "model": "m1"}
        adapter = RecordingAdapter()
        limits = {"alpha": {"m1": 8192}, "beta": {"m2": 8192}}
        gateway = Gateway(AgentLoop(adapter, context_limits=limits), current_model=lambda: selected["model"], current_provider=lambda: selected["provider"])
        first = gateway.handle("POST", "/conversations/messages", body=BODY, headers=HEADERS)
        list(first.stream)
        selected.update(provider="beta", model="m2")
        second = gateway.handle("POST", f"/conversations/{first.headers['X-Conversation-ID']}/messages", body=BODY, headers=HEADERS)
        list(second.stream)
        self.assertEqual([(request.provider, request.model) for request in adapter.requests], [("alpha", "m1"), ("beta", "m2")])
        detail = gateway.handle("GET", f"/conversations/{first.headers['X-Conversation-ID']}").body
        replies = [message for message in detail["messages"] if message["role"] == "assistant"]
        self.assertEqual([(reply["provider"], reply["model"]) for reply in replies], [("alpha", "m1"), ("beta", "m2")])

    def test_unknown_limit_and_oversized_current_message_do_not_call_model(self):
        adapter = RecordingAdapter()
        gateway = Gateway(AgentLoop(adapter, context_limits={"local": {"mock": 512}}))
        unknown = Gateway(AgentLoop(adapter, context_limits={}), current_provider=lambda: "unknown")
        self.assertEqual(unknown.handle("POST", "/conversations/messages", body=BODY, headers=HEADERS).body["code"], "context_limit_unknown")
        large = gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "x" * 1000}]}, headers=HEADERS)
        self.assertEqual((large.status, large.body["code"]), (422, "context_overflow"))
        self.assertEqual(adapter.requests, [])

    def test_old_turn_omitted_with_notice_and_full_history_retained(self):
        adapter = RecordingAdapter()
        gateway = Gateway(AgentLoop(adapter, context_limits={"local": {"mock": 680}}))
        first = gateway.handle("POST", "/conversations/messages", body=BODY, headers=HEADERS)
        list(first.stream)
        second = gateway.handle("POST", f"/conversations/{first.headers['X-Conversation-ID']}/messages", body=BODY, headers=HEADERS)
        events = list(second.stream)
        self.assertEqual(events[0]["event"], "context_notice")
        self.assertEqual(events[0]["data"]["omitted_turn_count"], 1)
        self.assertEqual(len(adapter.requests[-1].messages), 1)
        detail = gateway.handle("GET", f"/conversations/{first.headers['X-Conversation-ID']}").body
        self.assertEqual(len(detail["messages"]), 4)

    def test_agent_loop_checks_actual_request(self):
        adapter = RecordingAdapter()
        loop = AgentLoop(adapter, context_limits={"local": {"mock": 512}})
        request = AgentLoopRequest((Message("user", "x" * 1000),), AgentLoopRequestMetadata("corr"), "mock", "local", {"actor": {"id": "owner"}, "correlation_id": "corr"})
        self.assertEqual(list(loop.run(request))[0].data["code"], "context_overflow")
        self.assertEqual(adapter.requests, [])

    def test_derived_summary_is_ephemeral_and_labelled(self):
        adapter = RecordingAdapter()
        original = (Message("user", "current"),)
        request = AgentLoopRequest(original, AgentLoopRequestMetadata("corr"), "mock", "local", {"actor": {"id": "owner"}, "correlation_id": "corr"}, {"source": "gateway", "method": "deterministic", "omitted_turn_count": 1, "text": "older fact"})
        list(AgentLoop(adapter).run(request))
        self.assertEqual(len(original), 1)
        self.assertEqual(len(adapter.requests[0].messages), 2)
        self.assertIn("Gateway-derived context", adapter.requests[0].messages[0].text)
        self.assertEqual(adapter.requests[0].messages[1].text, "current")

    def test_adapter_routes_each_profile_without_fallback(self):
        urls = []
        def transport(url, payload, headers):
            urls.append(url)
            yield {"type": "done", "delta": {"finish_reason": "stop"}}
        adapter = OpenAICompatibleAdapter("", transport=transport, provider_profiles={
            "alpha": {"base_url": "http://alpha.local/v1", "model_context_limits": {"m": 8192}},
            "beta": {"base_url": "http://beta.local/v1", "model_context_limits": {"m": 4096}},
        })
        self.assertEqual(AgentLoop(adapter).context_limits["beta"]["m"], 4096)
        for provider in ("alpha", "beta"):
            list(adapter.stream(CompletionRequest((Message("user", "hi"),), model="m", provider=provider)))
        self.assertEqual(urls, ["http://alpha.local/v1/chat/completions", "http://beta.local/v1/chat/completions"])
        with self.assertRaises(ValueError):
            list(adapter.stream(CompletionRequest((Message("user", "hi"),), model="m", provider="missing")))
        with self.assertRaises(ValueError):
            list(adapter.stream(CompletionRequest((Message("user", "hi"),), provider="alpha")))


if __name__ == "__main__":
    unittest.main()
