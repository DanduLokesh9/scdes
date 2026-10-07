"""Who is using GAIUS, from where, for how long, and how far they have got.

For IIA, not for an agency. The client asked for "a user usage tracking page
… which state, how many hours he logged in, track every single user and what
they have worked on and their progress", readable by whoever signs in on an
``@iiac.ai`` address.

This crosses the line the rest of the application never crosses — *"THE
ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE OR HAVE ACCESS TO OTHER
AGENCIES."* — for the same reason the bug queue does, and on the same terms.
Reading who is using the product is running GAIUS; it is not governing an
agency. So it is keyed on a proven email address and nothing else, never on a
capacity somebody can pick from a dropdown. See `app/admin.py`.

What this can honestly say
--------------------------

Everything here is read out of the audit log, which is the only record of what
anybody did. That log was built to answer "who changed this clause and when",
and it answers that completely. It was not built to measure attendance, and
two limits follow from that. Both are reported rather than smoothed over,
because a usage page that quietly guesses is worse than one that says what it
does not know.

**There is no record of signing in.** Nothing in five weeks of log is
session-shaped: no sign-in, no sign-out, no heartbeat. So "hours logged in"
cannot be read, and this does not pretend to. What it reports is *time
active* — the span from a person's first action in a sitting to their last,
with a sitting ending after `IDLE_GAP` of silence. Somebody who opens the
framework, reads it for forty minutes and changes nothing registers as no
time at all, and that is the truth of what was recorded rather than a
flattering estimate. `sessions_recorded` on every row says whether real
sign-in events exist for that person yet; they are written from now on, so
this number becomes measured rather than inferred as the log fills.

**Older entries carry no agency.** Request-scoped tenancy came after the
first month of use, so roughly three entries in four predate it and say
nothing about which agency they belonged to. Those are counted under
`unattributed` and left out of the per-agency figures rather than being
guessed at from the actor's name.

Progress is not inferred at all. It is read from each agency's own answer
file, the same way the agency's own screen reads it, so the number on this
page and the number on theirs cannot disagree.
"""

from __future__ import annotations

import collections
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

#: Silence that ends a sitting. Thirty minutes is the convention for web
#: analytics and it is a convention, not a measurement — which is the whole
#: reason the figure it produces is labelled "active" and not "logged in".
IDLE_GAP = timedelta(minutes=30)

#: A sitting with one action in it has no span. Counting it as zero would
#: under-report somebody who signs in, answers one question and leaves, so it
#: is credited with this much and the crediting is stated.
LONE_ACTION = timedelta(minutes=2)

#: Inside a sign-in bracket the idle rule is suspended — silence is reading,
#: not absence — but not indefinitely. Most people close the tab rather than
#: signing out, so a bracket left open would otherwise swallow every action
#: for the next fortnight and report a week-long sitting. Past this much
#: silence the sitting is taken to have ended at the last thing they did.
MAX_SILENCE = timedelta(hours=4)

#: And a hard ceiling, for a bracket that is never closed at all. Nobody sat
#: at this for twelve hours; a figure that says they did discredits every
#: other figure on the page.
MAX_SITTING = timedelta(hours=12)

#: Actions that are somebody working on their framework, grouped so the page
#: can say what they were doing rather than listing forty verbs.
WORK: dict[str, str] = {
    "answer_framework_question": "Answering the framework",
    "answer_who_decides": "Answering the framework",
    "change_who_decides": "Answering the framework",
    "save_framework_version": "Saving a version",
    "adopt_framework_version": "Adopting",
    "record_framework_adoption": "Adopting",
    "upload_existing_policy": "Bringing in existing policy",
    "remove_existing_policy": "Bringing in existing policy",
    "take_snapshot": "Keeping a copy",
    "restore_snapshot": "Keeping a copy",
    "forget_snapshot": "Keeping a copy",
    "reset_agency_configuration": "Starting over",
    "record_data_holding": "Data warehouse",
    "update_data_holding": "Data warehouse",
    "forget_data_holding": "Data warehouse",
    "record_vendor": "Vendor registry",
    "forget_vendor": "Vendor registry",
    "record_project": "Projects",
    "create_project": "Projects",
    "save_appendix_G": "Appendices",
    "save_appendix_J": "Appendices",
    "respond_to_bug": "Running GAIUS",
    "raise_order": "Subscription",
    "settle_invoice": "Subscription",
    "nda_accepted": "Confidentiality",
    "nda_declined": "Confidentiality",
    "nda_locked": "Confidentiality",
    "nda_unlocked": "Confidentiality",
    "sign_in": "Signing in",
    "sign_out": "Signing in",
}

#: The two events that bracket a sitting exactly, rather than approximately.
OPENS = "sign_in"
CLOSES = "sign_out"

#: Words that mark a name as a script rather than a person. Counted
#: separately: a usage page reporting the test harness as its busiest user is
#: not reporting usage.
#:
#: Matched as whole words, not as substrings. "Test" on its own was getting
#: through a substring check against "tester" and "test person", and matching
#: the other way would make a robot of anyone named Tester or Checketts.
ROBOT_WORDS = frozenset((
    "test", "tests", "tester", "testing", "check", "checks", "harness",
    "fixture", "dummy", "sample", "placeholder", "robot", "bot", "qa",
))

#: Whole names that are known fixtures. The people in the test suite have
#: ordinary names on purpose — a fixture called "Test User" does not exercise
#: the same code paths as one called "Dana Reed" — so they cannot be spotted
#: by their words and are listed instead.
ROBOT_NAMES = frozenset((
    "dana reed", "jane smith", "jordan doe", "liz", "council member",
    "office of technology", "operator", "b two", "boot check",
    "switch check", "test person", "test officer", "test", "tester",
))


def _when(row: dict[str, Any]) -> datetime | None:
    try:
        return datetime.fromisoformat(str(row.get("at", "")))
    except ValueError:
        return None


def _is_robot(name: str, agency: str) -> bool:
    if agency == "gaius.harness":
        return True
    low = " ".join((name or "").strip().lower().split())
    if low in ROBOT_NAMES:
        return True
    return bool({w.strip(".,-_") for w in low.split()} & ROBOT_WORDS)


def _pretty(seconds: float) -> str:
    """A duration a person reads, not a float."""
    if seconds < 60:
        return "under a minute"
    minutes = int(seconds // 60)
    if minutes < 60:
        return f"{minutes} min"
    hours, rest = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {rest:02d}m" if rest else f"{hours}h"
    days, rest_h = divmod(hours, 24)
    return f"{days}d {rest_h}h" if rest_h else f"{days}d"


@dataclass
class Sitting:
    """One unbroken run of activity.

    `measured` when a sign-in opened it, which is the difference between
    knowing and estimating: somebody who signs in, reads their framework for
    forty minutes and changes nothing leaves no trail between the two events,
    so the gap rule would split that into two sittings of no length while the
    bracket reports the forty minutes that actually happened.
    """

    started: datetime
    ended: datetime
    actions: int = 0
    measured: bool = False
    #: Set once a sign-out closes it, so a later action cannot extend it.
    closed: bool = False

    @property
    def seconds(self) -> float:
        span = (self.ended - self.started).total_seconds()
        return span or LONE_ACTION.total_seconds()


@dataclass
class Person:
    name: str
    #: Capacity ids they have acted under. Not identities — the header lets a
    #: person choose a capacity, deliberately, and this records that they did
    #: rather than treating each one as somebody new.
    actors: set[str] = field(default_factory=set)
    titles: set[str] = field(default_factory=set)
    agencies: set[str] = field(default_factory=set)
    first: datetime | None = None
    last: datetime | None = None
    actions: int = 0
    refused: int = 0
    worked_on: collections.Counter = field(
        default_factory=collections.Counter)
    sittings: list[Sitting] = field(default_factory=list)
    sign_ins: int = 0
    robot: bool = False

    @property
    def active_seconds(self) -> float:
        return sum(s.seconds for s in self.sittings)


def _still_going(sitting: Sitting, at: datetime) -> bool:
    """Whether this action belongs to the sitting in hand.

    Inside a sign-in bracket the idle rule is suspended, because the sign-in
    is the evidence they were present and silence is reading. Outside one, a
    gap of `IDLE_GAP` ends it. Either way the two bounds above apply, so a
    bracket nobody closed cannot run away with the figures.
    """
    if at - sitting.started > MAX_SITTING:
        return False
    if sitting.measured:
        return at - sitting.ended <= MAX_SILENCE
    return at - sitting.ended <= IDLE_GAP


def _read(path: Any) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            # A truncated final line is a half-written append, not a reason to
            # refuse the whole report.
            continue
    return rows


def _log_path():
    from app.audit import CORPUS
    return CORPUS / "audit" / "log.jsonl"


def people(rows: list[dict[str, Any]] | None = None) -> list[Person]:
    """Everyone who has done anything, and what they did.

    Keyed on the name they entered, because that is the only thing in the log
    that identifies a person: `actor` is the capacity they were acting in and
    one person moves between several of them on purpose.
    """
    rows = rows if rows is not None else _read(_log_path())
    found: dict[str, Person] = {}

    for row in sorted(rows, key=lambda r: str(r.get("at", ""))):
        detail = row.get("detail") or {}
        name = str(detail.get("actor_name") or "").strip()
        agency = str(detail.get("agency") or "")
        if not name:
            # Nothing identifies who this was. Counted in `overview`, not
            # attributed to somebody it might not be.
            continue

        person = found.setdefault(name, Person(name=name))
        person.robot = person.robot or _is_robot(name, agency)
        person.actors.add(str(row.get("actor") or ""))
        title = str(detail.get("actor_title") or "").strip()
        if title:
            person.titles.add(title)
        if agency:
            person.agencies.add(agency)

        person.actions += 1
        if row.get("outcome") and row["outcome"] != "allowed":
            person.refused += 1
        action = str(row.get("action") or "")
        if action == "sign_in":
            person.sign_ins += 1
        person.worked_on[WORK.get(action, "Other")] += 1

        at = _when(row)
        if at is None:
            continue
        person.first = min(person.first or at, at)
        person.last = max(person.last or at, at)

        open_sitting = person.sittings[-1] if person.sittings else None
        if open_sitting and open_sitting.closed:
            open_sitting = None

        if action == OPENS:
            # An explicit start. Whatever came before is finished, however
            # recently — two sign-ins are two sittings even a minute apart.
            if person.sittings:
                person.sittings[-1].closed = True
            person.sittings.append(
                Sitting(started=at, ended=at, actions=1, measured=True))
        elif action == CLOSES and open_sitting:
            open_sitting.ended = at
            open_sitting.actions += 1
            open_sitting.closed = True
        elif open_sitting and _still_going(open_sitting, at):
            open_sitting.ended = at
            open_sitting.actions += 1
        else:
            person.sittings.append(Sitting(started=at, ended=at, actions=1))

    return sorted(found.values(),
                  key=lambda p: p.last or datetime.min.replace(
                      tzinfo=timezone.utc), reverse=True)


def _state_of(agency: str) -> tuple[str, str]:
    """The state code and agency name for a container code."""
    from app import states, tenancy

    known = tenancy.CONFIRMED.get(agency)
    if known:
        return str(known.get("state") or ""), str(known.get("label") or agency)
    for code in list(states.STATE_NAMES) + [states.FEDERAL_CODE]:
        for entry in states.agencies_for(code):
            if entry.get("id") == agency:
                return code, str(entry.get("name") or agency)
    return "", agency


def progress_of(agency: str) -> dict[str, Any]:
    """How far this agency has got, read from its own answer file.

    Not counted from the log. An answer changed twice is one answer, and a
    question that stopped being asked should stop being counted — both of
    which the agency's own file knows and a tally of events does not.
    """
    from app import module_one, tenant, versions

    token = tenant.set_current(agency)
    try:
        held = versions.state()
        answers = held.get("working") or {}
        asked = [q for step in module_one.STEPS for q in step.questions
                 if module_one.visible(q, answers)]
        answered = sum(1 for q in asked
                       if module_one.answered(q, answers))
        saved = held.get("versions") or []
        return {
            "answered": answered,
            "asked": len(asked),
            "percent": round(answered / len(asked) * 100) if asked else 0,
            "versions": len(saved),
            "adopted": bool(held.get("adopted")),
        }
    except Exception as exc:                                  # noqa: BLE001
        # One unreadable container must not take the whole report down.
        return {"answered": 0, "asked": 0, "percent": 0, "versions": 0,
                "adopted": False, "unreadable": type(exc).__name__}
    finally:
        tenant.reset(token)


def agencies(everyone: list[Person]) -> list[dict[str, Any]]:
    """Each agency using the product, with where it is and how far it has got."""
    from app import tenant
    seen: dict[str, dict[str, Any]] = {}
    for person in everyone:
        for agency in person.agencies:
            # "~unresolved" is not an organization: it is where a request with
            # nobody behind it was filed. Shown as a row it read as an agency
            # with work in it. Anything landing there now raises an alarm in
            # the daily technical report instead (app/techreport.py).
            if agency == tenant.ANONYMOUS:
                continue
            state, label = _state_of(agency)
            row = seen.setdefault(agency, {
                "agency": agency, "state": state, "name": label,
                "people": [], "actions": 0, "last": None,
                "test_only": agency.endswith((".test", ".harness")),
            })
            row["people"].append(person.name)
            row["actions"] += person.actions
            if person.last and (row["last"] is None
                                or person.last.isoformat() > row["last"]):
                row["last"] = person.last.isoformat()

    for agency, row in seen.items():
        row["progress"] = progress_of(agency)
        row["people"] = sorted(set(row["people"]))
    return sorted(seen.values(),
                  key=lambda r: (r["last"] or ""), reverse=True)


def report(*, include_robots: bool = False) -> dict[str, Any]:
    """The whole picture, for the admin page."""
    rows = _read(_log_path())
    everyone = people(rows)
    real = [p for p in everyone if not p.robot]
    shown = everyone if include_robots else real

    unattributed = sum(
        1 for r in rows if not (r.get("detail") or {}).get("actor_name"))
    no_agency = sum(
        1 for r in rows if not (r.get("detail") or {}).get("agency"))
    signed_in = sum(p.sign_ins for p in everyone)

    return {
        "people": [{
            "name": p.name,
            "titles": sorted(p.titles),
            "capacities": sorted(a for a in p.actors if a),
            "agencies": sorted(p.agencies),
            "states": sorted({s for s, _ in
                              (_state_of(a) for a in p.agencies) if s}),
            "first_seen": p.first.isoformat() if p.first else "",
            "last_seen": p.last.isoformat() if p.last else "",
            "actions": p.actions,
            "refused": p.refused,
            "sittings": len(p.sittings),
            "active_seconds": round(p.active_seconds),
            "active": _pretty(p.active_seconds),
            "sessions_recorded": p.sign_ins,
            "worked_on": [{"what": what, "times": n}
                          for what, n in p.worked_on.most_common()],
            "test_account": p.robot,
        } for p in shown],
        "agencies": agencies(real),
        "overview": {
            "people": len(real),
            "test_accounts": len(everyone) - len(real),
            "agencies": len({a for p in real for a in p.agencies}),
            "states": len({s for p in real for a in p.agencies
                           for s, _ in [_state_of(a)] if s}),
            "entries": len(rows),
            "first_entry": (rows[0].get("at") if rows else ""),
            "last_entry": (rows[-1].get("at") if rows else ""),
            "active": _pretty(sum(p.active_seconds for p in real)),
        },
        # Said on the page, not buried here. See the module docstring.
        "caveats": {
            "idle_gap_minutes": int(IDLE_GAP.total_seconds() // 60),
            "sign_ins_recorded": signed_in,
            "unattributed_entries": unattributed,
            "entries_without_agency": no_agency,
            "time_is_inferred": signed_in == 0,
            "note": (
                "Time active is inferred from the audit log: a sitting runs "
                f"from a person's first action to their last, and ends after "
                f"{int(IDLE_GAP.total_seconds() // 60)} minutes of silence. "
                "It is not time signed in — reading a screen without "
                "changing anything leaves no trace and counts as nothing. "
                f"{no_agency:,} of {len(rows):,} entries predate "
                "request-scoped tenancy and carry no agency, so they are "
                "excluded from the per-agency figures rather than guessed "
                "at."),
        },
    }
