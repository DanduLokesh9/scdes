"""The shared standard every surface binds to.

SPINE.md, as code. Eleven surfaces assemble into one application, each owning
part of a single record, and each has to move that record without asking the
other ten what they called things. This module fixes the shared names: the
gate identifiers, the record states, the transitions, the role powers, the
shape of a recorded gap, the shape of a recommendation, and the findings more
than one surface raises.

Where a surface and this module disagree, this module controls. Where this
module is silent, the surface decides and says so.

Three things are worth stating before anything else, because getting them
wrong is how a spec like this rots.

**The app refuses a passage at two gates and nowhere else.** At Identify, a
project with nobody's name against it. At Deploy, six floor obligations that
have to be satisfiable by pointing at something. Everywhere else a missing
answer becomes a gap with an owner or a condition with a date, and the work
moves. Declining to record a passage is the only enforcement this software
has — it cannot stop a tool being used in the world, and it says so rather
than implying otherwise.

**Every number belongs to the organization.** No default review period, no
default dollar amount, no default sample size, no default number of scrutiny
levels. This module supplies fields and names; it never supplies a threshold.
Where it is tempted to write a number, it writes a read-back instead.

**Organizations are never scored.** No composite, no percentage, no maturity
level, no comparison to another organization. Counts and absences only.
Ranking candidate solutions at a purchase decision is a different act, is
expressly permitted, and is bounded at §7 of the spine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ===========================================================================
# 1 · The seven gates
# ===========================================================================

#: Gate identifiers are names rather than numbers, and the choice was
#: deliberate. Numbered gates invite a reader to line them up against
#: somebody else's numbered gates and to import a staging scheme this
#: platform did not write. Never render a gate as "Gate 3" or "Stage 4"
#: anywhere, in code or in copy — `tests/test_spine.py` checks the copy.
GOVERN = "gate.govern"
IDENTIFY = "gate.identify"
PROCURE = "gate.procure"
TEST = "gate.test"
DEPLOY = "gate.deploy"
MEASURE = "gate.measure"
SUNSET = "gate.sunset"


@dataclass(frozen=True)
class Gate:
    id: str
    name: str
    #: What the gate turns on — the question it exists to answer.
    turns_on: str
    #: The surface that holds the evidence the gate turns on. That rule is
    #: what produced this column, and it is the rule to apply when a question
    #: arises about where a new field belongs.
    owner: str
    #: Surfaces that write evidence here. Projects is on all of them and is
    #: omitted, because Projects is the only writer of state. Audit trail is
    #: omitted for the opposite reason: it receives and never writes back.
    writes_from: tuple[str, ...]


GATES: tuple[Gate, ...] = (
    Gate(GOVERN, "Govern", "Who decides, under what rules", "Oversight",
         ("Oversight", "Process", "Vision")),
    Gate(IDENTIFY, "Identify",
         "Is the problem defined, and is there already something that "
         "solves it", "Projects",
         ("Projects", "Registry", "Data", "Vision", "Oversight")),
    Gate(PROCURE, "Procure",
         "How you got it, on what terms, at what full cost, measured "
         "against what", "Vendors",
         ("Vendors", "Budget", "Projects", "Process", "Oversight")),
    Gate(TEST, "Test",
         "What evidence exists that it does what it claims, and what was "
         "not tested", "Integrity",
         ("Integrity", "Data", "Process", "Oversight", "Projects")),
    Gate(DEPLOY, "Deploy",
         "Do the operating instructions exist, and can a person find them",
         "Process",
         ("Process", "Integrity", "Projects", "Oversight", "Vision")),
    Gate(MEASURE, "Measure", "Is it still true", "Integrity",
         ("Integrity", "Budget", "Vision", "Vendors", "Data", "Process",
          "Oversight", "Projects")),
    Gate(SUNSET, "Sunset",
         "Is it still worth keeping, and what happens to what it leaves "
         "behind", "Projects",
         ("Projects", "Vision", "Oversight", "Process", "Data", "Vendors",
          "Budget")),
)

GATE_ORDER: tuple[str, ...] = tuple(g.id for g in GATES)
BY_GATE: dict[str, Gate] = {g.id: g for g in GATES}


def gate(gate_id: str) -> Gate | None:
    return BY_GATE.get(gate_id)


def position(gate_id: str) -> int:
    """How far along the spine a gate sits. -1 for anything unrecognized."""
    return GATE_ORDER.index(gate_id) if gate_id in GATE_ORDER else -1


def before(one: str, other: str) -> bool:
    """Whether `one` sits earlier along the spine than `other`."""
    here, there = position(one), position(other)
    return here >= 0 and there >= 0 and here < there


# ===========================================================================
# 2 · The eight record states
# ===========================================================================

PROPOSED = "state.proposed"
BEING_WORKED = "state.being_worked"
WAITING_DECISION = "state.waiting_decision"
WAITING_PERSON = "state.waiting_person"
CLEARED = "state.cleared"
PAUSED = "state.paused"
TURNED_DOWN = "state.turned_down"
RETIRED = "state.retired"


@dataclass(frozen=True)
class State:
    id: str
    shown_as: str
    means: str


STATES: tuple[State, ...] = (
    State(PROPOSED, "Proposed", "Written down; nobody has picked it up."),
    State(BEING_WORKED, "Being worked",
          "Somebody is assembling what the gate in front of it asks for."),
    State(WAITING_DECISION, "Waiting on a decision",
          "Everything the gate asks for exists; it is with whoever decides."),
    State(WAITING_PERSON, "Waiting on somebody",
          "Held up on a named person, an unanswered question, or an office "
          "that does not exist here."),
    # The handoff. In a small organisation it lasts a second and the user
    # will rarely see it; in a large one it is where things sit for weeks.
    # The state is what separates a stuck queue from a long one.
    State(CLEARED, "Cleared",
          "The gate behind it is passed; nobody has picked it up at the "
          "next one."),
    State(PAUSED, "Paused", "Stopped where it stands. Still on the list."),
    State(TURNED_DOWN, "Turned down",
          "Considered and not taken up. Stays on the list."),
    State(RETIRED, "Retired", "Was in use, taken off. Stays on the list."),
)

STATE_ORDER: tuple[str, ...] = tuple(s.id for s in STATES)
BY_STATE: dict[str, State] = {s.id: s for s in STATES}

#: States a project cannot be moved out of by an ordinary passage. Both are
#: reversible — see `START_AGAIN` and `PICK_UP_AGAIN` — and neither is an
#: ending. Nothing is ever deleted.
STOPPED = (PAUSED, TURNED_DOWN)

#: `in_use` is a third field, independent of gate and state, because a tool
#: can be in real use at Identify and a tool at Measure can be paused.
IN_USE_YES = "yes"
IN_USE_NO = "no"
IN_USE_UNKNOWN = "not known"
IN_USE = (IN_USE_YES, IN_USE_NO, IN_USE_UNKNOWN)


def state(state_id: str) -> State | None:
    return BY_STATE.get(state_id)


# ===========================================================================
# 3 · The eight floor obligations, and how each binds
# ===========================================================================

#: A floor binds in one of two ways and the difference decides whether
#: anything is refused.
#:
#: SATISFIED — the answer has to exist and point at something. A passage is
#: refused while it does not. Identify and Deploy, and nowhere else.
#:
#: ANSWERED — the question has to be put and the answer recorded, present or
#: absent. An absent answer produces a finding and the passage is recorded.
#: Procure and Sunset.
#:
#: The distinction is load-bearing. A vendor who will not grant a term the
#: organisation requires is a fact to record and argue with, not a reason
#: this application refuses to let the organisation buy anything.
SATISFIED = "satisfied"
ANSWERED = "answered"


@dataclass(frozen=True)
class Floor:
    id: str
    #: What it is, in the words a user reads.
    says: str


#: Numbered because Module One numbers them and the read-back map at §12
#: refers to them by number. The numbers are the framework's, not a staging
#: scheme of this application's.
FLOORS: tuple[Floor, ...] = (
    Floor("floor.person_decides", "a person makes the final call"),
    Floor("floor.keep_a_list", "there is one list of every tool in use"),
    Floor("floor.tell_people", "people are told"),
    Floor("floor.accessibility",
          "it works for people with disabilities"),
    Floor("floor.turn_it_off",
          "it can be turned off and the work still gets done"),
    Floor("floor.data_stays_yours", "the information stays the organization's"),
    Floor("floor.somebody_named", "somebody's name is on it"),
    Floor("floor.explain_plainly", "it can be explained in plain language"),
)
BY_FLOOR: dict[str, Floor] = {f.id: f for f in FLOORS}

#: Which floors bind at which gate, and in which of the two senses.
#:
#: Read this table against §2.5 of the spine. Two gates refuse and five do
#: not. An earlier draft of the spine said the application blocks in exactly
#: one place, which its own Identify gate contradicted; another read as
#: though every binding floor refused a passage, which would have made four
#: gates block. Both are settled here, in one table, so nobody re-derives
#: them from prose.
BINDS: dict[str, dict[str, str]] = {
    GOVERN: {},
    IDENTIFY: {"floor.somebody_named": SATISFIED},
    PROCURE: {"floor.data_stays_yours": ANSWERED,
              "floor.accessibility": ANSWERED},
    TEST: {},
    DEPLOY: {"floor.person_decides": SATISFIED,
             "floor.tell_people": SATISFIED,
             "floor.accessibility": SATISFIED,
             "floor.turn_it_off": SATISFIED,
             "floor.somebody_named": SATISFIED,
             "floor.explain_plainly": SATISFIED},
    MEASURE: {},
    SUNSET: {"floor.data_stays_yours": ANSWERED,
             "floor.keep_a_list": ANSWERED},
}

#: The only two gates that can refuse a passage at all.
REFUSING_GATES: tuple[str, ...] = tuple(
    g for g, floors in BINDS.items() if SATISFIED in floors.values())


def binding(gate_id: str, how: str = SATISFIED) -> tuple[str, ...]:
    """The floors that bind at this gate, in the sense asked for."""
    return tuple(f for f, sense in BINDS.get(gate_id, {}).items()
                 if sense == how)


# ===========================================================================
# 4 · Transitions, and the refusal protocol
# ===========================================================================

#: The six reason strings, exactly. A surface must not compose its own: a
#: user meeting two wordings for one refusal will assume they mean different
#: things.
REFUSE_IDENTIFY = "This cannot be recorded as past Identify yet."
REFUSE_DEPLOY = "This cannot be recorded as past Deploy yet."
REFUSE_NOT_PASSED = "This has not passed {gate} yet."
REFUSE_NOT_AVAILABLE = (
    "That move is not available from where this project is standing.")
REFUSE_RETIREMENT = "Only whoever decides can close a retirement record."
REFUSE_STOPPED = "This project is stopped. Start it again before moving it."

REASONS: tuple[str, ...] = (
    REFUSE_IDENTIFY, REFUSE_DEPLOY, REFUSE_NOT_PASSED,
    REFUSE_NOT_AVAILABLE, REFUSE_RETIREMENT, REFUSE_STOPPED,
)

#: The two reversals. Neither invents a state: starting again restores
#: whatever the project held before the pause, and picking up again reopens
#: a turned-down project into its own history rather than a second one.
START_AGAIN = "start_again"
PICK_UP_AGAIN = "pick_up_again"


@dataclass
class Answer:
    """What a surface proposing a move gets back. Never a silent failure.

    The proposing surface shows `refused` verbatim and keeps its own record,
    because the decision happened whether or not the move did.
    """

    committed: str = ""
    refused: str = ""
    #: The legal moves from where the project actually is, so a refusal is
    #: navigable rather than a dead end.
    refused_illegal: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return bool(self.committed)

    def as_dict(self) -> dict[str, Any]:
        return {"committed": self.committed, "refused": self.refused,
                "refused_illegal": list(self.refused_illegal)}


def legal_moves(from_gate: str, from_state: str) -> tuple[str, ...]:
    """Every gate this project may legally move to from where it stands.

    Forward passage runs in gate order and skipping forward is not
    available: a project found already running still walks Identify, Procure
    and Test in order, with each gate's paper marked as recorded after the
    fact. The record shows what actually happened, including that it
    happened out of order.
    """
    here = position(from_gate)
    if here < 0:
        return ()
    if from_state in STOPPED:
        # Nothing moves from a stop until it is reversed. That is not a
        # refusal of the destination; it is the project not being in play.
        return ()

    moves: list[str] = []

    # One step forward, and one only.
    if here + 1 < len(GATE_ORDER):
        moves.append(GATE_ORDER[here + 1])

    # Back a gate. Measure to Test where the vendor changed something;
    # Deploy to Test where evidence failed; any gate to Identify where the
    # scrutiny level was wrong. The project keeps its history.
    if from_gate in (MEASURE, DEPLOY):
        moves.append(TEST)
    if here > position(IDENTIFY):
        moves.append(IDENTIFY)

    # Jump to Sunset from Measure or Deploy. Retirement does not walk back
    # through the gates.
    if from_gate in (MEASURE, DEPLOY):
        moves.append(SUNSET)

    seen: list[str] = []
    for move in moves:
        if move != from_gate and move not in seen:
            seen.append(move)
    return tuple(seen)


def may_move(from_gate: str, to_gate: str, from_state: str) -> Answer:
    """Is this move legal from where the project is standing?

    Legality only. Whether the gate behind it is *satisfied* is a separate
    question answered by `may_pass`, because the two failures need different
    sentences: "that move is not available" and "this cannot be recorded as
    past Identify yet" are different problems for the person reading them.
    """
    if from_state in STOPPED:
        return Answer(refused=REFUSE_STOPPED,
                      refused_illegal=(START_AGAIN if from_state == PAUSED
                                       else PICK_UP_AGAIN,))
    allowed = legal_moves(from_gate, from_state)
    if to_gate not in allowed:
        return Answer(refused=REFUSE_NOT_AVAILABLE, refused_illegal=allowed)
    return Answer(committed=to_gate)


def may_pass(from_gate: str, to_gate: str, from_state: str, *,
             satisfied: set[str] | None = None,
             has_owner: bool = True) -> Answer:
    """May this passage be recorded?

    `satisfied` is the set of floor ids this record can point at something
    for — pointing at something, not asserting it. `has_owner` is whether an
    accountable role is named, which is the one thing Identify refuses on.

    A refused passage is not recorded. No field holds an attempt, and this
    returns a string rather than writing anything. It follows that there can
    be no finding whose trigger is "a passage was attempted and refused" —
    such a finding would read off state this application never stores.
    """
    legal = may_move(from_gate, to_gate, from_state)
    if not legal.ok:
        return legal

    satisfied = satisfied or set()

    # The refusals below are about *passing* a gate — moving on to the next
    # one in order. They checked every move out of the gate, so a project at
    # Deploy with its launch obligations unmet could not go back to Test
    # "where evidence failed", could not go back to Identify "where the
    # scrutiny level was wrong", and could not be retired at all: a tool that
    # failed its launch checks was held at Deploy with no way to send it back
    # or switch it off. None of those moves is "past Deploy", which is what
    # the refusal says it is refusing.
    passing = position(to_gate) == position(from_gate) + 1
    if not passing:
        return Answer(committed=to_gate)

    # Identify refuses on one obligation: a project with nobody's name
    # against it cannot be recorded as having passed. Every later gate reads
    # off who is accountable, and a record with nobody named gives those
    # gates nothing to read.
    if from_gate == IDENTIFY:
        named = has_owner and "floor.somebody_named" in satisfied
        if not named:
            return Answer(refused=REFUSE_IDENTIFY,
                          refused_illegal=legal_moves(from_gate, from_state))

    # Deploy refuses on six, and each has to be satisfiable by pointing at
    # something rather than by asserting it.
    if from_gate == DEPLOY:
        missing = [f for f in binding(DEPLOY, SATISFIED)
                   if f not in satisfied]
        if missing:
            return Answer(refused=REFUSE_DEPLOY,
                          refused_illegal=legal_moves(from_gate, from_state))

    return Answer(committed=to_gate)


def requires_passed(at_gate: str, needs: str) -> Answer:
    """Whether a record has got far enough for something to be asked of it.

    A different question from "may it move", and it needs its own sentence.
    Measure reads the baseline written at Procure; Sunset reads the terms
    recorded there. Asking a project for either before it has been through
    that gate is not an illegal move — nobody proposed a move — it is a
    surface reaching for evidence that does not exist yet.

    The gate name is filled into the reason rather than each surface writing
    its own, so "This has not passed Procure yet." reads identically
    wherever it comes from.
    """
    if position(at_gate) < 0 or position(needs) < 0:
        return Answer(refused=REFUSE_NOT_AVAILABLE)
    if before(at_gate, needs) or at_gate == needs:
        named = BY_GATE[needs].name
        return Answer(refused=REFUSE_NOT_PASSED.format(gate=named))
    return Answer(committed=needs)


def unmet(gate_id: str, satisfied: set[str] | None = None) -> tuple[str, ...]:
    """Binding floors this record cannot yet point at something for.

    Both senses, because a surface showing what is outstanding shows both —
    the ones that will refuse a passage and the ones that will produce a
    finding and let it through.
    """
    satisfied = satisfied or set()
    return tuple(f for f in BINDS.get(gate_id, {}) if f not in satisfied)


# ===========================================================================
# 5 · The gap record
# ===========================================================================

#: The four not-sure answers. A gap is an answer rather than an absence: a
#: field produces one where it carries a Module One question and the person
#: gave one of these to it. An optional field merely left untouched is not a
#: gap, produces no record and raises nothing — a surface that opened one for
#: every blank would make its own clean state unreachable.
NOT_SURE = ("We are not sure", "We don't know", "We have not asked",
            "Nobody has counted")


@dataclass
class Gap:
    """Every surface produces these and they must have one shape, because a
    gap on Data and a gap on Vendors end up in the same list."""

    #: The Module One question the answer was owed to. A gap with no question
    #: to name is not a valid gap.
    question: str
    field: str
    answer: str
    #: A role title, required. Never a blank, and never a person's name
    #: alone — a person leaves and the gap stays.
    owner: str
    by: str = "no date set"
    opened: str = ""
    closed: str | None = None

    def valid(self) -> tuple[bool, str]:
        if not str(self.question or "").strip():
            return False, ("A gap names the question its answer was owed "
                           "to. Without one it is a blank field, not a gap.")
        if not str(self.owner or "").strip():
            # Where the organisation cannot name one, the app offers the same
            # two-way choice Module One offers: handle it internally, or note
            # that outside help is needed. The second becomes a line in the
            # record.
            return False, ("A gap needs somebody to close it. Name the role, "
                           "or record that outside help is needed.")
        if self.answer not in NOT_SURE:
            return False, (f"A gap carries one of the four answers, not "
                           f"{self.answer!r}.")
        return True, ""

    def as_dict(self) -> dict[str, Any]:
        return {"question": self.question, "field": self.field,
                "answer": self.answer, "owner": self.owner, "by": self.by,
                "opened": self.opened, "closed": self.closed}


# ===========================================================================
# 6 · The recommendation
# ===========================================================================

#: A third object alongside the finding and the gap. A finding says something
#: contradicts what you decided. A gap says something is unanswered and names
#: who will answer it. A recommendation says what good practice would be here
#: and why, and it is the only one of the three that offers an opinion.
OFFERED = "offered"
ACCEPTED = "accepted"
DECLINED = "declined"
UNANSWERED = "not yet answered"
RECOMMENDATION_STATES = (OFFERED, ACCEPTED, DECLINED, UNANSWERED)

#: Where the reason comes from. "Module One recommended answer" outranks the
#: others: the framework's own recommended answers beat anything this
#: application would say on its own.
FROM_MODULE_ONE = "Module One recommended answer"
FROM_SEQUENCING = "sequencing"
FROM_COST = "cost"
FROM_EXPERIENCE = "experience"
BASES = (FROM_MODULE_ONE, FROM_SEQUENCING, FROM_COST, FROM_EXPERIENCE)


@dataclass
class Recommendation:
    id: str
    #: The surface and the gate it appears at.
    where: str
    says: str
    #: Required, never omitted. A recommendation with no reason is an
    #: instruction, and this application does not issue instructions. The
    #: reason is the part that persuades somebody to accept it.
    because: str
    basis: str = FROM_EXPERIENCE
    state: str = OFFERED
    #: Free text where the organisation chose otherwise. Never required —
    #: declining is a complete and legitimate answer, recorded without
    #: comment.
    declined_note: str = ""

    def valid(self) -> tuple[bool, str]:
        if not str(self.because or "").strip():
            return False, ("A recommendation carries its reason. Without one "
                           "it is an instruction.")
        if self.basis not in BASES:
            return False, f"{self.basis!r} is not one of {BASES}."
        if self.state not in RECOMMENDATION_STATES:
            return False, f"{self.state!r} is not a recommendation state."
        return True, ""

    def as_dict(self) -> dict[str, Any]:
        return {"id": self.id, "where": self.where, "says": self.says,
                "because": self.because, "basis": self.basis,
                "state": self.state, "declined_note": self.declined_note}


#: The recommendations the spine defines. A surface may add its own; it may
#: not redefine these.
RECOMMENDATIONS: tuple[Recommendation, ...] = (
    Recommendation(
        "rec.walk_hierarchy", IDENTIFY,
        "Walk the hierarchy before choosing",
        "Every vendor arrives claiming to be the answer to a problem nobody "
        "has defined yet. Working down from what you already have is what "
        "prevents the waste.", FROM_MODULE_ONE),
    Recommendation(
        "rec.record_holdings", IDENTIFY,
        "Record where your information lives, before it is needed",
        "Every later use case depends on knowing what you hold and whether a "
        "tool can reach it. Discovering the gap at Test costs more than "
        "recording it now.", FROM_SEQUENCING),
    Recommendation(
        "rec.fix_data_first", IDENTIFY,
        "Fix the underlying data first",
        "Where the data behind the work is incomplete, inconsistent or "
        "wrong, most other fixes underperform and some fail outright. This "
        "is sequencing rather than preference.", FROM_SEQUENCING),
    Recommendation(
        "rec.ask_another_unit", IDENTIFY,
        "Ask another unit before buying",
        "Most organizations do not realize the cross-utilization "
        "capabilities of the tools already in place — Module One, question "
        "8.6.", FROM_MODULE_ONE),
    Recommendation(
        "rec.baseline_first", PROCURE,
        "Write the baseline before you build or buy",
        "Measure can only compare against a number written before the "
        "change. A project that skips it has nothing to be judged by "
        "later.", FROM_SEQUENCING),
    Recommendation(
        "rec.no_training_term", PROCURE,
        "Require a term forbidding training on your information",
        "You can get your information back; you cannot get back what it "
        "taught their tool. At sunset there is nothing to return.",
        FROM_EXPERIENCE),
    Recommendation(
        "rec.staging_environment", PROCURE,
        "Require a staging or testing environment",
        "Vendors routinely omit it and charge for it afterward. An update "
        "that lands straight in production lands on the people doing the "
        "work, and retraining everybody costs more than the environment "
        "would have.", FROM_COST),
    Recommendation(
        "rec.notice_of_changes", PROCURE,
        "Require notice before changes go live",
        "Without it you learn that the tool changed by noticing that it "
        "behaves differently.", FROM_MODULE_ONE),
    Recommendation(
        "rec.try_the_update_first", TEST,
        "Try the update before it goes live",
        "The tool you approved in March behaves differently in September "
        "because somebody changed what is underneath it. An update that "
        "goes straight into production lands on the people doing the work, "
        "and retraining everybody after a bad release costs more than the "
        "testing environment would have.", FROM_EXPERIENCE),
)
BY_RECOMMENDATION: dict[str, Recommendation] = {
    r.id: r for r in RECOMMENDATIONS}


def recommendations_at(gate_id: str) -> tuple[Recommendation, ...]:
    return tuple(r for r in RECOMMENDATIONS if r.where == gate_id)


# ===========================================================================
# 7 · Shared findings
# ===========================================================================

#: Raised by more than one surface, so defined once. A surface adds its own
#: on top and must not redefine these.
#:
#: The sentences carry `[square brackets]` where the organisation's own
#: answer is read back inline. A finding is never raised against an external
#: standard, another organisation, or a benchmark — only against a
#: contradiction with what this organisation itself decided.
@dataclass(frozen=True)
class Finding:
    id: str
    raised_by: str
    trigger: str
    says: str


FINDINGS: tuple[Finding, ...] = (
    Finding("finding.no_owner", "Projects",
            "A project at Identify or beyond with no accountable role",
            "Nobody is named against this. Every tool needs a person, not a "
            "department."),
    Finding("finding.running_ahead", "Projects",
            "in_use = yes and gate earlier than Deploy",
            "This is in use today and has not passed Deploy."),
    Finding("finding.floor_missing", "Process",
            "A floor obligation that binds at this gate is unanswered",
            "You said [their answer]. This record does not have it yet."),
    Finding("finding.consulted_missing", "Oversight",
            "A party the organization said must be asked was not asked",
            "You said [party] has to be asked before approval. Nothing here "
            "records that."),
    Finding("finding.term_absent", "Vendors",
            "A required agreement term marked absent",
            "You require this term in every agreement. This one does not "
            "have it."),
    Finding("finding.never_category", "Data",
            "A holding the organization said never goes into a general tool "
            "is in scope",
            "You said never for [their category]. This use case reaches it."),
    Finding("finding.condition_overdue", "Projects",
            "A condition attached at a passage is past its date",
            "A condition on this is past its date: [condition], owned by "
            "[role]."),
    Finding("finding.review_overdue", "Integrity",
            "A Measure cycle is past the organization's own frequency for "
            "that level",
            "You said [frequency] at this level. The last look was [date]."),
    Finding("finding.gap_no_owner", "Projects",
            "A gap record without an owner",
            "This is recorded as unknown with nobody named to close it."),
    Finding("finding.framework_moved", "Oversight",
            "The framework changed and this project's answer moved with it",
            "Your framework changed under this one: [what moved]."),
    Finding("finding.description_stale", "Process",
            "The tool changed after the plain-language description was "
            "written",
            "This changed after somebody wrote the description of it."),
    Finding("finding.no_baseline", "Projects",
            "The project passed Procure with no baseline recorded",
            "There is no before-measurement on this. There is nothing for "
            "Measure to compare against."),
    Finding("finding.version_untracked", "Projects",
            "A vendor notification has no version record, or a version went "
            "live with no Test record",
            "The vendor changed this and nothing here records what changed "
            "or whether it was tried."),
)
BY_FINDING: dict[str, Finding] = {f.id: f for f in FINDINGS}

#: Two findings were deliberately not written, and this is where somebody
#: about to add them reads why.
#:
#: There is no finding whose trigger is a declined recommendation, and none
#: whose trigger is an organisation having no data classification scheme.
#: Both would punish a choice this application explicitly leaves open, and
#: adding either would make §2.11 and §8 of the spine untrue.
NOT_FINDINGS = (
    "a recommendation was declined",
    "the organization has no data classification scheme",
    "a passage was attempted and refused",
)

#: The clean state, on every surface. One sentence, shared, so that eleven
#: surfaces do not each invent their own way of saying nothing is wrong.
NOTHING_TO_FLAG = ("Nothing to flag — nothing you have recorded here "
                   "contradicts anything you decided in your framework.")

#: A shared bank of absence counters for stat rows. Take one; do not take one
#: another surface has taken.
ABSENCE_COUNTERS: tuple[str, ...] = (
    "Nobody named against it",
    "Where it lives is unknown",
    "Never checked",
    "Running ahead of its gates",
    "Waiting on somebody",
    "Recorded as unknown",
    "No before measurement",
    "Turned down and still on the list",
    "Changed by the vendor and never tried",
)


# ===========================================================================
# 8 · The three computed flags
# ===========================================================================

def running_ahead(in_use: str, gate_id: str) -> bool:
    """In use today, and not yet past Deploy.

    The most valuable single fact the app produces, and on the first day of
    a small organization's use it will be true of nearly everything. Show it
    as a count, never as an accusation — most organizations arriving here
    already run AI tools nobody approved, and no surface may treat that as a
    failure state.
    """
    return in_use == IN_USE_YES and before(gate_id, DEPLOY)


def conditions_open(conditions: list[dict[str, Any]] | None) -> bool:
    """One or more conditions attached at a passage, not yet closed.

    Conditions attach to a passage; they are not a state. A project can be
    running with conditions open, and pretending otherwise is how conditions
    get forgotten.
    """
    return any(not c.get("closed") for c in (conditions or []))


def version_pending(versions: list[dict[str, Any]] | None) -> bool:
    """A vendor notification has opened a version record that has not gone
    live or been closed as immaterial. The project keeps running on its
    current version while this is true; the flag says only that something is
    coming."""
    for row in versions or []:
        if row.get("live"):
            continue
        if str(row.get("material", "")).strip().lower() == "no":
            continue
        return True
    return False


def flags(record: dict[str, Any]) -> dict[str, bool]:
    """The three, for a record. Shared so eleven surfaces compute them once."""
    return {
        "running_ahead": running_ahead(str(record.get("in_use", "")),
                                       str(record.get("gate", ""))),
        "conditions_open": conditions_open(record.get("conditions")),
        "version_pending": version_pending(record.get("versions")),
    }


# ===========================================================================
# 9 · The role matrix
# ===========================================================================

#: Three roles are live and the app has a switcher between them. A role is a
#: hat: one person may wear several, and in a twelve-person water district
#: one person holding all three is the normal case.
#:
#: The authority that adopts the framework is a named party on the Govern
#: record rather than a fourth role with a login. It is frequently a board
#: that will never sign in.
OPERATOR = "operator"
TECHNOLOGY = "office_of_technology"
DECIDER = "decision_maker"
ROLES = (OPERATOR, TECHNOLOGY, DECIDER)

ROLE_NAMES = {
    OPERATOR: "Operator",
    TECHNOLOGY: "Office of Technology",
    DECIDER: "Decision-maker",
}

#: Proposing is open. Restricting who may write something down produces
#: organisations where nothing is written down. The one qualified entry is
#: holdings, which the Operator reads rather than writes.
MAY_PROPOSE: dict[str, dict[str, str]] = {
    "new_project": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "problem_definition": {OPERATOR: "yes", TECHNOLOGY: "yes",
                           DECIDER: "yes"},
    "hierarchy_verdict": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "scrutiny_level": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "holdings": {OPERATOR: "reads", TECHNOLOGY: "yes", DECIDER: "yes"},
    "registry_rows": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "vendor_entry": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "business_case": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "test_evidence": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "version_record": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "accessibility_check": {OPERATOR: "yes", TECHNOLOGY: "yes",
                            DECIDER: "yes"},
    "fallback_and_wording": {OPERATOR: "yes", TECHNOLOGY: "yes",
                             DECIDER: "yes"},
    "measure_cycle": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    # And so may anyone with no role at all. A reporting route that depends
    # on holding a hat is a reporting route people go around.
    "incident_report": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes",
                        "anyone": "yes"},
    "retirement": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "gap": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "answer_recommendation": {OPERATOR: "yes", TECHNOLOGY: "yes",
                              DECIDER: "yes"},
}

#: What each role may approve. Three values carry weight and are not the
#: same as "no":
#:
#: "delegated" — the Operator may, but only within the delegation the
#: organisation itself set. Where they said everything flows through the
#: decision-maker, the Operator approves nothing and the app never suggests
#: otherwise.
#:
#: "readiness" — the Office of Technology confirms technical or accessibility
#: readiness that the decision-maker's approval depends on, and only where
#: the organisation said technology has to be asked. It approves nothing on
#: its own. Where the organisation marked no technology function, these
#: confirmations do not exist and are never shown as missing.
#:
#: "proposes" — may put it forward, cannot settle it.
DELEGATED = "delegated"
READINESS = "readiness"
PROPOSES = "proposes"
THEIR_ANSWER = "their answer"

MAY_APPROVE: dict[str, dict[str, str]] = {
    # Govern is the only gate the project does not pass. The organisation
    # passes it, and the adopting authority is not one of these three hats.
    GOVERN: {OPERATOR: "no", TECHNOLOGY: "no", DECIDER: "no"},
    IDENTIFY: {OPERATOR: DELEGATED, TECHNOLOGY: "no", DECIDER: "yes"},
    PROCURE: {OPERATOR: DELEGATED, TECHNOLOGY: "no", DECIDER: "yes"},
    TEST: {OPERATOR: "no", TECHNOLOGY: READINESS, DECIDER: "yes"},
    DEPLOY: {OPERATOR: "no", TECHNOLOGY: READINESS, DECIDER: "yes"},
    "close_version_immaterial": {OPERATOR: "yes", TECHNOLOGY: "yes",
                                 DECIDER: "yes"},
    "measure_keep_as_is": {OPERATOR: "yes", TECHNOLOGY: "no", DECIDER: "yes"},
    "measure_pause_or_retire": {OPERATOR: PROPOSES, TECHNOLOGY: PROPOSES,
                                DECIDER: "yes"},
    "set_scrutiny_level": {OPERATOR: PROPOSES, TECHNOLOGY: PROPOSES,
                           DECIDER: "yes"},
    # A recorded governance decision with an owner and a date, versioned like
    # any other framework change. A weight never sits in a formula one person
    # can quietly edit.
    "set_ranking_weights": {OPERATOR: PROPOSES, TECHNOLOGY: PROPOSES,
                            DECIDER: "yes"},
    # A hat that may approve a passage may attach a condition to it. Without
    # that, a hat facing something missing can only refuse — and conditions
    # are the mechanism that keeps this application from blocking.
    "condition_on_own_passage": {OPERATOR: DELEGATED, TECHNOLOGY: DELEGATED,
                                 DECIDER: "yes"},
    "condition_on_any_passage": {OPERATOR: "no", TECHNOLOGY: "no",
                                 DECIDER: "yes"},
    "close_own_condition": {OPERATOR: "yes", TECHNOLOGY: "yes",
                            DECIDER: "yes"},
    "close_any_condition": {OPERATOR: "no", TECHNOLOGY: "no", DECIDER: "yes"},
    # Who may amend the framework is the organisation's answer, not this
    # document's. Module One asks it directly and the role table renders
    # whichever they chose.
    "framework_amendment": {OPERATOR: THEIR_ANSWER, TECHNOLOGY: THEIR_ANSWER,
                            DECIDER: THEIR_ANSWER},
}

#: Stopping a tool and retiring it are separate acts with separate authority.
#: Stopping is fast, reversible and available to anyone the organisation
#: trusted with it. Retiring is a decision with a records disposition
#: attached. A version retiring inside the loop is neither — it is
#: bookkeeping.
NAMED_STOPPER = "if the organization named them"

MAY_RETIRE: dict[str, dict[str, str]] = {
    "stop_immediately": {OPERATOR: NAMED_STOPPER, TECHNOLOGY: NAMED_STOPPER,
                         DECIDER: "yes"},
    "retire_version": {OPERATOR: "yes", TECHNOLOGY: "yes", DECIDER: "yes"},
    "propose_tool_retirement": {OPERATOR: "yes", TECHNOLOGY: "yes",
                                DECIDER: "yes"},
    "decide_tool_retirement": {OPERATOR: "no", TECHNOLOGY: "no",
                               DECIDER: "yes"},
    "carry_out_turn_off": {OPERATOR: "yes", TECHNOLOGY: "yes",
                           DECIDER: "yes"},
    "confirm_records_moved": {OPERATOR: "no", TECHNOLOGY: "yes",
                              DECIDER: "yes"},
    "close_sunset_record": {OPERATOR: "no", TECHNOLOGY: "no", DECIDER: "yes"},
}

#: Visibility is uniform. Every role sees every record, every field, every
#: gap, every finding, every recommendation and the whole audit trail. There
#: are no hidden fields and no private notes, and that is a decision worth
#: stating out loud: nearly every organisation using this is subject to open
#: records, and a field that presents itself as private is a trap for the
#: person who types in it.
#:
#: The only content not visible to everyone is a draft its author has not
#: submitted. A draft belongs to its author until submitted, and it is
#: destroyed rather than retained if abandoned.
EVERYONE_SEES_EVERYTHING = True


def may(what: str, role: str, *, table: dict[str, dict[str, str]] | None
        = None) -> str:
    """What this hat may do about `what`. Returns the raw answer.

    Deliberately returns the word rather than a boolean, because four of the
    answers are not yes or no. "Delegated", "readiness", "proposes" and
    "their answer" each mean a different thing, and collapsing them to
    True/False is how a surface ends up either blocking somebody the
    organization authorized or authorizing somebody it did not.
    """
    for source in (table, MAY_APPROVE, MAY_PROPOSE, MAY_RETIRE):
        if source and what in source:
            return source[what].get(role, "no")
    return "no"


# ===========================================================================
# 10 · One person, three hats
# ===========================================================================

#: Consecutive same-person steps collapse into one confirmation, and the
#: consequence is stated once, plainly, and then accepted. There is no second
#: warning, no repetition on the next record, and no block.
SAME_PERSON_NOTE = ("You are approving your own proposal. In an organization "
                    "this size that is ordinary, and it will be recorded "
                    "that way.")

#: Where a hat is held by nobody, its writes fold into the Decision-maker,
#: each carrying this standing note.
NO_TECHNOLOGY_NOTE = ("No technology function here; recorded by whoever "
                      "decides.")

#: Concentration is a count on Oversight, not a finding. There is no score,
#: no colour, and no advice to fix it — the organisation already told us its
#: size and its function map, and it does not need the implication explained
#: back to it. A finding is raised only where the organisation's own answer
#: said somebody else must be involved.
def concentration(hats_by_person: dict[str, list[str]]) -> str:
    """"Three of three roles held by one person." A count, and nothing else."""
    if not hats_by_person:
        return ""
    most = max(len(set(hats)) for hats in hats_by_person.values())
    return f"{most} of {len(ROLES)} roles held by one person"


# ===========================================================================
# 11 · The solution selection hierarchy
# ===========================================================================

@dataclass(frozen=True)
class Step:
    number: int
    name: str
    question: str
    answered_from: str


#: Walked at Identify, in order, every step given a verdict and a line of
#: reasoning. Recommended, never required: the organisation may walk it, skip
#: it, or record that it went straight to a vendor, and each of those is a
#: complete answer.
#:
#: Steps 2 and 3 are separate on purpose. A unit with a problem does not know
#: what the unit down the hall already owns, and collapsing the two into
#: "existing capability" loses the more valuable half.
HIERARCHY: tuple[Step, ...] = (
    Step(1, "Define the problem",
         "What is actually going wrong, and what is causing it",
         "the problem definition"),
    Step(2, "Fix it in house now",
         "Is there something we already run that resolves this today",
         "Registry"),
    Step(3, "Another business unit",
         "Does another unit inside this organization have something that "
         "would", "Registry"),
    Step(4, "Piggyback",
         "Is it available on another government's agreement, a cooperative "
         "purchase, or from a sister agency", "Registry, Module One 8.2"),
    Step(5, "Build it in house", "Can we build or configure it ourselves",
         "the organization's own function map"),
    Step(6, "An external vendor's tool",
         "Only after 2 through 5 are documented as inadequate",
         "Registry, then Vendors"),
)

#: Only two of the honest outcomes are technology. A surface that renders the
#: hierarchy as a route to a purchase has misread it.
HIERARCHY_OUTCOMES: tuple[str, ...] = (
    "Do nothing",
    "This is a process change, not a project",
    "Change a rule",
    "Standardize what comes in",
    "Train people",
    "Fix the underlying data",
    "Add staff",
    "Build or configure it ourselves",
    "Buy or acquire a tool",
)


# ===========================================================================
# 12 · Vocabulary the spine enforces
# ===========================================================================

#: Say tool. Never these in anything a user reads.
#:
#: "Deploy" is a gate name and the only sanctioned use of that root:
#: everywhere else in user-facing copy a tool *goes live* or is *in use*.
#: "Contract" means the procurement instrument and nothing else — never a
#: pattern, never a protocol, never a name for a specification. "Statute"
#: means an actual legislative enactment, and most of what this product
#: governs has none behind it.
BANNED_IN_COPY: tuple[str, ...] = (
    "model", "inference", "training data", "llm", "algorithm", "matrix",
    "deployment", "deployed", "machine learning",
)


def banned_in(text: str) -> list[str]:
    """The banned words in `text`, matched as words. A substring test read
    "fulfillment" and "enrollment" as containing "llm"; "models" and
    "algorithms" are still caught."""
    import re
    found = []
    for word in BANNED_IN_COPY:
        if re.search(rf"(?<![a-z]){re.escape(word)}s?(?![a-z])", text.lower()):
            found.append(word)
    return found

#: Never render a gate as a number. Numbered gates invite a reader to import
#: a staging scheme this platform did not write.
BANNED_GATE_FORMS: tuple[str, ...] = (
    "gate 1", "gate 2", "gate 3", "gate 4", "gate 5", "gate 6", "gate 7",
    "stage 1", "stage 2", "stage 3", "stage 4", "stage 5", "stage 6",
    "stage 7", "step 1 of 7", "phase 1", "phase 2",
)


def as_dict() -> dict[str, Any]:
    """The whole spine, for a surface or the browser to read once."""
    return {
        "gates": [{"id": g.id, "name": g.name, "turns_on": g.turns_on,
                   "owner": g.owner, "writes_from": list(g.writes_from),
                   "binds": BINDS.get(g.id, {})} for g in GATES],
        "states": [{"id": s.id, "shown_as": s.shown_as, "means": s.means}
                   for s in STATES],
        "floors": [{"id": f.id, "says": f.says} for f in FLOORS],
        "refusing_gates": list(REFUSING_GATES),
        "reasons": list(REASONS),
        "recommendations": [r.as_dict() for r in RECOMMENDATIONS],
        "findings": [{"id": f.id, "raised_by": f.raised_by,
                      "trigger": f.trigger, "says": f.says}
                     for f in FINDINGS],
        "absence_counters": list(ABSENCE_COUNTERS),
        "nothing_to_flag": NOTHING_TO_FLAG,
        "hierarchy": [{"number": s.number, "name": s.name,
                       "question": s.question,
                       "answered_from": s.answered_from} for s in HIERARCHY],
        "hierarchy_outcomes": list(HIERARCHY_OUTCOMES),
        "roles": [{"id": r, "name": ROLE_NAMES[r]} for r in ROLES],
        "not_sure_answers": list(NOT_SURE),
    }
