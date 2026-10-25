"""Small standard-library HTTP host for the PAA gateway."""

from __future__ import annotations

import json
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class PAARequestHandler(BaseHTTPRequestHandler):
    gateway: Any = None
    owner_token: str = ""
    max_request_bytes = 1024 * 1024

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path.split("?", 1)[0] == "/health":
            self._write_json(200, {"status": "ok", "architecture": "PAA"})
            return
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._dispatch("POST")

    def do_PUT(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._dispatch("PUT")

    def _dispatch(self, method: str) -> None:
        supplied = self.headers.get("X-API-Key", "")
        authorization = self.headers.get("Authorization", "")
        if authorization.lower().startswith("bearer "):
            supplied = authorization[7:].strip()
        if not supplied or not hmac.compare_digest(supplied, self.owner_token):
            self._write_json(401, {"code": "unauthenticated", "message": "Authentication required."})
            return
        body: object | None = None
        if method in {"POST", "PUT"}:
            try:
                length = int(self.headers.get("Content-Length", "-1"))
                if length < 0:
                    self._write_json(411, {"code": "length_required", "message": "Content-Length required."})
                    return
                if length > self.max_request_bytes:
                    # Let an actively uploading client finish a modest body before
                    # responding, so it can receive the 413 instead of a reset.
                    if length <= 4 * self.max_request_bytes:
                        remaining = length
                        while remaining:
                            chunk = self.rfile.read(min(remaining, 64 * 1024))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    self._write_json(413, {"code": "request_too_large", "message": "Request body too large."})
                    self.close_connection = True
                    return
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                body = None
        headers = {"X-Actor-ID": "local-owner", "X-Actor-Permissions": "memory:read,memory:write"}
        if self.path == "/owner/preferences":
            memory = self.gateway.store.memory
            if method == "GET":
                try:
                    value = memory.read_preferences()
                except (OSError, ValueError):
                    value = None
                self._write_json(200 if value else 503, value or {"code": "selection_unavailable", "message": "Preferences unavailable."})
                return
            if method == "PUT":
                if not isinstance(body, dict) or not isinstance(body.get("model"), str) or not body["model"] or not isinstance(body.get("active_provider_profile"), str) or not body["active_provider_profile"]:
                    self._write_json(400, {"code": "invalid_request", "message": "Model and active_provider_profile are required."})
                    return
                try:
                    memory.write_preferences(body["model"], body["active_provider_profile"])
                except (OSError, ValueError):
                    self._write_json(503, {"code": "selection_unavailable", "message": "Preferences unavailable."})
                    return
                self._write_json(200, body)
                return
        response = self.gateway.handle(method, self.path, body=body, headers=headers)
        if response.stream is not None:
            self.send_response(response.status)
            for key, value in response.headers.items():
                if key.lower() in {"connection", "content-length"}:
                    continue
                self.send_header(key, value)
            self.send_header("Connection", "close")
            self.end_headers()
            for event in response.stream:
                payload = f"event: {event['event']}\ndata: {json.dumps(event.get('data', {}))}\n\n".encode("utf-8")
                self.wfile.write(payload)
                self.wfile.flush()
            self.close_connection = True
            return
        self._write_json(response.status, response.body or {})

    def _write_json(self, status: int, body: object) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, _format: str, *_args: object) -> None:
        return


def create_server(host: str, port: int, gateway: Any, owner_token: str) -> ThreadingHTTPServer:
    """Create a reusable HTTP server; port 0 selects an available local port."""

    if not owner_token:
        raise ValueError("A demo API key is required.")
    handler = type("BoundPAARequestHandler", (PAARequestHandler,), {"gateway": gateway, "owner_token": owner_token})
    return ThreadingHTTPServer((host, port), handler)
