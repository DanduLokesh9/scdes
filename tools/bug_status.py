"""What is still outstanding in the bug tracker, and what has been dealt with.

Written because the question "how many bugs are left" kept being answered from
memory, and the tracker is the only thing that actually knows. Reads the same
store the application reads, so the answer here and the answer on the Report a
problem screen cannot disagree.

    python -m tools.bug_status              the counts, and what is open
    python -m tools.bug_status --all        every ticket, whatever its state
    python -m tools.bug_status --full       what each outstanding one says
    python -m tools.bug_status --real       skip the ones that are test noise

On the server:

    cd /opt/governingai && sudo .venv/bin/python -m tools.bug_status
"""

from __future__ import annotations

import collections
import sys
from typing import Any

from app import bugs


#: Not `name`, which is the reporter's own name, and not `screen`, which is
#: their window size — both of which this tool printed as the description
#: before the store was actually looked at.
DESCRIBES = ("happened", "expected")

#: Keyboard mashing, which people type to get past a required field.
NOISE = frozenset(("asdf", "asd", "sdf", "test", "testing", "abc", "aaa",
                   "qwerty", "x", "xx", "xxx", "."))


def _plain(text: Any) -> str:
    return " ".join(str(text or "").split())


def junk(text: str) -> bool:
    return not text or text.strip(" .!").lower() in NOISE


def noise(row: dict) -> bool:
    """A ticket with nothing in it. Both boxes have to be empty or mashed.

    Worth being careful about. Reading only `happened` made eleven of
    seventeen outstanding tickets look like test submissions, because the
    reporter typed "asdf" to clear the required field and put the actual
    report in `expected` — "6.5a offers three-tier based inputs" and the
    rest. Calling those noise turned a real backlog into a clean one, which
    is the most expensive kind of wrong a status report can be.
    """
    return all(junk(_plain(row.get(field))) for field in DESCRIBES)


def _one_line(row: dict, width: int = 78) -> str:
    """A ticket in a line: whichever box actually says something."""
    for field in DESCRIBES:
        text = _plain(row.get(field))
        if not junk(text):
            return text[:width]
    return "(nothing recorded)"


def main(argv: list[str]) -> int:
    everything = "--all" in argv
    full = "--full" in argv
    rows = bugs._read()

    counts = collections.Counter(r.get("status") or "(none)" for r in rows)
    outstanding = [r for r in rows if r.get("status") in (bugs.NEW, bugs.OPEN)]
    junk = [r for r in outstanding if noise(r)]
    if "--real" in argv or full:
        outstanding = [r for r in outstanding if not noise(r)]

    print(f"{len(rows)} tickets in {bugs.STORE.name}\n")
    for status in (bugs.NEW, bugs.OPEN, bugs.FIXED, bugs.WONT_FIX,
                   bugs.CLOSED):
        if counts.get(status):
            print(f"  {status:<9} {counts[status]:>3}   "
                  f"{bugs.STATUSES.get(status, '')}")
    for status, how_many in counts.items():
        if status not in bugs.STATUSES:
            print(f"  {status:<9} {how_many:>3}   (unrecognized status)")

    print(f"\nSTILL TO DO: {len(outstanding)}", end="")
    print(f"   (plus {len(junk)} test submissions)" if junk else "")
    if not outstanding:
        print("  nothing outstanding")

    for row in outstanding:
        ref = str(row.get("id") or "")[:12]
        where = str(row.get("view") or "-")[:16]
        if not full:
            print(f"  {ref:<12} {row.get('status'):<5} {where:<16} "
                  f"{_one_line(row)}")
            continue
        print(f"\n  {ref}   {row.get('status')}   {where}   "
              f"{str(row.get('at') or '')[:10]}")
        for field in ("happened", "expected", "seen_before"):
            text = " ".join(str(row.get(field) or "").split())
            if text:
                print(f"    {field:<12} {text}")
        for reply in row.get("replies") or []:
            said = " ".join(str(reply.get("text") or "").split())
            print(f"    reply        {said[:100]}")

    if everything:
        print("\nEVERY TICKET")
        for row in rows:
            ref = str(row.get("id") or row.get("ref") or "")[:12]
            print(f"  {ref:<12} {str(row.get('status')):<9} "
                  f"{_one_line(row)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
