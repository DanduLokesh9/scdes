"""What is in one agency's working answers. Read-only.

Quoting a Python one-liner through PowerShell into ssh into bash mangles it
three different ways, so this is a file. Copied to the box and run there.

Usage:  python3 _peek_tenant.py <path to framework_versions.json>
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if not argv:
        print("give me a framework_versions.json")
        return 1
    try:
        with open(argv[0], encoding="utf-8") as handle:
            held = json.load(handle)
    except (OSError, ValueError) as why:
        print(f"could not read it: {why}")
        return 1

    working = held.get("working") or {}
    print(f"answers  : {len(working)}")
    print(f"version  : {held.get('current')}")
    print(f"adopted  : {(held.get('adopted') or {}).get('adopted_on') or 'no'}")
    print(f"history  : {len(held.get('history') or [])} saved versions")
    for key in sorted(working):
        raw = working[key]
        value = raw.get("value") if isinstance(raw, dict) else raw
        by = raw.get("by") if isinstance(raw, dict) else ""
        shown = str(value)
        if len(shown) > 54:
            shown = shown[:51] + "..."
        print(f"  {key:<26} {shown:<56} {by}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
