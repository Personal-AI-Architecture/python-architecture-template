#!/usr/bin/env python3
"""Run native checks and, optionally, the shared language-neutral validator."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_contracts import check_contracts  # noqa: E402
from check_imports import check_imports  # noqa: E402
from check_lockin import check_lockin  # noqa: E402
from check_paa import contract_errors  # noqa: E402


def run_command(label: str, command: list[str]) -> bool:
    print(f"\n[{label}]", flush=True)
    result = subprocess.run(command, cwd=ROOT)
    return result.returncode == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate this Python PAA template.")
    parser.add_argument("--source-checkout", help="Local PAA Git checkout for pinned-source comparison.")
    parser.add_argument("--shared-validator", help="Path to paa-validate.js for cross-language validation.")
    args = parser.parse_args()

    checks = [
        ("PAA pin", contract_errors(args.source_checkout)),
        ("contracts", check_contracts()),
        ("imports", check_imports()),
        ("lock-in", check_lockin()),
    ]
    for label, errors in checks:
        if errors:
            print(f"{label} failed:")
            print("\n".join(f"- {error}" for error in errors))
            return 1
        print(f"[PASS] {label}", flush=True)

    commands = [
        ("typecheck", [sys.executable, "-m", "mypy", "src"]),
        ("syntax", [sys.executable, "-m", "compileall", "-q", "src", "scripts", "tests"]),
        ("unit", [sys.executable, "-m", "unittest", "discover", "-s", "tests/unit", "-p", "test_*.py"]),
        ("integration", [sys.executable, "-m", "unittest", "discover", "-s", "tests/integration", "-p", "test_*.py"]),
        ("conformance", [sys.executable, "-m", "unittest", "discover", "-s", "tests/conformance", "-p", "test_*.py"]),
        ("acceptance", [sys.executable, "scripts/acceptance_check.py"]),
    ]
    if not all(run_command(label, command) for label, command in commands):
        return 1

    if args.shared_validator:
        command = ["node", str(Path(args.shared_validator).resolve()), "--target", "paa.target.json"]
        if args.source_checkout:
            command.extend(["--source-checkout", args.source_checkout])
        if not run_command("shared validator", command):
            return 1
    print("\nPAA Python template validation passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
