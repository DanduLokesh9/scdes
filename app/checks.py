"""Integrity — does it work, and is it still working.

**One entry per check or per incident** — one occasion when somebody looked,
or one occasion when it went wrong. This surface owns `gate.test` and
`gate.measure`.

Integrity is where somebody writes down that they looked.

**Why checks and incidents share one register.** The two shapes sit close
enough together that keeping them in one place is worth more than the
tidiness of splitting them. An incident is very often what triggers the next
check, and the look-back after an incident is itself a check. Filing them
separately puts the answer on a different screen from the question.

**Why the unit is an occasion and not a tool.** Registry counts tools and
Projects counts projects. This counts occasions of looking, because the
useful fact is when anybody last looked and what they found. A register with
one row per tool tells you only that the tool exists. This surface exists to
be able to say that nobody has looked in eighteen months.

**Why it owns two gates.** The first look at a tool, before it goes live,
and the fifth annual look four years later are the same document at
different times, measured against the same baseline and the same claim.
Putting the first check on one surface and every check after it on another
would file drift away from the baseline it drifted from.

Named `checks` because `app/integrity.py` is taken by something else — the
corpus document checker, which reads an adopted framework for internal
consistency. Different job, same word.

`app/oversight.py` holds the older SCDES incident response: Levels 1 to 3,
suspend, root-cause, look-back, resume. Under this specification incidents
belong here, and section 11 below supersedes it. That module stays in place
until the Integrity screens are built, because it still backs the running
product.
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

FILENAME = "checks.json"
_LOCK = threading.Lock()

CHECK = "check"
INCIDENT = "incident"


# ===========================================================================
# 2A · What this surface reads, and what it never writes
# ===========================================================================

#: Everything here belongs to somebody else. This surface writes checks and
#: incidents, and nothing else in the application.
READS_ONLY = (
    "the baseline and the data grounds, written at Procure and held on the "
    "project",
    "the scrutiny level and its interval, from the adopted framework",
    "the version records, held on the project",
    "the agreement terms about notice and about a testing environment, held "
    "on the vendor entry",
    "the holdings a check was run on, held on Data",
)

NEVER_WRITES = (
    "the baseline — that is written at Procure, on the project",
    "the version record — Projects opens it and Projects retires it",
    "the scrutiny level — a check may propose a lift; Projects commits it",
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return clock.today_str()


def _file():
    from app import tenant
    from app.audit import CORPUS
    return tenant.scoped(CORPUS / "config" / FILENAME)


def _read() -> dict[str, Any]:
    blank: dict[str, Any] = {"entries": {}, "stopping_rule": {}}
    path = _file()
    if not path.is_file():
        return blank
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return blank
    if not isinstance(held, dict):
        return blank
    held.setdefault("entries", {})
    held.setdefault("stopping_rule", {})
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _log(action: str, actor: Any, detail: dict[str, Any]) -> None:
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "unknown",
            role=getattr(getattr(actor, "role", None), "value", "")
            or "system",
            action=action, target="Integrity", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]})
    except Exception:                                         # noqa: BLE001
        pass


def _ref(prefix: str, existing: set[str]) -> str:
    for _ in range(64):
        ref = prefix + "".join(
            secrets.choice("23456789BCDFGHJKMNPQRSTVWXYZ") for _ in range(6))
        if ref not in existing:
            return ref
    return prefix + secrets.token_hex(5).upper()


def _days(earlier: str, later: str) -> int | None:
    """Whole days between two dates. `None` where either is unreadable."""
    try:
        one = datetime.fromisoformat(str(earlier)[:19])
        two = datetime.fromisoformat(str(later)[:19])
    except (ValueError, TypeError):
        return None
    return (two.replace(tzinfo=None) - one.replace(tzinfo=None)).days


# ===========================================================================
# 8.2 · Is this the first look, or one of the regular ones?
# ===========================================================================

FIRST_LOOK = "The first look, before it goes live"
REGULAR_LOOK = "One of the regular looks"
AFTER_A_CHANGE = "A look after something changed"
AFTER_AN_INCIDENT = "A look after an incident"
OCCASION_UNSURE = "We are not sure"

OCCASIONS = (FIRST_LOOK, REGULAR_LOOK, AFTER_A_CHANGE, AFTER_AN_INCIDENT,
             OCCASION_UNSURE)


def gate_for(occasion: str) -> str:
    """The first look attaches to Test; every look after it attaches to
    Measure. A look at a version the vendor has changed attaches to Test
    again — that is the loop."""
    if occasion in (FIRST_LOOK, AFTER_A_CHANGE):
        return spine.TEST
    return spine.MEASURE


# ===========================================================================
# 8.5b · Where was it tried?
# ===========================================================================

WHERE_STAGING = "A staging or testing environment"
WHERE_SANDBOX = "A sandbox, or a copy of the real thing"
WHERE_PRODUCTION = "In production, on real work"
WHERE_NONE = "We have no staging or testing environment"
WHERE_UNAVOIDABLE = "It cannot be tried without touching a real decision"
WHERE_UNSURE = "We are not sure"

WHERES = (WHERE_STAGING, WHERE_SANDBOX, WHERE_PRODUCTION, WHERE_NONE,
          WHERE_UNAVOIDABLE, WHERE_UNSURE)

#: The last two open a gap record with a role owner and a date.
WHERE_OPENS_A_GAP = (WHERE_UNAVOIDABLE, WHERE_UNSURE)

#: This one proposes a lift in the scrutiny level rather than waiving the
#: gate. Projects commits the change.
WHERE_PROPOSES_A_LIFT = WHERE_UNAVOIDABLE

#: The Where column. Text, never an icon.
WHERE_COLUMN = {
    WHERE_STAGING: "Staging",
    WHERE_SANDBOX: "Sandbox",
    WHERE_PRODUCTION: "In production",
    WHERE_NONE: "No staging environment",
    WHERE_UNAVOIDABLE: "Cannot be tried separately",
    WHERE_UNSURE: "Not recorded",
}

NO_STAGING_IS_NOT_A_FAULT = (
    "Somewhere separate from the live system, where a wrong answer reaches "
    "nobody, is the answer worth having. Where there is nowhere like that, "
    "say so — it is a real answer and a common one, and it is a term for "
    "the next agreement rather than a fault in this record.")


# ===========================================================================
# 8.9 · Did it hold up?   ·   8.9a · What happens now?
# ===========================================================================

HELD_UP = "It did what we expected"
HELD_UP_WITH_FIXES = "It did what we expected, with things to fix"
DID_NOT_HOLD_UP = "It did not do what we expected"
COULD_NOT_TELL = "We could not tell from this"
HOLDING_UNSURE = "We are not sure"

VERDICTS = (HELD_UP, HELD_UP_WITH_FIXES, DID_NOT_HOLD_UP, COULD_NOT_TELL,
            HOLDING_UNSURE)

ADJUST_AND_TEST = "Adjust it and test again"
PAUSE_UNTIL_FIXED = "Pause it until it is fixed"
RETIRE_IT = "Retire it"
DECIDE_CASE_BY_CASE = "Decide case by case"
DETERMINATION_UNSURE = "We are not sure"

#: All five are shown and none is disabled. This is the field that decides
#: whether a tool that is not delivering gets paused, and the person writing
#: up the check is frequently not the person who makes that call.
DETERMINATIONS = (ADJUST_AND_TEST, PAUSE_UNTIL_FIXED, RETIRE_IT,
                  DECIDE_CASE_BY_CASE, DETERMINATION_UNSURE)

#: Only two of the five say the tool comes out of service.
#: `finding.determination_not_followed` reads those two and no others, and
#: it closes itself the moment the project is paused or reaches Sunset.
#: There is no grace period; nothing in the framework asked for an interval
#: here, and the application does not invent one.
TAKES_IT_OUT_OF_SERVICE = (PAUSE_UNTIL_FIXED, RETIRE_IT)


# ===========================================================================
# 8.8 · What was not tested, and is therefore not known?
# ===========================================================================

#: The box beside the limits field. Ticking it is the honest answer where
#: nobody wrote the limits down, and it opens a gap record with a role owner
#: and a date.
DID_NOT_WRITE_IT_DOWN = "We did not write that down"

#: 8A · The one refusal on this form, and its exact wording.
#:
#: The refusal keeps the field from being left silently empty, and it does
#: not block the record. The record still moves, the gate still passes with
#: a gap attached, and nothing about the tool is prevented. The application
#: blocks at two gates and on seven obligations, and this is neither.
LIMITS_REQUIRED = (
    "Say what was not tested, or tick the box to say nobody wrote it down. "
    "One of the two is needed before this check can be marked complete.")

LIMITS_GUIDANCE = (
    "Every check has an edge. What material nobody tried it on, what "
    "conditions nobody put it under, what question nobody asked. An account "
    "with no limits is an account claiming everything was covered, and "
    "nobody has ever covered everything. If nobody wrote the limits down, "
    "tick the box; that is a real answer, and it records somebody to go and "
    "ask.")

#: The field has two ways of being unanswered and only one produces a
#: finding. An empty field is not a state a complete check can be in, which
#: is what makes the finding computable: it fires on the ticked box alone.
LIMITS_UNANSWERED_TWO_WAYS = (
    "the ticked box, which says nobody wrote the limits down — this raises "
    "finding.limits_absent",
    "an empty field with the box unticked, which a complete check cannot be "
    "in, so it never becomes a finding",
)


# ===========================================================================
# 8 · The check record
# ===========================================================================

#: Only the project is required, for the reason the built surfaces already
#: give: a register that refuses a row until every box is filled is one
#: nobody finishes.
ONLY_THE_PROJECT = (
    "Only the project is required. A check that says “somebody looked "
    "on Tuesday and here is the one thing they noticed” is worth more "
    "than a blank form waiting for a full evaluation nobody has time to "
    "write.")

DATE_GUIDANCE = "The date it happened, not the date you are typing it in."

WHO_GUIDANCE = ("A title rather than a person's name, so the record still "
                "makes sense after they move on. A name can sit beside it.")

FOUND_GUIDANCE = (
    "In plain words. Numbers where there are numbers, and no numbers where "
    "there are not; an invented percentage is worse than “it got about "
    "a third of them wrong”.")

#: The security note, carried from the Data surface.
ATTACHMENT_NOTE = ("A spreadsheet, a memo, a screenshot of the run. Nothing "
                   "here is read by the app; it is stored so the next "
                   "person can see what you saw.")
ATTACHMENT_SECURITY = ("The kind, never the credential. Nothing on this "
                       "screen should be a secret.")

CONDITION_GUIDANCE = ("A condition lets the record move while something is "
                      "still outstanding. It needs an owner and a date, or "
                      "it is a wish.")

COMPLETE = "Complete"
STILL_BEING_WRITTEN = "Still being written"

#: 8.4 · The one-tap chip for somebody from outside the organisation.
OUTSIDE = "Somebody outside the organization"
WHO_UNSURE = "We are not sure"

#: 8.10 · Was it measured against the baseline?
BASELINE_YES = "Yes — against the baseline on the project"
BASELINE_NONE = "There is no baseline on this project"
BASELINE_NOT_RETAKEN = "The measurement could not be retaken this time"
BASELINE_UNSURE = "We are not sure"
BASELINE_ANSWERS = (BASELINE_YES, BASELINE_NONE, BASELINE_NOT_RETAKEN,
                    BASELINE_UNSURE)

#: 8.12 · Was the manual way tried this time?
MANUAL_TRIED = "Yes, somebody did the work without it"
MANUAL_NOT_THIS_TIME = "No, not this time"
MANUAL_NONE_WRITTEN = "There is no written manual way for this one"
MANUAL_UNSURE = "We are not sure"
MANUAL_ANSWERS = (MANUAL_TRIED, MANUAL_NOT_THIS_TIME, MANUAL_NONE_WRITTEN,
                  MANUAL_UNSURE)

#: 8.13 · Accessibility.
ACCESS_HOLDS = "Checked, and it holds up"
ACCESS_FIXES = "Checked, and there are things to fix"
ACCESS_NOT_CHECKED = "Not checked this time"
ACCESS_NOT_PUBLIC = "This one is not public-facing"
ACCESS_UNSURE = "We are not sure"
ACCESS_ANSWERS = (ACCESS_HOLDS, ACCESS_FIXES, ACCESS_NOT_CHECKED,
                  ACCESS_NOT_PUBLIC, ACCESS_UNSURE)
ACCESS_GUIDANCE = (
    "The standard is WCAG 2.1 Level AA, which is what the ADA Title II web "
    "rule points at for state and local government. Where the tool came from "
    "a vendor, a conformance report on the Vendors entry is evidence rather "
    "than a substitute for somebody trying it.")

#: 8.14 · the written rule, and 8.14c · was it met on this check?
RULE_ANSWERS = ("Yes", "No", "We are not sure")
RULE_MET_ANSWERS = ("Yes", "No", "Not applicable to this one",
                    "We are not sure")

#: 8.2a · Does your own rule send this back for a fresh first look?
BACK_TO_FIRST_LOOK = ("Yes, back to the first look",
                      "No, this is one of the regular looks",
                      "We are not sure")


def record_check(*, project: str, actor: Any, occasion: str = "",
                 version: str = "", back_to_first_look: str = "",
                 at: str = "", who: str = "", who_name: str = "",
                 outside_organisation: str = "", tried_on: str = "",
                 holdings: list[str] | None = None, where: str = "",
                 period: str = "", found: str = "", limits: str = "",
                 limits_not_written: bool = False, verdict: str = "",
                 determination: str = "", against_baseline: str = "",
                 baseline_why_not: str = "",
                 watched: dict[str, str] | None = None,
                 manual_way: str = "", accessibility: str = "",
                 accessibility_fixes: str = "", stopping_rule_met: str = "",
                 segments: list[dict[str, str]] | None = None,
                 attachments: list[str] | None = None,
                 conditions: list[dict[str, str]] | None = None,
                 gaps: list[str] | None = None,
                 corrects: str = "",
                 complete: bool = False) -> dict[str, Any]:
    """One occasion on which somebody looked.

    `complete` is the difference between a draft and a record. A check
    marked still being written raises nothing and blocks nothing; marking it
    complete is what makes it evidence for a passage.
    """
    if not str(project or "").strip():
        return {"ok": False, "error": "Say which project this is about."}
    if complete and not str(limits or "").strip() and not limits_not_written:
        return {"ok": False, "error": LIMITS_REQUIRED, "field": "8.8"}

    with _LOCK:
        held = _read()
        ref = _ref("CK-", set(held["entries"]))
        row = {
            "ref": ref,
            "kind": CHECK,
            "project": project,
            "occasion": occasion,
            "gate": gate_for(occasion),
            "version": version,
            "back_to_first_look": back_to_first_look,
            # Recording late is ordinary. Both dates are kept rather than
            # flattened into one.
            "at": at or _today(),
            "written_down": _today(),
            "who": who,
            "who_name": str(who_name or "").strip(),
            "outside_organisation": str(outside_organisation or "").strip(),
            "tried_on": str(tried_on or "").strip(),
            "holdings": list(holdings or []),
            "where": where,
            "period": str(period or "").strip(),
            "found": str(found or "").strip(),
            "limits": str(limits or "").strip(),
            "limits_not_written": bool(limits_not_written),
            "verdict": verdict,
            "determination": determination,
            "against_baseline": against_baseline,
            "baseline_why_not": str(baseline_why_not or "").strip(),
            "watched": dict(watched or {}),
            "manual_way": manual_way,
            "accessibility": accessibility,
            "accessibility_fixes": str(accessibility_fixes or "").strip(),
            "stopping_rule_met": stopping_rule_met,
            # The application computes nothing from the segments. It holds
            # what a person wrote.
            "segments": list(segments or []),
            "attachments": list(attachments or []),
            "conditions": list(conditions or []),
            "gaps": list(gaps or []),
            # 13 · a correction is a new check that names the one it
            # corrects, and both stay on the list.
            "corrects": corrects if corrects in held["entries"] else "",
            "complete": bool(complete),
            # Who may edit it while it is still being written.
            "author": str(getattr(actor, "user_id", "") or ""),
            "recorded_at": _now(),
        }
        held["entries"][ref] = row
        _write(held)

    _log("event.check_recorded", actor,
         {"check": ref, "project": project, "gate": row["gate"],
          "complete": bool(complete)})
    return {"ok": True, "check": row, "says": after_a_check(row)}


def mark_complete(ref: str, *, actor: Any) -> dict[str, Any]:
    """The one state change the limits field can refuse."""
    with _LOCK:
        held = _read()
        row = held["entries"].get(ref)
        if not row or row.get("kind") != CHECK:
            return {"ok": False, "error": "No such check."}
        if not row.get("limits") and not row.get("limits_not_written"):
            return {"ok": False, "error": LIMITS_REQUIRED, "field": "8.8"}
        row["complete"] = True
        held["entries"][ref] = row
        _write(held)
    _log("event.check_completed", actor, {"check": ref})
    return {"ok": True, "check": row, "says": after_a_check(row)}


# ---------------------------------------------------------------------------
# 8.14 · Do you have a written rule for when testing is enough?
# ---------------------------------------------------------------------------

#: Nothing in Module One asks this, so this control is where the fact is
#: captured. The answer is recorded against the organisation rather than
#: against a check, and every later check opens the block already answered
#: and editable. Where the answer is no, its absence is never shown as a
#: defect.
STOPPING_RULE_GUIDANCE = (
    "Nothing in your framework asked whether you have one, so it is asked "
    "here once. The app holds your rule and records whether somebody said "
    "it was met. It does not calculate anything, and it does not have a "
    "rule of its own.")


def set_stopping_rule(*, actor: Any, have_one: str, name: str = "",
                      says: str = "") -> dict[str, Any]:
    with _LOCK:
        held = _read()
        held["stopping_rule"] = {
            "have_one": have_one,
            "name": str(name or "").strip(),
            "says": str(says or "").strip(),
            "recorded_at": _now(),
        }
        _write(held)
    _log("event.stopping_rule_recorded", actor, {"have_one": have_one})
    return {"ok": True, "stopping_rule": held["stopping_rule"]}


def stopping_rule() -> dict[str, Any]:
    return dict(_read().get("stopping_rule") or {})


def has_stopping_rule(rule: dict[str, Any] | None = None) -> bool:
    rule = stopping_rule() if rule is None else rule
    return str(rule.get("have_one") or "").strip().lower().startswith("yes")


# ===========================================================================
# 11 · The incident record
# ===========================================================================

ANYONE_CAN_WRITE_IT = (
    "Anyone can write this down, including somebody with no login and no "
    "role here. Only one thing is required: either which tool, or a "
    "sentence about what happened.")

VISIBLE_TO_EVERYONE = (
    "This record is visible to everyone in your organization and, in most "
    "places, to anyone who asks for it. Leave your name off if you would "
    "rather; the report still counts.")

WHAT_HAPPENED_GUIDANCE = (
    "In your own words. “It gave the wrong answer and I do not know "
    "why” is a complete report.")

NOTICED_GUIDANCE = ("These are often different, and the gap between them is "
                    "what tells somebody how far back to look.")

TOUCHED_A_PERSON = ("Yes", "No", "Not yet, but it could have", "Not sure")

STOPPED_YES = "Yes, stopped"
STOPPED_NO = "No, still running"
STOPPED_UNSURE = "Not sure"

#: 11.10 · Has anyone gone back over earlier work?
LOOKBACK_NOT_YET = "Not yet"
LOOKBACK_BACK_TO = "Yes, back to a date"
LOOKBACK_THEIR_SCOPE = "Yes, as far as you said"
LOOKBACK_NOT_NEEDED = "Not needed for this one"
LOOKBACK_UNSURE_HERE = "We are not sure"

LOOKBACK_ANSWERS = (LOOKBACK_NOT_YET, LOOKBACK_BACK_TO, LOOKBACK_THEIR_SCOPE,
                    LOOKBACK_NOT_NEEDED, LOOKBACK_UNSURE_HERE)

#: `Not needed for this one` is the writer's own judgement about this
#: incident. The application holds no mapping from a severity level to a
#: look-back, because nothing in the framework asked for one.
NO_SEVERITY_MAPPING = (
    "Severity is not read here. Nothing in your framework maps a level to a "
    "look-back, and a mapping would be one the app invented.")

INCIDENT_OPEN = "Still open"
INCIDENT_CLOSED = "Closed"

WRITE_UP_GUIDANCE = (
    "The write-up itself can live wherever you said it lives. This records "
    "who has it and where, so somebody looking two years from now can find "
    "it.")


def report_incident(*, actor: Any, project: str = "", tool: str = "",
                    what_were_you_using: str = "", what_happened: str = "",
                    at: str = "", first_noticed: str = "",
                    affected: str = "", touched_a_person: str = "",
                    severity: str = "", stopped: str = "",
                    stopped_at: str = "", stopped_by: str = "",
                    told: dict[str, str] | None = None, lookback: str = "",
                    lookback_back_to: str = "", cause: str = "",
                    what_was_done: str = "", written_up_by: str = "",
                    written_up_where: str = "", closed: str = INCIDENT_OPEN,
                    closed_at: str = "", closed_by: str = "",
                    attachments: list[str] | None = None,
                    gaps: list[str] | None = None,
                    signed_in: bool = True) -> dict[str, Any]:
    """One occasion on which it did not work.

    Anybody may write one, including somebody with no login and no role on
    this surface. A reporting route that depends on holding a hat is a
    reporting route people go around.
    """
    if not str(tool or "").strip() and not str(what_happened or "").strip():
        return {"ok": False,
                "error": "Either say which tool, or write a sentence about "
                         "what happened."}

    with _LOCK:
        held = _read()
        ref = _ref("IN-", set(held["entries"]))
        row = {
            "ref": ref,
            "kind": INCIDENT,
            "project": project,
            "tool": str(tool or "").strip(),
            "what_were_you_using": str(what_were_you_using or "").strip(),
            "what_happened": str(what_happened or "").strip(),
            # Empty where the reporter was not sure. Filling in today would
            # record a date nobody gave; the write-down date is kept below.
            "at": str(at or "").strip(),
            # Often a different date, and the gap between them is what
            # tells somebody how far back to look.
            "first_noticed": first_noticed,
            "written_down": _today(),
            # A name is optional. The report still counts without one.
            "by": str(getattr(actor, "name", "") or ""),
            "signed_in": bool(signed_in),
            "affected": str(affected or "").strip(),
            "touched_a_person": touched_a_person,
            # The organisation's own level, in their words. Never ours.
            "severity": severity,
            "stopped": stopped,
            "stopped_at": stopped_at,
            "stopped_by": stopped_by,
            "told": dict(told or {}),
            # Empty is a real state: an incident nobody has decided about
            # yet is a decision waiting, never something they failed to do.
            "lookback": lookback,
            "lookback_back_to": lookback_back_to,
            "cause": str(cause or "").strip(),
            "what_was_done": str(what_was_done or "").strip(),
            "written_up_by": written_up_by,
            "written_up_where": str(written_up_where or "").strip(),
            "closed": closed,
            "closed_at": closed_at,
            "closed_by": closed_by,
            "attachments": list(attachments or []),
            "gaps": list(gaps or []),
            "author": str(getattr(actor, "user_id", "") or ""),
            "reopened": [],
            "recorded_at": _now(),
        }
        held["entries"][ref] = row
        _write(held)

    _log("event.incident_reported", actor,
         {"incident": ref, "project": project, "signed_in": bool(signed_in)})
    return {"ok": True, "incident": row}


def stop_route(route: str = "", *, signed_in: bool = True,
               organisation: str = "") -> str:
    """11.8 · Where a problem goes, in the organization's own words.

    Internal role titles are not read out here. The route is the thing the
    organization wrote down for a person to use, and it is the only thing
    shown. The public page speaks in the third person.
    """
    if not route:
        # No route is ever invented. The recorded gap renders instead.
        return ("Nobody has written down where a problem goes. [Role] is "
                "recorded to decide, by [date].")
    if signed_in:
        return f"If it needs stopping now, you said that goes to {route}."
    who = organisation or "Your organization"
    return (f"If it needs stopping now, {who} recorded that it goes to "
            f"{route}.")


# ===========================================================================
# 13 · Editing, reopening, and stopping
# ===========================================================================

#: The fields a person may change on a record still being written. The
#: identifiers, the dates the application wrote and who wrote it never move.
_FIXED = {"ref", "kind", "written_down", "author", "recorded_at", "complete",
          "reopened", "corrects", "gate"}

NOT_EDITABLE_COMPLETE = ("A check marked complete is not editable by anyone. "
                         "A correction is a new check that names the one it "
                         "corrects, and both stay on the list.")
NOT_EDITABLE_CLOSED = ("A closed incident reopens rather than being edited. "
                       "Reopen it, then change it.")
NOT_YOURS_TO_EDIT = ("While it is still being written, this can be changed "
                     "by whoever wrote it and by whoever decides.")


def edit_entry(ref: str, fields: dict[str, Any], *, actor: Any,
               decider: bool = False) -> dict[str, Any]:
    """13 · A check or an incident submitted but not marked complete may be
    edited by its author and by the Decision-maker."""
    with _LOCK:
        held = _read()
        row = held["entries"].get(ref)
        if not row:
            return {"ok": False, "error": "No such record."}
        if row.get("kind") == CHECK and row.get("complete"):
            return {"ok": False, "error": NOT_EDITABLE_COMPLETE}
        if row.get("kind") == INCIDENT and row.get("closed") == INCIDENT_CLOSED:
            return {"ok": False, "error": NOT_EDITABLE_CLOSED}
        author = row.get("author") or ""
        if not decider and author != str(getattr(actor, "user_id", "") or ""):
            return {"ok": False, "error": NOT_YOURS_TO_EDIT}
        changed = []
        for key, value in (fields or {}).items():
            if key in _FIXED or key not in row:
                continue
            if row.get(key) != value:
                row[key] = value
                changed.append(key)
        if "occasion" in changed:
            row["gate"] = gate_for(row["occasion"])
        held["entries"][ref] = row
        _write(held)
    _log("event.field_changed", actor, {"entry": ref, "fields": sorted(changed)})
    return {"ok": True, "entry": row, "changed": changed}


def reopen_incident(ref: str, *, actor: Any, why: str = "") -> dict[str, Any]:
    """An incident that has been closed reopens rather than being edited, and
    the reopening is itself an event on the audit trail. Nothing is ever
    deleted."""
    with _LOCK:
        held = _read()
        row = held["entries"].get(ref)
        if not row or row.get("kind") != INCIDENT:
            return {"ok": False, "error": "No such incident."}
        if row.get("closed") != INCIDENT_CLOSED:
            return {"ok": False, "error": "It is still open."}
        row.setdefault("reopened", []).append({
            "at": _now(), "by": str(getattr(actor, "name", "") or ""),
            "why": str(why or "").strip()[:1000],
            "was_closed_at": row.get("closed_at", ""),
            "was_closed_by": row.get("closed_by", "")})
        row["closed"] = INCIDENT_OPEN
        row["closed_at"] = ""
        row["closed_by"] = ""
        held["entries"][ref] = row
        _write(held)
    _log("event.incident_reopened", actor, {"incident": ref,
                                            "why": str(why or "")[:300]})
    return {"ok": True, "incident": row}


STOPPED_CONFIRMED = ("Stopped. The project is paused and this is on the "
                     "record with your role against it.")


def stop_now(ref: str, *, role: str, actor: Any, stoppers: list[str]
             ) -> dict[str, Any]:
    """11.8 · Stop it now. Offered to a signed-in person who says they hold
    one of the roles the organization named at 10.5. The application reads no
    title to decide that — the person says which role, and the record keeps
    what they said. The project is paused with that role against it."""
    from app import projects, spine as sp
    role = str(role or "").strip()
    if role not in (stoppers or []):
        return {"ok": False, "error": "Stop it now is for the roles your "
                                      "framework named as able to stop a tool "
                                      "without waiting for a meeting."}
    with _LOCK:
        held = _read()
        row = held["entries"].get(ref)
        if not row or row.get("kind") != INCIDENT:
            return {"ok": False, "error": "No such incident."}
        row["stopped"] = STOPPED_YES
        row["stopped_at"] = _now()
        row["stopped_by"] = role
        held["entries"][ref] = row
        _write(held)
    _log("event.tool_stopped", actor, {"incident": ref, "role": role,
                                       "project": row.get("project", "")})
    paused = {}
    if row.get("project") and projects.one(row["project"]):
        paused = projects.set_state(row["project"], sp.PAUSED, actor,
                                    paused_by=role)
    return {"ok": True, "incident": row, "says": STOPPED_CONFIRMED,
            "project_paused": bool(paused.get("ok"))}


# ===========================================================================
# 12 · What each form says after submit
# ===========================================================================

#: Neither form thanks anybody, and neither implies anything has been sent
#: to anyone, because nothing has been. There is no notification system on
#: this surface and the copy does not suggest there is one.

def after_a_check(row: dict[str, Any], *, findings_changed: int = 0
                  ) -> list[str]:
    if not row.get("complete"):
        return [f"Added. {row['ref']}.",
                "Marked still being written. It raises nothing and blocks "
                "nothing until you mark it complete."]
    line = "It is evidence for a passage now."
    # Dropped where nothing changed, rather than rendering "0 findings
    # changed".
    if findings_changed:
        line += f" {findings_changed} findings on this surface changed."
    return [f"Added and marked complete. {row['ref']}.", line]


def after_an_incident(row: dict[str, Any], *, route: str = "") -> list[str]:
    line = "It is on the record and on the list."
    if route:
        line += (f" You said a problem here goes to {route}; this form has "
                 f"not told them.")
    return [f"Written down. {row['ref']}.", line]


# ===========================================================================
# Reading the register
# ===========================================================================

def all_entries() -> list[dict[str, Any]]:
    return list(_read()["entries"].values())


def entry(ref: str) -> dict[str, Any] | None:
    return _read()["entries"].get(ref)


def checks(rows: list[dict[str, Any]] | None = None
           ) -> list[dict[str, Any]]:
    rows = all_entries() if rows is None else rows
    return [r for r in rows if r.get("kind") == CHECK]


def incidents(rows: list[dict[str, Any]] | None = None
              ) -> list[dict[str, Any]]:
    rows = all_entries() if rows is None else rows
    return [r for r in rows if r.get("kind") == INCIDENT]


def complete_checks(rows: list[dict[str, Any]] | None = None
                    ) -> list[dict[str, Any]]:
    return [c for c in checks(rows) if c.get("complete")]


def grouped_by_project(rows: list[dict[str, Any]] | None = None
                       ) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in (all_entries() if rows is None else rows):
        grouped.setdefault(row.get("project") or "", []).append(row)
    return grouped


def last_looked(project: str, rows: list[dict[str, Any]] | None = None
                ) -> str:
    """The date of the last complete check on a project, or empty."""
    return max((c.get("at", "") for c in complete_checks(rows)
                if c.get("project") == project), default="")


# ===========================================================================
# 3 · The stat row   ·   3A · The counter that changes shape
# ===========================================================================

#: The framework's four answers about going back over earlier work. A
#: counter that cannot be computed honestly is replaced rather than left to
#: sit at a permanent zero.
LOOKBACK_YES = "yes"
LOOKBACK_NO = "no"
LOOKBACK_CASE_BY_CASE = "case_by_case"
LOOKBACK_UNSURE = "unsure"

LOOKBACK_ANSWER_VALUES = (LOOKBACK_YES, LOOKBACK_NO, LOOKBACK_CASE_BY_CASE,
                          LOOKBACK_UNSURE)

#: The swap is decided once, when the framework is adopted, and the
#: counter's position and label then hold steady — nobody learns to read a
#: stat row that reshuffles between visits.
FIFTH_COUNTER = {
    LOOKBACK_YES: "Look-backs owed",
    LOOKBACK_NO: "Checks with no limits written down",
    LOOKBACK_CASE_BY_CASE: "Look-backs not yet decided",
    LOOKBACK_UNSURE: "Look-backs not yet decided",
}

COUNTER_NAMES = ("Checks recorded", "Looked at this cycle", "Never checked",
                 "Past due for a look")


def swap_announcement(new_label: str) -> str:
    """Announced once in the live region where the framework is amended, so
    that nobody silently finds a different counter where the old one was."""
    return (f"Your framework changed. The last counter on this row now "
            f"reads {new_label}.")


#: Zero is a true reading here rather than an error state.
ZERO_IS_TRUE = ("Zero here means nothing is unchecked because nothing is "
                "recorded yet.")


def counters(rows: list[dict[str, Any]] | None = None, *,
             lookback_answer: str = LOOKBACK_YES,
             intervals: dict[str, int] | None = None,
             projects: dict[str, dict[str, Any]] | None = None,
             today: str = "") -> dict[str, Any]:
    """Five counters, always five, always in this order, phrased so that
    somebody reading them to a board is speaking English.

    `intervals` maps a scrutiny level to the organization's own number of
    days. **A level with no interval set never counts here. The application
    does not invent an interval, ever.**
    """
    rows = all_entries() if rows is None else rows
    intervals = intervals or {}
    projects = projects or {}
    today = today or _today()

    done = complete_checks(rows)
    per_project: dict[str, list[dict[str, Any]]] = {}
    for check in done:
        per_project.setdefault(check.get("project") or "", []).append(check)

    # Never checked: at Test or beyond, *or* already in use. The second
    # condition is the one that matters on a first day — a running tool
    # nobody has ever looked at counts here even though it has not reached
    # Test.
    never = 0
    for ref, project in projects.items():
        if per_project.get(ref):
            continue
        gate = project.get("gate") or ""
        reached = bool(gate) and not spine.before(gate, spine.TEST)
        if reached or project.get("in_use") == spine.IN_USE_YES:
            never += 1

    looked, overdue = 0, 0
    for ref, project in projects.items():
        days = intervals.get(project.get("level") or "")
        if not days:
            continue
        latest = max((c.get("at", "") for c in per_project.get(ref, [])),
                     default="")
        if latest and _inside(latest, today, days):
            looked += 1
        elif project.get("gate") == spine.MEASURE:
            overdue += 1

    return {
        "checks_recorded": len(done),
        "looked_at_this_cycle": looked,
        "never_checked": never,
        "past_due": overdue,
        "fifth": fifth_counter(rows, lookback_answer),
        "zero_is_true": ZERO_IS_TRUE,
    }


def _inside(when: str, today: str, days: int) -> bool:
    gone = _days(when, today)
    return gone is not None and gone <= days


def fifth_counter(rows: list[dict[str, Any]] | None = None,
                  answer: str = LOOKBACK_YES) -> dict[str, Any]:
    rows = all_entries() if rows is None else rows
    label = FIFTH_COUNTER.get(answer, FIFTH_COUNTER[LOOKBACK_YES])
    says = ""

    if answer == LOOKBACK_NO:
        # Their framework says they do not go back, so a look-back counter
        # would sit at a permanent zero. What is worth counting instead is
        # the complete checks that recorded no limits.
        count = sum(1 for c in complete_checks(rows)
                    if c.get("limits_not_written"))
    else:
        # An incident nobody has decided about yet is a decision waiting,
        # and never something they failed to do.
        count = sum(1 for i in incidents(rows) if not has_lookback(i))
        if answer == LOOKBACK_UNSURE:
            says = ("You have not decided whether you go back over earlier "
                    "work.")
        elif answer == LOOKBACK_CASE_BY_CASE:
            says = "You said you decide this case by case."

    return {"label": label, "count": count, "says": says}


def has_lookback(incident: dict[str, Any]) -> bool:
    answer = str(incident.get("lookback") or "").strip()
    return bool(answer) and answer not in (LOOKBACK_NOT_YET,
                                           LOOKBACK_UNSURE_HERE)


# ===========================================================================
# 6.1 · The due watch
# ===========================================================================

NO_INTERVAL_SET = "No interval set at this level"
INSIDE_YOUR_WINDOW = "Looked at within your own window"
PAST_DUE = "Past due"

DUE_WATCH_SAYS = (
    "Worked out overnight from what you said your own interval is at each "
    "level, and the date of the last complete check.")

WORK_OUT_WHAT_IS_DUE = "Work out what is due now"


def due_watch(rows: list[dict[str, Any]] | None = None, *,
              intervals: dict[str, int] | None = None,
              projects: dict[str, dict[str, Any]] | None = None,
              today: str = "") -> dict[str, Any]:
    """Arithmetic on records the organization already has.

    A project at a level with no interval set is excluded from both the
    numerator and the population, and appears on its own line reading
    `No interval set at this level`.
    """
    rows = all_entries() if rows is None else rows
    intervals = intervals or {}
    projects = projects or {}
    today = today or _today()

    watched = inside = past_due = no_interval = 0
    lines: list[dict[str, Any]] = []

    for ref, project in projects.items():
        level = project.get("level") or ""
        days = intervals.get(level)
        latest = last_looked(ref, rows)
        line: dict[str, Any] = {"project": ref, "level": level,
                                "last_looked": latest}

        if not days:
            no_interval += 1
            line["state"] = NO_INTERVAL_SET
            # The application does not invent an interval, ever.
            line["days_over"] = None
        else:
            watched += 1
            gone = _days(latest, today) if latest else None
            if gone is not None and gone <= days:
                inside += 1
                line["state"] = INSIDE_YOUR_WINDOW
                line["days_over"] = 0
            else:
                past_due += 1
                line["state"] = PAST_DUE
                line["days_over"] = (gone - days) if gone is not None else None

        # Whether the number can be got again is a different question, and
        # its answer sits in the data grounds written at Procure. A look
        # coming due is then not also a surprise.
        beside = project.get("baseline_unreachable") or ""
        if beside:
            line["beside_the_date"] = beside
        lines.append(line)

    return {
        "says": DUE_WATCH_SAYS,
        "watched": watched,
        "inside_your_window": inside,
        "past_due": past_due,
        "no_interval_set": no_interval,
        "lines": lines,
        "control": WORK_OUT_WHAT_IS_DUE,
    }


# ===========================================================================
# 6.3 · The change watch
# ===========================================================================

CHANGE_WATCH_SAYS = (
    "Whenever a change is written down against a tool or against its "
    "vendor, every project that names it appears here until somebody "
    "records whether the change mattered. A vendor notification that opened "
    "a version record on a project appears here too, and stays there until "
    "a check is recorded against that version.")

SHOW_ME_UNANSWERED = "Show me the ones nobody has answered"

#: The four things the change watch listens for.
CHANGE_WATCH_LISTENS_FOR = (
    "a change recorded on the Vendors surface",
    "a change recorded on the Registry row for the tool",
    "a version record opened on a project",
    "a check that itself records the vendor changed something",
)


def change_watch(rows: list[dict[str, Any]] | None = None, *,
                 changes: list[dict[str, Any]] | None = None,
                 versions: list[dict[str, Any]] | None = None
                 ) -> dict[str, Any]:
    """`changes` are recorded changes; `versions` are the version records
    held on projects. Both are read, never written, by this surface."""
    rows = all_entries() if rows is None else rows
    changes = list(changes or [])
    versions = list(versions or [])

    answered = sum(1 for c in changes if str(c.get("mattered") or "").strip())
    tools = {c.get("tool") for c in changes if c.get("tool")}

    checked = {c.get("version") for c in complete_checks(rows)
               if c.get("version")}
    live_unchecked = [v for v in versions
                      if v.get("live") and v.get("ref") not in checked]

    return {
        "says": CHANGE_WATCH_SAYS,
        "changes_recorded": len(changes),
        "tools_touched": len(tools),
        "answered": answered,
        "not_yet_answered": len(changes) - answered,
        "live_with_no_check": len(live_unchecked),
        "unchecked_versions": [v.get("ref") for v in live_unchecked],
        "control": SHOW_ME_UNANSWERED,
    }


#: Stated where a person will read it before they trust anything.
WHAT_THE_WATCHES_CANNOT_DO = (
    "They watch the calendar and they watch the change log. They do not "
    "watch the tool. Nothing here reads a tool's output, samples its "
    "answers, or measures whether it is still as accurate as it was. That "
    "would need a connection into the tool itself, and it is not built. A "
    "tick reading “still accurate” when nothing had been read "
    "would be untrue, so nothing here shows one.\n\n"
    "What these can tell you is when you last looked, what you said your "
    "own interval was, and that somebody wrote down a change. Whether the "
    "change mattered is a question only a person answering it can close.\n\n"
    "The change watch also only knows about a change somebody wrote down. A "
    "vendor who changes a tool without telling anyone is invisible to this "
    "watch, and to you. That is why what a vendor has to tell you sits on "
    "the Vendors entry as a term in the agreement rather than as a setting "
    "here.")

#: The due watch recomputes nightly and on demand. Notification is a
#: separate decision the organisation has not been asked about, and
#: inventing one would put mail in the inbox of a person who did not ask
#: for it.
NEVER_EMAILS = ("This recomputes overnight and whenever you ask it to. It "
                "never emails anybody.")


# ===========================================================================
# 4 · Findings
# ===========================================================================

#: Shown above the list, permanently, because the distinction is the whole
#: basis of the panel.
FINDINGS_ARE_COMPARISONS = (
    "Everything below is a comparison between your own framework and your "
    "own records. Nothing here is a judgment about whether a tool is any "
    "good.")

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.limits_absent", "Integrity",
        "A check marked complete with the box ticked saying nobody wrote "
        "the limits down",
        "Nobody wrote down what was not tested. [Role] is recorded to go "
        "and ask, by [date]."),
    spine.Finding(
        "finding.watch_missing", "Integrity",
        "A Measure check marked complete where something the organization "
        "said it watches has no answer recorded",
        "You said you watch [their words for that item]. This look did not "
        "record it."),
    spine.Finding(
        "finding.claim_unmeasured", "Integrity",
        "A Measure check marked complete with no measurement against the "
        "baseline written at Procure",
        "You said this would be worth keeping if [their words]. This look "
        "did not say whether it is."),
    spine.Finding(
        "finding.determination_not_followed", "Integrity",
        "A check records that it did not do what was expected, the "
        "organization's own answer is to pause it or to retire it, and the "
        "project is neither paused nor at Sunset",
        "You said a tool that is not delivering gets [their answer]. This "
        "one is recorded as not delivering and is still running."),
    spine.Finding(
        "finding.fallback_untried", "Integrity",
        "The organization said the manual way gets tried on an interval, "
        "and no check inside that interval records it being tried",
        "You said the manual way gets tried [their frequency]. The last "
        "time anyone recorded trying it was [date]."),
    spine.Finding(
        "finding.groups_check_missing", "Integrity",
        "The organization marked differential effect as some or major "
        "concern, and the Test check records no answer about it",
        "You marked [their words for that factor] as [their level of "
        "concern]. This check does not say whether anyone looked."),
    spine.Finding(
        "finding.accessibility_recheck_missing", "Integrity",
        "A public-facing project where the organization said accessibility "
        "gets checked on an interval, and no check inside it records an "
        "accessibility answer",
        "You said accessibility gets checked [their answer]. Nothing here "
        "records that for a tool the public uses."),
    spine.Finding(
        "finding.change_unanswered", "Integrity",
        "A change was recorded, no check has been marked complete since, "
        "and the organization's own answer says a change gets handled",
        "A change was recorded on [date]. You said a change gets handled "
        "this way: [their answer]. Nothing has been recorded since."),
    spine.Finding(
        "finding.level_unreviewed_after_incident", "Integrity",
        "The organization said the scrutiny level gets looked at again "
        "after an incident, an incident exists, and it has not been",
        "You said the scrutiny level gets looked at again after an "
        "incident. This one had an incident on [date] and the level has not "
        "been looked at since."),
    spine.Finding(
        "finding.lookback_owed", "Integrity",
        "The organization said it goes back after a problem, an incident "
        "exists, and no look-back result is recorded against it",
        "You said you go back [their scope] after a problem. This one has "
        "no look-back recorded."),
    spine.Finding(
        "finding.notified_missing", "Integrity",
        "An incident where a party the organization named must be told, "
        "with no notification recorded against that party",
        "You said [party] has to be told. Nothing here records that they "
        "were."),
    spine.Finding(
        "finding.report_slower_than_stated", "Integrity",
        "An incident written down later than the organization's own "
        "required reporting speed for that severity, measured from the "
        "recorded detection date",
        "You said [their level name] gets reported [their speed]. This one "
        "was detected on [date] and written down on [date]."),
    spine.Finding(
        "finding.test_on_never", "Integrity",
        "A check names a holding carrying a category the organization said "
        "never goes into a general-purpose tool, and the Registry row "
        "records the tool as general-purpose",
        "You said never for [their category]. This check was run on real "
        "material from [holding]."),
    spine.Finding(
        "finding.stopping_rule_unmet", "Integrity",
        "The organization has a written rule for when testing is enough, "
        "and a complete check does not say it was met",
        "You have a written rule for when testing is enough. This check "
        "does not say it was met."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}


# ---------------------------------------------------------------------------
# 4B · Findings defined elsewhere that render here
# ---------------------------------------------------------------------------

#: Defined once elsewhere — in the spine, or on the surface that owns the
#: record they attach to. Integrity renders them with the sentence their
#: owner wrote, and never redefines one.
#:
#: 4C · A finding has one id and one sentence and lives on one record. It
#: renders on the panel of the surface that owns the record, *and* on the
#: panel of the surface that holds the evidence it is missing. Both badges
#: count it. That double render is deliberate: the person looking at Process
#: needs to know a record cannot pass, and the person looking at Integrity
#: needs to know a check is owed. Telling only one of them leaves the
#: finding open for a month. Within a single panel a finding is drawn once.
RENDERS_HERE: dict[str, str] = {
    "finding.no_baseline":
        "Raised by Projects. The first check at Test is where the absence "
        "stops being an empty field and becomes a check with nothing to "
        "compare against. This surface never writes the baseline and never "
        "raises this finding on its own.",
    "finding.version_untracked":
        "Raised by Projects. The half about a version that went live with "
        "no Test record is this surface's evidence.",
    "finding.pj.baseline_unreachable":
        "Raised by Projects. This is the surface where somebody goes to "
        "take the measurement again and finds they cannot.",
    "finding.review_overdue":
        "Raised here, against the organization's own frequency at that "
        "scrutiny level.",
    "finding.condition_overdue":
        "Raised here, for conditions attached at a Test or a Measure "
        "passage.",
    "finding.framework_moved":
        "Rendered here only where what moved was what you watch, how often "
        "you look, how fast an incident gets reported, or how far back you "
        "go. An amendment that touched none of those raises nothing here.",
    "finding.description_stale":
        "Process owns the description; Integrity holds the record of the "
        "change that made it stale.",
    "finding.floor_missing":
        "Process raises this at Deploy. Where the missing evidence would "
        "have been a check on this surface, it renders here too, with the "
        "same id and the same sentence.",
}

#: The four amendments that make `finding.framework_moved` render here.
FRAMEWORK_MOVES_THAT_SHOW_HERE = (
    "what you watch",
    "how often you look",
    "how fast an incident gets reported",
    "how far back you go",
)

#: Raised here, from the spine, against the organisation's own answers.
RAISED_HERE_FROM_THE_SPINE = ("finding.review_overdue",
                              "finding.condition_overdue")

#: Where a finding renders twice, both badges count it, and within a single
#: panel it is drawn once.
DRAWN_ONCE_PER_PANEL = True


# ---------------------------------------------------------------------------
# 4D · What never produces a finding here
# ---------------------------------------------------------------------------

WILL_NOT_RAISE = (
    "Answering never about trying the manual way. That is the "
    "organization's answer. One line of consequence is shown at the moment "
    "they answer it, and this surface never raises it again.",
    "Watching only whether a tool works. An organization that selected "
    "nothing else is asked about nothing else, and the absence of the other "
    "items is never shown as missing.",
    "Not running a differential-effect check where the organization marked "
    "that factor as not a concern.",
    "Concentration of roles. One person holding all three hats is a plain "
    "count on Oversight and is never a finding here.",
    "Any absence of a function the organization marked as not present. The "
    "app never routes to an office the organization does not have, and "
    "never shows that absence as a defect.",
    "A recorded change the organization said simply goes on the list. The "
    "change watch still lists the change and every project that names the "
    "tool. Nothing is flagged, because a change going on the list is "
    "exactly what the organization said would happen to it.",
    "An incident with no look-back, where the organization does not go back "
    "or decides case by case. The field still exists, the answer is still "
    "recorded, and no look-back is ever shown as owed.",
    "Not having a written rule for when testing is enough. Nothing in your "
    "framework asks for one, and its absence is never a defect.",
    "Declining the recommendation. Declining is a complete answer, recorded "
    "without comment. There is no finding on this surface, or anywhere in "
    "the application, whose trigger is a declined recommendation.",
    "Having no staging or testing environment. Where there is none, the "
    "check records that, the recommendation fires with its reason, and "
    "nothing is flagged here.",
    "Anything about the state of your data. Where a measurement cannot be "
    "retaken because a holding is unreachable, the check says so in plain "
    "words. Nothing about data readiness blocks a passage here or anywhere "
    "else.",
    "Anything about how good a tool is, how fast, how modern, or how it "
    "compares to anything.",
)


def findings(rows: list[dict[str, Any]] | None = None, *,
             watches: list[str] | None = None,
             lookback_answer: str = LOOKBACK_YES,
             lookback_scope: str = "",
             determinations: dict[str, str] | None = None,
             projects: dict[str, dict[str, Any]] | None = None,
             must_be_told: list[str] | None = None,
             report_hours: dict[str, int] | None = None,
             never_categories: dict[str, str] | None = None,
             baselines: dict[str, str] | None = None,
             fallback_days: int | None = None,
             fallback_frequency: str = "",
             differential: dict[str, str] | None = None,
             holding_names: dict[str, str] | None = None,
             general_purpose_projects: set[str] | None = None,
             access: dict[str, Any] | None = None,
             change_words: str = "",
             vendor_changes: dict[str, list[str]] | None = None,
             level_after_incident: bool = False,
             today: str = "") -> list[dict[str, Any]]:
    """Every finding this surface can compute from what is recorded.

    Each keyword is somebody else's record, read in. Where one is absent the
    finding it feeds is not computed, and the absence is never shown as
    missing.
    """
    rows = all_entries() if rows is None else rows
    watches = list(watches or [])
    projects = projects or {}
    must_be_told = list(must_be_told or [])
    report_hours = report_hours or {}
    never_categories = never_categories or {}
    baselines = baselines or {}
    raised: list[dict[str, Any]] = []

    def add(finding_id: str, ref: str, says: str) -> None:
        raised.append({"id": finding_id, "entry": ref, "says": says})

    rule = has_stopping_rule()

    for check in complete_checks(rows):
        ref = check["ref"]

        # 4.1 — the ticked box alone. An empty field never becomes a
        # complete check, so it never becomes a finding.
        if check.get("limits_not_written"):
            add("finding.limits_absent", ref,
                "Nobody wrote down what was not tested.")

        if check.get("gate") == spine.MEASURE:
            # 4.2 — only the items the organisation said it watches. Where
            # it selected none, nothing is asked and nothing is missing.
            for item in watches:
                if item not in (check.get("watched") or {}):
                    add("finding.watch_missing", ref,
                        f"You said you watch {_lower_first(item)}. This look "
                        f"did not record it.")

            # 4.3 — measured against the baseline written at Procure. Where
            # the project carries no baseline this is Projects' finding, not
            # this one.
            has_baseline = baselines.get(check.get("project") or "", "")
            if has_baseline and not check.get("against_baseline"):
                add("finding.claim_unmeasured", ref,
                    f"You said this would be worth keeping if "
                    f"{has_baseline}. This look did not say whether it is.")

        # 4.4 — reads the project's state at the moment the check is marked
        # complete, and closes itself the moment the project is paused or
        # reaches Sunset. No grace period, because none was asked for.
        if check.get("verdict") == DID_NOT_HOLD_UP:
            answer = (determinations or {}).get(
                check.get("project") or "") or check.get("determination")
            project = projects.get(check.get("project") or "") or {}
            running = (project.get("state") != spine.PAUSED
                       and project.get("gate") != spine.SUNSET)
            if answer in TAKES_IT_OUT_OF_SERVICE and running:
                add("finding.determination_not_followed", ref,
                    f"You said a tool that is not delivering gets "
                    f"{answer[0].lower() + answer[1:]}. This one is "
                    f"recorded as not delivering and is still running.")

        # 4.14 — on No or on no answer, and only where a rule exists. Where
        # there is no rule its absence is never a defect.
        if rule and check.get("stopping_rule_met") in ("No", ""):
            add("finding.stopping_rule_unmet", ref,
                "You have a written rule for when testing is enough. This "
                "check does not say it was met.")

        # 4.13 — both halves come from recorded answers. Where the holding
        # field is empty the finding is not computed, and neither absence is
        # shown as missing.
        # The second half: the Registry row for the tool this project runs
        # records it as general-purpose. Where that set is given and the
        # project is not in it, nothing is computed.
        general = (general_purpose_projects is None or
                   check.get("project") in general_purpose_projects)
        for holding in (check.get("holdings") or []) if general else []:
            category = never_categories.get(holding)
            if category:
                add("finding.test_on_never", ref,
                    f"You said never for {category}. This check was run on "
                    f"real material from "
                    f"{(holding_names or {}).get(holding, holding)}.")

    # 4.5 — only where they said the manual way is tried on an interval.
    # "Never — we just write it down" is their answer, and it is never raised.
    today = today or _today()
    if fallback_days:
        for ref, project in projects.items():
            if project.get("gate") != spine.MEASURE:
                continue
            tried = max((c.get("at", "") for c in complete_checks(rows)
                         if c.get("project") == ref
                         and c.get("manual_way") == MANUAL_TRIED), default="")
            if tried and _inside(tried, today, fallback_days):
                continue
            says = (f"You said the manual way gets tried "
                    f"{fallback_frequency or 'on an interval'}. ")
            says += (f"The last time anyone recorded trying it was {tried}."
                     if tried else "There is no record of anyone trying it.")
            add("finding.fallback_untried", ref, says)

    # 4.6 — where they marked differential effect as some or major concern,
    # a complete Test check that records nothing about it. `differential` is
    # {"item": the key it is recorded under, "words": their factor,
    #  "concern": "some concern" / "a major concern"}.
    if differential and differential.get("item"):
        for check in complete_checks(rows):
            if check.get("gate") != spine.TEST:
                continue
            if str((check.get("watched") or {}).get(differential["item"])
                   or "").strip():
                continue
            add("finding.groups_check_missing", check["ref"],
                f"You marked {differential.get('words') or 'this factor'} as "
                f"{differential.get('concern') or 'a concern'}. This check "
                f"does not say whether anyone looked.")

    # 4.7 — a tool the public uses, an ongoing accessibility check in their
    # answer at 6.4b, and nothing inside that interval records one. `access`
    # is {"days": n or None, "on_change": bool, "words": their answer}.
    if access and (access.get("days") or access.get("on_change")):
        for pref, project in projects.items():
            if str((project.get("tool") or {}).get("public_facing") or "") \
                    .lower() != "yes":
                continue
            looked = [c.get("at", "") for c in complete_checks(rows)
                      if c.get("project") == pref and c.get("accessibility")]
            last = max(looked, default="")
            owed = False
            if access.get("days") and not (
                    last and _inside(last, today, access["days"])):
                owed = True
            if access.get("on_change"):
                live = max((str(v.get("live") or "") for v in
                            project.get("versions") or [] if isinstance(v, dict)),
                           default="")
                if live and last < live:
                    owed = True
            if owed:
                add("finding.accessibility_recheck_missing", pref,
                    f"You said accessibility gets checked "
                    f"{access.get('words') or 'on an interval'}. Nothing here "
                    f"records that for a tool the public uses.")

    # 4.8 — a change recorded against the tool's project or against its
    # vendor entry, nothing marked complete since, and only where their own
    # answer at 8.5 or 5.5 says a change is handled.
    if change_words:
        for pref, project in projects.items():
            opened = [str(v.get("opened") or "") for v in
                      project.get("versions") or [] if isinstance(v, dict)]
            opened += [d for d in (vendor_changes or {}).get(pref, []) if d]
            changed = max(opened, default="")
            if not changed:
                continue
            since = [c for c in complete_checks(rows)
                     if c.get("project") == pref
                     and str(c.get("at") or "") >= changed]
            if not since:
                add("finding.change_unanswered", pref,
                    f"A change was recorded on {changed}. You said a change "
                    f"gets handled this way: {change_words}. Nothing has been "
                    f"recorded since.")

    # 4.9 — they said the level gets looked at again after an incident.
    if level_after_incident:
        for pref, project in projects.items():
            hit = [str(i.get("at") or i.get("written_down") or "")
                   for i in incidents(rows) if i.get("project") == pref]
            latest = max(hit, default="")
            if latest and clock.local_date(str(project.get("level_set_at") or "")) < latest[:10]:
                add("finding.level_unreviewed_after_incident", pref,
                    f"You said the scrutiny level gets looked at again after "
                    f"an incident. This one had an incident on {latest[:10]} "
                    f"and the level has not been looked at since.")

    for incident in incidents(rows):
        ref = incident["ref"]

        # 4.10 — the Yes branch only. Severity is not read; the framework
        # carries no per-severity dimension, and a mapping from a level to a
        # look-back would be one the app invented.
        if lookback_answer == LOOKBACK_YES and not has_lookback(incident):
            scope = lookback_scope or "as far as you said"
            add("finding.lookback_owed", ref,
                f"You said you go back {scope} after a problem. This one "
                f"has no look-back recorded.")

        # 4.11 — a party the organisation named, with no notification
        # recorded against that party.
        for party in must_be_told:
            if party not in (incident.get("told") or {}):
                add("finding.notified_missing", ref,
                    f"You said {_lower_first(party)} has to be told. Nothing "
                    f"here records that they were.")

        # 4.12 — measured from the recorded detection date to the recorded
        # write-down date, against their own speed for their own level.
        hours = report_hours.get(incident.get("severity") or "")
        noticed = incident.get("first_noticed") or ""
        if hours and noticed:
            gone = _days(noticed, incident.get("written_down") or _today())
            if gone is not None and gone * 24 > hours:
                add("finding.report_slower_than_stated", ref,
                    f"You said {incident.get('severity')} gets reported "
                    f"within {hours} hours. This one was detected on "
                    f"{noticed[:10]} and written down on "
                    f"{incident.get('written_down')}.")

    return raised


# ===========================================================================
# 5 · The recommendation this surface carries
# ===========================================================================

#: A third object alongside the finding and the gap, and the only one of the
#: three that offers an opinion. A finding says something contradicts what
#: the organisation decided. A gap says something is unanswered and names
#: who will answer it. A recommendation says what good practice would be
#: here and why.
#:
#: It never blocks, it is never a score, and a record moves exactly the same
#: way whether it is accepted or declined.
TRY_THE_UPDATE = spine.BY_RECOMMENDATION["rec.try_the_update_first"]


def recommendation_fires(check: dict[str, Any], *,
                         offered_for: set[str] | None = None) -> bool:
    """Two ways in.

    Offered on a look after something changed — once per version, and not
    again on later checks of the same version. Offered also on any check,
    first build or version, run in production or where there is nowhere to
    try things. Both of those answers fire it, because without one the next
    update lands straight on the people doing the work.
    """
    offered_for = offered_for or set()
    if check.get("occasion") == AFTER_A_CHANGE:
        if (check.get("version") or "") not in offered_for:
            return True
    return check.get("where") in (WHERE_PRODUCTION, WHERE_NONE)


#: Where the organisation has nowhere to try things, the recommendation
#: still renders and its reason carries the fact rather than a reprimand.
#: Nobody can try an update in an environment they do not have. The place
#: that gets fixed is the next agreement, and Vendors is where that term is
#: written.
NOWHERE_TO_TRY_IT = (
    "You have nowhere separate to try an update. Nobody can try one in an "
    "environment they do not have. The place this gets fixed is the next "
    "agreement, and a testing environment is a term you can write into it.")

#: Nothing on this screen suggests the organisation should have known
#: earlier. A project that arrives here with a tool already in production is
#: the ordinary case.
ORDINARY_CASE = ("A tool that is already running when you start writing this "
                 "down is the ordinary case, not a lapse.")

#: What it never does: never blocks a passage, never names a vendor, a
#: product or a supplier, never scores or grades the organisation for
#: declining, and never renders without its reason. A recommendation that
#: renders without its reason reads as an instruction, which this
#: application does not issue.
NEVER_WITHOUT_ITS_REASON = True


def answer_recommendation(entry_ref: str, state: str, *, actor: Any
                          ) -> dict[str, Any]:
    """Accepted or declined, recorded without comment. Nothing reads a
    declined answer to raise anything, anywhere."""
    if state not in (spine.ACCEPTED, spine.DECLINED):
        return {"ok": False, "error": "Accept it or decline it."}
    with _LOCK:
        held = _read()
        if entry_ref not in held["entries"]:
            return {"ok": False, "error": "No such check."}
        held.setdefault("recommendations", {})[entry_ref] = {
            "state": state, "at": _now()}
        _write(held)
    _log("event.recommendation_answered", actor,
         {"check": entry_ref, "recommendation": TRY_THE_UPDATE.id,
          "state": state})
    return {"ok": True, "state": state}


def recommendation_answers() -> dict[str, dict[str, Any]]:
    return dict(_read().get("recommendations") or {})


# ===========================================================================
# 1.2 · The badge
# ===========================================================================

def badge(rows: list[dict[str, Any]] | None = None, *,
          open_findings: int = 0) -> str:
    """Two numbers, and no nag.

    Where the second is zero the badge carries only the first, because a
    badge reading "0 to fix" is a nag. The badge counts findings only; a
    recommendation is never part of the to fix number.
    """
    rows = all_entries() if rows is None else rows
    if open_findings:
        return f"Integrity {len(rows)} · {open_findings} to fix"
    return f"Integrity {len(rows)}"


# ===========================================================================
# 7 · The list view
# ===========================================================================

GROUPED = "Grouped by project"
FLAT = "Straight down the page by date"

#: Two reading needs exist here and the toggle serves both. Grouped by
#: project answers "when did anybody last look at this"; straight down the
#: page by date answers "what has been happening". Grouped is the default,
#: because the first question is asked more often.
GROUPINGS = (GROUPED, FLAT)
DEFAULT_GROUPING = GROUPED

#: Twelve columns, read-only. Text, never a colour or an icon alone.
COLUMNS = (
    ("Kind", "A check / An incident"),
    ("About", "The project name, linked to the project. Where the incident "
              "was filed without a tool: Tool not identified."),
    ("Version", "The version this check is about; First build where it is "
                "the first look; blank on an incident."),
    ("Gate", "Test / Measure for a check; for an incident, the gate the "
             "project stood at when it happened. Gate names only, never a "
             "number."),
    ("Date", "The date it happened. Where that differs from the date it was "
             "written down, the row shows both."),
    ("Who", "The role title, with a name beside it where one was given. "
            "Where an outside party did it, the organization they belong "
            "to."),
    ("Where", "Staging / Sandbox / In production / No staging environment — "
              "checks only."),
    ("What was found", "The first line, with the full text on the expanded "
                       "row."),
    ("Limits", "Written down / Not yet — checks only."),
    ("Level", "The organization's own severity label — incidents only. "
              "Their words, never ours."),
    ("State", "The shared gate-and-state control from the spine, plus "
              "running ahead, conditions open and version pending as "
              "words."),
    ("Findings", "A count of open findings attached to this entry, linked. "
                 "Blank rather than 0."),
)

SORTS = (
    "Most recent first",
    "Longest since anyone looked",
    "Past due first",
    "Open incidents first",
    "Checks with no limits first",
    "By project, A to Z",
    "Oldest first",
)
DEFAULT_SORT = {FLAT: "Most recent first",
                GROUPED: "Longest since anyone looked"}

FILTERS = (
    "Kind — checks / incidents / both",
    "Gate — Test / Measure",
    "Scrutiny level, in your own labels",
    "Project",
    "Tool",
    "Version checks only",
    "Went live without being tried",
    "Past due only",
    "Look-back owed",
    "Limits not written down",
    "Has an open finding",
    "Still being written",
    "Date range",
    "Who looked",
)

#: Their own labels only. Where the organisation chose two levels and called
#: them routine and elevated, the filter offers routine and elevated, and
#: the word moderate never appears anywhere on this surface.
THEIR_LABELS_ONLY = True


def date_column(row: dict[str, Any]) -> str:
    """Recording late is ordinary, and the row shows both dates rather than
    flattening them into one."""
    at = row.get("at") or ""
    written = row.get("written_down") or ""
    if not at and written:
        return f"when it happened is not known · written down {written}"
    if at and written and at != written:
        return f"happened {at} · written down {written}"
    return at


def version_column(row: dict[str, Any]) -> str:
    if row.get("kind") != CHECK:
        return ""
    if row.get("version"):
        return str(row["version"])
    return "First build" if row.get("occasion") == FIRST_LOOK else ""


def limits_column(row: dict[str, Any]) -> str:
    if row.get("kind") != CHECK:
        return ""
    return "Written down" if row.get("limits") else "Not yet"


TOOL_NOT_IDENTIFIED = "Tool not identified"


def empty_state(*, projects: int = 0, unaccounted: bool = False) -> str:
    """Three variants, two of them driven by what is already on Projects."""
    if not projects:
        return ("Nothing recorded yet. Start with the tool that is already "
                "running, and write down what anybody actually knows about "
                "whether it works — including that nobody has looked.")
    if unaccounted:
        return (f"You have {projects} projects on your list that nobody has "
                f"been able to account for yet. Start with the one somebody "
                f"is already using. A check that says “nobody has "
                f"looked at this, and here is what we do not know” is a "
                f"real entry, and today it is the most useful one you can "
                f"write.")
    return (f"You have {projects} projects on your list and nothing recorded "
            f"about whether any of them works. Start with the one that "
            f"touches a decision about a person.")


#: The findings panel above an empty list shows the clean state, because an
#: empty register contradicts nothing.
EMPTY_CONTRADICTS_NOTHING = spine.NOTHING_TO_FLAG


# ===========================================================================
# 9 · The example sentence, by organisation type
# ===========================================================================

#: The two most-used fields on this surface each render one example drawn
#: from the organisation's own world. The strings are given in full so that
#: nobody has to invent copy for them. None of them is a placeholder.
#:
#: The example renders as help text beneath the field rather than as
#: placeholder text inside it. A screen reader then reads it before the user
#: types, and it does not vanish the moment somebody starts.
EXAMPLES: dict[str, tuple[str, str]] = {
    "State agency or department": (
        "Fifty permit applications from last quarter, the awkward ones as "
        "well as the clean ones.",
        "The applicant whose permit it touched, and the reviewer who relied "
        "on it."),
    "County government": (
        "A month of assessment appeals, including the three that went to a "
        "hearing.",
        "The property owner, and the appeal it was used on."),
    "City, town, or village": (
        "Two weeks of code enforcement complaints, taken as they came in.",
        "The resident who complained, and the inspection that followed."),
    "Special district": (
        "A year of work orders from the oldest part of the network.",
        "The crew sent out on it, and the customers on that line."),
    "School district or education agency": (
        "One term of enrollment records from one school, including the late "
        "registrations.",
        "The student it concerned, and the family who was told."),
    "Regional council, authority, or commission": (
        "Three rounds of grant applications, including the ones that scored "
        "badly.",
        "The applicant it scored, and the member government that relied on "
        "the result."),
    "Tribal government": (
        "A season of benefit eligibility files, including the ones staff "
        "argued about.",
        "The member whose eligibility it touched, and the office that acted "
        "on it."),
    "Other public body": (
        "A month of case files, taken in the order they arrived.",
        "The person the case belongs to, and the staff who acted on it."),
}
FALLBACK_EXAMPLE = "Other public body"


def example_for(organisation_type: str = "") -> tuple[str, str]:
    """`(what did they try it on, who or what was affected)`.

    Where the organization type has not been answered yet the Other public
    body pair is used, and no field on this surface waits on an answer.
    """
    return EXAMPLES.get(organisation_type, EXAMPLES[FALLBACK_EXAMPLE])


# ===========================================================================
# 10 · A check on a version, rather than a first build
# ===========================================================================

#: It is the same check, on the same project, against the same baseline.
#: Nothing starts over and no second project is created. One screen holds
#: every occasion anybody looked at this project, from the first build to
#: the release running today.
SAME_CHECK_SAME_PROJECT = ("This is the same project and the same baseline. "
                           "Nothing starts over.")

#: Opens pre-filled from the last complete check on this project, each
#: field carrying the date it was last answered.
CARRIES_FORWARD = ("against_baseline", "baseline_why_not", "watched",
                   "manual_way", "accessibility", "stopping_rule_met")

STILL_TRUE = "Still true"
ANSWER_IT_AGAIN = "Answer it again"

#: Nothing carried forward is silently re-affirmed. A carried field left
#: untouched records that nobody said either way, and the check renders it
#: that way rather than showing last year's answer as though somebody had
#: confirmed it.
NOBODY_SAID_EITHER_WAY = "Carried forward. Nobody has said either way."

#: Always asked fresh. Those six are the check. A version check that copies
#: the last one's answers into all six is a check nobody performed, and the
#: form offers no way to do it.
ALWAYS_FRESH = ("tried_on", "holdings", "period", "where", "found", "limits")

#: The previous version's check renders beside this one, read-only, so that
#: what changed in the tool can be read against what changed in the answers.
#: The comparison is one a person makes and writes down. The application
#: computes no difference, draws no trend line, and produces no drift figure.
NO_DRIFT_FIGURE = (
    "The last check sits beside this one so you can read them together. The "
    "app draws no trend line and works out no drift figure; the comparison "
    "is yours to write down.")

#: The limits field binds on a version check exactly as it does on a first
#: build. An update is the occasion when somebody tries the things they
#: thought of and writes nothing about the ones they did not.
LIMITS_BIND_ON_VERSIONS = True

#: Where the version went live before anybody checked it, the check still
#: gets written, dated when it actually happened. Neither finding blocks
#: anything and neither is written as a reprimand.
WENT_LIVE_UNCHECKED = (
    "Write the check anyway, dated when it actually happened. The ordinary "
    "organization arriving here is fitting governance around a tool that "
    "has been updating itself for two years, and this is the first version "
    "anybody wrote down.")


def carry_forward(project: str, rows: list[dict[str, Any]] | None = None
                  ) -> dict[str, Any]:
    """The pre-fill for a version check, with the date each answer was last
    given and nothing re-affirmed on the organization's behalf."""
    rows = all_entries() if rows is None else rows
    earlier = [c for c in complete_checks(rows)
               if c.get("project") == project]
    if not earlier:
        return {}
    last = max(earlier, key=lambda c: c.get("at", ""))
    return {field: {"answer": last.get(field),
                    "last_answered": last.get("at"),
                    "state": NOBODY_SAID_EITHER_WAY,
                    "controls": [STILL_TRUE, ANSWER_IT_AGAIN]}
            for field in CARRIES_FORWARD}


# ===========================================================================
# The whole surface, for a screen to read once
# ===========================================================================

def report(*, lookback_answer: str = LOOKBACK_YES,
           watches: list[str] | None = None,
           intervals: dict[str, int] | None = None,
           projects: dict[str, dict[str, Any]] | None = None,
           changes: list[dict[str, Any]] | None = None,
           versions: list[dict[str, Any]] | None = None,
           organisation_type: str = "") -> dict[str, Any]:
    rows = all_entries()
    raised = findings(rows, watches=watches, lookback_answer=lookback_answer,
                      projects=projects)
    tried, affected = example_for(organisation_type)
    return {
        "entries": rows,
        "checks": len(checks(rows)),
        "incidents": len(incidents(rows)),
        "counters": counters(rows, lookback_answer=lookback_answer,
                             intervals=intervals, projects=projects),
        "badge": badge(rows, open_findings=len(raised)),
        "raised": raised,
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "renders_here": dict(RENDERS_HERE),
        "findings_are_comparisons": FINDINGS_ARE_COMPARISONS,
        "will_not_raise": list(WILL_NOT_RAISE),
        "recommendation": TRY_THE_UPDATE.as_dict(),
        "due_watch": due_watch(rows, intervals=intervals, projects=projects),
        "change_watch": change_watch(rows, changes=changes,
                                     versions=versions),
        "watches_cannot": WHAT_THE_WATCHES_CANNOT_DO,
        "never_emails": NEVER_EMAILS,
        "columns": [{"name": n, "contents": c} for n, c in COLUMNS],
        "sorts": list(SORTS),
        "filters": list(FILTERS),
        "groupings": list(GROUPINGS),
        "empty_state": empty_state(projects=len(projects or {})),
        "examples": {"tried_on": tried, "affected": affected},
        "only_the_project": ONLY_THE_PROJECT,
        "anyone_can_write_it": ANYONE_CAN_WRITE_IT,
        "visible_to_everyone": VISIBLE_TO_EVERYONE,
        "limits_required": LIMITS_REQUIRED,
        "stopping_rule": stopping_rule(),
        "reads_only": list(READS_ONLY),
        "never_writes": list(NEVER_WRITES),
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
    }


# ===========================================================================
# 14 · Framework read-back — the organisation's own answers, read in
# ===========================================================================

#: Their answer at Module One 10.6, turned into the four branches above.
_LOOKBACK_FROM = {"yes": LOOKBACK_YES, "no": LOOKBACK_NO,
                  "case": LOOKBACK_CASE_BY_CASE, "unknown": LOOKBACK_UNSURE}

#: Module One 9.6 in this form's words, so 8.9a can pre-select their answer.
_DETERMINATION_FROM = {"adjust": ADJUST_AND_TEST, "pause": PAUSE_UNTIL_FIXED,
                       "retire": RETIRE_IT, "case": DECIDE_CASE_BY_CASE}

#: Module One 9.3 and 6.5b, as days. Their option, never a cadence of ours.
_CADENCE_DAYS = {"monthly": 31, "quarterly": 92, "biannual": 183,
                 "annual": 366}

#: Module One 10.4, as hours. The register holds dates rather than times, so
#: "Immediately" and "Same day" both mean written down on the day it was
#: noticed — the finest honest reading of a date.
_REPORT_HOURS = {"now": 0, "sameday": 0, "3days": 72, "week": 168}


def _lower_first(text: str) -> str:
    text = str(text or "")
    return text[:1].lower() + text[1:] if text else text


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    """Everything this surface reads from Module One, in one pass.

    Where a question is unanswered its input is simply absent, the finding
    it feeds is not computed, and nothing is invented to stand in for it.
    The read-back strings are the ones the form shows beside each field.
    """
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def label_of(key: str, raw: Any) -> str:
        q = m.by_key(key)
        for o in (q.options if q else []) or []:
            if o.value == raw:
                return o.label
        return str(raw or "")

    def asked(key: str) -> bool:
        q = m.by_key(key)
        return bool(q) and m.answered(q, answers)

    out: dict[str, Any] = {"readbacks": {}}
    rb = out["readbacks"]

    # 1.1 — the organisation type picks the example sentences.
    kind = value("org.kind")
    out["organisation_type"] = label_of("org.kind", kind) if kind else ""

    # 5.2 · their own level labels, lowest first. None until answered.
    levels = m.level_names(answers)
    out["levels"] = [name for _, name in levels]

    # 9.3 · how often, at each of their levels.
    cadence = value("watch.cadence") if asked("watch.cadence") else {}
    intervals: dict[str, int] = {}
    said_per_level: dict[str, str] = {}
    for tier_value, tier_name in levels:
        every = ((cadence or {}).get(tier_value) or {}).get("every", "")
        if every in _CADENCE_DAYS:
            intervals[tier_name] = _CADENCE_DAYS[every]
            said_per_level[tier_name] = {
                "monthly": "monthly", "quarterly": "quarterly",
                "biannual": "twice a year", "annual": "once a year"}[every]
    out["intervals"] = intervals
    rb["cadence"] = said_per_level

    # 9.5 · what else they watch, in their words.
    watched = value("watch.what") if asked("watch.what") else []
    out["watches"] = [label_of("watch.what", w) for w in (watched or [])
                      if w != m.UNKNOWN]

    # 5.1 · differential effect as some or major concern.
    factors = value("risk.factors") if asked("risk.factors") else {}
    concern = (factors or {}).get("disparate", "")
    if concern in ("some", "major"):
        item = label_of("watch.what", "disparate")
        out["differential"] = {
            "item": item,
            "words": "whether it could affect one group of people "
                     "differently than another",
            "concern": "a major concern" if concern == "major"
                       else "some concern"}
        rb["differential"] = (f"You marked this "
                              f"{out['differential']['concern']}.")
    else:
        out["differential"] = {}

    # 9.2 · do they write a before-measurement down.
    base = value("watch.baseline")
    out["baseline_asked"] = base in ("always", "sometimes")
    rb["baseline"] = {"always": "You said you always write one down.",
                      "sometimes": "You said sometimes."}.get(base, "")

    # 9.1 · what would make it worth keeping, in their words.
    out["worth"] = str(value("watch.worth") or "").strip()

    # 9.4 · who does the check.
    who = str(value("watch.who") or "").strip()
    out["who_checks"] = who
    rb["who"] = f"You said {who}." if who else ""

    # 9.6 · what happens when it is not delivering.
    failing = value("watch.failing")
    out["determination"] = _DETERMINATION_FROM.get(failing, "")
    rb["determination"] = (f"You said: {_lower_first(label_of('watch.failing', failing))}."
                           if failing in _DETERMINATION_FROM else "")

    # 6.5b · how often the manual way is tried. Never is their answer.
    fallback = value("floor.fallback_tested")
    out["fallback_asked"] = fallback in ("annual", "biannual")
    out["fallback_days"] = _CADENCE_DAYS.get(fallback) if out["fallback_asked"] else None
    out["fallback_frequency"] = {"annual": "once a year",
                                 "biannual": "twice a year"}.get(fallback, "")
    rb["fallback"] = (f"You said {out['fallback_frequency']}."
                      if out["fallback_asked"] else "")

    # 6.4a / 6.4b · accessibility, re-checked on an interval.
    when = value("floor.access_when") if asked("floor.access_when") else []
    out["access_ongoing"] = bool(set(when or []) & {"annual", "vendor"})
    owner = str(value("floor.access_owner") or "").strip()
    rb["accessibility"] = (
        f"You said {owner or 'somebody'} checks it, "
        + ", ".join(_lower_first(label_of("floor.access_when", w))
                    for w in (when or []) if w != m.UNKNOWN) + "."
        if out["access_ongoing"] else "")
    # 4.7 reads the interval, and whether a vendor change re-opens it.
    out["access"] = {
        "days": 366 if "annual" in (when or []) else None,
        "on_change": "vendor" in (when or []),
        "words": ", ".join(_lower_first(label_of("floor.access_when", w))
                           for w in (when or []) if w in ("annual", "vendor")),
    }

    # 4.8 · how a change is handled — 8.5, or the vendor-change trigger at
    # 5.5. Where neither holds, the finding is never raised.
    added = value("proc.added_ai")
    revisit = value("risk.revisit") if asked("risk.revisit") else []
    revisit = revisit if isinstance(revisit, list) else []
    if added in ("as_new", "risk_first"):
        out["change_words"] = _lower_first(label_of("proc.added_ai", added))
    elif "vendor_change" in revisit:
        out["change_words"] = _lower_first(label_of("risk.revisit",
                                                    "vendor_change"))
    else:
        out["change_words"] = ""
    # 4.9 · After any incident, at 5.5.
    out["level_after_incident"] = "incident" in revisit

    # 10.1 · attached to an existing process.
    out["attached_to_existing"] = (value("bad.existing") == "yes"
                                   and value("bad.attach") == "attach")

    # 10.2 · where a problem goes.
    out["route"] = str(value("bad.report_to") or "").strip()

    # 10.3 · their severity levels and their own definitions.
    q_levels = m.by_key("bad.levels")
    given = value("bad.levels") if asked("bad.levels") else {}
    severities = []
    for row in (q_levels.rows if q_levels else []) or []:
        meaning = ((given or {}).get(row.value) or {}).get("meaning", "")
        if not meaning and q_levels.tier_fields:
            meaning = (q_levels.tier_fields[0].get("defaults") or {}).get(
                row.value, "")
        severities.append({"value": row.value, "label": row.label,
                           "meaning": meaning})
    out["severities"] = severities if asked("bad.levels") else []

    # 10.4 · how fast each level has to be reported.
    speed = value("bad.speed") if asked("bad.speed") else {}
    out["report_hours"] = {s["label"]: _REPORT_HOURS[(speed or {})[s["value"]]]
                           for s in severities
                           if (speed or {}).get(s["value"]) in _REPORT_HOURS}

    # 10.5 · who can stop a tool without waiting — roles only, never shown on
    # the public page.
    stoppers = value("bad.stopper") or []
    out["stoppers"] = [str(r.get("role") or "").strip()
                       for r in stoppers if isinstance(r, dict)
                       and str(r.get("role") or "").strip()]

    # 10.6 · going back over earlier work, and how far.
    look = value("bad.lookback")
    out["lookback_answer"] = _LOOKBACK_FROM.get(look, LOOKBACK_UNSURE)
    far = value("bad.lookback_far")
    out["lookback_scope"] = _lower_first(label_of("bad.lookback_far", far)) \
        if far else ""
    rb["lookback"] = {
        LOOKBACK_YES: f"You said you go back {out['lookback_scope'] or 'over earlier work'}.",
        LOOKBACK_CASE_BY_CASE: "You said you decide this case by case.",
        LOOKBACK_UNSURE: "You have not decided whether you go back over "
                         "earlier work.",
    }.get(out["lookback_answer"], "")

    # 10.7 · who outside must be told.
    tell = value("bad.tell") if asked("bad.tell") else []
    delegated = value("org.delegated") == "yes"
    out["must_be_told"] = [label_of("bad.tell", t) for t in (tell or [])
                           if t not in ("none", m.UNKNOWN)
                           and (t != "federal" or delegated)]

    # 10.8 · who writes it up.
    out["writes_up"] = str(value("bad.writeup") or "").strip()

    # 1.4 · whether a legal function exists, for the legal line at 15B.
    functions = value("org.functions")
    handled = (functions or {}).get("legal") if isinstance(functions, dict) \
        else None
    out["has_legal"] = handled not in (None, "", "none", m.UNKNOWN)
    out["legal_how"] = ({o.value: o.label for o in m.HOW_HANDLED}
                        .get(handled, "") if out["has_legal"] else "")

    # 6.1a · what a final action means here.
    final = str(value("floor.final_action") or "").strip()
    rb["final_action"] = (f"You said a final action here means {final}."
                          if final else "")
    return out


def surface(*, answers: dict[str, Any] | None,
            projects: list[dict[str, Any]] | None = None,
            holdings: list[dict[str, Any]] | None = None,
            tools: list[dict[str, Any]] | None = None,
            vendor_changes: dict[str, list[str]] | None = None,
            viewer: str = "") -> dict[str, Any]:
    """The whole Integrity screen, read once, from the organization's own
    framework and its own records."""
    from app import attachments, module_one as m
    inputs = framework_inputs(answers)
    projects = list(projects or [])
    by_ref = {p["ref"]: p for p in projects if p.get("ref")}
    rows = all_entries()

    # 4.13 · the holdings carrying a category they said never goes into a
    # general-purpose tool, and the projects whose Registry row records the
    # tool as general-purpose. Both halves recorded; neither inferred.
    banned = m.value_of(dict(answers or {}), "data.never")[0]
    banned = banned if isinstance(banned, list) else []
    labels = {}
    q_never = m.by_key("data.never")
    if q_never:
        labels = {o.value: o.label for o in m.options_for(q_never, dict(answers or {}))}
    never_categories = {}
    for h in holdings or []:
        hit = [s for s in h.get("sensitive") or [] if s in banned]
        if hit:
            words = labels.get(hit[0], hit[0])
            never_categories[h.get("id")] = words[:1].lower() + words[1:]
    general = {p for t in tools or [] if t.get("general_purpose") == "Yes"
               for p in t.get("projects") or []}

    # Their words from 9.1, where they wrote any; the finding still fires on
    # a project with a baseline where 9.1 is unanswered, in plainer words.
    baselines = {ref: (_lower_first(inputs["worth"].rstrip(". "))
                       or "it met the baseline written on the project")
                 for ref, p in by_ref.items()
                 if str(p.get("baseline") or "").strip()}
    raised = findings(
        rows, watches=inputs["watches"],
        lookback_answer=inputs["lookback_answer"],
        lookback_scope=inputs["lookback_scope"],
        determinations={ref: inputs["determination"] for ref in by_ref}
        if inputs["determination"] else None,
        projects=by_ref, must_be_told=inputs["must_be_told"],
        report_hours=inputs["report_hours"], baselines=baselines,
        fallback_days=inputs["fallback_days"],
        fallback_frequency=inputs["fallback_frequency"],
        differential=inputs["differential"],
        never_categories=never_categories,
        holding_names={h.get("id"): h.get("name", "") for h in holdings or []},
        general_purpose_projects=general,
        access=inputs["access"], change_words=inputs["change_words"],
        vendor_changes=vendor_changes,
        level_after_incident=inputs["level_after_incident"])

    # 5.1 · the recommendation, once per version, apart from the findings.
    offered: set[str] = set()
    recommended = []
    answered = recommendation_answers()
    for check in sorted(checks(rows), key=lambda c: c.get("recorded_at", "")):
        if recommendation_fires(check, offered_for=offered):
            recommended.append({
                "entry": check["ref"],
                "state": (answered.get(check["ref"]) or {}).get(
                    "state", spine.OFFERED),
                "reason": (NOWHERE_TO_TRY_IT if check.get("where") == WHERE_NONE
                           else TRY_THE_UPDATE.because)})
        if check.get("version"):
            offered.add(check["version"])

    tried, affected = example_for(inputs["organisation_type"])
    unaccounted = any(p.get("seeded") for p in projects)
    per_entry: dict[str, int] = {}
    for f in raised:
        per_entry[f["entry"]] = per_entry.get(f["entry"], 0) + 1

    listed = []
    for row in rows:
        project = by_ref.get(row.get("project") or "") or {}
        listed.append({
            **row,
            "about": project.get("name") or (row.get("tool") or
                                             row.get("what_were_you_using")
                                             or TOOL_NOT_IDENTIFIED),
            "level": project.get("level", ""),
            "date_shown": date_column(row),
            "version_shown": version_column(row),
            "limits_shown": limits_column(row),
            "where_shown": WHERE_COLUMN.get(row.get("where", ""), "")
            if row.get("kind") == CHECK else "",
            "gate_shown": spine.BY_GATE[row["gate"]].name
            if row.get("gate") in spine.BY_GATE else
            (spine.BY_GATE[project["gate"]].name
             if project.get("gate") in spine.BY_GATE else ""),
            "open_findings": per_entry.get(row["ref"], 0),
            "attached": attachments.describe(row.get("attachments") or []),
            # 13 · who may change it while it is still being written.
            "yours": bool(viewer) and row.get("author") == viewer,
            "editable": (row.get("kind") == CHECK and not row.get("complete"))
            or (row.get("kind") == INCIDENT
                and row.get("closed") != INCIDENT_CLOSED),
        })

    fifth = fifth_counter(rows, inputs["lookback_answer"])
    return {
        "counters": counters(rows, lookback_answer=inputs["lookback_answer"],
                             intervals=inputs["intervals"], projects=by_ref),
        "fifth": fifth,
        "badge": badge(rows, open_findings=len(raised)),
        "entries": listed,
        "raised": raised,
        "recommended": recommended,
        "recommendation": TRY_THE_UPDATE.as_dict(),
        "findings_are_comparisons": FINDINGS_ARE_COMPARISONS,
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "due_watch": due_watch(rows, intervals=inputs["intervals"],
                               projects=by_ref),
        "change_watch": change_watch(rows, versions=[
            {**v, "project": ref} for ref, p in by_ref.items()
            for v in (p.get("versions") or []) if isinstance(v, dict)]),
        "watches_cannot": WHAT_THE_WATCHES_CANNOT_DO,
        "never_emails": NEVER_EMAILS,
        "empty_state": empty_state(projects=len(projects),
                                   unaccounted=unaccounted),
        "examples": {"tried_on": tried, "affected": affected},
        "stopping_rule": stopping_rule(),
        "inputs": inputs,
        "projects": [{"ref": p["ref"], "name": p.get("name", ""),
                      "gate": p.get("gate", ""), "level": p.get("level", ""),
                      "has_baseline": bool(str(p.get("baseline") or "").strip()),
                      "baseline": p.get("baseline", ""),
                      "versions": [v for v in (p.get("versions") or [])
                                   if isinstance(v, dict)],
                      "carry": carry_forward(p["ref"], rows)}
                     for p in projects if p.get("ref")],
        "holdings": [{"id": h.get("id"), "name": h.get("name", ""),
                      "sensitive": h.get("sensitive", [])}
                     for h in (holdings or [])],
        "options": {
            "occasions": list(OCCASIONS), "wheres": list(WHERES),
            "verdicts": list(VERDICTS),
            "determinations": list(DETERMINATIONS),
            "baseline": list(BASELINE_ANSWERS),
            "manual": list(MANUAL_ANSWERS),
            "access": list(ACCESS_ANSWERS),
            "rule": list(RULE_ANSWERS), "rule_met": list(RULE_MET_ANSWERS),
            "back_to_first_look": list(BACK_TO_FIRST_LOOK),
            "touched": list(TOUCHED_A_PERSON),
            "stopped": [STOPPED_YES, STOPPED_NO, STOPPED_UNSURE],
            "lookback": list(LOOKBACK_ANSWERS),
        },
        "copy": {
            "only_the_project": ONLY_THE_PROJECT,
            "date": DATE_GUIDANCE, "who": WHO_GUIDANCE,
            "found": FOUND_GUIDANCE, "limits": LIMITS_GUIDANCE,
            "limits_required": LIMITS_REQUIRED,
            "did_not_write": DID_NOT_WRITE_IT_DOWN,
            "no_staging": NO_STAGING_IS_NOT_A_FAULT,
            "access": ACCESS_GUIDANCE,
            "rule": STOPPING_RULE_GUIDANCE,
            "attachment": ATTACHMENT_NOTE,
            "attachment_security": ATTACHMENT_SECURITY,
            "conditions": CONDITION_GUIDANCE,
            "anyone": ANYONE_CAN_WRITE_IT,
            "visible": VISIBLE_TO_EVERYONE,
            "what_happened": WHAT_HAPPENED_GUIDANCE,
            "noticed": NOTICED_GUIDANCE,
            "write_up": WRITE_UP_GUIDANCE,
            "no_drift": NO_DRIFT_FIGURE,
            "same_project": SAME_CHECK_SAME_PROJECT,
            "went_live_unchecked": WENT_LIVE_UNCHECKED,
            "stop_route": stop_route(inputs["route"]),
            "stop_now": STOPPED_CONFIRMED,
            "not_editable_complete": NOT_EDITABLE_COMPLETE,
            "attachment_limit": "Up to five files, 5 MB each.",
            "scope": SCOPE_DISCLAIMER,
            "legal": legal_line(inputs),
        },
    }


def legal_line(inputs: dict[str, Any], *, organisation: str = "") -> str:
    """15B · the legal line. Second person signed in, third on the public
    page, and never a route to an office the organization does not have."""
    lead = ("Where a check touches a decision about somebody's rights, "
            "money, standing or employment, that is a question for an "
            "attorney rather than for this application.")
    who = organisation or ""
    if inputs.get("has_legal"):
        how = _lower_first(inputs.get("legal_how") or "legal counsel")
        return (lead + (f" {who} recorded that legal counsel here is "
                        f"{how}." if who else
                        f" You said legal counsel here is {how}."))
    return (lead + (f" {who} has recorded that it does not have legal counsel "
                    f"of its own." if who else
                    " You said you do not have legal counsel here, and that is "
                    "recorded as a gap."))


#: 15B · Scope disclaimer, shown in the same place as the legal line.
SCOPE_DISCLAIMER = (
    "This is a governance register: a record of what somebody looked at and "
    "what they found. It does not run anything, it never touches the tool, "
    "and it cannot see a tool's output. It does not write the number it "
    "measures against: the baseline is written at Procure and lives on the "
    "project, and this surface reads it. Nothing here scores a tool, rates "
    "it, or certifies it, and nothing here compares your organization to "
    "anybody else's.")
