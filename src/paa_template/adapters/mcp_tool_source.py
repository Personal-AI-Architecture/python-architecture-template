"""Streamable HTTP MCP translation at the external tool boundary."""

from __future__ import annotations

import json
from typing import Any, Callable
from urllib.request import Request, urlopen

from paa_template.types.contracts import ToolDefinition


class McpToolSource:
    def __init__(self, source_id: str, url: str, transport: Callable[[Request], tuple[dict[str, Any], str | None]] | None = None) -> None:
        if not source_id.strip() or not url.startswith(("http://", "https://")):
            raise ValueError("Invalid MCP source configuration.")
        self.source_id = source_id
        self.url = url
        self.transport = transport or self._http_transport
        self.session_id: str | None = None
        self.initialized = False
        self.known_names: set[str] = set()
        self.next_id = 1

    @staticmethod
    def _http_transport(request: Request) -> tuple[dict[str, Any], str | None]:
        with urlopen(request, timeout=15) as response:
            body = response.read().decode("utf-8")
            if "text/event-stream" in response.headers.get("Content-Type", ""):
                messages = [json.loads(line[5:].strip()) for line in body.splitlines() if line.startswith("data:")]
                payload: dict[str, Any] = next((item for item in messages if "result" in item or "error" in item), {})
            else:
                payload = json.loads(body) if body else {}
            return payload, response.headers.get("Mcp-Session-Id")

    def _send(self, method: str, params: dict[str, Any] | None = None, notification: bool = False) -> dict[str, Any]:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if not notification:
            payload["id"] = self.next_id
            self.next_id += 1
            payload["params"] = params or {}
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-03-26"}
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        response, session_id = self.transport(Request(self.url, data=json.dumps(payload).encode(), headers=headers, method="POST"))
        self.session_id = session_id or self.session_id
        if notification:
            return {}
        if "error" in response or not isinstance(response.get("result"), dict):
            raise ValueError("MCP response was invalid or returned an error.")
        return response["result"]

    def _initialize(self) -> None:
        if self.initialized:
            return
        self._send("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "paa-template", "version": "0.1.0"}})
        self._send("notifications/initialized", notification=True)
        self.initialized = True

    def discover(self) -> tuple[ToolDefinition, ...]:
        self._initialize()
        definitions: list[ToolDefinition] = []
        self.known_names.clear()
        cursor: str | None = None
        while True:
            result = self._send("tools/list", {"cursor": cursor} if cursor else {})
            for item in result.get("tools", []):
                if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip():
                    continue
                name = item["name"]
                self.known_names.add(name)
                definitions.append(ToolDefinition(name, item.get("description", ""), item.get("inputSchema", {}), self.source_id, "discoverable", False, (), "mcp"))
            cursor = result.get("nextCursor")
            if not isinstance(cursor, str) or not cursor:
                return tuple(definitions)

    def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name not in self.known_names:
            raise ValueError("Tool was not discovered from this source.")
        return self._send("tools/call", {"name": name, "arguments": arguments})
