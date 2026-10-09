"""Which register each kind of organization is steered toward, and why.

The client: "If their governance inputs are 'modest' — e.g. 2 risk categories,
only one or two people, no council — the default will be KISS, recommend
'Simplified'. Bigger agencies where they have dedicated staff for legal,
procurement, IT, multiple people and inputs, recommend 'Formal'."

Read-only. Prints the recommendation and the reasons for it, so the rule can
be argued with rather than trusted.

Usage:  python -m tools._register_check
"""

from __future__ import annotations

from app import module_one as m1

CASES = {
    "a 20-person water district": {
        "org.size": "u25", "who.shape": "one", "risk.levels": "two",
        "org.functions": {"legal": "contracted", "it": "part",
                          "security": "none", "hr": "none"},
        "org.delegated": "no", "org.open_records": "no",
    },
    "a mid-size city": {
        "org.size": "100-500", "who.shape": "group", "risk.levels": "three",
        "org.functions": {"legal": "dedicated", "it": "dedicated",
                          "purchasing": "part", "finance": "dedicated"},
        "org.delegated": "no", "org.open_records": "yes",
    },
    "a large state agency": {
        "org.size": "2000+", "who.shape": "council", "risk.levels": "four",
        "org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS},
        "org.delegated": "yes", "org.open_records": "yes",
    },
    "nothing answered yet": {},
}


def main() -> int:
    for name, answers in CASES.items():
        found = m1.register_for(answers)
        print(f"{name}")
        print(f"  suggested : {found['suggested']}")
        for reason in found["because"]:
            print(f"      because {reason}")
        if not found["because"]:
            print("      (nothing to go on yet — the simpler default)")
        print()

    # Their choice always wins, which is the rule everywhere in this module.
    small = CASES["a 20-person water district"]
    print("a small district that asks for Formal anyway:",
          m1.register_of({**small, "done.register": m1.FORMAL}))
    big = CASES["a large state agency"]
    print("a large agency that asks for Simplified:",
          m1.register_of({**big, "done.register": m1.SIMPLIFIED}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
