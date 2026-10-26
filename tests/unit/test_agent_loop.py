import unittest

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter
from paa_template.agent_loop import AgentLoop
from paa_template.types import AgentLoopRequest, AgentLoopRequestMetadata, Message


class AgentLoopTests(unittest.TestCase):
    def test_agent_loop_emits_paa_stream_events(self):
        loop = AgentLoop(MockAdapter("hello"))
        request = AgentLoopRequest(
            messages=(Message("user", "Hi"),),
            metadata=AgentLoopRequestMetadata("corr-1"),
            model="mock",
            provider="local",
            auth_context={"actor": {"id": "actor-1"}, "correlation_id": "corr-1"},
        )
        events = list(loop.run(request))
        self.assertEqual([event.event for event in events], ["text-delta", "done"])
        self.assertEqual(events[0].data["content"], "hello")
        self.assertEqual(events[-1].data["finish_reason"], "stop")

    def test_authenticated_context_is_required(self):
        request = AgentLoopRequest((Message("user", "Hi"),), AgentLoopRequestMetadata("corr-1"), "mock", "local", {})
        events = list(AgentLoop(MockAdapter()).run(request))
        self.assertEqual(events[0].event, "error")


if __name__ == "__main__":
    unittest.main()
