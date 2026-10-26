#!/usr/bin/env python3
"""End-to-end acceptance checks for the Python PAA template."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paa_template.adapters import MockAdapter, load_model_adapter  # noqa: E402
from paa_template.config import RuntimeConfiguration, load_runtime_configuration  # noqa: E402
from paa_template.agent_loop import AgentLoop  # noqa: E402
from paa_template.gateway import Gateway  # noqa: E402
from paa_template.memory import MemoryStore  # noqa: E402
from paa_template.types import AgentLoopRequest, AgentLoopRequestMetadata, Message  # noqa: E402
from check_contracts import check_contracts  # noqa: E402
from check_imports import check_imports  # noqa: E402
from check_lockin import check_lockin  # noqa: E402
from check_paa import contract_errors  # noqa: E402


def main() -> int:
    runtime = load_runtime_configuration({"default": {"memory_root": "/tmp/paa-python-acceptance", "provider_adapter": "mock", "auth_mode": "enforced", "tool_sources": ["memory"]}})
    assert runtime.provider_adapter == "mock"
    assert load_model_adapter(runtime).name == "mock"
    assert load_model_adapter(RuntimeConfiguration(runtime.memory_root, "local", runtime.auth_mode, runtime.tool_sources)).name == "mock"
    assert load_model_adapter(RuntimeConfiguration(runtime.memory_root, "openai-compatible", runtime.auth_mode, runtime.tool_sources), openai_compatible={"api_base_url": "http://provider.local/v1"}).name == "openai-compatible"

    memory = MemoryStore(runtime.memory_root)
    gateway = Gateway(AgentLoop(MockAdapter("acceptance-ok")))
    gateway.store.memory = memory
    headers = {"X-Actor-ID": "actor-acceptance", "X-Actor-Permissions": "memory:read,memory:write"}
    response = gateway.handle("POST", "/conversations/messages", body={"content": [{"type": "text", "text": "Hello"}], "metadata": {"source": "acceptance"}}, headers=headers)
    assert response.status == 200
    events = list(response.stream)
    assert events[0]["event"] == "text-delta"
    assert events[-1]["event"] == "done"
    assert events[-1]["data"]["finish_reason"] == "stop"
    conversation_id = response.headers["X-Conversation-ID"]
    assert gateway.handle("GET", "/conversations").body["total"] == 1
    assert gateway.handle("GET", f"/conversations/{conversation_id}").body["messages"][-1]["role"] == "assistant"
    assert memory.export()["history"]

    for label, errors in [("paa pin", contract_errors()), ("contracts", check_contracts()), ("imports", check_imports()), ("lock-in", check_lockin())]:
        assert not errors, f"{label} check failed: {' | '.join(errors)}"
    print("Acceptance check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
