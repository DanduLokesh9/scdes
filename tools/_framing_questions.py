"""The register's framing questions, and the answers he already gave them.

Module One replaced the mined register and kept the operational questions
while dropping the ones that produce a Purpose and a Scope — which is why our
output reads as a rule-list and a real adopted framework does not.

Those questions were mined from the very document he compared us against, so
they are the right shape. This prints them with his own August answers beside
them, so Step 0 can be written from the source rather than from memory, and so
the migration can be checked rather than assumed.

Read-only.

Usage:  python -m tools._framing_questions [path to his versions.json]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from app import discretion

#: The register keys that carry the framing — everything a reader meets before
#: the rules start. Ordered as they appear in a finished framework.
FRAMING = [
    "agency.identity", "agency.why", "nascency.framing", "model.ambition",
    "state.strategy", "federal.requirements", "conflict.rule",
    "adoption.instrument", "scope.units", "scope.acquisition",
    "scope.exclusions", "definitions.autonomous",
]


def _his_answers(path: str | None) -> dict[str, str]:
    if not path:
        return {}
    try:
        held = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out = {}
    for key, raw in (held.get("working") or {}).items():
        value = raw.get("value") if isinstance(raw, dict) else raw
        who = raw.get("by", "") if isinstance(raw, dict) else ""
        if isinstance(value, str) and value.strip():
            out[key] = f"{value.strip()}   —{who}"
    return out


def main(argv: list[str]) -> int:
    mine = {r.key: r for s in discretion.SECTIONS for r in s.questions}
    his = _his_answers(argv[0] if argv else None)

    for key in FRAMING:
        row = mine.get(key)
        if row is None:
            print(f"{key}  — not in the register\n")
            continue
        print(f"### {key}")
        print(f"    asks   : {row.question}")
        helped = getattr(row, "help", "") or getattr(row, "why", "")
        if helped:
            print(f"    nuance : {str(helped)[:150]}")
        said = his.get(key)
        print(f"    he said: {said if said else '— nothing recorded —'}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
