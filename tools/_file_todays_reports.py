"""Put the two reports made in conversation onto the record, and close out.

Both came to me as a message rather than through the report form, so neither
existed as a ticket. Both are fixed and deployed. Filed anyway, because a
history with the work in it and not the reason for the work is a history that
answers "what changed" and not "why" — and the second question is the one
somebody asks eighteen months later.

Filed in his words, marked fixed against what was actually done, and then the
one remaining open ticket is closed at his direction.
"""

from __future__ import annotations

from app import bugs
from app.authz import Actor, Role

WHO = Actor("dev", "Dev", Role.OT, title="Development")

CONTEXT = {"view": "framework", "url": "", "browser": "",
           "screen": "reported in conversation"}

FILED = [
    {
        "happened": (
            "The polished download gives no warning that its wording came "
            "from an AI writing tool, or that the same answers will not "
            "produce the same wording twice."),
        "expected": (
            "we need to flash a disclaimer that the polished version uses an "
            "LLM which may adjust or alter their statements (trying to "
            "address the non-deterministic nature) and that additional "
            "scrutiny should be provided when reviewing the output"),
        "fixed": (
            "Done, in two places. Choosing Polished now shows a warning "
            "immediately under the question, and the document carries the "
            "same warning in bold as the first line of “How the wording "
            "was produced”.\n\n"
            "Both places say the thing you were getting at: it does not "
            "produce the same wording twice, asking again would give a "
            "differently worded document holding you to the same rules, and "
            "the checks are not a substitute for somebody reading it.\n\n"
            "Written as “AI writing tool” rather than “LLM” "
            "— your own rule is “never write model, write "
            "tool”, and LLM is on the same list. There is a test that "
            "fails if a banned word gets into that copy."),
    },
    {
        "happened": (
            "A misspelling typed into an answer came through unchanged in "
            "the polished document."),
        "expected": (
            "If they use the Polished version, it needs to catch things like "
            "spelling errors (I inentionally included a spelling error that "
            "translated over even after the polished version was selected)"),
        "fixed": (
            "Fixed, and the cause was not the writing tool.\n\n"
            "Reproduced first: the typo was in a clause carrying text you had "
            "typed, and those are never sent to the writing tool at all. "
            "Twenty-one clauses were skipped on that rule in the run that "
            "reproduced it, so the tool never saw the misspelling and no "
            "amount of instructing it would have helped.\n\n"
            "Choosing Polished now runs a separate, deterministic spelling "
            "pass over everything — the assembled clauses, the "
            "definitions, your own paragraphs and the table cells. It "
            "replaces only strings that are not words in any variety of "
            "English, so it cannot turn one word into a different one, and "
            "the document names the words it corrected. It needs no writing "
            "tool configured, so it works even where polishing cannot run.\n\n"
            "As Written is unchanged: it still carries your typing exactly "
            "as typed."),
    },
]

PARKED = "BUG-B898A895"
PARKED_SAID = (
    "Closed at your direction.\n\n"
    "Not a defect, and nothing here was broken — your note was that 6.1a "
    "is hard to answer well, and that pre-filled sets of actions tuned to "
    "each kind of agency would be worth more than a blank box. That is a "
    "feature, and a good one.\n\n"
    "Recording it here rather than leaving the ticket open, so the idea "
    "survives the ticket being closed. Your words: “This is tough... You "
    "did it correctly, but it's hard to think that highly and broadly and it "
    "could be a lot. This is where a pre-filled out set of actions tuned to "
    "each agency would be valuable.” Reopen or raise it fresh whenever "
    "you want it built."
)


def main() -> int:
    for entry in FILED:
        filed = bugs.report(expected=entry["expected"],
                            happened=entry["happened"],
                            context=CONTEXT, events=[],
                            name="Brett Butz", agency="iia.test")
        if not filed.get("ok"):
            print(f"FAILED to file: {filed.get('error')}")
            continue
        ref = filed["id"]
        moved = bugs.respond(ref, message=entry["fixed"],
                             status=bugs.FIXED, actor=WHO)
        print(f"{ref}  filed and marked fixed"
              if moved.get("ok") else f"{ref}  FAILED: {moved.get('error')}")

    held = bugs.ticket(PARKED)
    if held and held.get("status") in (bugs.NEW, bugs.OPEN):
        closed = bugs.respond(PARKED, message=PARKED_SAID,
                              status=bugs.CLOSED, actor=WHO)
        print(f"{PARKED}  closed"
              if closed.get("ok") else f"{PARKED}  FAILED: {closed.get('error')}")
    elif held:
        print(f"{PARKED}  already {held.get('status')}")

    after = bugs.summary()
    print(f"\nnow {after['open']} open of {after['total']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
