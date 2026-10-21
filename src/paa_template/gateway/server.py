"""Small standard-library HTTP host for the PAA gateway."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class PAARequestHandler(BaseHTTPRequestHandler):
    gateway: Any = None

    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        if self.path.split("?", 1)[0] == "/health":
            self._write_json(200, {"status": "ok", "architecture": "PAA"})
            return
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        body: object | None = None
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                body = json.loads(self.rfile.read(length).decode("utf-8"))
            except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
                body = None
        headers = {key: value for key, value in self.headers.items()}
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


def create_server(host: str, port: int, gateway: Any) -> ThreadingHTTPServer:
    """Create a reusable HTTP server; port 0 selects an available local port."""

    handler = type("BoundPAARequestHandler", (PAARequestHandler,), {"gateway": gateway})
    return ThreadingHTTPServer((host, port), handler)
