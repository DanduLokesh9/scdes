"""Walk Module One as three different organizations and see what each is asked.

The module's whole claim is that it adapts — that a twelve-person water district
and a two-thousand-person state agency both finish with something real, and that
neither is asked to route something to an office it does not have. That is a
claim about behavior across a whole journey, which a unit test asserts one
condition at a time and this shows end to end.

Usage:  python -m tools.check_module_one
"""

from __future__ import annotations

from app import module_one as m1

#: Three organisations from opposite ends of the client's own registry.
CASES = {
    "a 20-person water district": {
        "org.kind": "district",
        "org.size": "u25",
        "org.adopter": "board",
        "org.functions": {"legal": "contracted", "it": "part",
                          "security": "none", "purchasing": "part",
                          "records": "part", "finance": "part",
                          "hr": "none", "comms": "none"},
        "org.delegated": "no",
        "org.open_records": "yes",
    },
    "a county running a delegated program": {
        "org.kind": "county",
        "org.size": "100-500",
        "org.adopter": "board",
        "org.functions": {"legal": "dedicated", "it": "dedicated",
                          "security": "part", "purchasing": "dedicated",
                          "records": "dedicated", "finance": "dedicated",
                          "hr": "dedicated", "comms": "part"},
        "org.delegated": "yes",
        "org.open_records": "yes",
    },
    "a large state agency": {
        "org.kind": "state",
        "org.size": "2000+",
        "org.adopter": "cabinet",
        "org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS},
        "org.delegated": "yes",
        "org.open_records": "yes",
    },
}


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"    {'ok  ' if ok else 'FAIL'}  {label:<44} {detail}")
        if not ok:
            failures.append(label)

    for name, answers in CASES.items():
        print(f"\n{name}")
        state = m1.summary(answers)
        print(f"        {state['totals']['questions']} questions asked, "
              f"{state['totals']['answered']} answered so far")

        shape = m1.by_key("who.shape")
        rec = m1.recommended_for(shape, answers)
        label = next(o.label for o in shape.options if o.value == rec)
        print(f"        recommended shape: {label}")
        # The unknown is one of the options now — his "Not sure" where he
        # wrote one, a generic where he did not — so it is excluded from the
        # count of governance shapes rather than inflating it.
        shapes = [o for o in m1.options_for(shape, answers)
                  if o.value != m1.UNKNOWN]
        check("all four shapes still offered", len(shapes) == 4,
              "never disabled, whatever the size")

        consulted = m1.by_key("who.consulted")
        offered = [o.value for o in m1.options_for(consulted, answers)]
        absent = [f.value for f in m1.FUNCTIONS
                  if answers["org.functions"].get(f.value) == "none"]
        check("no office it does not have is offered",
              not set(absent) & set(offered),
              f"withheld: {', '.join(absent) if absent else 'none to withhold'}")
        check("the using program is always offered", "program" in offered)

        missing = m1.by_key("who.missing")
        rows = [r.value for r in m1.rows_for(missing, answers)]
        check("the follow-up lists exactly the missing offices",
              sorted(rows) == sorted(absent),
              f"{len(rows)} row(s)")
        # And hidden altogether when nothing is missing. "4.4b — if it is not
        # relevant based on previous answers, hide the component. It's sitting
        # there with nothing for me to do and is confusing."
        check("and is only asked when something is missing",
              m1.visible(missing, answers) is bool(absent),
              "shown" if rows else "hidden — nothing to ask about")

        signs = m1.by_key("who.signs")
        check("who signs is pre-filled from 1.3",
              m1.recommended_for(signs, answers) == answers["org.adopter"],
              answers["org.adopter"])

    print("\nthe honest gaps")
    partial = {**CASES["a 20-person water district"],
               "org.size": m1.UNKNOWN,
               "scope.arbiter": m1.UNKNOWN}
    found = m1.gaps(partial)
    check("an unknown answer becomes a named gap", len(found) == 2,
          ", ".join(g["number"] for g in found))
    check("each one needs an owner", all(g["needs_owner"] for g in found))
    check("and none of them is a blank", all(g["question"] for g in found))

    print("\nnothing quotes anybody else")
    blob = repr(m1.summary(CASES["a large state agency"]))
    for word in ("SCDES", "South Carolina", "Appendix", "Operations Manual"):
        check(f"no mention of {word}", word not in blob)

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — the module adapts, and never asks for an office that "
          "isn't there")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

