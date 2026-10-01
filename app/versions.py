"""Framework versions — and the act that turns a draft into an adopted document.

Two client decisions shape this module, and both are worth stating because they
are the reason it exists rather than a version counter living in a config file.

**Versions increment deliberately.** "Suggest it only increments when they
deliberately save a new version, not on every keystroke. Otherwise they'll be on
v47 by lunchtime." So answering questions edits the *working draft* and changes
nothing about its number. Pressing save cuts a version, and that version is
frozen: a snapshot of every answer as it stood, with who cut it and when. What
you exported as DRAFT VERSION 3 is what DRAFT VERSION 3 will always contain.

**Adoption happens here, not in a meeting the software never hears about.**
"How do we get them to go from draft to adopted? I think that's got to be in
platform?" It does. A watermark that can be stripped from a PDF is a deterrent,
not a control — the thing that actually distinguishes a draft from an adopted
framework is a record of a body with authority adopting it, and that record has
to live somewhere the platform can read. So adoption is an act performed against
a specific version number, by a named person, on a date, and every export after
it says so.

What this deliberately does not claim
-------------------------------------

It does not verify the adoption. The decision was taken in a room; this is the
application being told about it, and the record says exactly that. Nor does it
make a PDF tamper-proof. A determined person can strip a watermark. What the
provenance block and the version record give you is a way to *check* — an
exported document names a version, and the platform can say whether that version
was adopted, by whom, and whether the text matches. That is a stronger property
than an unremovable graphic, and an honest one.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import CORPUS, atomic_write
from app.authz import Actor, Target, guard

VERSIONS_FILE = CORPUS / "config" / "framework_versions.json"

DRAFT = "draft"
ADOPTED = "adopted"
SUPERSEDED = "superseded"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Version:
    number: int
    status: str = DRAFT
    created_at: str = ""
    created_by: str = ""
    created_title: str = ""
    #: What the person said this version changes. Optional, and worth asking for
    #: — a version history of "v1, v2, v3" tells a later reader nothing.
    note: str = ""
    #: Every answer as it stood when the version was cut. Frozen.
    answers: dict[str, Any] = field(default_factory=dict)
    #: Risk acceptances in force at that moment: which protection was given up,
    #: who accepted it, when. Travels with the version because a version that
    #: dropped human review is a materially different document.
    acceptances: list[dict[str, Any]] = field(default_factory=list)
    #: Fingerprint of the answers, so an exported document can be matched back
    #: to the version it claims to be.
    digest: str = ""
    adopted_on: str = ""
    adopted_by: str = ""
    adopted_title: str = ""
    adoption_note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "label": self.label, "is_draft": self.is_draft}

    @property
    def is_draft(self) -> bool:
        return self.status == DRAFT

    @property
    def label(self) -> str:
        """What an exported document calls itself, on the cover and page 2."""
        if self.status == ADOPTED:
            return f"VERSION {self.number} · adopted {self.adopted_on}"
        if self.status == SUPERSEDED:
            return f"VERSION {self.number} · superseded"
        return f"DRAFT VERSION {self.number}"


def _digest(answers: dict[str, Any]) -> str:
    blob = json.dumps(answers, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


# -------------------------------------------------------------------- storage

def _file() -> Path:
    """This agency's answers.

    Was `VERSIONS_FILE` directly, which meant every registered agency answered
    the same thirteen questions into the same file. The constant stays as the
    single-tenant default — tests and the CLI pin it, and `tenant.scoped` hands
    it straight back when no agency is bound to the request.
    """
    from app import tenant
    return tenant.scoped(VERSIONS_FILE)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return {"working": {}, "acceptances": [], "versions": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {"working": {}, "acceptances": [], "versions": []}
    data.setdefault("working", {})
    data.setdefault("acceptances", [])
    data.setdefault("versions", [])
    return data


def _write(data: dict[str, Any]) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(data, indent=2, default=str))


def _versions(data: dict[str, Any]) -> list[Version]:
    known = {f for f in Version.__dataclass_fields__}
    return [Version(**{k: v for k, v in row.items() if k in known})
            for row in data.get("versions", [])]


# ------------------------------------------------------------- the working set
#
# Answering a question writes here and nowhere else. No version number moves, no
# history entry appears, and nothing is frozen — this is the document being
# written, not a document being published.

#: How much of an answer goes into the log. Long enough for every real answer
#: — the longest thing anybody types here is a paragraph — and bounded so a
#: paste of a whole policy cannot make the log unreadable.
LOGGED_VALUE_LIMIT = 4000


def _for_the_log(value: Any) -> Any:
    """The answer, small enough to sit in a log line."""
    if isinstance(value, str) and len(value) > LOGGED_VALUE_LIMIT:
        return value[:LOGGED_VALUE_LIMIT] + f"… ({len(value)} characters)"
    return value


def _log_the_choice(key: str, value: Any, before: dict[str, Any],
                    actor: Actor) -> None:
    """Record what was chosen, and what it replaced.

    The client, in capitals: "WE NEED TO LOG ALL CHOICES, ACTIVITIES, and
    Framework versions on the back end."

    This wrote nothing at all. The register Module One replaced logged an
    `answer_framework_question` entry naming the question and the person — but
    never the answer — and Module One's own path did not log even that. So the
    log could say that somebody answered 1.1 and not what they said, which is
    not a record of a choice.

    Found the hard way: a test harness overwrote a client's answers and there
    was nothing to restore them from. Recording the previous value is what
    makes that recoverable rather than merely regrettable, and it is also what
    an auditor asking "when did this become the rule, and what was it before?"
    actually needs.
    """
    from app import tenant
    from app.authz import default_log
    try:
        default_log().append(
            actor=actor.user_id, role=actor.role.value,
            action="answer_framework_question", target="framework",
            outcome="allowed",
            detail={
                "key": key,
                "value": _for_the_log(value),
                "was": _for_the_log(before.get("value")),
                "agency": tenant.current(),
                "actor_name": (actor.name or "").strip()[:120],
                "actor_title": (actor.title or "").strip()[:120],
                "reason": "A working draft: answers are the agency's to give, "
                          "and every one of them is recorded.",
            })
    except Exception:
        # An answer is not lost because the log could not be written. The log
        # is a record of what happened, not a gate on it — and a builder that
        # refused to save because of a disk problem in the audit directory
        # would be a worse failure than a missing line.
        pass


def answer(key: str, value: Any, actor: Actor, *,
           accepted_risk: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record one answer against the working draft.

    **Not gated on a capacity, deliberately.** This used to pass through
    `guard(Target.CONFIG)`, which is the Office of Technology's to set — so
    anyone who had not switched their capacity to OT was refused, with a message
    about operational configuration they had no reason to understand.

    That was correct for the register it was written against, where answers set
    operational parameters the Council had adopted. It is wrong for Module One,
    which is the free offering: a public official with no AI background sits
    down to write their agency's first framework, and there is no Office of
    Technology yet — deciding whether there should be one is question 4.1.
    Requiring the answer before the question is asked is circular.

    Nothing is lost by opening it. A draft is a draft: the working answers
    carry the name and title of whoever gave them, and the governed acts —
    cutting a version, recording an adoption — are still guarded. That
    separation is the whole point of the draft/adopted distinction.
    """
    data = _read()
    before = data["working"].get(key) or {}
    data["working"][key] = {
        "value": value,
        "at": _now(),
        "by": (actor.name or "").strip()[:120],
        "by_title": (actor.title or "").strip()[:120],
    }
    _log_the_choice(key, value, before, actor)

    if accepted_risk:
        data["acceptances"] = [a for a in data["acceptances"]
                               if a.get("key") != key]
        data["acceptances"].append({
            "key": key,
            "gave_up": accepted_risk.get("abrogates", []),
            "warning": accepted_risk.get("warning", ""),
            "accepted_by": (actor.name or "").strip()[:120],
            "accepted_title": (actor.title or "").strip()[:120],
            "accepted_at": _now(),
        })
    else:
        # Moving back to the safe answer withdraws the acceptance rather than
        # leaving a stale "we accept this risk" attached to a document that no
        # longer takes it.
        data["acceptances"] = [a for a in data["acceptances"]
                               if a.get("key") != key]

    _write(data)
    return {"ok": True, "state": state()}


def working() -> dict[str, Any]:
    return _read()["working"]


def unsaved_changes() -> int:
    """How many answers differ from the last version cut.

    Shown next to the save button, because "save a new version" is meaningless
    without knowing whether anything changed.
    """
    data = _read()
    versions = _versions(data)
    if not versions:
        return len(data["working"])
    last = versions[-1].answers
    now = {k: v.get("value") for k, v in data["working"].items()}
    then = {k: v.get("value") if isinstance(v, dict) else v
            for k, v in last.items()}
    keys = set(now) | set(then)
    return sum(1 for k in keys if now.get(k) != then.get(k))


# ------------------------------------------------------------ cutting a version

def save_version(actor: Actor, note: str = "") -> dict[str, Any]:
    """Freeze the working draft as the next numbered version.

    This is the only thing that moves the number. Deliberate, so a version
    history is a record of decisions rather than of typing.
    """
    decision = guard(actor, Target.CONFIG, "save_framework_version",
                     detail={"note": note[:120]})
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}

    data = _read()
    if not data["working"]:
        return {"ok": False,
                "error": "Nothing has been answered yet, so there is no version "
                         "to cut."}

    versions = _versions(data)
    if versions and versions[-1].is_draft and not unsaved_changes():
        return {"ok": False,
                "error": f"Nothing has changed since DRAFT VERSION "
                         f"{versions[-1].number}. Saving again would add a "
                         f"version number to an identical document."}

    # A draft that is superseded by a newer draft is marked as such. An adopted
    # version is left alone: it was adopted, and that stays true.
    for v in versions:
        if v.is_draft:
            v.status = SUPERSEDED

    answers = {k: v.get("value") for k, v in data["working"].items()}
    fresh = Version(
        number=(versions[-1].number + 1) if versions else 1,
        status=DRAFT,
        created_at=_now(),
        created_by=(actor.name or "").strip()[:120],
        created_title=(actor.title or "").strip()[:120],
        note=(note or "").strip()[:300],
        answers=answers,
        acceptances=list(data["acceptances"]),
        digest=_digest(answers),
    )
    data["versions"] = [v.as_dict() for v in versions] + [fresh.as_dict()]
    _write(data)
    return {"ok": True, "version": fresh.as_dict(), "state": state()}


# ------------------------------------------------------------------- adoption

def adopt(number: int, actor: Actor, *, adopted_on: str = "",
          note: str = "", verified_member: bool = False) -> dict[str, Any]:
    """Record that a body with authority adopted a specific version.

    Recording an adoption is the act the DRAFT label exists to withhold, so
    it is guarded — by the one rule in `authz.ADOPTION_ACTIONS`, shared with
    the Framework screen. That rule used to be Council-only here, and nobody
    who signs in holds the Council capacity, so nothing could be adopted.
    `verified_member` is the caller's finding that the person is a proven,
    active member of this organization.
    """
    decision = guard(actor, Target.FRAMEWORK, "adopt_framework_version",
                     detail={"version": number},
                     verified_member=verified_member)
    if not decision.allowed:
        return {"ok": False, "error": decision.reason,
                "requires_council": decision.requires_council}

    data = _read()
    versions = _versions(data)
    target = next((v for v in versions if v.number == int(number)), None)
    if target is None:
        return {"ok": False, "error": f"There is no version {number}."}
    if target.status == ADOPTED:
        return {"ok": False,
                "error": f"Version {number} was already adopted on "
                         f"{target.adopted_on}."}

    target.status = ADOPTED
    target.adopted_on = (adopted_on or "").strip() or clock.today().isoformat()
    target.adopted_by = (actor.name or "").strip()[:120]
    target.adopted_title = (actor.title or "").strip()[:120]
    target.adoption_note = (note or "").strip()[:400]

    # Earlier drafts are superseded by an adoption, not left looking live.
    for v in versions:
        if v.number < target.number and v.status == DRAFT:
            v.status = SUPERSEDED

    data["versions"] = [v.as_dict() for v in versions]
    _write(data)

    # Keep the older single-record adoption file in step, so the Framework
    # screen and anything else reading it do not disagree with this module.
    try:
        from app import framework
        adoption = framework.adoption_file()
        adoption.parent.mkdir(parents=True, exist_ok=True)
        adoption.write_text(json.dumps({
            "adopted_on": target.adopted_on,
            "adopted_by": target.adopted_by,
            "adopted_by_title": target.adopted_title,
            "note": target.adoption_note,
            "version": target.number,
            "recorded_at": _now(),
            "verified": False,
            "record_note": "self-declared; the application was told, not shown",
        }, indent=2), encoding="utf-8")
    except Exception:
        pass

    return {"ok": True, "version": target.as_dict(), "state": state()}


# -------------------------------------------------------------------- reading

def current() -> Version | None:
    """The version a document would be exported as right now."""
    versions = _versions(_read())
    return versions[-1] if versions else None


def adopted() -> Version | None:
    """The most recently adopted version, if any."""
    return next((v for v in reversed(_versions(_read()))
                 if v.status == ADOPTED), None)


def history() -> list[dict[str, Any]]:
    return [v.as_dict() for v in reversed(_versions(_read()))]


def export_label() -> str:
    """What the next exported document calls itself.

    Before anything is saved there is no version, and the export says so rather
    than claiming to be version 1 of something nobody committed to.
    """
    v = current()
    if v is None:
        return "DRAFT — unsaved working document"
    # Checked before the status, not after. An adopted version with edits on top
    # is not an adopted document, and the label has to agree with watermark() —
    # they were disagreeing, which is exactly the confusion the DRAFT stamp is
    # supposed to prevent.
    pending = unsaved_changes()
    if pending:
        base = (f"DRAFT — {pending} change(s) since version {v.number}"
                if not v.is_draft else f"{v.label} + {pending} unsaved change(s)")
        return base
    return v.label


def watermark() -> str:
    """The diagonal stamp on every page, or empty once adopted."""
    v = current()
    if v is None or v.is_draft or unsaved_changes():
        return "DRAFT"
    return ""


def state() -> dict[str, Any]:
    """Everything the version panel needs."""
    data = _read()
    v = current()
    live = adopted()
    return {
        "current": v.as_dict() if v else None,
        "adopted": live.as_dict() if live else None,
        "history": history(),
        # The answers themselves, not just how many there are. The builder
        # re-opens on a half-finished framework and has to show what is already
        # filled in; without this it rendered every question blank and every
        # section as 0 answered, however much had been written.
        "working": data["working"],
        "answered": len(data["working"]),
        "unsaved": unsaved_changes(),
        "acceptances": data["acceptances"],
        "export_label": export_label(),
        "watermark": watermark(),
        "is_draft": (v is None) or v.is_draft or bool(unsaved_changes()),
        # Said plainly on the screen, because the client asked for the watermark
        # to be "non-removable" and it cannot honestly be described that way.
        "watermark_note": (
            "The DRAFT stamp appears on every page and the provenance block on "
            "page 2. Both deter casual reuse; neither is tamper-proof, because "
            "any PDF watermark can be stripped by someone determined. What "
            "makes a document checkable is the version number — this platform "
            "can say whether that version was adopted, by whom, and on what "
            "date."),
        "how_to_adopt": (
            "Save a version, then have whoever holds the authority record the "
            "adoption against that version number. The DRAFT stamp comes off "
            "the moment that record exists, and goes back on as soon as anyone "
            "answers another question."),
    }
