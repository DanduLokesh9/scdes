"""Give the shared framework answers back to the agency that wrote them.

A one-time migration, for this deployment's history and no other.

Before agencies were separated there was a single
`corpus/config/framework_versions.json`. Both registered containers wrote into
it. Separating them leaves that file with the agency that owns the corpus —
which on this deployment is SCDES, and which did not write a word of it. Every
one of the thirteen answers is Brett's, entered from the IIA account on
2026-08-22, and they say so plainly: "Innovative Infrastructure Advising - IIA,
LLC", "For IIA, everything is available."

So the file moves to IIA, and SCDES is left with none — which is the true state
of SCDES's framework work, as opposed to the flattering one.

Deliberately not clever. The destination is named on the command line, the
source is a single named file, and it refuses to run twice. Nothing is deleted
until a copy exists somewhere else.

    python3 deploy/split_shared_framework.py                 # say what it would do
    python3 deploy/split_shared_framework.py --apply
"""

from __future__ import annotations

import json
import shutil
import sys
from collections import Counter
from pathlib import Path

SOURCE = Path("corpus/config/framework_versions.json")
#: The container code the answers belong to. From the tenancy record, not
#: guessed: brett@iiac.ai is a member of exactly this one.
DESTINATION = Path("data/agencies/iia.test/framework_versions.json")


def main() -> int:
    apply = "--apply" in sys.argv

    if not SOURCE.is_file():
        print(f"{SOURCE} is not there — nothing to move")
        return 0
    if DESTINATION.is_file():
        print(f"{DESTINATION} already exists — this has been run. Refusing to "
              f"overwrite an agency's framework.")
        return 1

    blob = json.loads(SOURCE.read_text(encoding="utf-8")) or {}
    working = blob.get("working", {})
    authors = Counter((row.get("by") or row.get("answered_by") or "(unrecorded)")
                      for row in working.values())

    print(f"source      : {SOURCE}")
    print(f"destination : {DESTINATION}")
    print(f"answers     : {len(working)}")
    print(f"acceptances : {len(blob.get('acceptances', []))}")
    print(f"versions    : {len(blob.get('versions', []))}")
    print("written by  :")
    for author, n in authors.most_common():
        print(f"                {n:>3}  {author}")

    if len(authors) > 1:
        print("\nMore than one author. This migration assumes the whole file "
              "belongs to one agency; with mixed authorship it would hand one "
              "person's answers to somebody else. Refusing — split it by hand.")
        return 1

    if not apply:
        print("\ndry run — pass --apply to move it")
        return 0

    backup = SOURCE.with_suffix(".json.preseparation.bak")
    shutil.copy2(SOURCE, backup)
    DESTINATION.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SOURCE, DESTINATION)
    # Only now, with two copies on disk, does the original go.
    SOURCE.unlink()

    print(f"\nmoved. IIA's answers are at {DESTINATION}")
    print(f"the file as it was is kept at {backup}")
    print("SCDES now has no builder answers, which is the true state of them.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
