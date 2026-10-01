"""Remove tickets filed by the check harnesses, keeping every real one.

The jsdom checks file genuine reports against whatever server they are pointed
at, which is the only way to prove the round trip works — and it leaves their
test rows sitting in the queue next to reports from actual people.

Named addresses only. Nothing here globs, guesses at a date range, or decides
what looks like test data: a report is deleted because its reporter is on the
list below, and the list is the addresses the harnesses use. Anything else
survives, including anything that merely resembles a test.

The store is rewritten via a temporary file and rename, and the previous
contents are kept alongside it, because a bug queue is somebody's evidence.

    python3 deploy/drop_test_tickets.py            # say what would go
    python3 deploy/drop_test_tickets.py --apply    # do it
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

STORE = Path("data/bugs.jsonl")

# The addresses the harnesses report as — the two in tools/check_notify.js.
# check_bug_widget.js files as jane.smith@des.sc.gov, which is the seeded SCDES
# operator and therefore deliberately not on this list.
#
# dev@iiac.ai was on it briefly and should not have been. It is not an address
# any harness uses; it is a person at IIA testing the form, and "It's fixed and
# not moving" is a real observation about the lifecycle, not test noise. A list
# like this is only safe while every entry is one a script actually writes.
HARNESS = {
    "notify.check@iiac.ai",
    "someone.else@iiac.ai",
}


def main() -> int:
    apply = "--apply" in sys.argv
    if not STORE.exists():
        print(f"no {STORE} — nothing to do")
        return 0

    keep: list[str] = []
    dropped: list[dict] = []
    for line in STORE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            keep.append(line)          # unreadable is not the same as unwanted
            continue
        if str(row.get("reporter", "")).strip().lower() in HARNESS:
            dropped.append(row)
        else:
            keep.append(line)

    for row in dropped:
        print(f"  drop  {row.get('id')}  {row.get('reporter')}"
              f"  {str(row.get('happened', ''))[:52]}")
    print(f"\n{len(dropped)} to remove, {len(keep)} kept")

    if not dropped or not apply:
        if dropped:
            print("dry run — pass --apply to write")
        return 0

    backup = STORE.with_suffix(".jsonl.bak")
    shutil.copy2(STORE, backup)
    tmp = STORE.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(l + "\n" for l in keep), encoding="utf-8")
    os.replace(tmp, STORE)
    print(f"written · previous contents at {backup}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
