"""Polish a handful of real clauses against the live API, and show both.

The guardrail tests use mocks, which prove the checks work and say nothing
about whether the polishing is any good. This runs the real thing on real
assembled clauses and prints the before and after side by side, plus what
the pass cost, so the quality and the price are both observable rather than
asserted.

    python -m tools._try_polish [how_many]

Spends money. A handful of clauses, not the whole document.
"""

from __future__ import annotations

import sys
import time

from app import env, polish

env.load()


#: Real assembled clauses, taken from what the module actually produces for
#: the sample answers in tools/check_document.py. Deliberately includes the
#: awkward ones — a determination "made by" somebody, a list joined with
#: semicolons, a sentence carrying a date and a modal.
CLAUSES = [
    "Responsibility for decisions under this framework is vested in a group "
    "this organization already has, which has taken AI onto its agenda.",

    "No artificial intelligence system may be approved for use without prior "
    "consultation with legal counsel, information technology, and the "
    "program that will answer for the outcome.",

    "It does not apply to spreadsheet formulas and calculations; spellcheck "
    "and grammar tools. Nothing in this exclusion relieves any system of "
    "obligations arising under other policy.",

    "The following may proceed without that approval: free tools and trials; "
    "short pilots.",

    "This organization is subject to open records and open meetings law. "
    "Records created with the assistance of artificial intelligence are "
    "public records on the same terms as any other record.",

    "A problem of the most serious kind must be reported within 3 days to "
    "the Operations Lead, who shall stop the tool until it is resolved.",
]


def main(argv: list[str]) -> int:
    ok, why = polish.available()
    if not ok:
        print(f"Cannot run: {why}")
        return 2

    from app.provider import AnthropicProvider
    provider = AnthropicProvider()
    print(f"provider : {provider.name}:{provider.model}\n")

    how_many = int(argv[0]) if argv else len(CLAUSES)
    changed = refused = 0
    started = time.time()

    for i, clause in enumerate(CLAUSES[:how_many], 1):
        text, why_not, attempted = polish.one(provider, clause)
        print(f"--- {i}")
        print(f"  before : {clause}")
        if text == clause:
            print(f"  after  : (unchanged) {why_not or 'already fine'}")
            if why_not and why_not != "unchanged":
                refused += 1
                if attempted:
                    print(f"  refused: {attempted}")
        else:
            print(f"  after  : {text}")
            changed += 1
        print()

    took = time.time() - started
    print(f"{changed} reworded, {refused} rejected by the checks, "
          f"{how_many - changed - refused} left as written")
    print(f"{took:.1f}s for {how_many} clauses "
          f"({took / max(1, how_many):.1f}s each)")
    print(f"\nA full framework is roughly 90 clauses, so about "
          f"{took / max(1, how_many) * 90 / 60:.1f} minutes at this rate "
          f"if run one at a time.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
