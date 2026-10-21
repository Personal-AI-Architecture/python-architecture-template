#!/usr/bin/env python3
"""Run the local PAA HTTP demo server."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from paa_template.adapters import MockAdapter  # noqa: E402
from paa_template.engine import AgentLoop  # noqa: E402
from paa_template.gateway import Gateway  # noqa: E402
from paa_template.gateway.server import create_server  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the local Python PAA gateway demo.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    server = create_server(args.host, args.port, Gateway(AgentLoop(MockAdapter())))
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
