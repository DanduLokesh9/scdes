"""Lifecycle — how the seven steps work.

**This surface holds no records and writes nothing.** No table, no unit, no
state, no count, no date. It owns no gate. It is the page somebody reads
once and comes back to when they are stuck: what each step asks of them,
what has to exist before a project can leave it, and where the work is
actually done.

Every project lives on Projects, which holds the tracker, commits passages
and writes record state. This module points there constantly and does no
work of its own. Holding state here would create a second place for the
truth to live, and the two copies would disagree.

**The authority for all of this is the spine.** What follows is the
plain-language rendering. Where the two disagree the spine controls — which
is why the floors table below is derived from `spine.BINDS` rather than
typed out again.

**This is the page people will screenshot.** It will end up pasted into an
email to a director who has never opened this application, and it should
survive that with no context. No copy here may depend on the reader having
seen another screen.

If a ticket asks this page to store something, that ticket belongs to
Projects.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app import spine

#: Nothing. Stated as a value so that a test can hold it.
WRITES: tuple[str, ...] = ()
OWNS_NO_GATE = True
HOLDS_NO_RECORDS = True


# ===========================================================================
# 2 · The shape of the page
# ===========================================================================

#: One column, seven step blocks, in order, all expanded by default.
#:
#: Not an accordion that hides six of seven, not a carousel, and not a
#: numbered stepper that implies the reader is partway through something. A
#: person who lands here needs to scan the whole thing and then read one
#: part.
ALL_SEVEN_EXPANDED = True

NOT_THIS = ("an accordion that hides six of seven",
            "a carousel",
            "a numbered stepper implying the reader is partway through "
            "something")

#: Above the first step.
STANDING_PANEL = (
    "Where your work actually happens. Every project moves through these "
    "seven in order, and the tracker at the top right of each project shows "
    "you which one it is at and what it is waiting on. This page explains "
    "the steps; Projects is where you do them.")

#: The same five parts, in the same order, in every one of the seven blocks
#: — so that a reader who has understood one has understood all of them.
PARTS: tuple[tuple[str, str], ...] = (
    ("The name and the question",
     "The gate name, and the one question it exists to answer, in plain "
     "words."),
    ("What it asks of you",
     "What has to exist on paper before a project can leave, in the "
     "organization's own terms."),
    ("Who decides",
     "Read back from the organization's decision shape and delegation."),
    ("What holds people up here",
     "The two or three things that most commonly stall a project at this "
     "step, named honestly."),
    ("Where the work is done",
     "A link to the surface that owns the step, and to the tracker."),
)


# ===========================================================================
# 3 · The seven steps
# ===========================================================================

@dataclass(frozen=True)
class Step:
    gate: str
    #: The one question the step exists to answer.
    question: str
    #: The name-and-the-question copy, in full.
    says: str
    #: What has to exist on paper before a project can leave.
    asks: tuple[str, ...]
    #: Who decides, read back from their own decision shape.
    who_decides: str
    #: The two or three things that most commonly stall a project here.
    holds_people_up: tuple[str, ...]
    #: The surface that owns the step. Every line also links to the tracker.
    work_is_done_on: tuple[str, ...]
    #: The one thing about this step worth flagging, where there is one.
    flag: str = ""
    #: The framework questions this block reads back.
    reads_back: tuple[str, ...] = field(default_factory=tuple)

    @property
    def name(self) -> str:
        found = spine.BY_GATE.get(self.gate)
        return found.name if found else ""

    def as_dict(self) -> dict[str, Any]:
        return {"gate": self.gate, "name": self.name,
                "question": self.question, "says": self.says,
                "asks": list(self.asks), "who_decides": self.who_decides,
                "holds_people_up": list(self.holds_people_up),
                "work_is_done_on": list(self.work_is_done_on),
                "flag": self.flag, "reads_back": list(self.reads_back)}


STEPS: tuple[Step, ...] = (
    Step(
        spine.GOVERN,
        "Who decides, and under what rules?",
        "This one your organization passes, not your projects. You pass it "
        "once when you adopt your framework, and again whenever you change "
        "it. Every project after that inherits the pass and carries a note "
        "of which version of your rules it started under.",
        ("Your framework, adopted, with a date and the name of whoever "
         "adopted it.",
         "Who decides, by title.",
         "How many levels of scrutiny you have and what each one needs.",
         "Which internal functions exist here.",
         "Where decisions get written down."),
        "The authority you named as adopting the framework. That is "
        "frequently a board or a council who will never sign in to this "
        "application, and it is recorded by title rather than by name. "
        "Whoever you named as deciding day to day does not adopt the "
        "framework; they propose changes to it. Where you said your "
        "decision-maker may amend it alone, this page renders that instead, "
        "because it is your answer.",
        ("Waiting for a committee that does not exist.",
         "Assuming a council is required when one person by title is a "
         "complete answer.",
         "Leaving the tiebreaker unnamed."),
        ("Oversight",),
        reads_back=("who adopts it", "who decides, who sits in the seats, "
                    "who breaks a tie", "how many levels, and what each "
                    "level needs", "which functions exist here",
                    "where decisions get written down")),
    Step(
        spine.IDENTIFY,
        "Is the problem defined, and is there already something that solves "
        "it?",
        "Two halves. The first describes what is actually going wrong, "
        "without mentioning technology at all. The second looks for a "
        "solution, starting with what you already have and getting to "
        "buying something last. A great many projects end here, correctly, "
        "because the answer turned out to be a process change or a form.",
        ("The problem, described as what goes wrong, where, how often and "
         "at what cost.",
         "What you know separated from what you are assuming.",
         "What has already been tried.",
         "Then a verdict on each of the nine kinds of answer.",
         "Where the answer is technology, a verdict on each of the six "
         "places it could come from.",
         "Then somebody's name against it."),
        "Whoever you named as deciding. Where you set a delegation, the "
        "User may pass this gate within it and this page names your own "
        "limit back to you. Where you said everything flows through the "
        "decision-maker, the User proposes and nothing else.",
        ("Describing a solution instead of a problem, which is by far the "
         "most common.",
         "Nobody named as accountable.",
         "Not knowing what data the answer would need."),
        ("Projects",),
        flag="A project with no accountable name is the first of the two "
             "places this application declines to record a passage.",
        reads_back=("which contacts have to be named",
                    "which functions exist, which decides whether building "
                    "in house is available")),
    Step(
        spine.PROCURE,
        "How did you get it, on what terms, at what full cost, and measured "
        "against what?",
        "Procure means acquiring it, however you acquire it — including "
        "building it yourselves. What you are getting was already chosen at "
        "Identify; this is where you write down how you got it, what is "
        "actually in the agreement, what it costs across its whole life, "
        "and what the work looks like today so that somebody can tell later "
        "whether it helped.",
        ("How it arrived, one of five ways.",
         "Each term you said must be in every agreement, marked present or "
         "absent.",
         "The full cost on your own list of what counts as cost.",
         "Three things written at the same moment: the business case, the "
         "baseline, and where the measurement will come from."),
        "The same rule as Identify, against the same delegation. Where you "
        "named a purchasing function, this page names it here; where you "
        "said you have none, nothing routes to one and the absence is not "
        "shown as a defect.",
        ("A term you require that the vendor will not give.",
         "Nobody having written down what the work looks like today, which "
         "cannot be recovered later.",
         "A tool that arrived inside something you already owned, where "
         "there is no purchase to point at."),
        ("Vendors", "Projects"),
        flag="The gate still applies to that tool.",
        reads_back=("the terms you require in every agreement, in your "
                    "order", "what counts as cost",
                    "whether you write down a before measurement")),
    Step(
        spine.TEST,
        "What evidence is there that it does what it claims, and what was "
        "not tested?",
        "Try it somewhere that is not production. Write down what you tried "
        "it on, what you found, and — this is the part people skip — what "
        "you did not test and therefore do not know. An account with no "
        "limits in it is not accepted here.",
        ("What was tried, on what, over what period, by whom.",
         "Where it was tried, and whether that was a staging environment or "
         "production.",
         "What was found.",
         "What was not tested.",
         "The manual way to do the work without it, in writing."),
        "Whoever you named as deciding. Where you said the technology "
        "function has to be asked, the Office of Technology confirms "
        "technical readiness first, and that confirmation is what the "
        "decision depends on. Where you recorded no technology function, "
        "that confirmation does not exist and is never shown as missing.",
        ("No staging environment, because the vendor did not include one.",
         "A tool that cannot be tried on a small scale first.",
         "An account that says only what worked."),
        ("Integrity",),
        flag="Where a tool cannot be tried on a small scale, recording that "
             "fact raises the scrutiny level and does not waive the step.",
        reads_back=("what your scrutiny levels require",
                    "which tools need a written manual backup",
                    "the staging environment term")),
    Step(
        spine.DEPLOY,
        "Do the operating instructions exist, and can a person find them?",
        "One of the two steps where this application will decline to record "
        "a passage. Your framework has floors that bind at launch, and "
        "until each one can be satisfied by pointing at something rather "
        "than by asserting it, this will keep showing the project as "
        "running ahead of its gates.",
        ("Who makes the final call.",
         "Where the disclosure appears and in what exact wording.",
         "How a person reaches a person instead.",
         "The manual backup.",
         "Somebody's name.",
         "A plain-language description.",
         "Accessibility, where anything is public-facing.",
         "How to turn it off."),
        "Whoever you named as deciding. Where you said the technology "
        "function has to be asked, it confirms technical and accessibility "
        "readiness first. Everyone you said must be consulted is named "
        "here, drawn from your own function map.",
        ("Disclosure wording that has to be approved by somebody.",
         "The way a person reaches a person.",
         "Accessibility on a public-facing tool."),
        ("Process",),
        flag="The way a person reaches a person cannot be skipped, and many "
             "organizations have never written it down.",
        reads_back=("what counts as a final action",
                    "where disclosure appears, who approves the wording, "
                    "where the wording lives",
                    "how somebody reaches a person instead",
                    "the manual backup", "who has to be named",
                    "the plain-language description", "accessibility",
                    "what your scrutiny levels require")),
    Step(
        spine.MEASURE,
        "Is it still true?",
        "Where most projects live for years. On your own schedule, for that "
        "level of scrutiny, somebody looks at whether it is still doing "
        "what it was supposed to, measured against the number you wrote "
        "down before you started.",
        ("The measurement against the baseline.",
         "Whatever else you said you watch.",
         "Incidents since last time.",
         "Whether the fallback was tried.",
         "Whether the plain-language description is still true.",
         "A determination, defaulting to whatever you said happens when a "
         "tool is not delivering."),
        "Keeping a tool as it is can be the User's call. Pausing it, "
        "sending it back or retiring it is the decision-maker's. Anyone you "
        "named as able to stop a tool without waiting for a meeting can "
        "stop it alone, from here or from anywhere.",
        ("A baseline nobody wrote, so there is nothing to compare against.",
         "A measurement that cannot be taken again because the holding it "
         "came from is not reachable.",
         "A cycle that lapses without anyone noticing."),
        ("Integrity",),
        reads_back=("the before measurement", "what else you watch",
                    "how often the fallback is tried",
                    "the plain-language description",
                    "what happens if it is not delivering",
                    "how often you check, per level")),
    Step(
        spine.SUNSET,
        "Is it still worth keeping, and what happens to what it leaves "
        "behind?",
        "Two different things are called sunset. A version sunsets every "
        "time your vendor replaces it with a newer one, which is "
        "bookkeeping. The tool itself sunsets when you decide it is not "
        "worth keeping, which is a judgment against the reason you got it "
        "in the first place.",
        ("Which of your own triggers fired.",
         "Who decided.",
         "The notice you gave.",
         "What replaces it.",
         "What happened to the records and the information, confirmed "
         "rather than assumed.",
         "The final measurement against the baseline, kept whether the "
         "result is good or bad."),
        "Anyone may propose retirement. Only the decision-maker decides it, "
        "and only the decision-maker closes the record. Turning the tool "
        "off is separate from deciding to, and anyone may do that.",
        ("Nobody having said what happens to the records.",
         "An agreement with no term about returning and deleting.",
         "The discovery that a vendor trained on your information, which "
         "cannot be undone."),
        ("Projects", "Vision"),
        flag="Vision reads every tool sunset, because retiring something is "
             "a judgment against the reason it was bought.",
        reads_back=("your retirement triggers",
                    "who retires a tool, and what happens to the records "
                    "and data", "the notice period",
                    "the retention schedule",
                    "the baseline the final measurement runs against")),
)
BY_STEP: dict[str, Step] = {s.gate: s for s in STEPS}


def step(gate: str) -> Step | None:
    return BY_STEP.get(gate)


# ---------------------------------------------------------------------------
# 6 · Where the work is done, folded to the functions they have
# ---------------------------------------------------------------------------

#: Every link says where it goes, rather than "click here" or a bare arrow.
def where_the_work_is_done(gate: str, *,
                           folds_to: dict[str, str] | None = None) -> str:
    """The line under each step block.

    Where a function does not exist in the organization, the line names
    whoever holds that hat instead. **It never routes to an office the
    organization does not have.**
    """
    found = BY_STEP.get(gate)
    if not found:
        return ""
    folds_to = folds_to or {}
    named = [folds_to.get(surface, surface)
             for surface in found.work_is_done_on]
    return f"Where the work is done: {', '.join(named)}."


#: Where there is no technology function, the Identify block says building
#: in house is not available and echoes their own answer back.
NO_TECHNOLOGY_FUNCTION = (
    "You said you have no technology function here, so building it "
    "yourselves is not one of the places it could come from.")


# ===========================================================================
# 4 · The loop, explained
# ===========================================================================

#: A section of its own, because it is the part people do not expect.
LOOP = (
    "The seven steps are a circle, not a line.\n\n"
    "Most of what you run will sit at Measure for years. Then your vendor "
    "changes something underneath it — a new version, a different tool, a "
    "feature you did not ask for — and the tool you approved in March "
    "behaves differently in September.\n\n"
    "When that happens, the project goes back through Test and Deploy: you "
    "try the new version somewhere that is not production, you check the "
    "launch floors still hold, and when the new version goes live the one "
    "it replaced retires at that moment. The project does not start over. "
    "It keeps its whole history and gains a version.\n\n"
    "This is why your agreement should say two things: that they tell you "
    "before anything changes, and that you get somewhere to try it. Without "
    "the first you find out by noticing. Without the second the update "
    "lands on the people doing the work.")

LOOP_GOES_THROUGH = (spine.TEST, spine.DEPLOY)


def loop(*, vendor_without_notice: str = "") -> str:
    """Where the organization's agreement has no notice term, the section
    says so with the vendor named and links to Vendors, rather than leaving
    it as a general warning."""
    if not vendor_without_notice:
        return LOOP
    return (LOOP + f"\n\nYour agreement with {vendor_without_notice} has no "
                   f"term requiring notice before anything changes. That is "
                   f"written on the Vendors entry, and it is where it gets "
                   f"fixed.")


#: Rendered as a diagram only where a text version sits beside it, and the
#: text version is authoritative. A person using a screen reader gets the
#: same explanation in the same reading order. **A description of the
#: picture does not satisfy this.** Any diagram is decorative, marked as
#: such, and adds nothing the text does not carry.
TEXT_IS_AUTHORITATIVE = True
DIAGRAM_IS_DECORATIVE = True


# ===========================================================================
# 5.1 · The states a project can be in
# ===========================================================================

#: The eight states come from the spine, each with one plain sentence.
def states() -> list[dict[str, str]]:
    return [{"id": s.id, "shown_as": s.shown_as, "means": s.means}
            for s in spine.STATES]


#: The two facts that are not states and are frequently confused for them.
NOT_STATES: tuple[tuple[str, str], ...] = (
    ("Whether a tool is in use",
     "Independent of how far it has got in these steps."),
    ("Whether conditions are open",
     "Attaches to a passage rather than to a project."),
)

#: The one that needs explaining most. On the first day of most
#: organisations' use this is nearly everything they own, and the page says
#: so.
IN_USE_AND_EARLY = (
    "A tool can be in real use and still be early in these steps. On your "
    "first day that will be true of most of what you have, and it is the "
    "ordinary way this starts. It is a list to work through, not a list of "
    "mistakes.")


# ===========================================================================
# 5.2 · The three hats
# ===========================================================================

def hats() -> list[dict[str, str]]:
    """The three hats, named as the spine names them.

    This page's own prose calls the first one the User; the spine calls it
    the Operator. The spine controls, so the label comes from there and the
    two do not drift apart on a screen somebody screenshots.
    """
    return [{"id": role, "name": spine.ROLE_NAMES.get(role, role)}
            for role in spine.ROLES]


#: The paragraph appears for every organisation. Only its position changes
#: with headcount, following what is likely to be true of them.
ONE_PERSON_ALL_THREE = (
    "In an organization your size one person often wears all three hats. "
    "Nothing here requires a second signature you did not ask for. What it "
    "does is record which hat you were wearing each time, so that a year "
    "from now the history says what actually happened.")

#: Said plainly and without advice.
NO_ADVICE_ABOUT_CONCENTRATION = True


def hats_first(headcount: int = 0) -> bool:
    """Whether the one-person paragraph sits at the top of the item or
    further down. It appears either way."""
    return bool(headcount) and headcount < 25


# ===========================================================================
# 5.3 · The eight floors and where they come back
# ===========================================================================

#: Derived from the spine, so the table cannot drift from the rule it
#: describes. Where an organisation chose a lighter answer than the
#: framework recommended, their answer is shown without comment.
#:
#: This is the single most useful thing on the page for somebody who thinks
#: governance happens at purchase.
def floors() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for floor in spine.FLOORS:
        binds_at = [g for g in spine.GATE_ORDER
                    if floor.id in spine.BINDS.get(g, {})]
        rows.append({
            "id": floor.id,
            "says": floor.says,
            "set_at": spine.BY_GATE[binds_at[0]].name if binds_at else "",
            "comes_back_at": [spine.BY_GATE[g].name for g in binds_at[1:]],
            "refuses_at": [spine.BY_GATE[g].name for g in binds_at
                           if spine.BINDS[g].get(floor.id)
                           == spine.SATISFIED],
        })
    return rows


def why_the_floors_table() -> str:
    """The sentence above the table, with its numbers computed from the
    spine rather than typed.

    An earlier draft of this copy read "most of these come back more than
    once", which the spine's own table contradicts — most bind at exactly
    one gate. The point stands without the overstatement: the gates they
    bind at are mostly after the purchase.
    """
    rows = floors()
    again = sum(1 for r in rows if r["comes_back_at"])
    at_launch = len(spine.binding(spine.DEPLOY, spine.SATISFIED))
    return (f"These are not settled at purchase. {at_launch} of them have "
            f"to be satisfied before a tool goes live, and {again} are "
            f"checked again at a later step.")


# ===========================================================================
# 5.4 · Findings, gaps and recommendations
# ===========================================================================

#: Three objects, three plain sentences, because they look similar on screen
#: and mean different things.
THREE_OBJECTS: tuple[tuple[str, str], ...] = (
    ("A finding",
     "says something you recorded contradicts something you decided. It "
     "always quotes your own answer back at you."),
    ("A gap",
     "says something is not known yet, and names who is going to find out "
     "and by when. Recording a gap is an acceptable answer."),
    ("A recommendation",
     "says what good practice would be here, and why. It never stops you "
     "doing anything, and declining one is a complete answer that nothing "
     "will hold against you."),
)


# ===========================================================================
# 6 · Adaptive — the examples, by organisation type
# ===========================================================================

#: Where the type is unanswered the clause carrying the example is dropped
#: rather than filled with a word this application chose.
EXAMPLES: dict[str, str] = {
    "State agency or department": "permits",
    "County government": "permits",
    "Regional council, authority, or commission": "permits",
    "Special district": "work orders",
    "School district or education agency": "enrollment",
    "City, town, or village": "service calls",
}


def example_for(organisation_type: str = "") -> str:
    return EXAMPLES.get(organisation_type, "")


# ===========================================================================
# What this surface deliberately does not do
# ===========================================================================

WHAT_IT_DOES_NOT_DO = (
    "It does not track anything.",
    "It does not hold a record, a state, a count or a date.",
    "It does not rate progress or show a percentage complete.",
    "It does not tell an organization how long a step should take, because "
    "this application does not know.",
)

#: Where a read returns a gap rather than an answer, the gap renders with
#: its owner and a link to it. It is never filled in, and the section is
#: never hidden.
RENDER_THE_GAP = (
    "Where you answered that you are not sure, this page says so and links "
    "to the gap rather than filling it in.")

#: No number, no threshold, no default, anywhere on this page.
SUPPLIES_NO_NUMBER = True


def page(*, organisation_type: str = "", headcount: int = 0,
         folds_to: dict[str, str] | None = None,
         vendor_without_notice: str = "",
         has_technology_function: bool = True) -> dict[str, Any]:
    """The whole page, in one read. Nothing here is written anywhere."""
    blocks = []
    for found in STEPS:
        block = found.as_dict()
        block["where_the_work_is_done"] = where_the_work_is_done(
            found.gate, folds_to=folds_to)
        if found.gate == spine.IDENTIFY and not has_technology_function:
            block["adaptive"] = NO_TECHNOLOGY_FUNCTION
        blocks.append(block)

    return {
        "writes": list(WRITES),
        "owns_no_gate": OWNS_NO_GATE,
        "standing_panel": STANDING_PANEL,
        "parts": [{"part": p, "says": s} for p, s in PARTS],
        "steps": blocks,
        "loop": loop(vendor_without_notice=vendor_without_notice),
        "loop_goes_through": [spine.BY_GATE[g].name
                              for g in LOOP_GOES_THROUGH],
        "text_is_authoritative": TEXT_IS_AUTHORITATIVE,
        "states": states(),
        "not_states": [{"fact": f, "says": s} for f, s in NOT_STATES],
        "in_use_and_early": IN_USE_AND_EARLY,
        "hats": hats(),
        "one_person_all_three": ONE_PERSON_ALL_THREE,
        "hats_first": hats_first(headcount),
        "floors": floors(),
        "why_the_floors_table": why_the_floors_table(),
        "three_objects": [{"object": o, "says": s}
                          for o, s in THREE_OBJECTS],
        "example": example_for(organisation_type),
        "render_the_gap": RENDER_THE_GAP,
        "what_it_does_not_do": list(WHAT_IT_DOES_NOT_DO),
    }
