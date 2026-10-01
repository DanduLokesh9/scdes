"""Quarantine lines the audit log cannot parse, and say what was lost.

A torn line was found in the log: one entry's bytes written into the middle of
another's, because `append` read the head of the hash chain and wrote the next
entry without holding a lock, and the server handles requests in threads. The
race is fixed in `app/audit.py`; this deals with the damage it already did.

**Quarantined, not deleted.** The client's rule is that the log survives
absolutely, and a corrupt line is still evidence — of the corruption, if
nothing else. Unparseable lines are moved to a sidecar file beside the log and
the count is reported, so the gap is visible rather than silently closed.

The hash chain will not verify across a removed line, and that is correct: it
should say that something is missing, because something is.

Usage:
    python -m tools.repair_audit_log <log.jsonl>
    python -m tools.repair_audit_log <log.jsonl> --write
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = Path(argv[0])
    write = "--write" in argv
    if not path.is_file():
        print(f"not found: {path}")
        return 1

    good: list[str] = []
    torn: list[tuple[int, str]] = []
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                json.loads(stripped)
            except ValueError:
                torn.append((number, stripped))
                continue
            good.append(stripped)

    print(f"{len(good)} entries parse")
    print(f"{len(torn)} do not\n")
    for number, line in torn[:6]:
        print(f"  line {number}: {line[:96]}")

    if not torn:
        print("\nNothing to repair.")
        return 0
    if not write:
        print("\nRead-only. Add --write to quarantine them.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    sidecar = path.with_suffix(f".torn-{stamp}.txt")
    sidecar.write_text(
        "# Lines the audit log could not parse, moved aside rather than\n"
        "# deleted. Cause: concurrent appends interleaving before the write\n"
        "# was serialized. See app/audit.py.\n\n"
        + "\n".join(f"line {n}: {line}" for n, line in torn),
        encoding="utf-8")
    path.write_text("\n".join(good) + "\n", encoding="utf-8")

    print(f"\nQuarantined {len(torn)} line(s) to {sidecar.name}")
    print("The chain will not verify across the gap, which is the truthful "
          "result — something is missing, and the log now says so.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
