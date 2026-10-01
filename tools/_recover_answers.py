"""Recover an agency's answers from the audit log.

Why this exists: the browser harness answers real questions as a real
registered address, so it writes into a real tenant. On staging that tenant
turned out to be the client's own, and a walk both overwrote answers he had
given and blanked others on its way to a clean slate.

The audit log is the reason that is recoverable rather than merely regrettable.
It is append-only and hash-chained — "log should survive absolutely" — so every
answer ever recorded is still there, in order, with who gave it.

For each damaged key this finds the last value recorded by somebody who is not
the harness, and reports it. `--write` puts those values back into the working
answers and changes nothing else in the file; a backup is written alongside
first.

Usage:
    python3 _recover_answers.py <log.jsonl> <framework_versions.json> [--write]
"""

from __future__ import annotations

import json
import shutil
import sys
from typing import Any

#: Authors that are this project's own scaffolding rather than a person.
#: "Check" is the browser harness's registered name; the Office of Technology
#: actor is what its clean-slate loop authenticates as.
HARNESS_NAMES = {"Check", "Office of Technology", "Export check"}
HARNESS_ACTORS = {"sean.ot", "check.export"}


def _events(path: str) -> list[dict]:
    out = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def _key_of(event: dict) -> str:
    """The question this event answered, wherever the writer put it."""
    detail = event.get("detail") or {}
    for field in ("key", "question", "question_key", "setting", "field"):
        if detail.get(field):
            return str(detail[field])
    return ""


def _value_of(event: dict) -> Any:
    detail = event.get("detail") or {}
    for field in ("value", "to", "now", "answer"):
        if field in detail:
            return detail[field]
    return None


def _by(event: dict) -> str:
    return str((event.get("detail") or {}).get("actor_name")
               or event.get("actor") or "")


def _is_harness(event: dict) -> bool:
    return (_by(event) in HARNESS_NAMES
            or str(event.get("actor") or "") in HARNESS_ACTORS)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    log_path, held_path = argv[0], argv[1]
    write = "--write" in argv

    with open(held_path, encoding="utf-8") as handle:
        held = json.load(handle)
    working = held.get("working") or {}

    damaged = []
    for key, raw in sorted(working.items()):
        who = raw.get("by") if isinstance(raw, dict) else ""
        value = raw.get("value") if isinstance(raw, dict) else raw
        empty = value in (None, "", [], {})
        if empty or who in HARNESS_NAMES:
            damaged.append((key, who, "blank" if empty else "overwritten"))

    print(f"{len(damaged)} keys to look up\n")

    # Last human value per key, walking the log in order.
    human: dict[str, dict] = {}
    keyed = 0
    for event in _events(log_path):
        key = _key_of(event)
        if not key:
            continue
        keyed += 1
        if _is_harness(event):
            continue
        value = _value_of(event)
        if value in (None, "", [], {}):
            continue
        human[key] = {"value": value, "by": _by(event),
                      "at": event.get("at", ""), "seq": event.get("seq")}

    print(f"{keyed} events in the log name a question; "
          f"{len(human)} keys have a value from a person\n")

    recovered, lost = {}, []
    for key, who, how in damaged:
        found = human.get(key)
        if found:
            recovered[key] = found
            shown = str(found["value"])
            print(f"  {key:<26} {how:<12} -> {shown[:44]:<44} "
                  f"({found['by']}, {str(found['at'])[:10]})")
        else:
            lost.append((key, how))

    if lost:
        print(f"\n{len(lost)} not in the log under that key:")
        for key, how in lost:
            print(f"  {key:<26} {how}")

    if not write:
        print("\nRead-only. Add --write to put the recovered values back.")
        return 0

    if not recovered:
        print("\nNothing to restore.")
        return 0

    shutil.copy2(held_path, held_path + ".before-recovery")
    for key, found in recovered.items():
        working[key] = {"value": found["value"], "at": found["at"],
                        "by": found["by"]}
    held["working"] = working
    with open(held_path, "w", encoding="utf-8") as handle:
        json.dump(held, handle, indent=2)
    print(f"\nRestored {len(recovered)} answers. "
          f"Backup at {held_path}.before-recovery")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
