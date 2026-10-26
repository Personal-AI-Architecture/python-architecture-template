#!/usr/bin/env python3
"""Run the local PAA HTTP demo server."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paa_template.adapters.loader import load_model_adapter  # noqa: E402
from paa_template.config.runtime import load_runtime_configuration  # noqa: E402
from paa_template.agent_loop import AgentLoop  # noqa: E402
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
    provider = "local"
    limits = None
    adapter_config = None
    if runtime.provider_adapter == "openai-compatible":
        if os.environ.get("PAA_ADAPTER_CONFIG_FILE"):
            profiles = json.loads(Path(os.environ["PAA_ADAPTER_CONFIG_FILE"]).read_text(encoding="utf-8"))["provider_profiles"]
        elif os.environ.get("PAA_MODEL_PROFILES_JSON"):
            profiles = json.loads(os.environ["PAA_MODEL_PROFILES_JSON"])
        else:
            model = os.environ.get("PAA_MODEL_ID", "")
            base_url = os.environ.get("PAA_MODEL_API_BASE_URL", "")
            try:
                limit = int(os.environ.get("PAA_MODEL_CONTEXT_LIMIT", "0"))
            except ValueError:
                limit = 0
            if not model or not base_url or limit <= 0:
                parser.error("OpenAI-compatible mode requires provider profiles or PAA_MODEL_ID, PAA_MODEL_API_BASE_URL, and PAA_MODEL_CONTEXT_LIMIT")
            profiles = {"local": {"base_url": base_url, "api_key_env": "PAA_MODEL_API_KEY", "model_context_limits": {model: limit}}}
        if not isinstance(profiles, dict) or not profiles:
            parser.error("OpenAI-compatible mode requires provider profiles")
        provider = os.environ.get("PAA_DEFAULT_PROVIDER") or next(iter(profiles))
        model = os.environ.get("PAA_MODEL_ID") or next(iter(profiles[provider]["model_context_limits"]))
        limits = {name: profile["model_context_limits"] for name, profile in profiles.items()}
        adapter_config = {"provider_profiles": profiles}
    adapter = load_model_adapter(runtime, openai_compatible=adapter_config)
    memory_root = Path(runtime.memory_root)
    memory = MemoryStore(str(memory_root))
    if memory.read_preferences() is None:
        memory.write_preferences(model, provider)
    store = ConversationStore(memory, str(memory_root / "conversations.json"))
    def read_selection() -> tuple[str, str]:
        selection = memory.read_preferences()
        if selection is None:
            raise ValueError("Owner preferences are unavailable")
        return selection["model"], selection["active_provider_profile"]
    server = create_server(args.host, args.port, Gateway(AgentLoop(adapter, context_limits=limits), store,
                        current_selection=read_selection), api_key)
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
