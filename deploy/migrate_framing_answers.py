"""Offer back the framing answers already given to the register Module One
replaced.

Step 11 asks why the framework exists, what it implements, which federal
requirements apply and how far it reaches. The client answered every one of
those in August — to the register, which was mined from the very document he
later held ours up against. Those answers are still on disk under the old
keys, doing nothing.

Making somebody retype work they have already done is the kind of thing this
product exists to stop.

**Proposed, not applied.** It writes a `pending_framing` block into the
agency's own file rather than filling the answers in, so the interface can
show "we found these from August — keep them?" and they can accept or edit
each one. A framework that fills itself in without asking is the opposite of
what this module is for, and the mapping is a judgement in three places:

  * `state.strategy` held both the name and the principles in one sentence,
    which becomes 11.2's answer plus its detail;
  * `scope.acquisition` was a yes/no about keeping the reference scope, which
    becomes the full set of routes at 11.6;
  * `nascency.framing` was answered with something about who decides, which
    does not belong in Step 11 at all and is left where it is.

    python -m deploy.migrate_framing_answers <versions.json>
    python -m deploy.migrate_framing_answers <versions.json> --write
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

#: old register key -> the Step 11 question it belongs to.
#:
#: Only the ones that carry across cleanly. Anything needing a judgement the
#: person has to make is left for them to answer.
DIRECT = {
    "agency.why": "why.reason",
    "conflict.rule": "why.conflict",
    "scope.units": "why.units",
    "federal.requirements": "why.federal",
    "state.strategy": "why.state_strategy",
    "model.ambition": "why.ambition",
}

#: Free text that has to become a choice. The person confirms; nothing here
#: guesses on their behalf without showing them what it guessed.
AS_CHOICE = {
    "why.conflict": {
        "the more stringent standard controls": "stricter",
        "more stringent": "stricter",
        "stricter": "stricter",
    },
    "why.ambition": {
        "leave it out": "quiet",
        "no": "quiet",
        "yes": "say",
    },
}


def _read(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as why:
        raise SystemExit(f"could not read {path}: {why}")


def _plain(raw: object) -> str:
    value = raw.get("value") if isinstance(raw, dict) else raw
    return value.strip() if isinstance(value, str) else ""


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = Path(argv[0])
    write = "--write" in argv

    held = _read(path)
    working = held.get("working") or {}

    proposals: dict[str, dict] = {}
    for old, new in DIRECT.items():
        said = _plain(working.get(old))
        if not said:
            continue
        if new in working and _plain(working.get(new)):
            continue                       # they have already answered it

        proposal: dict[str, object] = {"from": old, "said": said}
        picks = AS_CHOICE.get(new)
        if picks:
            match = next((v for k, v in picks.items()
                          if k in said.lower()), "")
            if not match:
                proposal["needs_a_choice"] = True
            else:
                proposal["suggests"] = match
        proposals[new] = proposal

    if not proposals:
        print("Nothing to offer — either nothing was answered in August, or "
              "Step 11 has been answered already.")
        return 0

    print(f"{len(proposals)} answer(s) from the register, for Step 11:\n")
    for key, proposal in proposals.items():
        print(f"  {key}")
        print(f"    was {proposal['from']}: {str(proposal['said'])[:76]}")
        if proposal.get("suggests"):
            print(f"    reads as: {proposal['suggests']}")
        if proposal.get("needs_a_choice"):
            print("    needs them to pick — the old answer is free text")
        print()

    if not write:
        print("Read-only. Add --write to record them as proposals.")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    shutil.copy2(path, f"{path}.before-framing-{stamp}")
    held["pending_framing"] = {
        "found_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "note": "Answers given to the register Module One replaced. Offered "
                "back rather than filled in — theirs to accept or edit.",
        "proposals": proposals,
    }
    path.write_text(json.dumps(held, indent=2), encoding="utf-8")
    print(f"Recorded {len(proposals)} proposals. Nothing was answered on "
          f"their behalf.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
