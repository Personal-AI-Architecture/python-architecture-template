import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter
from paa_template.engine import AgentLoop
from paa_template.types import EngineRequest, EngineRequestMetadata, Message


class EngineTests(unittest.TestCase):
    def test_agent_loop_emits_paa_stream_events(self):
        loop = AgentLoop(MockAdapter("hello"))
        request = EngineRequest(
            messages=(Message("user", "Hi"),),
            metadata=EngineRequestMetadata("corr-1"),
        )
        events = list(loop.run(request, {"X-Actor-ID": "actor-1", "X-Actor-Permissions": "memory:read"}))
        self.assertEqual([event.event for event in events], ["text-delta", "done"])
        self.assertEqual(events[0].data["text"], "hello")
        self.assertEqual(events[-1].data["finish_reason"], "stop")

    def test_actor_headers_are_required(self):
        request = EngineRequest((Message("user", "Hi"),), EngineRequestMetadata("corr-1"))
        events = list(AgentLoop(MockAdapter()).run(request, {}))
        self.assertEqual(events[0].event, "error")


if __name__ == "__main__":
    unittest.main()
