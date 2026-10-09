"""Who wrote the answers that were sitting in the shared framework file?

Before agencies were separated there was one `framework_versions.json`, so both
registered containers wrote into it. The split leaves that file with the corpus
owner. If the work in it was actually done from the other account, it is now
filed under the wrong agency and its author will find an empty framework.

Reads only. Run it before deciding whether anything needs moving.

    python3 deploy/whose_answers.py
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

VERSIONS = Path("corpus/config/framework_versions.json")


def main() -> int:
    if not VERSIONS.is_file():
        print(f"{VERSIONS} is not there — nothing was shared")
        return 0

    blob = json.loads(VERSIONS.read_text(encoding="utf-8")) or {}
    working = blob.get("working", {})
    print(f"{len(working)} answered question(s) in the shared file\n")

    who = Counter()
    for key, row in sorted(working.items()):
        author = row.get("by") or row.get("answered_by") or "(not recorded)"
        title = row.get("title") or row.get("answered_title") or ""
        when = (row.get("at") or row.get("answered_on") or "")[:16]
        who[author] += 1
        value = str(row.get("value", ""))
        print(f"  {key:<28} {author:<22} {when}")
        print(f"      {value[:96]}")

    print("\nby author:")
    for author, n in who.most_common():
        print(f"  {n:>3}  {author}")

    print(f"\nnumbered versions: {len(blob.get('versions', []))}")
    print(f"acceptances:       {len(blob.get('acceptances', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
