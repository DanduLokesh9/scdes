"""What is actually in this deployment: who is registered, and what is shared.

Written to answer one question honestly — if two agencies are registered here,
whose framework answers are they looking at? Reads only; changes nothing.

    python3 deploy/tenancy_report.py
"""

from __future__ import annotations

import json
from pathlib import Path

STORE = Path("data/tenancy.json")
CONFIG = Path("corpus/config")


def main() -> int:
    if STORE.is_file():
        data = json.loads(STORE.read_text(encoding="utf-8"))
    else:
        data = {}

    agencies = data.get("agencies", {})
    print(f"registered agencies: {len(agencies)}")
    for code, container in agencies.items():
        members = [m.get("email", "?") for m in container.get("members", [])]
        print(f"  {code:<12} {container.get('status', '?'):<10} {members}")

    pending = data.get("pending", {})
    print(f"\npending: {len(pending)}")
    for address, row in pending.items():
        print(f"  {address:<28} {row.get('state', '?'):<12} {row.get('status', '?')}")

    print(f"\nsessions: {len(data.get('sessions', {}))}")

    print("\nshared, single-copy state in corpus/config:")
    for name in ("framework_versions.json", "decider.json", "agency.yaml",
                 "framework_adoption.json"):
        path = CONFIG / name
        if not path.is_file():
            print(f"  {name:<28} (absent)")
            continue
        size = path.stat().st_size
        note = ""
        if name == "framework_versions.json":
            try:
                blob = json.loads(path.read_text(encoding="utf-8")) or {}
                working = blob.get("working", {})
                note = f"— {len(working)} answered question(s)"
            except ValueError:
                note = "— unreadable"
        print(f"  {name:<28} {size:>7} bytes {note}")

    print("\ncorpus documents on disk (one set, shared by every agency):")
    for sub in ("framework", "manual", "appendices", "charter"):
        d = Path("corpus") / sub
        n = len(list(d.iterdir())) if d.is_dir() else 0
        print(f"  {sub:<12} {n} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
