"""Bug tickets nobody has closed. Read-only.

Usage:  python3 _open_tickets.py <bugs.jsonl>
"""

from __future__ import annotations

import json
import sys

DONE = {"closed", "fixed", "resolved", "wontfix", "declined"}


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    rows = []
    with open(argv[0], encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue

    # One entry per ticket, latest wins — the file is append-only, so a ticket
    # that was answered appears more than once.
    latest: dict[str, dict] = {}
    for row in rows:
        key = str(row.get("id") or row.get("ref") or "")
        if key:
            latest[key] = row

    open_ones = [r for r in latest.values()
                 if str(r.get("status", "")).lower() not in DONE
                 and not r.get("replies")]
    print(f"{len(latest)} tickets, {len(open_ones)} with no reply\n")
    for row in sorted(open_ones, key=lambda r: str(r.get("at", ""))):
        print(f"  {row.get('id')}  {str(row.get('at'))[:10]}  "
              f"{str(row.get('reporter') or ''):<20} "
              f"[{row.get('view') or '?'}]")
        expected = str(row.get("expected") or "").strip()
        happened = str(row.get("happened") or "").strip()
        if expected:
            print(f"       expected:  {expected[:88]}")
        if happened:
            print(f"       happened:  {happened[:88]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
