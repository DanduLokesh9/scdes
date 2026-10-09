"""What happens when somebody *types* "unknown" into a text answer.

The client's question, BUG-4C598D50: "If I type Unknown right now in 9.4, does
the system flag that in the output or write to the output unknown?"

Worth answering with behavior rather than prose. Read-only.

Usage:  python -m tools._typed_unknown
"""

from __future__ import annotations

from app import module_one as m1, prose

TYPED = ["unknown", "Unknown", "UNKNOWN", "don't know", "Don't know",
         "not known", "TBD", "tbd", "n/a", "N/A", "?", "to be decided",
         "The Operations Lead"]


def main() -> int:
    question = m1.by_key("watch.who")
    print(f"9.4 — {question.prompt}\n")
    print(f"  {'typed':<22} {'state':<10} {'a named gap?':<14} in the document")
    for said in TYPED:
        answers = {question.key: said}
        described = m1.describe(question, answers)
        gaps = [g["number"] for g in m1.gaps(answers)]
        clauses = [c.text for s in prose.sections(answers) for c in s.clauses]
        shown = next((c for c in clauses if said.lower() in c.lower()),
                     "— not printed —")
        print(f"  {said!r:<22} {described['state']:<10} "
              f"{('yes ' + ','.join(gaps)) if gaps else 'no':<14} "
              f"{shown[:56]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
