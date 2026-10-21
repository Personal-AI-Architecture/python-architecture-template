#!/usr/bin/env python3
"""Validate the pinned PAA contract mirror for this Python template."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_lock() -> dict:
    return json.loads((ROOT / "paa.lock.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def contract_errors(source_checkout: str | None = None) -> list[str]:
    errors: list[str] = []
    try:
        lock = load_lock()
    except (OSError, json.JSONDecodeError) as error:
        return [f"Unable to load paa.lock.json: {error}"]

    if lock.get("repository") != "https://github.com/Personal-AI-Architecture/the-architecture.git":
        errors.append("paa.lock.json repository must point to the PAA architecture repository.")
    if lock.get("ref") != "main":
        errors.append("paa.lock.json ref must be main.")
    if not isinstance(lock.get("commit"), str) or len(lock["commit"]) != 40 or any(character not in "0123456789abcdef" for character in lock["commit"]):
        errors.append("paa.lock.json commit must be a full 40-character SHA.")
    if lock.get("source_root") != "vendor/paa-contracts":
        errors.append("paa.lock.json source_root must be vendor/paa-contracts.")

    files = lock.get("contract_files", [])
    vendor_root = ROOT / lock.get("source_root", "")
    actual = sorted(path.relative_to(vendor_root).as_posix() for path in vendor_root.rglob("*") if path.is_file()) if vendor_root.exists() else []
    if actual != sorted(files):
        errors.append("Vendored contract file set differs from paa.lock.json.")

    for relative in files:
        vendor_path = vendor_root / relative
        mirror_path = ROOT / relative
        if not vendor_path.is_file():
            errors.append(f"Missing vendored contract: {lock.get('source_root')}/{relative}.")
            continue
        if sha256(vendor_path) != lock.get("sha256", {}).get(relative):
            errors.append(f"Hash drift in vendored contract: {relative}.")
        if not mirror_path.is_file():
            errors.append(f"Missing local contract mirror: {relative}.")
        elif mirror_path.read_bytes() != vendor_path.read_bytes():
            errors.append(f"Local contract mirror differs from vendored source: {relative}.")

        if source_checkout:
            try:
                source_bytes = subprocess.check_output(
                    ["git", "-C", source_checkout, "show", f"{lock['commit']}:{relative}"],
                    stderr=subprocess.STDOUT,
                )
                if source_bytes != vendor_path.read_bytes():
                    errors.append(f"Vendored contract differs from {lock['commit']}:{relative}.")
            except subprocess.CalledProcessError as error:
                errors.append(f"Unable to read pinned PAA source {relative}: {error.output.decode(errors='replace').strip()}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-checkout")
    args = parser.parse_args()
    errors = contract_errors(args.source_checkout)
    if errors:
        print("PAA pin check failed:")
        print("\n".join(f"- {error}" for error in errors))
        return 1
    print("PAA pin check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
