"""Does a misspelling survive the Polished download? Reproduce it.

The client: "If they use the Polished version, it needs to catch things like
spelling errors (I inentionally included a spelling error that translated
over even after the polished version was selected)."

Before changing anything, find out *where* it survives — a typo in a clause
this application assembled and a typo in a sentence the organization typed
are two different faults with two different fixes, and only one of them is
about the writing tool.

    python -m tools._typo_through_polish
"""

from __future__ import annotations

from app import env, module_one as m1, polish, prose, versions
from app.authz import Actor, Role

env.load()

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")

#: One in a free-text answer, one in a choice's follow-up box, and one in the
#: section's own paragraph. All three are text somebody typed.
TYPOS = {
    "who.tiebreak": "teh District Manager",
    "why.reason": ("We are doing this to protect teh public and to make sure "
                   "our use of these tools is responsable and open."),
}


def main() -> int:
    for key, value in TYPOS.items():
        versions.answer(key, value, WHO)
    versions.answer(m1.own_words_key(m1.by_number("04")),
                    "We deliberatly kept teh group small.", WHO)
    versions.answer("done.language", m1.POLISHED, WHO)

    answers = versions.working()
    built = prose.sections(answers)

    print("before polishing")
    for section in built:
        for clause in section.clauses:
            if "teh " in clause.text or "responsable" in clause.text:
                print(f"  clause  {section.number}: {clause.text[:88]}")
        if section.own_words and ("teh " in section.own_words
                                  or "deliberatly" in section.own_words):
            print(f"  theirs  {section.number}: {section.own_words[:88]}")

    ok, why = polish.available()
    print(f"\npolish available: {ok} {why}")
    if not ok:
        return 2

    outcome = polish.sections(built, answers)
    print(f"{outcome.summary()}\n")

    print("after polishing")
    left = 0
    for section in built:
        for clause in section.clauses:
            if "teh " in clause.text or "responsable" in clause.text:
                print(f"  STILL WRONG  clause {section.number}: "
                      f"{clause.text[:80]}")
                left += 1
        if section.own_words and ("teh " in section.own_words
                                  or "deliberatly" in section.own_words):
            print(f"  STILL WRONG  their words {section.number}: "
                  f"{section.own_words[:80]}")
            left += 1
    print(f"\n{left} misspelling(s) survived the polished pass"
          if left else "\nnothing survived — already fixed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
