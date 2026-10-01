"""What Purpose and Scope now read like, from his own August answers.

The client compared our output with a real adopted framework and said "the
questions we are asking should provide the inputs needed to create a draft
that matches this". Step 11 asks for those inputs. This feeds it the answers
he actually gave the register in August — the same content, since the register
was mined from that very document — and prints the two sections.

Read-only.

Usage:  python -m tools._purpose_preview [simplified|formal]
"""

from __future__ import annotations

import sys

from app import module_one as m1, prose

#: His own words, moved onto the new keys. Nothing invented.
HIS = {
    "why.reason": "To support the ethical, responsible, and efficient "
                  "deployment of this technology for our employees and the "
                  "citizens we serve.",
    "why.ambition": "say",
    "why.state_strategy": {
        "value": "yes",
        "detail": "the South Carolina State Agencies AI Strategy, published "
                  "in June 2024 by the South Carolina Department of "
                  "Administration, whose guiding principles are safely and "
                  "securely, fairly and objectively, ethically, "
                  "transparently, and beneficially",
    },
    "why.federal": ["omb", "nist", "ada"],
    "why.conflict": "stricter",
    "why.manual": {"value": "yes", "owner": "the AI Governance Council"},
    "why.units": "all programs, bureaus, and offices",
    "why.routes": ["built", "bought", "embedded", "upgrade", "cooperative",
                   "contractor"],

    # And enough of the rest for Scope to have something to say.
    "scope.covered": ["generative", "predictive", "recognition"],
    "scope.excluded": ["formulas", "spellcheck"],
    "scope.arbiter": "The Chief Technology Officer decides, subject to "
                     "Agency Director review",
    "scope.review": "standalone",
    "org.delegated": "yes",
    "org.open_records": "yes",
    "org.unusual": "No",

    # A large agency, so Formal is what gets recommended.
    "org.size": "2000+", "who.shape": "council",
    "org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS},
}


def main(argv: list[str]) -> int:
    register = argv[0] if argv else m1.register_of(HIS)
    answers = {**HIS, "done.register": register}
    flowing = register == m1.FORMAL

    print(f"register: {register}\n")
    for section in prose.sections(answers):
        if section.number not in ("1", "2"):
            continue
        print("=" * 74)
        print(f"{section.number}. {section.title}")
        print(f"   {section.purpose}")
        print("=" * 74)
        if section.empty:
            print("   (nothing decided here yet)\n")
            continue
        if flowing and section.number in prose.FLOWING:
            body = " ".join(c.text for c in section.clauses)
            line = ""
            for word in body.split():
                if len(line) + len(word) > 72:
                    print("   " + line)
                    line = ""
                line = (line + " " + word).strip()
            if line:
                print("   " + line)
        else:
            for i, clause in enumerate(section.clauses, start=1):
                print(f"   {section.number}.{i}  {clause.text}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
