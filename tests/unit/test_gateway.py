import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter
from paa_template.engine import AgentLoop
from paa_template.gateway import Gateway
from paa_template.adapters.mock import ModelStreamChunk


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.gateway = Gateway(AgentLoop(MockAdapter("gateway-ok")))
        self.headers = {"X-Actor-ID": "actor-1", "X-Actor-Permissions": "memory:read,memory:write"}

    def test_auth_context_rejects_unknown_top_level_field(self):
        from paa_template.types.contracts import EngineRequest, EngineRequestMetadata
        request = EngineRequest(messages=(), metadata=EngineRequestMetadata(correlation_id="corr"), model="mock", provider="local", auth_context={"actor": {"id": "owner"}, "correlation_id": "corr", "unexpected": "spoof"})
        events = list(AgentLoop(MockAdapter()).run(request))
        self.assertEqual([event.event for event in events], ["error"])
        self.assertEqual(events[0].data["code"], "auth_error")

    def test_canonical_message_route_streams_and_persists(self):
        response = self.gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "Hello"}]}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
        events = list(response.stream)
        self.assertEqual(events[0]["event"], "text-delta")
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(len(self.gateway.store.list()[0].messages), 2)
        detail = self.gateway.handle("GET", f"/conversations/{response.headers['X-Conversation-ID']}")
        self.assertEqual(detail.body["messages"][0]["content"], [{"type": "text", "text": "Hello"}])
        self.assertEqual(detail.body["messages"][1]["content"], [{"type": "text", "text": "gateway-ok"}])

    def test_old_string_shape_is_rejected(self):
        response = self.gateway.handle("POST", "/conversations/messages", body={"content": "Hello"}, headers=self.headers)
        self.assertEqual(response.status, 400)

    def test_model_is_selected_for_each_message(self):
        chosen = ["first"]
        seen = []

        class RecordingAdapter(MockAdapter):
            def stream(self, request):
                seen.append(request.model)
                yield from super().stream(request)

        gateway = Gateway(AgentLoop(RecordingAdapter(), context_limits={"local": {"first": 8192, "second": 8192}}), current_model=lambda: chosen[0])
        response = gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "Hi"}]}, headers=self.headers)
        list(response.stream)
        chosen[0] = "second"
        response = gateway.handle("POST", f"/conversations/{response.headers['X-Conversation-ID']}/messages", body={"content": [{"type": "text", "text": "Again"}]}, headers=self.headers)
        self.assertEqual(response.status, 200)
        list(response.stream)
        self.assertEqual(seen, ["first", "second"])

    def test_public_request_rejects_provider_shaped_messages(self):
        response = self.gateway.handle("POST", "/conversations/messages", body={"messages": []}, headers=self.headers)
        self.assertEqual(response.status, 400)

    def test_model_error_categories_reach_gateway_without_fallback_or_raw_text(self):
        calls = []
        class FailingAdapter(MockAdapter):
            def __init__(self, code, capability=None):
                self.code, self.capability = code, capability
            def stream(self, request):
                calls.append((request.model, request.provider))
                yield ModelStreamChunk("error", {"code": self.code, "capability": self.capability, "message": "secret=/tmp/key"})
        for code, capability in (("model_unavailable", None), ("capability_unsupported", "image_input")):
            gateway = Gateway(AgentLoop(FailingAdapter(code, capability)))
            response = gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "hello"}]}, headers=self.headers)
            events = list(response.stream)
            self.assertEqual([event["event"] for event in events], ["error"])
            self.assertEqual(events[0]["data"]["code"], code)
            if capability:
                self.assertEqual(events[0]["data"]["capability"], capability)
            self.assertNotIn("secret", str(events))
            self.assertEqual(len(gateway.store.list()[0].messages), 1)
        self.assertEqual(calls, [("mock", "local"), ("mock", "local")])

    def test_extension_is_inert_and_unknown_core_field_is_rejected(self):
        valid = self.gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "hello", "extensions": {"future": "ignored"}}]}, headers=self.headers)
        self.assertEqual(valid.status, 200)
        list(valid.stream)
        invalid = self.gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "hello", "future": "outside extensions"}]}, headers=self.headers)
        self.assertEqual(invalid.status, 400)


if __name__ == "__main__":
    unittest.main()
