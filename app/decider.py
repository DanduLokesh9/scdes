"""Who decides — the one framework answer that shapes the rest of the app.

Every governmental unit that writes a governance framework has to answer the
same question: *when a decision is gated, who makes it?* There are two honest
answers and this application must be able to hold either.

  ``group``       A standing body — a council, a board, a committee. Members,
                  a quorum, convened sessions, minutes. This is SCDES.
  ``individual``  One named role decides and reports out. A small unit with one
                  technology officer is not going to convene a nine-member AI
                  council, and pretending otherwise produces a framework nobody
                  follows.

Until the question is answered the shape is ``unset``, and the application says
so rather than assuming. That matters: an earlier build hardwired the council —
the rail carried a Council room, gate routing said "the decision is the
Council's", the decision levels described convened sessions and 72-hour
concurrence. All of that is SCDES's answer to this question, imported from their
binder and then presented to every agency as though it were the law. A unit that
had chosen a single decision-maker would have been told their approval routes to
a body they had deliberately not created.

So the body is not furniture. It is an *output* of the framework, and this
module is where that output lives.

Two design rules, both borrowed from `vocabulary.py` because they earned their
place there:

**Canonical keys stay stable.** A risk result still carries `council_required`;
a decision is still tier `a`/`b`/`c`. Only the rendering follows the answer.
That keeps scoring, the audit trail and every record already written readable
whichever shape an agency picks, and it means changing the answer re-labels the
application rather than invalidating its history.

**Defaults are derived, not invented.** `derive_from_corpus()` reads the loaded
documents and reports what they actually constitute. SCDES's corpus contains a
signed council charter, so the proposal is a council — with the evidence
attached, and marked unconfirmed until a person says yes.

Who may answer, and why it changes:

  unset → answered      A setup act, while the framework is being written. OT
                        may do it, like any other configuration.
  answered → changed    An amendment to the framework. Only the body that the
                        answer created may change who the body is.

That asymmetry is deliberate. Requiring the decider's approval to appoint the
first decider is a loop with no entrance.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.audit import CORPUS, atomic_write
from app.authz import Actor, Target, guard

#: Where the answer is recorded. Alongside the framework adoption and the
#: vocabulary, because it is the same kind of thing: a choice the agency made
#: once, at the top, that everything downstream reads.
DECIDER_FILE = CORPUS / "config" / "decider.json"

UNSET = "unset"
GROUP = "group"
INDIVIDUAL = "individual"

SHAPES = {
    UNSET: {
        "label": "Not decided yet",
        "means": "The framework has not yet said who makes gated decisions.",
    },
    GROUP: {
        "label": "A group decides",
        "means": "A standing body with members and a quorum. Decisions can be "
                 "graded — one person for routine matters, concurrence for "
                 "middling ones, a convened session for the serious ones.",
    },
    INDIVIDUAL: {
        "label": "One person decides",
        "means": "A single named role makes the call and reports out. No "
                 "members, no quorum, no convened sessions — one decision "
                 "level, and a record of every call made.",
    },
}

#: What a standing body might be called. Offered, not imposed — an agency can
#: type its own.
GROUP_NOUNS = ["Council", "Board", "Committee", "Commission", "Steering Group",
               "Working Group", "Panel"]

#: Roles that plausibly hold the decision alone in a small unit. Same status:
#: suggestions for a text field, never a closed list.
INDIVIDUAL_ROLES = ["Chief Technology Officer", "Chief Information Officer",
                    "Director", "County Administrator", "City Manager",
                    "Agency Head", "Chief Data Officer"]

#: The graded decision levels, keyed canonically. A group can use all three; a
#: single decider has only one, because there is nobody to concur with and
#: nobody to convene.
GROUP_LEVELS = {
    "a": "{holder} alone; logged to the decision record.",
    "b": "72-hour concurrence of the {body}; silence is not assent.",
    "c": "Convened session of the {body}; consensus, with quorum met.",
}
INDIVIDUAL_LEVEL = "{body} decides and records the call.{report}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ the record

@dataclass
class Decider:
    #: unset | group | individual
    shape: str = UNSET
    #: For a group, what it is called ("Council"). For an individual, the role
    #: that holds the decision ("Chief Technology Officer").
    noun: str = ""
    #: Where the individual reports their calls. Empty for a group, whose
    #: minutes are the report.
    report_out: str = ""
    #: How many members must be present for a convened session. Meaningless for
    #: an individual, and forced to 1 there rather than left to mislead.
    quorum: int = 1
    #: True once a person answered. A derived proposal is not an answer.
    confirmed: bool = False
    answered_by: str = ""
    answered_title: str = ""
    answered_on: str = ""
    #: Why this was proposed, when it was derived rather than answered.
    evidence: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    # -- rendering ---------------------------------------------------------
    #
    # Every user-visible mention of the deciding body goes through one of these,
    # so there is one place that knows what this agency calls it.

    @property
    def is_group(self) -> bool:
        return self.shape == GROUP

    @property
    def decided(self) -> bool:
        return self.shape in (GROUP, INDIVIDUAL)

    @property
    def rail_label(self) -> str:
        """The name of the room in the left rail."""
        if self.shape == GROUP:
            return self.noun or "Council"
        if self.shape == INDIVIDUAL:
            return "Decisions"
        return "Who decides"

    @property
    def body(self) -> str:
        """How to name the decider in a sentence: "routes to {body}"."""
        if self.shape == GROUP:
            return f"the {self.noun or 'Council'}"
        if self.shape == INDIVIDUAL:
            return f"the {self.noun}" if self.noun else "the named decision-maker"
        return "whoever this agency names as its decision-maker"

    @property
    def possessive(self) -> str:
        """"the decision is {possessive}".

        Not `body + "'s"` in every case. Unanswered, `body` is a whole clause —
        "whoever this agency names as its decision-maker" — and appending an
        apostrophe-s to a clause produces "whoever this agency names as its
        decision-maker's", which no reader parses on the first pass.
        """
        if self.shape == UNSET:
            return "the decision-maker's, once this agency names one"
        return self.body + "'s"

    @property
    def capacity_label(self) -> str:
        """What the sign-in screen calls the capacity that holds the decision."""
        if self.shape == GROUP:
            return f"{self.noun or 'Council'} member"
        if self.shape == INDIVIDUAL:
            return self.noun or "Decision-maker"
        return "Decision-maker"

    def levels(self) -> dict[str, str]:
        """The decision levels that actually apply to this shape."""
        if self.shape == INDIVIDUAL:
            report = (f" Reported to {self.report_out}." if self.report_out
                      else "")
            # Upper-case the first letter only. `.capitalize()` also lowers the
            # rest, which turned "the Chief Technology Officer" into "The chief
            # technology officer" — someone's actual job title, mangled.
            lead = self.body[:1].upper() + self.body[1:]
            return {"a": INDIVIDUAL_LEVEL.format(body=lead, report=report)}
        if self.shape == GROUP:
            # The holder of a routine call is the chair unless the agency said
            # otherwise; naming the body twice reads worse than naming a seat.
            holder = f"The chair of {self.body}"
            return {k: v.format(holder=holder, body=self.noun or "Council")
                    for k, v in GROUP_LEVELS.items()}
        return {}

    def level_for_band(self, band: str) -> str:
        """Which decision level a gate decision at this risk band needs."""
        if self.shape == INDIVIDUAL:
            return "a"                       # one decider, one level
        return {"low": "a", "moderate": "b", "high": "c"}.get(
            str(band).strip().lower(), "b")

    def sentence(self) -> str:
        """One line describing the arrangement, for anywhere that needs it."""
        if self.shape == GROUP:
            return (f"Gated decisions are {self.possessive}. It has "
                    f"{self.quorum} member(s) for quorum, and grades decisions "
                    f"into three levels by seriousness.")
        if self.shape == INDIVIDUAL:
            tail = (f", reporting out to {self.report_out}" if self.report_out
                    else ", and reports out")
            return (f"Gated decisions are {self.possessive}. One person decides"
                    f"{tail}. There is no group to consult and no meeting to "
                    f"hold.")
        return ("Nobody has been named yet. Until the framework says who "
                "decides, a gated decision has nowhere to go.")


# ------------------------------------------------------------------ derivation

def derive_from_corpus() -> Decider:
    """What the loaded documents already constitute — a proposal, not an answer.

    A signed charter is direct evidence that a body was actually stood up, so it
    counts for far more than a document mentioning the word "council" in
    passing. Where there is no such evidence this returns ``unset`` rather than
    guessing, because guessing here is exactly the failure being fixed.
    """
    charter_files: list[str] = []
    charter_dir = CORPUS / "charter"
    if charter_dir.is_dir():
        charter_files = sorted(f.name for f in charter_dir.iterdir()
                               if f.is_file() and not f.name.startswith("~$"))

    counts: dict[str, int] = {}
    try:
        from app.ingest_docx import parse_all as parse_docs
        text = "\n".join(f"{c.heading}\n{c.text}"
                         for d in parse_docs() for c in d.chunks)
        for candidate in GROUP_NOUNS:
            # Capitalised, as a constituted body is written. Lower-case "board"
            # in running prose is usually a different sense of the word.
            hits = len(re.findall(rf"\b{re.escape(candidate)}\b", text))
            if hits:
                counts[candidate] = hits
    except Exception:
        counts = {}

    if not charter_files and not counts:
        return Decider(shape=UNSET, evidence="No charter, and no constituted "
                                             "body named in the documents.")

    noun = max(counts.items(), key=lambda kv: kv[1])[0] if counts else "Council"
    bits = []
    if charter_files:
        bits.append(f"a charter is loaded ({', '.join(charter_files[:2])})")
    if counts.get(noun):
        bits.append(f"the documents name a {noun} {counts[noun]} times")

    return Decider(
        shape=GROUP, noun=noun, quorum=3, confirmed=False,
        evidence="Proposed because " + " and ".join(bits) +
                 ". Confirm or change it — nothing is assumed to be adopted.",
    )


# -------------------------------------------------------------------- storage

#: Keyed by agency code — "" is the single-tenant case (tests, the CLI, and the
#: agency that owns the corpus).
_cache: dict[str, Decider] = {}


def _file() -> Path:
    """This agency's answer to "who decides". See app/tenant.py."""
    from app import tenant
    return tenant.scoped(DECIDER_FILE)


def load(refresh: bool = False) -> Decider:
    """Who holds the decision for the agency on this request.

    The cache is keyed by agency. It used to be a single module-level value,
    which is a leak of its own kind: whichever agency asked first decided for
    everyone until the process restarted, so a DEMO account naming one officer
    could rename SCDES's Council in the next request.
    """
    from app import tenant
    global _cache
    key = tenant.current()
    if not isinstance(_cache, dict):
        _cache = {}
    if key in _cache and not refresh:
        return _cache[key]

    path = _file()
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8")) or {}
            known = {f for f in Decider.__dataclass_fields__}
            _cache[key] = Decider(**{k: v for k, v in raw.items() if k in known})
            return _cache[key]
        except (ValueError, OSError, TypeError):
            pass                              # fall through to derivation

    # Deriving reads the agency's charter out of the corpus. An agency that
    # does not own the corpus has no charter to read, and proposing SCDES's
    # answer to them would be exactly the suggestion this must never make.
    _cache[key] = derive_from_corpus() if tenant.owns_corpus() else Decider()
    return _cache[key]


def invalidate() -> None:
    """Drop every agency's cached answer. Cheap, and safer than guessing which
    one changed — a stale entry here is another agency's governance."""
    global _cache
    _cache = {}


def _save(record: Decider) -> None:
    path = _file()
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(path, json.dumps(record.as_dict(), indent=2))
    invalidate()


# ---------------------------------------------------------------- the answer

def answer(shape: str, actor: Actor, *, noun: str = "", quorum: int = 3,
           report_out: str = "") -> dict[str, Any]:
    """Record who decides. Validated, guarded and audited.

    Answering for the first time is a setup act and belongs to OT. Changing an
    answer already on record is an amendment to the framework, and only the body
    the answer created may make it — otherwise anyone with the configuration
    could quietly reassign the authority the whole application defers to.
    """
    shape = (shape or "").strip().lower()
    if shape not in (GROUP, INDIVIDUAL):
        return {"ok": False,
                "error": f"{shape!r} is not an answer. Choose a group or one "
                         f"person."}

    noun = " ".join((noun or "").split())[:80]
    if not noun:
        return {"ok": False,
                "error": ("Name the body — Council, Board, Committee, whatever "
                          "your framework calls it."
                          if shape == GROUP else
                          "Name the role that holds the decision, such as "
                          "Chief Technology Officer.")}

    current = load()
    first_time = not current.confirmed
    target = Target.CONFIG if first_time else Target.FRAMEWORK
    decision = guard(
        actor, target,
        "answer_who_decides" if first_time else "change_who_decides",
        detail={"shape": shape, "noun": noun,
                "was": current.shape, "was_noun": current.noun},
    )
    if not decision.allowed:
        return {"ok": False, "error": decision.reason,
                "requires_council": decision.requires_council}

    if shape == GROUP:
        try:
            quorum = int(quorum)
        except (TypeError, ValueError):
            quorum = 3
        if quorum < 2:
            return {"ok": False,
                    "error": "A group needs at least two members present to be "
                             "a group. If one person decides, say so — that is "
                             "the other answer, and the app will stop asking "
                             "for a quorum."}
        record = Decider(shape=GROUP, noun=noun, quorum=quorum, report_out="")
    else:
        record = Decider(shape=INDIVIDUAL, noun=noun, quorum=1,
                         report_out=" ".join((report_out or "").split())[:120])

    record.confirmed = True
    record.answered_by = (actor.name or "").strip()[:120]
    record.answered_title = (actor.title or "").strip()[:120]
    record.answered_on = _now()
    record.evidence = ""            # an answer supersedes the proposal
    _save(record)
    return {"ok": True, "decider": record.as_dict(), "state": state(),
            "reason": decision.reason}


# ------------------------------------------------------------------ shortcuts
#
# The rest of the application asks these rather than reading the record itself,
# so "what does this agency call its decider" has exactly one implementation.

def current() -> Decider:
    return load()


def is_group() -> bool:
    return load().is_group


def quorum() -> int:
    """Members needed for a convened session. Always 1 for a single decider."""
    d = load()
    return d.quorum if d.is_group else 1


def body() -> str:
    return load().body


def possessive() -> str:
    return load().possessive


def rail_label() -> str:
    return load().rail_label


def capacity_label() -> str:
    return load().capacity_label


def levels() -> dict[str, str]:
    return load().levels()


def level_for_band(band: str) -> str:
    return load().level_for_band(band)


# ------------------------------------------------------------------ reporting

def state() -> dict[str, Any]:
    """Everything a screen needs to draw the question, or its answer."""
    d = load()
    return {
        **d.as_dict(),
        "decided": d.decided,
        "is_group": d.is_group,
        "rail_label": d.rail_label,
        "body": d.body,
        "possessive": d.possessive,
        "capacity_label": d.capacity_label,
        "levels": d.levels(),
        "sentence": d.sentence(),
        "shapes": [{"key": k, **v} for k, v in SHAPES.items() if k != UNSET],
        "group_nouns": GROUP_NOUNS,
        "individual_roles": INDIVIDUAL_ROLES,
        "question": "When a decision is gated, who makes it?",
        "why": ("Some units stand up a council. Others have one technology "
                "officer who makes the call and reports out. Both are real "
                "answers, and the application follows whichever you choose — "
                "the room in the sidebar, the wording on every gate, and the "
                "decision levels all come from this."),
        # Named plainly, because a user who changes this later deserves to know
        # it is not a cosmetic setting.
        "affects": [
            "The room in the sidebar, and what it is called",
            "Where a gated decision routes, and how that is worded",
            "How many decision levels exist, and what each one requires",
            "Whether a quorum is asked for at all",
        ],
    }
