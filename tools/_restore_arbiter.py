"""Put back the one answer of the client's that survived, and nothing else.

A test harness overwrote fourteen of his answers. Thirteen are gone — the
audit log recorded which question was answered but not the answer, which is
now fixed but was not fixed then. One survives in a pre-separation backup:
`scope.arbiter`, question 3.3, "when it isn't clear whether something counts,
who decides?"

This restores that single key and touches nothing else. It deliberately does
not guess at the other thirteen: putting a plausible answer into a governance
framework under somebody's name is worse than leaving the question blank for
him to answer himself.

Usage:
    python3 _restore_arbiter.py <backup.json> <framework_versions.json>
    python3 _restore_arbiter.py <backup.json> <framework_versions.json> --write
"""

from __future__ import annotations

import json
import shutil
import sys

KEY = "scope.arbiter"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    backup_path, live_path = argv[0], argv[1]
    write = "--write" in argv

    with open(backup_path, encoding="utf-8") as handle:
        backup = json.load(handle)
    with open(live_path, encoding="utf-8") as handle:
        live = json.load(handle)

    was = (backup.get("working") or {}).get(KEY)
    now = (live.get("working") or {}).get(KEY)
    if not was:
        print(f"{KEY} is not in the backup either. Nothing to do.")
        return 1

    print(f"in the backup : {json.dumps(was, indent=2)}")
    print(f"live now      : {json.dumps(now, indent=2)}")

    if not write:
        print("\nRead-only. Add --write to restore it.")
        return 0

    shutil.copy2(live_path, live_path + ".before-restore")
    live.setdefault("working", {})[KEY] = was
    with open(live_path, "w", encoding="utf-8") as handle:
        json.dump(live, handle, indent=2)
    print(f"\nRestored {KEY}. Backup at {live_path}.before-restore")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
