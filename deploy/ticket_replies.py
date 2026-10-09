"""Answer the reports in the queue, one reply per ticket.

Thirty-two tickets were filed and thirty-one had no reply, so the queue looked
untouched while the work was live. A reporter who cannot tell what landed has
no way to test it, and no reason to keep filing.

Every reply says what changed, in the reporter's own terms rather than in
file names, and where to look. Nothing is marked `fixed` that was not
actually fixed and verified; the two that are genuinely unfinished say so.

Run once. Re-running is safe — it skips any ticket that already has a reply,
so it cannot double-post.

    python -m deploy.ticket_replies                 # show what it would post
    python -m deploy.ticket_replies --post          # post it
    python -m deploy.ticket_replies --post --base https://app.staging...
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://app.staging.governingai.us"
#: Replies are posted as a real admin, through the real endpoint, with the
#: same identity check every other admin action goes through.
ADMIN = "lokesh@iiac.ai"
ADMIN_AGENCY = "iia.test"

FIXED = "fixed"
WONT = "wont_fix"
OPEN = "open"
CLOSED = "closed"

#: id -> (status, reply). Ordered as he filed them.
REPLIES: dict[str, tuple[str, str]] = {

    # ---------------------------------------------------- 24-25 August
    "BUG-B6552A3E": (FIXED,
        "Sign Out works now. The cause was that it asked for confirmation "
        "through a browser dialog, and Chrome permanently disables those "
        "after anyone ticks “prevent additional dialogs” — so the click did "
        "nothing, silently, forever. It uses an in-app confirmation instead.\n\n"
        "Also done: “What gets sent with this” is gone from the report form."),

    "BUG-8B555A49": (FIXED,
        "The reference documents are no longer visible to any account but "
        "the one they belong to. While fixing this we swept every read "
        "endpoint as a non-owner and found nine more doing the same thing — "
        "the agency profile, the home screen's incident panel, and the "
        "registry, vision, budget, oversight and council screens. All of "
        "them now say plainly that nothing there is yours yet, rather than "
        "showing somebody else's."),

    "BUG-AB29F592": (FIXED,
        "“Section 4 + Appendix H” is gone. Those came from the register the "
        "build used before Module One, which quoted the reference agency "
        "under every question. Module One replaced it and quotes nobody, so "
        "there is no cross-reference to explain."),

    # ---------------------------------------------------- 26-28 August
    "BUG-A5033FAE": (FIXED,
        "Agency profile no longer shows SCDES. It now explains that the "
        "screen fills in from your own adopted documents, with a link to "
        "your framework.\n\n"
        "Worth saying that your screenshot caught a second half we had "
        "missed: the endpoint had been fixed to withhold the data, but the "
        "page still expected it, so it would have rendered a table of "
        "dashes. That is fixed too."),

    "BUG-C756E02A": (CLOSED,
        "Thank you — noted, and no change needed."),

    "BUG-5E136A61": (CLOSED,
        "Closing this one as a test ticket. Nothing needed."),

    "BUG-ED813720": (FIXED,
        "3.1 and 3.2 now have “Add a use of your own” and “Add something "
        "else that should not count”. What you type appears in the list as a "
        "chosen option, can be un-ticked like any other, and goes into the "
        "framework in your words.\n\n"
        "The same control is now on 5.1, 6.2b, 6.6 and 7.1, which were the "
        "other places you asked for it."),

    "BUG-94687A56": (FIXED,
        "There is now a “← Back to 04 — Who decides” button to the left of "
        "Continue, on every step, naming the step it returns to."),

    "BUG-527E2217": (FIXED,
        "Fixed, and it was a real bug rather than a quirk. The code scrolled "
        "the window to the top — but this page does not scroll, the panel "
        "inside it does. So the call did nothing and your position carried "
        "over from the bottom of step 03. On the much longer step 04 that "
        "same offset lands at 4.4, which is exactly where you saw it stop. "
        "It now resets the panel that actually scrolls."),

    "BUG-FAA09660": (FIXED,
        "“Administration or executive leadership” is now the first option at "
        "1.4 and 4.4, in your order: Administration, Information Technology, "
        "Legal Counsel.\n\n"
        "The cybersecurity question is in as 1.4b — “Is your cybersecurity "
        "team a part of the IT team?” — and it only appears if you have an "
        "IT team to be part of. Answer yes and cybersecurity stops being "
        "asked about separately anywhere in the module, including in the "
        "“offices you don't have” follow-up."),

    "BUG-C0258767": (FIXED,
        "4.4b now disappears entirely when nothing is missing, rather than "
        "sitting there with nothing to do."),

    "BUG-E34DA12D": (CLOSED,
        "Noted, no change made. 4.7's answers are flagged in our own notes "
        "as a signal for the subscription conversation."),

    "BUG-21DBEC69": (FIXED,
        "5.1's number now sits on the same line as the question. The "
        "statements have a wider column and are left-aligned by rule rather "
        "than by accident — they were inheriting a centring rule meant for "
        "the radio columns.\n\n"
        "Flagged for you to reconsider the phrasing whenever you want to; "
        "the wording is untouched."),

    "BUG-9B298881": (FIXED,
        "5.1 now has “Add a factor of your own”. What you add arrives as a "
        "row with the same three weights as every other factor, and nothing "
        "is chosen for you."),

    "BUG-1A0753E1": (FIXED,
        "5.3 is now greyed out and genuinely not editable until 5.2 is "
        "answered, with a line saying to answer 5.2 first and why. It is "
        "disabled rather than only dimmed, so a keyboard user cannot tab "
        "into it either.\n\n"
        "Thank you for the note on 5.2-5.3 — glad it reads well."),

    "BUG-15744B13": (FIXED,
        "Both parts done.\n\n"
        "The seeding was wrong: it offered “the council” to a unit that has "
        "no council. The lowest level now goes to whoever holds approval "
        "authority — typically IT — and “with legal and IT asked first” only "
        "appears if 1.4 said those offices exist. Your point about "
        "self-approval was the reason: it used to suggest the person who "
        "will use the tool, which lets low-level staff approve themselves.\n\n"
        "American spelling: “Programme” is gone. We found “organisation” in "
        "fourteen places in the generated document as well, all corrected, "
        "and there is now a check that fails the build if British spelling "
        "reappears anywhere a user reads."),

    "BUG-CFB51494": (FIXED,
        "The averaging note at 5.4 — and every other explanatory line in the "
        "module — now sits directly below the question and above the "
        "answers. You were right that it is a context point; underneath the "
        "options it was a footnote to a decision already made."),

    "BUG-29BBB23A": (FIXED,
        "6.2b now has “Add something else to record”."),

    "BUG-C1F3A8EB": (FIXED,
        "6.2d is multi-select. The “must be registered within ___ days” "
        "blank works alongside the other answers rather than replacing "
        "them — more than one of those is usually true at once."),

    "BUG-58AC00FF": (FIXED,
        "6.6 now has “Add a term of your own”."),

    # ---------------------------------------------------- 2 September
    "BUG-F4DAE83E": (FIXED,
        "You were right, and it was worse than a display problem — the "
        "export left those answers out of the framework entirely.\n\n"
        "Built exactly as you described it: leaving a step records what is on "
        "it. Committed on the way out rather than the way in, so opening "
        "step 05 does not silently answer five questions nobody has read, "
        "but clicking Continue past them is you saying “yes, that”. A toast "
        "confirms how many were recorded.\n\n"
        "This also fixed 10.3, which was the same cause."),

    "BUG-3F2B4446": (FIXED,
        "Fixed by the same change as BUG-F4DAE83E. 10.3's three severity "
        "definitions arrive pre-written, and nothing was stored unless you "
        "edited them — so a level you agreed with registered as blank. "
        "Continuing past the step now records them."),

    "BUG-D48EE440": (FIXED,
        "6.5b now shows your line when “Never” is chosen: “An untested "
        "fallback is a document, not a plan. Your answer stands — it will "
        "appear in your framework as written, and on the floor checklist as "
        "a place you chose to be less strict.”\n\n"
        "The cause was that these lines were hardcoded in the interface, "
        "which knew about 4.1's consequence and no others. They now travel "
        "with the questions, so the next one cannot go missing the same way."),

    "BUG-4C598D50": (FIXED,
        "Good question, and the honest answer was: inconsistently, and "
        "badly.\n\n"
        "Lower-case “unknown” happened to be caught, because it matches the "
        "value the module uses internally. “Unknown” with a capital, “TBD”, "
        "“n/a” and “don't know” all went into the framework as though they "
        "were roles — producing sentences like “That review is carried out "
        "by TBD” as adopted policy.\n\n"
        "Any of those is now treated as the same admission as clicking “we "
        "don't know”: it becomes a named gap with an owner and never appears "
        "as a rule. A real role called “TBD Coordination Office” still "
        "survives — the match is on the whole answer only."),

    "BUG-4E0C7B79": (FIXED,
        "7.4 is now the two options you described: the structure you chose "
        "in step 04, named and pre-selected, or “Someone else” with a "
        "fill-in. The blank no longer registers as missing.\n\n"
        "One refinement — where you pick “Someone else” and name a role, the "
        "framework prints the role you named rather than “someone else”. The "
        "audit trail at the back still shows both."),

    "BUG-DF9606E6": (FIXED,
        "8.4 takes as many roles as you want to add."),

    "BUG-67776904": (FIXED,
        "10.5 takes several roles now — CTO, Agency Director, and however "
        "many others should be able to act alone."),

    "BUG-07844C63": (FIXED,
        "7.1 now has “Add something else that should never go in”, with a "
        "form field, as you asked."),

    "BUG-5219EB75": (CLOSED,
        "Thank you — noted, and nothing changed."),

    "BUG-B898A895": (OPEN,
        "Left as it is, as you asked. Parked here rather than closed so it "
        "comes back when you have thought it through.\n\n"
        "For what it is worth, the pre-filled set of actions tuned to each "
        "agency is buildable — 1.1 already tells us what kind of body you "
        "are, and 6.1a's examples could be drawn from that the way the other "
        "illustrations are. Say the word and it is a small piece of work."),

    "BUG-B949552A": (OPEN,
        "Held open because we are not confident we have understood it, and "
        "would rather ask than build the wrong thing.\n\n"
        "Our reading: the last step's “Where will it live?” should pre-fill "
        "from what you chose at 9.10 about publishing, and offer other "
        "options alongside. Is that right, or did you mean a different "
        "field? “Section -3” could also be the third question of the "
        "unnumbered step, which is the same one."),
}


def _post(base: str, path: str, body: dict, session: str = "") -> dict:
    request = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    if session:
        request.add_header("X-GAIUS-Session", session)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def _get(base: str, path: str, session: str = "") -> dict:
    request = urllib.request.Request(base.rstrip("/") + path)
    if session:
        request.add_header("X-GAIUS-Session", session)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def _session(base: str) -> str:
    """An admin session, obtained the way a person obtains one."""
    asked = _post(base, "/api/agency/signin", {"email": ADMIN})
    code = asked.get("code")
    if not code:
        raise SystemExit(
            f"could not get a sign-in code for {ADMIN}: "
            f"{asked.get('error') or asked}\n"
            "Replies have to be posted by a real admin, so this needs the "
            "code that a sign-in would email. With SMTP configured, sign in "
            "as an admin in the browser and post from Reported Bugs instead.")
    done = _post(base, "/api/agency/verify", {"email": ADMIN, "code": code})
    if not done.get("session"):
        raise SystemExit(f"could not verify {ADMIN}: {done}")
    return str(done["session"])


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--post", action="store_true",
                        help="actually post them")
    args = parser.parse_args(argv)

    if not args.post:
        print(f"{len(REPLIES)} replies drafted. Nothing posted.\n")
        for ref, (status, said) in REPLIES.items():
            first = said.split("\n")[0]
            print(f"  {ref}  {status:<9} {first[:66]}")
        print("\nAdd --post to send them.")
        return 0

    session = _session(args.base)
    queue = _get(args.base, "/api/bugs?status=&user=sean.ot", session)
    if queue.get("error"):
        print(f"could not read the queue: {queue['error']}")
        return 1
    known = {t.get("id"): t for t in queue.get("tickets", [])}

    posted, skipped, failed = 0, 0, 0
    for ref, (status, said) in REPLIES.items():
        ticket = known.get(ref)
        if ticket is None:
            print(f"  --    {ref}  not in the queue")
            skipped += 1
            continue
        if ticket.get("replies"):
            print(f"  --    {ref}  already answered, left alone")
            skipped += 1
            continue
        # Two checks, both required and both correct: the endpoint verifies
        # the *identity* is one of the three admin addresses, and
        # `bugs.respond` guards the *capacity* through the usual chokepoint.
        # Sending no capacity defaults to operator, which is refused — as it
        # should be, since an operator answering another agency's report is
        # exactly what that guard is for.
        out = _post(args.base, "/api/bugs/respond?user=sean.ot",
                    {"id": ref, "message": said, "status": status}, session)
        if out.get("ok"):
            print(f"  ok    {ref}  {status}")
            posted += 1
        else:
            print(f"  FAIL  {ref}  {out.get('error') or out}")
            failed += 1

    _post(args.base, "/api/session/end", {"session": session})
    print(f"\n{posted} posted, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
