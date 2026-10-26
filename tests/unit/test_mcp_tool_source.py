import json
import unittest

from paa_template.adapters.mcp_tool_source import McpToolSource


class McpToolSourceTests(unittest.TestCase):
    def test_discovery_binds_configured_identity_and_call_uses_discovered_name(self) -> None:
        methods: list[str] = []

        def transport(request: object) -> tuple[dict, str | None]:
            payload = json.loads(request.data)
            methods.append(payload["method"])
            if payload["method"] == "notifications/initialized":
                return {}, "session-1"
            result = {"tools": [{"name": "search", "description": "Search", "inputSchema": {"type": "object"}, "source": {"id": "spoofed"}}]} if payload["method"] == "tools/list" else {"content": [{"type": "text", "text": "found"}]} if payload["method"] == "tools/call" else {"protocolVersion": "2025-03-26"}
            return {"jsonrpc": "2.0", "id": payload["id"], "result": result}, "session-1"

        adapter = McpToolSource("external", "http://127.0.0.1:9999/mcp", transport)
        with self.assertRaisesRegex(ValueError, "not discovered"):
            adapter.call("search", {})
        definitions = adapter.discover()
        self.assertEqual((definitions[0].name, definitions[0].source, definitions[0].source_kind), ("search", "external", "mcp"))
        self.assertEqual(adapter.call("search", {"query": "PAA"})["content"][0]["text"], "found")
        self.assertEqual(methods, ["initialize", "notifications/initialized", "tools/list", "tools/call"])
