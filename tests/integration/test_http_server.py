import json
import threading
import unittest
from urllib.request import Request, urlopen

from tests import bootstrap  # noqa: F401
from paa_template.adapters import MockAdapter
from paa_template.engine import AgentLoop
from paa_template.gateway import Gateway
from paa_template.gateway.server import create_server


class HTTPServerTests(unittest.TestCase):
    def test_health_and_canonical_message_route(self):
        server = create_server("127.0.0.1", 0, Gateway(AgentLoop(MockAdapter("http-ok"))))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}"
            with urlopen(f"{base}/health") as response:
                self.assertEqual(json.loads(response.read()), {"status": "ok", "architecture": "PAA"})
            request = Request(
                f"{base}/conversations/messages",
                data=json.dumps({"content": [{"type": "text", "text": "Hello"}]}).encode(),
                headers={
                    "Content-Type": "application/json",
                    "X-Actor-ID": "http-test",
                    "X-Actor-Permissions": "memory:read",
                },
                method="POST",
            )
            with urlopen(request) as response:
                stream = response.read().decode()
            self.assertIn("event: text-delta", stream)
            self.assertIn("event: done", stream)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
