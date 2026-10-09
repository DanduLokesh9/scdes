"""Did the federal registry land, and does it change who may register?

The client supplied 472 federal entities and a domain allowlist "to go along
with your SC state registry". Two things could go wrong quietly: the federal
list loads but nobody can reach it, or the allowlist loads but the suffix rule
still turns away the bodies it was supposed to admit.

Usage:  python tools/check_federal.py
"""

from __future__ import annotations

import sys

from app import onboarding, states

# Bodies in the client's own registry that the suffix rule alone refuses.
LISTED_BUT_NOT_DOT_GOV = [
    ("clerk@scalc.net", "SC Administrative Law Court"),
    ("staff@scdmvonline.com", "SC DMV"),
    ("someone@amtrak.com", "Amtrak"),
    ("staff@santeecooper.com", "Santee Cooper"),
]

MUST_STILL_BE_REFUSED = [
    ("me@gmail.com", "a personal mailbox"),
    ("sales@random-startup.com", "an unrelated company"),
    ("me@notreally-amtrak.com", "a lookalike of a listed domain"),
]


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<46} {detail}")
        if not ok:
            failures.append(label)

    print("the federal registry")
    fed = states.agencies_for(states.FEDERAL_CODE)
    check("agencies offered", len(fed) > 300, f"{len(fed)}")
    check("every one has a domain", all(a["domain"] for a in fed))
    check("none claims a derived convention",
          all(a["convention"] == "any" for a in fed),
          "the federal sheet has no staff addresses to derive one from")
    check("no defunct agency is offered",
          not any("defunct" in a.get("category", "").lower() for a in fed))
    epa = [a for a in fed if a["abbrev"] == "EPA"]
    check("a known agency is reachable", bool(epa),
          epa[0]["name"][:44] if epa else "EPA missing")

    print("\nno names were imported")
    import json
    from pathlib import Path
    raw = json.loads((Path("app/data/federal_agencies.json"))
                     .read_text(encoding="utf-8"))
    fields = set()
    for a in raw["agencies"]:
        fields |= set(a)
    check("no head / head_title field", not ({"head", "head_title"} & fields),
          "the client's rule: do not pre-load any user names")

    print("\nthe allowlist admits the bodies the suffix rule refuses")
    for address, who in LISTED_BUT_NOT_DOT_GOV:
        v = onboarding.check_email(address)
        check(who, v.ok, f"{address}  evidence={v.evidence or '-'}")

    print("\nand still refuses everything else")
    for address, what in MUST_STILL_BE_REFUSED:
        v = onboarding.check_email(address)
        check(what, not v.ok, f"{address}  {v.reason[:40]}")

    print("\n.gov is unaffected")
    v = onboarding.check_email("jane@epa.gov")
    check("a .gov address still passes as restricted",
          v.ok and v.evidence == "restricted", f"evidence={v.evidence}")

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — the federal registry is reachable and the allowlist is narrow")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
