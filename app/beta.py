"""The beta notice, shown once each time somebody signs in.

The client: "after they login, we need a disclaimer. 'This is a beta version
of a tool. It is subject to error and is prone to errors etc etc blah blah
blah'. Not sure what we should put here, open to interpretation."

What it says, and why each part is there:

- **That it is a beta, plainly.** Unfinished, still changing, and wrong in
  places. Said once and not dressed up.
- **Check what it produces.** The framework is assembled from their own
  answers and is a draft until the people with authority adopt it. The
  Polished option runs the text through an AI writing tool that can alter
  what they meant — the same caution the download already gives, repeated
  here because this is the first thing a person reads.
- **It is not legal advice.** A governance framework touches public records,
  procurement and people's rights. Their attorney reviews it; this does not.
- **How to tell us.** A notice that asks people to expect errors owes them
  the way to report one.
- **What happens to what they enter.** One sentence, and only what is true:
  it stays within their organization and every change is recorded.

Kept here rather than in the page so the wording is in one place, carries a
version, and can be checked by the same tests that keep the rest of the
product's language honest. Changing the words is a new `VERSION`, and
everybody sees the new notice on their next sign-in.
"""

from __future__ import annotations

from typing import Any

#: Bumped whenever the wording changes, so a changed notice is shown again.
VERSION = "2026-09-24"

TITLE = "GoverningAI.US is in beta"

LEAD = ("This is an early version of GoverningAI.US, opened to governmental "
        "units so they can use it and tell us what needs to change. It is "
        "still being built. It will contain errors, screens and features will "
        "change, and some things may not yet work as described.")

POINTS: tuple[tuple[str, str], ...] = (
    ("Check everything it produces.",
     "Your framework is assembled from your own answers, but it is a draft "
     "until the people with the authority to adopt it have read it and done "
     "so. If you choose the Polished version, an AI writing tool rewords "
     "the text, and it can change or misstate what you meant — read it "
     "against your answers before you rely on it."),
    ("It is not legal advice.",
     "Have your attorney review the framework before it is adopted, "
     "especially where it touches public records, procurement, or anyone's "
     "rights."),
    # Worded for the control as it actually is: "Report an issue", inside the
    # ? help button in the corner. A first draft said "Report a bug", which
    # was the old standalone button's name and is not on the screen any more.
    ("Tell us when something is wrong.",
     "Press the ? button in the corner of any screen and choose Report an "
     "issue. It captures what you were looking at, so you only need to say "
     "what happened."),
)

DATA_LINE = ("What you enter stays within your organization, and every change "
             "is recorded in its audit trail.")

BUTTON = "I understand"

#: Said under the button, so nobody wonders what pressing it does.
RECORDED = ("Pressing this records that you have read this notice, with your "
            "name and the time.")


def notice() -> dict[str, Any]:
    return {"version": VERSION, "title": TITLE, "lead": LEAD,
            "points": [{"head": h, "body": b} for h, b in POINTS],
            "data": DATA_LINE, "button": BUTTON, "recorded": RECORDED}


def acknowledge(actor: Any, version: str) -> dict[str, Any]:
    """Record that this person read this version of the notice.

    Refuses a version that is not the current one, so an acknowledgment on
    the record always refers to words that were actually shown.
    """
    if version != VERSION:
        return {"ok": False, "error": "That is not the current notice."}
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "unknown",
            role=getattr(getattr(actor, "role", None), "value", "") or "",
            action="acknowledge_beta_notice", target="beta_notice",
            outcome="allowed",
            detail={"version": VERSION,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120],
                    "actor_title": str(getattr(actor, "title", "") or "")[:120],
                    "actor_email": str(getattr(actor, "email", "") or "")})
    except Exception:                                         # noqa: BLE001
        # A notice that could not be recorded is still a notice that was
        # read. The person is not stopped at the door over a log write.
        return {"ok": True, "recorded": False}
    return {"ok": True, "recorded": True}
