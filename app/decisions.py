"""Oversight — who decides, and what happens when it goes wrong.

The record of every decision made under the organization's framework: who
decided, on what day, under whose authority, and what they attached to it.
This surface owns `gate.govern`.

**The unit is one decision** — one thing decided, by one recorded decider, on
one date, with whatever was attached. That choice is load-bearing and worth
defending, because the obvious alternative is to build this around a council
and its meetings, and that fails half the organizations this product is for.

In a twelve-person water district there is no council, no minutes, no quorum
and no next session. There is a general manager who said yes on a Tuesday
afternoon in the yard. In a two-thousand-person agency there is a standing
group that reached consensus at a convened session, with one member recused,
two conditions attached and a minority view recorded. Those two look nothing
alike as meetings and are identical as decisions. A surface built on the
meeting is empty for the district and heavy for the agency; a surface built
on the decision holds both.

Every other surface holds evidence. This one holds the moment somebody looked
at that evidence and said yes, no, not yet, or yes on these conditions. It is
the only place in the product where authority is recorded, and it is the
first surface an auditor, a reporter, a board member or a judge asks for.

Named `decisions` rather than `oversight` because `app/oversight.py` already
exists and holds incident response — Levels 1 to 3, suspend, root-cause,
look-back, resume. Under this specification incidents belong to Integrity,
which owns Test and Measure. That module moves there when Integrity is
built; this one is the Oversight surface the spine describes.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import json
import secrets
import threading
from datetime import datetime, timezone
from typing import Any

from app import spine
from app.audit import atomic_write

FILENAME = "decisions.json"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file():
    from app import tenant
    from app.audit import CORPUS
    return tenant.scoped(CORPUS / "config" / FILENAME)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return _blank()
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _blank()
    if not isinstance(held, dict):
        return _blank()
    for key, empty in _blank().items():
        held.setdefault(key, empty)
    return held


def _blank() -> dict[str, Any]:
    return {"decisions": {}, "conditions": [], "weights": {},
            "labels": [], "escalation": {}, "hats": {}}


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _record(action: str, actor: Any, detail: dict[str, Any]) -> None:
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "unknown",
            role=getattr(getattr(actor, "role", None), "value", "")
            or "system",
            action=action, target="Oversight", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]})
    except Exception:                                         # noqa: BLE001
        pass


# ===========================================================================
# The four governance shapes
# ===========================================================================

#: Module One 4.1 lets an organisation choose one of four shapes, and this
#: surface renders whichever one they chose without ever implying that a
#: heavier one was correct. Everything that differs between them is a
#: rendering difference; the underlying decision row is identical.
ONE_PERSON = "one"
SMALL_GROUP = "group"
COUNCIL = "council"
EXISTING_BODY = "existing"
SHAPES = (ONE_PERSON, SMALL_GROUP, COUNCIL, EXISTING_BODY)

#: The shapes that have a body rather than a person. Presence, seats and the
#: session vocabulary belong to these two and to nothing else.
BODIES = (SMALL_GROUP, COUNCIL)

#: Words that must never reach an organisation that did not choose the shape
#: they belong to — unless the organisation typed them itself.
#:
#: This is the rule most easily broken, and the outcome list is where it
#: breaks: the outcome that puts a matter off renders as "Put off for now"
#: to a single decider and as "Deferred to the next session" to a body. One
#: stored value, two strings.
SHAPE_WORDS = ("council", "quorum", "seat", "consensus", "vote", "session")


def body_name(shape: str, named: str = "") -> str:
    """What the decider is called, in this organization's own words."""
    named = (named or "").strip()
    if shape == ONE_PERSON:
        return named or "whoever decides"
    if shape == COUNCIL:
        return named or "the council"
    if shape == SMALL_GROUP:
        return named or "the group"
    # Shape D has a name the organisation gave it, and this surface uses
    # that name everywhere: "the executive team" and "the safety committee"
    # are not interchangeable to the people who sit on them.
    return named or "the group that took this on"


def asks_who_was_present(shape: str) -> bool:
    """Optional, repeatable rows — and only for a body.

    Whoever attended without a seat is recorded as present and is not
    counted as deciding.
    """
    return shape in BODIES


# ===========================================================================
# Outcomes
# ===========================================================================

APPROVED = "outcome.approved"
APPROVED_WITH = "outcome.approved_with_conditions"
SENT_BACK = "outcome.sent_back"
TURNED_DOWN = "outcome.turned_down"
DEFERRED = "outcome.deferred"
STOPPED = "outcome.stopped"
RETIRED = "outcome.retired"
NOT_DECIDED = ""

#: The seven outcomes at 6.9, in the specification's order. Outcome may be
#: left unanswered, which is a real answer: somebody asked, it is written
#: down, and it is waiting.
OUTCOMES = (APPROVED, APPROVED_WITH, SENT_BACK, TURNED_DOWN, DEFERRED,
            STOPPED, RETIRED)

# ---------------------------------------------------------------------------
# 6.6 · How it was decided — written once here and nowhere else
# ---------------------------------------------------------------------------

DECIDED_ALONE = "decided.alone"
DECIDED_MEETING = "decided.meeting"
DECIDED_IN_WRITING = "decided.in_writing"
DECIDED_TIEBREAK = "decided.tiebreak"
DECIDED_DELEGATION = "decided.delegation"
HOW_DECIDED = (DECIDED_ALONE, DECIDED_MEETING, DECIDED_IN_WRITING,
               DECIDED_TIEBREAK, DECIDED_DELEGATION)


def how_decided_options(shape: str, named: str = "",
                        tiebreaker: str = "") -> list[dict[str, str]]:
    """Two options for one person, four for a body. [Body] is the shape's own
    word: the group, the council, or the name the organization gave it. There
    is no chair option, because Module One asks no question about a chair."""
    if shape == ONE_PERSON:
        return [{"value": DECIDED_ALONE, "label": "One person decided"},
                {"value": DECIDED_DELEGATION,
                 "label": "Decided under the delegation, without a meeting"}]
    body = body_name(shape, named)
    body = body[:1].upper() + body[1:]
    who = tiebreaker.strip() or "whoever has the final say"
    return [
        {"value": DECIDED_MEETING, "label": f"{body} agreed at a meeting"},
        {"value": DECIDED_IN_WRITING,
         "label": f"{body} agreed in writing, without meeting"},
        {"value": DECIDED_TIEBREAK,
         "label": f"{body} could not agree, so {who} decided"},
        {"value": DECIDED_DELEGATION,
         "label": "Decided under the delegation, without a meeting"},
    ]


# ---------------------------------------------------------------------------
# 6.1 · What kind of decision is this?
# ---------------------------------------------------------------------------

KIND_TOOL = "kind.tool"
KIND_FRAMEWORK = "kind.framework"
KIND_WENT_WRONG = "kind.went_wrong"
KIND_STANDING = "kind.standing"
KIND_WEIGHTS = "kind.weights"
KINDS = (
    (KIND_TOOL, "About a tool or a proposal",
     "approving, turning down, sending back, or setting a level"),
    (KIND_FRAMEWORK, "About the framework itself",
     "adopting it, changing it, or its scheduled look"),
    (KIND_WENT_WRONG, "About something that went wrong",
     "what was decided after a wrong or harmful result"),
    (KIND_STANDING, "A standing decision",
     "who may do what, from now on, without asking again"),
    (KIND_WEIGHTS, "About how candidates are weighed",
     "what you weigh, and how heavily, when you are choosing between two or "
     "more candidate solutions"),
)
KIND_NAMES = {k: name for k, name, _ in KINDS}

# 6.16 · 6.21 · 6.25 · 6.29 · 6.32 · 6.34 · 6.35 — the fixed option lists.
FRAMEWORK_WHAT = ("Adopting it for the first time", "Changing it",
                  "Its scheduled look, with no changes",
                  "Its scheduled look, with changes")
CHANGES = ("Changing it", "Its scheduled look, with changes")
OWED = ("Yes, approved and recorded", "Notice given to the adopting authority",
        "Not yet", "Not required, we said the group can change it on its own")
STOPPED_ANSWERS = ("Yes", "No", "It stopped itself",
                   "Not yet, and here is why")
LOOKBACK_ANSWERS = ("Yes, as far as you said", "Yes, a different period",
                    "No", "Not yet")
STANDING_WHICH = ("Who may approve what without asking",
                  "Who may stop a tool without waiting",
                  "How often this gets looked at",
                  "What each level of scrutiny requires",
                  "Who is told when something goes wrong", "Something else")
STANDING_CHANGES = ("Yes, and it needs the adopting authority",
                    "Yes, and we said the group can change it on its own",
                    "No, this is how we are reading what is already there")
WEIGHTS_WHAT = ("Setting the weights for the first time", "Changing them",
                "Confirming them unchanged")

#: The fields a decision row may carry beyond the core, by kind. Anything
#: else sent is dropped rather than stored.
EXTRA_FIELDS = (
    "kind", "hat_worn", "consulted", "why", "disagreed", "where_else",
    "anyway_reason",
    # 6C · the framework itself
    "framework_what", "adopted_by_title", "effective_on", "what_changed",
    "owed", "comes_back",
    # 6D · something that went wrong
    "incident", "severity", "severity_position", "was_stopped",
    "not_stopped_why", "stopped_by", "stopped_at", "told", "lookback",
    "lookback_other", "restart_condition", "writeup_by",
    # 6E · a standing decision
    "standing_which", "standing_other", "says_now", "changes_framework",
    # 6F · how candidates are weighed
    "weights_what", "axes", "single_factors", "weights_owner", "weights_from",
    "weights_version")


def outcome_label(outcome: str, shape: str) -> str:
    """The stored value rendered for this organization's shape.

    Only the deferred outcome differs, and it is the one that matters:
    "Deferred to the next session" told to a general manager who decided it
    in the yard is the application describing a meeting that does not exist.
    """
    if outcome == DEFERRED:
        return ("Deferred to the next session" if shape in BODIES
                else "Put off for now")
    return {
        APPROVED: "Approved",
        APPROVED_WITH: "Approved, with conditions",
        SENT_BACK: "Sent back for more",
        TURNED_DOWN: "Turned down",
        STOPPED: "Stopped it where it stands",
        RETIRED: "Retired it",
        NOT_DECIDED: "Not decided yet",
    }.get(outcome, "Not decided yet")


# ===========================================================================
# The decision record
# ===========================================================================

def _reference(existing: set[str]) -> str:
    for _ in range(64):
        ref = "D-" + "".join(secrets.choice("23456789BCDFGHJKMNPQRSTVWXYZ")
                             for _ in range(6))
        if ref not in existing:
            return ref
    return "D-" + secrets.token_hex(6).upper()


def record(*, about: str, what: str, actor: Any, shape: str = ONE_PERSON,
           decider: str = "", outcome: str = NOT_DECIDED,
           how_decided: str = "", present: list[str] | None = None,
           conditions: list[dict[str, Any]] | None = None,
           minority: str = "", recused: list[str] | None = None,
           gate: str = "", decided_on: str = "",
           extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """One thing decided, by one recorded decider, on one date.

    Only the line saying what was decided is required. A decision with no
    statement of what was decided is not a record of anything; everything
    else may be left for later.
    """
    if not str(what or "").strip():
        return {"ok": False, "error": "Say what was decided, in one line."}
    if outcome and outcome not in OUTCOMES:
        return {"ok": False, "error": f"{outcome!r} is not an outcome."}
    if how_decided and how_decided not in HOW_DECIDED:
        how_decided = ""
    extra = {k: v for k, v in (extra or {}).items() if k in EXTRA_FIELDS}

    with _LOCK:
        held = _read()
        ref = _reference(set(held["decisions"]))
        row = {
            "ref": ref,
            "about": about,
            "what": what,
            "gate": gate,
            "shape": shape,
            "decider": decider,
            "outcome": outcome,
            "how_decided": how_decided,
            # Only a body is asked, and whoever attended without a seat is
            # present rather than deciding.
            "present": list(present or []) if shape in BODIES else [],
            "recused": list(recused or []) if shape in BODIES else [],
            "minority": minority if shape in BODIES else "",
            # The day it was actually decided. Left empty where nobody said,
            # and the list shows "No date recorded" rather than today.
            "decided_on": str(decided_on or "")[:10],
            "recorded_at": _now(),
            "recorded_by": str(getattr(actor, "name", "") or ""),
            "hat": getattr(getattr(actor, "role", None), "value", ""),
            "version": _framework_version(),
            **extra,
        }
        held["decisions"][ref] = row
        for condition in conditions or []:
            held.setdefault("conditions", []).append({
                **condition, "decision": ref, "attached_at": _now(),
                "closed": None})
        _write(held)

    _record("event.decision_recorded", actor,
            {"decision": ref, "outcome": outcome, "about": about})
    for condition in conditions or []:
        _record("event.condition_attached", actor,
                {"decision": ref, **condition})
    return {"ok": True, "decision": row}


def _framework_version() -> str:
    """The version in force, stamped on the decision at the moment it is made.

    Every project inherits the Govern pass and carries this stamp. It is what
    lets somebody say, two years from now, what the rules were on the day
    something was approved rather than what the rules are today.
    """
    try:
        from app import versions
        return str(versions.export_label() or "")
    except Exception:                                         # noqa: BLE001
        return ""


def all_decisions() -> list[dict[str, Any]]:
    rows = list(_read()["decisions"].values())
    rows.sort(key=lambda d: str(d.get("recorded_at") or ""), reverse=True)
    return rows


def conditions(open_only: bool = False) -> list[dict[str, Any]]:
    held = _read().get("conditions") or []
    return [c for c in held if not c.get("closed")] if open_only else held


# ===========================================================================
# The stat row
# ===========================================================================

#: Exactly five counters, all counts and absences, no score of any kind.
def counters(rows: list[dict[str, Any]] | None = None,
             held_conditions: list[dict[str, Any]] | None = None,
             hats: dict[str, list[str]] | None = None) -> dict[str, Any]:
    rows = all_decisions() if rows is None else rows
    held_conditions = (conditions() if held_conditions is None
                       else held_conditions)
    today = clock.today_str()

    open_conditions = [c for c in held_conditions if not c.get("closed")]
    overdue = [c for c in open_conditions
               if str(c.get("by") or "").strip()
               and str(c["by"]) < today]

    # Counted against the stored value rather than the rendered string,
    # because that string differs by governance shape.
    waiting = sum(1 for d in rows
                  if not d.get("outcome") or d.get("outcome") == DEFERRED)

    return {
        "recorded": len(rows),
        # This tile counts decisions this body has not yet made. The spine's
        # `state.waiting_person` renders as "Waiting on somebody" and means
        # something else entirely — one record held up on a named person or
        # an office the organisation does not have. Two different objects,
        # two different counts, and no copy on this surface borrows the
        # other's string.
        "asked_not_decided": waiting,
        "conditions_open": len(open_conditions),
        "conditions_overdue": len(overdue),
        "roles_held": concentration(hats or {}),
        "says": {
            "asked_not_decided":
                "Somebody asked and nobody has decided. In a small "
                "organization this is usually zero, because the person who "
                "asks is the person who decides.",
        },
    }


def concentration(hats: dict[str, list[str]]) -> dict[str, Any]:
    """The largest number of the three hats held by any one person.

    A fact the organization already knows, stated once so that it appears in
    the record rather than only in the room. No color treatment, no
    threshold, no arrow, no advice, and never a link — a link from this tile
    would be the beginning of advice.
    """
    most = max((len(set(h)) for h in hats.values()), default=1) or 1
    return {
        "held": most,
        "of": len(spine.ROLES),
        "shown_as": f"{most} of {len(spine.ROLES)}",
        "says": (f"{_spelled(most)} of three roles held by one person."
                 if most > 1 else "Nobody here holds more than one hat."),
        "is_a_link": False,
    }


def _spelled(n: int) -> str:
    return {1: "One", 2: "Two", 3: "Three"}.get(n, str(n))


# ===========================================================================
# The adoption line
# ===========================================================================

#: Five renderings and no sixth. Every title, date and cadence is read from
#: the organisation's own answers; the application supplies none of its own.
def adoption_line(*, adopted_on: str = "", authority: str = "",
                  version: str = "", in_effect: str = "",
                  cadence: str = "", next_look: str = "",
                  signed_copy: bool = True, review_passed: bool = False,
                  gap_owner: str = "", gap_by: str = "") -> str:
    if not adopted_on:
        return ("No framework adopted yet. Nothing on this list binds "
                "anybody until whoever has the authority adopts one.")

    version_part = f"Version {version}" if version else "Version not recorded"

    if not authority.strip():
        # Never rendered blank and never rendered with an invented name.
        # "An elected board or council, by vote" is a category and reads as
        # nothing in a sentence, so where no title was typed the line
        # carries the recorded gap instead.
        tail = (f"Owned by {gap_owner}, by {gap_by}." if gap_by
                else f"Owned by {gap_owner}, no date set.")
        return (f"Adopted {adopted_on}. {version_part}"
                f"{f', in effect since {in_effect}' if in_effect else ''}. "
                f"Who has the authority to adopt this (Step 1, question 3): "
                f"you said you were not sure. {tail}")

    opening = f"Adopted {adopted_on} by {authority}. {version_part}"
    if not signed_copy:
        return (f"{opening}"
                f"{f', in effect since {in_effect}' if in_effect else ''}. "
                f"No signed copy on file.")
    if review_passed:
        return (f"{opening}. You said it comes back {cadence}; the last look "
                f"was {adopted_on}.")
    return (f"{opening}"
            f"{f', in effect since {in_effect}' if in_effect else ''}. "
            f"You said it comes back {cadence}; next look {next_look}.")


# ===========================================================================
# Findings
# ===========================================================================

SHARED_FINDINGS = ("finding.condition_overdue", "finding.consulted_missing",
                   "finding.gap_no_owner", "finding.framework_moved")

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.oversight.above_delegation", "Oversight",
        "A decision approved by the Operator hat, on a record outside the "
        "delegation the organization set",
        "You said an Operator may approve [their delegation answer]. This "
        "one is [what it is]."),
    spine.Finding(
        "finding.oversight.deferred_twice", "Oversight",
        "The same matter recorded twice or more at the deferred outcome, "
        "where the organization named a tiebreaker",
        "This has been put off twice. You named [role] as the one who "
        "decides when there is no agreement."),
    spine.Finding(
        "finding.oversight.cadence_missed", "Oversight",
        "The last decision is older than the cadence the organization set, "
        "and at least one record is waiting",
        "You said [cadence]. The last decision recorded here was [date], and "
        "[N] are waiting."),
    spine.Finding(
        "finding.oversight.stop_authority_unnamed", "Oversight",
        "Nobody is named who can stop a tool without waiting, and at least "
        "one record is in use",
        "Nobody is named who can stop a tool without waiting for a meeting, "
        "and [N] are in use."),
    spine.Finding(
        "finding.oversight.notify_not_recorded", "Oversight",
        "A decision responding to something that went wrong, at a severity "
        "where a party must be told, with no notification recorded",
        "You said [party] has to be told when something at this level "
        "happens. Nothing here records that."),
    spine.Finding(
        "finding.oversight.lookback_not_decided", "Oversight",
        "A response decision at the second or third severity level records "
        "no look-back determination",
        "You said you go back [period] after a serious problem. This "
        "decision does not say whether that was done."),
    spine.Finding(
        "finding.oversight.amendment_unapproved", "Oversight",
        "A framework amendment recorded as proposed, on one of the two "
        "answers that owe somebody something",
        "This amendment is recorded as proposed and nothing records "
        "[what is owed]."),
    # 3.12. Missing until now. A condition with an owner and no date will not
    # come back on its own, and on a tool in use that matters.
    spine.Finding(
        "finding.oversight.condition_no_date", "Oversight",
        "A condition with an owner and no date, on a record that is in use",
        "This condition has nobody's date on it. It will not come back on "
        "its own."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}

#: Findings written for this surface and cut, named so that nobody restores
#: them without first changing Module One. From the specification's own list.
#:
#: The first was built here — `finding.oversight.before_adoption` — against
#: the specification's explicit instruction, and has been taken out. A
#: decision dated before the framework took effect has no framework answer to
#: contradict, because on that date there was no framework. It would have put
#: a finding on every row a new organization records on its first day. The
#: fact stays on the row instead — see `decided_before_framework` — and it can
#: be filtered on. Nothing more is done with it.
CUT_FINDINGS: dict[str, str] = {
    "a decision dated before the framework took effect":
        "There is no framework answer for it to contradict. Carried on the "
        "row as 'Decided before the framework took effect' and filterable.",
    "a proposer deciding their own proposal":
        "Module One asks no conflict-of-interest or recusal question, so "
        "there is no rule of theirs to hold them to.",
    "a decision with no reviewer from outside the program":
        "None of the four things Module One 5.3 asks per level captures "
        "'from outside the program'.",
    "a severity the framework does not describe":
        "It cannot occur: every organization always has three defined "
        "levels, and the picker is drawn from them.",
}

#: Never raised here, stated so nobody adds them later.
WILL_NOT_RAISE = (
    "One person holding all three hats.",
    "A small organization approving its own proposals.",
    "A decision shape lighter than the headcount suggests.",
    "A cadence of 'as requests come in'.",
    "A short framework.",
    "Functions the organization marked as not present. The absence of an "
    "office is never shown as a defect anywhere on this screen.",
    "Anything about the ranking weights, or about labels for information.",
    "A recommendation somebody declined.",
)

DECIDED_BEFORE_FRAMEWORK = "Decided before the framework took effect"


def decided_before_framework(row: dict[str, Any], adopted_on: str) -> bool:
    """A fact about the row, never a finding. See `CUT_FINDINGS`."""
    when = str(row.get("decided_on") or "")
    return bool(adopted_on and when and when < adopted_on)

#: The trigger for the look-back finding binds to a severity level's
#: *position*, never to its name, because an organisation may rename all
#: three. A renamed level keeps its position and the rule survives the
#: rename.
LOOKBACK_LEVELS = (2, 3)


def findings(*, rows: list[dict[str, Any]] | None = None,
             cadence: str = "", tiebreaker: str = "",
             stop_authority: str = "", in_use: int = 0,
             adopted_on: str = "",
             in_use_records: set[str] | None = None) -> list[dict[str, Any]]:
    """`adopted_on` is still accepted, and deliberately raises nothing — a
    decision before the framework took effect is a fact on the row, not a
    contradiction. See `CUT_FINDINGS`.

    `in_use_records` is the set of records with in_use = yes, read from
    Projects. It feeds the one finding that depends on it.
    """
    rows = all_decisions() if rows is None else rows
    found: list[dict[str, Any]] = []

    deferred: dict[str, int] = {}
    for row in rows:
        if row.get("outcome") == DEFERRED:
            key = str(row.get("about") or "")
            deferred[key] = deferred.get(key, 0) + 1

    if tiebreaker.strip():
        for about, times in deferred.items():
            if times >= 2:
                found.append({
                    "id": "finding.oversight.deferred_twice",
                    "says": (f"This has been put off {times} times. You "
                             f"named {tiebreaker} as the one who decides "
                             f"when there is no agreement."),
                    "about": about})

    if not stop_authority.strip() and in_use:
        found.append({
            "id": "finding.oversight.stop_authority_unnamed",
            "says": (f"Nobody is named who can stop a tool without waiting "
                     f"for a meeting, and {in_use} are in use.")})

    today = clock.today_str()
    in_use_records = in_use_records or set()
    about_of = {r.get("ref"): r.get("about") for r in rows}
    for condition in conditions(open_only=True):
        by = str(condition.get("by") or "")
        if by and by < today:
            found.append({
                "id": "finding.condition_overdue",
                "says": (f"A condition on this is past its date: "
                         f"{condition.get('what', '')}, owned by "
                         f"{condition.get('owner', '')}.")})
        # 3.12 — an owner and no date, on something in use. A condition
        # with nobody's date on it never comes back by itself, and a tool in
        # use is where that costs something. Without an owner it is
        # `finding.gap_no_owner`'s business, not this one's.
        about = condition.get("about") or about_of.get(condition.get("decision"))
        if (not by and str(condition.get("owner") or "").strip()
                and about in in_use_records):
            found.append({
                "id": "finding.oversight.condition_no_date",
                "says": "This condition has nobody's date on it. It will not "
                        "come back on its own.",
                "about": about})

    return found


# ===========================================================================
# 4 · The standing watch
# ===========================================================================

#: The whole of the automation on this surface, and deliberately no more.
#: It reads the organization's own dates and nothing outside the application.
WATCH_SAYS = "Your own dates, re-read every night and whenever you open this screen."

CHECK_THE_DATES = "Check the dates now"

#: How far ahead "coming due before your next look" reaches, read from their
#: own answer at Module One 4.5. The option they chose, turned into days; the
#: application supplies no cadence of its own. "As requests come in" has no
#: next look at all, which is its own honest answer below.
CADENCE_DAYS = {"monthly": 31, "quarterly": 92, "biannual": 183, "annual": 366}
ON_REQUEST = "onrequest"

NO_NEXT_LOOK = ("You decide as things come in, so there is no next look to "
                "count toward.")

#: Shown under the watch, and not collapsible.
WATCH_CANNOT = (
    "This watch reads your own dates and nothing else. It cannot tell whether "
    "a meeting happened, whether somebody signed a paper copy, or whether a "
    "decision was made in a hallway and never written down here. Nothing "
    "checks a calendar, nothing reads your minutes, and nothing verifies a "
    "signature; where you sign on paper, this records that a file was "
    "uploaded, by whom, and when. There is no tick on this screen that means "
    "'we assume it happened'.")


def standing_watch(held_conditions: list[dict[str, Any]] | None = None, *,
                   cadence: str = "", today: str = "") -> dict[str, Any]:
    """Four counters over open conditions — text and number only."""
    held_conditions = (conditions(open_only=True) if held_conditions is None
                       else [c for c in held_conditions if not c.get("closed")])
    today = today or clock.today_str()

    dated = [c for c in held_conditions if str(c.get("by") or "").strip()]
    past = [c for c in dated if str(c["by"]) < today]
    undated = [c for c in held_conditions if not str(c.get("by") or "").strip()]

    window = CADENCE_DAYS.get(cadence)
    if cadence == ON_REQUEST:
        coming: Any = None
        note = NO_NEXT_LOOK
    elif window:
        from datetime import date, timedelta
        horizon = (date.fromisoformat(today) + timedelta(days=window)).isoformat()
        coming = sum(1 for c in dated if today <= str(c["by"]) <= horizon)
        note = ""
    else:
        # No cadence answered yet. Nothing is invented to stand in for it.
        coming = None
        note = ("You have not said how often decisions are looked at, so "
                "there is no next look to count toward yet.")

    return {
        "says": WATCH_SAYS,
        "with_a_date": len(dated),
        "coming_due": coming,
        "coming_due_shown": "—" if coming is None else str(coming),
        "coming_due_note": note,
        "past_their_date": len(past),
        "no_date_set": len(undated),
        "control": CHECK_THE_DATES,
        "cannot": WATCH_CANNOT,
    }


# ===========================================================================
# 4A · What you said happens when it goes wrong
# ===========================================================================

#: A read-only panel rendered entirely from Module One 10.2 to 10.7. It
#: exists because 10.2 sets its own test: a person or channel a new employee
#: could find in under a minute. Edited by recording a decision, never by
#: typing into the panel — a panel that could be edited in place would let
#: somebody change the reporting rules without a decision.
WENT_WRONG_HEADING = "When a tool produces a wrong or harmful result"

WENT_WRONG_ROWS: tuple[tuple[str, str], ...] = (
    ("Tell", "bad.report_to"),
    ("Your levels", "bad.levels"),
    ("How fast", "bad.speed"),
    ("Who can stop it without waiting", "bad.stopper"),
    ("Do you go back over earlier work", "bad.lookback"),
    ("Who outside is told", "bad.tell"),
)

RECORD_SOMETHING_WENT_WRONG = "Record something that went wrong"


def when_it_goes_wrong(answers: dict[str, Any] | None = None) -> dict[str, Any]:
    """The organization's own words from Step 10, row by row.

    Where a question is unanswered the row carries the recorded gap —
    which question, and that nobody has answered it — rather than an empty
    line. Module One already filters the parties at 10.7 by the functions
    the organization said it has, so an office it does not have is never
    listed and never shown as missing.
    """
    from app import module_one
    answers = answers if answers is not None else _working_answers()
    rows = []
    for label, key in WENT_WRONG_ROWS:
        question = module_one.by_key(key)
        said = (module_one.describe(question, answers)
                if question and module_one.visible(question, answers)
                else {"state": "hidden"})
        if said.get("state") == "answered":
            rows.append({"label": label, "key": key, "answered": True,
                         "lines": list(said.get("lines") or [])})
        elif said.get("state") == "hidden":
            continue
        else:
            gap = ("Nobody named yet." if key == "bad.stopper"
                   else "Not answered yet.")
            rows.append({"label": label, "key": key, "answered": False,
                         "lines": [f"{gap} Step 10, question "
                                   f"{question.number if question else ''}."]})
    return {"heading": WENT_WRONG_HEADING, "rows": rows,
            "control": RECORD_SOMETHING_WENT_WRONG, "editable": False}


def _working_answers() -> dict[str, Any]:
    try:
        from app import versions
        return dict(versions.state().get("working") or {})
    except Exception:                                         # noqa: BLE001
        return {}


# ===========================================================================
# Ranking weights
# ===========================================================================

#: The set of weights by which candidate solutions are ranked at a purchase
#: decision. Somebody has to say what the organisation is weighing and how
#: heavily, and that is a governance decision with a recorded owner and a
#: date — the alternative is a number living in a formula that one person
#: can change without telling anybody.
#:
#: What the weights are applied to is always a candidate solution and never
#: the organisation.
def set_weights(axes: dict[str, float], actor: Any, *,
                why: str = "") -> dict[str, Any]:
    if not axes:
        return {"ok": False,
                "error": "A weighting needs at least one axis to weigh."}
    with _LOCK:
        held = _read()
        held["weights"] = {
            "axes": {str(k): float(v) for k, v in axes.items()},
            "set_by": str(getattr(actor, "name", "") or ""),
            "hat": getattr(getattr(actor, "role", None), "value", ""),
            "on": clock.today_str(),
            "why": why,
            "version": _framework_version(),
        }
        _write(held)
    _record("event.decision_recorded", actor,
            {"what": "ranking weights", "axes": list(axes)})
    return {"ok": True, "weights": held["weights"]}


def weights() -> dict[str, Any]:
    return _read().get("weights") or {}


#: Where the organisation has not settled what it is weighing, candidates
#: are shown side by side, unranked, on whatever axes they did settle. The
#: application computes nothing until then.
UNWEIGHTED = ("You have not said what you are weighing or how heavily, so "
              "these are shown side by side rather than ranked. Setting the "
              "weights is a decision with somebody's name on it.")

#: Never about the organisation. The two rules read as contradictory to
#: anyone who has not been told which is which, so this surface says which.
SCORING_LINE = ("Candidate solutions are ranked here, on your own weights, "
                "with the working shown. Nothing in this application scores "
                "your organization, your governance or your progress.")


# ===========================================================================
# The organisation's own labels
# ===========================================================================

#: Where an organisation keeps its own labels for information, the list
#: lives here so that Data can offer them back on a holding. The framework
#: asks for no such scheme and nothing here requires one — an organisation
#: that keeps none never learns that this block exists.
def labels() -> list[str]:
    return list(_read().get("labels") or [])


def set_labels(names: list[str], actor: Any) -> dict[str, Any]:
    with _LOCK:
        held = _read()
        held["labels"] = [str(n).strip() for n in names if str(n).strip()]
        _write(held)
    _record("event.decision_recorded", actor,
            {"what": "information labels", "count": len(held["labels"])})
    return {"ok": True, "labels": held["labels"]}


def has_labels() -> bool:
    return bool(labels())


# ===========================================================================
# The whole surface
# ===========================================================================

def report(*, shape: str = ONE_PERSON, named: str = "",
           hats: dict[str, list[str]] | None = None, cadence: str = "",
           adopted_on: str = "",
           answers: dict[str, Any] | None = None) -> dict[str, Any]:
    rows = all_decisions()
    # The fact on the row that replaced a finding the specification cut.
    for row in rows:
        row["before_framework"] = decided_before_framework(row, adopted_on)
    return {
        "decisions": rows,
        "before_framework_label": DECIDED_BEFORE_FRAMEWORK,
        "conditions": conditions(),
        "counters": counters(rows, hats=hats),
        "standing_watch": standing_watch(cadence=cadence),
        "when_it_goes_wrong": when_it_goes_wrong(answers),
        "will_not_raise": list(WILL_NOT_RAISE),
        "cut_findings": dict(CUT_FINDINGS),
        "shape": shape,
        "body": body_name(shape, named),
        "asks_who_was_present": asks_who_was_present(shape),
        "outcomes": [{"value": o, "label": outcome_label(o, shape)}
                     for o in OUTCOMES],
        "weights": weights(),
        "unweighted": UNWEIGHTED,
        "scoring_line": SCORING_LINE,
        "labels": labels(),
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "shared_findings": list(SHARED_FINDINGS),
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "role_powers": {"approve": spine.MAY_APPROVE,
                        "retire": spine.MAY_RETIRE},
    }


# ===========================================================================
# Conditions are closed on the decision they belong to
# ===========================================================================

def close_condition(decision: str, index: int, *, actor: Any, by: str = "",
                    may_close_any: bool = False) -> dict[str, Any]:
    """Close one condition. A User or the technology hat may close those they
    own; whoever decides may close any. Nothing is removed — a closed
    condition stays on the list with who closed it and when."""
    with _LOCK:
        held = _read()
        mine = [c for c in held.get("conditions") or []
                if c.get("decision") == decision]
        if not 0 <= index < len(mine):
            return {"ok": False, "error": "No such condition."}
        condition = mine[index]
        if condition.get("closed"):
            return {"ok": False, "error": "That condition is already closed."}
        owner = str(condition.get("owner") or "").strip().lower()
        title = str(getattr(actor, "title", "") or "").strip().lower()
        if not may_close_any and (not owner or owner != title):
            return {"ok": False,
                    "error": "You can close conditions you own. Whoever "
                             "decides can close any of them."}
        condition["closed"] = {"on": clock.today_str(),
                               "by": by or str(getattr(actor, "title", "")
                                               or getattr(actor, "name", ""))}
        _write(held)
    _record("event.condition_closed", actor, {"decision": decision,
                                              "index": index})
    return {"ok": True, "condition": condition}


# ===========================================================================
# 8 · Framework read-back
# ===========================================================================

def _lower_first(text: str) -> str:
    text = str(text or "")
    return text[:1].lower() + text[1:] if text else text


#: Module One 4.4's parties and the 1.4 function each maps to. "The program
#: that will actually use it" is not an office, so it always exists.
_PARTY_FUNCTION = {"exec": "exec", "it": "it", "legal": "legal",
                   "security": "security", "purchasing": "purchasing",
                   "finance": "finance", "hr": "hr", "comms": "comms",
                   "records": "records", "program": ""}

#: 10.7's parties and the 1.4 function each needs, where one is needed.
_TOLD_FUNCTION = {"attorney": "legal"}

_REVIEW_YEARS = {"annual": 1, "biennial": 2}


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    """Everything Oversight reads from Module One. Missing answers stay
    missing; nothing is invented to stand in for one."""
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def asked(key: str) -> bool:
        q = m.by_key(key)
        return bool(q) and m.answered(q, answers)

    def label_of(key: str, raw: Any) -> str:
        q = m.by_key(key)
        for o in (q.options if q else []) or []:
            if o.value == raw:
                return m._fill(o.label, answers)
        return str(raw or "")

    def listed(key: str) -> list[str]:
        got = value(key) if asked(key) else []
        return [g for g in (got if isinstance(got, list) else [got])
                if g and g != m.UNKNOWN]

    out: dict[str, Any] = {"readbacks": {}}
    rb = out["readbacks"]

    shape = value("who.shape")
    out["shape"] = shape if shape in SHAPES else ONE_PERSON
    out["shape_answered"] = shape in SHAPES
    seats = value("who.seats") or []
    out["seats"] = [str(r.get("role") or r.get("title") or "").strip()
                    for r in seats if isinstance(r, dict)
                    and str(r.get("role") or r.get("title") or "").strip()]
    # Shape D's body carries the name they typed; 4.2 holds it where they
    # gave one.
    named = ""
    for extra in (m.value_of(answers, "who.seats")[1] or {}).values():
        if isinstance(extra, str) and extra.strip():
            named = extra.strip()
            break
    out["body_named"] = named
    out["body"] = body_name(out["shape"], named)
    out["tiebreaker"] = str(value("who.tiebreak") or "").strip()
    cadence = value("who.cadence")
    out["cadence"] = cadence or ""
    out["cadence_words"] = _lower_first(label_of("who.cadence", cadence)) \
        if cadence else ""
    out["decision_place"] = str(value("who.record") or "").strip()

    # 4.6 · the delegation.
    out["delegation"] = listed("who.without")
    rb["delegation"] = (
        "You said nothing moves without whoever decides."
        if "nothing" in out["delegation"] else
        "You said these can move forward without whoever decides: " +
        "; ".join(_lower_first(label_of("who.without", w))
                  for w in out["delegation"]) + "."
        if out["delegation"] else "")

    # 1.4 · functions, and 4.4 · who has to be asked, filtered by them.
    functions = value("org.functions")
    functions = functions if isinstance(functions, dict) else {}
    missing_how = value("who.missing")
    missing_how = missing_how if isinstance(missing_how, dict) else {}
    consulted, outside = [], []
    for party in listed("who.consulted"):
        fn = _PARTY_FUNCTION.get(party, "")
        label = label_of("who.consulted", party)
        if fn and functions.get(fn) == "none":
            # Never routed to an office they do not have. Where they said
            # outside help would be needed, one line says so instead.
            if str(missing_how.get(fn) or "").startswith("outside"):
                outside.append(label)
            continue
        consulted.append(label)
    out["must_consult"] = consulted
    out["consult_outside"] = outside

    # 4.8 · 4.9 · 4.10 · the adopting authority and what is owed.
    out["adopter_category"] = _lower_first(label_of("who.signs",
                                                    value("who.signs")))
    amend = value("who.amend")
    out["amend"] = amend or ""
    out["amend_words"] = _lower_first(label_of("who.amend", amend)) \
        if amend else ""
    review = value("who.review")
    out["review"] = review or ""
    out["review_words"] = _lower_first(label_of("who.review", review)) \
        if review else ""

    # 5.2 · their level names.
    out["levels"] = [n for _, n in m.level_names(answers)]

    # 5.4 · one factor settles it; 5.1 · the factors that matter.
    out["single_factor"] = value("risk.worst") == "yes"
    factors = value("risk.factors") if asked("risk.factors") else {}
    q_factors = m.by_key("risk.factors")
    out["factors"] = [r.label for r in (q_factors.rows if q_factors else [])
                      if (factors or {}).get(r.value) in ("some", "major")]

    # 10.3 · their severity levels, by position.
    q_levels = m.by_key("bad.levels")
    given = value("bad.levels") if asked("bad.levels") else {}
    severities = []
    for pos, row in enumerate((q_levels.rows if q_levels else []) or [], 1):
        meaning = ((given or {}).get(row.value) or {}).get("meaning", "")
        if not meaning and q_levels.tier_fields:
            meaning = (q_levels.tier_fields[0].get("defaults") or {}).get(
                row.value, "")
        severities.append({"position": pos, "label": row.label,
                           "meaning": meaning})
    out["severities"] = severities

    # 10.5 · who can stop; 10.6 · look-back; 10.7 · who is told; 10.8.
    stoppers = value("bad.stopper") or []
    out["stoppers"] = [str(r.get("role") or "").strip() for r in stoppers
                       if isinstance(r, dict) and str(r.get("role") or "").strip()]
    out["lookback_yes"] = value("bad.lookback") == "yes"
    far = value("bad.lookback_far")
    out["lookback_period"] = _lower_first(label_of("bad.lookback_far", far)) \
        if far else ""
    delegated = value("org.delegated") == "yes"
    told = []
    for party in listed("bad.tell"):
        if party == "none" or (party == "federal" and not delegated):
            continue
        fn = _TOLD_FUNCTION.get(party)
        if fn and functions.get(fn) == "none":
            continue
        told.append(label_of("bad.tell", party))
    out["must_tell"] = told
    out["writes_up"] = str(value("bad.writeup") or "").strip()

    # 9.6 · what happens when it is not delivering.
    out["failing_words"] = _lower_first(label_of("watch.failing",
                                                 value("watch.failing"))) \
        if value("watch.failing") else ""

    # 1.1 · examples, and 2.5 · their own project, which replaces them.
    kind = value("org.kind")
    out["example"] = _EXAMPLES.get(kind, "")
    return out


#: 8A · placeholders by organisation type. Their own project replaces these
#: where they described one.
_EXAMPLES = {
    "state": "Approved the permit-triage pilot for ninety days",
    "federal": "Approved the grant-review assistant for one funding cycle",
    "district": "Turned down the work-order assistant until the vendor "
                "answers on data",
    "school": "Approved the enrollment forecasting tool at the routine level",
    "city": "Sent the service-call summarizer back for a fallback in writing",
    "county": "Approved the assessment review tool for one quarter",
    "regional": "Sent the grant-application screen back for a fallback",
    "tribal": "Approved the member-services assistant for a pilot",
}


def _next_look(adopted_on: str, review: str) -> str:
    years = _REVIEW_YEARS.get(review)
    if not (years and adopted_on):
        return ""
    try:
        year, rest = int(adopted_on[:4]), adopted_on[4:10]
        return f"{year + years}{rest}"
    except ValueError:
        return ""


def surface(*, answers: dict[str, Any] | None,
            projects: list[dict[str, Any]] | None = None,
            incidents: list[dict[str, Any]] | None = None,
            adopted: dict[str, Any] | None = None,
            versions_list: list[str] | None = None) -> dict[str, Any]:
    """The whole Oversight screen, read once."""
    inputs = framework_inputs(answers)
    rows = all_decisions()
    held = conditions()
    projects = [p for p in (projects or []) if p.get("ref")]
    by_ref = {p["ref"]: p for p in projects}
    shape = inputs["shape"]
    today = clock.today_str()

    # The adoption row the organisation recorded, if it did.
    adoption = next((r for r in sorted(rows, key=lambda r: r.get(
        "decided_on") or "") if r.get("kind") == KIND_FRAMEWORK
        and r.get("framework_what") == FRAMEWORK_WHAT[0]), None)
    adopted = adopted or {}
    adopted_on = str((adoption or {}).get("decided_on") or
                     adopted.get("adopted_on") or "")[:10]
    in_effect = str((adoption or {}).get("effective_on") or "")[:10]
    authority = str((adoption or {}).get("adopted_by_title") or "").strip()
    next_look = _next_look(adopted_on, inputs["review"])
    line = adoption_line(
        adopted_on=adopted_on, authority=authority,
        version=str(adopted.get("number") or ""), in_effect=in_effect,
        cadence=inputs["review_words"] or "when you decide",
        next_look=next_look, signed_copy=False,
        review_passed=bool(next_look and next_look < today),
        gap_owner=inputs["tiebreaker"] or "whoever decides")
    effective = in_effect or adopted_on

    # Hats worn by each person, as the rows record them.
    hats: dict[str, list[str]] = {}
    for r in rows:
        who = str(r.get("recorded_by") or "").strip()
        worn = r.get("hat_worn") or r.get("hat")
        if who and worn:
            hats.setdefault(who, []).append(worn)

    count = counters(rows, held_conditions=held, hats=hats)
    in_use = {p["ref"] for p in projects if p.get("in_use") == spine.IN_USE_YES}
    raised = findings(rows=rows, cadence=inputs["cadence"],
                      tiebreaker=inputs["tiebreaker"],
                      stop_authority=", ".join(inputs["stoppers"]),
                      in_use=len(in_use), in_use_records=in_use)

    approving = (APPROVED, APPROVED_WITH)
    lowest = (inputs["levels"] or [""])[0]
    for r in rows:
        ref = r.get("ref")
        before = bool(effective and r.get("decided_on") and
                      r["decided_on"] < effective) or not effective
        # Before the framework took effect there is nothing to contradict.
        if before:
            continue
        kind = r.get("kind") or KIND_TOOL
        if kind == KIND_TOOL and r.get("outcome") in approving:
            asked_ = set(r.get("consulted") or [])
            for party in inputs["must_consult"]:
                if party not in asked_:
                    raised.append({
                        "id": "finding.consulted_missing", "entry": ref,
                        "says": f"You said {_lower_first(party)} has to be "
                                f"asked before approval. Nothing here records "
                                f"that."})
            # 3.5 — computable only where their delegation can be read
            # against the record: nothing moves without them, or only the
            # lowest level does.
            if (r.get("hat_worn") or r.get("hat")) == "operator":
                delegation = inputs["delegation"]
                level = (by_ref.get(r.get("about")) or {}).get("level", "")
                if "nothing" in delegation or not delegation or (
                        delegation == ["lowest_risk"] and level
                        and level != lowest):
                    raised.append({
                        "id": "finding.oversight.above_delegation",
                        "entry": ref,
                        "says": (f"{inputs['readbacks']['delegation'] or 'You have not said what the User may approve.'} "
                                 f"This one was approved in the User hat"
                                 f"{f' at {level}' if level else ''}.")})
        if kind == KIND_FRAMEWORK and r.get("framework_what") in CHANGES \
                and r.get("owed") in ("", "Not yet", None):
            if inputs["amend"] == "same":
                raised.append({
                    "id": "finding.oversight.amendment_unapproved",
                    "entry": ref,
                    "says": "This change to your framework is recorded as "
                            "proposed. You said the same authority that "
                            "adopted it approves changes. No approval is "
                            "recorded."})
            elif inputs["amend"] == "group_notice":
                raised.append({
                    "id": "finding.oversight.amendment_unapproved",
                    "entry": ref,
                    "says": "This change to your framework is recorded as "
                            "proposed. You said the adopting authority is "
                            "told when it changes. No notice is recorded."})
        if kind == KIND_WENT_WRONG:
            told_ = {t.get("party") for t in (r.get("told") or [])
                     if isinstance(t, dict)}
            for party in inputs["must_tell"]:
                if party not in told_:
                    raised.append({
                        "id": "finding.oversight.notify_not_recorded",
                        "entry": ref,
                        "says": f"You said {_lower_first(party)} has to be "
                                f"told when something like this happens. "
                                f"Nothing here records that."})
            pos = int(r.get("severity_position") or 0)
            if inputs["lookback_yes"] and pos in LOOKBACK_LEVELS and \
                    not r.get("lookback"):
                raised.append({
                    "id": "finding.oversight.lookback_not_decided",
                    "entry": ref,
                    "says": f"You said you go back "
                            f"{inputs['lookback_period'] or 'over earlier work'} "
                            f"after a serious problem. This decision does "
                            f"not say whether that was done."})

    # 3.7 — their cadence, and something waiting.
    days = CADENCE_DAYS.get(inputs["cadence"])
    decided = sorted(r["decided_on"] for r in rows if r.get("decided_on")
                     and r.get("outcome"))
    if days and count["asked_not_decided"] and decided:
        from datetime import date
        try:
            gone = (date.fromisoformat(today) -
                    date.fromisoformat(decided[-1])).days
        except ValueError:
            gone = 0
        if gone > days:
            raised.append({
                "id": "finding.oversight.cadence_missed", "entry": "",
                "says": f"You said {inputs['cadence_words']}. The last "
                        f"decision recorded here was {decided[-1]}, and "
                        f"{count['asked_not_decided']} are waiting."})
    # 3.3 — a condition with nobody named.
    for c in held:
        if not c.get("closed") and not str(c.get("owner") or "").strip():
            raised.append({"id": "finding.gap_no_owner",
                           "entry": c.get("decision", ""),
                           "says": spine.BY_FINDING["finding.gap_no_owner"].says})

    # The rows as the list renders them.
    listed = []
    for r in rows:
        mine = [c for c in held if c.get("decision") == r["ref"]]
        open_ = [c for c in mine if not c.get("closed")]
        past = [c for c in open_ if str(c.get("by") or "") and
                str(c["by"]) < today]
        about = r.get("about") or ""
        listed.append({
            **r,
            "about_shown": ("The framework itself" if about == "framework"
                            else "How candidates are weighed"
                            if about == "weights"
                            else (f"{about} · {by_ref[about]['name']}"
                                  if about in by_ref else
                                  about or "Not written up yet")),
            "gate_shown": (spine.BY_GATE[r["gate"]].name
                           if r.get("gate") in spine.BY_GATE
                           else "Standing decision"),
            "outcome_shown": outcome_label(r.get("outcome") or "", shape),
            "date_shown": (
                (f"Decided {r['decided_on']}. Recorded "
                 f"{clock.local_date(str(r.get('recorded_at') or ''))}."
                 if r.get("decided_on") and clock.local_date(str(r.get("recorded_at") or ""))
                 != r["decided_on"] else r.get("decided_on") or "")
                or "No date recorded"),
            "before_framework": bool(r.get("decided_on") and effective and
                                     r["decided_on"] < effective)
            or (bool(r.get("decided_on")) and not effective),
            "conditions_shown": ("None" if not mine else
                                 f"{len(open_)} open"
                                 + (f", {len(past)} past its date" if past
                                    else "")),
            "kind_shown": KIND_NAMES.get(r.get("kind") or KIND_TOOL, ""),
        })

    cond_rows = []
    per_decision: dict[str, int] = {}
    what_of = {r["ref"]: r.get("what", "") for r in rows}
    about_of = {r["ref"]: r.get("about", "") for r in rows}
    gate_of = {r["ref"]: r.get("gate", "") for r in rows}
    for c in held:
        d = c.get("decision", "")
        idx = per_decision.get(d, 0)
        per_decision[d] = idx + 1
        by = str(c.get("by") or "")
        closed = c.get("closed") or {}
        cond_rows.append({
            "decision": d, "index": idx, "what": c.get("what", ""),
            "owner": c.get("owner", "") or "Nobody named",
            "by_shown": by or "No date set",
            "state": (f"Closed {closed.get('on', '')} by {closed.get('by', '')}"
                      if closed else "Past its date" if by and by < today
                      else "Open"),
            "from": what_of.get(d, ""),
            "about": about_of.get(d, ""),
            "gate_shown": (spine.BY_GATE[gate_of.get(d)].name
                           if gate_of.get(d) in spine.BY_GATE
                           else "Standing decision"),
            "closed": bool(closed),
        })

    return {
        "adoption_line": line,
        "counters": count,
        "raised": raised,
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "standing_watch": standing_watch(held, cadence=inputs["cadence"]),
        "when_it_goes_wrong": when_it_goes_wrong(answers),
        "decisions": listed,
        "conditions": cond_rows,
        "empty_state": (
            "Nothing recorded yet. You said one person decides here. Start "
            "with the last thing that person said yes to, even if it was said "
            "out loud and never written down; writing it down now is the "
            "point." if shape == ONE_PERSON and inputs["shape_answered"]
            else "Nothing recorded yet. Start with the decision that has "
            "already happened: whoever adopted this framework, and the day "
            "they did it. Every other decision on this list points back to "
            "that one." if adopted_on else
            "Your framework is not finished, and you can still record "
            "decisions here. Each one will be marked as decided before the "
            "framework took effect, which is honest and is how most "
            "organizations actually start."),
        "before_framework_label": DECIDED_BEFORE_FRAMEWORK,
        "inputs": inputs,
        "shape": shape,
        "options": {
            "kinds": [{"value": k, "name": n, "says": s} for k, n, s in KINDS],
            "outcomes": [{"value": o, "label": outcome_label(o, shape)}
                         for o in OUTCOMES],
            "how_decided": how_decided_options(shape, inputs["body_named"],
                                               inputs["tiebreaker"]),
            "framework_what": list(FRAMEWORK_WHAT), "owed": list(OWED),
            "stopped": list(STOPPED_ANSWERS),
            "lookback": list(LOOKBACK_ANSWERS),
            "standing_which": list(STANDING_WHICH),
            "standing_changes": list(STANDING_CHANGES),
            "weights_what": list(WEIGHTS_WHAT),
            "gates": [{"id": g.id, "name": g.name} for g in spine.GATES],
            "versions": list(versions_list or []),
        },
        "projects": [{"ref": p["ref"], "name": p.get("name", ""),
                      "gate": p.get("gate", ""), "level": p.get("level", "")}
                     for p in projects],
        "incidents": [{"ref": i.get("ref"), "what": (i.get("what_happened")
                                                     or i.get("tool") or "")[:120]}
                      for i in (incidents or [])],
        "weights": weights(),
        "unweighted": UNWEIGHTED,
        "scoring_line": SCORING_LINE,
        "labels": labels(),
        "labels_on": bool(_read().get("labels_on")),
        "copy": {
            "only_what": ("Only the line saying what was decided is required. "
                          "Everything else can be filled in later, and a "
                          "half-recorded decision beats a decision nobody "
                          "wrote down. A log that refuses a row until every "
                          "box is complete is one nobody keeps."),
            "watch_cannot": WATCH_CANNOT,
            "same_person": ("You are approving your own proposal. In an "
                            "organization this size that is ordinary, and it "
                            "will be recorded that way."),
            "scope": ("A record of decisions, not a meeting system. No "
                      "agendas, no invitations, no attendance tracking, no "
                      "votes counted, no calendar, no reminders sent to "
                      "anybody. Nothing here schedules a meeting, and nothing "
                      "here knows whether one happened. The event that went "
                      "wrong belongs in Integrity; what you decided about it "
                      "belongs here. The move a decision causes belongs to "
                      "the project; the stamp belongs to the audit trail."),
            "labels_says": ("These are your labels and this application does "
                            "not interpret them. It records which one you "
                            "chose and shows it wherever this holding "
                            "appears. Nothing here will tell you that a label "
                            "is wrong, because nothing here knows what your "
                            "labels mean."),
        },
    }


def set_labels_on(on: bool, actor: Any) -> dict[str, Any]:
    """§7 · turning the labels block on or off. A setting, not a decision:
    it writes no row on the list and needs nobody's approval."""
    with _LOCK:
        held = _read()
        held["labels_on"] = bool(on)
        _write(held)
    _record("event.labels_setting", actor, {"on": bool(on)})
    return {"ok": True, "labels_on": bool(on)}


#: The move each outcome proposes, written against the stored value. Projects
#: commits it, or refuses — and a refusal is shown verbatim while the decision
#: row stays, because the decision happened whether or not the move did.
def proposed_move(outcome: str) -> str:
    return {APPROVED: "forward", APPROVED_WITH: "forward",
            TURNED_DOWN: spine.TURNED_DOWN, STOPPED: spine.PAUSED,
            RETIRED: spine.SUNSET}.get(outcome, "")
