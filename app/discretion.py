"""The Discretion Register — what an agency actually gets to decide.

This implements the client's section-miner method. The insight it rests on is
worth stating because it shapes everything below: **do not hunt for questions.**
Classify every sentence first, because the sentence type determines whether
there is a question at all, and what kind.

The five tests, applied sentence by sentence
--------------------------------------------

``SWAP``      Would a different agency need a different value here?
              → **IDENTITY**. A fill-in, not a discussion.

``CITE``      Does it invoke an external authority?
              → **CITATION**. The question is not "do you like this" but "which
              instruments bind *you*, and what re-checks the list when they
              move?" Carries a refresh trigger.

``TUNE``      Is there a number, list, degree, or default rule?
              → **POSTURE**. Confirmable, with the default stated.

``VOICE``     Is it aspiration or self-description?
              → **ASPIRATION**. Genuinely theirs, and the answer propagates
              into tone everywhere.

``STRIKE``    Could this be deleted without breaking the architecture? If not,
              → **STRUCTURAL**. No question — but the register says so out
              loud, because "not configurable, and here is why" is what earns
              trust in the blanks that *are* configurable.

``TIME-BOUND`` sits alongside: true as of a date, and will decay. Also carries
a refresh trigger.

Two rules the miner must not break
----------------------------------

**Never invent alternatives.** Questions are framed neutrally with the reference
setting as the visible default. Offering three made-up options where the source
offers one is how a template starts writing an agency's policy for it.

**Bundle related sentences.** Several sentences that configure the same fact are
one question, not four. A busy executive answering the same thing four times
stops reading.

What falls out is uneven by design: narrative sections mine into fill-ins and
posture confirmations; the appendices mine into numeric calibrations. Same five
tests, different output mix — which is the argument for classifying first.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict, field
from typing import Any

#: The six classifications. STRUCTURAL is the only one that yields no question.
CLASSIFICATIONS = {
    "IDENTITY": "An agency-specific fact. A different agency needs a different "
                "value.",
    "CITATION": "An external authority is invoked. Which instruments bind you, "
                "and what re-checks the list when they change?",
    "POSTURE": "A chosen default, degree or rule that could be set otherwise.",
    "ASPIRATION": "A value or ambition. Genuinely the agency's to decide.",
    "TIME-BOUND": "True as of a date, and will decay.",
    "STRUCTURAL": "Load-bearing architecture. Changing it breaks the framework.",
}

#: How an answer is given. Kept small on purpose — every extra control type is
#: another thing a busy executive has to work out how to operate.
FORMATS = {
    "fill-in": "Free text, short. A name, a title, an instrument.",
    "select": "Choose one of the stated options.",
    "confirm-default": "Keep the reference setting, or say what yours is.",
    "text": "A sentence or two in the agency's own words.",
    "accept-risk": "A choice the agency may make, where moving off the default "
                   "gives something up. The consequence is stated and has to be "
                   "accepted explicitly before the answer is taken.",
}

#: Numeric sections — risk weights, thresholds, timings — mine into calibrations
#: rather than fill-ins, and they are still `confirm-default`. Never sliders.
#:
#: The client's call, and the right one: a slider invites fiddling with numbers
#: that carry real consequences, and the method already says to show the
#: reference setting as the visible default. Someone who wants a different
#: threshold can type it and say why; someone who does not should not be
#: presented with a control that implies they ought to be adjusting it.
NUMERIC_ANSWER_FORMAT = "confirm-default"

#: Who should answer. The framework establishes four roles; "any" means it does
#: not matter who, only that it is recorded.
ANSWERERS = ("Management", "Legal", "Technology", "Council", "any")


@dataclass
class RegisterRow:
    """One decision an agency has to make — or one that is not theirs to make."""
    key: str
    classification: str
    #: The exact phrase from the source that triggered the test. Quoted so the
    #: user can see what in their own document prompted the question.
    source_phrase: str
    #: In the user's words, answerable without reading the framework.
    question: str = ""
    answer_format: str = "text"
    answers: str = "any"
    #: Every other place in the corpus this value appears or implies. The key
    #: field: one answer flows to many places, and that is what makes the
    #: register worth keeping rather than a form.
    propagates: list[str] = field(default_factory=list)
    #: The reference setting, shown as the visible default. Never invented.
    default: str = ""
    #: Stated options where the source itself offers them. Empty otherwise —
    #: the miner does not manufacture choices.
    options: list[str] = field(default_factory=list)
    #: What event should re-open this answer. CITATION and TIME-BOUND only.
    refresh_trigger: str = ""
    #: STRUCTURAL only: why this is not configurable.
    why_fixed: str = ""
    #: What moving off the default gives up, in plain words. Shown prominently,
    #: not in a footnote — this is the whole point of allowing the choice.
    warning: str = ""
    #: Claims elsewhere in the framework that stop being true if they move off
    #: the default. Named specifically, because "there are risks" is not a
    #: consequence anybody can weigh.
    abrogates: list[str] = field(default_factory=list)

    @property
    def configurable(self) -> bool:
        return self.classification != "STRUCTURAL"

    @property
    def requires_acceptance(self) -> bool:
        """Whether the answer needs an explicit "we accept this" to be taken.

        Only where a stated protection is given up. Attaching it to everything
        would train people to click through it, which is worse than not having
        it at all.
        """
        return bool(self.warning or self.abrogates)

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "configurable": self.configurable,
                "requires_acceptance": self.requires_acceptance}


@dataclass
class SectionRegister:
    number: str
    title: str
    #: One line on what this section does, for the module header.
    purpose: str
    rows: list[RegisterRow] = field(default_factory=list)
    #: Set when the section has not yet been mined, so the interface can say so
    #: rather than presenting an empty section as a finished one.
    mined: bool = True

    @property
    def questions(self) -> list[RegisterRow]:
        return [r for r in self.rows if r.configurable]

    @property
    def structural(self) -> list[RegisterRow]:
        return [r for r in self.rows if not r.configurable]

    def as_dict(self) -> dict[str, Any]:
        return {
            "number": self.number, "title": self.title, "purpose": self.purpose,
            "mined": self.mined,
            "question_count": len(self.questions),
            "structural_count": len(self.structural),
            "rows": [r.as_dict() for r in self.rows],
        }


# ===========================================================================
# Section 1 — Purpose
#
# Encoded from the client's own worked example, so the implementation can be
# checked against the method rather than taken on trust. Eight questions and one
# structural note, exactly as the method produced.
# ===========================================================================

SECTION_1 = SectionRegister(
    number="1", title="Purpose",
    purpose="Establishes what the framework is for, whose it is, what binds it, "
            "and the tone everything downstream inherits.",
    rows=[
        RegisterRow(
            key="agency.identity",
            classification="IDENTITY",
            source_phrase="The South Carolina Department of Environmental "
                          "Services … within the South Carolina Department of "
                          "Environmental Services (Agency)",
            question="What is your agency's full name, short name, and what "
                     "kind of agency are you?",
            answer_format="fill-in",
            answers="Management",
            propagates=["Every document header", "the risk framing that calls "
                        "you a 'state environmental regulatory agency'",
                        "naming rules throughout the corpus",
                        "Appendix C registry entries"],
            default="South Carolina Department of Environmental Services · "
                    "SCDES · state environmental regulatory agency",
        ),
        RegisterRow(
            key="adoption.instrument",
            classification="IDENTITY",
            source_phrase="a determination by Agency leadership",
            question="Who is adopting this — title and name — and by what "
                     "instrument (directive, charter, memo)?",
            answer_format="fill-in",
            answers="Management",
            propagates=["The adoption memo", "the charter",
                        "the signature block on every generated draft",
                        "Appendix M table of authorities"],
            default="Agency leadership, by adoption directive and signed "
                    "council charter",
        ),
        RegisterRow(
            key="state.strategy",
            classification="CITATION",
            source_phrase="South Carolina State Agencies Artificial "
                          "Intelligence Strategy, published in June 2024 … five "
                          "guiding principles",
            question="What statewide AI policy or strategy binds your agency, "
                     "and what are its principles?",
            answer_format="confirm-default",
            answers="Legal",
            propagates=["The principles crosswalk in Section 4",
                        "public-facing summaries",
                        "Appendix M table of authorities"],
            default="SC State Agencies AI Strategy (June 2024, SC Department of "
                    "Administration) — safely and securely, fairly and "
                    "objectively, ethically, transparently, beneficially",
            refresh_trigger="When the statewide strategy is reissued, or at "
                            "annual review",
        ),
        RegisterRow(
            key="federal.requirements",
            classification="CITATION",
            source_phrase="Office of Management and Budget Memorandum M-25-21 "
                          "and the National Institute of Standards and "
                          "Technology AI Risk Management Framework as of the "
                          "date of adoption",
            question="Which federal requirements apply to you, and who "
                     "re-checks this list when they change?",
            answer_format="confirm-default",
            answers="Legal",
            propagates=["Section 9 legal and federal programme compliance",
                        "Appendix M table of authorities",
                        "the annual review agenda"],
            default="OMB M-25-21 and the NIST AI Risk Management Framework",
            refresh_trigger="On federal reissuance, or at annual review — "
                            "whichever comes first",
        ),
        RegisterRow(
            key="conflict.rule",
            classification="POSTURE",
            source_phrase="Where this framework imposes requirements more "
                          "stringent than state or federal policy, the more "
                          "stringent standard controls.",
            question="When your rules and state or federal rules conflict, the "
                     "reference framework defaults to whichever is stricter. "
                     "Keep that?",
            answer_format="confirm-default",
            answers="Legal",
            propagates=["Every compliance determination",
                        "Section 9", "gate review checklists"],
            default="The more stringent standard controls",
        ),
        RegisterRow(
            key="agency.why",
            classification="ASPIRATION",
            source_phrase="ethical, responsible, and efficient … feel "
                          "confident that we are putting our best faith "
                          "efforts into this endeavor",
            question="In one or two sentences, why is YOUR agency doing this? "
                     "What should the public believe about your use of AI?",
            answer_format="text",
            answers="Management",
            propagates=["Every public-facing summary", "the annual public AI "
                        "report", "the tone of the whole document"],
            default="To support the ethical, responsible, and efficient "
                    "deployment of this technology for our employees and the "
                    "citizens we serve.",
        ),
        RegisterRow(
            key="model.ambition",
            classification="ASPIRATION",
            source_phrase="to serve as a model to others",
            question="Is being a model for other agencies an explicit goal, or "
                     "would you prefer quieter framing?",
            answer_format="select",
            answers="Management",
            options=["State it explicitly as a goal",
                     "Quieter framing — focus on our own operations",
                     "Leave it out"],
            propagates=["The closing of Section 1",
                        "external communications"],
            default="State it explicitly as a goal",
        ),
        RegisterRow(
            key="nascency.framing",
            classification="TIME-BOUND",
            source_phrase="As of the date of adoption, artificial intelligence "
                          "is a nascent and emerging technology",
            question="This framing dates itself deliberately. What triggers a "
                     "refresh — annual review, or a Council call?",
            answer_format="select",
            answers="Council",
            options=["Annual review", "A Council call at any time",
                     "Both — annual, and on request"],
            propagates=["Section 1", "the annual review agenda",
                        "the version history"],
            default="Annual review",
            refresh_trigger="Annual review of the framework",
        ),
        RegisterRow(
            key="framework.manual.split",
            classification="STRUCTURAL",
            source_phrase="Where this framework states a rule, the Operations "
                          "Manual states how the rule is carried out. The "
                          "Operations Manual is owned by the AI Governance "
                          "Council.",
            why_fixed="The framework/manual split and Council ownership of the "
                      "manual are the architecture. The framework holds rules; "
                      "the manual holds procedure and can be updated without "
                      "amending the rules. Collapse the two and every "
                      "operational tweak becomes a framework amendment.",
        ),
    ],
)


# ===========================================================================
# Section 2 — Scope
# ===========================================================================

SECTION_2 = SectionRegister(
    number="2", title="Scope",
    purpose="Fixes what the framework covers, what it deliberately does not, "
            "and who decides the edge cases.",
    rows=[
        RegisterRow(
            key="scope.units",
            classification="IDENTITY",
            source_phrase="all programs, bureaus, and offices within SCDES",
            question="What are your organisational units called, and does this "
                     "cover all of them?",
            answer_format="fill-in",
            answers="Management",
            propagates=["Section 2", "the accountability roster",
                        "Appendix C registry ownership fields"],
            default="All programs, bureaus, and offices",
        ),
        RegisterRow(
            key="scope.acquisition",
            classification="POSTURE",
            source_phrase="developed internally … procured from external "
                          "vendors, embedded within third-party platforms, or "
                          "acquired through cooperative purchasing agreements, "
                          "multi-state contracts, or platform upgrades",
            question="The reference scope catches AI however it arrives — "
                     "built, bought, embedded in something else, or arriving in "
                     "an upgrade you did not ask for. Keep all of those?",
            answer_format="confirm-default",
            answers="Legal",
            propagates=["Procurement (Step 3)", "vendor disclosure Appendix E",
                        "the intake form Appendix G"],
            default="All routes in scope, including platform upgrades",
        ),
        RegisterRow(
            key="scope.exclusions",
            classification="POSTURE",
            source_phrase="conventional statistical analysis … deterministic "
                          "automation … routine data analytics tools",
            question="Three things are expressly excluded: conventional "
                     "statistics, fixed-rule automation, and dashboards without "
                     "prediction. Are those the right exclusions for you?",
            answer_format="confirm-default",
            answers="Technology",
            propagates=["Section 2", "the intake screening questions",
                        "Appendix A use case taxonomy"],
            default="Excluded: conventional statistical analysis (e.g. SAS), "
                    "deterministic automation (e.g. form workflows), routine "
                    "analytics without predictive or generative capability "
                    "(e.g. Power BI)",
        ),
        RegisterRow(
            key="scope.arbiter",
            classification="IDENTITY",
            source_phrase="the Chief Technology Officer (CTO) shall make the "
                          "determination, subject to AI Governance Council's "
                          "review",
            question="When it is unclear whether a tool is in scope, who "
                     "decides — and who reviews that decision?",
            answer_format="fill-in",
            answers="Management",
            propagates=["Section 2", "the governance structure in Section 6",
                        "gate review checklists"],
            default="The Chief Technology Officer decides, subject to Council "
                    "review",
        ),
        RegisterRow(
            key="scope.future",
            classification="STRUCTURAL",
            source_phrase="The scope applies to future-developed technology "
                          "not yet conceived.",
            why_fixed="Scope that only covers today's techniques is obsolete "
                      "the moment something new arrives. Naming techniques as "
                      "examples while binding the category is what keeps the "
                      "framework from needing an amendment per innovation.",
        ),
    ],
)


# ===========================================================================
# Section 3 — Definitions
#
# Mined at the client's direction after a specific ruling. The reference text
# says "No autonomous decision system is authorized", and the first read of that
# was STRUCTURAL — architecture, not a choice. The client's answer was that it is
# configurable:
#
#   "It's configurable. If an agency wants that, they are free to do so, but
#    then their claims of human in authority are abrogated. I would put a big
#    warning and accept risk to proceed flag if they don't want that
#    capability. (note: the goal is to encourage the human in authority, but
#    they get to choose their direction; they do not get to choose if the
#    framework is a public document)"
#
# That draws the line precisely, and it is a better line than the one the miner
# guessed. What an agency does with its own AI is the agency's to decide, and a
# framework that forbids what an agency has already chosen to do is a framework
# they will quietly ignore. What is *not* theirs to decide is whether the choice
# is visible. Hence: the autonomy rule is POSTURE with a stated consequence, and
# publication is STRUCTURAL.
# ===========================================================================

SECTION_3 = SectionRegister(
    number="3", title="Definitions",
    purpose="Fixes the meaning of terms the whole corpus depends on, and states "
            "which systems are prohibited outright.",
    rows=[
        RegisterRow(
            key="definitions.autonomous",
            classification="POSTURE",
            source_phrase="No autonomous decision system is authorized. A human "
                          "with authority must review and be accountable for "
                          "any decision affecting a member of the public, a "
                          "regulated entity, or an employee.",
            question="Must a person with authority review every AI-influenced "
                     "decision that affects the public, a regulated entity or "
                     "an employee — or may some decisions be made by the system "
                     "alone?",
            answer_format="accept-risk",
            answers="Management",
            options=[
                "A person reviews and is accountable for every such decision",
                "Some decisions may be made by the system alone, with the "
                "consequence accepted below",
            ],
            default="A person reviews and is accountable for every such decision",
            propagates=["Section 3", "Section 4 operating principles",
                        "the intake screening questions",
                        "Appendix B risk factors — reversibility and "
                        "public-facing", "gate review checklists",
                        "the public-facing framework document"],
            warning="Allowing decisions to be made without a person in "
                    "authority is a choice your agency may make, and this "
                    "platform will not stop you. It cannot be made quietly. "
                    "Every claim your framework makes about human "
                    "accountability stops being true at the same moment, and "
                    "those claims are removed from your published document "
                    "rather than left standing beside a practice that "
                    "contradicts them.",
            abrogates=[
                "\u201cA human with authority must review and be accountable for "
                "any decision affecting a member of the public, a regulated "
                "entity, or an employee\u201d — Section 3",
                "The human-in-authority operating principle — Section 4",
                "Any statement to the public that a person reviews decisions "
                "affecting them — Section 10",
            ],
        ),
        RegisterRow(
            key="definitions.publication",
            classification="STRUCTURAL",
            source_phrase="This framework is a public document.",
            why_fixed="An agency chooses its own direction on AI. It does not "
                      "choose whether that direction is visible. A governance "
                      "framework the public cannot read is not governance, it "
                      "is an internal preference — and the accountability every "
                      "other section rests on comes from the document being "
                      "readable by the people it affects. This is the one thing "
                      "in Section 3 that is not on the table.",
        ),
    ],
)


# ===========================================================================
# Sections 4–13
#
# Mined the same way as the first three: every `source_phrase` below is quoted
# from the reference framework, and no option is offered that the source does
# not itself put on the table.
#
# One correction carried into these. The client read Section 3 and said its
# questions were reading as operational rather than definitional — asking what
# an agency should *do* rather than what its framework *says*. The distinction
# matters because this register produces a document, not a task list, and a
# question phrased as an instruction produces a sentence nobody can adopt. So
# these ask what the agency's own framework establishes, and the operational
# consequence is left to the Operations Manual, which is where the source
# itself keeps putting it.
# ===========================================================================

SECTION_4 = SectionRegister(
    number="4", title="Operating Principles",
    purpose="The binding principles every deployment must satisfy, and what "
            "happens when one cannot be met.",
    rows=[
        RegisterRow(
            key="principles.binding",
            classification="POSTURE",
            source_phrase="All AI activity within SCDES shall adhere to the "
                          "following binding principles.",
            question="Are your operating principles binding on every AI "
                     "deployment, or guidance a project may depart from?",
            answer_format="confirm-default",
            answers="Management",
            options=["Binding — a deployment that cannot satisfy one does not "
                     "proceed without a documented exception",
                     "Guidance — projects are expected to follow them and are "
                     "not blocked"],
            default="Binding — a deployment that cannot satisfy one does not "
                    "proceed without a documented exception",
            propagates=["Section 4", "the gate review checklists",
                        "Appendix H requirement text",
                        "the exception route below"],
        ),
        RegisterRow(
            key="principles.exception",
            classification="IDENTITY",
            source_phrase="unless the AI Governance Council grants a documented "
                          "exception with conditions, a remediation timeline, or "
                          "explicit acceptance of the documented risks",
            question="Who may grant an exception when a deployment cannot meet "
                     "one of your principles?",
            answer_format="fill-in",
            answers="Management",
            default="The body that holds the decision",
            propagates=["Section 4", "who decides",
                        "the exception record in the audit trail",
                        "gate review escalation"],
        ),
        RegisterRow(
            key="principles.list",
            classification="IDENTITY",
            source_phrase="Accessibility. Continuity. Data Security and "
                          "Cybersecurity. Data Stewardship. Fiscal "
                          "Responsibility. Human Accountability. "
                          "Interoperability. Measurable Value. Mission "
                          "Alignment. Non-Discrimination. Risk Management. "
                          "Transparency.",
            question="Which principles does your framework bind itself to? The "
                     "reference set is listed — add, remove or rename to match "
                     "what your agency will actually stand behind.",
            answer_format="fill-in",
            answers="Management",
            default="Accessibility, Continuity, Data Security and "
                    "Cybersecurity, Data Stewardship, Fiscal Responsibility, "
                    "Human Accountability, Interoperability, Measurable Value, "
                    "Mission Alignment, Non-Discrimination, Risk Management, "
                    "Transparency",
            propagates=["Section 4", "the published framework document",
                        "gate review checklists",
                        "the annual review criteria"],
        ),
        RegisterRow(
            key="principles.continuity",
            classification="POSTURE",
            source_phrase="Every AI deployment shall be accompanied by "
                          "documented manual fallback procedures. No AI "
                          "deployment may create a dependency that the Agency "
                          "cannot exit.",
            question="Must every deployment have a documented way of working "
                     "without it?",
            answer_format="accept-risk",
            answers="Technology",
            options=["Yes — a documented manual fallback for every deployment",
                     "Only where the system is judged critical",
                     "No standing requirement"],
            default="Yes — a documented manual fallback for every deployment",
            propagates=["Section 4", "Appendix G intake questions",
                        "gate review checklists", "the sunset conditions"],
            warning="Without a fallback, an agency cannot leave a supplier or "
                    "survive an outage. This is the principle that turns a "
                    "vendor problem into a service problem.",
            abrogates=["“No AI deployment may create a dependency that the "
                       "Agency cannot exit” — Section 4"],
        ),
        RegisterRow(
            key="principles.security_authority",
            classification="IDENTITY",
            source_phrase="The substantive security determination rests within "
                          "the Office of the CTO under the authority of the "
                          "Chief Information Security and Data Officer (CISDO).",
            question="Who makes the security determination for an AI system in "
                     "your organisation?",
            answer_format="fill-in",
            answers="Technology",
            default="The officer accountable for information security",
            propagates=["Section 4", "Section 8 data governance",
                        "the accountability roster",
                        "Appendix D data readiness sign-off"],
        ),
        RegisterRow(
            key="principles.measurable_value",
            classification="TIME-BOUND",
            source_phrase="Systems that cannot demonstrate measurable value at "
                          "annual review are subject to suspension or sunset.",
            question="How often is a system asked to show it is still worth "
                     "running, and what happens if it cannot?",
            answer_format="select",
            answers="Management",
            options=["Annually — suspension or sunset if it cannot",
                     "Annually — reported, with no automatic consequence",
                     "At each gate only"],
            default="Annually — suspension or sunset if it cannot",
            refresh_trigger="The review interval passes",
            propagates=["Section 4", "Section 12 sunset conditions",
                        "the oversight schedule", "Appendix J evaluation"],
        ),
        RegisterRow(
            key="principles.accessibility_law",
            classification="CITATION",
            source_phrase="in compliance with Title II of the ADA, Section 504 "
                          "and Section 508 of the Rehabilitation Act, and later "
                          "adopted rules or regulations regarding accessibility",
            question="Which accessibility law binds your organisation?",
            answer_format="fill-in",
            answers="Legal",
            default="Title II of the ADA, Section 504 and Section 508 of the "
                    "Rehabilitation Act",
            refresh_trigger="The cited authority is amended or replaced",
            propagates=["Section 4", "Section 10 accessibility compliance",
                        "the public disclosure wording"],
        ),
        RegisterRow(
            key="principles.human_authority_scope",
            classification="POSTURE",
            source_phrase="Final decision authority for all regulatory "
                          "determinations, enforcement actions, and public-facing "
                          "services rests with qualified Agency personnel.",
            question="Which kinds of decision must always end with a qualified "
                     "person rather than the system?",
            answer_format="fill-in",
            answers="Legal",
            default="Regulatory determinations, enforcement actions, and "
                    "public-facing services",
            propagates=["Section 4", "Section 3 autonomous decisions",
                        "Section 10 the right to human review",
                        "Appendix B reversibility scoring"],
        ),
    ],
)


SECTION_5 = SectionRegister(
    number="5", title="Authorized Use Case Structure",
    purpose="Which categories of use are permitted, and the conditions "
            "attached to each.",
    rows=[
        RegisterRow(
            key="usecase.categories",
            classification="IDENTITY",
            source_phrase="Category 1: Internal Service Optimization and "
                          "Efficiency. Category 2: Measurable Public or Economic "
                          "Benefit. Category 3: Innovation and Transformational "
                          "Applications.",
            question="What are your categories of authorised AI use called, and "
                     "what does each cover?",
            answer_format="fill-in",
            answers="Management",
            default="1 — Internal service optimisation and efficiency; "
                    "2 — Measurable public or economic benefit; "
                    "3 — Innovation and transformational applications",
            propagates=["Section 5", "Appendix A use case taxonomy",
                        "the intake screening", "Section 10 bias screening "
                        "scope", "Appendix C registry category field"],
        ),
        RegisterRow(
            key="usecase.review_category1",
            classification="POSTURE",
            source_phrase="Human technical review is mandatory for all outputs, "
                          "including those affecting regulatory determinations.",
            question="For your lowest-risk category, is human review of outputs "
                     "mandatory or discretionary?",
            answer_format="confirm-default",
            answers="Management",
            options=["Mandatory for all outputs",
                     "Mandatory only where a regulatory determination is "
                     "affected",
                     "At the project sponsor's discretion"],
            default="Mandatory for all outputs",
            propagates=["Section 5", "Section 4 human accountability",
                        "gate review checklists"],
        ),
        RegisterRow(
            key="usecase.new_category",
            classification="IDENTITY",
            source_phrase="The AI Governance Council may adopt new categories "
                          "that are consistent with the purpose outlined above "
                          "and must be supported by a documented Council "
                          "rationale.",
            question="Who may add a new category of authorised use?",
            answer_format="fill-in",
            answers="Council",
            default="The body that holds the decision",
            propagates=["Section 5", "who decides",
                        "the amendment route", "the decision log"],
        ),
        RegisterRow(
            key="usecase.new_category_rationale",
            classification="POSTURE",
            source_phrase="must be supported by a documented Council rationale",
            question="Must a written rationale accompany a new category?",
            answer_format="confirm-default",
            answers="Council",
            options=["Yes — recorded with the decision",
                     "No — the decision alone is enough"],
            default="Yes — recorded with the decision",
            propagates=["Section 5", "the decision log", "the audit trail"],
        ),
    ],
)


SECTION_6 = SectionRegister(
    number="6", title="Governance Structure",
    purpose="Who holds the decision, what they own, and how it is taken.",
    rows=[
        RegisterRow(
            key="governance.composition",
            classification="IDENTITY",
            source_phrase="The Council consists of four standing members: the "
                          "Agency Director, who serves as Council Chair; the "
                          "CTO; and two executive-level delegates appointed by "
                          "the Director",
            question="Who holds the decision in your organisation, and who sits "
                     "with them?",
            answer_format="fill-in",
            answers="Management",
            # The source's own answer, de-branded rather than dropped. Naming
            # SCDES's four seats would be pre-loading somebody else's structure;
            # showing the shape they took is the reference setting, which is
            # what a default is for.
            default="The head of the organisation as chair, the technology "
                    "officer, and two executive delegates they appoint",
            propagates=["Section 6", "who decides", "the capacity picker",
                        "Appendix N operating procedures",
                        "every gate that routes a decision"],
        ),
        RegisterRow(
            key="governance.duties",
            classification="POSTURE",
            source_phrase="approval, modification, or rejection of project "
                          "proposals at each phase of a project’s lifecycle; "
                          "assignment and validation of risk classifications; "
                          "authorization of pilots and operational deployments; "
                          "ongoing monitoring of system performance and "
                          "compliance; and suspension of systems when warranted",
            question="What is the deciding body actually responsible for?",
            answer_format="fill-in",
            answers="Management",
            default="Approving, modifying or rejecting proposals at each phase; "
                    "assigning and validating risk classifications; authorising "
                    "pilots and deployments; monitoring performance and "
                    "compliance; suspending systems when warranted",
            propagates=["Section 6", "the gate map", "Appendix H checklists",
                        "the decision log"],
        ),
        RegisterRow(
            key="governance.amendment",
            classification="POSTURE",
            source_phrase="Amendments to this framework require Council input "
                          "and are subject to the Agency Director’s approval.",
            question="How is this framework amended, and whose approval "
                     "finishes it?",
            answer_format="fill-in",
            answers="Council",
            default="Input from the deciding body, and the approval of the "
                    "head of the organisation",
            propagates=["Section 6", "the amendment route",
                        "the mode transition", "version adoption"],
        ),
        RegisterRow(
            key="governance.program_roles",
            classification="IDENTITY",
            source_phrase="Each AI project shall designate four individuals "
                          "responsible for program-level accountability: a "
                          "project sponsor within the operating program; an "
                          "identified contact in the Office of Technology and "
                          "Information Services; an identified contact in the "
                          "Finance office; and an identified contact in the "
                          "Office of General Counsel.",
            question="Which roles must every AI project name before it starts?",
            answer_format="fill-in",
            answers="Management",
            default="A project sponsor, a technology contact, a finance "
                    "contact, and a legal contact",
            propagates=["Section 6", "Appendix G intake form fields",
                        "Appendix C registry ownership",
                        "the accountability roster"],
        ),
        RegisterRow(
            key="governance.role_consolidation",
            classification="POSTURE",
            source_phrase="Detailed role definitions and consolidation rules are "
                          "set forth in the SCDES AI Operations Manual.",
            question="May one person hold more than one of those roles on the "
                     "same project?",
            answer_format="select",
            answers="Management",
            options=["Yes — a small unit may consolidate them",
                     "Yes, except the sponsor and the legal contact",
                     "No — four separate people"],
            default="Yes — a small unit may consolidate them",
            propagates=["Section 6", "Appendix G intake validation",
                        "the accountability roster"],
        ),
        RegisterRow(
            key="governance.escalation",
            classification="POSTURE",
            source_phrase="escalate concerns to leadership and to the Council "
                          "when appropriate",
            question="When must a project's named roles escalate rather than "
                     "resolve something themselves?",
            answer_format="text",
            answers="Management",
            default="To leadership, and to the body that holds the decision, "
                    "when appropriate",
            propagates=["Section 6", "Section 11 incident escalation",
                        "the gate review path"],
        ),
        RegisterRow(
            key="governance.decision_body_exists",
            classification="STRUCTURAL",
            source_phrase="The AI Governance Council is the principal "
                          "consultative and decision-making authority for all AI "
                          "activity within SCDES.",
            why_fixed="Something has to hold the decision. Whether that is a "
                      "standing body of four or a single officer is entirely "
                      "yours to choose — and the application asks you that "
                      "question directly rather than assuming a Council. What "
                      "is not on the table is nobody holding it: every gate, "
                      "every exception and every suspension in the sections "
                      "below routes to this answer, and a framework with no "
                      "decision-maker cannot say who approved anything.",
        ),
    ],
)


SECTION_7 = SectionRegister(
    number="7", title="Risk Management Policy",
    purpose="How risk is classified, re-checked, and what each band requires.",
    rows=[
        RegisterRow(
            key="risk.dimensions",
            classification="POSTURE",
            source_phrase="a weighted, multi-factor assessment matrix evaluating "
                          "no less than six dimensions of risk: regulatory "
                          "impact, public-facing exposure, data sensitivity, "
                          "reversibility, community impact, and federal program "
                          "nexus",
            question="Which dimensions does your risk assessment weigh?",
            answer_format="fill-in",
            answers="Management",
            default="Regulatory impact, public-facing exposure, data "
                    "sensitivity, reversibility, community impact, and federal "
                    "program nexus",
            propagates=["Section 7", "Appendix B risk classification matrix",
                        "the risk engine", "Appendix G intake questions",
                        "the live consequence preview"],
        ),
        RegisterRow(
            key="risk.tiers",
            classification="IDENTITY",
            source_phrase="The classification produces one of three tiers: Low, "
                          "Moderate, or High.",
            question="What are your risk tiers called?",
            answer_format="fill-in",
            answers="Management",
            default="Low, Moderate, High",
            propagates=["Section 7", "Appendix B thresholds",
                        "the gate map", "Appendix C registry risk field",
                        "every screen that shows a band"],
        ),
        RegisterRow(
            key="risk.single_high",
            classification="POSTURE",
            source_phrase="Projects scoring High in any single factor require AI "
                          "Governance Council review with heightened scrutiny.",
            question="What happens when a project scores at the top of any one "
                     "dimension?",
            answer_format="confirm-default",
            answers="Council",
            options=["Review by the deciding body, with heightened scrutiny",
                     "Review by the deciding body, ordinary scrutiny",
                     "No automatic consequence — the composite score decides"],
            default="Review by the deciding body, with heightened scrutiny",
            propagates=["Section 7", "Appendix B rules", "the gate map",
                        "the risk engine"],
        ),
        RegisterRow(
            key="risk.two_highs",
            classification="POSTURE",
            source_phrase="Projects scoring High in two or more factors are "
                          "classified as High Risk regardless of composite score "
                          "and require independent review in addition to Council "
                          "review. This requirement prevents averaging from "
                          "concealing a serious risk concentration.",
            question="Should two top scores force the highest tier even when the "
                     "average does not?",
            answer_format="accept-risk",
            answers="Council",
            options=["Yes — two or more force the highest tier regardless of "
                     "the composite, plus independent review",
                     "Yes — force the highest tier, no independent review",
                     "No — the composite score alone decides"],
            default="Yes — two or more force the highest tier regardless of "
                    "the composite, plus independent review",
            propagates=["Section 7", "Appendix B rules", "the risk engine",
                        "the gate map"],
            warning="This rule exists to stop averaging from hiding a "
                    "concentration of risk. Removing it means a project can be "
                    "seriously exposed on two dimensions and still score as "
                    "moderate overall.",
            abrogates=["“This requirement prevents averaging from concealing a "
                       "serious risk concentration” — Section 7"],
        ),
        RegisterRow(
            key="risk.reassessment",
            classification="TIME-BOUND",
            source_phrase="Risk classification shall be reassessed at each stage "
                          "of any AI project and annually for all production "
                          "systems.",
            question="When is a risk classification re-checked?",
            answer_format="select",
            answers="Management",
            options=["At each stage, and annually once in production",
                     "At each stage only",
                     "Annually only"],
            default="At each stage, and annually once in production",
            refresh_trigger="The review interval passes",
            propagates=["Section 7", "the oversight schedule",
                        "the gate map", "Appendix C registry review dates"],
        ),
        RegisterRow(
            key="risk.methodology_owner",
            classification="IDENTITY",
            source_phrase="The detailed scoring methodology, weighting factors, "
                          "threshold ranges, and reassessment procedure are "
                          "established by the Council and set forth in the SCDES "
                          "AI Operations Manual.",
            question="Who sets the scoring methodology, and can it be changed "
                     "without amending this framework?",
            answer_format="fill-in",
            answers="Council",
            default="The deciding body, recorded in the operations manual "
                    "rather than in the framework",
            propagates=["Section 7", "the mode transition",
                        "who may tune the risk model", "the audit trail"],
        ),
        RegisterRow(
            key="risk.registry_required",
            classification="POSTURE",
            source_phrase="No AI system may operate within SCDES without a "
                          "current entry in the Registry, and any AI system "
                          "discovered operating without registration constitutes "
                          "Shadow AI in violation of this framework.",
            question="May an AI system operate before it is on your register?",
            answer_format="accept-risk",
            answers="Technology",
            options=["No — an unregistered system is in violation",
                     "Yes, during evaluation only",
                     "No standing rule"],
            default="No — an unregistered system is in violation",
            propagates=["Section 7", "Appendix C registry",
                        "the intake gate", "the oversight sweep"],
            warning="The register is what makes oversight possible at all. "
                    "Without this rule there is no way to know what is running, "
                    "and nothing else in this section can be enforced.",
            abrogates=["“No AI system may operate within SCDES without a "
                       "current entry in the Registry” — Section 7"],
        ),
    ],
)


SECTION_8 = SectionRegister(
    number="8", title="Data Governance",
    purpose="Who controls the data, what a supplier may do with it, and what "
            "they may not.",
    rows=[
        RegisterRow(
            key="data.control",
            classification="POSTURE",
            source_phrase="The State of South Carolina retains control of its "
                          "data at all times, and no AI system may use, retain, "
                          "or repurpose state data in a manner that is "
                          "inconsistent with this section.",
            question="Who retains control of your data once it is inside an AI "
                     "system?",
            answer_format="fill-in",
            answers="Legal",
            default="The organisation retains control at all times",
            propagates=["Section 8", "Section 4 data stewardship",
                        "Appendix E vendor disclosure",
                        "the mandatory contract provisions"],
        ),
        RegisterRow(
            key="data.package_reviewers",
            classification="IDENTITY",
            source_phrase="a complete data documentation package shall be "
                          "prepared, reviewed by General Counsel and the CISDO, "
                          "and approved before the project advances past initial "
                          "consideration",
            question="Who has to review the data documentation before a project "
                     "goes further?",
            answer_format="fill-in",
            answers="Legal",
            default="The legal officer and the officer accountable for "
                    "information security",
            propagates=["Section 8", "Appendix D data readiness",
                        "the gate map", "the accountability roster"],
        ),
        RegisterRow(
            key="data.package_timing",
            classification="POSTURE",
            source_phrase="approved before the project advances past initial "
                          "consideration",
            question="At what point must that review be finished?",
            answer_format="select",
            answers="Management",
            options=["Before the project advances past initial consideration",
                     "Before a pilot begins",
                     "Before production deployment"],
            default="Before the project advances past initial consideration",
            propagates=["Section 8", "the gate map",
                        "Appendix H gate review checklists"],
        ),
        RegisterRow(
            key="data.procurement_precedence",
            classification="CITATION",
            source_phrase="Where this framework imposes requirements more "
                          "stringent than State Procurement or OTIS, the more "
                          "stringent standard controls; where State Procurement "
                          "or OTIS impose requirements more stringent than this "
                          "framework, those requirements control.",
            question="Which external procurement or technology authorities must "
                     "your AI contracts satisfy in addition to this framework?",
            answer_format="fill-in",
            answers="Legal",
            default="The state procurement authority, and the state technology "
                    "authority that reviews technology contracts",
            refresh_trigger="The cited authority changes its requirements",
            propagates=["Section 8", "Section 2 the conflict rule",
                        "the procurement workflow",
                        "Appendix E vendor disclosure"],
        ),
        RegisterRow(
            key="data.substitution",
            classification="POSTURE",
            source_phrase="Material modification of any AI component, including "
                          "substitution of the underlying foundation model, "
                          "embedding model, retrieval components, safety or "
                          "content filters, fine-tuning datasets, or prompt and "
                          "orchestration logic, constitutes a substitution",
            question="What counts as a change big enough to require re-approval "
                     "of a supplier's system?",
            answer_format="fill-in",
            answers="Technology",
            default="Substituting the foundation model, embedding model, "
                    "retrieval components, safety or content filters, "
                    "fine-tuning datasets, or prompt and orchestration logic",
            propagates=["Section 8", "Section 12 reconstruction obligation",
                        "the vendor re-evaluation trigger",
                        "Appendix E disclosure tiers"],
        ),
        RegisterRow(
            key="data.disclosure_tiers",
            classification="POSTURE",
            source_phrase="Disclosure obligations are graduated by tier "
                          "reflecting the criticality of the AI system and the "
                          "degree of public or regulatory exposure its outputs "
                          "create.",
            question="Are supplier disclosure obligations the same for every "
                     "system, or graduated by exposure?",
            answer_format="confirm-default",
            answers="Legal",
            options=["Graduated by criticality and public or regulatory "
                     "exposure",
                     "The same for every system"],
            default="Graduated by criticality and public or regulatory exposure",
            propagates=["Section 8", "Appendix E vendor disclosure",
                        "the procurement workflow"],
        ),
    ],
)


SECTION_9 = SectionRegister(
    number="9", title="Legal and Federal Program Compliance",
    purpose="How delegated programmes and legal obligations constrain AI use, "
            "and what AI output is and is not.",
    rows=[
        RegisterRow(
            key="legal.evaluation_scope",
            classification="POSTURE",
            source_phrase="applicable state and federal statutes and "
                          "regulations; the requirements specific to any "
                          "delegated federal program implicated by the use case; "
                          "the due process implications; the Freedom of "
                          "Information Act and public records implications; and "
                          "the litigation exposure and defensibility",
            question="What must the legal review of an AI project cover?",
            answer_format="fill-in",
            answers="Legal",
            default="Applicable statutes and regulations; any delegated "
                    "programme implicated; due process implications; public "
                    "records and disclosure implications; litigation exposure "
                    "and defensibility",
            propagates=["Section 9", "Appendix G intake questions",
                        "the gate map", "Appendix M table of authorities"],
        ),
        RegisterRow(
            key="legal.delegated_programs",
            classification="IDENTITY",
            source_phrase="AI use in delegated programs shall not jeopardize "
                          "delegation status.",
            question="Which delegated or externally authorised programmes does "
                     "your organisation run that AI must not put at risk?",
            answer_format="fill-in",
            answers="Legal",
            # Not a list — the list is the agency's and cannot be guessed. This
            # states the reference position, which is that such programmes
            # exist and are in scope, so an agency with none says so explicitly
            # rather than leaving the question looking unanswered.
            default="Any federally delegated or externally authorised "
                    "programme this organisation administers",
            propagates=["Section 9", "Appendix B federal program nexus factor",
                        "the risk engine", "Section 11 incident notification"],
        ),
        RegisterRow(
            key="legal.signature",
            classification="POSTURE",
            source_phrase="AI-generated documents used in enforcement or "
                          "permitting shall be reviewed and signed by authorized "
                          "personnel. AI output alone does not constitute Agency "
                          "action.",
            question="Does AI output ever constitute an action of your "
                     "organisation on its own?",
            answer_format="accept-risk",
            answers="Legal",
            options=["No — a person with authority reviews and signs",
                     "Yes, for defined low-consequence output"],
            default="No — a person with authority reviews and signs",
            propagates=["Section 9", "Section 3 autonomous decisions",
                        "Section 10 the administrative record",
                        "gate review checklists"],
            warning="A determination that cannot be attributed to a responsible "
                    "person is the one your source calls vulnerable to "
                    "challenge — and where a delegated programme is involved, "
                    "the delegation itself is what is exposed.",
            abrogates=["“AI output alone does not constitute Agency action” — "
                       "Section 9"],
        ),
        RegisterRow(
            key="legal.records_status",
            classification="CITATION",
            source_phrase="AI-generated content, including permits, reports, "
                          "correspondence, analyses, and any other document "
                          "produced with AI assistance, is a state record "
                          "subject to the applicable records retention schedule.",
            question="Under which records schedule does AI-assisted content "
                     "fall in your organisation?",
            answer_format="fill-in",
            answers="Legal",
            default="The applicable records retention schedule, regardless of "
                    "how much AI was involved",
            refresh_trigger="The records schedule is revised",
            propagates=["Section 9", "Section 12 retention after retirement",
                        "the export and archive rules"],
        ),
        RegisterRow(
            key="legal.output_ownership",
            classification="POSTURE",
            source_phrase="SCDES retains ownership of all outputs generated "
                          "using state data, regardless of the AI tool used to "
                          "produce them.",
            question="Who owns the outputs produced from your data?",
            answer_format="confirm-default",
            answers="Legal",
            options=["The organisation, whichever tool produced them",
                     "Determined contract by contract"],
            default="The organisation, whichever tool produced them",
            propagates=["Section 9", "Section 8 supplier contracts",
                        "Appendix E vendor disclosure"],
        ),
        RegisterRow(
            key="legal.ip_opinions",
            classification="IDENTITY",
            source_phrase="General Counsel is responsible for providing binding "
                          "legal opinions on intellectual property matters as "
                          "they arise.",
            question="Who gives the binding opinion when an intellectual "
                     "property question arises?",
            answer_format="fill-in",
            answers="Legal",
            default="The legal officer",
            propagates=["Section 9", "the accountability roster",
                        "the escalation path"],
        ),
        RegisterRow(
            key="legal.authorship_disclosure",
            classification="POSTURE",
            source_phrase="AI-generated content shall not be represented as "
                          "original human authorship without disclosure of AI "
                          "involvement.",
            question="Must AI involvement be disclosed when content is "
                     "presented as someone's work?",
            answer_format="confirm-default",
            answers="Legal",
            options=["Yes — disclosed",
                     "Only where the output is public-facing"],
            default="Yes — disclosed",
            propagates=["Section 9", "Section 10 public disclosure",
                        "the published framework document"],
        ),
    ],
)


SECTION_10 = SectionRegister(
    number="10", title="Transparency and Public Accountability",
    purpose="What the public is told, when, through what channel — and what "
            "they may ask for.",
    rows=[
        RegisterRow(
            key="transparency.administrative_record",
            classification="POSTURE",
            source_phrase="The role of the AI system shall be documented in the "
                          "administrative record for any permitting decision, "
                          "compliance determination, or enforcement action.",
            question="Must the role AI played be written into the record of a "
                     "decision?",
            answer_format="confirm-default",
            answers="Legal",
            options=["Yes — for every determination of this kind",
                     "Only where AI materially influenced the outcome",
                     "No standing requirement"],
            default="Yes — for every determination of this kind",
            propagates=["Section 10", "Section 9 defensibility",
                        "the decision record fields", "the audit trail"],
        ),
        RegisterRow(
            key="transparency.public_disclosure",
            classification="POSTURE",
            source_phrase="Public-facing AI tools shall include clear disclosure "
                          "that AI is being used, stated in terms a member of "
                          "the public can understand.",
            question="Are people told when they are dealing with an AI system?",
            answer_format="accept-risk",
            answers="Management",
            options=["Yes — clear disclosure, in plain terms",
                     "Only on request",
                     "No standing requirement"],
            default="Yes — clear disclosure, in plain terms",
            propagates=["Section 10", "the public-facing wording",
                        "Appendix F community impact screening"],
            warning="Undisclosed AI in a public service is the single fastest "
                    "way to lose the public trust every other section is trying "
                    "to build.",
            abrogates=["“Public-facing AI tools shall include clear disclosure "
                       "that AI is being used” — Section 10"],
        ),
        RegisterRow(
            key="transparency.human_contact",
            classification="POSTURE",
            source_phrase="Human contact options shall remain available for all "
                          "Agency services and shall be accessible to persons "
                          "with disabilities.",
            question="Can someone always reach a person instead?",
            answer_format="confirm-default",
            answers="Management",
            options=["Yes — for all services",
                     "Yes — for public-facing services only"],
            default="Yes — for all services",
            propagates=["Section 10", "Section 4 accessibility",
                        "the public-facing wording"],
        ),
        RegisterRow(
            key="transparency.right_to_review",
            classification="POSTURE",
            source_phrase="Any regulated entity may request human review of any "
                          "AI-influenced determination as a matter of right.",
            question="Who may demand that a person re-examine an AI-influenced "
                     "determination, and is it a right or a discretion?",
            answer_format="fill-in",
            answers="Legal",
            default="Any affected party, as a matter of right",
            propagates=["Section 10", "Section 4 human accountability",
                        "the appeal route", "the published framework document"],
        ),
        RegisterRow(
            key="transparency.appeal_meaningful",
            classification="POSTURE",
            source_phrase="these mechanisms shall provide a meaningful "
                          "opportunity for review by a qualified human, not "
                          "merely a recirculation through the same AI process",
            question="Must an appeal reach a person, rather than the same system "
                     "a second time?",
            answer_format="confirm-default",
            answers="Legal",
            options=["Yes — a qualified person, not the same process again",
                     "A re-run of the process is sufficient"],
            default="Yes — a qualified person, not the same process again",
            propagates=["Section 10", "the appeal route",
                        "Section 4 human accountability"],
        ),
        RegisterRow(
            key="transparency.working_notes",
            classification="POSTURE",
            source_phrase="individual staff communications within an AI platform "
                          "unshared to others, provided the AI exchange is not "
                          "relied upon as the basis for an Agency action and the "
                          "user's working notes are not introduced into the "
                          "administrative record, are considered personal "
                          "working notes",
            question="Is a member of staff's unshared exchange with an AI tool a "
                     "record of the organisation, or a personal working note?",
            answer_format="select",
            answers="Legal",
            options=["A personal working note, while unshared and not relied "
                     "upon",
                     "A record of the organisation in every case"],
            default="A personal working note, while unshared and not relied "
                    "upon",
            propagates=["Section 10", "Section 9 records status",
                        "the retention rules"],
        ),
        RegisterRow(
            key="transparency.annual_report",
            classification="TIME-BOUND",
            source_phrase="SCDES shall publish an annual public report on AI "
                          "systems in use, their purposes, and aggregate "
                          "performance metrics",
            question="How often do you publish what AI you are using, and what "
                     "does that report contain?",
            answer_format="fill-in",
            answers="Management",
            default="Annually — the systems in use, their purposes, and "
                    "aggregate performance",
            refresh_trigger="The reporting period ends",
            propagates=["Section 10", "the oversight schedule",
                        "Appendix C registry as the source"],
        ),
        RegisterRow(
            key="transparency.bias_screening_scope",
            classification="POSTURE",
            source_phrase="All Category 2 and Category 3 use cases shall include "
                          "an impact screening before deployment.",
            question="Which categories of use require an impact screening before "
                     "deployment?",
            answer_format="fill-in",
            answers="Management",
            default="Every category above the lowest",
            propagates=["Section 10", "Section 5 categories",
                        "Appendix F community impact screening",
                        "the gate map"],
        ),
        RegisterRow(
            key="transparency.bias_found",
            classification="POSTURE",
            source_phrase="Where bias is detected, the system shall be suspended "
                          "pending remediation unless the Council approves "
                          "continued use with documented mitigations and a "
                          "remediation timeline",
            question="What happens when bias is found in a running system?",
            answer_format="accept-risk",
            answers="Council",
            options=["Suspended pending remediation, unless the deciding body "
                     "approves continued use with documented mitigations",
                     "Continued use with mitigations, reported to the deciding "
                     "body",
                     "Recorded and addressed at the next review"],
            default="Suspended pending remediation, unless the deciding body "
                    "approves continued use with documented mitigations",
            propagates=["Section 10", "Section 11 suspension",
                        "Appendix F screening", "the oversight schedule"],
            warning="Anything weaker than suspension means a system known to be "
                    "producing biased outcomes goes on producing them while the "
                    "remediation is scheduled.",
            abrogates=["“the system shall be suspended pending remediation” — "
                       "Section 10"],
        ),
        RegisterRow(
            key="transparency.accessibility_standard",
            classification="TIME-BOUND",
            source_phrase="establishes WCAG 2.1 Level AA as the mandatory "
                          "technical standard for all government web content and "
                          "mobile applications, with compliance required by "
                          "April 24, 2027, or later amended date",
            question="Which accessibility standard applies to your public-facing "
                     "systems, and by when?",
            answer_format="fill-in",
            answers="Technology",
            default="WCAG 2.1 Level AA, by 24 April 2027 or a later amended "
                    "date",
            refresh_trigger="The compliance date passes or the standard is "
                            "amended",
            propagates=["Section 10", "Section 4 accessibility",
                        "the public-facing systems checklist"],
        ),
    ],
)


SECTION_11 = SectionRegister(
    number="11", title="Incident Response",
    purpose="Incident levels, who is notified, in what time, and what stops.",
    rows=[
        RegisterRow(
            key="incident.separate_protocol",
            classification="POSTURE",
            source_phrase="The Agency shall therefore maintain a dedicated AI "
                          "incident response protocol distinct from general IT "
                          "incident response.",
            question="Is your AI incident procedure separate from general IT "
                     "incident response, or the same one?",
            answer_format="confirm-default",
            answers="Technology",
            options=["Separate — an AI error is not an outage",
                     "The same procedure, with AI-specific severity levels",
                     "The same procedure"],
            default="Separate — an AI error is not an outage",
            propagates=["Section 11", "Appendix L incident report",
                        "the oversight register"],
        ),
        RegisterRow(
            key="incident.levels",
            classification="IDENTITY",
            source_phrase="The protocol shall classify AI-related incidents by "
                          "severity. All Level 2 and Level 3 incidents shall be "
                          "reported to the AI Governance Council.",
            question="What are your incident severity levels called?",
            answer_format="fill-in",
            answers="Technology",
            default="Level 1, Level 2, Level 3",
            propagates=["Section 11", "Appendix L incident report",
                        "Section 10 accessibility failures",
                        "the notification thresholds below"],
        ),
        RegisterRow(
            key="incident.council_threshold",
            classification="POSTURE",
            source_phrase="All Level 2 and Level 3 incidents shall be reported "
                          "to the AI Governance Council.",
            question="At which severity does an incident reach the deciding "
                     "body?",
            answer_format="fill-in",
            answers="Management",
            default="The middle level and above",
            propagates=["Section 11", "who decides",
                        "the escalation path", "the decision log"],
        ),
        RegisterRow(
            key="incident.executive_threshold",
            classification="POSTURE",
            source_phrase="All Level 3 incidents shall additionally be reported "
                          "to executive leadership and referred to the Office of "
                          "General Counsel for evaluation.",
            question="At which severity does an incident reach executive "
                     "leadership and the legal officer?",
            answer_format="fill-in",
            answers="Management",
            default="The highest level",
            propagates=["Section 11", "the escalation path",
                        "the accountability roster"],
        ),
        RegisterRow(
            key="incident.stages",
            classification="POSTURE",
            source_phrase="graduated procedures for detection, suspension, "
                          "notification, root-cause analysis, lookback review, "
                          "and resumption",
            question="What stages does your incident procedure require?",
            answer_format="fill-in",
            answers="Technology",
            default="Detection, suspension, notification, root-cause analysis, "
                    "lookback review, and resumption",
            propagates=["Section 11", "Appendix L incident report fields",
                        "the oversight register"],
        ),
        RegisterRow(
            key="incident.external_notification",
            classification="IDENTITY",
            source_phrase="the Office of the CTO and the Office of General "
                          "Counsel shall jointly determine whether notification "
                          "to the applicable federal regional office is required",
            question="Who decides whether an incident must be reported outside "
                     "the organisation?",
            answer_format="fill-in",
            answers="Legal",
            default="The technology officer and the legal officer, jointly",
            propagates=["Section 11", "Section 9 delegated programmes",
                        "the escalation path"],
        ),
    ],
)


SECTION_12 = SectionRegister(
    number="12", title="Sunset and Deprecation Policy",
    purpose="How a system is retired, and what is preserved when it is.",
    rows=[
        RegisterRow(
            key="sunset.triggers",
            classification="POSTURE",
            source_phrase="failure to meet success criteria at annual "
                          "performance review; expiration of vendor support for "
                          "the underlying model or platform; regulatory or legal "
                          "change that invalidates the use case; availability of "
                          "a superior alternative; or non-renewal of the budget",
            question="What forces a system into a retirement review?",
            answer_format="fill-in",
            answers="Management",
            default="Failing its annual review; the supplier ending support; a "
                    "legal change that invalidates the use case; a better "
                    "alternative; or the budget not being renewed",
            propagates=["Section 12", "Section 4 measurable value",
                        "the oversight schedule",
                        "Appendix C registry lifecycle field"],
        ),
        RegisterRow(
            key="sunset.retention",
            classification="CITATION",
            source_phrase="All AI system documentation, outputs, and decision "
                          "records shall be retained per the state records "
                          "retention schedule following system retirement.",
            question="How long is a retired system's record kept, and under "
                     "whose schedule?",
            answer_format="fill-in",
            answers="Legal",
            default="Per the applicable records retention schedule",
            refresh_trigger="The records schedule is revised",
            propagates=["Section 12", "Section 9 records status",
                        "the archive rules"],
        ),
        RegisterRow(
            key="sunset.reconstruction",
            classification="POSTURE",
            source_phrase="the Agency shall retain the configuration, weights or "
                          "model artifacts where available from the vendor, "
                          "prompt and orchestration logic, and a sufficient "
                          "operational record to permit the prior system to be "
                          "reconstructed for evidentiary purposes",
            question="Must a retired system be reconstructable while decisions "
                     "it influenced can still be challenged?",
            answer_format="accept-risk",
            answers="Legal",
            options=["Yes — configuration, model artifacts, prompt and "
                     "orchestration logic, and the operational record",
                     "The operational record only",
                     "No standing requirement beyond the records schedule"],
            default="Yes — configuration, model artifacts, prompt and "
                    "orchestration logic, and the operational record",
            propagates=["Section 12", "Section 8 substitution",
                        "Section 9 defensibility", "the archive rules"],
            warning="Without this, a determination made two years ago cannot be "
                    "explained when it is challenged — the system that made it "
                    "no longer exists in any form that can be examined.",
            abrogates=["“a sufficient operational record to permit the prior "
                       "system to be reconstructed for evidentiary purposes” — "
                       "Section 12"],
        ),
    ],
)


SECTION_13 = SectionRegister(
    number="13", title="Conclusion",
    purpose="The closing statement, and the standard the framework holds "
            "itself to.",
    rows=[
        RegisterRow(
            key="conclusion.standard",
            classification="ASPIRATION",
            source_phrase="The framework succeeds when it produces AI "
                          "deployments that the Agency can explain, defend, and "
                          "stand behind in a public hearing, a courtroom, and in "
                          "the communities the Agency is charged to protect.",
            question="Finish this sentence in your own words: this framework "
                     "succeeds when…",
            answer_format="text",
            answers="Management",
            default="…it produces AI deployments we can explain, defend, and "
                    "stand behind in a public hearing, a courtroom, and in the "
                    "communities we serve.",
            propagates=["Section 13", "the published framework document",
                        "the opening statement of purpose"],
        ),
        RegisterRow(
            key="conclusion.priority",
            classification="ASPIRATION",
            source_phrase="AI shall serve the Agency's mission rather than "
                          "displace the professional judgment, legal authority, "
                          "and public accountability on which that mission "
                          "depends.",
            question="When modernising and existing obligations pull in "
                     "different directions, which does your framework say wins?",
            answer_format="text",
            answers="Management",
            default="AI serves the mission; it does not displace professional "
                    "judgment, legal authority or public accountability.",
            propagates=["Section 13", "Section 1 purpose",
                        "the published framework document"],
        ),
    ],
)


SECTIONS: list[SectionRegister] = [
    SECTION_1, SECTION_2, SECTION_3, SECTION_4, SECTION_5, SECTION_6,
    SECTION_7, SECTION_8, SECTION_9, SECTION_10, SECTION_11, SECTION_12,
    SECTION_13,
]


def by_number(number: str) -> SectionRegister | None:
    return next((s for s in SECTIONS if s.number == str(number)), None)


def summary() -> dict[str, Any]:
    """The whole register, for the module workflow to draw itself from."""
    mined = [s for s in SECTIONS if s.mined]
    return {
        "method": {
            "name": "Five tests, applied sentence by sentence",
            "tests": [
                {"test": "Swap", "asks": "Would a different agency need a "
                                         "different value?", "yields": "IDENTITY"},
                {"test": "Cite", "asks": "Does it invoke external authority?",
                 "yields": "CITATION"},
                {"test": "Tune", "asks": "Is there a number, list, degree or "
                                         "default rule?", "yields": "POSTURE"},
                {"test": "Voice", "asks": "Is it aspiration or "
                                          "self-description?", "yields": "ASPIRATION"},
                {"test": "Strike", "asks": "Could this be deleted without "
                                           "breaking the architecture?",
                 "yields": "STRUCTURAL"},
            ],
            "note": "Classify first. The sentence type determines whether there "
                    "is a question at all, and what kind. Questions are framed "
                    "neutrally with the reference setting as the visible "
                    "default; no alternatives are invented.",
        },
        "classifications": CLASSIFICATIONS,
        "formats": FORMATS,
        "sections": [s.as_dict() for s in SECTIONS],
        "totals": {
            "sections": len(SECTIONS),
            "mined": len(mined),
            "questions": sum(len(s.questions) for s in SECTIONS),
            "structural": sum(len(s.structural) for s in SECTIONS),
        },
    }
