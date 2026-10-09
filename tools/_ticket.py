"""One ticket in full, or all of them. Read-only.

Usage:  python3 _ticket.py <bugs.jsonl> [BUG-XXXX ...]
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path, wanted = argv[0], set(argv[1:])
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                bug = json.loads(line)
            except ValueError:
                continue
            if wanted and bug.get("id") not in wanted:
                continue
            print(f"=== {bug.get('id')}  {str(bug.get('at'))[:10]}  "
                  f"[{bug.get('view')}]  {bug.get('reporter')}")
            for name in ("expected", "happened"):
                said = str(bug.get(name) or "").strip()
                if said:
                    print(f"  {name}:")
                    for para in said.splitlines():
                        if para.strip():
                            print(f"    {para.strip()}")
            if bug.get("replies"):
                print(f"  replies: {len(bug['replies'])}")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
