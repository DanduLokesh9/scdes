"""Move the tickets fixed on 16 September to "fixed", with what changed.

The code went out and the tracker was never told, so it went on reporting
seventeen open — honestly, because nothing had said otherwise. The client saw
"all done" from me and 17 open on his own screen, which is worse than a stale
tracker: it makes the tracker not worth reading.

"Fixed" means "waiting for the reporter to confirm", so this is the team's to
set and his to close. Each reply says what actually changed, because a ticket
that flips to fixed with no reason attached asks him to take it on trust and
gives him nothing to check.

    python -m tools.close_fixed_bugs            what it would do
    python -m tools.close_fixed_bugs --apply    do it

On the server:

    cd /opt/governingai && sudo .venv/bin/python -m tools.close_fixed_bugs --apply
"""

from __future__ import annotations

import sys

from app import bugs
from app.authz import Actor, Role

#: Dev, one of the three named admin addresses. Recorded as the actor because
#: the audit trail should say who moved a ticket, and "the system" is not a
#: person.
WHO = Actor("dev", "Dev", Role.OT, title="Development")

#: One line per ticket, saying what changed. Written to be read by the person
#: who raised it, not by whoever wrote the patch.
FIXED: dict[str, str] = {
    "BUG-9BC45FF0":
        "6.5a now uses the levels you chose at 5.2. On a two-level framework "
        "it offers “All tools” and “Elevated tools only” "
        "— the three-tier wording is gone, and the middle option is not "
        "offered at all when it would mean the same as the last one. 6.8a had "
        "the same fault and got the same fix.",
    "BUG-60400B65":
        "4.2 now follows 4.1. Answer “One accountable person” and it "
        "asks “Which role holds that responsibility?” in a single "
        "box instead of showing a grid of roles. The clause in the document "
        "follows too — it read “The roles holding that "
        "responsibility are…” in the plural for a single answer, "
        "which was the same fault reappearing in the output.",
    "BUG-19BFF585":
        "4.3 now follows 4.1 as well. Where one person holds it all there is "
        "nobody to disagree with, so it asks “Who decides when that "
        "person is unavailable?” — which is the gap that structure "
        "actually leaves.",
    "BUG-DA3E8A6B":
        "2.1 is now multi-select, so approved use and unapproved use can both "
        "be reported. A single choice made you pick which half of your own "
        "situation to tell us about.",
    "BUG-01326CF4":
        "11.5 is now your three parts: “Do you have organizational "
        "sub-units?”, then what you call them, then whether the framework "
        "applies to all of them — with a box for which are excluded if "
        "not. The last two are hidden if you answer no. All three appear "
        "immediately, without saving.",
    "BUG-85CEBE6F":
        "6.8a now offers “No”. Your framework states the decision "
        "either way, and 6.8b (who writes it) is no longer asked when nobody "
        "has to write one. Their program, their choice.",
    "BUG-8C3C816A":
        "7.6 now reads “No, we treat them as personal working "
        "notes…” and “Yes, we treat all of them as "
        "records”, so which way each option answers the question is "
        "plain.",
    "BUG-25753D8D":
        "7.4 is capitalized. The label on the control now reads “The "
        "accountable person”; the clause in the document keeps the "
        "lower-case form, because there it sits in the middle of a sentence.",
    "BUG-2AC1A6E5":
        "6.9 now takes your own line items. Nine good practices that could "
        "not be extended told an organization its tenth one did not count.",
    "BUG-08A219A6":
        "Checked, and no change was needed — “Whichever is "
        "stricter” is already the recommended answer at 11.4. Closing "
        "this one as verified rather than as fixed; say if you meant "
        "something else by it.",
    "BUG-1BEA5EC5":
        "6.1b now offers “Yes — decided on a case-by-case "
        "basis”, and asks who decides and against what test. A "
        "case-by-case permission with nobody named against it is not a rule, "
        "so the clause states both.",
    "BUG-B949552A":
        "—.3 now fills in from 9.10. If you said there that you would "
        "publish this framework, “Public website” comes "
        "pre-selected; if you said “Nothing for now”, "
        "“Internal only” does. Two options added: “Available "
        "on request only”, which is a real position and a different one "
        "from both of the others, and “Somewhere else” with a box.",
    "BUG-CFD7131F":
        "Fixed, and you were right that it happened in other places — "
        "there were thirteen. The screen reloads after certain answers so "
        "that questions which just changed appear straight away, and the list "
        "of which answers those are was written by hand and had fallen "
        "behind. It is now worked out from the questions themselves, so it "
        "cannot fall behind again. Two of the thirteen were questions added "
        "this week that would have shipped with the same fault.",
    "BUG-EC53B047":
        "This already exists — “Start over” on the Your "
        "content panel clears every answer, version and decision, and there "
        "is a snapshot facility beside it so you can take a copy first and "
        "put your work back afterward. Your audit trail is never touched. "
        "Closing as already available; tell me if it is not where you looked "
        "for it.",
    "BUG-9FF9442B":
        "Gone. The Start Here section now disappears as soon as any question "
        "is answered. Keyed on that rather than on reaching the save screen: "
        "you mentioned save-a-version because that is where you were, but "
        "the pitch is stale from the first answer onwards.",
}

#: Left alone, deliberately.
HELD: dict[str, str] = {
    "BUG-305E491D": "you were testing spellcheck on purpose — needs an "
                    "answer from me, not a code change",
    "BUG-B898A895": "parked by you: “Leave as is for now, I'll think "
                    "about it”",
}


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    held = {b["id"]: b for b in bugs._read()
            if b.get("status") in (bugs.NEW, bugs.OPEN)}

    missing = [ref for ref in FIXED if ref not in held]
    if missing:
        print("not open on this install, so not touched:")
        for ref in missing:
            print(f"  {ref}")
        print()

    print(f"{'moving' if apply else 'would move'} to fixed:")
    moved = 0
    for ref, message in FIXED.items():
        if ref not in held:
            continue
        print(f"  {ref}  {message[:66]}…")
        if apply:
            result = bugs.respond(ref, message=message, status=bugs.FIXED,
                                  actor=WHO)
            if not result.get("ok"):
                print(f"      FAILED: {result.get('error')}")
                continue
            moved += 1

    print(f"\nleft open on purpose:")
    for ref, why in HELD.items():
        mark = "" if ref in held else "  (not open here)"
        print(f"  {ref}  {why}{mark}")

    if apply:
        after = bugs.summary()
        print(f"\nmoved {moved}. now {after['open']} open of "
              f"{after['total']} tickets.")
    else:
        print("\nnothing changed. pass --apply to do it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
