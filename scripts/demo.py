#!/usr/bin/env python3
"""Show one complete PAA request, stream, and persisted conversation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paa_template.adapters import MockAdapter  # noqa: E402
from paa_template.engine import AgentLoop  # noqa: E402
from paa_template.gateway import Gateway  # noqa: E402


def main() -> int:
    gateway = Gateway(AgentLoop(MockAdapter("Hello from a PAA Agent Loop.")))
    response = gateway.handle(
        "POST",
        "/conversations/messages",
        body={"content": "Explain what PAA is."},
        headers={"X-Actor-ID": "demo-user", "X-Actor-Permissions": "memory:read,memory:write"},
    )
    events = list(response.stream or ())
    conversation_id = response.headers.get("X-Conversation-ID")
    print("PAA Python template demo")
    print("========================")
    print("Request: POST /conversations/messages")
    print(f"Conversation: {conversation_id}")
    print("Stream:")
    for event in events:
        print(f"  {event['event']}: {json.dumps(event.get('data', {}))}")
    detail = gateway.handle("GET", f"/conversations/{conversation_id}")
    print(f"Persisted messages: {len(detail.body['messages']) if detail.body else 0}")
    print("\nPAA boundary demonstrated: Gateway -> Agent Loop -> Model Adapter -> stream -> memory.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
