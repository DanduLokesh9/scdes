"""Move BUG-305E491D to fixed, with what was actually done about it.

He raised it as a test — "I intentionally mis-spelled 'the' to 'teh' to see
if the system notices and correct" — and it turned into two pieces of work:
the suggestion under a text field, and then the correction inside the
Polished download when the first one turned out not to reach text that had
already been typed.
"""

from __future__ import annotations

from app import bugs
from app.authz import Actor, Role

WHO = Actor("dev", "Dev", Role.OT, title="Development")

REF = "BUG-305E491D"
SAID = (
    "Fixed, in two places.\n\n"
    "Typing a misspelling into any free-text answer now shows a line under "
    "the box — “Possible typo: ‘teh’ → "
    "‘the’. Nothing has been changed.” — with a button to "
    "apply it and one to leave it as typed. It suggests rather than "
    "rewriting on its own, because your answers go into the adopted document "
    "word for word and this framework's own first rule is that no tool "
    "finalizes anything without a person.\n\n"
    "Separately, choosing Polished now corrects misspellings outright, "
    "including in sentences you typed. That was the second half of your "
    "report — the typo survived the polished version — and the "
    "cause was that clauses carrying your own words are never sent to the "
    "writing tool, so it never saw it. The correction is deterministic, from "
    "a list of about two hundred strings that are not words in any variety "
    "of English, so it cannot turn one word into another. The document names "
    "the words it corrected.\n\n"
    "British spellings are deliberately left alone: organization, license, "
    "program and judgment are correctly spelled words, and flagging them "
    "would be us having a view about your prose."
)


def main() -> int:
    ticket = bugs.ticket(REF)
    if not ticket:
        print(f"no ticket {REF} on this install")
        return 1
    if ticket.get("status") not in (bugs.NEW, bugs.OPEN):
        print(f"{REF} is already {ticket.get('status')}")
        return 0
    result = bugs.respond(REF, message=SAID, status=bugs.FIXED, actor=WHO)
    print("moved" if result.get("ok") else f"FAILED: {result.get('error')}")
    after = bugs.summary()
    print(f"now {after['open']} open of {after['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
