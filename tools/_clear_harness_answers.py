"""Remove answers a test harness wrote into somebody's real container.

Not a guess at what they should have been — a removal. A harness overwrote
fourteen of the client's answers; one was recoverable from a backup and has
been put back. The other thirteen are gone, and what sits in their place is
test data: `who.shape` reads "council" when his own notes say two people decide
and the CEO has sole veto.

Leaving that is the worst of the three options. He could export a framework
stating a governance structure he never chose, under his name, with a date on
it. Blanking them puts the questions back in front of him, which is what the
module does with anything unanswered — a gap it names rather than a hole it
hides.

Only keys whose recorded author is the harness are touched. Anything a person
wrote is left exactly as it is, and a timestamped backup is written first.

Usage:
    python3 _clear_harness_answers.py <framework_versions.json>
    python3 _clear_harness_answers.py <framework_versions.json> --write
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone

#: Names the automated checks record themselves under. Anything else is a
#: person, and is never touched.
HARNESS_AUTHORS = {"Check", "Office of Technology", "Export check",
                   "Automated walk", "Admin check"}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = argv[0]
    write = "--write" in argv

    with open(path, encoding="utf-8") as handle:
        held = json.load(handle)
    working = held.get("working") or {}

    theirs, mine = [], []
    for key, raw in sorted(working.items()):
        who = raw.get("by", "") if isinstance(raw, dict) else ""
        (mine if who in HARNESS_AUTHORS else theirs).append((key, who))

    print(f"{len(theirs)} answers by a person — untouched")
    print(f"{len(mine)} answers by the harness — to be removed:\n")
    for key, who in mine:
        raw = working[key]
        value = raw.get("value") if isinstance(raw, dict) else raw
        print(f"  {key:<24} {str(value)[:44]:<46} ({who})")

    if not write:
        print("\nRead-only. Add --write to remove them.")
        return 0
    if not mine:
        print("\nNothing to remove.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = f"{path}.before-clear-{stamp}"
    shutil.copy2(path, backup)
    for key, _ in mine:
        working.pop(key, None)
    held["working"] = working
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(held, handle, indent=2)
    print(f"\nRemoved {len(mine)}. Backup at {backup}")
    print("Those questions will now be asked again, unanswered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
