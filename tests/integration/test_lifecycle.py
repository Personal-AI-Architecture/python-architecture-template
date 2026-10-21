import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter
from paa_template.engine import AgentLoop
from paa_template.gateway import Gateway
from paa_template.memory import MemoryStore


class GatewayLifecycleTests(unittest.TestCase):
    def test_create_stream_list_detail_and_export(self):
        memory = MemoryStore("/tmp/paa-python-test-memory")
        gateway = Gateway(AgentLoop(MockAdapter("integration-ok")), store=None)
        gateway.store.memory = memory
        headers = {"X-Actor-ID": "actor-integration", "X-Actor-Permissions": "memory:read,memory:write"}

        response = gateway.handle("POST", "/conversations/messages", body={"content": "Start"}, headers=headers)
        events = list(response.stream)
        self.assertEqual(events[-1]["data"]["finish_reason"], "stop")
        conversation_id = response.headers["X-Conversation-ID"]

        listing = gateway.handle("GET", "/conversations")
        self.assertEqual(listing.body["total"], 1)
        detail = gateway.handle("GET", f"/conversations/{conversation_id}")
        self.assertEqual([item["role"] for item in detail.body["messages"]], ["user", "assistant"])
        exported = memory.export()
        self.assertEqual(exported["memory_root"], "/tmp/paa-python-test-memory")
        self.assertGreaterEqual(len(exported["history"]), 2)


if __name__ == "__main__":
    unittest.main()
