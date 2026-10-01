"""The same answers, written both ways.

The client, having compared our output with a real adopted framework: "Let
them choose. If their governance inputs are 'modest'... recommend
'Simplified'. Bigger agencies... recommend 'Formal'. But in either instance,
the incorporated questions AND the responses get integrated and then go into
the text."

Both registers say the same thing and bind the organization to the same
rules. Whether that is true is a judgment about prose, so this prints them
side by side and lets a person read them.

Usage:  python -m tools._compare_registers
"""

from __future__ import annotations

from app import module_one as m1, prose

#: A large agency, so the recommendation is Formal and the difference shows.
ANSWERS: dict[str, object] = {
    "org.kind": "state", "org.size": "2000+", "who.shape": "council",
    "org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS},
    "org.delegated": "yes", "org.open_records": "yes",
    "org.unusual": "No",

    "scope.covered": ["generative", "predictive", "recognition"],
    "scope.excluded": ["formulas", "spellcheck"],
    "scope.arbiter": "The Chief Technology Officer decides, subject to "
                     "Agency Director review",
    "scope.review": "standalone",

    "who.tiebreak": "The Agency Director",
    "who.consulted": ["exec", "it", "legal", "program"],
    "who.without": ["free"],
    "risk.levels": "four", "risk.worst": "yes",
    "floor.ai_finalises": "none",
    "floor.list_owner": "The Chief Data Officer",
    "floor.access_docs": "yes",
    "proc.terms": ["disclose", "notice", "audit", "return"],
}


def show(register: str) -> None:
    answers = {**ANSWERS, "done.register": register}
    flowing = register == m1.FORMAL
    print("=" * 74)
    print(f"{register.upper()}")
    print("=" * 74)
    for section in prose.sections(answers):
        if section.empty or section.number not in ("1", "2", "3"):
            continue
        print(f"\n{section.number}. {section.title}")
        print(f"   {section.purpose}\n")
        if flowing and section.number in prose.FLOWING:
            body = " ".join(c.text for c in section.clauses)
            print("   " + body.replace(". ", ".\n   "))
        else:
            for i, clause in enumerate(section.clauses, start=1):
                print(f"   {section.number}.{i}  {clause.text}")
    print()


def main() -> int:
    found = m1.register_for(ANSWERS)
    print(f"recommended for this organization: {found['suggested']}")
    for reason in found["because"]:
        print(f"    because {reason}")
    print()
    show(m1.SIMPLIFIED)
    show(m1.FORMAL)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
