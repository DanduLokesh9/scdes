"""Process — intake and the gates.

**One entry per standing procedure** — a written instruction that exists
once, independently of any single project, and that more than one record
can point at. This surface owns `gate.deploy` and supplies the checklist at
all seven gates.

Every other surface holds a fact about one piece of work. Process holds the
instructions: the written things that apply to more than one tool, and that
somebody has to be able to find on the morning the tool stops working.

**Why the unit is the procedure and not the passage.** One entry per gate
crossing is what a gate review checklist looks like on paper, and what most
organizations have if they have anything. It was rejected because if the
paper a passage requires is attached to the passage, a twelve-person
district writes the same fallback instruction four times and a
two-thousand-person agency writes it four hundred times — and on the day the
wording changes, nobody can say which records are still following the old
one. A procedure written once, versioned, owned and pointed at survives
that. The passage is still recorded, on the project, and it points at the
procedure that was in force on the day it happened.

**Why it owns Deploy.** Deploy turns on whether the operating instructions
exist and whether a person can find them, and those instructions live here.
The application refuses a passage at two gates and on seven obligations,
and six of the seven are here: a record cannot be recorded as having passed
`gate.deploy` while a floor obligation that binds there is unsatisfied. The
seventh is Floor 7 at Identify, which belongs to Projects and which nothing
here implements.

**What it never does.** It writes nothing at Identify. The walkthrough a
person answers there is on Projects, and Projects creates the project
record. A code path here that creates a project is the same class of defect
as one that writes state.

Named `procedures` because the unit is the standing procedure. `process`
would have read as the noun for the whole application.
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

FILENAME = "procedures.json"
_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    return clock.today_str()


def _file():
    from app import tenant
    from app.audit import CORPUS
    return tenant.scoped(CORPUS / "config" / FILENAME)


def _read() -> dict[str, Any]:
    blank: dict[str, Any] = {"procedures": {}}
    path = _file()
    if not path.is_file():
        return blank
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return blank
    if not isinstance(held, dict):
        return blank
    held.setdefault("procedures", {})
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
            action=action, target="Process", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]})
    except Exception:                                         # noqa: BLE001
        pass


def _ref(existing: set[str]) -> str:
    for _ in range(64):
        ref = "PR-" + "".join(
            secrets.choice("23456789BCDFGHJKMNPQRSTVWXYZ") for _ in range(6))
        if ref not in existing:
            return ref
    return "PR-" + secrets.token_hex(5).upper()


# ===========================================================================
# 6.2.1 · What kind of procedure it is
# ===========================================================================

ROUTE_IN = "The way something gets written down in the first place"
CHECKLIST = "What has to exist on paper before something passes a gate"
WORDING = "The words the public sees when a tool is involved"
ROUTE_TO_PERSON = "How somebody reaches a person instead"
MANUAL_WAY = "How the work gets done when the tool is off"
TURN_IT_OFF = "How to turn it off"
TRY_AN_UPDATE = "How an update gets tried before it goes live"
DESCRIPTION = ("Who writes the plain-language description, and who approves "
               "it")
TRAINING = "How staff are trained before they get access"
DECISION_RECORD = "How a decision gets written down, and where it is kept"
PROBLEM_ROUTE = "How a problem gets reported, and who gets told"
SOMETHING_ELSE = "Something else we run this way"

#: Twelve kinds, shown as the full phrase rather than an abbreviation.
KINDS: tuple[str, ...] = (
    ROUTE_IN, CHECKLIST, WORDING, ROUTE_TO_PERSON, MANUAL_WAY, TURN_IT_OFF,
    TRY_AN_UPDATE, DESCRIPTION, TRAINING, DECISION_RECORD, PROBLEM_ROUTE,
    SOMETHING_ELSE,
)

#: Eight of the twelve can be required by the organisation's own answers.
#: Nothing else on this surface may make a kind required.
CAN_BE_REQUIRED: tuple[str, ...] = (
    ROUTE_IN, CHECKLIST, WORDING, ROUTE_TO_PERSON, MANUAL_WAY, TURN_IT_OFF,
    DESCRIPTION, TRAINING,
)

#: Four are never required, and each absence is a decision rather than an
#: oversight.
NEVER_REQUIRED: dict[str, str] = {
    DECISION_RECORD:
        "The organization already answered where decisions live, and a "
        "procedure repeating it earns nothing.",
    PROBLEM_ROUTE:
        "Integrity is where a person actually reports something. The route "
        "is written here; the reports themselves are recorded there.",
    SOMETHING_ELSE:
        "Nothing in the framework can require a kind the organization "
        "invented.",
    TRY_AN_UPDATE:
        "An organization that ticked the testing-environment term required "
        "a term in an agreement, which Vendors records and Procure marks "
        "present or absent. It did not require a written instruction here. "
        "Turning their answer about a contract into a requirement would be "
        "this surface inventing an obligation they never took on.",
}

#: The spine makes the testing environment a recommendation with its
#: reason, and a recommendation never blocks and never hardens into a
#: requirement.
NEVER_COUNTED_SHORT = ("None of the four is ever counted short, and none of "
                       "them ever produces a ghost row.")


# ===========================================================================
# 6.4.3 · Status
# ===========================================================================

IN_FORCE = "In force"
DRAFTED = "Drafted, not adopted"
REPLACED = "Replaced"
WITHDRAWN = "Withdrawn"

STATUSES = (IN_FORCE, DRAFTED, REPLACED, WITHDRAWN)

#: Replaced and withdrawn procedures stay on the list. Two years from now,
#: explaining a decision means knowing which version was in force on the day.
NOTHING_IS_REMOVED = True


# ===========================================================================
# 6.3.1 · The framework's fixed tiers, rendered in their own level names
# ===========================================================================

#: The framework's fallback question is a fixed three-option question, asked
#: before the organisation's level names are in play. Left alone, the word
#: *moderate* leaks straight out of that answer and into a finding, in front
#: of an organisation that never wrote it. So the answer is mapped once,
#: here, and every render of it anywhere on this surface goes through this
#: function.
ALL_TOOLS = "all"
MIDDLE_AND_UP = "moderate_and_high"
TOP_ONLY = "high_only"

TIERS = (ALL_TOOLS, MIDDLE_AND_UP, TOP_ONLY)

EVERY_LEVEL = "Every level"


def levels_that_bind(tier: str, levels: list[str]) -> list[str]:
    """The three tiers are three widths rather than three names: everything,
    everything above the lowest level, and the top level only.

    **The two-level case, said out loud.** With two levels, the two narrower
    tiers land in the same place: both exclude the level the organization
    defined as its routine one, and excluding the bottom of two leaves the
    top of two. So an organization that chose *routine* and *elevated* and
    answered either narrower tier is told that fallbacks are required at
    *elevated*, and the finding and the read-back both say *elevated*.

    It binds to the top level because that is the only reading of their
    answer that is theirs. Widening it to everything would require more of
    them than they agreed to, and narrowing it to nothing is not an answer
    the question offers.
    """
    levels = [str(lvl) for lvl in levels if str(lvl).strip()]
    if not levels or tier == ALL_TOOLS:
        return [EVERY_LEVEL]
    if len(levels) <= 2:
        return levels[-1:]
    if tier == MIDDLE_AND_UP:
        return levels[1:]
    return levels[-1:]


def level_phrase(tier: str, levels: list[str]) -> str:
    """Their own level names, or the words *every level*, and nothing else.

    Wherever the mapping renders, it renders the names and never the tier
    string.
    """
    bound = levels_that_bind(tier, levels)
    if bound == [EVERY_LEVEL]:
        return "every level"
    if len(bound) == 1:
        return bound[0]
    return ", ".join(bound[:-1]) + " and " + bound[-1]


# ===========================================================================
# The record
# ===========================================================================

ONLY_THE_NAME = (
    "Only the name is required. A register that refuses a row until every "
    "box is filled is one nobody finishes; write the name now and come back "
    "for the rest when you know it.")

NAME_GUIDANCE = (
    "Whatever the people who follow it would call it. “Turning off the "
    "permit assistant” is a better name than “Decommissioning "
    "Protocol”.")

STEPS_GUIDANCE = (
    "In enough detail that somebody who has never done it could follow it. "
    "If the real document lives somewhere else, say where and paste the "
    "part that matters.")

#: Shown where the organisation is subject to open records.
NOTHING_IS_PRIVATE = (
    "Nothing on this screen is private. You are almost certainly subject to "
    "open records, and a field that presented itself as private would be a "
    "trap set for whoever typed in it.")

OWNER_GUIDANCE = (
    "A title rather than a person's name, so it survives turnover. One "
    "person holding several of these is normal and will be recorded as one "
    "person holding several.")

NOBODY_NAMED = "Recorded as unknown — nobody named to close it"

#: A procedure can exist before anything points at it. That is a procedure
#: waiting to be used rather than an error.
NOTHING_POINTS_AT_THIS = "Nothing points at this yet"

EVERY_GATE = "It applies at every gate"
NO_GATE = "It does not belong to a gate"


def write(*, name: str, actor: Any, kind: str = "", steps: str = "",
          where_it_lives: str = "", lives_here: bool = False,
          unusual: str = "", gates: list[str] | None = None,
          levels: list[str] | None = None, covers: str = "",
          covered_records: list[str] | None = None, owner: str = "",
          adopted_by: str = "", adopted_on: str = "",
          status: str = DRAFTED, in_force_from: str = "",
          replaced_by: str = "", look_again: list[str] | None = None,
          look_again_date: str = "", confirmed_on: str = "",
          confirmed_by: str = "", ever_tried: str = "",
          last_tried: str = "", items: list[dict[str, Any]] | None = None,
          asks: list[dict[str, Any]] | None = None,
          what_happens_next: str = "", words: str = "",
          words_appear: list[str] | None = None, wrote_it: str = "",
          approved_by: str = "", approved_on: str = "",
          is_current: str = "", may_stop_it: str = "",
          turning_off_means: str = "", can_roll_back: str = "",
          falls_back_to: str = "", somewhere_to_try: str = "",
          who_tries_it: str = "", how_long: str = "",
          when_nowhere_to_try: str = "", records_the_version: str = "",
          gaps: list[str] | None = None) -> dict[str, Any]:
    """One standing procedure. Only the name is required."""
    if not str(name or "").strip():
        return {"ok": False, "error": "Give it a name."}

    with _LOCK:
        held = _read()
        ref = _ref(set(held["procedures"]))
        row = {
            "ref": ref,
            "name": str(name).strip(),
            "kind": kind,
            "steps": str(steps or "").strip(),
            "where_it_lives": str(where_it_lives or "").strip(),
            "lives_here": bool(lives_here),
            # Surfaces verbatim wherever the procedure is shown.
            "unusual": str(unusual or "").strip(),
            "gates": list(gates or []),
            # Their own level names, only ever.
            "levels": list(levels or []),
            "covers": covers,
            "covered_records": list(covered_records or []),
            "owner": str(owner or "").strip(),
            "adopted_by": adopted_by,
            "adopted_on": adopted_on,
            "status": status,
            "in_force_from": in_force_from,
            "replaced_by": replaced_by,
            "replaces": "",
            # Only the triggers the organisation ticked are ever offered.
            "look_again": list(look_again or []),
            "look_again_date": look_again_date,
            # Never is an honest answer and nothing is flagged for it.
            "confirmed_on": confirmed_on,
            "confirmed_by": confirmed_by,
            "ever_tried": ever_tried,
            "last_tried": last_tried,
            "items": list(items or []),
            "asks": list(asks or []),
            "what_happens_next": str(what_happens_next or "").strip(),
            "words": str(words or "").strip(),
            "words_appear": list(words_appear or []),
            "wrote_it": wrote_it,
            "approved_by": approved_by,
            "approved_on": approved_on,
            "is_current": is_current,
            "may_stop_it": may_stop_it,
            "turning_off_means": turning_off_means,
            "can_roll_back": str(can_roll_back or "").strip(),
            "falls_back_to": falls_back_to,
            "somewhere_to_try": somewhere_to_try,
            "who_tries_it": str(who_tries_it or "").strip(),
            "how_long": how_long,
            "when_nowhere_to_try": str(when_nowhere_to_try or "").strip(),
            "records_the_version": records_the_version,
            "gaps": list(gaps or []),
            "written_on": _today(),
            "recorded_at": _now(),
        }
        held["procedures"][ref] = row
        _write(held)

    _log("event.procedure_written", actor, {"procedure": ref, "kind": kind})
    return {"ok": True, "procedure": row}


# ---------------------------------------------------------------------------
# 7 · Versions, and why editing works this way
# ---------------------------------------------------------------------------

#: Stated above the button, never asked as a question.
VERSION_RULE = (
    "This is in force, so saving makes a new version. The old one stays on "
    "the list and every record that passed under it keeps pointing at it. "
    "Nothing that already happened changes.")

ADD_IT = "Add it"
SAVE_A_NEW_VERSION = "Save a new version"


def submit_label(procedure: dict[str, Any] | None) -> str:
    if procedure and procedure.get("status") == IN_FORCE:
        return SAVE_A_NEW_VERSION
    return ADD_IT


def save(ref: str, *, actor: Any, **changes: Any) -> dict[str, Any]:
    """A drafted procedure is edited in place. One in force is not.

    Saving a change to a procedure in force writes a new version, marks the
    previous one replaced, and leaves every record that already passed a
    gate pointing at the version that was in force on the day it passed.
    """
    with _LOCK:
        held = _read()
        row = held["procedures"].get(ref)
        if not row:
            return {"ok": False, "error": "No such procedure."}

        if row.get("status") != IN_FORCE:
            row.update({k: v for k, v in changes.items() if k in row})
            held["procedures"][ref] = row
            _write(held)
            _log("event.procedure_edited", actor, {"procedure": ref})
            return {"ok": True, "procedure": row, "new_version": False}

        fresh = _ref(set(held["procedures"]))
        made = {**row, **{k: v for k, v in changes.items() if k in row},
                "ref": fresh, "status": IN_FORCE, "replaces": ref,
                "in_force_from": _today(), "replaced_by": "",
                # A new version has not been confirmed by anybody yet.
                "confirmed_on": "", "confirmed_by": "",
                "recorded_at": _now()}
        row["status"] = REPLACED
        row["replaced_by"] = fresh
        held["procedures"][ref] = row
        held["procedures"][fresh] = made
        _write(held)

    _log("event.procedure_version_saved", actor,
         {"procedure": fresh, "replaces": ref})
    return {"ok": True, "procedure": made, "new_version": True,
            "says": VERSION_RULE}


#: Moving the records that still point at the old version is a choice.
#: Leaving them raises a finding, which is a fact rather than a fault,
#: because there are good reasons to let a pilot finish under the rules it
#: started with.
MOVING_IS_A_CHOICE = ("Leaving a record on the version it started under is "
                      "a fact rather than a fault.")


def confirm(ref: str, *, actor: Any, by: str = "", on: str = ""
            ) -> dict[str, Any]:
    """Recording that somebody read it and said it is still true.

    A direct write available in any hat, because the alternative is a
    finding that stays open because confirming it needed a meeting.
    """
    with _LOCK:
        held = _read()
        row = held["procedures"].get(ref)
        if not row:
            return {"ok": False, "error": "No such procedure."}
        row["confirmed_on"] = on or _today()
        row["confirmed_by"] = by or str(getattr(actor, "name", "") or "")
        held["procedures"][ref] = row
        _write(held)
    _log("event.procedure_confirmed", actor, {"procedure": ref})
    return {"ok": True, "procedure": row}


def mark_tried(ref: str, *, actor: Any, answer: str, on: str = ""
               ) -> dict[str, Any]:
    """6.5.3 · Has it ever been tried? A direct write in any hat."""
    if answer not in TRIED_ANSWERS:
        return {"ok": False, "error": "Choose one of the answers."}
    with _LOCK:
        held = _read()
        row = held["procedures"].get(ref)
        if not row:
            return {"ok": False, "error": "No such procedure."}
        row["ever_tried"] = answer
        row["last_tried"] = (on or _today()) if answer == TRIED_YES else \
            row.get("last_tried", "")
        _write(held)
    _log("event.fallback_tried", actor, {"procedure": ref, "answer": answer})
    return {"ok": True, "procedure": row}


#: 6.5.3 · the three answers.
TRIED_YES = "Yes, on a date"
TRIED_NOT_YET = "No, it has been written but not tried"
TRIED_CANNOT = "This one cannot be tried without doing real harm"
TRIED_ANSWERS = (TRIED_YES, TRIED_NOT_YET, TRIED_CANNOT)


def set_status(ref: str, status: str, *, actor: Any, on: str = "",
               adopted_by: str = "") -> dict[str, Any]:
    """Put a procedure in force, or withdraw one. Who may is decided by the
    caller against the organization's own delegation; this only records it.

    Nothing is deleted. A withdrawn procedure stays on the list with its
    history, because explaining a decision two years from now means knowing
    which instruction was in force on the day.
    """
    if status not in (IN_FORCE, WITHDRAWN):
        return {"ok": False, "error": "A procedure is put in force or "
                                      "withdrawn from here."}
    with _LOCK:
        held = _read()
        row = held["procedures"].get(ref)
        if not row:
            return {"ok": False, "error": "No such procedure."}
        if row.get("status") == REPLACED:
            return {"ok": False, "error": "This has been replaced. Its newer "
                                          "version is the one to change."}
        row["status"] = status
        if status == IN_FORCE:
            row["in_force_from"] = on or _today()
            row["adopted_on"] = on or _today()
            row["adopted_by"] = adopted_by or row.get("adopted_by", "")
        else:
            row["withdrawn_on"] = on or _today()
        _write(held)
    _log("event.procedure_status", actor, {"procedure": ref, "status": status})
    return {"ok": True, "procedure": row}


def move_records(old_ref: str, *, actor: Any) -> dict[str, Any]:
    """7.2 · Move the records still pointing at a replaced version onto the
    version in force. A choice, never automatic."""
    with _LOCK:
        held = _read()
        old = held["procedures"].get(old_ref)
        if not old or old.get("status") != REPLACED or not old.get(
                "replaced_by"):
            return {"ok": False, "error": "Only a replaced procedure has "
                                          "records to move."}
        new = held["procedures"].get(old["replaced_by"])
        if not new:
            return {"ok": False, "error": "The newer version is missing."}
        moved = list(old.get("covered_records") or [])
        new["covered_records"] = sorted(set(new.get("covered_records") or [])
                                        | set(moved))
        old["covered_records"] = []
        old["moved_on"] = _today()
        _write(held)
    _log("event.procedure_records_moved", actor,
         {"from": old_ref, "to": new["ref"], "records": moved})
    return {"ok": True, "moved": moved, "to": new["ref"]}


#: 4.3 · Events a person writes down. Nothing here watches the statute book,
#: a budget office or a vendor; the count moves when somebody records one.
RECORDABLE_EVENTS = {
    "Whenever the vendor stops supporting it": "The vendor stopped supporting a tool",
    "When a law or rule changes": "A law or rule changed",
    "When the contract behind it ends": "A contract ended",
    "When its funding is not renewed": "Funding was not renewed",
}


def record_event(*, actor: Any, trigger: str, on: str = "", note: str = "",
                 records: list[str] | None = None) -> dict[str, Any]:
    if trigger not in RECORDABLE_EVENTS:
        return {"ok": False, "error": "Choose what happened."}
    with _LOCK:
        held = _read()
        row = {"trigger": trigger, "on": on or _today(),
               "note": str(note or "").strip()[:500],
               "records": list(records or []), "recorded_at": _now()}
        held.setdefault("events", []).append(row)
        _write(held)
    _log("event.procedure_event_recorded", actor, {"trigger": trigger})
    return {"ok": True, "event": row}


def events() -> list[dict[str, Any]]:
    return list(_read().get("events") or [])


def all_procedures() -> list[dict[str, Any]]:
    return list(_read()["procedures"].values())


def procedure(ref: str) -> dict[str, Any] | None:
    return _read()["procedures"].get(ref)


def in_force(rows: list[dict[str, Any]] | None = None
             ) -> list[dict[str, Any]]:
    rows = all_procedures() if rows is None else rows
    return [p for p in rows if p.get("status") == IN_FORCE]


def of_kind(kind: str, rows: list[dict[str, Any]] | None = None
            ) -> list[dict[str, Any]]:
    return [p for p in in_force(rows) if p.get("kind") == kind]


# ===========================================================================
# 6.7.4 · The six locked rows at Deploy
# ===========================================================================

#: Read-only, locked, present wherever the gate is Deploy, cannot be
#: deleted, and cannot be set to anything other than *it has to exist
#: before this passes*. Rendered above the editable rows under this heading.
SIX_BIND_HERE = "Six things bind here"

#: In the spine's order, so that the ids and the sentences stay in step.
LOCKED_AT_DEPLOY: tuple[tuple[str, str], ...] = (
    ("floor.person_decides",
     "A person makes the final call on anything this touches."),
    ("floor.tell_people",
     "People are told when they are dealing with it, and how to reach a "
     "person instead."),
    ("floor.accessibility",
     "It works for people with disabilities, where anything about it is "
     "public-facing."),
    ("floor.turn_it_off",
     "It can be turned off and the work still gets done."),
    ("floor.somebody_named", "Somebody's name is on it."),
    ("floor.explain_plainly", "Somebody can explain it in plain language."),
)

#: Shown under the six.
UNDER_THE_SIX = (
    "These six are almost everything this application refuses. A record "
    "cannot be recorded as having passed Deploy while one of them is "
    "unanswered. The only other refusal is at Identify, where a tool with "
    "nobody's name against it cannot pass. Everywhere else, at every other "
    "gate, a missing item is written down as missing and the work moves on. "
    "You chose how strict each one is in your framework; you did not choose "
    "whether to have them, and neither did we.")


def _locked_ids() -> tuple[str, ...]:
    return tuple(floor for floor, _ in LOCKED_AT_DEPLOY)


# 6.7.3 · What happens if it is missing
MUST_EXIST = "It has to exist before this passes"
SHOULD_EXIST = "It should exist; record it as a condition if it does not"
WORTH_NOTING = "Worth noting; note it and move on"

CONSEQUENCES = (MUST_EXIST, SHOULD_EXIST, WORTH_NOTING)

#: This sets how the item reads and how hard it is to walk past. It does not
#: stop the passage being recorded; nothing in this application does, except
#: the six that bind at Deploy.
CONSEQUENCE_GUIDANCE = (
    "This sets how the item reads and how hard it is to walk past. It does "
    "not stop the passage being recorded; nothing in this application does, "
    "except the six things that bind at Deploy. The middle answer is the "
    "one that keeps this from becoming a wall: attach a condition with an "
    "owner and a date, let the record move, and the app will tell you when "
    "the date passes.")

OUTSIDE_DEPLOY = (
    "Outside Deploy this records the item as missing on the record and "
    "raises a finding, and the passage is still recorded. The application "
    "cannot stop anyone using a tool, and a checklist that behaved as "
    "though it could would be describing software that does not exist.")


# 5.6.1 · How each checklist item resolves
RECORDED = "Recorded"
AS_A_CONDITION = "Attached as a condition"
AS_UNKNOWN = "Recorded as unknown"
NOT_ANSWERED = "Not answered"

RESOLUTIONS = (RECORDED, AS_A_CONDITION, AS_UNKNOWN, NOT_ANSWERED)

#: `Not answered` is available on any item at any gate **except** the seven
#: floor obligations that must be satisfied rather than answered: Floor 7 at
#: Identify, and the six at Deploy. This surface supplies the Identify
#: checklist as well as the Deploy one, so the exception has to name both or
#: the resolution reaches an item the spine says refuses a passage.
MUST_BE_SATISFIED: dict[str, tuple[str, ...]] = {
    spine.IDENTIFY: spine.binding(spine.IDENTIFY, spine.SATISFIED),
    spine.DEPLOY: spine.binding(spine.DEPLOY, spine.SATISFIED),
}


def resolutions_for(gate: str, floor: str = "") -> tuple[str, ...]:
    """Which resolutions an item may take. Four everywhere, three on a
    floor obligation that must be satisfied rather than answered."""
    if floor and floor in MUST_BE_SATISFIED.get(gate, ()):
        return (RECORDED, AS_A_CONDITION, AS_UNKNOWN)
    return RESOLUTIONS


def checklist_for(gate: str, level: str = "",
                  rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """What this surface supplies to a passage screen on Projects.

    Process supplies the checklist and records the pointer. Projects commits
    the passage and writes the state. Any code path here that writes state
    directly is a bug.
    """
    written: list[dict[str, Any]] = []
    for found in of_kind(CHECKLIST, rows):
        gates = found.get("gates") or []
        levels = found.get("levels") or []
        if gates and gate not in gates and EVERY_GATE not in gates:
            continue
        if level and levels and level not in levels and \
                EVERY_LEVEL not in levels:
            continue
        for item in found.get("items") or []:
            written.append({**item, "procedure": found["ref"],
                            "from": found.get("name", "")})

    locked = [{"item": says, "floor": floor, "consequence": MUST_EXIST,
               "locked": True,
               "resolutions": resolutions_for(gate, floor)}
              for floor, says in LOCKED_AT_DEPLOY] \
        if gate == spine.DEPLOY else []

    return {
        "gate": gate,
        "level": level,
        "locked": locked,
        "heading": SIX_BIND_HERE if locked else "",
        "under_the_six": UNDER_THE_SIX if locked else "",
        "items": written,
        "supplies_only": ("Process supplies the checklist. Projects commits "
                          "the passage and writes the state."),
    }


#: 5.6.2 · Where the passage is a version going live inside the loop, the
#: Deploy checklist renders one further row above the editable ones, naming
#: the version going live and the version it replaces. **The row is not a
#: floor and does not bind.** It exists because the person confirming a
#: checklist is entitled to know which version they are confirming it
#: against.
def version_row(going_live: str, replacing: str = "") -> dict[str, Any]:
    said = f"This passage is version {going_live} going live"
    if replacing:
        said += f", replacing {replacing}"
    return {"says": said + ".", "binds": False, "locked": True,
            "version": going_live, "replaces": replacing}


# ===========================================================================
# 2 · The stat row
# ===========================================================================

#: Two of the five are absences, and neither is drawn from the shared bank
#: at the spine. `Never checked` is deliberately not taken here: Registry
#: holds that phrase against a catalog row nobody has confirmed, and
#: Integrity holds it against a project nobody has looked at. A third
#: surface shipping the same phrase against a third object would teach the
#: user that the phrase means nothing in particular.
COUNTER_NAMES = ("Procedures written down", "In force today",
                 "Required here and not written",
                 "Never confirmed since it was written",
                 "Past the date its owner set")

#: The short form in the register's column, because the column heading
#: already says what is being confirmed.
NEVER_CONFIRMED = "Never confirmed"

#: The counters are text. None of them is a colour, a ring, a bar, or a
#: proportion of anything.
COUNTERS_ARE_TEXT = True


def counters(rows: list[dict[str, Any]] | None = None, *,
             required: dict[str, str] | None = None,
             today: str = "") -> dict[str, Any]:
    """Five counters, computed on load and refreshed when anything here is
    written."""
    rows = all_procedures() if rows is None else rows
    today = today or _today()
    live = in_force(rows)
    kinds_live = {p.get("kind") for p in live}

    return {
        # This number never goes down. A procedure somebody followed last
        # year is still the reason a decision from last year makes sense.
        "written_down": len(rows),
        "in_force": len(live),
        "required_not_written": sum(
            1 for kind in (required or {}) if kind not in kinds_live),
        # Includes fallbacks written and never tried, where that is the
        # organisation's own answer; the count is honest and the finding is
        # not raised.
        "never_confirmed": sum(1 for p in live if not p.get("confirmed_on")),
        # Counts the date the owner chose, never a date this application
        # invented.
        "past_its_date": sum(
            1 for p in live
            if p.get("look_again_date")
            and str(p["look_again_date"])[:10] < today),
    }


# ---------------------------------------------------------------------------
# 2.6 · The waiting line
# ---------------------------------------------------------------------------

#: One sentence directly beneath the stat row, the way Vendors carries its
#: money line.
#:
#: Counts only projects that came in through a route recorded here. Tools
#: seeded from the organisation's framework answers arrive in the same gate
#: and state without having come through any route, and counting those would
#: report a queue nobody formed.
#:
#: There is no target, no threshold and no colour. Eleven days is a fact
#: about a small organisation whose decision-maker meets quarterly, and
#: calling it late would be inventing a clock nobody agreed to.
def waiting_line(waiting: list[dict[str, Any]] | None = None, *,
                 route_exists: bool = True, ever_arrived: bool = True,
                 today: str = "") -> str:
    if not route_exists:
        return ("There is no written route in yet. Everything on the list "
                "so far was started straight on Projects.")
    if not ever_arrived:
        return ("Nothing has come in through the route yet. It is written; "
                "it has not been used.")
    waiting = [w for w in (waiting or []) if w.get("route")]
    if not waiting:
        return "Nothing is waiting to be picked up."

    today = today or _today()
    oldest = min((str(w.get("written_on") or today) for w in waiting),
                 default=today)
    try:
        then = datetime.fromisoformat(oldest[:19])
        days = (datetime.fromisoformat(today[:19]) - then).days
    except ValueError:
        days = 0
    each = "one" if len(waiting) == 1 else str(len(waiting))
    was = "it" if len(waiting) == 1 else "them"
    day = "day" if days == 1 else "days"
    return (f"{each} written down and nobody has picked {was} up. The "
            f"oldest has been there {days} {day}.")


# ===========================================================================
# 3 · The findings panel
# ===========================================================================

#: Findings here come from one source: a contradiction between what is
#: recorded on this surface and what the organisation itself answered. There
#: is no external standard behind any of them, no benchmark, and no
#: comparison to anybody else. Each one names the answer it contradicts, in
#: the organisation's own words, so that the user can tell in one read
#: whether the finding is right or whether their answer was.
CLEAN_STATE = spine.NOTHING_TO_FLAG

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.process.no_route_in", "Process",
        "The organization said nothing moves without its framework and "
        "process, and no intake route is in force",
        "You said everything flows through your framework and process. "
        "There is no route written here that says how something enters "
        "it."),
    spine.Finding(
        "finding.process.no_checklist_for_level", "Process",
        "The organization said what has to exist on paper before approval "
        "at a scrutiny level, and no gate checklist is in force for that "
        "gate at that level",
        "You said [their paper answer] has to exist before approval at "
        "[their level name]. No checklist here says what that is."),
    spine.Finding(
        "finding.process.gate_paper_absent", "Process",
        "A passage was recorded at a gate where the checklist in force "
        "names an item the record does not have, and no condition was "
        "attached",
        "This passed [gate] without [item], which your [level name] "
        "checklist asks for. Nothing was attached to close it later."),
    spine.Finding(
        "finding.process.no_route_to_person", "Process",
        "A record at or past Deploy whose disclosure answer says the public "
        "sees it, with no route-to-a-person procedure attached",
        "You said anyone dealing with this can reach a person instead. "
        "Nothing here says how."),
    spine.Finding(
        "finding.process.no_fallback", "Process",
        "A record at or past Deploy, at a level the fallback answer binds "
        "at, with no manual-way procedure attached",
        "You said tools at [their level names] need a written way to do the "
        "job without them. This one is [that record's level name] and does "
        "not have one."),
    spine.Finding(
        "finding.process.fallback_never_tried", "Process",
        "The organization said fallbacks are tried on a schedule, and a "
        "manual-way procedure in force has never been tried, or was last "
        "tried longer ago than that schedule",
        "You said the backup gets tried [their cadence]. This one has never "
        "been tried."),
    spine.Finding(
        "finding.process.wording_off_book", "Process",
        "The organization named one place where approved wording lives, and "
        "a record's disclosure text was typed free-hand instead",
        "You said approved wording lives in one place so everyone says the "
        "same thing. This record has its own."),
    spine.Finding(
        "finding.process.wording_unapproved", "Process",
        "The organization named who approves the wording, and a wording "
        "procedure is in force with no approver recorded",
        "You said [role] approves the wording. Nothing here records that "
        "they did."),
    spine.Finding(
        "finding.process.turnoff_unwritten", "Process",
        "The organization named a role able to stop a tool without waiting "
        "for a meeting, and a record in use has no turn-off procedure "
        "attached",
        "You named [role] as able to stop a tool without waiting for a "
        "meeting. Nothing here tells them how to stop this one."),
    spine.Finding(
        "finding.process.description_unassigned", "Process",
        "The organization said tools need a plain-language description and "
        "no description procedure is in force",
        "You said [all tools / only public-facing ones] need a "
        "plain-language description. Nothing here says who writes one or "
        "who approves it."),
    spine.Finding(
        "finding.process.training_unrecorded", "Process",
        "The organization said staff are trained before they get access, "
        "and a record at or past Deploy has no training procedure attached "
        "and no training recorded",
        "You said staff are trained before they get access. Nothing here "
        "records that for this one."),
    spine.Finding(
        "finding.process.superseded_still_followed", "Process",
        "A procedure is marked replaced and one or more records still point "
        "at it rather than at the version in force",
        "You replaced this on [date]. [n] records still point at the old "
        "one."),
    spine.Finding(
        "finding.process.procedure_no_owner", "Process",
        "A procedure is in force with no owning role recorded",
        "This is in force and nobody owns it. An unowned procedure is a "
        "document, not a procedure."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}

#: Two of the spine's shared findings are *raised* here rather than merely
#: rendered. Their ids and their sentences are the spine's and are not
#: rewritten. What belongs here is the trigger, because in both cases it is
#: this surface that holds the thing being contradicted.
RAISES_FROM_THE_SPINE: dict[str, str] = {
    "finding.floor_missing":
        "A floor obligation that binds at the gate in front of a record is "
        "unanswered on that record. At six of the seven gates it is a "
        "finding and nothing else: the record moves, and a condition may be "
        "attached against it. At Deploy the finding is also the sentence "
        "behind the one refusal this application makes. The finding is the "
        "same object in both places; what differs is whether the passage "
        "gets recorded.",
    "finding.description_stale":
        "A version went live on a project later than the day the "
        "plain-language description covering that record was written or "
        "last confirmed. It attaches to the description procedure and to "
        "every record pointing at it, and it names the version and the date "
        "it went live.",
}

#: The finding makes no claim that the description is now wrong. Somebody
#: has to read it and say whether it is still right, and the finding closes
#: when a confirmation is recorded.
DESCRIPTION_STALE_CLAIMS_NOTHING = (
    "This does not say the description is wrong. It says the tool changed "
    "after somebody wrote it. Read it and confirm it, and this closes.")

#: Rendered here where they attach to a procedure or a passage, and defined
#: once at the spine.
RENDERS_FROM_THE_SPINE = ("finding.consulted_missing",
                          "finding.condition_overdue",
                          "finding.framework_moved",
                          "finding.gap_no_owner",
                          "finding.running_ahead")

#: Rendered here as a count and never as a sentence about a particular
#: person. On a small organisation's first day it will be true of nearly
#: everything they own, which is the honest state of the world.
RUNNING_AHEAD_IS_A_COUNT = True


# ---------------------------------------------------------------------------
# 3C · What deliberately raises nothing
# ---------------------------------------------------------------------------

WILL_NOT_RAISE = (
    "A fallback the organization said it does not test. The framework "
    "accepts that answer, shows one line of consequence, and lets it "
    "stand. This surface counts it and raises nothing. Flagging an answer "
    "the application invited teaches the user to lie to it.",
    "A procedure that looks heavy or light for the size of the "
    "organization. No finding, no note, no suggestion. They set the weight "
    "themselves.",
    "A project that never came in through the written route. Tools found "
    "already running are the normal case and the whole point of the honest "
    "inventory. This application was built for governance that arrives "
    "after the tool did.",
    "Concentration of roles. Three of three hats held by one person is a "
    "plain count on Oversight and is never a finding here.",
    "A project that has been waiting a long time to be picked up. The "
    "waiting line states the fact and stops there.",
    "A recommendation the organization declined. Declining one is a "
    "complete answer, recorded without comment. There is no finding on "
    "this surface, and none anywhere in this application, whose trigger is "
    "a declined recommendation.",
    "A tool with no testing environment. This surface records the answer, "
    "asks what happens instead, and raises nothing.",
)


def findings(rows: list[dict[str, Any]] | None = None, *,
             required: dict[str, str] | None = None,
             records: list[dict[str, Any]] | None = None,
             fallback_cadence: str = "",
             fallback_days: int | None = None,
             wording_lives_in_one_place: bool = False,
             wording_approver: str = "",
             may_stop_it: list[str] | None = None,
             pointing_at: dict[str, int] | None = None
             ) -> list[dict[str, Any]]:
    """Every finding this surface can compute from what is recorded.

    Each keyword is one of the organization's own answers, read in. Where
    one is absent the finding it feeds is not computed, and the absence is
    never shown as missing.
    """
    rows = all_procedures() if rows is None else rows
    required = required or {}
    records = list(records or [])
    pointing_at = pointing_at or {}
    raised: list[dict[str, Any]] = []

    def add(finding_id: str, entry: str, says: str) -> None:
        raised.append({"id": finding_id, "entry": entry, "says": says})

    live = in_force(rows)
    kinds_live = {p.get("kind") for p in live}

    # 3.13 — an unowned procedure is a document, not a procedure.
    for found in live:
        if not found.get("owner"):
            add("finding.process.procedure_no_owner", found["ref"],
                "This is in force and nobody owns it.")

    # 3.1 — the intake route, where their own answer requires one.
    if ROUTE_IN in required and ROUTE_IN not in kinds_live:
        add("finding.process.no_route_in", "",
            BY_OWN_FINDING["finding.process.no_route_in"].says)

    # 3.10 — who writes the description and who approves it.
    if DESCRIPTION in required and DESCRIPTION not in kinds_live:
        # The finding and the ghost row carry the same sentence (3.10 and
        # §5.2a are worded identically). A bare scope phrase is still read.
        said = required[DESCRIPTION]
        if not said.startswith("You said"):
            said = (f"You said {said} need a plain-language description. "
                    f"Nothing here says who writes one or who approves it.")
        add("finding.process.description_unassigned", "", said)

    # 3.6 — only where they said fallbacks are tried on a schedule. Where
    # they said they do not test them, nothing is raised.
    if fallback_cadence:
        for found in of_kind(MANUAL_WAY, rows):
            # "It cannot be tried without doing real harm" is an answer this
            # form offers, and flagging an answer it invited would teach the
            # user to lie to it.
            if found.get("ever_tried") == TRIED_CANNOT:
                continue
            last = str(found.get("last_tried") or "")[:10]
            if not last:
                add("finding.process.fallback_never_tried", found["ref"],
                    f"You said the backup gets tried {fallback_cadence}. "
                    f"This one has never been tried.")
            elif fallback_days:
                try:
                    gone = (datetime.fromisoformat(_today()) -
                            datetime.fromisoformat(last)).days
                except ValueError:
                    gone = None
                if gone is not None and gone > fallback_days:
                    add("finding.process.fallback_never_tried", found["ref"],
                        f"You said the backup gets tried {fallback_cadence}. "
                        f"This one was last tried {last}.")

    # 3.8 — they named who approves the wording.
    if wording_approver:
        for found in of_kind(WORDING, rows):
            if not found.get("approved_by"):
                add("finding.process.wording_unapproved", found["ref"],
                    f"You said {wording_approver} approves the wording. "
                    f"Nothing here records that they did.")

    # 3.12 — a replaced procedure that records still point at.
    for found in rows:
        if found.get("status") != REPLACED:
            continue
        left = pointing_at.get(found["ref"], 0)
        if left:
            when = found.get("in_force_from") or "a recorded date"
            add("finding.process.superseded_still_followed", found["ref"],
                f"You replaced this on {when}. {left} records still point "
                f"at the old one.")

    # 3.4, 3.5, 3.9, 3.11 — read against the records at or past Deploy.
    for record in records:
        gate = record.get("gate") or ""
        past_deploy = bool(gate) and not spine.before(gate, spine.DEPLOY)
        ref = record.get("ref") or ""

        if past_deploy and record.get("public_facing") and not \
                record.get("route_to_person"):
            add("finding.process.no_route_to_person", ref,
                "You said anyone dealing with this can reach a person "
                "instead. Nothing here says how.")

        # 3.7 — one place for approved wording, and this record has its own.
        if wording_lives_in_one_place and record.get("own_wording"):
            add("finding.process.wording_off_book", ref,
                "You said approved wording lives in one place so everyone "
                "says the same thing. This record has its own.")

        if past_deploy and record.get("fallback_binds") and not \
                record.get("manual_way"):
            # Their own level names, through the mapping, never the tier
            # string the framework's question is phrased in.
            bound = record.get("fallback_levels") or "those levels"
            mine = record.get("level") or "at that level"
            add("finding.process.no_fallback", ref,
                f"You said tools at {bound} need a written way to do the "
                f"job without them. This one is {mine} and does not have "
                f"one.")

        if may_stop_it and record.get("in_use") == spine.IN_USE_YES and not \
                record.get("turn_off"):
            add("finding.process.turnoff_unwritten", ref,
                f"You named {', '.join(may_stop_it)} as able to stop a tool "
                f"without waiting for a meeting. Nothing here tells them "
                f"how to stop this one.")

        if past_deploy and TRAINING in required and not \
                record.get("training"):
            add("finding.process.training_unrecorded", ref,
                "You said staff are trained before they get access. Nothing "
                "here records that for this one.")

    return raised


# ===========================================================================
# 4 · The standing check
# ===========================================================================

#: Runs once a night against every procedure marked in force. It writes
#: nothing except the four counts and a per-procedure result. It never
#: changes a status, never marks anything stale on its own authority, and
#: never sends anything anywhere.
CHECK_WRITES_NOTHING = True

CHECK_THEM_ALL_NOW = "Check them all now"

WATCH_COUNTS = ("Watched", "Current", "Past their date",
                "Overtaken by something")

#: Every trigger available is an option the organisation ticked, offered
#: again per procedure and switchable off there. An organisation that did
#: not tick vendor changes is never offered a vendor trigger and never gets
#: a vendor-change alert. An organisation that ticked nothing gets the
#: counter and a permanent zero, which is the honest reading of their own
#: answers.
TRIGGERS: dict[str, str] = {
    "Whenever the vendor changes the tool it covers":
        "a vendor changed the tool this procedure covers",
    "Whenever the vendor stops supporting it":
        "a vendor stopped supporting it",
    "After any incident":
        "an incident was recorded against a record pointing at this "
        "procedure",
    "When a law or rule changes": "a law or rule change was recorded",
    "When the contract behind it ends":
        "the contract behind a tool this procedure covers ended",
    "When its funding is not renewed": "funding for it was not renewed",
}

ON_A_DATE = "On a date I set"
NO_LOOK_AGAIN = "It does not need looking at again"

#: Two events earlier drafts counted are gone: *the framework was amended*
#: and *a record's scrutiny level moved*. Neither is an option anywhere in
#: the framework, and a count the user can neither switch on nor switch off
#: would be this application supplying a number of its own.
NOT_TRIGGERS = ("the framework was amended",
                "a record's scrutiny level moved")

#: Two of the framework's own triggers are about the tool rather than the
#: instruction — *it failed its performance review* and *something better is
#: available*. Those belong to the project on Projects. They are not offered
#: here and their absence is never shown as missing.
BELONGS_TO_THE_PROJECT = ("it failed its performance review",
                          "something better is available")


def standing_check(rows: list[dict[str, Any]] | None = None, *,
                   fired: dict[str, list[str]] | None = None,
                   today: str = "") -> dict[str, Any]:
    """The four counts, and a per-procedure result.

    `fired` maps a procedure reference to the triggers that have fired
    against it since it was last confirmed. The events are things a person
    writes down; nothing here is watching a vendor, the statute book or a
    budget office. The count moves when somebody records one and not before.
    """
    rows = all_procedures() if rows is None else rows
    fired = fired or {}
    today = today or _today()

    watched = current = past = overtaken = 0
    results: list[dict[str, Any]] = []

    for found in in_force(rows):
        triggers = [t for t in (found.get("look_again") or [])
                    if t != NO_LOOK_AGAIN]
        has_date = bool(found.get("look_again_date"))
        if not triggers and not has_date:
            continue
        watched += 1

        result: dict[str, Any] = {"procedure": found["ref"], "state": []}
        if has_date and str(found["look_again_date"])[:10] < today:
            past += 1
            result["state"].append("Past their date")
        since = fired.get(found["ref"]) or []
        if since:
            overtaken += 1
            result["state"].append("Overtaken by something")
            result["fired"] = since
        if not result["state"]:
            current += 1
            result["state"].append("Current")
        results.append(result)

    return {
        "watched": watched,
        "current": current,
        "past_their_date": past,
        "overtaken": overtaken,
        "results": results,
        "control": CHECK_THEM_ALL_NOW,
        "honest_limit": WHAT_THE_CHECK_CANNOT_SEE,
    }


#: Shown under the counts.
WHAT_THE_CHECK_CANNOT_SEE = (
    "This checks the dates and the events the app recorded itself. It "
    "cannot see whether the document at that address still exists, whether "
    "the person named in it still works here, or whether the words a member "
    "of the public actually reads on your website match the wording "
    "recorded here. Somebody has to look at those, and this will keep "
    "saying so rather than showing a tick that meant nothing.\n\n"
    "Two of the events above are things a person writes down rather than "
    "things this application observes: a law or rule changing, and funding "
    "not being renewed. The count moves when somebody records one and not "
    "before. Nothing here is watching the statute book or your budget "
    "office.")


# ===========================================================================
# 5 · The list view
# ===========================================================================

#: Seven columns, read-only.
COLUMNS = (
    ("What it is called", "The name, in the organization's words. Links to "
                          "the procedure."),
    ("Kind", "One of the twelve kinds, shown as its full phrase rather than "
             "an abbreviation."),
    ("Where it applies", "Gate names and the organization's own scrutiny "
                         "level names. Every gate and Every level are "
                         "values rather than blanks."),
    ("Who owns it", "A role title. Where none is recorded, the cell reads "
                    "Nobody named and links to the finding."),
    ("Status", "In force / Drafted, not adopted / Replaced / Withdrawn. "
               "Text, always; never a color alone."),
    ("Last confirmed", "A date, or Never confirmed."),
    ("Records pointing at it", "A count. Zero renders as Nothing points at "
                               "this yet, because zero on a newly written "
                               "procedure means something different from "
                               "zero on a three-year-old one."),
)

FILTERS = (
    "Kind",
    "Gate",
    "Scrutiny level, in their own level names",
    "Status",
    "Owner role",
    "Last confirmed — never / within a year / longer than a year / past its "
    "date",
    "Records pointing at it — any / none",
    "Only the ones nothing points at",
)

#: Filters are checkboxes in a labelled group rather than chips that vanish
#: when applied. The applied set is stated in a sentence above the table and
#: cleared with one control.
FILTERS_ARE_CHECKBOXES = True

#: The default order puts what is missing at the top.
SORT_ORDER = (
    "kinds required and not written, as ghost rows",
    "in force and never confirmed",
    "in force and past the date its owner set",
    "everything else alphabetically by name",
)


def owner_cell(found: dict[str, Any]) -> str:
    return found.get("owner") or "Nobody named"


def pointing_cell(count: int) -> str:
    return str(count) if count else NOTHING_POINTS_AT_THIS


def confirmed_cell(found: dict[str, Any]) -> str:
    return found.get("confirmed_on") or NEVER_CONFIRMED


# ---------------------------------------------------------------------------
# 5.2 · Ghost rows
# ---------------------------------------------------------------------------

#: A kind the organisation's own answers require, with nothing in force,
#: appears as a row with the kind name, the reason it is required in their
#: own words, and a single action. It is a row rather than a banner because
#: it belongs in the same list as everything else, and because a person
#: scanning a table should not have to read a second thing to find out what
#: is missing.
WRITE_IT = "Write it"

#: One ghost row per scrutiny level for the checklist kind, never one per
#: gate per level. A four-level organisation would otherwise open the
#: register to twenty-eight ghost rows on its first morning and close it.
#: The row names the level and lists the gates that have no checklist at it.
ONE_ROW_PER_LEVEL = True


def ghost_rows(rows: list[dict[str, Any]] | None = None, *,
               required: dict[str, str] | None = None,
               levels_needing_a_checklist: dict[str, list[str]] | None = None
               ) -> list[dict[str, Any]]:
    """The requirement rule, rendered.

    `required` maps a requirable kind to the sentence its ghost row carries,
    in the organization's own words. Nothing here invents a requirement, and
    the four kinds that are never required never appear.
    """
    rows = all_procedures() if rows is None else rows
    required = required or {}
    kinds_live = {p.get("kind") for p in in_force(rows)}
    ghosts: list[dict[str, Any]] = []

    for kind, says in required.items():
        if kind in NEVER_REQUIRED or kind not in CAN_BE_REQUIRED:
            continue
        if kind == CHECKLIST:
            for level, gates in (levels_needing_a_checklist or {}).items():
                if gates:
                    ghosts.append({"kind": kind, "level": level,
                                   "gates": list(gates), "says": says,
                                   "action": WRITE_IT, "ghost": True})
            continue
        if kind not in kinds_live:
            ghosts.append({"kind": kind, "says": says, "action": WRITE_IT,
                           "ghost": True})
    return ghosts


# ---------------------------------------------------------------------------
# 5.4 · The empty state
# ---------------------------------------------------------------------------

def empty_state(*, already_using: bool = False, project: str = "",
                no_technology: bool = False) -> str:
    """Four variants, three of them chosen from the organization's own
    answers. None of them treats an existing tool as a fault."""
    if no_technology:
        return ("Nothing written down yet. Start with how the work gets "
                "done when the tool is off. You said there is no technology "
                "function here, which makes the written fallback the thing "
                "you actually rely on.")
    if project:
        return (f"Nothing written down yet. You told us about {project}. "
                f"Start with how somebody proposes a tool, and then walk "
                f"that one through it.")
    if already_using:
        return ("Nothing written down yet. You said people may already be "
                "using AI tools on their own. Start with how somebody tells "
                "you about one, because until that route exists you will "
                "keep finding out last.")
    return ("Nothing written down yet. Start with how somebody tells you "
            "they want to use an AI tool. Every other procedure here is "
            "downstream of that one.")


# ===========================================================================
# 5.5 · The route in, rendered
# ===========================================================================

#: Any signed-in person, in any hat. No delegation check and no approval to
#: get in. An account is the whole of the restriction, and it is
#: authenticated rather than public. The spine grants no-role submission for
#: exactly one thing, the incident report on Integrity.
WHO_MAY_RAISE = "Any signed-in person, in any hat"

#: Where an organisation wants a genuinely public route in, it goes into the
#: spine first, with its own rule about what an anonymous visitor may see.
#: This surface does not open that door on its own authority — behind an
#: account the holdings list is ordinary; in front of one, the same list
#: would be a directory of what is worth taking.
NOT_OPEN_TO_THE_WORLD = (
    "The route in is behind an account. The one thing this application "
    "accepts from somebody with no login is an incident report.")

#: The walkthrough creates the project, and Projects owns that write.
PROJECTS_WRITES_THE_RECORD = (
    "The walkthrough on Projects creates the project. A code path here "
    "that creates one is the same class of defect as one that writes "
    "state.")

#: Default rows. Row one is fixed — its two fields, its required flag and
#: its position at the top — because a route that does not say who came in
#: through it produces a record nobody can follow up. The rest are each
#: editable, removable and reorderable.
DEFAULT_ASKS: tuple[dict[str, Any], ...] = (
    {"question": "Who is asking, and how do we reach you?",
     "type": "short text", "required": True, "fixed": True,
     "help": "A name and one way to reach you — an extension, an email "
             "address, or where you sit. Whoever picks this up will have a "
             "question about it, and this application does not send "
             "messages, so somebody has to be able to find you."},
    {"question": "Is anything already running for this?",
     "type": "yes/no/not known", "required": False, "fixed": False,
     "help": "Answer honestly. A tool nobody approved is the ordinary way "
             "this starts and nothing here treats it as a fault."},
    {"question": "Does this touch a program another government gave you "
                 "or pays for?",
     "type": "single select", "required": False, "fixed": False,
     "conditional": "only where the organization runs one",
     "help": "This changes the scrutiny level and adds a notification party "
             "later, so it is asked at the way in rather than discovered "
             "later."},
)

INPUT_TYPES = ("short text", "long text", "single select", "multi select",
               "date", "role", "link to a holding", "link to a vendor",
               "yes/no/not known")

#: A route that takes forty minutes is a route people walk past, and then
#: you find the tool later.
THREE_QUESTIONS = (
    "Only the first row is required, and it fills itself in. A route that "
    "takes forty minutes is a route people walk past, and then you find the "
    "tool later.")

#: What is deliberately not asked at the route in, and where it went. An
#: earlier draft asked what the tool would do, who would supply it and what
#: it would cost at the head of the way in — which invited exactly the
#: answer the walkthrough is built to walk somebody back from.
ASKED_ELSEWHERE = {
    "What is the problem, in your own words":
        "question one of the walkthrough on Projects; asking it twice would "
        "produce two descriptions that disagree",
    "What the tool would do, who would supply it, what it would cost":
        "the optional parked-idea block on Projects, asked after the "
        "problem rather than before it",
    "Who would be accountable for it":
        "the end of Identify, because Floor 7 binds there and a name given "
        "at the front door by somebody without the authority to give it is "
        "a name nobody honors",
    "What you are required to do that this helps with":
        "read from Vision at the end of Identify",
    "Anything else somebody should know":
        "question nine of the walkthrough",
}


def what_they_are_told(*, record_id: str, shape: str, cadence: str = "",
                       their_words: str = "") -> str:
    """What the person sees at the end of the walkthrough.

    Specified once, here; Projects renders it. Where the organization has
    rewritten it, their words render. The identifier token and the control
    are preserved whatever they write around it, because the identifier is
    the only way that person has of finding out what happened.
    """
    if their_words:
        return their_words.replace("[record id]", record_id)
    middle = (f"It goes to {shape}; there is no set meeting, so it goes to "
              f"them now."
              if cadence.strip().lower().startswith("as requests")
              else f"It goes to {shape}, who look at AI matters {cadence}.")
    return (f"Written down. This is now on the list as {record_id}. "
            f"{middle} Write that identifier down, or follow it now: this "
            f"application sends no messages and no email, so the way to "
            f"find out what they decided is to open the record.")


OPEN_THE_RECORD = "Open the record"


# ===========================================================================
# 8 · Gaps
# ===========================================================================

#: Every unanswered field on this surface produces a gap record rather than
#: a blank, in the shared shape: the framework question it was owed to, the
#: field, the answer given, a required role owner, and a date or *no date
#: set*. An unanswered field renders as the gap rather than as empty.
GAP_ANSWERS = ("We are not sure", "We don't know", "We have not asked")

HANDLE_INTERNALLY = "Handle it internally"
NEED_OUTSIDE_HELP = "We would need outside help for this"

#: A gap with no owner at all is not a valid gap.
NO_OWNER_IS_NOT_A_GAP = True


# ===========================================================================
# Scope
# ===========================================================================

#: What this surface is, in one line, where a person will read it.
SCOPE = (
    "This holds the written instructions: what has to exist before "
    "something moves, the words the public sees, how the work gets done "
    "when the tool is off, and how to turn it off. It does not run "
    "anything, it does not create a project, and it does not write a "
    "record's state. It cannot stop anyone using a tool. Its only "
    "enforcement is that a record cannot be recorded as having passed "
    "Deploy while one of the six things that bind there is unanswered.")


def report(*, required: dict[str, str] | None = None,
           records: list[dict[str, Any]] | None = None,
           pointing_at: dict[str, int] | None = None,
           levels_needing_a_checklist: dict[str, list[str]] | None = None,
           waiting: list[dict[str, Any]] | None = None,
           route_exists: bool = True, ever_arrived: bool = True
           ) -> dict[str, Any]:
    rows = all_procedures()
    raised = findings(rows, required=required, records=records,
                      pointing_at=pointing_at)
    return {
        "procedures": rows,
        "counters": counters(rows, required=required),
        "counter_names": list(COUNTER_NAMES),
        "waiting_line": waiting_line(waiting, route_exists=route_exists,
                                     ever_arrived=ever_arrived),
        "standing_check": standing_check(rows),
        "raised": raised,
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "raises_from_the_spine": dict(RAISES_FROM_THE_SPINE),
        "renders_from_the_spine": list(RENDERS_FROM_THE_SPINE),
        "will_not_raise": list(WILL_NOT_RAISE),
        "clean_state": CLEAN_STATE,
        "ghost_rows": ghost_rows(
            rows, required=required,
            levels_needing_a_checklist=levels_needing_a_checklist),
        "kinds": list(KINDS),
        "can_be_required": list(CAN_BE_REQUIRED),
        "never_required": dict(NEVER_REQUIRED),
        "statuses": list(STATUSES),
        "columns": [{"name": n, "contents": c} for n, c in COLUMNS],
        "filters": list(FILTERS),
        "sort_order": list(SORT_ORDER),
        "empty_state": empty_state(),
        "deploy": checklist_for(spine.DEPLOY),
        "six_bind_here": SIX_BIND_HERE,
        "under_the_six": UNDER_THE_SIX,
        "only_the_name": ONLY_THE_NAME,
        "version_rule": VERSION_RULE,
        "route_in": {"who": WHO_MAY_RAISE, "asks": [dict(a) for a in
                                                    DEFAULT_ASKS],
                     "help": THREE_QUESTIONS,
                     "not_public": NOT_OPEN_TO_THE_WORLD},
        "scope": SCOPE,
    }


# ===========================================================================
# 9 · Framework read-back — the organisation's own answers, read in
# ===========================================================================

#: The gates a checklist can be required at. Govern is the framework itself,
#: which is adopted rather than passed.
CHECKLIST_GATES = tuple(g for g in spine.GATE_ORDER if g != spine.GOVERN)

#: 6.5.1 · each re-look trigger, and the framework answers that offer it.
#: Only what they ticked at 5.5 or 9.7 is ever offered.
_TRIGGER_FROM = {
    "Whenever the vendor changes the tool it covers":
        (("risk.revisit", "vendor_change"),),
    "Whenever the vendor stops supporting it":
        (("watch.triggers", "unsupported"),),
    "After any incident":
        (("risk.revisit", "incident"), ("watch.triggers", "incident")),
    "When a law or rule changes":
        (("risk.revisit", "law_change"), ("watch.triggers", "law")),
    "When the contract behind it ends": (("watch.triggers", "contract"),),
    "When its funding is not renewed": (("watch.triggers", "funding"),),
}

_CADENCE_DAYS = {"annual": 366, "biannual": 183}


def _lower_first(text: str) -> str:
    text = str(text or "")
    return text[:1].lower() + text[1:] if text else text


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    """Everything Process reads from Module One, in one pass. Where an answer
    is missing its input is absent, and nothing stands in for it."""
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def extras(key: str) -> dict[str, Any]:
        return m.value_of(answers, key)[1]

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

    # 5.2 · their level names, lowest first.
    levels = m.level_names(answers)
    names = [n for _, n in levels]
    out["levels"] = names
    rb["levels"] = (f"You chose {len(names)} levels and called them "
                    f"{', '.join(names[:-1]) + ' and ' + names[-1] if len(names) > 1 else names[0]}. "
                    f"Those are the only ones this will ever show."
                    if names else "")

    # 5.3 · what has to exist on paper at each level.
    tiers = value("risk.tiers") if asked("risk.tiers") else {}
    paper = {}
    for tier_value, name in levels:
        written = str(((tiers or {}).get(tier_value) or {}).get(
            "written") or "").strip()
        if written:
            paper[name] = written
    out["paper"] = paper

    # 4.6 · the delegation.
    without = listed("who.without")
    out["delegation"] = without
    out["everything_flows_through"] = "nothing" in without
    rb["delegation"] = (
        "You said nothing moves without whoever decides."
        if out["everything_flows_through"] else
        "You said these can move forward without whoever decides: " +
        "; ".join(_lower_first(label_of("who.without", w)) for w in without)
        + "." if without else "")

    # 4.1 · 4.3 · 4.5 · who decides, the tiebreaker and the cadence.
    shape = value("who.shape")
    out["shape"] = _lower_first(label_of("who.shape", shape)) if shape else ""
    tiebreak = str(value("who.tiebreak") or "").strip()
    rb["adopted"] = (f"You said {out['shape'] or 'somebody'} decides"
                     + (f", and that {tiebreak} has the final say when there "
                        f"is disagreement." if tiebreak else ".")
                     if shape else "")
    cadence = value("who.cadence")
    out["cadence"] = _lower_first(label_of("who.cadence", cadence)) \
        if cadence else ""

    # 4.7 · where decisions are written.
    place = str(value("who.record") or "").strip()
    rb["where_it_lives"] = (f"You said decisions get written down in {place}. "
                            f"If this lives there too, say so."
                            if place else "")
    out["decision_place"] = place

    # 1.6 · open records.
    out["open_records"] = value("org.open_records") == "yes"

    # 4.10 · the framework comes back.
    review = value("who.review")
    rb["review"] = (f"You said the framework itself comes back "
                    f"{_lower_first(label_of('who.review', review))}. A "
                    f"procedure written under it is worth a look then."
                    if review else "")

    # 5.5 · 9.7 · the re-look triggers offered.
    offered = []
    for trigger, sources in _TRIGGER_FROM.items():
        if any(opt in listed(key) for key, opt in sources):
            offered.append(trigger)
    out["triggers"] = offered
    revisit = [label_of("risk.revisit", r) for r in listed("risk.revisit")]
    keep = [label_of("watch.triggers", t) for t in listed("watch.triggers")]
    rb["triggers"] = " ".join(filter(None, [
        f"You said the risk level gets looked at again: "
        f"{', '.join(_lower_first(r) for r in revisit)}." if revisit else "",
        f"You said a keep-or-retire review is triggered by: "
        f"{', '.join(_lower_first(k) for k in keep)}." if keep else ""]))

    # 6.3a–d · disclosure.
    out["places"] = [label_of("floor.disclose_where", p)
                     for p in listed("floor.disclose_where")]
    reach = str(value("floor.reach_human") or "").strip()
    out["reach_human"] = reach
    who_words = str(value("floor.disclose_who") or "").strip()
    out["wording_roles"] = who_words
    out["wording_home"] = str(value("floor.disclose_home") or "").strip()
    rb["wording_roles"] = f"You said: {who_words}." if who_words else ""

    # 6.5a · 6.5b · the manual way, through the level mapping.
    scope = value("floor.fallback_scope")
    tier = {"all": ALL_TOOLS, "mod_high": MIDDLE_AND_UP,
            "high": TOP_ONLY}.get(scope, "")
    out["fallback_tier"] = tier
    out["fallback_levels"] = levels_that_bind(tier, names) if tier else []
    out["fallback_phrase"] = level_phrase(tier, names) if tier else ""
    tested = value("floor.fallback_tested")
    out["fallback_cadence"] = {"annual": "once a year",
                               "biannual": "twice a year"}.get(tested, "")
    out["fallback_days"] = _CADENCE_DAYS.get(tested)
    rb["fallback_tried"] = (
        "You said you write the backup down and do not test it. This will "
        "show as never tried, and it will not be flagged."
        if tested == "never" else
        f"You said the backup gets tried {out['fallback_cadence']}."
        if out["fallback_cadence"] else "")

    # 6.8a · the plain-language description.
    plain = value("floor.plain_scope")
    out["description_scope"] = {"all": "all tools",
                                "higher_risk": "only higher-scrutiny tools"
                                }.get(plain, "")

    # 6.9 · training first.
    out["training_first"] = "training" in listed("floor.optional")

    # 10.5 · who can stop a tool without waiting.
    stoppers = value("bad.stopper") or []
    out["stoppers"] = [str(r.get("role") or "").strip() for r in stoppers
                       if isinstance(r, dict) and str(r.get("role") or "").strip()]

    # 9.4 · who confirms.
    who = str(value("watch.who") or "").strip()
    rb["confirm"] = f"You said {who}." if who else ""

    # 8.3 · the testing-environment term.
    terms = listed("proc.terms")
    rb["staging_term"] = (
        "You said a testing or staging environment is one of the terms you "
        "require in every agreement. Whether the term is present or absent is "
        "recorded on Vendors; this asks whether one actually exists for this "
        "tool." if "staging" in terms else "")

    # 1.5 · delegated programmes, for the conditional route-in question.
    out["delegated"] = value("org.delegated") == "yes"

    # 1.4 · functions that exist, for the "who confirms it" picker.
    functions = value("org.functions")
    functions = functions if isinstance(functions, dict) else {}
    out["functions"] = [o.label for o in m.FUNCTIONS
                        if functions.get(o.value) not in (None, "", "none")]
    out["no_technology"] = functions.get("it") == "none"

    # 2.1 · 2.5 · the empty state.
    used = listed("have.used")
    out["already_using"] = bool(set(used) & {"informal"}) or \
        (asked("have.used") and "unknown" in (value("have.used") or []))
    project = ""
    if value("have.project") == "yes":
        for held in extras("have.project").values():
            if isinstance(held, str) and held.strip():
                project = held.strip()
                break
    out["project"] = project

    # 4.2 · the seats, for owner suggestions.
    seats = value("who.seats") or []
    out["seats"] = [str(r.get("role") or r.get("title") or "").strip()
                    for r in seats if isinstance(r, dict)
                    and str(r.get("role") or r.get("title") or "").strip()]
    return out


def required_kinds(inputs: dict[str, Any]) -> dict[str, str]:
    """§5.2a · the whole requirement rule. Each kind the organization's own
    answers require, and the sentence its ghost row carries. The checklist
    kind is handled per level, in `surface`."""
    req: dict[str, str] = {}
    if inputs.get("everything_flows_through"):
        req[ROUTE_IN] = ("You said nothing moves without your framework and "
                         "process. Nothing here says how something enters it.")
    if inputs.get("wording_home"):
        req[WORDING] = ("You said approved wording lives in one place so "
                        "everyone says the same thing. There is no wording "
                        "here to point at.")
    # 6.3b is required with no opt-out.
    reach = inputs.get("reach_human", "")
    req[ROUTE_TO_PERSON] = (
        "You said anyone dealing with a tool can reach a person instead"
        + (f", and you wrote {reach}" if reach else "")
        + ". Nothing here says how.")
    if inputs.get("fallback_tier"):
        req[MANUAL_WAY] = (f"You said tools at {inputs['fallback_phrase']} "
                           f"need a written way to do the job without them. "
                           f"There is none here.")
    if inputs.get("stoppers"):
        req[TURN_IT_OFF] = (f"You named {', '.join(inputs['stoppers'])} as "
                            f"able to stop a tool without waiting for a "
                            f"meeting. Nothing here tells them how.")
    if inputs.get("description_scope"):
        req[DESCRIPTION] = (f"You said {inputs['description_scope']} need a "
                            f"plain-language description. Nothing here says "
                            f"who writes one or who approves it.")
    if inputs.get("training_first"):
        req[TRAINING] = ("You said staff are trained before they get access. "
                         "Nothing here says how that happens.")
    return req


def _covers(found: dict[str, Any], record: dict[str, Any]) -> bool:
    """Whether a procedure covers a record, by its own 6.3.4 answer."""
    covers = found.get("covers") or ""
    if covers == "Every record":
        return True
    if covers == "Every record at a level I pick":
        levels = found.get("levels") or []
        return EVERY_LEVEL in levels or record.get("level") in levels
    if covers == "Only the ones I pick":
        return record.get("ref") in (found.get("covered_records") or [])
    return False


COVERS = ("Every record", "Every record at a level I pick",
          "Only the ones I pick", "Nothing yet")


def seed_preview(inputs: dict[str, Any]) -> list[dict[str, Any]]:
    """What the seeding offer would write — shown before anything is.

    One route in with the default questions, one checklist per scrutiny
    level pre-filled from what they said has to exist on paper at that
    level, and one update-testing route, empty. Every one arrives Drafted,
    not adopted, so somebody has to adopt it. Nobody reads a register that
    filled itself in.
    """
    asks = [dict(a) for a in DEFAULT_ASKS
            if not a.get("conditional") or inputs.get("delegated")]
    out = [{"name": "How somebody proposes a tool", "kind": ROUTE_IN,
            "asks": asks, "gates": [spine.IDENTIFY], "covers": "Every record"}]
    for level, written in (inputs.get("paper") or {}).items():
        items = [{"item": line.strip(" -•\t"), "confirms": "",
                  "consequence": SHOULD_EXIST}
                 for line in written.replace(";", "\n").split("\n")
                 if line.strip(" -•\t")]
        out.append({"name": f"What has to exist at {level}",
                    "kind": CHECKLIST, "items": items, "gates": [EVERY_GATE],
                    "levels": [level], "covers": "Every record at a level I pick"})
    out.append({"name": "How an update gets tried before it goes live",
                "kind": TRY_AN_UPDATE, "gates": [spine.TEST, spine.DEPLOY],
                "covers": "Every record"})
    return out


def seed(inputs: dict[str, Any], *, actor: Any) -> dict[str, Any]:
    made = []
    for row in seed_preview(inputs):
        got = write(actor=actor, status=DRAFTED, **row)
        if got.get("ok"):
            made.append(got["procedure"]["ref"])
    _log("event.procedures_seeded", actor, {"procedures": made})
    return {"ok": True, "made": made}


def surface(*, answers: dict[str, Any] | None,
            projects: list[dict[str, Any]] | None = None,
            incidents: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """The whole Process screen, read once."""
    inputs = framework_inputs(answers)
    rows = all_procedures()
    projects = [p for p in (projects or []) if p.get("ref")]
    required = required_kinds(inputs)
    live = in_force(rows)

    # Ghost rows: one per level for the checklist kind, listing the gates
    # with no checklist in force at that level.
    ghosts = ghost_rows(rows, required=required)
    for level, written in (inputs.get("paper") or {}).items():
        missing = []
        for gate in CHECKLIST_GATES:
            covered = any(
                (not p.get("gates") or gate in p["gates"] or
                 EVERY_GATE in p["gates"]) and
                (not p.get("levels") or level in p["levels"] or
                 EVERY_LEVEL in p["levels"])
                for p in of_kind(CHECKLIST, rows))
            if not covered:
                missing.append(spine.BY_GATE[gate].name)
        if missing:
            ghosts.append({
                "kind": CHECKLIST, "level": level, "gates": missing,
                "says": (f"You said {_lower_first(written.rstrip('. '))} has "
                         f"to exist before approval at {level}. No checklist "
                         f"here says what that is, at {', '.join(missing)}."),
                "action": WRITE_IT, "ghost": True})

    # What each project has pointing at it, by each procedure's own coverage.
    kinds_for: dict[str, set[str]] = {}
    pointing: dict[str, int] = {}
    for found in rows:
        count = 0
        for record in projects:
            if _covers(found, record) or record["ref"] in (
                    found.get("covered_records") or []):
                count += 1
                if found.get("status") == IN_FORCE:
                    kinds_for.setdefault(record["ref"], set()).add(
                        found.get("kind"))
        pointing[found["ref"]] = count

    records = []
    for p in projects:
        kinds = kinds_for.get(p["ref"], set())
        records.append({
            "ref": p["ref"], "gate": p.get("gate", ""),
            "level": p.get("level", ""), "in_use": p.get("in_use"),
            "fallback_binds": bool(inputs["fallback_levels"]) and (
                inputs["fallback_levels"] == [EVERY_LEVEL] or
                p.get("level") in inputs["fallback_levels"]),
            "fallback_levels": inputs["fallback_phrase"],
            "manual_way": MANUAL_WAY in kinds,
            "turn_off": TURN_IT_OFF in kinds,
            "training": TRAINING in kinds,
            "route_to_person": ROUTE_TO_PERSON in kinds,
            # The disclosure answer on the project: the public uses it, or
            # sees what it produces.
            "public_facing": str((p.get("tool") or {}).get("public_facing")
                                 or "") in ("yes", "output"),
            # Typed in free-hand rather than pointing at a wording procedure.
            "own_wording": bool(str((p.get("tool") or {}).get(
                "disclosure_text") or "").strip()) and not (
                p.get("tool") or {}).get("disclosure_ref"),
        })

    raised = findings(rows, required=required, records=records,
                      fallback_cadence=inputs["fallback_cadence"],
                      fallback_days=inputs["fallback_days"],
                      wording_lives_in_one_place=bool(inputs["wording_home"]),
                      wording_approver=inputs["wording_roles"],
                      may_stop_it=inputs["stoppers"], pointing_at={
                          r["ref"]: len(r.get("covered_records") or [])
                          for r in rows if r.get("status") == REPLACED})
    for ghost in ghosts:
        if ghost["kind"] == CHECKLIST:
            raised.append({"id": "finding.process.no_checklist_for_level",
                           "entry": "", "says": ghost["says"]})

    # 4 · the standing check, fed by what a person recorded.
    fired: dict[str, list[str]] = {}
    recorded = events()
    for found in live:
        since = str(found.get("confirmed_on") or found.get("written_on")
                    or "")[:10]
        triggers = found.get("look_again") or []
        hits = []
        for ev in recorded:
            if ev["trigger"] in triggers and ev["on"][:10] > since:
                hits.append(RECORDABLE_EVENTS[ev["trigger"]])
        covered = {r["ref"] for r in projects if _covers(found, r)}
        if "Whenever the vendor changes the tool it covers" in triggers:
            for r in projects:
                if r["ref"] in covered and any(
                        str(v.get("live_on") or v.get("opened") or "")[:10] > since
                        for v in (r.get("versions") or []) if isinstance(v, dict)):
                    hits.append("A vendor changed a tool this covers")
                    break
        if "After any incident" in triggers:
            if any(i.get("project") in covered and
                   str(i.get("written_down") or "")[:10] > since
                   for i in (incidents or [])):
                hits.append("An incident was recorded against a record this covers")
        if hits:
            fired[found["ref"]] = hits

    waiting = [p for p in projects if p.get("route")
               and p.get("gate") == spine.IDENTIFY
               and p.get("state") == spine.PROPOSED]
    route_exists = bool(of_kind(ROUTE_IN, rows))
    count = counters(rows, required=required)
    count["required_not_written"] = len(ghosts)

    listed = []
    for found in rows:
        listed.append({**found,
                       "owner_shown": owner_cell(found),
                       "confirmed_shown": confirmed_cell(found),
                       "pointing": pointing.get(found["ref"], 0),
                       "pointing_shown": pointing_cell(
                           pointing.get(found["ref"], 0)),
                       "where_shown": ", ".join(
                           [g if g in (EVERY_GATE, NO_GATE)
                            else spine.BY_GATE[g].name if g in spine.BY_GATE
                            else g for g in (found.get("gates") or [])]
                           + (found.get("levels") or []))})

    return {
        "counters": count,
        "counter_names": list(COUNTER_NAMES),
        "waiting_line": waiting_line(
            waiting, route_exists=route_exists,
            ever_arrived=any(p.get("route") for p in projects)),
        "raised": raised,
        "clean_state": CLEAN_STATE,
        "standing_check": standing_check(rows, fired=fired),
        "ghosts": ghosts,
        "procedures": listed,
        "empty_state": empty_state(already_using=inputs["already_using"],
                                   project=inputs["project"],
                                   no_technology=inputs["no_technology"]),
        "seed": seed_preview(inputs) if not rows else [],
        # The tier key is internal. Its string carries a level name the
        # organisation may never have written, so it never leaves the server.
        "inputs": {k: v for k, v in inputs.items() if k != "fallback_tier"},
        "projects": [{"ref": p["ref"], "name": p.get("name", ""),
                      "level": p.get("level", "")} for p in projects],
        "gates": [{"id": g.id, "name": g.name} for g in spine.GATES],
        "options": {
            "kinds": list(KINDS), "statuses": list(STATUSES),
            "covers": list(COVERS), "consequences": list(CONSEQUENCES),
            "tried": list(TRIED_ANSWERS), "input_types": list(INPUT_TYPES),
            "triggers": inputs["triggers"],
            "recordable": list(RECORDABLE_EVENTS),
            "every_gate": EVERY_GATE, "no_gate": NO_GATE,
            "every_level": EVERY_LEVEL,
            "turning_off": ["The whole tool stops",
                            "Access is taken away from the people using it",
                            "This version stops and the one before it comes back",
                            "We are not sure"],
            "yes_no_unsure": ["Yes", "No", "We are not sure"],
        },
        "locked": [{"floor": f, "says": s} for f, s in LOCKED_AT_DEPLOY],
        "copy": {
            "only_the_name": ONLY_THE_NAME, "name": NAME_GUIDANCE,
            "steps": STEPS_GUIDANCE, "owner": OWNER_GUIDANCE,
            "nothing_private": NOTHING_IS_PRIVATE
            if inputs["open_records"] else "",
            "version_rule": VERSION_RULE, "six": SIX_BIND_HERE,
            "under_six": UNDER_THE_SIX, "consequence": CONSEQUENCE_GUIDANCE,
            "outside_deploy": OUTSIDE_DEPLOY, "asks_help": THREE_QUESTIONS,
            "check_cannot": WHAT_THE_CHECK_CANNOT_SEE, "scope": SCOPE,
            "what_they_are_told": what_they_are_told(
                record_id="[record id]",
                shape=inputs["shape"] or "whoever decides",
                cadence=inputs["cadence"]),
            "moving": MOVING_IS_A_CHOICE,
        },
    }
