import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter
from paa_template.engine import AgentLoop
from paa_template.gateway import Gateway


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.gateway = Gateway(AgentLoop(MockAdapter("gateway-ok")))
        self.headers = {"X-Actor-ID": "actor-1", "X-Actor-Permissions": "memory:read,memory:write"}

    def test_canonical_message_route_streams_and_persists(self):
        response = self.gateway.handle("POST", "/conversations/messages", body={"content": "Hello"}, headers=self.headers)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["Content-Type"], "text/event-stream")
        events = list(response.stream)
        self.assertEqual(events[0]["event"], "text-delta")
        self.assertEqual(events[-1]["event"], "done")
        self.assertEqual(len(self.gateway.store.list()[0].messages), 2)

    def test_public_request_rejects_provider_shaped_messages(self):
        response = self.gateway.handle("POST", "/conversations/messages", body={"messages": []}, headers=self.headers)
        self.assertEqual(response.status, 400)


if __name__ == "__main__":
    unittest.main()
