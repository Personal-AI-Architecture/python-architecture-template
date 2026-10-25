#!/usr/bin/env python3
"""Run the local PAA HTTP demo server."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paa_template.adapters.loader import load_model_adapter  # noqa: E402
from paa_template.config.runtime import load_runtime_configuration  # noqa: E402
from paa_template.engine import AgentLoop  # noqa: E402
from paa_template.gateway import Gateway  # noqa: E402
from paa_template.gateway.routes import ConversationStore  # noqa: E402
from paa_template.memory.store import MemoryStore  # noqa: E402
from paa_template.gateway.server import create_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Python PAA gateway demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    api_key = os.environ.get("PAA_DEMO_API_KEY", "")
    if not api_key:
        parser.error("set PAA_DEMO_API_KEY to a local test token before starting")
    runtime = load_runtime_configuration({"memory_root": os.environ.get("RUNTIME_MEMORY_ROOT", ".paa-memory"),
                                          "provider_adapter": os.environ.get("RUNTIME_PROVIDER_ADAPTER", "mock"),
                                          "auth_mode": os.environ.get("RUNTIME_AUTH_MODE", "enforced")})
    if runtime.auth_mode != "enforced":
        parser.error("HTTP starter requires enforced Auth")
    model = "mock"
    limits = None
    adapter_config = None
    if runtime.provider_adapter == "openai-compatible":
        model = os.environ.get("PAA_MODEL_ID", "")
        base_url = os.environ.get("PAA_MODEL_API_BASE_URL", "")
        try:
            limit = int(os.environ.get("PAA_MODEL_CONTEXT_LIMIT", "0"))
        except ValueError:
            limit = 0
        if not model or not base_url or limit <= 0:
            parser.error("OpenAI-compatible mode requires PAA_MODEL_ID, PAA_MODEL_API_BASE_URL, and PAA_MODEL_CONTEXT_LIMIT")
        limits = {"local": {model: limit}}
        adapter_config = {"api_base_url": base_url, "api_key": os.environ.get("PAA_MODEL_API_KEY")}
    adapter = load_model_adapter(runtime, openai_compatible=adapter_config)
    memory_root = Path(runtime.memory_root)
    store = ConversationStore(MemoryStore(str(memory_root)), str(memory_root / "conversations.json"))
    server = create_server(args.host, args.port, Gateway(AgentLoop(adapter, context_limits=limits), store,
                        current_model=lambda: model, current_provider=lambda: "local"), api_key)
    print(f"PAA Python template listening at http://{args.host}:{server.server_port}")
    print("Try: curl http://127.0.0.1:%d/health" % server.server_port)
    print("Press Ctrl-C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping PAA Python template.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
