"""Vision — where you are trying to get to.

**One entry per goal** — an outcome this organization is trying to reach,
and by when. Where they want to be a year from now and five years from now,
in their own words. This surface **owns no gate**.

A goal is not a project, a tool, or a claim about a purchase. A goal
outlives every tool bought in service of it, so it is written down on its
own.

**The tie runs one way.** A project points at a goal; a goal does not own a
project. The read-back here is the portfolio: what is being done about each
thing the organization said it wanted.

**This surface holds no numbers about any tool.** What the work looks like
today, what would count as it having worked, and the measurement afterward
all live on the project — written at Procure alongside the business case, and
read by Measure for the rest of the project's life. An earlier version of
this product made the per-tool claim the unit and kept a before-number here.
That number is now the baseline, on the project. Anything still reading a
before-number from this surface is reading from a surface that no longer
holds one.

**It is the required reader at every sunset.** Retiring something is a
judgment against the goal the tool was bought to serve. The sunset record
is written on the project; this surface is told, shows it, and reads the
final measurement back against that goal.

**A goal with nothing against it is the most useful row on this page.** An
organization that wrote down five goals and has projects against two of them
has learned something. Nothing about that is phrased as a failure, because a
goal nobody is working on may be one that needs no work.

Named `goals` because the unit is the goal, and because `app/vision.py` is
taken by something else — the SCDES funded roadmap and its capability
dependency graph. Different job, same word.

One place where the specification says two things. Section 1 reads "a
project may serve one goal or more goals, or names none"; the builder's
notes read "a project names at most one goal" and say not to build a join
that lets a goal claim a project. The notes govern here because they are
addressed to whoever builds it and carry the reason. Nothing on this surface
writes the tie either way, so `goal_of()` reads a single goal or a list
without forcing the question.
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

FILENAME = "goals.json"
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
    blank: dict[str, Any] = {"goals": {}, "published": {}}
    path = _file()
    if not path.is_file():
        return blank
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return blank
    if not isinstance(held, dict):
        return blank
    held.setdefault("goals", {})
    held.setdefault("published", {})
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
            action=action, target="Vision", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]})
    except Exception:                                         # noqa: BLE001
        pass


def _ref(existing: set[str]) -> str:
    for _ in range(64):
        ref = "GL-" + "".join(
            secrets.choice("23456789BCDFGHJKMNPQRSTVWXYZ") for _ in range(6))
        if ref not in existing:
            return ref
    return "GL-" + secrets.token_hex(5).upper()


# ===========================================================================
# 5.2 · By when
# ===========================================================================

WITHIN_A_YEAR = "Within a year"
WITHIN_FIVE = "Within five years"
LONGER = "Longer than that"
NO_DATE = "No date set"

HORIZONS = (WITHIN_A_YEAR, WITHIN_FIVE, LONGER, NO_DATE)

#: Nearest horizon first. A small organisation plans as far ahead as a large
#: one, so the options never change with headcount.
HORIZON_ORDER = {h: i for i, h in enumerate(HORIZONS)}


# ===========================================================================
# 5.6 · Where it stands
# ===========================================================================

OPEN = "Open"
REACHED = "Reached"
NO_LONGER_WANTED = "No longer what we want"
OVERTAKEN = "Overtaken by something else"

STANDINGS = (OPEN, REACHED, NO_LONGER_WANTED, OVERTAKEN)

#: Closed either way, and still on the list.
CLOSED = (REACHED, NO_LONGER_WANTED, OVERTAKEN)

#: **Where it stands is never computed.** A goal is reached when a person
#: says it is, not when a number crosses a line. This application has no way
#: to know whether an organisation got where it was going.
NEVER_COMPUTED = (
    "A goal is reached when a person says it is, not when a number crosses "
    "a line.")

#: The four states are the record's own status rather than an answer the
#: organisation gives, so this is the one select on the surface that does
#: not gain a *We are not sure* option.
NO_UNSURE_OPTION = OPEN


# ===========================================================================
# 5.1 · The placeholder, by organisation type
# ===========================================================================

#: Where the organisation type is unanswered the clause carrying the example
#: is dropped rather than filled with a word this application chose.
PLACEHOLDERS: dict[str, str] = {
    "State agency or department":
        "Permits decided within the time we publish",
    "County government": "Permits decided within the time we publish",
    "Regional council, authority, or commission":
        "Permits decided within the time we publish",
    "Special district": "Fewer repeat work orders on the same asset",
    "School district or education agency":
        "Every family gets an enrollment answer the same week",
    "City, town, or village":
        "Service calls answered without anybody having to call twice",
}

GOAL_GUIDANCE = ("In your own words, the way you would say it out loud. One "
                 "sentence.")

WOULD_HAVE_TO_BE_TRUE = (
    "How you would know you had got there. This is not a measurement of any "
    "one tool — it is the state of the world you are aiming at.")

OWNER_GUIDANCE = ("A role. The person who would be asked about this at a "
                  "board meeting.")

RESPONSIBILITIES_GUIDANCE = (
    "The program, the service, or the duty. If the honest answer is that "
    "it frees up staff time for something else, write that; keeping people "
    "available for the work only they can do is a purpose.")


def placeholder(organisation_type: str = "") -> str:
    """The example, or nothing at all.

    Returns an empty string where the type has not been answered, so the
    clause carrying the example can be dropped rather than filled with a
    word this application chose.
    """
    return PLACEHOLDERS.get(organisation_type, "")


# ===========================================================================
# The record
# ===========================================================================

ONLY_THE_GOAL = "Only the goal itself is required."


def write(*, goal: str, actor: Any, horizon: str = NO_DATE,
          would_be_true: str = "", owner: str = "",
          responsibilities: str = "", stands: str = OPEN,
          owner_is_also_decider: bool = False,
          extended_to: str = "", gaps: list[str] | None = None
          ) -> dict[str, Any]:
    """One stated goal."""
    if not str(goal or "").strip():
        return {"ok": False, "error": "Write down the goal."}

    with _LOCK:
        held = _read()
        ref = _ref(set(held["goals"]))
        row = {
            "ref": ref,
            "goal": str(goal).strip(),
            "horizon": horizon,
            "would_be_true": str(would_be_true or "").strip(),
            "owner": str(owner or "").strip(),
            # Under twenty-five people the application offers to fold the
            # goal owner into whoever decides, and records that one person
            # holds both.
            "owner_is_also_decider": bool(owner_is_also_decider),
            "responsibilities": str(responsibilities or "").strip(),
            "stands": stands,
            "extended_to": extended_to,
            "gaps": list(gaps or []),
            "written_on": _today(),
            "recorded_at": _now(),
        }
        held["goals"][ref] = row
        _write(held)

    _log("event.goal_written", actor, {"goal": ref})
    return {"ok": True, "goal": row}


def _decides(actor: Any) -> bool:
    """Whoever decides — the spine calls the capacity `decision_maker`, and
    this codebase carries it on the actor as the council capacity, whichever
    governance shape the organization chose."""
    return bool(getattr(actor, "is_council", False))


PROPOSED_NOT_SETTLED = ("Recorded as proposed. Whoever decides settles this "
                        "one.")


def reword(ref: str, *, actor: Any, goal: str = "", horizon: str = ""
           ) -> dict[str, Any]:
    """Only whoever decides may change what a goal says.

    If anybody could reword a goal, goals would quietly be rewritten to
    match whatever was achieved.
    """
    if not _decides(actor):
        return {"ok": False, "proposed": True,
                "error": "Recorded as proposed. Whoever decides settles the "
                         "wording of a goal."}
    with _LOCK:
        held = _read()
        row = held["goals"].get(ref)
        if not row:
            return {"ok": False, "error": "No such goal."}
        if goal.strip():
            row["goal"] = goal.strip()
        if horizon:
            row["horizon"] = horizon
        held["goals"][ref] = row
        _write(held)
    _log("event.goal_reworded", actor, {"goal": ref})
    return {"ok": True, "goal": row}


def close(ref: str, *, actor: Any, stands: str,
          extended_to: str = "") -> dict[str, Any]:
    """Mark a goal reached, no longer wanted, or overtaken.

    Whoever decides, and nobody else. A goal closed either way stays on the
    list.
    """
    if stands not in STANDINGS:
        return {"ok": False, "error": "That is not one of the four states."}
    if not _decides(actor):
        return {"ok": False, "proposed": True,
                "error": "Recorded as proposed. Whoever decides closes a "
                         "goal."}
    with _LOCK:
        held = _read()
        row = held["goals"].get(ref)
        if not row:
            return {"ok": False, "error": "No such goal."}
        row["stands"] = stands
        if extended_to:
            row["extended_to"] = extended_to
        held["goals"][ref] = row
        _write(held)
    _log("event.goal_closed", actor, {"goal": ref, "stands": stands})
    return {"ok": True, "goal": row}


def update(ref: str, *, actor: Any, would_be_true: str | None = None,
           owner: str | None = None, responsibilities: str | None = None
           ) -> dict[str, Any]:
    """The fields any hat may change. The wording, the horizon and whether
    it is closed stay with whoever decides."""
    with _LOCK:
        held = _read()
        row = held["goals"].get(ref)
        if not row:
            return {"ok": False, "error": "No such goal."}
        for key, value in (("would_be_true", would_be_true), ("owner", owner),
                           ("responsibilities", responsibilities)):
            if value is not None:
                row[key] = str(value).strip()
        _write(held)
    _log("event.goal_updated", actor, {"goal": ref})
    return {"ok": True, "goal": row}


def propose(ref: str, *, actor: Any, goal: str = "", horizon: str = "",
            stands: str = "") -> dict[str, Any]:
    """Anybody may propose rewording, a new horizon, or closing a goal. The
    proposal is recorded, so whoever decides can see it and settle it."""
    if horizon and horizon not in HORIZONS:
        horizon = ""
    if stands and stands not in STANDINGS:
        stands = ""
    if not (str(goal).strip() or horizon or stands):
        return {"ok": False, "error": "Say what you would change."}
    with _LOCK:
        held = _read()
        if ref not in held["goals"]:
            return {"ok": False, "error": "No such goal."}
        held.setdefault("proposals", []).append({
            "goal_ref": ref, "goal": str(goal).strip(), "horizon": horizon,
            "stands": stands, "by": str(getattr(actor, "title", "")
                                        or getattr(actor, "name", "")),
            "at": _now(), "settled": ""})
        _write(held)
    _log("event.goal_proposed", actor, {"goal": ref})
    return {"ok": True, "proposed": True, "says": PROPOSED_NOT_SETTLED}


def settle(index: int, *, actor: Any, accept: bool) -> dict[str, Any]:
    """Whoever decides accepts or declines a proposal. Declining is recorded
    without comment; both stay on the goal's history."""
    if not _decides(actor):
        return {"ok": False, "error": "Whoever decides settles a proposal."}
    with _LOCK:
        held = _read()
        items = held.setdefault("proposals", [])
        if not 0 <= index < len(items) or items[index].get("settled"):
            return {"ok": False, "error": "No such proposal waiting."}
        item = items[index]
        item["settled"] = "accepted" if accept else "declined"
        item["settled_at"] = _now()
        row = held["goals"].get(item["goal_ref"])
        if accept and row:
            if item.get("goal"):
                row["goal"] = item["goal"]
            if item.get("horizon"):
                row["horizon"] = item["horizon"]
            if item.get("stands"):
                row["stands"] = item["stands"]
        _write(held)
    _log("event.goal_proposal_settled", actor,
         {"goal": item["goal_ref"], "accepted": accept})
    return {"ok": True}


def proposals(open_only: bool = True) -> list[dict[str, Any]]:
    items = list(enumerate(_read().get("proposals") or []))
    return [{**p, "index": i} for i, p in items
            if not open_only or not p.get("settled")]


# ---------------------------------------------------------------------------
# Reading an organisation's own planning document, first
# ---------------------------------------------------------------------------

#: Words that mark a sentence as a statement of where the organisation wants
#: to get to. Read from their own document; nothing is saved until a person
#: adds it.
_GOAL_CUES = ("goal", "objective", "we will", "vision", "mission", "priority",
              "aim", "by 20", "within five years", "within a year",
              "commit to", "strive", "ensure that", "outcome")


def candidates(paragraphs: list[str], *, today: str = "") -> list[dict[str, Any]]:
    """Sentences from their own document that read like a goal, each with a
    horizon where the document itself names a year. Offered, never saved:
    the person reads them, keeps the ones that are theirs, and edits the
    rest."""
    import re
    year_now = int((today or _today())[:4])
    found: list[dict[str, Any]] = []
    seen: set[str] = set()
    for para in paragraphs:
        for sentence in re.split(r"(?<=[.!?])\s+", str(para)):
            text = sentence.strip(" •-–\t")
            low = text.lower()
            if not (25 <= len(text) <= 300):
                continue
            if not any(cue in low for cue in _GOAL_CUES):
                continue
            key = low[:80]
            if key in seen:
                continue
            seen.add(key)
            horizon = NO_DATE
            years = [int(y) for y in re.findall(r"\b(20\d\d)\b", text)]
            if "within a year" in low or (years and max(years) <= year_now + 1):
                horizon = WITHIN_A_YEAR
            elif "five years" in low or (years and max(years) <= year_now + 5):
                horizon = WITHIN_FIVE
            elif years:
                horizon = LONGER
            found.append({"goal": text, "horizon": horizon})
            if len(found) >= 12:
                return found
    return found


def from_framework(within_a_year: str, within_five: str,
                   recorded: list[dict[str, Any]] | None = None
                   ) -> list[dict[str, Any]]:
    """The goals the framework already holds, offered on this page.

    Brett, BUG-BE30FBD3: "Vision should be a module inside the Framework …
    the vision section can be pre-filled from the framework." Framework
    11.1a and 11.1b ask what AI should help the organization achieve within a
    year and within five years, one goal per line. Each line is offered here
    with its horizon already set. Offered, not saved — the same as goals read
    from a document — and a line already written down as a goal is not
    offered again."""
    have = {str(g.get("goal", "")).strip().lower().rstrip(".")
            for g in (recorded if recorded is not None else all_goals())}
    out: list[dict[str, Any]] = []
    for text, horizon, number in ((within_a_year, WITHIN_A_YEAR, "11.1a"),
                                  (within_five, WITHIN_FIVE, "11.1b")):
        for line in str(text or "").splitlines():
            goal_text = line.strip(" •-–\t").strip()
            if len(goal_text) < 3 or goal_text.lower().rstrip(".") in have:
                continue
            if goal_text.lower().rstrip(".") in ("no", "none", "nothing", "n/a", "na"):
                continue
            have.add(goal_text.lower().rstrip("."))
            out.append({"goal": goal_text[:300], "horizon": horizon,
                        "from": f"Framework {number}"})
    return out


FROM_YOUR_FRAMEWORK = (
    "From your framework, 11.1a and 11.1b — what you said AI should help you "
    "achieve. Nothing is saved until you add it. To change them for good, "
    "change the answer in the framework.")


READ_FROM_YOUR_DOCUMENT = (
    "These were read from your document. Nothing is saved until you add it — "
    "keep the ones that are yours, change the wording, and leave the rest.")


def all_goals() -> list[dict[str, Any]]:
    return list(_read()["goals"].values())


def goal(ref: str) -> dict[str, Any] | None:
    return _read()["goals"].get(ref)


def goal_of(project: dict[str, Any]) -> list[str]:
    """The goal or goals a project names, read from the project.

    Nothing here writes the tie. A goal never claims a project, because then
    two surfaces could disagree about what a project is for.
    """
    named = project.get("goal") or project.get("goals") or []
    if isinstance(named, str):
        return [named] if named.strip() else []
    return [str(g) for g in named if str(g).strip()]


LIVE_STATES = (spine.PROPOSED, spine.BEING_WORKED, spine.WAITING_DECISION,
               spine.WAITING_PERSON, spine.CLEARED)


def _is_live(project: dict[str, Any]) -> bool:
    state = project.get("state") or ""
    if state in (spine.TURNED_DOWN, spine.RETIRED):
        return False
    return project.get("gate") != spine.SUNSET


def serving(ref: str, projects: list[dict[str, Any]] | None = None
            ) -> list[dict[str, Any]]:
    return [p for p in (projects or []) if ref in goal_of(p)]


# ===========================================================================
# 2 · The stat row
# ===========================================================================

COUNTER_NAMES = ("Goals recorded", "Being worked on", "Nothing against them",
                 "Projects serving no goal", "Reached, or no longer wanted")

#: The copy under the row. The two absence counters are the two halves of
#: the same question, and neither is a fault.
TWO_HALVES = (
    "One counts what you said you wanted and are not doing. The other "
    "counts what you are doing and did not say you wanted. Both are worth "
    "knowing and neither is a fault.")


def counters(rows: list[dict[str, Any]] | None = None, *,
             projects: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Five counters, each a count with a plain-English label."""
    rows = all_goals() if rows is None else rows
    projects = list(projects or [])
    live = [p for p in projects if _is_live(p)]

    worked_on = 0
    nothing_against = 0
    for row in rows:
        against = serving(row["ref"], projects)
        if any(_is_live(p) for p in against):
            worked_on += 1
        if not against:
            nothing_against += 1

    return {
        "recorded": len(rows),
        "being_worked_on": worked_on,
        "nothing_against_them": nothing_against,
        "serving_no_goal": sum(1 for p in live if not goal_of(p)),
        "closed": sum(1 for r in rows if r.get("stands") in CLOSED),
        "two_halves": TWO_HALVES,
    }


# ===========================================================================
# 3 · The findings panel
# ===========================================================================

CLEAN_STATE = spine.NOTHING_TO_FLAG

#: Defined in the spine and not redefined here.
RAISED_HERE_FROM_THE_SPINE = ("finding.gap_no_owner",)

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.vs.no_goal_named", "Vision",
        "The organization said every tool must serve a stated goal, and a "
        "live project names none",
        "You said every tool has to serve one of your goals. [Project] does "
        "not name one."),
    spine.Finding(
        "finding.vs.goal_horizon_passed", "Vision",
        "A goal's horizon has passed and it is neither closed nor extended",
        "This was for [date]. Nothing here says whether you got there."),
    spine.Finding(
        "finding.vs.retired_against_goal", "Vision",
        "A tool sunset closed with a final measurement that did not reach "
        "what the goal asked for",
        "[Project] was retired. Against [goal], it ended at [figure] where "
        "you were looking for [figure]."),
    spine.Finding(
        "finding.vs.goal_orphaned", "Vision",
        "Every project serving a goal has retired or been turned down",
        "Nothing is working on [goal] any more."),
    spine.Finding(
        "finding.vs.value_unmeasured", "Vision",
        "The organization said a tool must show measurable value or be "
        "retired; a project serving this goal is at Measure, its expected "
        "date has passed, and no outcome measurement is recorded",
        "You said a tool must show measurable value or be retired. This has "
        "been running since [date] and nothing has been written down about "
        "whether it worked."),
    spine.Finding(
        "finding.vs.outcome_missed_no_decision", "Vision",
        "An outcome measurement was recorded, it did not reach what the goal "
        "asked for, and nothing records what is being done about it",
        "This did not do what you said it would, and nothing has been "
        "decided about it. You said [their answer] when a tool is not "
        "delivering."),
    spine.Finding(
        "finding.vs.goal_gone_tool_running", "Vision",
        "A goal is marked no longer what we want and a project serving it "
        "is in use",
        "You recorded that this is no longer what you want. The tool bought "
        "for it is still running."),
    spine.Finding(
        "finding.vs.publish_overdue", "Vision",
        "The organization said it publishes a yearly report and nothing is "
        "recorded within the last twelve months",
        "You said you would publish a yearly report on what you use and how "
        "it is working. Nothing is recorded since [date]."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}

#: Stated without judgement and **never suppressed**. A tool that did not
#: get there is the single most useful thing this application can tell an
#: organisation.
NEVER_SUPPRESSED = "finding.vs.retired_against_goal"


def findings(rows: list[dict[str, Any]] | None = None, *,
             projects: list[dict[str, Any]] | None = None,
             mission_tie: bool = False, value_or_retire: str = "",
             not_delivering: str = "", publishes_yearly: bool = False,
             last_published: str = "", today: str = "") -> list[dict[str, Any]]:
    """Every finding this surface can compute from what is recorded.

    `mission_tie` and `value_or_retire` are optional additions the
    organization may or may not have adopted. Where one was not adopted the
    finding behind it never renders, and the absence is never shown as
    missing.
    """
    rows = all_goals() if rows is None else rows
    projects = list(projects or [])
    today = today or _today()
    raised: list[dict[str, Any]] = []

    def add(finding_id: str, entry: str, says: str) -> None:
        raised.append({"id": finding_id, "entry": entry, "says": says})

    # 3.1 — renders only where the organisation adopted the mission tie.
    # Where they did not, projects naming no goal are ordinary, and the
    # counter is shown without a finding behind it.
    if mission_tie:
        for project in projects:
            if _is_live(project) and not goal_of(project):
                add("finding.vs.no_goal_named", project.get("ref", ""),
                    f"You said every tool has to serve one of your goals. "
                    f"{project.get('name') or project.get('ref', '')} does "
                    f"not name one.")

    for row in rows:
        ref = row["ref"]
        against = serving(ref, projects)

        # 3.2 — a horizon that has passed with nothing said about it.
        if row.get("stands") == OPEN and not row.get("extended_to"):
            due = _horizon_date(row, today)
            if due and due < today:
                add("finding.vs.goal_horizon_passed", ref,
                    f"This was for {due}. Nothing here says whether you got "
                    f"there.")

        # 3.4 — every project serving it has gone.
        if against and not any(_is_live(p) for p in against):
            add("finding.vs.goal_orphaned", ref,
                f"Nothing is working on {row['goal']} any more.")

        # 3.7 — the goal is gone and the tool is not.
        if row.get("stands") == NO_LONGER_WANTED:
            for project in against:
                if project.get("in_use") == spine.IN_USE_YES:
                    add("finding.vs.goal_gone_tool_running", ref,
                        "You recorded that this is no longer what you want. "
                        "The tool bought for it is still running.")

        for project in against:
            # 3.3 — never suppressed, and stated without judgement.
            if project.get("state") == spine.RETIRED and \
                    project.get("final_measurement") and \
                    project.get("reached") is False:
                add("finding.vs.retired_against_goal", ref,
                    f"{project.get('name') or project.get('ref', '')} was "
                    f"retired. Against {row['goal']}, it ended at "
                    f"{project['final_measurement']} where you were looking "
                    f"for {project.get('was_looking_for', 'what you wrote')}.")

            # 3.5 — only where they said value or retire.
            if value_or_retire and project.get("gate") == spine.MEASURE \
                    and not project.get("outcome_recorded"):
                since = project.get("expected_by") or ""
                if since and since < today:
                    add("finding.vs.value_unmeasured", project.get("ref", ""),
                        f"You said a tool must show measurable value or be "
                        f"retired. This has been running since {since} and "
                        f"nothing has been written down about whether it "
                        f"worked.")

            # 3.6 — a miss with nothing decided about it.
            if project.get("outcome_recorded") and \
                    project.get("reached") is False and \
                    not project.get("what_now"):
                answer = not_delivering or "what happens next"
                add("finding.vs.outcome_missed_no_decision",
                    project.get("ref", ""),
                    f"This did not do what you said it would, and nothing "
                    f"has been decided about it. You said {answer} when a "
                    f"tool is not delivering.")

    # 3.8 — their own publishing answer, and nothing else.
    if publishes_yearly:
        if not last_published or _months(last_published, today) > 12:
            when = last_published or "you started"
            add("finding.vs.publish_overdue", "",
                f"You said you would publish a yearly report on what you "
                f"use and how it is working. Nothing is recorded since "
                f"{when}.")

    return raised


def _horizon_date(row: dict[str, Any], today: str) -> str:
    """The date a horizon fell due, computed from the day it was written.

    Returns empty for *longer than that* and *no date set*: neither is a
    date, and this application does not invent one.
    """
    written = str(row.get("written_on") or "")[:10]
    if not written or row.get("horizon") not in (WITHIN_A_YEAR, WITHIN_FIVE):
        return ""
    years = 1 if row["horizon"] == WITHIN_A_YEAR else 5
    try:
        then = datetime.fromisoformat(written).replace(tzinfo=timezone.utc)
    except ValueError:
        return ""
    try:
        return then.replace(year=then.year + years).date().isoformat()
    except ValueError:                                  # 29 February
        return then.replace(year=then.year + years, day=28).date().isoformat()


def _months(earlier: str, later: str) -> int:
    try:
        one = datetime.fromisoformat(str(earlier)[:10])
        two = datetime.fromisoformat(str(later)[:10])
    except ValueError:
        return 0
    return (two.year - one.year) * 12 + (two.month - one.month)


# ===========================================================================
# 4 · The list view
# ===========================================================================

COLUMNS = ("The goal", "Horizon", "What would have to be true", "Projects",
           "Where it stands")

FILTERS = ("By horizon", "By whether anything is being done",
           "By which unit owns it", "By where it stands")

#: Nearest horizon first, and within each group the goals with nothing
#: against them sort to the top — because they are the ones somebody needs
#: to look at.
GROUPED_BY_HORIZON = True


def grouped(rows: list[dict[str, Any]] | None = None, *,
            projects: list[dict[str, Any]] | None = None
            ) -> list[dict[str, Any]]:
    rows = all_goals() if rows is None else rows
    projects = list(projects or [])
    out: list[dict[str, Any]] = []
    for horizon in HORIZONS:
        here = [r for r in rows if r.get("horizon") == horizon]
        if not here:
            continue
        here.sort(key=lambda r: (bool(serving(r["ref"], projects)),
                                 r.get("goal", "")))
        out.append({
            "horizon": horizon,
            # Announced before the goals, so a screen reader user hears
            # "Within a year, four goals" first.
            "heading": f"{horizon}, {len(here)} "
                       f"{'goal' if len(here) == 1 else 'goals'}",
            "goals": here,
        })
    return out


EMPTY_STATE = (
    "Nothing here yet.\n\nWrite down one thing you want to be true a year "
    "from now. Write the outcome you would tell somebody about if it "
    "happened, not the project or the tool that gets you there.")

#: A goal with nothing against it says so in words, in its own region,
#: rather than being conveyed by an empty space where other goals have
#: content.
NOTHING_AGAINST_IT = "Nothing is being done about this one yet."


# ===========================================================================
# 6 · The portfolio read-back
# ===========================================================================

#: The section that makes this surface worth opening. Prose and a list,
#: never a chart or a matrix.
#:
#: **No score, no progress bar, no percentage toward a goal.** It shows
#: counts, states, and what each project is waiting on. This application
#: does not know how far along a goal is, and it does not aggregate, average
#: or roll up.
NO_PROGRESS_FIGURE = (
    "There is no progress figure here. This application does not know how "
    "far along a goal is.")

#: It shows retired and turned-down projects alongside live ones. Take a
#: goal served by four projects where three were turned down at Identify
#: because the answer was a process change: that history tells a truer story
#: than a read-back showing only what survived.
HISTORY_STAYS = (
    "Retired and turned-down projects stay here. A goal's history is more "
    "useful than its current state.")


def portfolio(ref: str, *, projects: list[dict[str, Any]] | None = None,
              rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Under one goal, every project that names it — live, retired and
    turned down — as prose and a list."""
    rows = all_goals() if rows is None else rows
    found = next((r for r in rows if r["ref"] == ref), None)
    if not found:
        return {}
    against = serving(ref, projects or [])

    head = f"{found['goal']}. By {found.get('horizon') or NO_DATE}."
    if found.get("owner"):
        head += f" Owned by {found['owner']}."

    live = [p for p in against if _is_live(p)]
    waiting = [p for p in live if p.get("state") == spine.WAITING_DECISION]
    retired = [p for p in against if p.get("state") == spine.RETIRED]
    turned_down = [p for p in against
                   if p.get("state") == spine.TURNED_DOWN]

    if not against:
        summary = NOTHING_AGAINST_IT
    else:
        bits = [f"{_count(len(against))} "
                f"{'project names' if len(against) == 1 else 'projects name'}"
                f" this goal."]
        running = len(live) - len(waiting)
        if running:
            bits.append(f"{_count(running).capitalize()} "
                        f"{'is' if running == 1 else 'are'} running.")
        if waiting:
            bits.append(f"{_count(len(waiting)).capitalize()} "
                        f"{'is' if len(waiting) == 1 else 'are'} waiting on "
                        f"a decision.")
        for project in retired:
            said = (f"{_name(project)} was retired")
            if project.get("retired_on"):
                said += f" in {project['retired_on'][:7]}"
            if project.get("reached") is False:
                said += " and did not reach what you were looking for"
            bits.append(said + ".")
        if turned_down:
            bits.append(f"{_count(len(turned_down)).capitalize()} "
                        f"{'was' if len(turned_down) == 1 else 'were'} "
                        f"turned down.")
        summary = " ".join(bits)

    # Each project under a goal is a sentence naming the project, its gate
    # and what it is waiting on. Never a chart, never a matrix.
    lines = []
    for project in against:
        gate = spine.BY_GATE.get(project.get("gate") or "")
        state = spine.BY_STATE.get(project.get("state") or "")
        said = _name(project)
        if gate:
            said += f", at {gate.name}"
        if state:
            said += f", {state.shown_as.lower()}"
        lines.append(said + ".")

    return {"heading": head, "summary": summary, "lines": lines,
            "counts": {"all": len(against), "live": len(live),
                       "waiting": len(waiting), "retired": len(retired),
                       "turned_down": len(turned_down)},
            "no_progress_figure": NO_PROGRESS_FIGURE}


_WORDS = ("no", "one", "two", "three", "four", "five", "six", "seven",
          "eight", "nine", "ten")


def _count(many: int) -> str:
    return _WORDS[many] if many < len(_WORDS) else str(many)


def _name(project: dict[str, Any]) -> str:
    return str(project.get("name") or project.get("ref") or "A project")


# ===========================================================================
# 7 · The public view
# ===========================================================================

#: **Nothing is published from this application.** This surface records what
#: the organisation says it publishes and where. It composes nothing, sends
#: nothing and hosts nothing — said plainly, because a surface named the
#: public view will otherwise be taken for a publishing tool.
PUBLISHES_NOTHING = (
    "Nothing is published from here. This records what you say you publish "
    "and where. It composes nothing, sends nothing and hosts nothing.")

PUBLISH_YES = "Yes"
PUBLISH_NO = "No"
PUBLISH_UNDECIDED = "Not decided"
PUBLISH_ANSWERS = (PUBLISH_YES, PUBLISH_NO, PUBLISH_UNDECIDED)

APPEARS_PUBLICLY = ("The goal", "What would have to be true",
                    "What you are running against it", "How to reach a "
                    "person", "Nothing")


def set_public_view(*, actor: Any, publishes: str = PUBLISH_UNDECIDED,
                    appears: list[str] | None = None, where: str = "",
                    approver: str = "", last_published: str = ""
                    ) -> dict[str, Any]:
    """Where the organization said it publishes something about the AI it
    uses, this surface holds it — a goal being the only thing on the list a
    member of the public would recognize. What appears publicly is set by
    whoever decides; anybody else proposes it."""
    if not _decides(actor):
        return {"ok": False, "proposed": True,
                "error": "Recorded as proposed. Whoever decides sets what "
                         "appears publicly."}
    if publishes not in PUBLISH_ANSWERS:
        publishes = PUBLISH_UNDECIDED
    appears = [a for a in (appears or []) if a in APPEARS_PUBLICLY]
    with _LOCK:
        held = _read()
        held["published"] = {
            "publishes": publishes,
            "appears": list(appears or []),
            "where": str(where or "").strip(),
            # Where no public information function exists, this folds to
            # whoever holds that hat. The absence is never shown as a defect.
            "approver": approver,
            "last_published": last_published,
            "recorded_at": _now(),
        }
        _write(held)
    _log("event.public_view_recorded", actor, {"publishes": publishes})
    return {"ok": True, "published": held["published"],
            "says": PUBLISHES_NOTHING}


def public_view() -> dict[str, Any]:
    return dict(_read().get("published") or {})


#: Where they said they publish nothing, the section states that and offers
#: to change it, rather than disappearing.
PUBLISHES_NOTHING_TODAY = (
    "You said you publish nothing about this. That is recorded. You can "
    "change it here.")


# ===========================================================================
# 10 · Who may do what
# ===========================================================================

#: Anybody may propose a goal and anybody may tie a project to one. Only
#: whoever decides may change what a goal says or close it — because if
#: anybody could reword a goal, goals would quietly be rewritten to match
#: whatever was achieved.
ANYONE_MAY: tuple[str, ...] = (
    "see every goal and every field",
    "propose a goal",
    "say what would have to be true",
    "name a goal on a project",
    "read the final measurement at a tool sunset",
)

DECIDER_ONLY: tuple[str, ...] = (
    "edit the wording of a goal",
    "set the horizon",
    "mark a goal reached, or no longer wanted",
    "set what appears publicly",
)

WHY_THE_WORDING_IS_HELD = (
    "If anybody could reword a goal, goals would quietly be rewritten to "
    "match whatever was achieved.")


# ===========================================================================
# 9 · What this surface is not
# ===========================================================================

WHAT_IT_IS_NOT = (
    "A statement of where you are going, not a plan for getting there. No "
    "tasks, no milestones, no owners of steps, no dates other than the "
    "horizon. Scheduling the work is left to the organization.",
    "It holds no measurement of any tool. The baseline, what would count as "
    "success, and the measurement afterward live on the project, written "
    "at Procure and read at Measure. This surface reads the final result "
    "and none of the numbers behind it.",
    "Not a strategic plan and not a substitute for one. Most organizations "
    "using this already have one. This holds the handful of outcomes the AI "
    "work is meant to serve, and links to that plan.",
    "It publishes nothing. It records what you say you publish and where.",
    "It gates nothing. No project is refused for naming no goal.",
)

#: Answers this surface deliberately does not render. Scrutiny levels,
#: agreement terms, cost and review cadence are read elsewhere. A goal is
#: what the organisation wants, and loading this surface with governance
#: settings would make it the second place every answer lives.
NOT_RENDERED_HERE = ("scrutiny levels", "agreement terms", "cost",
                     "review cadence")

#: Owns no gate. Serves Identify, Procure and Sunset, and is the required
#: reader at Sunset.
OWNS_NO_GATE = True
SERVES = (spine.IDENTIFY, spine.PROCURE, spine.SUNSET)
REQUIRED_READER_AT = spine.SUNSET

#: Where a governmental unit already has a vision statement, a mission
#: statement or other planning documents, those are uploaded first and the
#: fields here are pre-written from them where possible.
UPLOAD_FIRST = (
    "If you already have a vision or mission statement, or any planning "
    "document, upload it first and we will fill in what we can from it.")


def report(*, projects: list[dict[str, Any]] | None = None,
           organisation_type: str = "", mission_tie: bool = False,
           value_or_retire: str = "", publishes_yearly: bool = False
           ) -> dict[str, Any]:
    rows = all_goals()
    published = public_view()
    raised = findings(rows, projects=projects, mission_tie=mission_tie,
                      value_or_retire=value_or_retire,
                      publishes_yearly=publishes_yearly,
                      last_published=published.get("last_published", ""))
    return {
        "goals": rows,
        "counters": counters(rows, projects=projects),
        "counter_names": list(COUNTER_NAMES),
        "two_halves": TWO_HALVES,
        "grouped": grouped(rows, projects=projects),
        "raised": raised,
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "raised_here_from_the_spine": list(RAISED_HERE_FROM_THE_SPINE),
        "clean_state": CLEAN_STATE,
        "columns": list(COLUMNS),
        "filters": list(FILTERS),
        "horizons": list(HORIZONS),
        "standings": list(STANDINGS),
        "empty_state": EMPTY_STATE,
        "placeholder": placeholder(organisation_type),
        "portfolio": [portfolio(r["ref"], projects=projects, rows=rows)
                      for r in rows],
        "public_view": published,
        "publishes_nothing": PUBLISHES_NOTHING,
        "anyone_may": list(ANYONE_MAY),
        "decider_only": list(DECIDER_ONLY),
        "what_it_is_not": list(WHAT_IT_IS_NOT),
        "no_progress_figure": NO_PROGRESS_FIGURE,
        "history_stays": HISTORY_STAYS,
        "never_computed": NEVER_COMPUTED,
        "only_the_goal": ONLY_THE_GOAL,
        "upload_first": UPLOAD_FIRST,
    }
