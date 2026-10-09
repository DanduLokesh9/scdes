"""The last few answers recorded in the audit log, with what they replaced.

Confirms the thing that was missing: the log now says what was chosen, not
only that a choice was made. Read-only.

Usage:  python3 _tail_answers.py <log.jsonl> [how many]
"""

from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = argv[0]
    want = int(argv[1]) if len(argv) > 1 else 8

    found = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("action") == "answer_framework_question":
                found.append(event)

    print(f"{len(found)} answer events in the log; the last {want}:\n")
    for event in found[-want:]:
        detail = event.get("detail") or {}
        print(f"  #{event.get('seq')} {str(event.get('at'))[:19]}  "
              f"{detail.get('agency', '?')}")
        print(f"      {detail.get('key')} = {str(detail.get('value'))[:52]}")
        print(f"      was: {str(detail.get('was'))[:52]}")
        print(f"      by:  {detail.get('actor_name') or event.get('actor')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
