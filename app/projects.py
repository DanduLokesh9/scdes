"""Projects — the work, gate by gate.

One project per use case, from the problem somebody noticed to the day the
last version is turned off. This is the screen a person opens when they want
to see one piece of work: every other surface answers a question *about* a
project, and this is the page the project itself lives on.

**It is the only surface that may write a project's state.** Every movement
between gates is recorded here. A code path on another surface that writes
`state`, or that creates a project, is the same class of defect.

Three things the spec is firm about, carried into the code rather than left
in prose.

**A project frequently ends without a tool.** The first half of Identify
defines a problem without mentioning technology; the second half walks a
hierarchy that reaches an external vendor last. A project that closes at
Identify because the answer was a two-week process change has been used
correctly, stays on the list with its reasoning intact, and is *counted* —
an organization that declined four AI purchases on the evidence can show
that record to anybody who asks.

**Backfilling is the ordinary case.** On the first day most of this list is
work already under way, running without anybody's approval. Nothing here
uses blame language in any state for any answer, because a register that
punishes the first honest answer never gets a second one.

**It cannot stop a tool being used.** Its only enforcement is declining to
record a passage while a floor that binds there is unsatisfied, and showing
the project as running ahead of its gates until the missing answer exists.
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

#: Where a tenant's projects live. Scoped per agency like every other
#: record: one organisation's work is never visible from another's.
FILENAME = "projects.json"

_LOCK = threading.Lock()

#: The reference alphabet. No vowels, so nothing spells a word by accident;
#: no 0/O or 1/I/L, so nothing is misread over a phone.
#:
#: "Short, opaque, permanent, never reused, and carrying no classification
#: in its shape." No year, no department code, no sequence a reader could
#: use to infer how many projects came before. A reference that encodes the
#: year invites somebody to sort by it and to believe the ordering means
#: something.
ALPHABET = "23456789BCDFGHJKMNPQRSTVWXYZ"
REFERENCE_LENGTH = 6


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file():
    from app import tenant
    from app.audit import CORPUS
    return tenant.scoped(CORPUS / "config" / FILENAME)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return {"projects": {}, "prefix": ""}
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"projects": {}, "prefix": ""}
    if not isinstance(held, dict):
        return {"projects": {}, "prefix": ""}
    held.setdefault("projects", {})
    held.setdefault("prefix", "")
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


def _record(action: str, actor: Any, detail: dict[str, Any], *,
            happened: str = "") -> None:
    """Into the hash-chained trail, like every other decision in the product.

    Every passage, state change, approval, condition and recorded gap writes
    here. This surface never reads it back.
    """
    try:
        from app.authz import default_log
        default_log().append(
            actor=getattr(actor, "user_id", "") or "unknown",
            role=getattr(getattr(actor, "role", None), "value", "")
            or "system",
            action=action, target="Projects", outcome="allowed",
            detail={**detail,
                    "actor_name": str(getattr(actor, "name", "") or "")[:120]},
            happened=happened)
    except Exception:                                         # noqa: BLE001
        pass


# ===========================================================================
# The record
# ===========================================================================

def reference(existing: set[str], prefix: str = "") -> str:
    """A new one, never reused.

    No person is required to issue a reference. A twelve-person district has
    nobody whose job that is, and a register that waits on an office to hand
    out numbers is a register with a queue in front of it.
    """
    head = (prefix or "").strip().upper().rstrip("-")
    for _ in range(64):
        body = "".join(secrets.choice(ALPHABET)
                       for _ in range(REFERENCE_LENGTH))
        ref = f"{head}-{body}" if head else body
        if ref not in existing:
            return ref
    # Astronomically unlikely; lengthen rather than fail. A register that
    # refuses to accept a project because of a collision would be a worse
    # outcome than a slightly longer reference.
    return (f"{head}-" if head else "") + "".join(
        secrets.choice(ALPHABET) for _ in range(REFERENCE_LENGTH + 4))


#: The nine questions of Identify's first half. This half never mentions
#: technology, and the interface enforces that by what it asks rather than by
#: refusing answers. Each is answerable with "I don't know" — a legitimate
#: answer here, and frequently more useful than a guess.
PROBLEM_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("happening", "What's happening?"),
    ("affects", "Who does this affect, and how often?"),
    ("costs", "What does it cost?"),
    ("known_assumed", "What do you know, and what are you assuming?"),
    ("tried", "What's already been tried?"),
    ("who_else", "Who else has this problem?"),
    ("if_nothing", "What happens if nothing changes?"),
    ("how_known", "How would you know it was fixed?"),
    ("parked", "Anything else you noticed along the way"),
)

#: Words that mean somebody has described a solution rather than a problem.
#: Checked against the problem description only, and never against the
#: parked-idea block — parking the solution somebody walked in with is the
#: point of that block.
SOLUTION_WORDS = ("chatgpt", "copilot", "gemini", "claude", "ai tool",
                  "software", "platform", "vendor", "licence", "license",
                  "subscription", "module", "system that", "an app",
                  "chatbot", "automation tool")


def blank_project(name: str, *, ref: str, asked_by: str = "",
                  in_use: str = spine.IN_USE_UNKNOWN) -> dict[str, Any]:
    """A project at the moment it is created.

    Created at Identify, Proposed, with `in_use` from the person's own
    answer. Only the name is required: a register that refuses a row until
    every box is filled is one nobody finishes, and the whole first half of
    this surface exists to be answered slowly by somebody who does not yet
    know the answers.
    """
    return {
        "ref": ref,
        "name": name.strip(),
        "asked_by": asked_by.strip(),
        "gate": spine.IDENTIFY,
        "state": spine.PROPOSED,
        "in_use": in_use,
        "level": "",
        "accountable": "",
        "opened": _now(),
        "last_moved": _now(),
        # Identify, first half.
        "problem": {},
        # Identify, second half — one verdict and one line of reasoning per
        # step. A step skipped silently is the failure that gate exists to
        # prevent.
        "hierarchy": {},
        "chosen_step": 0,
        "chosen_why": "",
        # Written at Procure, read by Measure for the rest of the life of
        # the project.
        "business_case": "",
        "baseline": "",
        "data_grounds": "",
        # The loop.
        "versions": [],
        "sunset": {},
        "conditions": [],
        "gaps": [],
        "passages": [],
        # Floors this record can point at something for. Pointing at
        # something, not asserting it.
        "satisfied": [],
        "seeded": False,
    }


# ===========================================================================
# Reading
# ===========================================================================

def all_projects() -> list[dict[str, Any]]:
    held = _read()
    rows = list(held["projects"].values())
    rows.sort(key=lambda p: str(p.get("last_moved") or ""), reverse=True)
    return rows


def one(ref: str) -> dict[str, Any] | None:
    return _read()["projects"].get(ref)


def prefix() -> str:
    return str(_read().get("prefix") or "")


# ===========================================================================
# The tracker
# ===========================================================================

#: The tracker does not show a percentage, a score, or an estimate of how
#: long the rest will take. The application does not know how long a decision
#: takes in a given organisation, and a guessed estimate would be wrong often
#: enough that people stop trusting the tracker.
def tracker(project: dict[str, Any], *,
            missing_function: str = "") -> dict[str, Any]:
    """All seven gates, always, with the current position and what it waits on.

    A labeled list rather than a decorative progress graphic. Gate status is
    carried by text as well as by position, and the waiting-on line is
    readable as text rather than inferred from an icon.
    """
    here = str(project.get("gate") or "")

    # A gate is passed when a forward passage *left* it, and it still sits
    # behind the project. This was keyed on the gate a passage arrived at, so
    # passing Identify stamped the date on Procure — where "here now" hid it —
    # and Identify read "not yet" for ever. No gate on any tracker ever showed
    # as passed. A later move back to an earlier gate takes the gates after it
    # out of "passed", because the project is no longer past them.
    passed: dict[str, str] = {}
    recorded_after: set[str] = set()
    for step in project.get("passages") or []:
        left, went = str(step.get("from") or ""), str(step.get("to") or "")
        if left and went and spine.before(left, went):
            passed[left] = str(step.get("at", ""))
            if step.get("happened"):
                recorded_after.add(left)
            else:
                recorded_after.discard(left)

    gates = []
    for g in spine.GATES:
        behind = bool(here) and spine.before(g.id, here)
        gates.append({
            "id": g.id,
            "name": g.name,
            "current": g.id == here,
            "passed_on": str(passed.get(g.id, ""))[:10] if behind else "",
            "recorded_after_the_fact": behind and g.id in recorded_after,
        })

    return {
        "gates": gates,
        "waiting_on": waiting_on(project, missing_function=missing_function),
        "version_pending": spine.version_pending(project.get("versions")),
        "version_pending_says": "The vendor says something is changing",
    }


def waiting_on(project: dict[str, Any], *,
               missing_function: str = "") -> str:
    """What is standing between this project and the next gate."""
    state = str(project.get("state") or "")
    if state == spine.WAITING_DECISION:
        return "Waiting on a decision"
    if state == spine.WAITING_PERSON:
        if missing_function:
            # Never shown as a defect. The gap that replaced the
            # consultation at Module One carries through instead.
            return (f"Waiting on {missing_function}, which you recorded as "
                    f"not present here")
        held = str(project.get("waiting_for") or "").strip()
        return f"Waiting on {held}" if held else "Waiting on somebody"
    if state == spine.PAUSED:
        return "Stopped where it stands"
    if state == spine.TURNED_DOWN:
        return "Turned down, and still on the list"
    if state == spine.RETIRED:
        return "Retired, and still on the list"
    return "Nothing is holding this up"


# ===========================================================================
# Writing — creation
# ===========================================================================

def start(name: str, actor: Any, *, asked_by: str = "",
          already_running: str = "") -> dict[str, Any]:
    """Open a project. Only the name is required."""
    name = str(name or "").strip()
    if not name:
        return {"ok": False,
                "error": "Give it a name — whatever the people who would use "
                         "it call it. You can change it later."}

    in_use = {"yes": spine.IN_USE_YES, "no": spine.IN_USE_NO}.get(
        str(already_running).strip().lower(), spine.IN_USE_UNKNOWN)

    with _LOCK:
        held = _read()
        ref = reference(set(held["projects"]), held.get("prefix", ""))
        project = blank_project(name, ref=ref, asked_by=asked_by,
                                in_use=in_use)
        held["projects"][ref] = project
        _write(held)

    _record("event.record_created", actor,
            {"ref": ref, "name": name, "in_use": in_use})
    return {"ok": True, "project": project}


# ===========================================================================
# Writing — who is accountable, and what the record points at
# ===========================================================================
#
# Until these existed, nothing could get past Identify. The spine refuses
# that passage unless a role is named against the project *and* Floor 7 is
# satisfied, and the record had fields for both and no way to write either —
# so the one rule Identify enforces could never be met from any screen.

#: Pointing at something, not asserting it. An answer that only says "yes"
#: is the assertion the floor exists to refuse.
_ASSERTIONS = {"yes", "y", "done", "ok", "okay", "true", "confirmed",
               "complete", "completed", "n/a", "na", "tbd", "-", "x"}


def _evidence_ok(points_at: str) -> str:
    """Empty when the pointer points at something; the refusal otherwise."""
    said = str(points_at or "").strip()
    if not said:
        return "Say what this points at — a procedure, a document, a decision."
    if said.lower().strip(".!") in _ASSERTIONS or len(said) < 6:
        return ("Point at something rather than confirming it — name the "
                "procedure, the document or the decision, and where it is.")
    return ""


def name_accountable(ref: str, role: str, actor: Any, *,
                     person: str = "") -> dict[str, Any]:
    """Name the role accountable for this project. Floor 7.

    A role, with a person beside it where one is given, so the record still
    makes sense after somebody moves on. Naming it is what satisfies the
    floor: the record then points at the role it names, which is the whole
    of "somebody's name is on it".
    """
    role = str(role or "").strip()
    if not role:
        return {"ok": False,
                "error": "Name the role accountable for this — a title, such "
                         "as General Manager. A person's name can go beside "
                         "it."}
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        project["accountable"] = role[:120]
        project["accountable_person"] = str(person or "").strip()[:120]
        satisfied = set(project.get("satisfied") or [])
        satisfied.add("floor.somebody_named")
        project["satisfied"] = sorted(satisfied)
        project.setdefault("evidence", {})["floor.somebody_named"] = {
            "points_at": f"The accountable role named on this record: {role}",
            "by": str(getattr(actor, "name", "") or ""),
            "at": _now(),
        }
        project["last_moved"] = _now()
        _write(held)
    _record("event.accountable_named", actor,
            {"ref": ref, "role": role, "person": person})
    return {"ok": True, "project": project}


def point_at(ref: str, floor: str, points_at: str,
             actor: Any) -> dict[str, Any]:
    """Satisfy a floor obligation by pointing at the thing that meets it.

    For the six that bind at Deploy above all: a person decides, people are
    told, it works for people with disabilities, it can be turned off, a name
    is on it, it can be explained. Each is met by pointing at the procedure,
    the document or the decision — "Procedure PR-4F2K9M, turning off the
    permit assistant" — never by a box that says yes.
    """
    if floor not in spine.BY_FLOOR:
        return {"ok": False, "error": f"{floor!r} is not a floor obligation."}
    refusal = _evidence_ok(points_at)
    if refusal:
        return {"ok": False, "error": refusal}
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        satisfied = set(project.get("satisfied") or [])
        satisfied.add(floor)
        project["satisfied"] = sorted(satisfied)
        project.setdefault("evidence", {})[floor] = {
            "points_at": str(points_at).strip()[:400],
            "by": str(getattr(actor, "name", "") or ""),
            "at": _now(),
        }
        _write(held)
    _record("event.floor_pointed_at", actor,
            {"ref": ref, "floor": floor, "points_at": str(points_at)[:200]})
    return {"ok": True, "project": project}


def name_goal(ref: str, goal: str, actor: Any) -> dict[str, Any]:
    """The goal this project serves, or none.

    The tie is written here and only here: a project points at a goal, and a
    goal never claims a project, so two surfaces cannot disagree about what a
    project is for. A project names at most one goal. Anybody may name one.
    """
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        was = project.get("goal", "")
        project["goal"] = str(goal or "").strip()
        _write(held)
    _record("event.goal_named", actor, {"ref": ref, "was": was,
                                        "now": project["goal"]})
    return {"ok": True, "project": project}


def set_level(ref: str, level: str, actor: Any, *,
              levels: list[str] | None = None) -> dict[str, Any]:
    """Set the scrutiny level, in the organization's own words.

    `levels` is their own list from the framework. Where they have one, only
    those names are accepted — a level this application made up would be a
    rule nobody agreed to. Where they have none yet, it says so rather than
    offering defaults.
    """
    level = str(level or "").strip()
    levels = [str(x).strip() for x in (levels or []) if str(x).strip()]
    if not levels:
        return {"ok": False,
                "error": "Your framework has not set its levels of scrutiny "
                         "yet. Set them there, and they will be offered "
                         "here."}
    if level not in levels:
        return {"ok": False,
                "error": f"Choose one of your own levels: "
                         f"{', '.join(levels)}."}
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        was = project.get("level", "")
        project["level"] = level
        project["last_moved"] = _now()
        # When the level was last looked at — setting it again to the same
        # level is a review too. Integrity 4.9 reads it.
        project["level_set_at"] = _now()
        _write(held)
    _record("event.level_set", actor, {"ref": ref, "was": was, "now": level})
    return {"ok": True, "project": project}


def passage_options(project: dict[str, Any]) -> dict[str, Any]:
    """What a passage screen needs: where it may go, and what binds here.

    Offered from the spine, so the screen shows only the moves the spine
    allows and names each gate by name. The obligations are the ones that
    bind at the gate the project is leaving, in both senses — the ones that
    refuse a passage and the ones that produce a finding and let it through.
    """
    gate = str(project.get("gate") or "")
    state = str(project.get("state") or "")
    satisfied = set(project.get("satisfied") or [])
    evidence = project.get("evidence") or {}
    moves = [{"id": g, "name": spine.BY_GATE[g].name,
              "back": spine.before(g, gate)}
             for g in spine.legal_moves(gate, state)]
    binds = []
    for floor, sense in spine.BINDS.get(gate, {}).items():
        binds.append({
            "id": floor,
            "says": spine.BY_FLOOR[floor].says,
            "refuses": sense == spine.SATISFIED,
            "satisfied": floor in satisfied,
            "points_at": (evidence.get(floor) or {}).get("points_at", ""),
        })
    return {"moves": moves, "binds": binds,
            "stopped": state in spine.STOPPED,
            "restart": (spine.START_AGAIN if state == spine.PAUSED
                        else spine.PICK_UP_AGAIN
                        if state == spine.TURNED_DOWN else "")}


# ===========================================================================
# Writing — the passage
# ===========================================================================

def _adopted_version() -> str:
    try:
        from app import versions
        live = versions.adopted()
        return f"Version {live.number}" if live else ""
    except Exception:                                         # noqa: BLE001
        return ""


def move(ref: str, to_gate: str, actor: Any, *, happened: str = "",
         conditions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Record a passage, or decline to and say why.

    The refusal reasons come from the spine verbatim. A surface must not
    compose its own: a user meeting two wordings for one refusal will assume
    they mean different things.

    A refused passage is not recorded. Nothing here writes an attempt.
    """
    held = _read()
    project = held["projects"].get(ref)
    if project is None:
        return {"ok": False, "error": f"No project {ref!r}."}

    from_gate = str(project.get("gate") or "")
    from_state = str(project.get("state") or "")
    answer = spine.may_pass(
        from_gate, to_gate, from_state,
        satisfied=set(project.get("satisfied") or []),
        has_owner=bool(str(project.get("accountable") or "").strip()))

    if not answer.ok:
        return {"ok": False, "error": answer.refused,
                "legal_moves": list(answer.refused_illegal),
                "unmet": list(spine.unmet(
                    from_gate, set(project.get("satisfied") or [])))}

    with _LOCK:
        held = _read()
        project = held["projects"][ref]
        moving_back = spine.before(to_gate, from_gate)
        project["gate"] = to_gate
        # Cleared is the handoff: the gate behind it is passed and nobody has
        # picked it up at the next one. In a small organisation it lasts a
        # second; in a large one it is where things sit for weeks.
        project["state"] = spine.CLEARED
        project["last_moved"] = _now()
        project.setdefault("passages", []).append({
            "from": from_gate, "to": to_gate, "at": _now(),
            "happened": happened,
            "by": str(getattr(actor, "name", "") or ""),
            "by_title": str(getattr(actor, "title", "") or ""),
            "hat": getattr(getattr(actor, "role", None), "value", ""),
            "conditions": conditions or [],
            # Which rules were in force on the day, resolved now and never
            # afterwards.
            "framework_version": _adopted_version(),
        })
        for condition in conditions or []:
            project.setdefault("conditions", []).append(
                {**condition, "attached_at": _now(), "closed": None})
        _write(held)

    _record("event.gate_moved_back" if moving_back else "event.gate_passed",
            actor, {"ref": ref, "from": from_gate, "to": to_gate},
            happened=happened)
    for condition in conditions or []:
        _record("event.condition_attached", actor,
                {"ref": ref, **condition})
    return {"ok": True, "project": project}


def set_state(ref: str, to_state: str, actor: Any, *,
              waiting_for: str = "", paused_by: str = "") -> dict[str, Any]:
    """The only place a project's state is written.

    `event.paused` and `event.restarted` exist because "stopped" and
    "started again" are the words a reader is looking for. Where either
    fires, `event.state_changed` does not fire alongside it.
    """
    if to_state not in spine.STATE_ORDER:
        return {"ok": False, "error": f"{to_state!r} is not a state."}

    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        was = str(project.get("state") or "")
        project["state"] = to_state
        project["waiting_for"] = waiting_for.strip()
        project["last_moved"] = _now()
        if to_state != spine.PAUSED:
            project.pop("paused_from", None)
        if to_state == spine.PAUSED:
            # A pause that cannot be reversed is a retirement, so what it was
            # doing before is kept — and who stopped it, by title, because
            # the framework names who may stop a tool alone.
            project["paused_from"] = was
            # Where the person said which of the named roles they hold (the
            # Stop it now control), that is what is kept.
            project["paused_by"] = str(paused_by or
                                       getattr(actor, "title", "") or
                                       getattr(actor, "name", "") or "")
        _write(held)

    if to_state == spine.PAUSED:
        _record("event.paused", actor, {"ref": ref, "was": was})
    elif was == spine.PAUSED:
        _record("event.restarted", actor, {"ref": ref, "now": to_state})
    else:
        _record("event.state_changed", actor,
                {"ref": ref, "was": was, "now": to_state})
    return {"ok": True, "project": project}


def start_again(ref: str, actor: Any) -> dict[str, Any]:
    """Reverses a pause to whatever state the project held before it."""
    project = one(ref)
    if project is None:
        return {"ok": False, "error": f"No project {ref!r}."}
    if project.get("state") != spine.PAUSED:
        return {"ok": False, "error": spine.REFUSE_NOT_AVAILABLE}
    return set_state(ref, str(project.get("paused_from")
                              or spine.BEING_WORKED), actor)


def pick_up_again(ref: str, actor: Any) -> dict[str, Any]:
    """Reopens a turned-down project.

    Nothing is ever deleted, and a proposal that comes back next year joins
    its own history rather than starting a second one.
    """
    project = one(ref)
    if project is None:
        return {"ok": False, "error": f"No project {ref!r}."}
    if project.get("state") != spine.TURNED_DOWN:
        return {"ok": False, "error": spine.REFUSE_NOT_AVAILABLE}
    return set_state(ref, spine.BEING_WORKED, actor)


# ===========================================================================
# The stat row
# ===========================================================================

def counters(rows: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Five counts, each with a plain-English label. Never a rate, never a
    grade, never a proportion, and never a color that reads as an alarm."""
    rows = all_projects() if rows is None else rows

    ahead = sum(1 for p in rows
                if spine.running_ahead(str(p.get("in_use") or ""),
                                       str(p.get("gate") or "")))
    unnamed = sum(1 for p in rows
                  if not str(p.get("accountable") or "").strip()
                  and not spine.before(str(p.get("gate") or ""),
                                       spine.IDENTIFY)
                  and str(p.get("gate")) != spine.GOVERN)
    never_tried = sum(1 for p in rows if _changed_and_never_tried(p))
    without_tool = sum(1 for p in rows if _ended_without_a_tool(p))

    return {
        "open": sum(1 for p in rows if p.get("state") not in (
            spine.TURNED_DOWN, spine.RETIRED)),
        "running_ahead": ahead,
        "nobody_named": unnamed,
        "changed_never_tried": never_tried,
        "ended_without_a_tool": without_tool,
        "says": {
            "running_ahead":
                "Most organizations start here. This counts what is already "
                "running, so you can work through it. It is not a list of "
                "mistakes.",
            "ended_without_a_tool":
                "These are the problems you solved without buying anything.",
        },
    }


def _changed_and_never_tried(project: dict[str, Any]) -> bool:
    for version in project.get("versions") or []:
        material = str(version.get("material", "")).strip().lower() == "yes"
        if material and version.get("live") and not version.get("tested"):
            return True
        if version.get("live") and not version.get("retired") and not \
                version.get("tested"):
            return True
    return False


def _ended_without_a_tool(project: dict[str, Any]) -> bool:
    """Closed at Identify, where the chosen step was anything other than an
    external vendor's tool — including doing nothing."""
    if project.get("state") != spine.TURNED_DOWN:
        return False
    if project.get("gate") != spine.IDENTIFY:
        return False
    return int(project.get("chosen_step") or 0) != 6


# ===========================================================================
# Findings
# ===========================================================================

def findings(project: dict[str, Any], *, framework: dict[str, Any] | None
             = None) -> list[dict[str, Any]]:
    """What this project records that contradicts what the organization
    decided. Never an external standard, another organization, or a
    benchmark — and never a declined recommendation."""
    framework = framework or {}
    found: list[dict[str, Any]] = []

    def raise_it(finding_id: str, says: str) -> None:
        found.append({"id": finding_id, "says": says})

    gate_now = str(project.get("gate") or "")
    past_identify = not spine.before(gate_now, spine.PROCURE)

    if (not str(project.get("accountable") or "").strip()
            and gate_now not in (spine.GOVERN,)):
        raise_it("finding.no_owner",
                 spine.BY_FINDING["finding.no_owner"].says)

    if spine.running_ahead(str(project.get("in_use") or ""), gate_now):
        raise_it("finding.running_ahead",
                 spine.BY_FINDING["finding.running_ahead"].says)

    said = " ".join(str(v) for v in (project.get("problem") or {}).values()
                    if isinstance(v, str)).lower()
    # Never fires on the parked-idea block: parking the solution somebody
    # walked in with is the point of that block.
    parked = str((project.get("problem") or {}).get("parked") or "").lower()
    for word in SOLUTION_WORDS:
        if word in said and word not in parked:
            raise_it("finding.pj.problem_is_a_solution",
                     "This describes a solution rather than a problem. What "
                     "goes wrong, where, and how often?")
            break

    if past_identify:
        missing = [s.number for s in spine.HIERARCHY
                   if not str((project.get("hierarchy") or {}).get(
                       str(s.number), {}).get("verdict") or "").strip()]
        if missing:
            chosen = int(project.get("chosen_step") or 0)
            above = ", ".join(f"step {n}" for n in missing if n < chosen) \
                or "the steps above it"
            raise_it("finding.pj.hierarchy_skipped",
                     f"You went to step {chosen} without recording an answer "
                     f"on {above}.")
        if not str(project.get("level") or "").strip():
            raise_it("finding.pj.level_unset",
                     "This moved past Identify with no level set. Everything "
                     "later reads off that level.")

    if (not spine.before(gate_now, spine.TEST)
            and not str(project.get("baseline") or "").strip()):
        raise_it("finding.no_baseline",
                 spine.BY_FINDING["finding.no_baseline"].says)

    for condition in project.get("conditions") or []:
        if condition.get("closed"):
            continue
        by = str(condition.get("by") or "")
        if by and by < clock.today_str():
            raise_it("finding.condition_overdue",
                     f"A condition on this is past its date: "
                     f"{condition.get('what', '')}, owned by "
                     f"{condition.get('owner', '')}.")

    for gap in project.get("gaps") or []:
        if not str(gap.get("owner") or "").strip():
            raise_it("finding.gap_no_owner",
                     spine.BY_FINDING["finding.gap_no_owner"].says)

    if _changed_and_never_tried(project):
        raise_it("finding.version_untracked",
                 spine.BY_FINDING["finding.version_untracked"].says)

    if (project.get("state") == spine.RETIRED
            and project.get("in_use") == spine.IN_USE_YES):
        raise_it("finding.pj.retired_still_in_use",
                 "This is recorded as retired and still recorded as in use. "
                 "One of the two is out of date.")

    return found


#: One finding is deliberately absent, and this is where somebody about to
#: add it reads why. Declining is a complete answer, and this surface records
#: it without comment.
NO_FINDING_FOR = ("a recommendation was declined",)


# ===========================================================================
# §13 · Framework read-back, and every finding a project can raise
# ===========================================================================

_LIST_DAYS = {"quarterly": 92, "biannual": 183, "annual": 366}


def framework_inputs(answers: dict[str, Any] | None) -> dict[str, Any]:
    from app import module_one as m
    answers = dict(answers or {})

    def value(key: str) -> Any:
        return m.value_of(answers, key)[0]

    def listed(key: str) -> list[str]:
        got = value(key) or []
        return [g for g in (got if isinstance(got, list) else [got])
                if g and g != m.UNKNOWN]

    def label_of(key: str, raw: Any) -> str:
        q = m.by_key(key)
        for o in (q.options if q else []) or []:
            if o.value == raw:
                return m._fill(o.label, answers)
        return str(raw or "")

    optional = listed("floor.optional")
    factors = value("risk.factors")
    factors = factors if isinstance(factors, dict) else {}
    q_factors = m.by_key("risk.factors")
    factor_rows = [(r.value, r.label) for r in (q_factors.rows if q_factors
                                               else [])]
    stoppers = value("bad.stopper") or []
    notice = value("watch.notice")
    out = {
        "levels": [n for _, n in m.level_names(answers)],
        "mission_tie": "mission" in optional,
        "roi": "roi" in optional,
        "single_factor": value("risk.worst") == "yes",
        "factors": factor_rows,
        "factor_weights": {k: factors.get(k, "") for k, _ in factor_rows},
        "severe": [label for key, label in factor_rows
                   if factors.get(key) == "major"],
        "severe_keys": [key for key, _ in factor_rows
                        if factors.get(key) == "major"],
        "borderline_reviewed": value("scope.review") == "yes",
        "arbiter": str(value("scope.arbiter") or "").strip(),
        "scope_covered": [label_of("scope.covered", v)
                          for v in listed("scope.covered")],
        "scope_excluded": [label_of("scope.excluded", v)
                           for v in listed("scope.excluded")],
        "no_finalising": value("floor.ai_finalises") == "none",
        "list_records_data": "data" in listed("floor.list_fields"),
        "list_cadence": value("floor.list_checked") or "",
        "list_days": _LIST_DAYS.get(value("floor.list_checked")),
        "list_words": _lower(label_of("floor.list_checked",
                                      value("floor.list_checked"))),
        "staging_required": "staging" in listed("proc.terms"),
        "returned_required": "returned" in listed("floor.data_terms"),
        "notice_days": int(notice) if str(notice).isdigit() else None,
        "notice_words": label_of("watch.notice", notice) if notice else "",
        "retire_words": str(value("watch.retire") or "").strip(),
        "delegation": listed("who.without"),
        "stoppers": [str(r.get("role") or "").strip() for r in stoppers
                     if isinstance(r, dict) and str(r.get("role") or "").strip()],
        "triggers": [label_of("watch.triggers", t)
                     for t in listed("watch.triggers")],
        "coop": {"regularly": "regularly", "sometimes": "sometimes",
                 "no": "never"}.get(value("proc.cooperative"), ""),
        "reuse": value("proc.reuse") == "yes",
        "delegated": value("org.delegated") == "yes",
        "can_build": (value("org.functions") or {}).get("it") not in
        (None, "", "none") if isinstance(value("org.functions"), dict)
        else False,
        "baseline_asked": value("watch.baseline") in ("always", "sometimes"),
    }
    return out


def _lower(text: str) -> str:
    text = str(text or "")
    return text[:1].lower() + text[1:] if text else text


def findings_all(project: dict[str, Any], *, inputs: dict[str, Any],
                 holdings: dict[str, dict[str, Any]] | None = None,
                 checks_done: list[dict[str, Any]] | None = None,
                 list_checked: str = "", today: str = ""
                 ) -> list[dict[str, Any]]:
    """Every finding §4 defines that the record can support, on top of the
    shared ones. Each one quotes the organization's own answer; none reads
    an outside standard, and none is raised for a declined recommendation."""
    found = findings(project)
    today = today or clock.today_str()
    holdings = holdings or {}
    gate = str(project.get("gate") or "")
    state = str(project.get("state") or "")
    levels = inputs.get("levels") or []
    level = str(project.get("level") or "")
    tool = project.get("tool") or {}
    sunset = project.get("sunset") or {}
    name = project.get("name") or project.get("ref") or ""

    def add(fid: str, says: str) -> None:
        found.append({"id": fid, "says": says})

    past_identify = bool(gate) and not spine.before(gate, spine.PROCURE)
    past_procure = bool(gate) and not spine.before(gate, spine.TEST)

    # 4.4 — their single-factor rule, a severe factor answered yes here, and
    # the level below their top.
    factors = tool.get("factors") or {}
    if inputs.get("single_factor") and levels and level and \
            level != levels[-1]:
        for key in inputs.get("severe_keys") or []:
            if str(factors.get(key) or "").lower() == "yes":
                label = dict(inputs.get("factors") or []).get(key, key)
                add("finding.pj.level_below_own_rule",
                    f"You said one severe factor lifts the whole thing. "
                    f"{label} is marked here, and this sits at {level}.")
                break
    # 4.6 — a delegated programme, marked severe, and the level not lifted.
    if "delegated" in (inputs.get("severe_keys") or []) and \
            str(factors.get("delegated") or "").lower() == "yes" and \
            levels and level and level != levels[-1]:
        add("finding.pj.delegated_not_lifted",
            f"You said a program another government delegated to you is a "
            f"major concern. This touches one and sits at {level}.")
    # 4.5 — a borderline call they said gets looked at afterward.
    if tool.get("in_scope") == "Borderline" and \
            inputs.get("borderline_reviewed") and \
            not str(tool.get("borderline_reviewed") or "").lower() == "yes":
        add("finding.pj.borderline_unreviewed",
            "You said a borderline call gets looked at afterward. This was "
            "called borderline and nothing records a look.")
    # 4.7 — the list records what information each tool touches.
    if inputs.get("list_records_data") and past_identify and \
            not (project.get("holdings") or tool.get("holdings")) and \
            not tool.get("holdings_unsure"):
        add("finding.pj.nothing_touched",
            "You said the list records what information each tool touches. "
            "This one has nothing against it, and nothing recorded as unknown "
            "either.")
    # 4.8 — no decision finalised by a tool alone.
    if inputs.get("no_finalising") and \
            str(tool.get("finalises") or "").lower() == "yes":
        add("finding.pj.finalises",
            "You said no decision gets finalized by a tool on its own. This "
            "one is recorded as doing that.")
    # 4.10 — every tool must serve a goal.
    if inputs.get("mission_tie") and past_identify and not project.get("goal"):
        add("finding.pj.no_vision_tie",
            "You said every tool has to serve one of your goals. This one "
            "does not name one.")
    # 4.11 — the measurement comes from a holding nothing can reach.
    for hid in ((project.get("grounds") or {}).get("holdings") or []):
        h = holdings.get(hid) or {}
        reach = str(h.get("reachable") or h.get("reachable_label") or "")
        if reach in ("no", "unknown", "Nothing can reach it",
                     "We do not know where it is"):
            add("finding.pj.baseline_unreachable",
                f"The measurement for this comes from "
                f"{h.get('name') or hid}, which is recorded as "
                f"{h.get('reachable_label') or reach}.")
    # 4.12 — a return figure required, and no before measurement.
    if inputs.get("roi") and past_procure and \
            not str(project.get("baseline") or "").strip() and \
            not any("baseline" in str(g.get("field", ""))
                    for g in project.get("gaps") or []):
        add("finding.pj.roi_no_baseline",
            "You require a return on investment figure for tools you buy. "
            "There is no before measurement to work it out against.")
    # 4.13 — a passage approved in the User hat, outside their delegation.
    delegation = inputs.get("delegation") or []
    for p in project.get("passages") or []:
        if p.get("hat") == "operator" and not spine.before(
                str(p.get("to") or ""), str(p.get("from") or "")):
            inside = "lowest_risk" in delegation and levels and \
                level == levels[0]
            if not delegation or "nothing" in delegation or \
                    (delegation == ["lowest_risk"] and not inside):
                add("finding.pj.outside_delegation",
                    "This passage was approved in the User hat, and your "
                    "delegation does not cover it.")
                break
    # 4.14 — stopped by somebody they did not name as able to stop a tool.
    stoppers = [s.lower() for s in inputs.get("stoppers") or []]
    if state == spine.PAUSED and stoppers and \
            str(project.get("paused_by") or "").lower() not in stoppers:
        add("finding.pj.stopped_by_unnamed",
            f"You named {', '.join(inputs['stoppers'])} as able to stop a "
            f"tool without waiting for a meeting. This was stopped by "
            f"{project.get('paused_by') or 'somebody else'}, who is not on "
            f"that list. It stays stopped.")
    # 4.15 — a date somebody set for the next gate has passed.
    target = str(project.get("next_gate_by") or "")[:10]
    if target and target < today and state not in spine.STOPPED:
        add("finding.pj.past_their_date",
            f"Somebody set {target} as when this would reach the next gate. "
            f"That date has passed.")
    # 4.16 — back to Test, and passed again with nothing dated after.
    passages = project.get("passages") or []
    back = [p for p in passages if p.get("to") == spine.TEST and
            spine.before(spine.TEST, str(p.get("from") or ""))]
    if back:
        since = str(back[-1].get("at") or "")[:10]
        passed_again = any(p.get("from") == spine.TEST and
                           str(p.get("at") or "")[:10] >= since
                           for p in passages)
        evidence = any(str(c.get("at") or "") >= since for c in
                       (checks_done or [])
                       if c.get("project") == project.get("ref"))
        if passed_again and not evidence:
            add("finding.pj.sent_back_not_retested",
                f"This came back to Test on {since} and passed again with "
                f"nothing recorded after that date.")
    # 4.17 — a gate passed with no adopted framework behind it.
    if any(not p.get("framework_version") for p in passages
           if not spine.before(str(p.get("to") or ""),
                               str(p.get("from") or ""))):
        add("finding.pj.no_framework_version",
            "This passed a gate with no adopted framework behind it. Nothing "
            "here is wrong; there is just nothing yet that says what the "
            "rules were.")
    # 4.18 — the list checked on their own period.
    days = inputs.get("list_days")
    if days and not project.get("gaius"):
        pass  # raised once for the list, in `list_findings`
    # 4.19 — a version straight into production where they require staging.
    for v in project.get("versions") or []:
        if v.get("live") and v.get("staged") == "No" and \
                inputs.get("staging_required"):
            add("finding.pj.version_unstaged",
                "You require a testing environment in every agreement. This "
                "update went straight into production.")
            break
    # 4.20 — a version live with nothing tried.
    for v in project.get("versions") or []:
        if v.get("live") and not v.get("tested") and not \
                v.get("tested_reason"):
            add("finding.pj.version_untracked",
                "The vendor changed this and nothing here records what "
                "changed or whether it was tried.")
            break
    # 4E — at Sunset.
    if sunset.get("closed_on"):
        if not str(sunset.get("records") or "").strip():
            add("finding.pj.retired_no_disposition",
                f"You said records and information go to "
                f"{inputs.get('retire_words') or 'where your framework says'}"
                f". This was retired with nothing recorded about where the "
                f"records went.")
        elif not str(sunset.get("records_confirmed_by") or "").strip():
            add("finding.pj.records_unconfirmed",
                "This was turned off and nobody has confirmed where its "
                "records went.")
        if not str(sunset.get("replaced_by") or "").strip():
            add("finding.pj.retired_no_replacement",
                "This was retired and nothing here says how the work gets "
                "done now.")
        if not str(sunset.get("final_measurement") or "").strip():
            add("finding.pj.final_measurement_missing",
                "This was retired without a last look at whether it did what "
                "it was bought to do.")
        notice_days = inputs.get("notice_days")
        if notice_days:
            notice_on = str(sunset.get("notice_on") or "")[:10]
            off = str(sunset.get("closed_on") or "")[:10]
            if not notice_on:
                add("finding.pj.retired_short_notice",
                    f"You said {inputs.get('notice_words')} notice before a "
                    f"tool is turned off. This one records none.")
            else:
                from datetime import date
                try:
                    gap = (date.fromisoformat(off) -
                           date.fromisoformat(notice_on)).days
                except ValueError:
                    gap = notice_days
                if gap < notice_days:
                    add("finding.pj.retired_short_notice",
                        f"You said {inputs.get('notice_words')} notice. "
                        f"Notice was given on {notice_on} and it was turned "
                        f"off {gap} days later.")
        if inputs.get("returned_required") and project.get("supplier") and \
                not sunset.get("information_returned_on"):
            add("finding.pj.data_terms_absent_at_sunset",
                "You require that your information comes back and is deleted "
                "when you leave. Nothing here confirms that happened.")
        if str(factors.get("delegated") or "").lower() == "yes" and \
                sunset.get("delegating_told") not in DELEGATING_TOLD[:2]:
            add("finding.pj.delegated_not_determined",
                "This touches a program another government delegated to "
                "you. Nothing here records a decision about whether they had "
                "to be told, either way.")
    # Drawn once per finding id per project.
    seen, unique = set(), []
    for f in found:
        key = (f["id"], f["says"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def list_findings(rows: list[dict[str, Any]], *, inputs: dict[str, Any],
                  list_checked: str = "", today: str = ""
                  ) -> list[dict[str, Any]]:
    """4.18 · the list checked on their own period, raised once for the
    list — or, where they said as updated, per project that changed since."""
    today = today or clock.today_str()
    out: list[dict[str, Any]] = []
    days = inputs.get("list_days")
    if days:
        from datetime import date
        stale = True
        if list_checked:
            try:
                stale = (date.fromisoformat(today) -
                         date.fromisoformat(list_checked)).days > days
            except ValueError:
                stale = True
        if stale and rows:
            out.append({"id": "finding.pj.list_unchecked", "ref": "",
                        "says": (f"You said the list is checked "
                                 f"{inputs.get('list_words')}. The last check "
                                 f"was {list_checked}." if list_checked else
                                 f"You said the list is checked "
                                 f"{inputs.get('list_words')}. There has "
                                 f"never been a check.")})
    elif inputs.get("list_cadence") == "asupdated":
        for p in rows:
            changed = str(p.get("last_written") or p.get("last_moved") or "")
            if changed[:10] > (list_checked or ""):
                out.append({"id": "finding.pj.list_unchecked",
                            "ref": p.get("ref"),
                            "says": f"You said the list is checked as it is "
                                    f"updated. This changed on {changed[:10]} "
                                    f"and has not been confirmed since."})
    return out


# ===========================================================================
# §8 – §10 · Writing up a project, section by section
# ===========================================================================

#: The shared verdict vocabulary at 9.0, for every solution category and
#: every hierarchy step. One control, one vocabulary.
TAKEN = "Taken"
INADEQUATE = "Inadequate"
NOT_AVAILABLE = "Not available here"
NOT_ANSWERED = "Not answered"
VERDICTS = (TAKEN, INADEQUATE, NOT_AVAILABLE, NOT_ANSWERED)

#: 9A · the nine categories, in the order the interface asks them. It never
#: opens this list with a technology option.
CATEGORIES: tuple[tuple[str, str, str], ...] = (
    ("process", "Change the process",
     "Reorder steps, remove a step, change who does what, move a check "
     "earlier or later, stop doing something that no longer earns its keep."),
    ("rule", "Change a rule or requirement",
     "What is required, what is allowed, what is optional, what the deadline "
     "is, what triggers a review."),
    ("standardise", "Standardize what comes in",
     "Forms, templates, required fields, defined submission formats, naming "
     "conventions, a specified document structure. This is the answer more "
     "often than people expect, and it is usually the cheapest durable fix."),
    ("train", "Train",
     "Sometimes people do not know how, or do not know a capability exists, "
     "or learned a workaround that outlived the problem it worked around."),
    ("data", "Fix the underlying data",
     "Where the data is incomplete, inconsistent or wrong, most other fixes "
     "will underperform and some will fail outright."),
    ("staff", "Add staff or reallocate people",
     "Where there is more work than there are people, no process change or "
     "tool resolves that."),
    ("simple_tech", "Add technology that is not complicated",
     "A form, a workflow rule, a required field, a report, a dashboard, "
     "connecting two systems that already exist."),
    ("involved_tech", "Add technology that is more involved",
     "Systems that interpret language or documents, that handle high volume, "
     "or that apply rules at scale. Worth being skeptical of where the data is "
     "inconsistent, the volume is low, or the work needs professional "
     "judgment."),
    ("nothing", "Do nothing",
     "Sometimes the cost of fixing exceeds the cost of living with it, or "
     "something already in motion will resolve it."),
)
BY_CATEGORY = {k: (name, says) for k, name, says in CATEGORIES}
#: The categories whose Taken verdict can close the project at Identify.
CLOSES_WITHOUT_TOOL = ("process", "rule", "standardise", "train", "data",
                       "staff", "nothing")
TECH_CATEGORIES = ("simple_tech", "involved_tech")

#: 8.16 · the walkthrough's statement about its own reasoning — the one place
#: on this surface where the vocabulary is the application's own.
CONFIDENCE = ("Confident", "Fairly confident",
              "Not confident — this is the best guess available",
              "Not established")

#: The fields each section may hold. Anything else sent is dropped.
SECTION_FIELDS: dict[str, tuple[str, ...]] = {
    # §8 · the nine questions, the parked idea, and the cause.
    "problem": ("happening", "affects", "affects_people", "affects_how_often",
                "costs", "costs_not_counted", "known", "assumed", "tried",
                "who_else", "who_else_units", "if_nothing", "how_known",
                "parked", "idea", "idea_users", "idea_holdings",
                "idea_company", "idea_company_name", "idea_cost", "cause",
                "confidence",
                # Data 5.1 and 5.2 · what information would resolve this,
                # and which part of the organisation is asking.
                "info_for", "unit"),
    # 9C · sequence and pressure-test.
    "pressure": ("first_regardless", "cheapest", "what_breaks",
                 "what_breaks_unanswered", "rebuild"),
    # 9E · what the record carries when the answer is a tool.
    "tool": ("what_it_is", "in_scope", "borderline_by", "borderline_reviewed",
             "factors", "holdings", "holdings_unsure", "found_on", "used_by",
             "finalises", "advances", "needs_help",
             # Whether the public uses it or sees what it produces —
             # Integrity 4.7 reads "yes", Process 3.4 reads "yes" or "output".
             "public_facing",
             # The words the public sees: a wording procedure on Process, or
             # this project's own. Process 3.7 reads which.
             "disclosure_ref", "disclosure_text"),
    # 10A · the business case.
    "business_case": ("expect_back", "money_from", "money_note", "wrote_it",
                      # Registry 4.3 · why a second thing was bought where
                      # another unit already has one. Never required.
                      "why_buy_new"),
    # 10B · the baseline.
    "baseline": ("today", "rows", "sharpened"),
    # 10C · the data grounds.
    "grounds": ("holdings", "who_measures", "how_often"),
}

_SECTION_KEY = {"baseline": "baseline_detail", "business_case": "case_detail"}

MONEY_FROM = ("Existing budget", "A grant", "Fees",
              "Reallocating something we already fund",
              "Shared with another government", "Not identified yet")
HOW_OFTEN = ("Live", "Daily", "Weekly", "Monthly or less often",
             "Only by asking somebody", "We are not sure")
IN_SCOPE = ("Yes", "No", "Borderline", "We are not sure")


def save_section(ref: str, section: str, fields: dict[str, Any], actor: Any
                 ) -> dict[str, Any]:
    """Write one section of the write-up. Every answer is optional here —
    the first half of this surface exists to be answered slowly, by somebody
    who does not yet know the answers."""
    allowed = SECTION_FIELDS.get(section)
    if allowed is None:
        return {"ok": False, "error": "That is not a section of a project."}
    clean = {k: v for k, v in (fields or {}).items() if k in allowed}
    # Two sections are stored beside a plain field of the same name that
    # other surfaces read as text — the baseline and the business case — so
    # their detail lives under its own key and the plain field stays text.
    key = _SECTION_KEY.get(section, section)
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        store = project.get(key)
        if not isinstance(store, dict):
            store = {}
        store.update(clean)
        project[key] = store
        if section == "business_case":
            project["business_case"] = str(store.get("expect_back") or
                                           store.get("money_note") or
                                           "written").strip()
        if section == "tool":
            if "holdings" in clean:
                project["holdings"] = list(clean["holdings"] or [])
        if section == "grounds":
            names = ", ".join(str(h) for h in store.get("holdings") or [])
            project["data_grounds"] = names
        project["last_written"] = _now()
        _write(held)
    # The baseline other surfaces read is the text of 10.10.
    if section == "baseline" and "today" in clean:
        _set_field(ref, "baseline", str(clean.get("today") or "").strip())
    _record("event.field_changed", actor,
            {"ref": ref, "field": section, "fields": sorted(clean)})
    return {"ok": True, "project": one(ref)}


def _set_field(ref: str, key: str, value: Any) -> None:
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is not None:
            project[key] = value
            _write(held)


def save_verdicts(ref: str, *, categories: dict[str, dict] | None = None,
                  steps: dict[str, dict] | None = None, actor: Any
                  ) -> dict[str, Any]:
    """9A and 9B · a verdict and one line of reasoning on each. Skipping one
    without saying anything is the failure; saying it does not apply is a
    complete answer."""
    def clean(entry: dict[str, Any]) -> dict[str, str]:
        verdict = str((entry or {}).get("verdict") or "")
        return {"verdict": verdict if verdict in VERDICTS else "",
                "why": str((entry or {}).get("why") or "").strip()[:500],
                "candidate": str((entry or {}).get("candidate") or "")
                .strip()[:300]}
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        if categories:
            store = project.setdefault("solution", {})
            for key, entry in categories.items():
                if key in BY_CATEGORY:
                    store[key] = clean(entry)
        if steps:
            store = project.setdefault("hierarchy", {})
            for key, entry in steps.items():
                if str(key) in {str(s.number) for s in spine.HIERARCHY}:
                    store[str(key)] = clean(entry)
            taken = [int(k) for k, v in store.items()
                     if v.get("verdict") == TAKEN]
            project["chosen_step"] = min(taken) if taken else 0
        _write(held)
    _record("event.field_changed", actor, {"ref": ref, "field": "verdicts"})
    return {"ok": True, "project": one(ref)}


#: 9A · on the close screen, in these words.
CLOSED_WITHOUT_TOOL = ("This is a complete outcome. What you learned here is "
                       "on the record and the next person with this problem "
                       "will find it.")


def close_without_tool(ref: str, category: str, actor: Any, *, why: str = ""
                       ) -> dict[str, Any]:
    """Where the answer at Identify was not a tool. The project closes at
    Turned down with the chosen category and its reasoning, stays on the list
    for ever, and counts under Ended without a tool."""
    if category not in CLOSES_WITHOUT_TOOL:
        return {"ok": False, "error": "That category does not close a "
                                      "project without a tool."}
    project = one(ref)
    if project is None:
        return {"ok": False, "error": f"No project {ref!r}."}
    if project.get("gate") != spine.IDENTIFY:
        return {"ok": False, "error": "A project closes without a tool at "
                                      "Identify."}
    with _LOCK:
        held = _read()
        p = held["projects"][ref]
        p["ended_category"] = category
        p["ended_why"] = str(why or "").strip()[:1000]
        p["chosen_step"] = 0
        _write(held)
    out = set_state(ref, spine.TURNED_DOWN, actor)
    if out.get("ok"):
        out["says"] = CLOSED_WITHOUT_TOOL
    return out


def summary(project: dict[str, Any]) -> dict[str, Any]:
    """9D · what Identify produces, assembled from what was written and
    nothing else. Nothing here is invented: where an answer is missing the
    summary says so rather than filling it in."""
    problem = project.get("problem") or {}
    solution = project.get("solution") or {}
    steps = project.get("hierarchy") or {}
    pressure = project.get("pressure") or {}
    none = "Not written yet."
    considered = []
    for key, name, _ in CATEGORIES:
        v = solution.get(key) or {}
        considered.append(f"{name}: {v.get('verdict') or 'no verdict yet'}"
                          + (f" — {v['why']}" if v.get("why") else ""))
    for s in spine.HIERARCHY:
        v = steps.get(str(s.number)) or {}
        considered.append(f"Step {s.number}, {s.name}: "
                          f"{v.get('verdict') or 'no verdict yet'}"
                          + (f" — {v['why']}" if v.get("why") else ""))
    sequence = [x for x in (pressure.get("first_regardless"),
                            pressure.get("cheapest")) if x]
    return {
        "problem_statement": problem.get("happening") or none,
        "known": problem.get("known") or none,
        "assumed": problem.get("assumed") or none,
        "cause": (f"{problem.get('cause')} ({problem.get('confidence')})"
                  if problem.get("cause") else
                  f"Not established" if problem.get("confidence") ==
                  "Not established" else none),
        "options_considered": considered,
        "sequence": sequence or [none],
        "what_to_measure": problem.get("how_known") or none,
        "parking_lot": problem.get("parked") or "",
    }


# ===========================================================================
# §11 · Versions, and the update loop
# ===========================================================================

MATERIAL = ("Yes", "No", "Not yet decided")
STAGED = ("Yes", "No", "We have no testing environment")


def open_version(ref: str, actor: Any, *, what: str, told_on: str = "",
                 not_told: bool = False) -> dict[str, Any]:
    """11B · Anything the vendor tells you about opens a version record.
    Their own words, kept verbatim — a summary written today is the thing
    somebody disputes in two years."""
    what = str(what or "").strip()
    if not what:
        return {"ok": False, "error": "Paste what the vendor said changed."}
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        vref = "V-" + "".join(secrets.choice(ALPHABET) for _ in range(5))
        version = {"ref": vref, "opened": clock.today_str(),
                   "told_on": "" if not_told else str(told_on or "")[:10],
                   "not_told": bool(not_told), "what": what[:6000],
                   "material": "Not yet decided", "staged": "",
                   "tested": "", "tested_reason": "", "live": "",
                   "retired": ""}
        project.setdefault("versions", []).append(version)
        project["version_pending"] = True
        _write(held)
    _record("event.version_opened", actor, {"ref": ref, "version": vref,
                                            "what": what[:300]})
    return {"ok": True, "version": version}


def update_version(ref: str, vref: str, actor: Any, **fields: Any
                   ) -> dict[str, Any]:
    """Judge it, say where it was tried, and record it going live. On going
    live the version that was running retires on the same date."""
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        versions = project.get("versions") or []
        version = next((v for v in versions if v.get("ref") == vref), None)
        if version is None:
            return {"ok": False, "error": "No such version."}
        events = []
        if "material" in fields and fields["material"] in MATERIAL:
            version["material"] = fields["material"]
            events.append(("event.version_judged",
                           {"judgement": {"Yes": "This change was called "
                                          "material", "No": "This change was "
                                          "called not material"}.get(
                               fields["material"], "Nobody has decided yet "
                                                   "whether this change is "
                                                   "material")}))
        if "staged" in fields and fields["staged"] in STAGED:
            version["staged"] = fields["staged"]
        if "tested" in fields:
            version["tested"] = str(fields["tested"] or "")[:60]
        if "tested_reason" in fields:
            version["tested_reason"] = str(fields["tested_reason"] or "")[:500]
        if fields.get("live") and not version.get("live"):
            live = str(fields["live"])[:10]
            version["live"] = live
            for other in versions:
                if other is not version and other.get("live") and \
                        not other.get("retired"):
                    other["retired"] = live
                    events.append(("event.version_retired",
                                   {"version": other.get("ref")}))
            events.append(("event.version_live", {"version": vref}))
        project["version_pending"] = any(
            not v.get("live") for v in versions)
        _write(held)
    for action, detail in events:
        _record(action, actor, {"ref": ref, **detail})
    return {"ok": True, "version": version}


# ===========================================================================
# §12 · The tool sunset record
# ===========================================================================

REPLACED_BY = ("The manual way", "Another tool — named",
               "Nothing; we stop doing this")
DELEGATING_TOLD = ("Required", "Not required", "Pending")
SUNSET_FIELDS = ("trigger", "decided_by", "decided_on", "notice_on",
                 "notice_to", "short_notice_why", "replaced_by",
                 "replaced_by_project", "records", "records_confirmed_by",
                 "information_returned_by", "information_returned_on",
                 "information_not_confirmed", "delegating_told",
                 "final_measurement", "explain_later")


def save_sunset(ref: str, actor: Any, **fields: Any) -> dict[str, Any]:
    """12A · The tool sunset record, written as it is known. A tool sunset
    is a judgment against the claim that justified the tool, and it is
    written here; Vision reads it."""
    clean = {k: str(v).strip()[:4000] if isinstance(v, str) else v
             for k, v in fields.items() if k in SUNSET_FIELDS}
    with _LOCK:
        held = _read()
        project = held["projects"].get(ref)
        if project is None:
            return {"ok": False, "error": f"No project {ref!r}."}
        sunset = project.setdefault("sunset", {})
        sunset.update(clean)
        _write(held)
    _record("event.field_changed", actor, {"ref": ref, "field": "sunset",
                                          "fields": sorted(clean)})
    return {"ok": True, "project": one(ref)}


def close_sunset(ref: str, actor: Any) -> dict[str, Any]:
    """Close the retirement record: pass Sunset, then move to Retired. The
    project stays on the list with its whole history and is never
    deleted."""
    project = one(ref)
    if project is None:
        return {"ok": False, "error": f"No project {ref!r}."}
    if project.get("gate") != spine.SUNSET:
        moved = move(ref, spine.SUNSET, actor)
        if not moved.get("ok"):
            return moved
    with _LOCK:
        held = _read()
        p = held["projects"][ref]
        p.setdefault("sunset", {})["closed_on"] = clock.today_str()
        p["retired_on"] = clock.today_str()
        _write(held)
    return set_state(ref, spine.RETIRED, actor)


# ===========================================================================
# 4.18 · The list was checked
# ===========================================================================

def list_checked(actor: Any) -> dict[str, Any]:
    """Somebody confirmed the list is accurate today."""
    with _LOCK:
        held = _read()
        held["list_checked"] = clock.today_str()
        _write(held)
    _record("event.field_changed", actor, {"field": "list_checked"})
    return {"ok": True, "on": held["list_checked"]}


def last_list_check() -> str:
    return str(_read().get("list_checked") or "")


# ===========================================================================
# §14 · GAIUS as project number one
# ===========================================================================

GAIUS_NAME = "GAIUS — the walkthrough that works the problem with you"

#: 14 · the Floor 6 line, in the words the spine gives it. The spine leaves
#: it pending a decision; it renders only once that decision is recorded.
GAIUS_DATA_LINE = (
    "Your walkthrough is your data. It lives in your account. We do not want "
    "it and we do not take it. If you ever decide to share something with "
    "us, that is your decision, and we will record that you made it.")

GAIUS_EVIDENCE = {
    "floor.person_decides":
        "The walkthrough proposes, summarizes and argues; it approves no "
        "passage, sets no scrutiny level and closes no gap. Every write it "
        "makes carries the hat of the person it was working with.",
    "floor.tell_people":
        "A disclosure appears wherever the walkthrough runs, stating that a "
        "tool is doing the asking.",
    "floor.accessibility":
        "It meets WCAG 2.1 AA, with a text-only route through all nine "
        "questions as a form.",
    "floor.turn_it_off":
        "It can be turned off; the fallback is the nine questions as a "
        "form, which asks worse follow-up questions.",
    "floor.explain_plainly":
        "A tool that asks what is going wrong, where and how often, and "
        "writes down the answers before anybody talks about what to buy.",
}


def seed_gaius(actor: Any) -> dict[str, Any]:
    """Seeded once, on the day the framework is adopted, so the first record
    anybody sees shows what a complete one looks like. It does not mark
    itself approved: its passages are the organization's to record, and
    until they are it shows as running ahead of its gates like everything
    else. It is never deleted."""
    if any(p.get("gaius") for p in all_projects()):
        return {"ok": True, "seeded": False}
    made = start(GAIUS_NAME, actor, already_running="yes")
    if not made.get("ok"):
        return made
    ref = made["project"]["ref"]
    with _LOCK:
        held = _read()
        p = held["projects"][ref]
        p["gaius"] = True
        p["problem"] = {"happening": "People need to work out what is going "
                        "wrong before anybody decides what to buy."}
        p["tool"] = {"what_it_is": "A walkthrough that asks the nine "
                     "questions and writes down the answers.",
                     "in_scope": "Yes"}
        evidence = p.setdefault("evidence", {})
        for floor, says in GAIUS_EVIDENCE.items():
            evidence[floor] = {"points_at": says, "at": _now()}
        p["satisfied"] = sorted(set(p.get("satisfied") or []) |
                                set(GAIUS_EVIDENCE))
        # Floor 7 — a person at the supplier, by name. Left for the
        # organisation to confirm: no name is pre-loaded into anybody's
        # account.
        p["gaps"] = [{"field": "floor.somebody_named",
                      "says": "The named person at the supplier is to be "
                              "confirmed.", "owner": "Whoever decides"}]
        _write(held)
    _record("event.record_created", actor, {"ref": ref, "gaius": True})
    return {"ok": True, "seeded": True, "ref": ref}


# ===========================================================================
# The list view
# ===========================================================================

COLUMNS = ("Reference", "What it is", "Gate", "State", "Waiting on",
           "Running?", "Scrutiny level", "Named person", "Last moved")

EMPTY = ("Nothing here yet.\n\nStart with the thing somebody complained "
         "about most recently. You do not need a solution in mind — the "
         "first half of this asks what goes wrong, and it is better answered "
         "before anybody has decided what to buy.")


def empty_state(seeded: int = 0) -> str:
    """Where the framework already named tools, the list is not empty on the
    first day and the copy says so without calling any of it a problem."""
    if seeded:
        return (f"{seeded} things you already have, waiting to be written "
                f"up.\n\nThese came from what you told us in your framework. "
                f"None of them is a problem. This is the list you said you "
                f"did not have. Open the one you would miss most if it "
                f"stopped.")
    return EMPTY


#: What this surface is not. Kept in the code because each line is a feature
#: somebody will eventually propose.
NOT_THIS = (
    "a record of work — no permits, no case files, no correspondence, and "
    "nothing anybody typed into an AI tool",
    "a project management tool — no chart, no task list, no assignments, no "
    "percentage complete, no dependency graph",
    "a scorecard — nothing here rates a project, a person, a unit or the "
    "organization",
    "a judge of whether a tool is a good idea — an organization that runs "
    "every project to ended without a tool has used this correctly",
)

#: Nothing here watches your vendors. Shown on the screen in these words.
NO_VENDOR_FEED = (
    "Nothing here watches your vendors. This application finds out that a "
    "tool changed when a person writes it down, and there is no feed "
    "anywhere that would tell it otherwise. What you see is what somebody "
    "recorded, and this count says so rather than presenting itself as "
    "complete.")


def report() -> dict[str, Any]:
    rows = all_projects()
    return {
        "projects": rows,
        "counters": counters(rows),
        "columns": list(COLUMNS),
        "empty": empty_state(sum(1 for p in rows if p.get("seeded"))),
        "spine": spine.as_dict(),
        "not_this": list(NOT_THIS),
        "no_vendor_feed": NO_VENDOR_FEED,
        "nothing_to_flag": spine.NOTHING_TO_FLAG,
    }
