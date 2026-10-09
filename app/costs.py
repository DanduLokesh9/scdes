"""Budget — what it costs you, all in.

What a tool costs over its whole life, including what it would cost to leave
it. **The unit is one cost line, committed or not** — one kind of cost, on
one basis, with one owner, carrying what you expected it to cost and what it
came to.

The license renewing every year is a line. The consultant who set it up is a
second. The two weeks of staff time it takes to clean the file before the
tool can read it is a third, and it is a line whether or not anybody has put
a number on it. What it would cost to walk away is a fourth, and it is
usually not written down anywhere.

**The line is the unit because the total is never the thing that moves.**
Roll a tool's costs into one figure and the moment the figure changes you
cannot say which part changed or who owns the part that changed. A license
has a renewal date and an invoice behind it; staff time has a person and an
hour count; an exit cost has a contract clause and no invoice at all. A
register that flattens those into one number has thrown away everything
somebody would need to explain the number later.

**The full cost is computed here and never typed in.** The figure the
business case argues from at Procure is this computation read across, not a
second number keyed in somewhere else. A business case with its own editable
cost box disagrees with the register by the second week, and when the two
disagree nobody can say which of them the decision was made on.

What this surface will not do, and why each refusal matters
-----------------------------------------------------------

**No lifetime total.** A lifetime total needs a number of years and nobody
has told the application how long any of this will run. A total built on a
guessed life span would be wrong, and it would be the number quoted back in
a meeting.

**No return, no payback period, no ratio.** What comes back is recorded on
the project as a claim in the organization's own words, to be checked later.
This surface contributes one half of that question, which is what the thing
cost.

**No hours converted to money.** Annual hours and one-off hours are totaled
separately. An hour needs a rate, the application does not have one, and an
hour that was captured and then reported nowhere is an hour the register
lost.

**Nothing is annualized that cannot be.** Charged by use, priced per person
with no headcount, or no basis recorded — each is excluded from every figure
*and counted in a line that says so*, rather than quietly dropped.

Named `costs` rather than `budget` because `app/budget.py` already holds a
different concept: SCDES's recurring and one-off pools, and a weighted
purchase recommendation. Ranking candidates on weights now belongs to
Oversight, which records the weights as a governance decision with an owner
and a date.
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

FILENAME = "cost_lines.json"
_LOCK = threading.Lock()

# ===========================================================================
# The vocabulary
# ===========================================================================

#: How a cost is charged. Each basis decides whether a yearly figure can be
#: worked out at all, and three of them mean it cannot.
A_YEAR = "year"
A_MONTH = "month"
PER_PERSON_MONTH = "per_person_month"
ONE_OFF = "one_off"
BY_USE = "by_use"
NO_CHARGE = "no_charge"
UNSURE = "unsure"

BASIS = {
    A_YEAR: "A year",
    A_MONTH: "A month",
    PER_PERSON_MONTH: "Each person, each month",
    ONE_OFF: "One-off",
    BY_USE: "How much we use it",
    NO_CHARGE: "No charge",
    UNSURE: "We are not sure",
}

#: The kinds of cost, as Module One 8.7 writes them. An organisation ticks
#: which of these count as cost for them; this surface measures against
#: their list and never against one of its own.
#:
#: The keys are Module One 8.7b's own, in its order. They had drifted — this
#: surface said "leaving" where the framework says "exit" and "watching"
#: where it says "monitoring" — so a kind ticked in the framework was
#: invisible to anything reading this list, and every project read as
#: missing its cost of leaving. Stored rows are read through `_RENAMED`.
KINDS = {
    "licence": "The license or subscription",
    "setup": "Setting it up",
    "training": "Training staff",
    "staff_time": "Staff time to run it",
    "data_prep": "Getting your information ready",
    "integration": "Connecting it to other systems",
    "monitoring": "Ongoing monitoring and review",
    "exit": "What it costs to leave",
    # Only where 6.9 ticked energy and environmental cost.
    "energy": "Energy and environmental cost",
    "other": "Something else — say what",
}
LEAVING = "exit"
ENERGY = "energy"
OTHER = "other"
#: The eight kinds Module One 8.7b lists, in its order.
FRAMEWORK_KINDS = ("licence", "setup", "training", "staff_time", "data_prep",
                   "integration", "monitoring", "exit")

#: Keys this surface used before it read Module One's. "Storage" and
#: "support" have no framework equivalent, so they are kept as something
#: else with their old name in the note rather than silently re-filed.
_RENAMED = {"leaving": "exit", "watching": "monitoring",
            "storage": "other", "support": "other"}
_OLD_NAMES = {"storage": "Storage and infrastructure",
              "support": "Support and maintenance"}

#: 6.12 · whose money it is.
WHOSE_MONEY = ("Money already in our budget",
               "A new appropriation or budget request", "A grant",
               "Another government pays for it",
               "Nobody has identified where this comes from",
               "We are not sure")
#: 6.9 · when the estimate was made.
ESTIMATE_WHEN = ("Before we committed", "Afterward", "We are not sure")
#: 6.11 · is the AI part included in what you already pay?
INCLUDED = ("It is included in what we already pay", "It costs extra",
            "It is free for now", "We are not sure")
COSTS_EXTRA = "It costs extra"
#: 6.14 · when does it run out?
ENDS_HOW = ("On this date", "It does not — it renews until we stop it",
            "It was a one-off", "We are not sure")
#: The hours bases, offered only for the kinds that are mostly hours.
HOURS_KINDS = ("staff_time", "setup", "training", "data_prep")

#: Where a line stands. Only Open lines reach any figure — money that has
#: stopped is history rather than a commitment — but every line, whatever
#: its status, is counted in "Cost lines recorded". The register never
#: shrinks.
OPEN = "open"
ENDED = "ended"
SUPERSEDED = "superseded"
WITHDRAWN = "withdrawn"
LINE_STATUS = {
    OPEN: "Open",
    ENDED: "Ended",
    SUPERSEDED: "Superseded by a later line",
    WITHDRAWN: "Withdrawn",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file():
    from app import tenant
    from app.audit import CORPUS
    return tenant.scoped(CORPUS / "config" / FILENAME)


def _read() -> dict[str, Any]:
    blank: dict[str, Any] = {"lines": {}, "kind_gaps": [], "settings": {}}
    path = _file()
    if not path.is_file():
        return blank
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return blank
    if not isinstance(held, dict):
        return blank
    held.setdefault("lines", {})
    for row in held["lines"].values():
        old = row.get("kind")
        if old in _RENAMED:
            row["kind"] = _RENAMED[old]
            if old in _OLD_NAMES and not row.get("other_kind"):
                row["other_kind"] = _OLD_NAMES[old]
        # Lines written before a line could be shared carry one project.
        if "projects" not in row:
            row["projects"] = [row["project"]] if row.get("project") else []
    held.setdefault("kind_gaps", [])
    held.setdefault("settings", {})
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _record(action: str, actor: Any, detail: dict[str, Any]) -> None:
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "unknown",
            role=getattr(getattr(actor, "role", None), "value", "")
            or "system",
            action=action, target="Budget", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]})
    except Exception:                                         # noqa: BLE001
        pass


# ===========================================================================
# The line
# ===========================================================================

#: The fields a line carries beyond the arithmetic. Anything else sent is
#: dropped rather than stored.
LINE_FIELDS = ("what_for", "other_kind", "estimate_unsure", "actual_unsure",
               "estimate_when", "based_on", "included_or_extra",
               "whose_money", "starts", "ends", "ends_how", "owner_outside",
               "supersedes", "leaving_involves", "field_gaps")


def add(*, kind: str = "", actor: Any, project: str = "", basis: str = "",
        estimate: float | None = None, actual: float | None = None,
        hours_a_year: float = 0.0, hours_one_off: float = 0.0,
        headcount: int = 0, owner: str = "", committed: bool = False,
        version: str = "", note: str = "",
        not_one_project: bool = False,
        projects: list[str] | None = None,
        extra: dict[str, Any] | None = None) -> dict[str, Any]:
    """One kind of cost, on one basis, with one owner.

    A line that was proposed and never committed is still a line. A line
    entered in error and withdrawn stays on the register: it holds what was
    written down, whether or not anybody agreed to it.

    Only the first line — what the cost is for — is required on the form.
    The kind may be left for later, but an unknown one is refused.
    """
    extra = {k: v for k, v in (extra or {}).items() if k in LINE_FIELDS}
    if kind and kind not in KINDS:
        return {"ok": False, "error": f"{kind!r} is not a kind of cost."}
    if not kind and not str(extra.get("what_for") or "").strip():
        return {"ok": False, "error": "Say what this cost is for, in one "
                                      "line."}
    tied = [p for p in (projects or ([project] if project else [])) if p]
    with _LOCK:
        held = _read()
        ref = "C-" + "".join(
            secrets.choice("23456789BCDFGHJKMNPQRSTVWXYZ") for _ in range(6))
        # 6.16 · a line that replaces one already recorded. The app sets the
        # earlier line's status; no control sets it by hand.
        replaced = held["lines"].get(str(extra.get("supersedes") or ""))
        if replaced and replaced.get("status") == OPEN:
            replaced["status"] = SUPERSEDED
            replaced["superseded_by"] = ref
        row = {
            "ref": ref,
            "kind": kind,
            # Costs belonging to no single project — the money it takes to
            # run the governance work itself — say so on the line rather
            # than being attached to a project they do not belong to.
            "project": "" if not_one_project else (tied[0] if tied else ""),
            # A shared licence covering four jobs is four projects and one
            # line, listed under all four and counted once.
            "projects": [] if not_one_project else tied,
            "not_one_project": bool(not_one_project),
            "basis": basis if basis in BASIS else "",
            "estimate": estimate,
            "actual": actual,
            # Never converted to money. An hour needs a rate and this
            # application does not have one.
            "hours_a_year": float(hours_a_year or 0),
            "hours_one_off": float(hours_one_off or 0),
            "headcount": int(headcount or 0),
            "owner": owner.strip(),
            "committed": bool(committed),
            # Set where the line arrived with a change a vendor made after
            # the tool was bought, so what it cost to buy can be told apart
            # from what it has cost since.
            "version": version,
            "status": OPEN,
            "note": note.strip(),
            "added": _now(),
            "recorded_by": str(getattr(actor, "name", "") or ""),
            "recorded_hat": getattr(getattr(actor, "role", None), "value", ""),
            **extra,
        }
        if committed:
            row.update(_commit_stamp(actor))
        held["lines"][ref] = row
        _write(held)
    _record("event.record_created", actor, {"line": ref, "kind": kind})
    return {"ok": True, "line": row}


def _commit_stamp(actor: Any) -> dict[str, Any]:
    return {"committed": True, "committed_on": clock.today_str(),
            "committed_by_hat": getattr(getattr(actor, "role", None),
                                        "value", ""),
            "committed_by_person": str(getattr(actor, "name", "") or "")}


def commit(ref: str, actor: Any) -> dict[str, Any]:
    """6.22 · Commit this line. Three things are written and never edited
    afterward: the date, the hat worn, and the person behind it.
    Uncommitting is not offered — a wrong commitment is withdrawn or
    superseded, and both leave the original visible."""
    with _LOCK:
        held = _read()
        row = held["lines"].get(ref)
        if not row:
            return {"ok": False, "error": "No such line."}
        if row.get("committed"):
            return {"ok": False, "error": "This line is already committed."}
        if row.get("status") != OPEN:
            return {"ok": False, "error": "Only an open line can be "
                                          "committed."}
        row.update(_commit_stamp(actor))
        _write(held)
    _record("event.cost_committed", actor, {"line": ref})
    return {"ok": True, "line": row}


def set_line_status(ref: str, status: str, actor: Any) -> dict[str, Any]:
    """Ended or Withdrawn. Superseded is set by the app when a later line is
    recorded, never by hand. Nothing is deleted."""
    if status not in (ENDED, WITHDRAWN):
        return {"ok": False, "error": "A line is ended or withdrawn from "
                                      "here."}
    with _LOCK:
        held = _read()
        row = held["lines"].get(ref)
        if not row:
            return {"ok": False, "error": "No such line."}
        if row.get("status") != OPEN:
            return {"ok": False, "error": "Only an open line can change."}
        row["status"] = status
        row[f"{status}_on"] = clock.today_str()
        _write(held)
    _record("event.cost_line_status", actor, {"line": ref, "status": status})
    return {"ok": True, "line": row}


#: The fields a line's amounts can be changed through before it is
#: committed. After a commitment the later number arrives as a superseding
#: line, and both remain visible.
AMOUNT_FIELDS = ("estimate", "actual", "basis", "headcount", "hours_a_year",
                 "hours_one_off", "estimate_unsure", "actual_unsure")


def edit(ref: str, actor: Any, **fields: Any) -> dict[str, Any]:
    with _LOCK:
        held = _read()
        row = held["lines"].get(ref)
        if not row:
            return {"ok": False, "error": "No such line."}
        if row.get("committed") and any(k in fields for k in AMOUNT_FIELDS):
            return {"ok": False, "error": "An amount somebody committed to is "
                                          "not changed in place. Record a new "
                                          "line that supersedes it."}
        for key, value in fields.items():
            if key in AMOUNT_FIELDS or key in LINE_FIELDS or key in (
                    "owner", "note", "kind", "version"):
                row[key] = value
        _write(held)
    _record("event.field_changed", actor, {"line": ref,
                                          "fields": sorted(fields)})
    return {"ok": True, "line": row}


def record_kind_gap(project: str, kind: str, actor: Any, *, owner: str = "",
                    by: str = "", outside: str = "") -> dict[str, Any]:
    """5.7 · Nobody knows this one. The only way to say a whole kind of cost
    is unknown rather than merely unwritten."""
    if kind not in KINDS:
        return {"ok": False, "error": "That is not a kind of cost."}
    with _LOCK:
        held = _read()
        held["kind_gaps"].append({"project": project, "kind": kind,
                                  "owner": str(owner or "").strip(),
                                  "by": str(by or "")[:10],
                                  "outside": str(outside or "").strip(),
                                  "at": _now()})
        _write(held)
    _record("event.gap_recorded", actor, {"project": project, "kind": kind})
    return {"ok": True}


def kind_gaps() -> list[dict[str, Any]]:
    return list(_read().get("kind_gaps") or [])


#: 6.20 · the one setting this surface asks for. The app supplies no
#: amount and no percentage.
DIFFERENCE_MODES = ("Any difference at all", "More than an amount",
                    "More than a percentage", "We have not decided")


def set_difference(mode: str, value: float | None, actor: Any
                   ) -> dict[str, Any]:
    if mode not in DIFFERENCE_MODES:
        return {"ok": False, "error": "Choose one of the answers."}
    with _LOCK:
        held = _read()
        held["settings"]["difference"] = {"mode": mode,
                                          "value": value if mode in (
                                              DIFFERENCE_MODES[1],
                                              DIFFERENCE_MODES[2]) else None}
        _write(held)
    _record("event.setting_changed", actor, {"difference": mode})
    return {"ok": True}


def difference_setting() -> dict[str, Any]:
    return dict((_read().get("settings") or {}).get("difference") or
                {"mode": DIFFERENCE_MODES[3], "value": None})


def worth_a_conversation(estimate: float, actual: float,
                         setting: dict[str, Any]) -> bool:
    """Whether an actual above its estimate crosses the organization's own
    line. Until they pick one, nothing is flagged."""
    if actual <= estimate:
        return False
    mode, value = setting.get("mode"), setting.get("value")
    if mode == DIFFERENCE_MODES[0]:
        return True
    if mode == DIFFERENCE_MODES[1] and isinstance(value, (int, float)):
        return actual - estimate > value
    if mode == DIFFERENCE_MODES[2] and isinstance(value, (int, float)) \
            and estimate:
        return (actual - estimate) / estimate * 100 > value
    return False


def all_lines() -> list[dict[str, Any]]:
    return list(_read()["lines"].values())


def open_lines(rows: list[dict[str, Any]] | None = None
               ) -> list[dict[str, Any]]:
    rows = all_lines() if rows is None else rows
    return [r for r in rows if r.get("status") == OPEN]


# ===========================================================================
# The arithmetic, and everything it refuses to do
# ===========================================================================

#: Why a line could not be turned into a yearly figure. Each one is reported
#: rather than the line being quietly dropped — a figure that silently
#: omitted something would understate the money the organisation carries.
NO_BASIS = "no basis recorded"
BY_USE_WHY = "charged by how much you use it"
NO_HEADCOUNT = "priced per person with no headcount recorded"
NO_NUMBER = "no number against it"


def figure(line: dict[str, Any]) -> float | None:
    """What this line holds, preferring the actual over the estimate.

    Where a line holds both, every figure reads the actual. Where it holds
    one of the two, it reads the one it has. Where it holds neither, it
    contributes nothing and is counted under "No number against it".
    """
    for key in ("actual", "estimate"):
        value = line.get(key)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def a_year(line: dict[str, Any]) -> tuple[float, float, str]:
    """(yearly, one-off, why it could not be annualized).

    A year is taken as it stands. A month is multiplied by twelve. Each
    person each month is multiplied by twelve and by the headcount recorded
    *on that line* — where none was recorded the line is excluded, because
    the application does not have the organization's headcount and will not
    guess it.

    One-off is never annualized and is reported separately. How much we use
    it cannot be turned into a yearly figure by any means the application
    has. No charge contributes zero and is included. We are not sure is
    excluded: an amount without a basis could be a month or a decade, and
    the application will not pick one.
    """
    basis = line.get("basis") or ""
    amount = figure(line)

    if basis == NO_CHARGE:
        return 0.0, 0.0, ""
    if not basis:
        return 0.0, 0.0, NO_BASIS
    if basis == UNSURE:
        return 0.0, 0.0, NO_BASIS
    if basis == BY_USE:
        return 0.0, 0.0, BY_USE_WHY
    if amount is None:
        return 0.0, 0.0, NO_NUMBER
    if basis == A_YEAR:
        return amount, 0.0, ""
    if basis == A_MONTH:
        return round(amount * 12, 2), 0.0, ""
    if basis == ONE_OFF:
        return 0.0, amount, ""
    if basis == PER_PERSON_MONTH:
        heads = int(line.get("headcount") or 0)
        if heads <= 0:
            return 0.0, 0.0, NO_HEADCOUNT
        return round(amount * 12 * heads, 2), 0.0, ""
    return 0.0, 0.0, NO_BASIS


def totals(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Yearly, one-off, hours, and everything left out — with the reason."""
    yearly = one_off = 0.0
    hours_year = hours_once = 0.0
    left_out: dict[str, int] = {}

    for line in rows:
        year, once, why = a_year(line)
        yearly += year
        one_off += once
        hours_year += float(line.get("hours_a_year") or 0)
        hours_once += float(line.get("hours_one_off") or 0)
        if why:
            left_out[why] = left_out.get(why, 0) + 1

    return {
        "a_year": round(yearly, 2),
        "one_off": round(one_off, 2),
        # Totalled separately and never turned into money.
        "hours_a_year": round(hours_year, 2),
        "hours_one_off": round(hours_once, 2),
        "left_out": left_out,
    }


# ===========================================================================
# The money strip
# ===========================================================================

def _money(value: float) -> str:
    return f"${value:,.0f}"


def money_strip(rows: list[dict[str, Any]] | None = None, *,
                projects: dict[str, dict[str, Any]] | None = None
                ) -> dict[str, Any]:
    """Three sentences, then what those three sentences leave out.

    `projects` maps a project reference to its `in_use`, `gate` and `state`.
    Passed in rather than read here: those three fields are written by
    Projects and by no other surface, and two surfaces reading the same
    record by different routes is how they come to disagree.
    """
    rows = open_lines() if rows is None else open_lines(rows)
    projects = projects or {}

    def running(line: dict[str, Any]) -> bool:
        # A cost with no project to read — the money it takes to run the
        # governance work — is money carried today, so a committed one
        # counts.
        if line.get("not_one_project"):
            return True
        held = projects.get(line.get("project") or "")
        if not held:
            return False
        if held.get("in_use") == spine.IN_USE_YES:
            return True
        # A tool being trialled has reached Test, and the money on it is
        # being spent whatever the trial concludes.
        gate = held.get("gate") or ""
        state = held.get("state") or ""
        reached = not spine.before(gate, spine.TEST)
        return reached and state not in (spine.RETIRED, spine.TURNED_DOWN)

    committed_running = [r for r in rows
                         if r.get("committed") and running(r)]
    everything = rows
    leaving = [r for r in rows if r.get("kind") == LEAVING]
    retired = [r for r in rows if r.get("committed")
               and (projects.get(r.get("project") or "") or {}).get("state")
               == spine.RETIRED]
    from_a_change = [r for r in rows if r.get("version")]

    first = totals(committed_running)
    second = totals(everything)
    third = totals(leaving)
    after = totals(retired)
    changed = totals(from_a_change)

    with_leaving = {r.get("project") for r in leaving if r.get("project")}
    all_projects = {r.get("project") for r in rows if r.get("project")}
    nothing_for_leaving = len(all_projects - with_leaving)

    headline = [
        (f"{_money(first['a_year'])} a year, and {_money(first['one_off'])} "
         f"one-off, committed on everything you are running or trialling."),
        (f"{_money(second['a_year'])} a year, and "
         f"{_money(second['one_off'])} one-off, across everything recorded "
         f"here, committed or not."),
        (f"{_money(third['a_year'] + third['one_off'])} recorded as what it "
         f"would cost to leave. {nothing_for_leaving} project"
         f"{'' if nothing_for_leaving == 1 else 's'} have nothing recorded "
         f"for that at all."),
    ]

    # Each renders only where its figure is above zero.
    conditional: list[str] = []
    if after["a_year"]:
        conditional.append(
            f"{_money(after['a_year'])} a year still committed on tools you "
            f"have retired.")
    if changed["a_year"] or changed["one_off"]:
        conditional.append(
            f"{_money(changed['a_year'])} a year, and "
            f"{_money(changed['one_off'])} one-off, arrived with a change a "
            f"vendor made after you bought the tool.")
    hours_lines = [r for r in rows
                   if (r.get("hours_a_year") or r.get("hours_one_off"))
                   and figure(r) is None]
    if hours_lines:
        conditional.append(
            f"{len(hours_lines)} line"
            f"{'' if len(hours_lines) == 1 else 's'} carry hours of staff "
            f"time with no money against them — "
            f"{second['hours_a_year']:g} hours a year, and "
            f"{second['hours_one_off']:g} hours one-off.")
    for why, count in second["left_out"].items():
        conditional.append(
            f"{count} line{'' if count == 1 else 's'} {why}, so "
            f"{'it is' if count == 1 else 'they are'} in none of these "
            f"figures.")

    return {"headline": headline, "conditional": conditional,
            "committed_running": first, "everything": second,
            "leaving": third, "no_lifetime_total": NO_LIFETIME_TOTAL}


#: Shown wherever a figure is. The reason is the point: a total built on a
#: guessed life span would be the number quoted back in the meeting.
NO_LIFETIME_TOTAL = (
    "There is no lifetime total here. A lifetime total needs a number of "
    "years, and nobody has told this application how long any of this will "
    "run. What it can work out without inventing anything is a yearly "
    "figure and a one-off figure, so those are the two it shows. If you "
    "want a lifetime number, multiply the yearly figure by the number of "
    "years you are prepared to defend, and record that you chose it.")


# ===========================================================================
# What the business case reads
# ===========================================================================

def full_cost(project: str, *, counts_as_cost: list[str] | None = None,
              rows: list[dict[str, Any]] | None = None,
              gaps: list[str] | None = None) -> dict[str, Any]:
    """The figure the business case argues from, computed here and shown
    there. Nobody types it twice.

    A cost kind the organization ticked with no line and no recorded gap
    shows as the kind, and the words "Nothing recorded" — rather than the
    total quietly leaving it out.
    """
    rows = open_lines() if rows is None else open_lines(rows)
    mine = [r for r in rows if r.get("project") == project]
    wanted = list(counts_as_cost or list(KINDS))
    recorded = {r.get("kind") for r in mine} | set(gaps or [])

    got = totals(mine)
    missing = [{"kind": k, "label": KINDS.get(k, k),
                "says": "Nothing recorded"}
               for k in wanted if k not in recorded]

    return {
        "project": project,
        "a_year": got["a_year"],
        "one_off": got["one_off"],
        "hours_a_year": got["hours_a_year"],
        "hours_one_off": got["hours_one_off"],
        # Named rather than silently dropped.
        "left_out": got["left_out"],
        "nothing_recorded": missing,
        "no_lifetime_total": NO_LIFETIME_TOTAL,
        # The claim about what comes back lives on the project, in the
        # organisation's own words. This surface never renders it as a
        # figure, never annualises it, never nets it against a cost, and
        # never carries it into a total.
        "no_return_computed": NO_RETURN,
    }


NO_RETURN = (
    "What you expect to get back is recorded on the project, in your own "
    "words, as a claim to be checked later. It is not turned into a figure "
    "here, netted against a cost, or used to work out a payback period. "
    "What this surface contributes is one half of that question, which is "
    "what the thing cost.")


# ===========================================================================
# The stat row
# ===========================================================================

def counters(rows: list[dict[str, Any]] | None = None, *,
             counts_as_cost: list[str] | None = None,
             gaps_by_project: dict[str, list[str]] | None = None,
             projects_at_identify: list[str] | None = None
             ) -> dict[str, Any]:
    """Five plain counts of rows. None weighted, averaged, scored or
    compared to anybody else."""
    rows = all_lines() if rows is None else rows
    live = open_lines(rows)
    gaps_by_project = gaps_by_project or {}

    by_project: dict[str, set[str]] = {}
    for line in live:
        key = line.get("project") or ""
        if key:
            by_project.setdefault(key, set()).add(line.get("kind"))
    for key, kinds in gaps_by_project.items():
        by_project.setdefault(key, set()).update(kinds)

    if counts_as_cost:
        estimated = sum(1 for kinds in by_project.values()
                        if set(counts_as_cost) <= kinds)
        says = ""
    else:
        # Never measured against a list of kinds the organisation did not
        # tick. With no list there is no denominator, so this counts the
        # projects holding anything at all.
        estimated = sum(1 for kinds in by_project.values() if kinds)
        says = ("You have not said what counts as cost, so this counts the "
                "projects that have anything recorded against them at all.")

    no_number = sum(1 for r in live if figure(r) is None)
    over = sum(1 for r in live
               if isinstance(r.get("estimate"), (int, float))
               and isinstance(r.get("actual"), (int, float))
               and r["actual"] > r["estimate"])

    considered = set(projects_at_identify or list(by_project))
    with_leaving = {r.get("project") for r in live
                    if r.get("kind") == LEAVING and r.get("project")}
    with_leaving |= {p for p, kinds in gaps_by_project.items()
                     if LEAVING in kinds}

    return {
        # Every line in any status, including withdrawn and superseded.
        # The register never shrinks.
        "recorded": len(rows),
        "full_cost_estimated": estimated,
        "no_number_against_it": no_number,
        "no_cost_of_leaving": len(considered - with_leaving),
        "costing_more_than_estimated": over,
        "says": {
            "full_cost_estimated": says,
            "no_cost_of_leaving": (
                "It is counted here whether or not you said it counts as "
                "cost, because it is the one most organizations find out "
                "about late. Nothing here will be flagged for it."),
        },
    }


#: Written for this surface rather than taken from the shared bank. The
#: obvious phrase, "Recorded as unknown", is already taken by another
#: surface over a different population — records carrying any open gap,
#: rather than cost lines carrying no figure. Two surfaces showing one
#: counter name over two populations is the confusion the bank exists to
#: prevent.
OWN_COUNTER_NAME = "No number against it"


# ===========================================================================
# Findings
# ===========================================================================

OWN_FINDINGS: tuple[spine.Finding, ...] = (
    spine.Finding(
        "finding.budget.not_estimated", "Budget",
        "The organization said full cost must be estimated before "
        "committing, and a record at or past Procure has kinds with neither "
        "a cost line nor a recorded gap",
        "You said the full cost has to be estimated before you commit. "
        "Nothing is recorded here for: [their kinds, in their own words]."),
    spine.Finding(
        "finding.budget.exit_cost_missing", "Budget",
        "The leaving kind is ticked, and a record at or past Procure has no "
        "leaving line and no gap for one",
        "You said what it costs to leave counts as cost. Nothing here says "
        "what leaving this one would cost."),
    spine.Finding(
        "finding.budget.over_estimate", "Budget",
        "Lifetime cost is tracked against the original estimate, and a line's "
        "actual exceeds its estimate by more than the difference the "
        "organization said is worth a conversation",
        "You said full lifetime cost is tracked against the original "
        "estimate. This one was estimated at [estimate] and came in at "
        "[actual]."),
    spine.Finding(
        "finding.budget.price_disagrees", "Budget",
        "A license line naming a supplier annualizes to a figure different "
        "from the price recorded on that supplier",
        "The price recorded against this supplier and the license cost "
        "recorded here are not the same number: [Vendors figure] against "
        "[Budget figure]."),
    spine.Finding(
        "finding.budget.no_budget_contact", "Budget",
        "A budget contact must be named, and a record with cost lines has "
        "none",
        "You said a budget contact has to be named for every tool. This one "
        "has cost recorded and nobody named against the money."),
    spine.Finding(
        "finding.budget.funding_ends_first", "Budget",
        "Funding not being renewed triggers a review, and money on a tool in "
        "use runs out before its next scheduled look",
        "You said funding not being renewed should trigger a review. The "
        "money on this one runs out on [date] and it is in use."),
    spine.Finding(
        "finding.budget.roi_without_baseline", "Budget",
        "A return figure is required for tools bought, and a project with "
        "cost recorded has no baseline",
        "You said a return figure is required for tools you buy. There is "
        "cost recorded here and no baseline to compare it to."),
    spine.Finding(
        "finding.budget.energy_missing", "Budget",
        "Energy and environmental cost is to be considered, and a record at "
        "or past Procure has no energy line and no gap for one",
        "You said energy and environmental cost should be considered. "
        "Nothing is recorded here for it."),
    spine.Finding(
        "finding.budget.no_actual_recorded", "Budget",
        "Lifetime cost is tracked, and a record past Deploy has estimates, "
        "no actual, and is past its own review frequency",
        "You said full lifetime cost is tracked against the original "
        "estimate. Nothing has been recorded as an actual on this one, and "
        "you said you look [their frequency]."),
    spine.Finding(
        "finding.budget.line_open_after_retirement", "Budget",
        "The record is retired and a line on it is still open",
        "This was retired on [date] and this cost line is still open."),
    spine.Finding(
        "finding.budget.included_but_extra", "Budget",
        "Recorded as switched on inside something already owned, and also "
        "as costing extra",
        "This is recorded as switched on inside something you already own, "
        "and also as costing extra. That second answer describes a "
        "purchase."),
    spine.Finding(
        "finding.budget.threshold_crossed", "Budget",
        "Approved by a User under the delegation amount, and the record's "
        "committed total is at or above it",
        "You said anything under [their amount] moves without [their "
        "decision role]. This one was approved by [role] and what is "
        "recorded here comes to [committed total]."),
)
BY_OWN_FINDING = {f.id: f for f in OWN_FINDINGS}


def findings(rows: list[dict[str, Any]] | None = None, *,
             projects: dict[str, dict[str, Any]] | None = None,
             vendor_price: dict[str, float] | None = None,
             tracks_lifetime: bool = False,
             difference: dict[str, Any] | None = None
             ) -> list[dict[str, Any]]:
    """The findings read line by line. The ones that read a whole project
    against the organization's list of kinds are in `project_findings`.

    `vendor_price` maps a supplier's id to its yearly price on Vendors."""
    rows = open_lines() if rows is None else open_lines(rows)
    projects = projects or {}
    vendor_price = vendor_price or {}
    difference = difference if difference is not None else difference_setting()
    found: list[dict[str, Any]] = []

    for line in rows:
        estimate, actual = line.get("estimate"), line.get("actual")
        # 3.3 — only where they adopted the rule, and only past the line
        # they said is worth a conversation. Otherwise it is a count.
        if (tracks_lifetime and isinstance(estimate, (int, float))
                and isinstance(actual, (int, float))
                and worth_a_conversation(estimate, actual, difference)):
            found.append({
                "id": "finding.budget.over_estimate", "line": line["ref"],
                "says": (f"You said full lifetime cost is tracked against the "
                         f"original estimate. This one was estimated at "
                         f"{_money(estimate)} and came in at "
                         f"{_money(actual)}.")})

        # 3.10 — reads the state, not the gate.
        for ref in line.get("projects") or [line.get("project")]:
            held = projects.get(ref or "") or {}
            if held.get("state") == spine.RETIRED:
                when = str(held.get("last_moved") or "")[:10] or "a recorded date"
                found.append({
                    "id": "finding.budget.line_open_after_retirement",
                    "line": line["ref"],
                    "says": f"This was retired on {when} and this cost line "
                            f"is still open."})
                break

        # 3.4 — shown rather than resolved: the application has no way of
        # knowing which of the two numbers you typed is the right one.
        theirs = vendor_price.get(line.get("supplier") or "")
        if theirs is None:
            theirs = vendor_price.get(line.get("project") or "")
        mine = a_year(line)[0]
        if (line.get("kind") == "licence" and theirs is not None
                and mine and abs(mine - theirs) > 0.5):
            found.append({
                "id": "finding.budget.price_disagrees", "line": line["ref"],
                "says": (f"The price recorded against this supplier and the "
                         f"license cost recorded here are not the same "
                         f"number: {_money(theirs)} against "
                         f"{_money(mine)}.")})
    return found


# ===========================================================================
# §4 · The comparison
# ===========================================================================

def comparison(rows: list[dict[str, Any]] | None = None, *,
               vendor_price: dict[str, float] | None = None) -> dict[str, Any]:
    """Two comparisons, reported separately. Reads what was typed and
    nothing else, and writes nothing.

    The five estimate-against-actual counts are mutually exclusive and add
    up to every open line, so a reader can check the arithmetic on the
    screen."""
    rows = open_lines() if rows is None else open_lines(rows)
    vendor_price = vendor_price or {}
    agree = disagree = est_only = act_only = cannot = 0
    for line in rows:
        e, a = line.get("estimate"), line.get("actual")
        has_e, has_a = isinstance(e, (int, float)), isinstance(a, (int, float))
        _, _, why = a_year(line)
        if why in (BY_USE_WHY, NO_HEADCOUNT, NO_BASIS) or \
                line.get("estimate_unsure") or line.get("actual_unsure") or \
                (not has_e and not has_a):
            cannot += 1
        elif has_e and has_a:
            if a == e:
                agree += 1
            else:
                disagree += 1
        elif has_e:
            est_only += 1
        else:
            act_only += 1

    match = differ = no_supplier = unknown = 0
    for line in rows:
        if line.get("kind") != "licence":
            continue
        theirs = vendor_price.get(line.get("project") or "")
        mine = a_year(line)[0]
        if theirs is None:
            no_supplier += 1
        elif not mine or theirs == 0 and not mine:
            unknown += 1
        elif abs(mine - theirs) <= 0.5:
            match += 1
        else:
            differ += 1
    return {
        "says": ("Two numbers are compared against each other every night: "
                 "what you estimated against what you recorded as actual, and "
                 "the license cost recorded here against the price recorded "
                 "against the supplier. Nothing is fetched from anywhere."),
        "estimate_actual": [[agree, "Both numbers, and they agree"],
                            [disagree, "Both numbers, and they disagree"],
                            [est_only, "Estimate only"],
                            [act_only, "Actual only"],
                            [cannot, "Cannot be compared"]],
        "vendors": [[match, "License lines that match the supplier's price"],
                    [differ, "That do not"],
                    [no_supplier, "With no supplier recorded to compare against"],
                    [unknown, "Where one of the two figures is unknown"]],
        "cannot": COMPARISON_CANNOT,
    }


COMPARISON_CANNOT = (
    "This reads what you typed and nothing else. It is not connected to your "
    "accounting system, your purchasing system, your card statements or your "
    "bank, and it never will be without you being told exactly what was "
    "connected and what it can see. It cannot tell you what you actually "
    "spent. It can tell you when the two numbers you gave it stopped "
    "agreeing, and it can tell you which lines have only ever had one "
    "number. If this screen showed a figure as your actual spend, somebody "
    "would quote it as your actual spend.")


# ===========================================================================
# §7 · Framework read-back, and the whole screen
# ===========================================================================

_CADENCE_DAYS = {"monthly": 31, "quarterly": 92, "biannual": 183,
                 "annual": 366}


def _lower_first(text: str) -> str:
    text = str(text or "")
    return text[:1].lower() + text[1:] if text else text


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def extras(key: str) -> dict[str, Any]:
        return m.value_of(answers, key)[1]

    def asked(key: str) -> bool:
        q = m.by_key(key)
        return bool(q) and m.answered(q, answers)

    def listed(key: str) -> list[str]:
        got = value(key) if asked(key) else []
        return [g for g in (got if isinstance(got, list) else [got])
                if g and g != m.UNKNOWN]

    out: dict[str, Any] = {}
    out["full_cost_required"] = value("proc.full_cost") == "yes"
    out["full_cost_answered"] = asked("proc.full_cost")
    ticked = [k for k in listed("proc.cost_parts") if k in FRAMEWORK_KINDS]
    out["counts_as_cost"] = ticked
    optional = listed("floor.optional")
    out["tracks_lifetime"] = "lifetime" in optional
    out["roi_required"] = "roi" in optional
    out["energy"] = "energy" in optional
    if out["energy"] and ENERGY not in out["counts_as_cost"]:
        out["counts_as_cost"] = out["counts_as_cost"] + [ENERGY]
    out["budget_contact_required"] = "budget" in listed("floor.named")
    out["funding_trigger"] = "funding" in listed("watch.triggers")
    # 4.6 · a set amount below which things move without the decision-maker.
    without = listed("who.without")
    amount = None
    if "under_amount" in without:
        for held in (extras("who.without") or {}).values():
            try:
                amount = float(str(held).replace("$", "").replace(",", ""))
                break
            except (TypeError, ValueError):
                continue
    out["delegation_amount"] = amount
    # 9.3 · how often each level is looked at.
    cadence = value("watch.cadence") if asked("watch.cadence") else {}
    out["review_days"] = {
        name: _CADENCE_DAYS.get(((cadence or {}).get(v) or {}).get("every"))
        for v, name in m.level_names(answers)}
    # 8.5 · a vendor adds AI to something already owned.
    q85 = m.by_key("proc.added_ai")
    got85 = value("proc.added_ai")
    out["added_ai_words"] = next((o.label for o in (q85.options if q85 else [])
                                  if o.value == got85), "")
    # 2.2 · what they already run.
    q22 = m.by_key("have.software")
    have = listed("have.software")
    out["first_software"] = next((o.label for o in (q22.options if q22 else [])
                                  if o.value in have), "")
    # 1.2 · a small organisation.
    out["small"] = value("org.size") == "u25"
    return out


def project_findings(*, rows: list[dict[str, Any]], projects: dict[str, dict],
                     inputs: dict[str, Any], gaps: list[dict[str, Any]],
                     today: str = "") -> list[dict[str, Any]]:
    """The findings that read a whole project against the organization's
    own list of what counts as cost."""
    today = today or clock.today_str()
    live = open_lines(rows)
    found: list[dict[str, Any]] = []
    by_project: dict[str, list[dict[str, Any]]] = {}
    for line in live:
        for ref in line.get("projects") or ([line["project"]]
                                            if line.get("project") else []):
            by_project.setdefault(ref, []).append(line)
    gap_kinds: dict[str, set[str]] = {}
    for g in gaps:
        gap_kinds.setdefault(g.get("project", ""), set()).add(g.get("kind"))

    for ref, project in projects.items():
        gate = project.get("gate") or ""
        at_procure = bool(gate) and not spine.before(gate, spine.PROCURE)
        mine = by_project.get(ref, [])
        answered = {l.get("kind") for l in mine} | gap_kinds.get(ref, set())
        name = project.get("name") or ref

        if at_procure and inputs["full_cost_required"]:
            missing = [KINDS[k] for k in inputs["counts_as_cost"]
                       if k not in answered and k in KINDS]
            if missing:
                found.append({
                    "id": "finding.budget.not_estimated", "project": ref,
                    "says": f"You said the full cost has to be estimated "
                            f"before you commit. Nothing is recorded here for: "
                            f"{', '.join(_lower_first(k) for k in missing)}."})
        if at_procure and LEAVING in inputs["counts_as_cost"] and \
                LEAVING not in answered:
            found.append({
                "id": "finding.budget.exit_cost_missing", "project": ref,
                "says": "You said what it costs to leave counts as cost. "
                        "Nothing here says what leaving this one would cost."})
        if at_procure and inputs["energy"] and ENERGY not in answered:
            found.append({
                "id": "finding.budget.energy_missing", "project": ref,
                "says": "You said energy and environmental cost should be "
                        "considered. Nothing is recorded here for it."})
        if inputs["budget_contact_required"] and mine and not any(
                str(l.get("owner") or "").strip() for l in mine):
            found.append({
                "id": "finding.budget.no_budget_contact", "project": ref,
                "says": "You said a budget contact has to be named for every "
                        "tool. This one has cost recorded and nobody named "
                        "against the money."})
        # 3.7 — suppressed where a tool was found running and the missing
        # baseline is a recorded gap with an owner.
        if inputs["roi_required"] and mine and not str(
                project.get("baseline") or "").strip():
            gapped = any(isinstance(g, dict) and "baseline" in str(
                g.get("field", "")) and g.get("owner")
                for g in project.get("gaps") or [])
            if not (project.get("in_use") == spine.IN_USE_YES and gapped):
                found.append({
                    "id": "finding.budget.roi_without_baseline", "project": ref,
                    "says": "You said a return figure is required for tools "
                            "you buy. There is cost recorded here and no "
                            "baseline to compare it to."})
        # 3.6 — money running out before the next look, on a tool in use.
        days = inputs["review_days"].get(project.get("level") or "")
        if inputs["funding_trigger"] and project.get("in_use") == \
                spine.IN_USE_YES and days:
            from datetime import date, timedelta
            horizon = (date.fromisoformat(today) +
                       timedelta(days=days)).isoformat()
            for line in mine:
                ends = str(line.get("ends") or "")[:10]
                if ends and ends < horizon:
                    found.append({
                        "id": "finding.budget.funding_ends_first",
                        "project": ref, "line": line["ref"],
                        "says": f"You said funding not being renewed should "
                                f"trigger a review. The money on this one "
                                f"runs out on {ends} and it is in use."})
        # 3.9 — past Deploy, estimates, no actual, past their own frequency.
        if inputs["tracks_lifetime"] and days and gate and \
                spine.before(spine.DEPLOY, gate):
            estimated = [l for l in mine
                         if isinstance(l.get("estimate"), (int, float))]
            actualled = [l for l in mine
                         if isinstance(l.get("actual"), (int, float))]
            oldest = min((str(l.get("added") or "")[:10] for l in estimated),
                         default="")
            from datetime import date
            try:
                gone = (date.fromisoformat(today) -
                        date.fromisoformat(oldest)).days if oldest else 0
            except ValueError:
                gone = 0
            if estimated and not actualled and gone > days:
                found.append({
                    "id": "finding.budget.no_actual_recorded", "project": ref,
                    "says": "You said full lifetime cost is tracked against "
                            "the original estimate. Nothing has been recorded "
                            "as an actual on this one, and you said you look "
                            "at it on a set cycle."})
        # 3.11 — switched on inside something owned, and costing extra.
        if project.get("route") in ("activated", "found") and any(
                l.get("included_or_extra") == COSTS_EXTRA for l in mine):
            found.append({
                "id": "finding.budget.included_but_extra", "project": ref,
                "says": "This is recorded as switched on inside something you "
                        "already own, and also as costing extra. That second "
                        "answer describes a purchase."})
        # 3.12 — the committed total against their own amount.
        amount = inputs["delegation_amount"]
        # Who approved the Procure passage is read off the passage itself —
        # the one leaving Procure, forward — rather than a field somebody
        # has to remember to set.
        passage = next((p for p in reversed(project.get("passages") or [])
                        if p.get("from") == spine.PROCURE and
                        not spine.before(str(p.get("to") or ""), spine.PROCURE)),
                       None)
        hat = (passage or {}).get("hat") or project.get("approved_by_hat")
        if amount is not None and hat == "operator":
            committed = [l for l in mine if l.get("committed")]
            got = totals(committed)
            total = got["a_year"] + got["one_off"]
            if committed and total >= amount:
                left = sum(got["left_out"].values())
                found.append({
                    "id": "finding.budget.threshold_crossed", "project": ref,
                    "says": f"You said anything under {_money(amount)} moves "
                            f"without whoever decides. This one was approved "
                            f"by {(passage or {}).get('by_title') or 'somebody in the User hat'} "
                            f"and what is recorded here comes "
                            f"to {_money(total)}."
                            + (f" {left} lines could not be added to that "
                               f"figure." if left else "")})
    # 3.13 — a gap with nobody named.
    for g in gaps:
        if not str(g.get("owner") or "").strip():
            found.append({"id": "finding.gap_no_owner",
                          "project": g.get("project", ""),
                          "says": spine.BY_FINDING["finding.gap_no_owner"].says})
    return found


def surface(*, answers: dict[str, Any] | None,
            projects: list[dict[str, Any]] | None = None,
            vendors_rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    inputs = framework_inputs(answers)
    rows = all_lines()
    gaps = kind_gaps()
    projects = [p for p in (projects or []) if p.get("ref")]
    by_ref = {p["ref"]: p for p in projects}
    # Each supplier's yearly price, read against the projects it serves.
    vendor_price: dict[str, float] = {}
    for v in vendors_rows or []:
        yearly = v.get("a_year")
        if yearly is None and isinstance(v.get("amount"), (int, float)):
            yearly = {"year": v["amount"], "month": v["amount"] * 12}.get(
                v.get("basis") or "")
        if yearly:
            for ref in v.get("projects") or []:
                vendor_price[ref] = float(yearly)

    difference = difference_setting()
    raised = findings(rows, projects=by_ref, vendor_price=vendor_price,
                      tracks_lifetime=inputs["tracks_lifetime"],
                      difference=difference) + project_findings(
        rows=rows, projects=by_ref, inputs=inputs, gaps=gaps)

    gaps_by_project: dict[str, list[str]] = {}
    for g in gaps:
        gaps_by_project.setdefault(g.get("project", ""), []).append(g["kind"])
    at_identify = [p["ref"] for p in projects if p.get("gate")]
    count = counters(rows, counts_as_cost=inputs["counts_as_cost"] or None,
                     gaps_by_project=gaps_by_project,
                     projects_at_identify=at_identify)
    count["says"]["no_cost_of_leaving"] = (
        "You said what it costs to leave counts as cost."
        if LEAVING in inputs["counts_as_cost"] else
        "You did not count this as cost at question 8.7b. It is counted here "
        "anyway, because it is the one most organizations find out about "
        "late. Nothing here will be flagged for it.")

    # §5.1 · grouped by project, ticked kinds first in the framework's order.
    order = {k: i for i, k in enumerate(list(FRAMEWORK_KINDS) + [ENERGY, OTHER])}
    groups = []
    for p in projects:
        mine = [l for l in rows if p["ref"] in (l.get("projects") or [])]
        mine.sort(key=lambda l: (0 if l.get("kind") in inputs["counts_as_cost"]
                                 else 1, order.get(l.get("kind"), 99)))
        answered = {l.get("kind") for l in mine if l.get("status") == OPEN}
        gapped = {g["kind"]: g for g in gaps if g.get("project") == p["ref"]}
        nothing = [{"kind": k, "label": KINDS[k]}
                   for k in inputs["counts_as_cost"]
                   if k not in answered and k not in gapped and k in KINDS]
        if mine or nothing or gapped:
            groups.append({"project": p["ref"], "name": p.get("name", ""),
                           "lines": [l["ref"] for l in mine],
                           "nothing_recorded": nothing,
                           "gaps": list(gapped.values()),
                           "full_cost": full_cost(
                               p["ref"], counts_as_cost=inputs["counts_as_cost"],
                               rows=rows, gaps=list(gapped))})
    programme = [l["ref"] for l in rows if l.get("not_one_project")]

    listed = []
    for l in rows:
        year, once, why = a_year(l)
        listed.append({
            **l,
            "kind_shown": (l.get("other_kind") if l.get("kind") == OTHER
                           and l.get("other_kind") else
                           KINDS.get(l.get("kind") or "", "Not said")),
            "basis_shown": BASIS.get(l.get("basis") or "", "Not said"),
            "estimate_shown": ("We are not sure" if l.get("estimate_unsure")
                               else _money(l["estimate"])
                               if isinstance(l.get("estimate"), (int, float))
                               else ""),
            "actual_shown": ("We are not sure" if l.get("actual_unsure")
                             else _money(l["actual"])
                             if isinstance(l.get("actual"), (int, float))
                             else ""),
            "above_estimate": isinstance(l.get("estimate"), (int, float))
            and isinstance(l.get("actual"), (int, float))
            and l["actual"] > l["estimate"],
            "status_shown": LINE_STATUS.get(l.get("status") or OPEN, ""),
            "left_out_why": why,
            "projects_shown": ", ".join(by_ref.get(r, {}).get("name", r)
                                        for r in l.get("projects") or [])
            or ("Not tied to one project" if l.get("not_one_project") else ""),
        })

    empty = ("Nothing recorded yet. You said the full cost does not have to "
             "be estimated before you commit, so nothing on this screen will "
             "be flagged for being incomplete. This is still the place the "
             "money lives. Start with the tool you are already paying for."
             if inputs["full_cost_answered"] and not inputs["full_cost_required"]
             else f"Nothing recorded yet. You told us you already run "
             f"{_lower_first(inputs['first_software'])}. Start there: one "
             f"line for what you pay for it now, and one line for what it "
             f"would cost to leave it." if inputs["first_software"] else
             "Nothing recorded yet. Start with the tool you are already "
             "paying for, and write down what it would cost to leave it "
             "before you write down what it costs to keep it. What it costs "
             "to keep it is on an invoice somewhere. What it would cost to "
             "leave decides whether you are free to stop, and that number is "
             "usually not written down anywhere.")

    return {
        "counters": count,
        "money": money_strip(rows, projects=by_ref),
        "raised": raised,
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "comparison": comparison(rows, vendor_price=vendor_price),
        "groups": groups,
        "programme": programme,
        "lines": listed,
        "empty": empty,
        "difference": difference,
        "inputs": inputs,
        "projects": [{"ref": p["ref"], "name": p.get("name", ""),
                      "versions": [v for v in p.get("versions") or []
                                   if isinstance(v, dict)],
                      "accountable": p.get("accountable", ""),
                      "route": p.get("route", "")} for p in projects],
        "options": {
            "kinds": [{"value": k, "label": v, "counts": k in
                       inputs["counts_as_cost"]} for k, v in KINDS.items()
                      if k != ENERGY or inputs["energy"]],
            "basis": [{"value": k, "label": v} for k, v in BASIS.items()],
            "hours_kinds": list(HOURS_KINDS),
            "whose_money": list(WHOSE_MONEY),
            "estimate_when": list(ESTIMATE_WHEN),
            "included": list(INCLUDED), "ends_how": list(ENDS_HOW),
            "difference": list(DIFFERENCE_MODES),
        },
        "copy": {
            "no_lifetime_total": NO_LIFETIME_TOTAL,
            "no_return": NO_RETURN,
            "scope": ("This screen holds no invoices, no purchase orders, no "
                      "account codes, no payment details and no authority to "
                      "spend anything. Nothing recorded here moves any money "
                      "or approves anybody to. It records what a tool was "
                      "expected to cost, what it turned out to cost, whose "
                      "money it is and what leaving would cost, so that a "
                      "decision made about the tool can be explained "
                      "afterward. This is a governance register rather than "
                      "a ledger, and your finance office remains the record "
                      "of what was actually spent."),
            "form_head": ("Only the first line is required. A cost register "
                          "that refuses a row until somebody knows the number "
                          "will never hold the costs nobody has priced — staff "
                          "time, getting your information ready, what it costs "
                          "to leave. Those are the costs that decide whether "
                          "you can afford to keep the thing. Write the line "
                          "now. Come back with the number when you have it, or "
                          "record that nobody knows and put a name against "
                          "finding out."),
            "not_required": ("You said the full cost does not have to be "
                             "estimated before you commit. Nothing here will "
                             "be flagged for being incomplete."
                             if inputs["full_cost_answered"]
                             and not inputs["full_cost_required"] else ""),
        },
    }


def report(*, projects: dict[str, dict[str, Any]] | None = None,
           counts_as_cost: list[str] | None = None) -> dict[str, Any]:
    rows = all_lines()
    return {
        "lines": rows,
        "counters": counters(rows, counts_as_cost=counts_as_cost),
        "money": money_strip(rows, projects=projects),
        "basis": BASIS,
        "kinds": KINDS,
        "line_status": LINE_STATUS,
        "findings": [{"id": f.id, "trigger": f.trigger, "says": f.says}
                     for f in OWN_FINDINGS],
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
        "no_lifetime_total": NO_LIFETIME_TOTAL,
        "no_return_computed": NO_RETURN,
    }
