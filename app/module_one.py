"""Module One — Build Your AI Governance Framework.

Ten steps plus orientation and assembly, taking a public official with no AI
background from a blank page to an adopted framework written in their own words.
Steps 00–04 are here; 05–10 and assembly follow.

This **replaces** `app/discretion.py`, and the reason is worth writing down
because it was a week's work.

That register mined 72 questions out of SCDES's own framework document and
showed, above each question, the SCDES sentence that produced it. It was built
on the premise that somebody answering deserves to see what in the document they
are being asked about — which is a reasonable premise for a reader who already
has a framework, and the wrong one for almost everybody. It also broke the
client's hardest rule in the most direct way available:

    "Do not reference other agencies, users, or frameworks. Privacy and security
     are paramount controls within the framework, we can't violate our own rules
     by letting other content bleed across accounts."

Nothing in this module quotes another organization. There is no `source_phrase`
field to leak.

The premise this one rests on
-----------------------------

An AI tool is an asset the government buys, like a truck. Every public body
already knows who may drive one, who maintains it, what happens when one is
wrecked and when it goes to auction. Four questions, asked ten different ways —
and then the handful of things AI needs that a truck does not.

Two commitments, checked against every question below:

**No structure is imposed.** No council, no CTO, no committee anyone has to
invent. A twelve-person water district and a two-thousand-person state agency
both have to finish with something real.

**There is a floor.** Eight requirements, in step 06, that come from law and
from what actually goes wrong. The user chooses how strict, never whether.

How the branching works
-----------------------

Steps 01 and 02 change what is asked afterward, and 1.4 does the most work of
anything in the module: any function an organization says it does not have is
removed from every later consultation list. Nothing makes a governance tool feel
written for somebody else faster than asking a town clerk to route something to
their General Counsel.

Conditions are declarative rather than callables so they survive the trip to the
browser and can be asserted in a test. See `visible()`.

Roles, never people
-------------------

The client, asked whether 4.2 should collect contact details alongside the role
title:

    "Workflow process will be the operational component which covers the names.
     Framework sets rules meant to outlast individual people."

So nothing in this module asks who somebody is. Every question that establishes
a responsibility asks for a role title, and the individuals currently holding
those roles are the subscription's business. 4.2 originally offered an optional
name field beside the role, on the reasoning that titles survive turnover and
names do not — which was the right reasoning and the wrong conclusion. If names
do not survive, the document should not carry them at all.

The one exception is an adoption, and it is not really an exception: `who signs
this` records a person because a signature is an act by somebody at a moment,
not a standing rule. A rule outlasts people; a signature is the point at which
one person took responsibility. Those are different things and the document says
both.

Rules the copy is held to, and tested for
-----------------------------------------

* Never "model", "algorithm", "LLM", "inference", "training data", "deployment"
  in anything a user reads. The subject is assets and accountability.
* One idea per question. Under twenty words for the prompt itself; nuance goes
  in the help text, where it can be ignored.
* "We don't know" is always available and always produces a real entry as a
  documented gap with an owner. Never a blank.
* Never disable a recommended-against answer. Show the consequence once, accept
  the choice, record the rationale.
"""

from __future__ import annotations

import functools
from dataclasses import dataclass, field, replace
from typing import Any

#: The answer that means "we don't know", stored like any other. It is not an
#: absence — it produces a line in the finished framework naming the gap and
#: who owns closing it, which is the honest version and the one that survives
#: an audit.
UNKNOWN = "unknown"

#: Words that must never appear in anything the user reads. Asserted by
#: tests/test_module_one.py.
#: "matrix" is his too, from 05: "Define risk in one sentence and never use the
#: word 'matrix' in front of the user." It is a control type in this file, not
#: a word anybody reads.
BANNED = ("model", "algorithm", "llm", "inference", "training data", "matrix",
          "machine learning")

#: Banned in the question itself, but not in a response set.
#:
#: His rule names "deployment" with the rest — and then his own reviewed copy
#: uses it four times, all of them in places that are not the question: the
#: statement of floor 5 ("every deployment has a written way to do the job
#: without it"), and option labels at 6.9 and 8.3 where "before changes are
#: deployed" is the term of art a contract clause actually uses.
#:
#: His rule says "in a question the user reads", and he said afterwards: "Stick
#: to what I wrote to the best of your ability. I reviewed every question,
#: response set, and recommendation individually." So the guard holds where he
#: wrote it — the prompt, and the nuance under it — and his response sets and
#: floor statements stand as written.
BANNED_IN_QUESTIONS = ("deployment", "deploy")


@dataclass
class Option:
    value: str
    label: str
    #: A clarifying line under the option. Where the spec puts examples.
    note: str = ""
    recommended: bool = False
    #: Shown only when this holds — see `visible()`. Used by 4.4, which offers
    #: only the offices the organisation said it has.
    shows_when: dict[str, Any] | None = None
    #: Answering this way opens a text field for the detail.
    then_text: str = ""
    #: ...and a file picker beside it. 2.3 said "Upload or paste it" and
    #: offered only the text box (Brett, BUG-0081CD67). The file goes into the
    #: organization's own documents, where every later question can match it.
    then_upload: bool = False
    #: Ticked from the start, when this organisation is the kind it applies to.
    #: 7.1 is the case: "Student records surface for school districts; criminal
    #: justice information for counties, cities, and law enforcement." Every
    #: category is still offered to everybody — withholding a whole class of
    #: protected information from someone who holds it would be worse than
    #: showing one they do not — but the ones that match arrive already chosen.
    recommend_when: list[dict[str, Any]] = field(default_factory=list)
    #: As a row of a matrix: the choice already filled in before they touch it,
    #: and the rules that decide it. 5.1 needs this — "the safety-critical
    #: factor is pre-weighted as a major concern for special districts and
    #: utilities per 1.1 — for a water district this is the factor that matters
    #: most, and defaulting it low would be a serious miss."
    preset: str = ""
    preset_when: list[dict[str, Any]] = field(default_factory=list)
    #: Nothing else can be chosen alongside this one.
    #:
    #: The client, on "nothing moves forward without them" ticked next to three
    #: things that do: "good catch. If they click nothing, then gray out and
    #: make all others un-clickable." Not a refusal — it is one answer that
    #: means the absence of the others, so the interface should say so at the
    #: moment of clicking rather than complain about it four steps later.
    exclusive: bool = False
    #: Which earlier answer made this the suggestion, in words.
    #:
    #: His instruction at 10.7: "give them some insight before the selection;
    #: 'In Section _, you selected ABC, therefore, you should select XYZ'." A
    #: recommendation that cannot say where it came from is the module having
    #: an opinion about them.
    because: str = ""
    #: The same choice as a phrase inside a sentence, for the document.
    #:
    #: An option label is written to be clicked. "A group you already have
    #: takes it on" is exactly right above a radio button and produces
    #: "Responsibility sits with A group you already have takes it on" in the
    #: framework. Where the label cannot be read mid-sentence, this is what
    #: the document uses instead; where it can, this stays empty and the label
    #: is used, so there is only one piece of copy to keep right.
    prose: str = ""

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"value": self.value, "label": self.label}
        if self.note:
            out["note"] = self.note
        if self.recommended:
            out["recommended"] = True
        if self.then_text:
            out["then_text"] = self.then_text
        if self.then_upload:
            out["then_upload"] = True
        if self.preset:
            out["preset"] = self.preset
        if self.exclusive:
            out["exclusive"] = True
        if self.because:
            out["because"] = self.because
        if self.value == UNKNOWN:
            out["is_unknown"] = True
        return out


#: "We don't know", as an option in the response set rather than a checkbox
#: bolted underneath it.
#:
#: The first version rendered a separate tick-box on every question and dropped
#: the "Not sure" the client had written into eleven of his own response sets.
#: He reviewed every question and every response set individually, so his
#: wording is the wording — "Not sure" in most places, "We honestly do not
#: know" at 2.1, "Unsure, have not considered." at 10.6. Where he did not write
#: one, `Question.unknown_ok` appends the generic below, because the build note
#: is explicit that it is always available.
GENERIC_UNKNOWN = "We don't know"

#: Where a section's own paragraph is stored. Prefixed so it can never collide
#: with a question key, and so the export can find them all without a list.
OWN_WORDS_PREFIX = "words."


def own_words_key(step_number: str) -> str:
    return f"{OWN_WORDS_PREFIX}{step_number}"


#: Text answers that are not answers.
#:
#: The client asked: "If I type Unknown right now in 9.4, does the system flag
#: that in the output or write to the output unknown?" The answer was
#: inconsistent and bad — lower-case "unknown" happened to be caught because
#: it equals the sentinel, while "Unknown", "TBD", "don't know" and "n/a" went
#: into the framework as if they were roles, producing "That review is carried
#: out by TBD" as adopted policy.
#:
#: Matched only against the whole answer, trimmed. A role genuinely called
#: "TBD Coordination Office" is somebody's actual job title and must survive.
READS_AS_UNKNOWN = frozenset({
    "unknown", "not known", "don't know", "dont know", "do not know",
    "we don't know", "we dont know", "no idea", "unsure", "not sure",
    "tbd", "t.b.d.", "to be decided", "to be determined", "tba",
    "n/a", "na", "none yet", "nobody yet", "not yet", "?", "??", "-", "—",
})


def reads_as_unknown(value: Any) -> bool:
    """Whether a typed answer is really "we don't know" in other words."""
    if not isinstance(value, str):
        return False
    return value.strip().strip(".").lower() in READS_AS_UNKNOWN


def unknown_option(question: Question) -> Option | None:
    """The unknown choice for this question, if it should have one."""
    if not question.unknown_ok:
        return None
    written = next((o for o in question.options if o.value == UNKNOWN), None)
    if written is not None:
        return None                       # his own wording is already in place
    return Option(UNKNOWN, GENERIC_UNKNOWN)


#: What this kind of organisation actually does, in its own vocabulary.
#:
#: The client: "Where there's a chance to provide context specific to them in
#: order to help them answer questions (example: environmental agencies issue
#: permits, dept of revenue does tax audits, etc) if you can incorporate that,
#: great." And the build note: "Examples should come from their regulatory
#: universe. Once 1.1 is answered, illustrations should be permits for a
#: regulatory agency, work orders for a utility, enrollment for a school
#: district. Generic examples read as generic software."
#:
#: Keyed on 1.1, so nothing appears until they have said who they are — a wrong
#: example is worse than none, because it tells the reader this was written for
#: somebody else.
ORG_EXAMPLES: dict[str, dict[str, str]] = {
    "state": {
        "decision": "issuing or denying a permit, assessing a penalty, a "
                    "benefits determination",
        "predicts": "which application to look at first, which facility is "
                    "most likely to need an inspection",
        "record": "your licensing system",
    },
    "federal": {
        "decision": "a grant award, a benefits determination, an enforcement "
                    "action, a permit or license decision",
        "predicts": "which application to review first, which grantee or "
                    "facility is most likely to need a closer look",
        "record": "your case management system",
    },
    "county": {
        "decision": "issuing a permit, a property assessment, a benefits "
                    "determination, a code enforcement action",
        "predicts": "which parcel to reassess, which complaint to route first",
        "record": "your permit system",
    },
    "city": {
        "decision": "issuing a building permit, a business license, a code "
                    "citation, a utility shut-off",
        "predicts": "which street needs resurfacing first, which complaint to "
                    "route first",
        "record": "the permit system",
    },
    "district": {
        "decision": "a service connection, a shut-off, a rate determination, a "
                    "safety hold",
        "predicts": "which pipe is likely to fail, which pump is due for "
                    "service",
        "record": "the work-order system",
    },
    "school": {
        "decision": "an enrollment decision, a placement, a discipline outcome, "
                    "an eligibility determination",
        "predicts": "which student may need support, which route to change",
        "record": "the student information system",
    },
    "regional": {
        "decision": "a grant award, a project approval, an eligibility "
                    "determination",
        "predicts": "which project to prioritize, which corridor to study "
                    "first",
        "record": "the grant file",
    },
    "tribal": {
        "decision": "an enrollment decision, a permit, a benefits "
                    "determination, a service eligibility",
        "predicts": "which application to review first, which facility needs "
                    "attention",
        "record": "the program file",
    },
}

#: Used before 1.1 is answered, and for "other public body".
#:
#: These are the client's own words, kept verbatim — his 3.1 illustration and
#: his 4.7 prompt. The per-type entries above *substitute* for them where a
#: sector makes a sharper example available, which is what he asked for: "where
#: there's a chance to provide context specific to them in order to help them
#: answer questions... if you can incorporate that, great." A school district
#: has no pipes. Everyone else keeps his phrasing.
NEUTRAL_EXAMPLES = {
    "decision": "issuing or denying a permit, assessing a penalty, approving a "
                "payment, a benefits determination",
    "predicts": "which pipe is likely to fail, which application to look at "
                "first, which facility is most likely to need increased "
                "inspections",
    "record": "the permit system",
}


#: How to refer to whoever decides, in the structure they chose at 4.1.
#:
#: Step 05 pre-fills what has to happen at each level of scrutiny, and the
#: build note says why: "Populate sensible defaults for each tier based on the
#: shape chosen in 4.1, so the user is editing rather than composing." A
#: pre-fill that says "the committee" to an organisation that chose one
#: accountable person is worse than a blank, because now they have to delete
#: something before they can write.
DECIDERS = {
    "one": "the accountable person",
    "group": "the standing group",
    "council": "the council",
    "existing": "the group that took this on",
}
NEUTRAL_DECIDER = "whoever approves AI use"


def examples_for(answers: dict[str, Any]) -> dict[str, str]:
    """The illustrations to use, given who they said they are."""
    kind = _value(answers, "org.kind")
    words = dict(ORG_EXAMPLES.get(str(kind or ""), NEUTRAL_EXAMPLES))
    shape = str(_value(answers, "who.shape") or "")
    words["decider"] = DECIDERS.get(shape, NEUTRAL_DECIDER)
    # The same words with a capital, for where they open a sentence or stand
    # alone as the label on a choice. `decider` carries its article and is
    # written for the middle of a clause — "approved by the accountable
    # person" — so 7.4 offered a choice reading "the accountable person" in
    # lower case beside "Someone else", which was raised as a ticket.
    words["Decider"] = words["decider"][:1].upper() + words["decider"][1:]
    words["approver"] = _lowest_approver(answers)
    words["first_ask"] = _who_is_asked_first(answers)
    words.update(_tier_words(answers))
    return words


def _tier_words(answers: dict[str, Any]) -> dict[str, str]:
    """The names of the levels of scrutiny they chose, for use in a label.

    A question about which levels a rule covers has to use the level names
    this organization picked. 6.5a offered "Moderate- and high-risk only" and
    "High-risk only" to an organization that had chosen two levels called
    Routine and Elevated — options naming a vocabulary it had declined, and
    two of them for a distinction it did not have. His ticket: "Decided
    earlier in this version of only 2 tiers, routine and enhanced; 6.5a
    offers three-tier based inputs. Needs to be adaptive to previous
    question."
    """
    levels = tiers_for(answers)
    names = [o.label.split(" — ")[0] for o in levels]
    upper = names[1:] or names
    if len(upper) == 1:
        joined = upper[0]
    else:
        joined = f"{', '.join(upper[:-1])} and {upper[-1]}"
    return {"top_tier": names[-1], "upper_tiers": joined,
            "lowest_tier": names[0]}


def _has_function(answers: dict[str, Any], name: str) -> bool:
    """Whether 1.4 said this office exists in some form."""
    held = _value(answers, "org.functions")
    if not isinstance(held, dict):
        return False
    return held.get(name) not in (None, "", "none")


def _lowest_approver(answers: dict[str, Any]) -> str:
    """Who signs off the least risky tools.

    The client's correction to the first draft of these pre-fills, which said
    "the person who will use it": "It can't be the person that uses it,
    low-level staff could just 'approve' themselves and integrate it."

    So it is whoever holds approval authority — typically IT, where there is
    an IT office. Where there is not, it falls back to whoever they said
    decides, because naming an office they do not have is the other way this
    goes wrong.
    """
    if _has_function(answers, "it"):
        return "Whoever has authority to approve it — typically IT"
    shape = str(_value(answers, "who.shape") or "")
    return DECIDERS.get(shape, NEUTRAL_DECIDER).capitalize()


def _who_is_asked_first(answers: dict[str, Any]) -> str:
    """The ", with legal and IT asked first" clause, if those offices exist.

    Named unconditionally it told a twelve-person district to consult a legal
    department it had already said it does not have.
    """
    asked = [name for name, label in (("legal", "legal"), ("it", "IT"))
             if _has_function(answers, name)]
    if not asked:
        return ""
    labels = {"legal": "legal", "it": "IT"}
    named = " and ".join(labels[a] for a in asked)
    return f", with {named} asked first"


def _fill(text: str, answers: dict[str, Any]) -> str:
    """Substitute `{decision}` and friends with this organization's own words."""
    if not text or "{" not in text:
        return text
    words = examples_for(answers)
    for name, value in words.items():
        text = text.replace("{" + name + "}", value)
    return text


@dataclass
class Question:
    key: str
    number: str
    prompt: str
    #: single · multi · matrix · short · long · rows
    kind: str
    options: list[Option] = field(default_factory=list)
    #: For a matrix: the things being asked about, and the choices per row.
    rows: list[Option] = field(default_factory=list)
    row_options: list[Option] = field(default_factory=list)
    #: Rows taken from another question's rows, filtered by what was answered.
    rows_from: dict[str, Any] | None = None
    #: Shown inline. Nuance, examples, and the "why we ask" the spec calls for.
    help: str = ""
    #: Said above the control rather than under it, where the spec says so.
    above: str = ""
    optional: bool = False
    unknown_ok: bool = True
    shows_when: dict[str, Any] | None = None
    #: [{"if": {...}, "then": "value"}] — the recommendation moves with the
    #: organisation's own answers rather than being fixed.
    recommend_when: list[dict[str, Any]] = field(default_factory=list)
    placeholder: str = ""
    #: Which parts of the finished framework this answer writes.
    writes: list[str] = field(default_factory=list)
    #: A second field on the same question, because he asked two things at
    #: once: 8.1's approval process *and* its dollar thresholds, 9.8's decider
    #: *and* what happens to the records, 10.8's writer *and* where the record
    #: lives. Splitting them into separate numbered questions would renumber
    #: his document, so they travel together and store under "also".
    also: dict[str, Any] | None = None
    #: For kind="tiers": what is asked about every level of scrutiny. Rows come
    #: from how many levels they chose at 5.2.
    tier_fields: list[dict[str, Any]] = field(default_factory=list)
    #: Guidance that appears under the question only when it is needed —
    #: {"shows_when": ..., "title": ..., "body": [...], "close": "..."}. 7.3's
    #: readiness panel is the reason this exists: "the highest-value advisory
    #: moment in the entire module and it should not be buried".
    advice: dict[str, Any] | None = None
    #: The block this question sits under. Step 06 is eight of them.
    group: str = ""
    #: The wording on the control that lets them add a choice of their own.
    #: Empty means the response set is closed. See `_their_own`.
    can_add: str = ""
    #: One line shown when a particular answer is chosen, and then accepted.
    #:
    #: "Nudge, don't block — if they answer 'never', show one line, 'An
    #: untested fallback is a document, not a plan', and let the answer
    #: stand." His lines live here, beside the question they belong to, rather
    #: than hardcoded in the interface where the first one was: the browser
    #: knew about 4.1 and nothing else, so 6.5b showed nothing at all and he
    #: raised a ticket about it.
    #: [{"if": {...}, "say": "..."}]
    consequences: list[dict[str, Any]] = field(default_factory=list)
    #: A question that must be answered before this one can be. Shown, but not
    #: editable, until it is.
    #:
    #: "If someone says in 5.2 'We don't know', then 5.3 cannot be filled out.
    #: Gray out boxes, do not allow for editing (because 5.3 requires 5.2)."
    #: This is not the module refusing an answer — it is one question having
    #: nothing to ask until another is settled, which is worth saying plainly
    #: rather than pre-filling a grid against levels they have not chosen.
    #: {"key": ..., "unless": {...}, "say": "..."}
    needs: dict[str, Any] | None = None
    #: Wording, and sometimes the control itself, replaced when an earlier
    #: answer makes the default wrong.
    #:
    #: "4.1/4.2 need to be adaptive. If 4.1 selects One accountable Person,
    #: 4.2 should ask who is that person?" — asking for "roles" in the plural,
    #: as a grid, of an organization that has just said one person holds it
    #: all, is the module not listening to the answer it was given.
    #:
    #: A second Question sharing the key would have been the obvious way to do
    #: this and is a trap: `by_key` returns the first match and takes no
    #: answers, so the export would have resolved to whichever copy was
    #: written first and dropped the clause whenever the other was the visible
    #: one. One question, one key, one stored answer; only the presentation
    #: moves.
    #:
    #: [{"if": {...}, "prompt": ..., "kind": ..., "above": ..., "help": ...,
    #:   "placeholder": ...}] — the first rule that holds wins.
    instead_when: list[dict[str, Any]] = field(default_factory=list)

    def _as_asked(self, answers: dict[str, Any]) -> dict[str, str]:
        """The overrides in force, given what has been answered."""
        for rule in self.instead_when:
            if holds(rule.get("if"), answers):
                return {name: value for name, value in rule.items()
                        if name != "if"}
        return {}

    def as_dict(self, answers: dict[str, Any] | None = None) -> dict[str, Any]:
        answers = answers or {}
        instead = self._as_asked(answers)
        kind = instead.get("kind", self.kind)
        out = {
            "key": self.key,
            "number": self.number,
            "prompt": _fill(instead.get("prompt", self.prompt), answers),
            "kind": kind,
            "options": [
                {**o.as_dict(),
                 **({"note": _fill(o.note, answers)} if o.note else {})}
                for o in options_for(self, answers)],
            "help": _fill(instead.get("help", self.help), answers),
            "above": _fill(instead.get("above", self.above), answers),
            "optional": self.optional,
            "unknown_ok": self.unknown_ok,
            "placeholder": _fill(
                instead.get("placeholder", self.placeholder), answers),
            "writes": list(self.writes),
            "recommended": recommended_for(self, answers),
            "can_add": self.can_add,
            # Every line and the answer that triggers it, so the interface can
            # show one the moment it is clicked without another round trip.
            "consequences": [
                {"if": rule.get("if"), "say": _fill(rule.get("say", ""),
                                                    answers)}
                for rule in self.consequences],
        }
        if self.needs:
            waiting = not holds(self.needs.get("unless"), answers)
            out["waiting_on"] = {
                "on": self.needs.get("key", ""),
                "say": _fill(str(self.needs.get("say", "")), answers),
            } if waiting else None
        if kind in ("matrix", "tiers"):
            out["rows"] = [r.as_dict() for r in rows_for(self, answers)]
            out["row_options"] = [o.as_dict() for o in self.row_options]
        if kind == "tiers":
            out["tier_fields"] = [
                {**f, "label": _fill(f.get("label", ""), answers),
                 "ask": _fill(f.get("ask", ""), answers),
                 "defaults": {t: _fill(v, answers)
                              for t, v in (f.get("defaults") or {}).items()}}
                # A field can be conditional like anything else: the "what you
                # call this level" box only exists for the four-level set,
                # which he left unnamed on purpose.
                for f in self.tier_fields
                if holds(f.get("shows_when"), answers)]
        if self.also:
            out["also"] = {**self.also,
                           "label": _fill(self.also.get("label", ""), answers),
                           "placeholder": _fill(
                               self.also.get("placeholder", ""), answers)}
        if self.group:
            out["group"] = self.group
        # Guidance is withheld until it applies. Shown unconditionally it is
        # noise; shown at the moment they admit the gap it is the advice.
        if self.advice and holds(self.advice.get("shows_when"), answers):
            out["advice"] = {
                "title": _fill(self.advice.get("title", ""), answers),
                "body": [_fill(b, answers)
                         for b in self.advice.get("body", [])],
                "close": _fill(self.advice.get("close", ""), answers),
            }
        return out


@dataclass
class Step:
    number: str
    title: str
    #: "THE BRANCHING SPINE · 7 QUESTIONS"
    strapline: str
    #: "PURPOSE · SCOPE · ADAPTS EVERY LATER STEP"
    writes: str
    #: Shown before the first question. The framing that does the work.
    opening: list[str] = field(default_factory=list)
    questions: list[Question] = field(default_factory=list)
    #: Orientation steps ask nothing.
    asks: bool = True
    #: "A free-text box per section: 'Anything you'd add here, in your own
    #: voice?' Text goes in verbatim." Not a question — it is never counted,
    #: never required, and never interpreted. It is the one place in the module
    #: where the document takes dictation.
    own_words: bool = False
    #: Named blocks the questions sit in, keyed by `Question.group`. Step 06's
    #: eight floors, each with the rule in plain words and one line on why it
    #: exists, "presented the same way".
    groups: list[dict[str, Any]] = field(default_factory=list)
    #: Shown after the last question — {"title": ..., "body": [...],
    #: "table": {"head": [...], "rows": [[...]]}, "after": "..."}.
    closing: dict[str, Any] | None = None

    def as_dict(self, answers: dict[str, Any] | None = None) -> dict[str, Any]:
        answers = answers or {}
        shown = [q for q in self.questions if visible(q, answers)]
        out = {
            "number": self.number,
            "title": self.title,
            "strapline": self.strapline,
            "writes": self.writes,
            "opening": list(self.opening),
            "asks": self.asks,
            "questions": [q.as_dict(answers) for q in shown],
            "question_count": len(shown),
            "answered": sum(1 for q in shown if answered(q, answers)),
        }
        if self.groups:
            # Only the blocks that still have a question in them. A floor whose
            # questions all branched away would otherwise leave a heading with
            # nothing under it.
            live = {q.group for q in shown}
            out["groups"] = [g for g in self.groups if g["key"] in live]
        if self.closing:
            out["closing"] = self.closing
        if self.own_words:
            out["own_words"] = {
                "key": own_words_key(self.number),
                "prompt": "Anything you'd add here, in your own voice?",
                "note": "Goes into your framework word for word, under this "
                        "section. Nothing rewrites it.",
                "value": str(_value(answers, own_words_key(self.number))
                             or ""),
            }
        return out


# --------------------------------------------------------------- conditions

def _unwrap(raw: Any) -> tuple[Any, dict[str, Any]]:
    """The answer itself, and whatever traveled with it.

    Answers arrive nested twice and it is not an accident of one layer being
    sloppy — each wrapper is doing a different job. `versions.answer` records
    *who* answered and *when*, around whatever it was given; the endpoint
    records the owner of a gap or the detail a "yes" opened up, around the value
    itself. So a "we don't know" with an owner is stored as::

        {"value": {"value": "unknown", "owner": "Town Attorney"},
         "at": ..., "by": ...}

    Reading one level deep returned the inner dict where a plain string was
    expected, so every gap silently failed to register as one. This descends
    until it reaches the value and keeps the extras it passes on the way.
    """
    extras: dict[str, Any] = {}
    seen = 0
    # Everything except the value and the wrapper's own bookkeeping. Named
    # extras were listed here one at a time, which meant a question with a
    # paired field — "who writes it, and who approves it" — silently dropped
    # the second half.
    skip = ("value", "at", "by", "by_title")
    while isinstance(raw, dict) and "value" in raw and seen < 4:
        for name, held in raw.items():
            if name not in skip and held:
                extras[name] = held
        raw = raw["value"]
        seen += 1
    return raw, extras


def _value(answers: dict[str, Any], key: str) -> Any:
    return _unwrap(answers.get(key))[0]


def value_of(answers: dict[str, Any], key: str) -> tuple[Any, dict[str, Any]]:
    """The answer to one question, and whatever traveled with it.

    Public because the export needs the same reading the module uses. Two
    readers disagreeing about how an answer is stored is how the builder ended
    up writing into a bucket nothing else looked at.
    """
    return _unwrap(answers.get(key))


def holds(condition: dict[str, Any] | None, answers: dict[str, Any]) -> bool:
    """Whether a declarative condition is satisfied by the answers so far.

    Deliberately small: five forms, no expressions, no callables. It has to be
    serializable — the browser evaluates the same conditions to avoid a round
    trip per keystroke — and it has to be assertable in a test.
    """
    if not condition:
        return True

    # Two combining forms, because some of his conditions genuinely are
    # compound: the readiness panel at 7.3 appears when *either* "where does
    # your information live" or "which systems hold what" came back as
    # anything other than documented — and only once they have said so, or it
    # would greet them before they had answered anything.
    if "any" in condition:
        return any(holds(c, answers) for c in condition["any"])
    if "all" in condition:
        return all(holds(c, answers) for c in condition["all"])

    key = condition.get("key", "")
    got = _value(answers, key)

    if "row" in condition:
        # A matrix answer: {"legal": "dedicated", "it": "none"}
        got = (got or {}).get(condition["row"]) if isinstance(got, dict) else None

    if "answered" in condition:
        filled = got not in (None, "", [], {})
        return filled is bool(condition["answered"])
    if "is" in condition:
        return got == condition["is"]
    if "not" in condition:
        return got != condition["not"]
    if "in" in condition:
        if isinstance(got, list):
            return any(v in condition["in"] for v in got)
        return got in condition["in"]
    if "includes" in condition:
        return isinstance(got, list) and condition["includes"] in got
    if "beyond" in condition:
        # A multi-select that also holds something outside the given set. The
        # shape of half the contradictions: "nothing moves forward without
        # them" ticked alongside three things that do.
        return isinstance(got, list) and any(v not in condition["beyond"]
                                             for v in got)
    return True


def kind_of(question: Question, answers: dict[str, Any]) -> str:
    """The control this question is actually asking with.

    Public because more than the browser needs it. A question whose
    `instead_when` swaps a grid for a single box stores a different shape of
    answer, and anything reading that answer back — the export, the gap list,
    the polish pass — has to ask what was asked rather than what the question
    was declared as.
    """
    return question._as_asked(answers).get("kind", question.kind)


def visible(question: Question, answers: dict[str, Any]) -> bool:
    if not holds(question.shows_when, answers):
        return False
    # A grid whose rows are drawn from another answer, and which came back with
    # none, has nothing to ask. It used to render the heading and a line saying
    # so: "4.4b — if it is not relevant based on previous answers, hide the
    # component. It's sitting there with nothing for me to do and is
    # confusing." Quite so.
    if question.rows_from and not rows_for(question, answers):
        return False
    return True


#: Marks a choice the organization wrote themselves, rather than one we
#: offered. The label follows the prefix, so the answer carries its own
#: meaning and nothing has to be stored alongside it.
CUSTOM = "custom:"


def is_custom(value: str) -> bool:
    return str(value).startswith(CUSTOM)


def custom_label(value: str) -> str:
    return str(value)[len(CUSTOM):] if is_custom(value) else str(value)


def _their_own(question: Question, answers: dict[str, Any]) -> list[Option]:
    """The choices they added themselves, recovered from the answer.

    Four of his tickets say the same thing in four places — 3.1/3.2 "add Other
    and a fillable line", 5.1 "let them add their own risks", 6.2b "provide
    ability to add rows", 6.6 "self-add fields". A response set that cannot be
    extended is the module telling an organization that its business is one of
    the eight things we thought of.

    Nothing is stored beside the answer: a custom choice *is* its label, behind
    a prefix. So it survives, appears ticked, can be un-ticked, and needs no
    second list that could fall out of step with the first.
    """
    if not question.can_add:
        return []
    held, _ = value_of(answers, question.key)
    if question.kind == "matrix":
        found = list(held) if isinstance(held, dict) else []
    else:
        found = held if isinstance(held, list) else []
    return [Option(str(v), custom_label(v)) for v in found if is_custom(v)]


def options_for(question: Question, answers: dict[str, Any]) -> list[Option]:
    shown = [o for o in question.options if holds(o.shows_when, answers)]
    # An option can become recommended on the strength of an earlier answer —
    # 7.1's student records for a school district. Resolved here so the same
    # option can be the obvious one for a school and merely available to
    # everybody else, and carrying the reason so the screen can say which
    # answer put it there.
    shown = [_resolve_recommendation(o, answers) for o in shown]
    # Then anything they wrote themselves, before the unknown.
    shown = shown + _their_own(question, answers)
    # Substituted here, once, rather than at each of the four places that read
    # an option. 7.4 offers "{decider}" as a choice — the structure they picked
    # at 4.1 — and every reader of an option label needs it filled: the screen,
    # the document, the read-back and the audit trail.
    shown = [replace(o, label=_fill(o.label, answers),
                     note=_fill(o.note, answers),
                     prose=_fill(o.prose, answers),
                     then_text=_fill(o.then_text, answers))
             for o in shown]
    # Appended last, and only where the client did not write one himself. On a
    # question with no options at all — a text field — there is nothing to
    # append it to; the interface offers it separately there.
    if shown:
        extra = unknown_option(question)
        if extra is not None:
            shown = shown + [extra]
    return shown


#: The levels of scrutiny, by how many of them they asked for at 5.2.
#:
#: He named two of the three sets himself — "routine and elevated" and "low,
#: moderate, high". He did not name the four-level set, so it extends his own
#: three downwards rather than introducing a second vocabulary; a framework
#: that calls the same thing "elevated" in one section and "tier 3" in another
#: is one nobody can follow.
TIER_SETS: dict[str, list[Option]] = {
    "two": [Option("routine", "Routine"), Option("elevated", "Elevated")],
    "three": [Option("low", "Low"), Option("moderate", "Moderate"),
              Option("high", "High")],
    # He named the other two sets and left this one open: "Let them fill in the
    # levels. 2 and 3 being pre-loaded helps cut down onboarding; if they want
    # to configure to that degree, let them." So these are placeholders to be
    # typed over at 5.3, not a vocabulary the module is imposing.
    "four": [Option("t1", "Level 1 — least scrutiny"),
             Option("t2", "Level 2"), Option("t3", "Level 3"),
             Option("t4", "Level 4 — most scrutiny")],
}
DEFAULT_TIERS = "three"


def tiers_for(answers: dict[str, Any]) -> list[Option]:
    """The levels of scrutiny this organization chose, lowest first."""
    chosen = str(_value(answers, "risk.levels") or "")
    return list(TIER_SETS.get(chosen, TIER_SETS[DEFAULT_TIERS]))


def level_names(answers: dict[str, Any]) -> list[tuple[str, str]]:
    """`(value, the name they use)` for each level, lowest first — or none
    until they have said how many levels there are.

    Where they typed their own word for a level at 5.3 (the four-level set
    asks for it), that word is the name. Every surface reads levels through
    this, so a placeholder like "Level 2" never stands in for a name they
    wrote, and three levels are never offered to an organization that has
    not chosen any.
    """
    question = by_key("risk.levels")
    if question is None or not answered(question, answers):
        return []
    if reads_as_unknown(_value(answers, "risk.levels")):
        return []
    given = _value(answers, "risk.tiers")
    given = given if isinstance(given, dict) else {}
    out = []
    for tier in tiers_for(answers):
        typed = str(((given.get(tier.value) or {}).get("name")) or "").strip()
        out.append((tier.value, typed or tier.label))
    return out


def _resolve_recommendation(option: Option,
                            answers: dict[str, Any]) -> Option:
    """Whether this option is the suggestion here, and why.

    The reason travels with it. "You said X in step N, so we suggest Y" is a
    different thing from "we suggest Y" — the first is the module reading their
    answers back, which is what earns the suggestion; the second is the module
    having a view about their organization, which it has no standing to have.
    """
    for rule in option.recommend_when:
        if holds(rule.get("if"), answers):
            return replace(option, recommended=True,
                           because=str(rule.get("because", "")
                                       or option.because))
    return option


def rows_for(question: Question, answers: dict[str, Any]) -> list[Option]:
    """A matrix's rows, which may be drawn from another question's answers.

    4.4b asks what to do about each office the organization said it does not
    have — so its rows are exactly the rows of 1.4 that came back "none". A
    fixed list could not express that, and hardcoding the offices would defeat
    the point of asking. 5.3, 9.3 and 10.4 do the same trick with the levels of
    scrutiny chosen at 5.2.
    """
    spec = question.rows_from
    if not spec:
        rows = list(question.rows)
    elif spec.get("tiers"):
        rows = tiers_for(answers)
    else:
        source = by_key(spec["key"])
        given = _value(answers, spec["key"]) or {}
        if source is None or not isinstance(given, dict):
            return []
        wanted = spec.get("where")
        rows = [r for r in source.rows if given.get(r.value) == wanted]
        # A row can be excluded for a reason the source question does not
        # know about: cybersecurity is not a missing office if 1.4b said IT
        # covers it, even though 1.4 recorded no separate team.
        unless = spec.get("unless") or {}
        rows = [r for r in rows
                if not (r.value in unless and holds(unless[r.value], answers))]
    # A row can be conditional in its own right, the same way an option is:
    # 5.1's delegated-program factor "appears only if 1.5 is yes". This was
    # only ever applied to options, so the row was asked of everybody.
    rows = [r for r in rows if holds(r.shows_when, answers)]
    # And a row can be one they wrote: "5.1 — wanted to fill in and add a
    # field + weight it. Locked in only options now. Let them add their own
    # risks."
    rows = rows + _their_own(question, answers)
    # A row can also arrive pre-weighted — 5.1's safety-critical factor for a
    # water district. Resolved here rather than on the row so the same row can
    # mean different things to different organisations.
    return [replace(r, preset=_preset_for(r, answers)) for r in rows]


def _preset_for(row: Option, answers: dict[str, Any]) -> str:
    for rule in row.preset_when:
        if holds(rule.get("if"), answers):
            return str(rule.get("then", ""))
    return row.preset


def recommended_for(question: Question, answers: dict[str, Any]) -> str:
    """Which option is recommended, given what the organization has said.

    A fixed recommendation would be the module having an opinion about
    organizations in general. These move: 4.1 leans on size, 5.2 leans on size.
    The spec is firm that a recommendation is never an obligation — nothing is
    disabled, and picking against it is accepted without further argument.
    """
    # One computed recommendation, and it has to be computed: which register
    # suits an organization is a weighing of several signals — size, shape,
    # levels, dedicated offices, delegated programmes — and `holds` tests one
    # condition at a time by design. Special-cased here rather than bent into
    # a declarative rule that would be unreadable and still wrong.
    if question.key == "done.register":
        return str(register_for(answers)["suggested"])

    for rule in question.recommend_when:
        if holds(rule.get("if"), answers):
            return str(rule.get("then", ""))
    # The resolved list, not the raw one, so an option that becomes the
    # recommendation on the strength of an earlier answer is seen here too.
    for option in options_for(question, answers):
        if option.recommended:
            return option.value
    return ""


def answered(question: Question, answers: dict[str, Any]) -> bool:
    got = _value(answers, question.key)
    if got in (None, "", [], {}):
        return False
    return True


# ------------------------------------------------- one answer, in plain words

def phrase_pairs(question: Question,
                 answers: dict[str, Any]) -> list[tuple[str, bool]]:
    """Each phrase, and whether the organization wrote it themselves.

    The flag matters downstream: a label this project wrote can be lowered to
    sit mid-sentence, and a phrase they typed cannot. Without it, "Meter
    reading models" came out of the document as "meter reading models", which
    is this module editing their words again by a new route.
    """
    value, extras = value_of(answers, question.key)
    if value in (None, "", [], {}) or value == UNKNOWN:
        return []
    words = {o.value: (o.prose or o.label)
             for o in options_for(question, answers)}
    if question.kind == "single":
        # Where the choice opened a blank and they filled it, the document
        # reads what they wrote. "Approved by someone else — the Records
        # Officer" is the audit trail's job; the framework says "approved by
        # the Records Officer", which is the rule.
        typed = str(extras.get("detail", "")).strip()
        if typed:
            return [(typed, True)]
        return [(words.get(str(value), str(value)), is_custom(value))]
    if question.kind == "multi":
        chosen = value if isinstance(value, list) else [value]
        if UNKNOWN in chosen:
            return []
        return [(words.get(str(v), str(v)), is_custom(v)) for v in chosen]

    # Everything else — text, grids, seats — is already their own words. The
    # paired half is left out: `paired()` returns it separately so a sentence
    # can put it where it belongs, rather than having it appended with its own
    # field label attached.
    lines = describe(question, answers)["lines"]
    if question.also and lines:
        label = str(question.also.get("label", ""))
        lines = [line for line in lines if not line.startswith(f"{label}:")]
    return [(line, True) for line in lines]


def phrases(question: Question, answers: dict[str, Any]) -> list[str]:
    """This answer as phrases that can sit inside a sentence.

    The same answer `describe` returns, but using each option's `prose` form
    where it has one. Only choices have one; free text is whatever they typed
    and is never reworded.

    Delegates rather than repeating `phrase_pairs`. It used to be a second
    implementation of the same logic, and the two drifted the moment one of
    them learned that a choice which opens a blank should read back what was
    typed in it.
    """
    return [text for text, _ in phrase_pairs(question, answers)]


def paired(question: Question, answers: dict[str, Any]) -> str:
    """The second half of a two-part question, on its own."""
    if not question.also:
        return ""
    _, extras = value_of(answers, question.key)
    return str(extras.get(str(question.also.get("key", "")), "")).strip()


def describe(question: Question, answers: dict[str, Any]) -> dict[str, Any]:
    """What this question was answered, written the way a reader needs it.

    The stored answer is a set of option values — `{"legal": "dedicated"}`,
    `["before_live", "annual"]` — which is the right thing to store and the
    wrong thing to print. This turns it back into the labels the person
    actually clicked, so the finished framework reads as their words rather
    than as this platform's vocabulary leaking into their document.

    Three states, and the middle one is the point: an unknown is a *gap*, not a
    blank. "'We don't know' is a valid answer and appears in the document as a
    stated gap with an owner — NO BLANKS."
    """
    value, extras = value_of(answers, question.key)
    owner = str(extras.get("owner") or "").strip()
    detail = str(extras.get("detail") or "").strip()

    if value in (None, "", [], {}):
        return {"state": "blank", "lines": [], "owner": ""}
    # Clicked "we don't know", or typed it in their own words. Both are the
    # same admission and both belong in the gaps list rather than in the
    # framework as a statement of who does the work.
    if value == UNKNOWN or reads_as_unknown(value):
        return {"state": "gap", "lines": [], "owner": owner}

    labels = {o.value: o.label for o in options_for(question, answers)}
    lines: list[str] = []

    # What was actually asked, not what the question was declared as — 4.2
    # asks for one role in a box where responsibility sits with one person,
    # and for a grid of roles otherwise.
    kind = kind_of(question, answers)

    if kind == "single":
        lines = [labels.get(str(value), str(value))]
        if detail:
            lines[0] += f" — {detail}"
    elif kind == "multi":
        chosen = value if isinstance(value, list) else [value]
        if UNKNOWN in chosen:
            return {"state": "gap", "lines": [], "owner": owner}
        lines = [labels.get(str(v), str(v)) for v in chosen]
    elif kind == "matrix":
        rows = {r.value: r.label for r in rows_for(question, answers)}
        picks = {o.value: o.label for o in question.row_options}
        given = value if isinstance(value, dict) else {}
        lines = [f"{label} — {picks.get(str(given[key]), str(given[key]))}"
                 for key, label in rows.items() if key in given]
    elif kind == "tiers":
        given = value if isinstance(value, dict) else {}
        for tier in rows_for(question, answers):
            held = given.get(tier.value) or {}
            for spec in question.tier_fields:
                said = held.get(spec["key"])
                if not said:
                    continue
                shown = {o["value"]: o["label"]
                         for o in spec.get("options", [])}.get(said, said)
                lines.append(f"{tier.label} · {spec['label']}: {shown}")
    elif kind == "rows":
        seats = value if isinstance(value, list) else []
        lines = [str(r.get("role", "")).strip() for r in seats
                 if isinstance(r, dict) and str(r.get("role", "")).strip()]
    # A box, or a box that used to be a grid. Where `instead_when` has
    # swapped the control under them, the stored answer is still the shape
    # the old control wrote — and `str()` on that puts a Python repr of a
    # list of dictionaries into somebody's governance framework. They
    # answered the question; changing 4.1 afterwards is not a reason to lose
    # it or to print it as code.
    elif isinstance(value, list):
        lines = [str(r.get("role", "")).strip() if isinstance(r, dict)
                 else str(r).strip() for r in value]
    else:
        lines = [str(value).strip()]

    # The paired half of a two-part question, printed under the first so the
    # document reads back both things he asked for.
    if question.also:
        said = str(extras.get(str(question.also.get("key", "")), "")).strip()
        if said:
            lines.append(f"{question.also.get('label', 'And')}: {said}")

    lines = [line for line in lines if line]
    if not lines:
        return {"state": "blank", "lines": [], "owner": ""}
    return {"state": "answered", "lines": lines, "owner": ""}


# ------------------------------------------------- how formal the document is

#: The two registers the finished framework can be written in.
#:
#: The client, after comparing our output with a real adopted framework: "Let
#: them choose. If their governance inputs are 'modest' — e.g. 2 risk
#: categories, only one or two people, no council — the default will be KISS,
#: recommend 'Simplified'. Bigger agencies where they have dedicated staff for
#: legal, procurement, IT, multiple people and inputs, recommend 'Formal'."
#:
#: Recommended, never imposed — the same rule as everywhere else in the
#: module. A twelve-person water district that wants a formal instrument for
#: its board is entitled to one, and a large agency that wants plain sentences
#: is entitled to that.
SIMPLIFIED = "simplified"
FORMAL = "formal"

#: How the language reads — the client's second question at the download.
#: `as_written` is what this module assembles. `polished` runs it through a
#: language model for wording only; see `app/polish.py` for what that is and
#: is not allowed to do.
AS_WRITTEN = "as_written"
POLISHED = "polished"


def language_of(answers: dict[str, Any]) -> str:
    """Whether they asked for the wording to be polished.

    Defaults to `as_written`. Nobody gets a language model run over their
    policy because they did not read a question — the honest default is the
    thing that has been nowhere near one.
    """
    chosen, _ = value_of(answers, "done.language")
    return POLISHED if str(chosen or "") == POLISHED else AS_WRITTEN


def register_for(answers: dict[str, Any]) -> dict[str, Any]:
    """Which register suits this organization, and the reasons for saying so.

    The reasons are returned with it because a recommendation the module
    cannot explain is the module having an opinion about them. On screen it
    says "we suggest Formal because you have dedicated legal and IT, a
    council, and a delegated program" — which is checkable, and arguable.
    """
    formal_because: list[str] = []
    simple_because: list[str] = []

    size = str(_value(answers, "org.size") or "")
    if size in ("500-2000", "2000+"):
        formal_because.append("more than five hundred people")
    elif size in ("u25", "25-100"):
        simple_because.append("a small organization")

    shape = str(_value(answers, "who.shape") or "")
    if shape == "council":
        formal_because.append("a formal council with a written charter")
    elif shape == "one":
        simple_because.append("one accountable person rather than a committee")

    levels = str(_value(answers, "risk.levels") or "")
    if levels == "two":
        simple_because.append("two levels of scrutiny")
    elif levels == "four":
        formal_because.append("four levels of scrutiny")

    functions = _value(answers, "org.functions")
    if isinstance(functions, dict):
        # Three, because those are the three he named: "dedicated staff for
        # legal, procurement, IT".
        dedicated = [k for k, v in functions.items() if v == "dedicated"]
        if len(dedicated) >= 3:
            formal_because.append(
                f"dedicated staff for {len(dedicated)} functions")
        elif dedicated == [] and functions:
            simple_because.append("no dedicated offices")

    if _value(answers, "org.delegated") == "yes":
        formal_because.append("a delegated or federally funded program")

    # Open records is *not* a signal, though it looks like one. Nearly every
    # public body in the country is subject to it, so it says nothing about
    # how large or formal this one is — and counting it tipped a mid-size
    # city into Formal on its own, which is the recommendation being made by
    # something that is true of everybody.

    suggested = FORMAL if len(formal_because) > len(simple_because) \
        else SIMPLIFIED
    return {
        "suggested": suggested,
        "because": formal_because if suggested == FORMAL else simple_because,
        "formal_signals": formal_because,
        "simple_signals": simple_because,
    }


def register_of(answers: dict[str, Any]) -> str:
    """The register the document will actually be written in.

    Their choice if they made one, the suggestion otherwise. Nobody should
    have to answer a question about document style before they can download
    anything.
    """
    chosen = str(_value(answers, "done.register") or "")
    if chosen in (SIMPLIFIED, FORMAL):
        return chosen
    return str(register_for(answers)["suggested"])


# ---------------------------------------------------- what disagrees with what

#: "Contradictions, flagged plainly. 'You said nothing gets approved without
#: the committee, and also that free tools don't need approval. Which wins?'
#: This check earns real trust — it proves something read the answers."
#:
#: Every rule here is a genuine conflict, not a preference: two answers that
#: cannot both be operated. A rule that fires on something merely unusual
#: would teach people to skip this screen, which is the one screen that has to
#: be read.
#: Three rules used to live here and no longer can: "nothing moves forward
#: without them" alongside things that do, "publish nothing" alongside things
#: to publish, and "tell no one outside" alongside people who are told. His
#: ruling was that the interface should prevent those rather than report them —
#: "if they click nothing, then gray out and make all others un-clickable" —
#: so they are `Option.exclusive` now. A flag for something a person cannot do
#: is a rule that never fires, which is worse than no rule: it looks like
#: coverage.
CONTRADICTIONS: list[dict[str, Any]] = [
    {
        "key": "vendor-adds-ai-but-we-re-look",
        "when": {"all": [{"key": "proc.added_ai", "is": "nothing"},
                         {"key": "risk.revisit",
                          "includes": "vendor_change"}]},
        "line": "You said the risk level gets looked at again whenever the "
                "vendor changes the tool, and also that a vendor adding AI to "
                "something you already own needs nothing. Which wins?",
        "at": ["5.5", "8.5"],
    },
    {
        "key": "publish-framework-but-internal",
        "when": {"all": [{"key": "watch.publish", "includes": "framework"},
                         {"key": "done.where", "is": "internal"}]},
        "line": "You said you'd publish this framework, and also that it "
                "lives internally only. Which wins?",
        "at": ["9.10", "—"],
    },
    {
        "key": "backup-for-all-but-never-tested",
        "when": {"all": [{"key": "floor.fallback_scope", "is": "all"},
                         {"key": "floor.fallback_tested", "is": "never"}]},
        "line": "You require a written manual backup for every tool, and also "
                "never test one. An untested fallback is a document, not a "
                "plan — is that what you intend?",
        "at": ["6.5a", "6.5b"],
    },
    {
        "key": "accessibility-checked-but-not-required",
        "when": {"all": [{"key": "floor.access_when",
                          "includes": "purchase"},
                         {"key": "floor.access_docs", "is": "no"}]},
        "line": "You check accessibility before purchase, and also don't ask "
                "vendors for accessibility documentation. What are you "
                "checking against?",
        "at": ["6.4b", "6.4c"],
    },
    {
        "key": "no-lookback-after-an-incident",
        "when": {"all": [{"key": "bad.lookback", "is": "no"},
                         {"key": "risk.revisit", "includes": "incident"}]},
        "line": "You look at the risk level again after any incident, and "
                "also never go back over the work the tool already touched. "
                "Which wins?",
        "at": ["5.5", "10.6"],
    },
]


def contradictions(answers: dict[str, Any]) -> list[dict[str, Any]]:
    """Every pair of answers that cannot both be operated.

    Reported, never blocked. The module's firmest rule is that it does not
    refuse an answer — so this says what disagrees with what and hands the
    choice back, which is also the only honest thing it could do: which of two
    answers is right is not something a form can know.
    """
    return [{"key": rule["key"], "line": rule["line"], "at": list(rule["at"])}
            for rule in CONTRADICTIONS if holds(rule["when"], answers)]


# --------------------------------------------------------- the floor, honestly

#: How each floor can be made less strict. "If the user weakened one, it's
#: shown, not hidden."
WEAKENED = {
    "f1": ({"key": "floor.ai_finalises", "is": "some"},
           "Some decisions may be finalized by AI without a person."),
    "f4": ({"key": "floor.access_docs", "is": "no"},
           "Vendors are not asked for accessibility documentation before "
           "purchase."),
    "f5": ({"key": "floor.fallback_tested", "is": "never"},
           "The manual backup is written down but never tested."),
    "f8": ({"key": "floor.plain_scope", "is": "higher_risk"},
           "Only tools in the higher levels of scrutiny need a plain-language "
           "description."),
}


def floor_state(answers: dict[str, Any]) -> list[dict[str, Any]]:
    """The eight, with how strictly each was set and whether it was softened.

    "A short checklist showing all eight requirements are addressed, and how
    strictly. If the user weakened one, it's shown, not hidden."
    """
    step = by_number("06")
    out = []
    for group in (step.groups if step else []):
        if group["key"] == "extra":
            continue
        asked = [q for q in step.questions
                 if q.group == group["key"] and visible(q, answers)]
        settled = [q for q in asked
                   if describe(q, answers)["state"] != "blank"]
        rule, why = WEAKENED.get(group["key"], (None, ""))
        softened = bool(rule) and holds(rule, answers)
        out.append({
            "key": group["key"],
            "number": group["number"],
            "title": group["title"],
            "answered": len(settled),
            "asked": len(asked),
            "settled": len(settled) == len(asked),
            "weakened": softened,
            "weakened_note": why if softened else "",
        })
    return out


# ------------------------------------------------------------------- the gaps

def gaps(answers: dict[str, Any]) -> list[dict[str, str]]:
    """Every "we don't know", as a named gap rather than a blank.

    The spec is explicit — "'We don't know' is always available, and always
    produces a real entry as a documented gap with an owner. Never a blank." A
    framework with holes in it that says so is auditable. One with holes it does
    not mention is not.
    """
    out = []
    for step in STEPS:
        for question in step.questions:
            if not visible(question, answers):
                continue
            value, extras = _unwrap(answers.get(question.key))
            # Clicked, or typed in their own words — "Unknown", "TBD", "n/a".
            # Both are the same admission, and only one of them used to reach
            # this list, so the other went into the framework as policy.
            if value != UNKNOWN and not reads_as_unknown(value):
                continue
            owner = str(extras.get("owner") or "")
            out.append({
                "key": question.key,
                "number": question.number,
                "step": step.number,
                "question": question.prompt,
                "owner": owner,
                "needs_owner": not owner,
            })
    return out


# ===========================================================================
# 00 — orientation
# ===========================================================================

STEP_00 = Step(
    number="00",
    title="What governance actually is",
    strapline="Orientation · no questions · 3–4 minutes",
    writes="Nothing — sets the frame",
    asks=False,
    opening=[
        "Most governmental units own motor vehicles. Somewhere there is an "
        "answer to who may drive one, who maintains it, what happens when one "
        "is wrecked, and when it gets sold at auction. Nobody calls that "
        "“fleet governance philosophy.” It is just how you run an asset "
        "responsibly.",

        "An AI tool is an asset you buy. The same four questions apply, and "
        "they are the only four questions this module asks, in ten different "
        "ways.",

        "Four things make AI different. It can be confidently wrong — a truck "
        "that breaks down stops moving, while a tool that is wrong keeps "
        "producing clean, professional, plausible output. It changes without "
        "you touching it, so the tool you approved in March behaves "
        "differently in September. It arrives inside things you already "
        "bought, usually as a feature in software you own. And it scales "
        "judgment: one bad decision by one employee affects one case, while "
        "one bad rule inside a tool affects every case it touches, in exactly "
        "the same way, until someone notices.",

        "What a framework buys you: your staff get a clear answer instead of "
        "asking nobody or asking everybody. The public gets a straight answer "
        "when they ask whether a machine decided their permit. You get a "
        "defensible record — “we followed our adopted process” is a position, "
        "“it seemed fine” is not. And you keep your exit, because governance "
        "is what stops a pilot from quietly becoming a dependency you cannot "
        "afford to leave.",

        "This takes about 60–90 minutes. You can stop anywhere and come back. "
        "You can send any single question to your legal team, IT contact or "
        "finance office and keep going. You will not be asked to know "
        "anything technical — and if a question needs knowledge you do not "
        "have, “we don't know” is always available and produces a real entry "
        "in your framework as a gap to close later.",

        "There is no correct answer to most of what follows, and adopting "
        "this does not bind your governmental unit in perpetuity. What you "
        "create now can be adjusted as your capacity matures.",
    ],
)


# ===========================================================================
# 01 — the branching spine
# ===========================================================================

#: The offices 1.4 asks about, in the order he asked for them.
#:
#: "4.4, wanted to select Executive Leadership or Administration, but not
#: listed. Add 'Administration/Executive Leadership', then Information
#: Technology, then Legal Counsel." — his ticket. 4.4 only offers offices they
#: said they have at 1.4, so the option had to be added here for it to be
#: offerable there, and the order is his.
FUNCTIONS = [
    Option("exec", "Administration or executive leadership"),
    Option("it", "Information technology"),
    Option("legal", "Legal counsel"),
    Option("security", "Cybersecurity"),
    Option("purchasing", "Purchasing or procurement"),
    Option("records", "Records management"),
    Option("finance", "Finance or budget"),
    Option("hr", "Human resources"),
    Option("comms", "Public information or communications"),
]

HOW_HANDLED = [
    Option("dedicated", "Dedicated staff", "Name the department or unit"),
    Option("part", "One person, part of their job"),
    Option("shared", "Shared with another government"),
    Option("contracted", "Contracted outside"),
    Option("none", "We don't have this"),
]

STEP_01 = Step(
    number="01",
    title="About your organization",
    strapline="The branching spine · 8 questions",
    writes="Purpose · Scope · adapts every later step",
    opening=[
        "This step does the most work in the module. Every answer here changes "
        "what you are asked later — most importantly, which offices actually "
        "exist in your organization.",
    ],
    questions=[
        Question(
            key="org.kind", number="1.1",
            prompt="What kind of organization are you?",
            kind="single",
            help="Confirmed against how you signed in, where we can. Change it "
                 "if it is wrong — everything after this adapts to it.",
            writes=["Purpose", "Scope"],
            options=[
                Option("state", "State agency or department"),
                # Brett, BUG-87D0867C: "1.1 - Wanted to select Federal Agency.
                # Not available."
                Option("federal", "Federal agency or department"),
                Option("county", "County government"),
                Option("city", "City, town, or village"),
                Option("district", "Special district",
                       "Water, sewer, transit, fire, utility, port, drainage"),
                Option("school", "School district or education agency"),
                Option("regional", "Regional council, authority, or commission"),
                Option("tribal", "Tribal government"),
                Option("other", "Other public body"),
            ],
        ),
        Question(
            key="org.size", number="1.2",
            prompt="About how many people work for your organization?",
            kind="single",
            help="This shapes what we suggest later — how decisions are made, "
                 "how many levels of scrutiny are worth running, and whether "
                 "to suggest one person holding several roles.",
            writes=["Purpose"],
            options=[
                Option("u25", "Under 25"),
                Option("25-100", "25 to 100"),
                Option("100-500", "100 to 500"),
                Option("500-2000", "500 to 2,000"),
                Option("2000+", "More than 2,000"),
            ],
        ),
        Question(
            key="org.adopter", number="1.3",
            prompt="Who has the authority to adopt a policy like this one?",
            kind="single",
            help="This is the person or body whose signature makes your "
                 "framework binding rather than advisory. We come back to it "
                 "at the end.",
            writes=["Authority"],
            options=[
                Option("board", "An elected board or council, by vote"),
                Option("elected", "A single elected official"),
                Option("appointed",
                       "An appointed director, administrator, or manager"),
                Option("cabinet", "A state-level executive or cabinet officer"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="org.functions", number="1.4",
            prompt="For each of these, how is it handled in your organization today?",
            kind="matrix",
            rows=FUNCTIONS,
            row_options=HOW_HANDLED,
            above="There are no wrong answers here, and small organizations "
                  "routinely answer “we don't have this” four or five times. We "
                  "ask so that we never tell you to send something to an "
                  "office you do not have.",
            help="Anything marked “we don't have this” is taken out of every "
                 "later list of people to consult, and replaced with a real "
                 "choice: handle it internally, or note that you would need "
                 "outside help. That note becomes a line in your framework.",
            writes=["Scope", "Governance Structure"],
        ),
        Question(
            key="org.cyber_in_it", number="1.4b",
            prompt="Is your cybersecurity team a part of the IT team?",
            kind="single",
            # Only worth asking where there is an IT team to be part of.
            shows_when={"key": "org.functions", "row": "it", "not": "none"},
            help="If it is, we will treat IT as covering cybersecurity and "
                 "stop asking you to consult two offices staffed by the same "
                 "people. If not, cybersecurity gets its own call-out "
                 "wherever it matters.",
            writes=["Governance Structure"],
            options=[
                Option("yes", "Yes — IT covers cybersecurity"),
                Option("no", "No — cybersecurity is separate"),
            ],
        ),
        Question(
            key="org.delegated", number="1.5",
            prompt="Do you run any programs that a state or federal agency "
                   "delegated to you, or that they pay for?",
            kind="single",
            help="If another level of government gave you the authority to run "
                 "a program, or funds it, they usually have expectations about "
                 "how it is run. Using AI in those programs carries extra care.",
            writes=["Scope", "Legal and Federal Compliance"],
            options=[
                Option("yes", "Yes",
                       then_text="Which ones? For example: environmental "
                                 "permitting, health services, transportation, "
                                 "education, housing, benefits, law enforcement"),
                Option("no", "No"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="org.open_records", number="1.6",
            prompt="Are you subject to open records and open meetings laws?",
            kind="single",
            help="Nearly every public body is. It matters because documents an "
                 "AI tool helps produce are usually public records, which "
                 "surprises people.",
            writes=["Records"],
            options=[
                Option("yes", "Yes"),
                Option("no", "No"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        # Brett, BUG-41D9BD0A: "Add to 1.7 'Does your IT program coordinate
        # with a centralized IT authority?' Yes/No. If yes, name." At a state
        # level the answer will largely be yes, and that coordination
        # requirement matters. What was 1.7 is 1.8.
        Question(
            key="org.it_authority", number="1.7",
            prompt="Does your IT program coordinate with a centralized IT "
                   "authority?",
            kind="single",
            help="At the state level this is usually yes — a state IT office "
                 "or chief information officer whose standards your AI use "
                 "has to meet. Naming it here means your framework can point "
                 "to that coordination rather than leave it assumed.",
            writes=["Governance Structure"],
            options=[
                Option("yes", "Yes",
                       then_text="Which one? Name the central IT authority"),
                Option("no", "No"),
            ],
        ),
        Question(
            key="org.unusual", number="1.8",
            prompt="Is there anything unusual about your organization we should "
                   "know before we start?",
            kind="long",
            optional=True,
            unknown_ok=False,
            placeholder="A consent decree, a recent audit finding, a shared "
                        "services agreement, a merger in progress…",
            help="Catches what a form cannot anticipate. Whatever you write "
                 "appears word for word in your final review.",
            writes=["Purpose"],
        ),
    ],
)


# ===========================================================================
# 02 — the honest inventory
# ===========================================================================

STEP_02 = Step(
    number="02",
    title="What you already have",
    strapline="The honest inventory · 5 questions",
    writes="Current state · seeds the tool list",
    opening=[
        "This is not an audit and nobody is in trouble. Most organizations "
        "discover they already have AI running somewhere. Knowing where you "
        "actually stand is the whole point of this step.",
    ],
    questions=[
        Question(
            key="have.used", number="2.1",
            prompt="Has anyone in your organization used AI tools for work?",
            # "Needs to be a multi-check; could have approved tools people are
            # using + unapproved tools they know are being used." Both are
            # usually true at once, and a single choice made an organization
            # pick which half of its own situation to report.
            kind="multi",
            above="Tick everything that applies. Approved use and unapproved "
                  "use are usually both going on.",
            writes=["Current state"],
            options=[
                Option("permitted", "Yes, with permission"),
                Option("informal", "Yes, informally or on their own"),
                Option("no", "No, not that we know of"),
                Option(UNKNOWN, "We honestly do not know"),
            ],
        ),
        Question(
            key="have.software", number="2.2",
            prompt="Which of these do you use?",
            kind="multi",
            above="Any of these may already include AI features.",
            help="Vendors add AI features to software you already own, without "
                 "a new purchase and without a new decision. This is where AI "
                 "usually turns up first, and it is the most common thing a "
                 "governance framework misses.",
            writes=["Current state"],
            options=[
                Option("office", "Office software with a built-in assistant",
                       "Microsoft Copilot, Google Gemini, ChatGPT, Claude"),
                Option("permitting",
                       "Permitting, licensing, or case management software"),
                Option("chat", "A chat window on your website"),
                Option("records", "Document or records management"),
                Option("gis", "Mapping or GIS"),
                Option("scada", "Operations monitoring or SCADA"),
                Option("erp", "Financial, ERP, or billing systems"),
                Option("hr", "Hiring or HR software"),
                Option("cameras", "Security cameras or access control"),
                Option("transcription", "Meeting transcription or note-taking"),
                Option("translation", "Translation services"),
                Option("phone", "Phone system or call center software"),
                Option("none", "None of these"),
                Option(UNKNOWN, "Not sure"),
                Option("other", "Something else", then_text="What is it?"),
            ],
        ),
        Question(
            key="have.policy", number="2.3",
            prompt="Do you have any written rule today about staff using AI?",
            kind="single",
            help="If you have one, your framework will say how the two "
                 "documents relate and which one controls where they "
                 "disagree — rather than quietly replacing it.",
            writes=["Current state"],
            options=[
                Option("adopted", "Yes, a formally adopted policy",
                       then_text="Paste it, or its title",
                       then_upload=True),
                Option("informal", "Informal guidance, an email, or a verbal rule"),
                Option("nothing", "Nothing written"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="have.asked", number="2.4",
            prompt="Has anyone outside your organization asked you about AI?",
            kind="multi",
            help="It tells us how much public-facing pressure you are under, "
                 "which affects how much of your framework should be written "
                 "for an outside reader.",
            writes=["Transparency"],
            options=[
                Option("public", "A resident or member of the public"),
                Option("board", "Your board or elected officials"),
                Option("press", "A reporter"),
                Option("auditor", "An auditor"),
                Option("partner", "A state or federal partner"),
                Option("attorney", "An attorney, or in litigation"),
                Option("vendor", "A vendor selling something"),
                Option("noone", "No one yet"),
            ],
        ),
        Question(
            key="have.project", number="2.5",
            prompt="Is there an AI project someone wants to start right now?",
            kind="single",
            help="If you describe it, we use it as the running example for the "
                 "rest of the module — “would your rule let this project "
                 "through?” — which is the fastest way to make an abstract "
                 "question concrete.",
            writes=["Current state"],
            options=[
                Option("yes", "Yes",
                       then_text="Describe it in a sentence or two, in your "
                                 "own words"),
                Option("no", "No"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
    ],
)


# ===========================================================================
# 03 — drawing the boundary
# ===========================================================================

STEP_03 = Step(
    number="03",
    title="What counts as AI here",
    strapline="Drawing the boundary · 4 questions",
    writes="Scope · Definitions",
    opening=[
        "Defining what counts as artificial intelligence is genuinely hard. Too "
        "wide and you are reviewing spellcheck; too narrow and things slip "
        "through. Here is a starting point — adjust it to match your "
        "understanding.",
        "Everything below starts checked at a sensible default. Most people "
        "accept it, which is fine. The ones who change it are the ones who "
        "needed to.",
    ],
    questions=[
        Question(
            key="scope.covered", number="3.1",
            can_add="Add a use of your own",
            prompt="Which of these should your rules cover?",
            kind="multi",
            above="All pre-selected. Uncheck anything that should not count.",
            writes=["Scope", "Definitions"],
            options=[
                # `prose` is the third-person form the *document* uses. His
                # labels are written to be read above a checkbox and address
                # the reader as "you", which is right on screen and wrong in
                # an adopted instrument. No label is changed.
                Option("generative", "Tools that write text, images, or code "
                                     "for you", recommended=True,
                       prose="tools that write text, images or code"),
                Option("predictive", "Tools that predict or score things",
                       "For example: {predicts}", recommended=True),
                Option("recognition",
                       "Tools that recognize things in photos, video, or audio",
                       recommended=True),
                Option("retrieval",
                       "Tools that answer questions using your own documents",
                       recommended=True,
                       prose="tools that answer questions using the "
                             "organization's own documents"),
                Option("embedded", "AI features built into software you already "
                                   "bought", recommended=True,
                       prose="AI features built into software already "
                             "purchased"),
                Option("contractor", "AI a contractor or consultant uses to do "
                                     "work for you",
                       "Easy to forget. If a consultant uses AI to draft "
                       "something you then adopt as your own, your name is on "
                       "the output.", recommended=True,
                       prose="AI used by a contractor or consultant doing "
                             "work for the organization"),
            ],
        ),
        Question(
            key="scope.excluded", number="3.2",
            can_add="Add something else that should not count",
            prompt="And which of these should not count?",
            kind="multi",
            above="All pre-selected. A framework that technically covers "
                  "everything gets ignored in practice — naming what is out "
                  "keeps what is in credible.",
            writes=["Scope", "Definitions"],
            options=[
                Option("formulas", "Spreadsheet formulas and calculations",
                       recommended=True),
                Option("dashboards", "Dashboards and reports that only display "
                                     "data you gave them", recommended=True),
                Option("automation", "Automation that follows fixed steps you "
                                     "created", "If this, then that",
                       recommended=True),
                Option("spellcheck", "Spellcheck and grammar tools",
                       recommended=True),
                Option("search", "Ordinary keyword search", recommended=True),
            ],
        ),
        Question(
            key="scope.arbiter", number="3.3",
            prompt="When it isn't clear whether something counts, who decides?",
            kind="short",
            placeholder="A role title",
            help="Name one role, not a committee. Borderline cases come up "
                 "constantly and you need a tiebreaker. A role title outlasts "
                 "whoever holds it today.",
            writes=["Definitions", "Governance Structure"],
        ),
        Question(
            key="scope.review", number="3.4",
            prompt="Should that call be reviewed by anyone afterward?",
            kind="single",
            writes=["Definitions"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("standalone", "No, the decision stands on its own"),
                Option("objection", "Only if someone objects"),
            ],
        ),
    ],
)


# ===========================================================================
# 04 — the load-bearing step
# ===========================================================================

CONSULTED = [
    Option("exec", "Administration or executive leadership", recommended=True,
           shows_when={"key": "org.functions", "row": "exec", "not": "none"}),
    Option("it", "Information technology", recommended=True,
           shows_when={"key": "org.functions", "row": "it", "not": "none"}),
    Option("legal", "Legal counsel", recommended=True,
           shows_when={"key": "org.functions", "row": "legal", "not": "none"}),
    # Only where cybersecurity is a thing to ask separately. "If yes, then IT
    # covers cybersecurity and we do not need to individually call out the
    # Cybersecurity team" — so answering 1.4b yes folds this into IT rather
    # than asking them to consult two offices staffed by the same people.
    Option("security", "Cybersecurity", recommended=True,
           shows_when={"all": [
               {"key": "org.functions", "row": "security", "not": "none"},
               {"key": "org.cyber_in_it", "not": "yes"}]}),
    Option("purchasing", "Purchasing", recommended=True,
           shows_when={"key": "org.functions", "row": "purchasing",
                       "not": "none"}),
    Option("finance", "Finance", recommended=True,
           shows_when={"key": "org.functions", "row": "finance", "not": "none"}),
    Option("program", "The program that will actually use it", recommended=True),
    Option("hr", "Human resources", "If it affects staff",
           shows_when={"key": "org.functions", "row": "hr", "not": "none"}),
    Option("comms", "Public information or records requests",
           shows_when={"key": "org.functions", "row": "comms", "not": "none"}),
    Option("records", "Records management",
           shows_when={"key": "org.functions", "row": "records", "not": "none"}),
    Option("affected", "Someone who represents the people it affects"),
]

STEP_04 = Step(
    number="04",
    title="Who decides",
    strapline="The load-bearing step · 10 questions",
    writes="Governance structure · Authority · Amendment",
    opening=[
        "Every governmental unit faces the same question: who is accountable, "
        "and how many people were involved in a decision made on behalf of the "
        "organization?",
        "Four shapes are common. Pick the one that matches how your "
        "organization already makes decisions. A new committee that does not "
        "actually convene is worse than one named person who shows up.",
    ],
    questions=[
        Question(
            key="who.shape", number="4.1",
            prompt="Which of these shapes fits your organization?",
            kind="single",
            writes=["Governance Structure"],
            # Leans on size, and never disables the others. Picking a heavier
            # shape than the size suggests earns one line about sustainability
            # and is then accepted.
            #
            # First match wins, so the most specific rule goes first. A
            # delegated programme raises the recommendation whatever the size —
            # a twenty-person district running a federally delegated programme
            # carries the exposure of a much larger body, and the spec ties the
            # formal-council shape to delegation as well as to headcount. With
            # the size rules first this never fired.
            recommend_when=[
                {"if": {"key": "org.delegated", "is": "yes"}, "then": "council"},
                {"if": {"key": "org.size", "is": "u25"}, "then": "one"},
                {"if": {"key": "org.size", "in": ["25-100", "100-500"]},
                 "then": "group"},
                {"if": {"key": "org.size", "in": ["500-2000", "2000+"]},
                 "then": "council"},
            ],
            options=[
                Option("one", "One accountable person",
                       prose="a single named person",
                       note="A named individual approves AI use and asks others for "
                       "input as needed. Fast and clear. Depends entirely on "
                       "one person being available and informed. Common under "
                       "50 employees."),
                Option("group", "A small standing group",
                       "Three to five people who meet on a set schedule and "
                       "write down what they decide. Balances speed against a "
                       "range of expertise. Common in mid-size organizations.",
                       prose="a small standing group that meets on a set "
                             "schedule"),
                Option("council", "A formal council with a written charter",
                       "Defined seats, quorum, voting rules, published "
                       "procedures. Most durable and most defensible; also the "
                       "most work to sustain. Fits large organizations, or "
                       "anyone with high public exposure.",
                       prose="a formal council working to a written charter"),
                # Recommended by default, and it earns it. "For most
                # organizations it is the right answer and it is the one nobody
                # thinks of." Where a size has been given the rules above take
                # over; before that, this is the standing suggestion.
                Option("existing", "A group you already have takes it on",
                       "Your executive team, IT steering committee, safety "
                       "committee or risk group adds AI to its existing "
                       "agenda. Frequently the lowest-effort answer that "
                       "actually works.", recommended=True,
                       prose="a group this organization already has, which "
                             "has taken AI onto its agenda"),
            ],
        ),
        # 4.2 and 4.3 both follow from 4.1, and both used to ignore it.
        #
        # "Asks for 'Which roles hold that responsibility?' Should only be
        # which Role if it's one person. 4.1/4.2 need to be adaptive. If 4.1
        # selects One accountable Person, 4.2 should ask who is that person?"
        #
        # Handled with `instead_when` rather than two questions sharing a key:
        # `by_key` returns the first match and knows nothing about answers, so
        # a second copy would have taken the clause out of the finished
        # document whenever the other copy was the visible one.
        Question(
            key="who.seats", number="4.2",
            prompt="Which roles hold that responsibility?",
            kind="rows",
            above="Roles, not people. Whoever holds the role holds the "
                  "responsibility, and it stays true when they move on.",
            help="If one role covers three of these, list it once. That is "
                 "normal in a small organization and your framework will say "
                 "so rather than pretending otherwise. Naming the individuals "
                 "who currently hold these roles is the workflow system's job, "
                 "not this document's.",
            instead_when=[{
                "if": {"key": "who.shape", "is": "one"},
                "prompt": "Which role holds that responsibility?",
                "kind": "short",
                "placeholder": "One role title",
                "above": "A role, not a person. Whoever holds the role holds "
                         "the responsibility, and it stays true when they "
                         "move on.",
                "help": "You said one accountable person, so this is the one "
                        "role that answers for AI decisions. Naming the "
                        "individual who currently holds it is the workflow "
                        "system's job, not this document's.",
            }],
            writes=["Governance Structure"],
        ),
        # "4.1/4.3 should also be adaptive like 4.1." There is nobody to
        # disagree with when one person decides, so the question becomes who
        # stands in when that person is unavailable — the real gap a
        # single-decider structure has, and worth a named answer.
        Question(
            key="who.tiebreak", number="4.3",
            prompt="Who has the final say when there's disagreement?",
            kind="short",
            placeholder="One role title",
            help="One role. Consensus is a good practice and a bad rule — "
                 "every governance structure needs a documented tiebreaker.",
            instead_when=[{
                "if": {"key": "who.shape", "is": "one"},
                "prompt": "Who decides when that person is unavailable?",
                "help": "One role. A single accountable person is fast and "
                        "clear until they are on leave — a named stand-in is "
                        "what keeps it working, and your framework will say "
                        "who it is.",
            }],
            writes=["Authority"],
        ),
        Question(
            key="who.consulted", number="4.4",
            prompt="Before an AI tool is approved for use, who has to be asked?",
            kind="multi",
            help="Only the offices you told us you have are listed.",
            writes=["Governance Structure"],
            options=CONSULTED,
        ),
        Question(
            key="who.missing", number="4.4b",
            prompt="And for the offices you don't have, what happens instead?",
            kind="matrix",
            rows_from={"key": "org.functions", "where": "none",
                       "unless": {"security": {"key": "org.cyber_in_it",
                                               "is": "yes"}}},
            shows_when={"key": "org.functions", "answered": True},
            above="You told us these are not offices you have. Neither answer "
                  "is wrong — the second becomes a named gap in your framework "
                  "with an owner, which is better than a silent hole.",
            writes=["Governance Structure"],
            row_options=[
                Option("internal", "Handle it internally"),
                Option("outside", "We would need outside help"),
            ],
        ),
        Question(
            key="who.cadence", number="4.5",
            prompt="How often does this person or group look at AI matters?",
            kind="single",
            writes=["Governance Structure"],
            options=[
                Option("onrequest", "As requests come in"),
                Option("monthly", "Monthly"),
                Option("quarterly", "Quarterly"),
                Option("biannual", "Twice a year"),
                Option("annual", "Once a year"),
            ],
        ),
        Question(
            key="who.without", number="4.6",
            prompt="What can move forward without them?",
            kind="multi",
            help="If everything requires approval, staff may route around you "
                 "and you end up with less oversight rather than more. Decide "
                 "now what genuinely does not need a meeting.",
            writes=["Governance Structure"],
            options=[
                Option("under_amount", "Anything under a set amount",
                       then_text="What amount?"),
                Option("lowest_risk", "Tools in your lowest level of scrutiny",
                       "You set those levels in step 05"),
                Option("free", "Free tools and trials",
                       "Worth knowing: free tools often carry the worst data "
                       "terms"),
                Option("short_pilot", "Short pilots",
                       then_text="Up to how many days?"),
                Option("nothing", "Nothing — everything goes through the "
                                  "process", exclusive=True),
            ],
        ),
        Question(
            key="who.record", number="4.7",
            prompt="Where do these decisions get written down, and who keeps "
                   "them?",
            kind="short",
            placeholder="Meeting minutes, a shared folder, {record}, "
                        "a spreadsheet the clerk maintains…",
            # Brett, BUG-8EC4E0E9: sub-text for 4.7, "or something like that".
            help="Explore the Subscription version of GoverningAI.US to "
                 "integrate your framework and management system.",
            writes=["Governance Structure", "Records"],
        ),
        Question(
            key="who.signs", number="4.8",
            prompt="Who signs or adopts this framework to make it official?",
            kind="single",
            help="Pre-filled from what you told us in 1.3.",
            writes=["Authority"],
            options=[
                Option("board", "An elected board or council, by vote"),
                Option("elected", "A single elected official"),
                Option("appointed",
                       "An appointed director, administrator, or manager"),
                Option("cabinet", "A state-level executive or cabinet officer"),
            ],
            recommend_when=[
                {"if": {"key": "org.adopter", "is": "board"}, "then": "board"},
                {"if": {"key": "org.adopter", "is": "elected"},
                 "then": "elected"},
                {"if": {"key": "org.adopter", "is": "appointed"},
                 "then": "appointed"},
                {"if": {"key": "org.adopter", "is": "cabinet"},
                 "then": "cabinet"},
            ],
        ),
        Question(
            key="who.amend", number="4.9",
            prompt="Who can change this framework later, and how?",
            kind="single",
            writes=["Amendment"],
            options=[
                Option("same", "The same authority that adopted it",
                       recommended=True),
                Option("group_notice", "The person or group from 4.1, with "
                                       "notice to the adopting authority"),
                Option("group_alone", "The person or group from 4.1, on their "
                                      "own"),
            ],
        ),
        Question(
            key="who.review", number="4.10",
            prompt="How often should the framework itself come back for review?",
            kind="single",
            writes=["Amendment"],
            options=[
                Option("annual", "Every year",
                       "Recommended while the law is still moving",
                       recommended=True),
                Option("biennial", "Every two years"),
                Option("onchange", "Only when something changes in the law"),
                Option("other", "Something else", then_text="How often?"),
            ],
        ),
    ],
)


# ===========================================================================
# 05 — how much scrutiny, and when
# ===========================================================================

#: 5.1's factors. Two of them do not apply to everyone, and one of them is the
#: single most important factor for the organisations that have it.
RISK_FACTORS = [
    Option("consequence",
           "It affects someone's money, permit, license, benefits, or job"),
    Option("public", "The public interacts with it directly"),
    Option("sensitive",
           "It uses personal, medical, student, or confidential information"),
    Option("irreversible", "A mistake would be hard or impossible to undo"),
    # Only where there is a delegated programme to touch.
    Option("delegated",
           "It touches a program another government delegated to you or funds",
           shows_when={"key": "org.delegated", "is": "yes"}),
    Option("disparate",
           "It could affect one group of people differently than another"),
    # "For a water district this is the factor that matters most, and
    # defaulting it low would be a serious miss." So it arrives already set to
    # major for the bodies that run the pipes, the pumps and the dispatch.
    Option("safety",
           "It touches safety-critical operations — water treatment, dispatch, "
           "traffic control, power",
           preset_when=[{"if": {"key": "org.kind", "in": ["district",
                                                          "regional"]},
                         "then": "major"}]),
    Option("news", "Getting it wrong would end up in the news"),
]

RISK_WEIGHTS = [
    Option("none", "Not a concern"),
    Option("some", "Some"),
    Option("major", "Major"),
]

STEP_05 = Step(
    number="05",
    title="How much scrutiny, and when",
    strapline="Graduated oversight · 5 questions",
    writes="Risk management",
    opening=[
        "Risk here means one thing: what happens if the AI is wrong.",
        "A tool that drafts meeting minutes and a tool that flags permit "
        "applications for denial should not go through the same process. This "
        "step helps you determine how you tell them apart.",
    ],
    questions=[
        Question(
            key="risk.factors", number="5.1",
            can_add="Add a factor of your own",
            prompt="How much does each of these matter in your work?",
            kind="matrix",
            rows=RISK_FACTORS,
            row_options=RISK_WEIGHTS,
            writes=["Risk Management"],
        ),
        Question(
            key="risk.levels", number="5.2",
            prompt="How many levels of scrutiny do you want?",
            kind="single",
            help="More tiers than an organization can staff is a common "
                 "failure.",
            writes=["Risk Management"],
            # Two under twenty-five people, three for everyone else.
            recommend_when=[
                {"if": {"key": "org.size", "is": "u25"}, "then": "two"},
            ],
            options=[
                Option("two", "Two — routine and elevated",
                       "Simplest to run",
                       prose="two levels of scrutiny, routine and elevated"),
                Option("three", "Three — low, moderate, high",
                       recommended=True,
                       prose="three levels of scrutiny — low, moderate and "
                             "high"),
                Option("four",
                       "Four — for organizations with a wide range of uses",
                       prose="four levels of scrutiny"),
            ],
        ),
        Question(
            key="risk.tiers", number="5.3",
            prompt="For each level, what has to happen?",
            kind="tiers",
            rows_from={"tiers": True},
            # Nothing to fill in until they have said how many levels there
            # are. Pre-filling a grid against levels they have not chosen —
            # or worse, against "we don't know" — is a guess presented as
            # their answer.
            needs={"key": "risk.levels",
                   "unless": {"all": [
                       {"key": "risk.levels", "answered": True},
                       {"key": "risk.levels", "not": UNKNOWN}]},
                   "say": "Answer 5.2 first — what has to happen depends on "
                          "how many levels of scrutiny you decide to have."},
            above="Filled in already, based on how you answered step 04. "
                  "Change anything that isn't right — editing a draft is far "
                  "easier than facing an empty grid.",
            writes=["Risk Management"],
            tier_fields=[
                # Only when they asked for four levels, because he named the
                # other two sets himself and left this one open: "Let them fill
                # in the levels. 2 and 3 being pre-loaded helps cut down
                # onboarding; if they want to configure to that degree, let
                # them."
                {"key": "name", "label": "What you call this level",
                 "ask": "Your own word for it.", "kind": "short",
                 "shows_when": {"key": "risk.levels", "is": "four"},
                 "defaults": {}},
                # Not the person who will use it. His correction: "It can't be
                # the person that uses it, low-level staff could just 'approve'
                # themselves and integrate it." So even the lowest level goes
                # to somebody who holds approval authority.
                {"key": "reviews", "label": "Who reviews it",
                 "ask": "Which of the people from Step 4 have to see it?",
                 "kind": "short",
                 "defaults": {
                     "routine": "{approver}",
                     "elevated": "{decider}",
                     "minimal": "{approver}",
                     "low": "{approver}",
                     "moderate": "{decider}",
                     # "with legal and IT asked first" only where 1.4 said
                     # there is a legal office and an IT office to ask.
                     "high": "{decider}{first_ask}",
                 }},
                {"key": "written", "label": "What gets written down",
                 "ask": "What has to exist on paper before it's approved?",
                 "kind": "short",
                 "defaults": {
                     "routine": "A line on the list of tools, and what it does",
                     "elevated": "What it does, what information it touches, "
                                 "who owns it, and the manual backup",
                     "minimal": "A line on the list of tools, and what it does",
                     "low": "A line on the list of tools, what it does, and "
                            "who owns it",
                     "moderate": "What it does, what information it touches, "
                                 "and who owns it",
                     # Brett, BUG-1D7F2D29: "All of THE ABOVE", not "all of
                     # that".
                     "high": "All of the above, plus the manual backup and a "
                             "plain-language description",
                 }},
                {"key": "recheck", "label": "How often it's re-checked",
                 "ask": "Once approved, when do you look again? Quarterly is "
                        "recommended for your highest level; yearly is the "
                        "minimum for any of them.",
                 "kind": "single",
                 "options": [
                     {"value": "monthly", "label": "Monthly"},
                     {"value": "quarterly", "label": "Quarterly"},
                     {"value": "biannual", "label": "Twice a year"},
                     {"value": "annual", "label": "Once a year"},
                 ],
                 "defaults": {"routine": "annual", "elevated": "quarterly",
                              "minimal": "annual", "low": "annual",
                              "moderate": "biannual", "high": "quarterly"}},
                {"key": "nomeeting",
                 "label": "Can it be approved without a meeting",
                 "ask": "Yes or no.", "kind": "single",
                 "options": [{"value": "yes", "label": "Yes"},
                             {"value": "no", "label": "No"}],
                 "defaults": {"routine": "yes", "elevated": "no",
                              "minimal": "yes", "low": "yes",
                              "moderate": "yes", "high": "no"}},
            ],
        ),
        Question(
            key="risk.worst", number="5.4",
            prompt="If a tool rates high on any single factor, should it "
                   "automatically get the highest level of scrutiny — even if "
                   "everything else is low?",
            kind="single",
            help="Averaging hides significant risks. A tool that is low-risk "
                 "in seven ways and severe in one is a severe-risk tool. This "
                 "rule stops the average from burying the potential impacts of "
                 "a high-risk failure.",
            writes=["Risk Management"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("no", "No — use the overall picture"),
            ],
        ),
        Question(
            key="risk.revisit", number="5.5",
            prompt="When should the risk level be looked at again?",
            kind="multi",
            writes=["Risk Management"],
            options=[
                Option("before_approval", "Before it's approved",
                       recommended=True),
                Option("before_live", "Before it goes live", recommended=True),
                Option("annual", "Once a year", recommended=True),
                Option("vendor_change", "Whenever the vendor changes the tool",
                       recommended=True),
                Option("incident", "After any incident", recommended=True),
                Option("law_change", "When a law or rule changes",
                       recommended=True),
            ],
        ),
    ],
)


# ===========================================================================
# 06 — the floor
# ===========================================================================

#: The eight, each with the rule in plain words and one line on why it exists.
#: "Each is presented the same way: the rule in plain words, one line on why it
#: exists, then the choices that genuinely are theirs."
FLOORS = [
    {"key": "f1", "number": "Floor 1",
     "title": "The Human in Authority – A person makes the final call",
     "badge": "Required",
     "why": "No AI finalizes an action that affects a person's rights, money, "
            "standing, or employment. AI can draft, sort, flag, and recommend, "
            "but a person decides."},
    {"key": "f2", "number": "Floor 2", "title": "Keep a list of every AI tool",
     "badge": "Required",
     "why": "One list, one owner, every tool. This is the piece everything "
            "else depends on: you cannot review, audit, or retire what nobody "
            "wrote down."},
    {"key": "f3", "number": "Floor 3",
     "title": "Tell people when they're dealing with AI", "badge": "Required",
     "why": "If a member of the public is interacting with an AI tool, or "
            "receiving something an AI tool produced, they're told and they "
            "can always reach a person instead."},
    {"key": "f4", "number": "Floor 4",
     "title": "It has to work for people with disabilities",
     "badge": "Required by law",
     "why": "Public-facing AI tools must meet the same accessibility "
            "standards as everything else you put in front of the public. For "
            "most state and local governments, the technical standard is WCAG "
            "2.1 Level AA under the ADA Title II web rule."},
    {"key": "f5", "number": "Floor 5",
     "title": "You can turn it off and still do the work", "badge": "Required",
     "why": "Every tool in use has a written way to do the job without it. "
            "This helps your organization put AI tools to use quickly and "
            "effectively and is what keeps a convenience from becoming a "
            "dependency you cannot afford to leave."},
    {"key": "f6", "number": "Floor 6", "title": "Your data stays yours",
     "badge": "Required",
     "why": "A vendor may not use your information to build or improve their "
            "products, and you get it back when you leave."},
    {"key": "f7", "number": "Floor 7", "title": "Somebody's name is on it",
     "badge": "Required",
     "why": "Every tool has a person accountable for it, not just a "
            "department. When something goes wrong, “the system” is not an "
            "answer anyone accepts."},
    {"key": "f8", "number": "Floor 8",
     "title": "You can explain it in plain language", "badge": "Required",
     "why": "For every tool, someone can say in a few sentences what it does, "
            "what information it uses, and how it affects decisions without "
            "jargon. If nobody can, that is a risk flag to the public."},
    {"key": "extra", "number": "Optional", "title": "Good practice, not rules",
     "badge": "Optional",
     "why": "Nothing below is required of you. They are the additions "
            "organizations most often wish they had put in from the start."},
]

#: Floor 7 offers only the roles the organisation said it has, and says out
#: loud when one person holds several. "Offers only roles that exist per 1.4,
#: and explicitly permits one person to hold several — with a line in the
#: framework acknowledging the concentration rather than hiding it."
NAMED_CONTACTS = [
    Option("owner", "Someone in the program that uses it, commonly called a "
                    "‘product owner’", "Required"),
    Option("technical", "A technical contact",
           shows_when={"key": "org.functions", "row": "it", "not": "none"}),
    Option("legal", "A legal contact",
           shows_when={"key": "org.functions", "row": "legal", "not": "none"}),
    Option("budget", "A budget contact",
           shows_when={"key": "org.functions", "row": "finance",
                       "not": "none"}),
]

STEP_06 = Step(
    number="06",
    title="Your non-negotiables",
    strapline="The floor · 8 required, plus anything you want to add",
    writes="Operating principles · Transparency · Accessibility",
    opening=[
        "Everything so far has been your choice. These eight are different. "
        "They come from law, from federal guidance, and from what actually "
        "goes wrong in practice. Here, you are deciding how strict your "
        "version is, not whether you have one.",
    ],
    groups=FLOORS,
    closing={
        "title": "The floor establishes ongoing responsibility",
        "body": [
            "The most common misunderstanding about governance is that it "
            "happens at purchase. Each of these eight comes back at points "
            "across a tool's life.",
        ],
        "table": {
            "head": ["Requirement", "Set", "Checked again"],
            "rows": [
                ["1 · A human decides", "Before approval",
                 "Any time the tool's role changes, or after an incident"],
                ["2 · Keep a list", "At approval",
                 "On your list-accuracy schedule, and whenever a tool changes "
                 "or retires"],
                ["3 · Tell people", "Before it goes live",
                 "When the tool changes, and when the wording is revised"],
                ["4 · Accessibility", "Before purchase and before launch",
                 "Annually, and after any vendor change"],
                ["5 · You can turn it off", "Before it goes live",
                 "Whenever the fallback is tested"],
                ["6 · Your data stays yours", "In the agreement",
                 "At renewal, and whenever the vendor changes the AI"],
                ["7 · Somebody's name is on it", "At approval",
                 "Whenever that person changes roles or leaves"],
                ["8 · You can explain it", "Before it goes live",
                 "Whenever the tool changes enough that the description stops "
                 "being true"],
            ],
        },
        "after": "Tracking eight recurring obligations across every tool you "
                 "own is exactly the work a spreadsheet stops handling "
                 "somewhere around the fourth tool.",
    },
    questions=[
        # ---------------------------------------------------------- floor 1
        Question(
            key="floor.final_action", number="6.1a", group="f1",
            prompt="In your organization, what counts as a “final action”?",
            kind="long",
            placeholder="{decision}…",
            help="For example: {decision}. Also worth naming: terminating a "
                 "service, a hiring decision.",
            writes=["Operating Principles"],
        ),
        Question(
            key="floor.ai_finalises", number="6.1b", group="f1",
            prompt="Are there any decisions you would allow AI to finalize on "
                   "its own?",
            kind="single",
            writes=["Operating Principles", "Risk Management"],
            # "Add option 2, yes, decided on a case-by-case basis." Between
            # "none" and a list written in advance there is the answer most
            # organizations actually give — that it depends, and somebody
            # decides each time. Offering only the other two made them either
            # overstate the prohibition or invent a list they do not have.
            options=[
                Option("none", "No, none", recommended=True),
                Option("some", "Yes — list them",
                       then_text="Which ones, and why is it safe to?"),
                Option("case_by_case",
                       "Yes — decided on a case-by-case basis",
                       then_text="Who decides, and against what test?"),
            ],
        ),
        # ---------------------------------------------------------- floor 2
        Question(
            key="floor.list_owner", number="6.2a", group="f2",
            prompt="Who keeps the list?",
            kind="short", placeholder="One role title",
            writes=["Operating Principles"],
        ),
        Question(
            key="floor.list_fields", number="6.2b", group="f2",
            can_add="Add something else to record",
            prompt="What do you want recorded for each tool?",
            kind="multi",
            writes=["Operating Principles"],
            options=[
                Option("name", "Name and vendor", recommended=True),
                Option("what", "What it does in one sentence",
                       recommended=True),
                Option("owner", "Who owns it", recommended=True),
                Option("data", "What information it touches",
                       recommended=True),
                Option("risk", "Its risk level", recommended=True),
                Option("approved", "Date approved", recommended=True),
                Option("reviewed", "Date last reviewed", recommended=True),
                Option("cost", "What it costs"),
                Option("contract", "When the contract ends"),
                Option("offswitch", "How to turn it off", recommended=True),
            ],
        ),
        Question(
            key="floor.list_checked", number="6.2c", group="f2",
            prompt="How often is the list checked for accuracy?",
            kind="single",
            writes=["Operating Principles"],
            options=[
                Option("quarterly", "Quarterly"),
                Option("biannual", "Twice a year"),
                Option("annual", "Annually"),
                Option("asupdated", "As updated"),
            ],
        ),
        Question(
            key="floor.unlisted", number="6.2d", group="f2",
            prompt="What happens if someone uses a tool that isn't on the "
                   "list?",
            # "6.2d — allow for multi-select." More than one of these is
            # usually true at once: it is a policy violation *and* IT blocks
            # it *and* it has to be registered within a fortnight.
            kind="multi",
            writes=["Operating Principles"],
            options=[
                Option("violation", "Treated as a policy violation"),
                Option("register", "Must be registered",
                       then_text="Within how many days?"),
                Option("blocked", "Blocked by IT",
                       shows_when={"key": "org.functions", "row": "it",
                                   "not": "none"}),
                Option("other", "Something else", then_text="What happens?"),
            ],
        ),
        # ---------------------------------------------------------- floor 3
        Question(
            key="floor.disclose_where", number="6.3a", group="f3",
            prompt="Where should disclosure appear?",
            kind="multi",
            writes=["Transparency"],
            options=[
                Option("chat", "Website chat"),
                Option("phone", "Phone systems"),
                Option("letters", "Letters and notices"),
                Option("forms", "Public forms"),
                Option("reports", "Published reports"),
                Option("decisions", "Permits and decisions"),
            ],
        ),
        Question(
            key="floor.reach_human", number="6.3b", group="f3",
            prompt="How does someone reach a human instead?",
            kind="short",
            placeholder="A phone number, a counter, a named office…",
            # No opt-out on this one, which is why it is the only question in
            # the step that cannot be answered "we don't know".
            unknown_ok=False,
            help="This one has no opt-out. “Determined on a case-by-case "
                 "basis” is an acceptable answer, and it will need a route "
                 "built behind it.",
            writes=["Transparency"],
        ),
        Question(
            key="floor.disclose_who", number="6.3c", group="f3",
            prompt="Who writes the disclosure wording, and who approves it?",
            kind="short", placeholder="Role title",
            also={"key": "approver", "label": "And who approves it",
                  "kind": "short", "placeholder": "Role title"},
            writes=["Transparency"],
        ),
        Question(
            key="floor.disclose_home", number="6.3d", group="f3",
            prompt="Where does the approved wording live so everyone uses the "
                   "same version?",
            kind="short",
            placeholder="A named page, folder or system",
            help="One approved wording, in one place, is easier to keep right "
                 "than six copies that drift apart.",
            writes=["Transparency"],
        ),
        # ---------------------------------------------------------- floor 4
        Question(
            key="floor.access_owner", number="6.4a", group="f4",
            prompt="Who is responsible for checking accessibility?",
            kind="short", placeholder="One role title",
            writes=["Accessibility"],
        ),
        Question(
            key="floor.access_when", number="6.4b", group="f4",
            prompt="When is it checked?",
            kind="multi",
            writes=["Accessibility"],
            options=[
                Option("purchase", "Before purchase", recommended=True),
                Option("live", "Before it goes live", recommended=True),
                Option("annual", "Once a year", recommended=True),
                Option("vendor", "After the vendor changes it",
                       recommended=True),
            ],
        ),
        Question(
            key="floor.access_docs", number="6.4c", group="f4",
            prompt="Do you require vendors to provide accessibility "
                   "documentation before purchase?",
            kind="single",
            writes=["Accessibility", "Procurement"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("no", "No"),
            ],
        ),
        # ---------------------------------------------------------- floor 5
        Question(
            key="floor.fallback_scope", number="6.5a", group="f5",
            prompt="Does every tool need a written manual backup?",
            kind="single",
            writes=["Operating Principles"],
            # The levels named here are the ones they chose at 5.2 — see
            # `_tier_words`. With only two levels the middle option is the
            # same as the last one, so it is not offered at all.
            options=[
                Option("all", "All tools", prose="every tool"),
                Option("mod_high", "{upper_tiers} tools only",
                       shows_when={"key": "risk.levels", "not": "two"},
                       recommended=True,
                       prose="tools in the upper levels of scrutiny"),
                Option("high", "{top_tier} tools only",
                       prose="tools in the highest level of scrutiny",
                       recommend_when=[
                           {"if": {"key": "risk.levels", "is": "two"},
                            "because": "you chose two levels of scrutiny"}]),
            ],
        ),
        Question(
            key="floor.fallback_tested", number="6.5b", group="f5",
            prompt="How often is that backup actually tested?",
            kind="single",
            writes=["Operating Principles"],
            # His line, verbatim, and his instruction that it is a nudge:
            # "show one line... and let the answer stand."
            consequences=[
                {"if": {"key": "floor.fallback_tested", "is": "never"},
                 "say": "An untested fallback is a document, not a plan. Your "
                        "answer stands — it will appear in your framework as "
                        "written, and on the floor checklist as a place you "
                        "chose to be less strict."},
            ],
            options=[
                Option("annual", "Annually", recommended=True),
                Option("biannual", "Twice a year"),
                # Accepted, with one line. "Nudge, don't block."
                Option("never", "Never — we just write it down"),
            ],
        ),
        # ---------------------------------------------------------- floor 6
        Question(
            key="floor.data_terms", number="6.6", group="f6",
            can_add="Add a term of your own",
            prompt="Which of these must be in every agreement?",
            kind="multi",
            writes=["Operating Principles", "Procurement"],
            options=[
                Option("no_training",
                       "The vendor may not train on our information",
                       recommended=True),
                Option("we_own", "We own what the tool produces",
                       recommended=True),
                Option("returned",
                       "Our data is returned and deleted when we leave",
                       recommended=True),
                Option("no_sharing", "No sharing with anyone else without our "
                                     "written permission", recommended=True),
                Option("residency", "Our data stays in a place we name",
                       recommended=True, then_text="Where?"),
            ],
        ),
        # ---------------------------------------------------------- floor 7
        Question(
            key="floor.named", number="6.7", group="f7",
            prompt="For each tool, who has to be named?",
            kind="multi",
            help="One person may hold several of these. That is normal in a "
                 "small organization, and your framework will say so rather "
                 "than pretending otherwise.",
            writes=["Operating Principles"],
            options=NAMED_CONTACTS,
        ),
        # ---------------------------------------------------------- floor 8
        Question(
            key="floor.plain_scope", number="6.8a", group="f8",
            prompt="Does every tool need a plain-language description?",
            kind="single",
            writes=["Transparency"],
            # "Change from public facing to the higher risk tiered categories
            # (those will almost always be public-facing)" — his correction.
            # Tying it to the levels they set at 5.2 makes it a rule their own
            # framework can apply, where "public-facing" needed a judgement
            # call every time.
            options=[
                Option("all", "Yes, all", recommended=True,
                       prose="every tool"),
                Option("higher_risk",
                       "Only {upper_tiers} tools",
                       "Those are almost always the public-facing ones",
                       prose="tools in the higher levels of scrutiny"),
                # "Their program, their choice." Offering only two kinds of
                # yes made this a question about scope when it is a question
                # about whether. The framework records the decision either
                # way — that is the point of asking.
                Option("none", "No",
                       "Your framework will say so, and the floor checklist "
                       "will record it as a place you chose to be less "
                       "strict"),
            ],
        ),
        Question(
            key="floor.plain_who", number="6.8b", group="f8",
            # Nothing to ask when nobody has to write one.
            shows_when={"key": "floor.plain_scope", "not": "none"},
            prompt="Who writes it, and who approves it?",
            kind="short", placeholder="Role title",
            also={"key": "approver", "label": "And who approves it",
                  "kind": "short", "placeholder": "Role title"},
            writes=["Transparency"],
        ),
        # --------------------------------------------------------- optional
        Question(
            key="floor.optional", number="6.9", group="extra",
            prompt="Would you like to add any of these?",
            kind="multi", optional=True, unknown_ok=False,
            above="They're good practice, not requirements.",
            # "Add ability to add your own line items." A list of nine good
            # practices that cannot be extended tells an organization its
            # tenth one does not count.
            can_add="Add a practice of your own",
            writes=["Operating Principles"],
            options=[
                Option("value", "A tool must show measurable value or be "
                                "retired"),
                Option("mission", "A tool must tie to a documented mission "
                                  "need"),
                Option("roi",
                       "Return on Investment calculations are required for "
                       "purchased AI tools",
                       "This triggers baseline assessments and business plans "
                       "before procurement, so there is a baseline taken "
                       "before it goes live. Tools you already run may not have one — "
                       "that is fine, it can be recorded as a gap."),
                Option("lifetime",
                       "Full lifetime cost is tracked against the original "
                       "estimate"),
                Option("open", "Prefer open standards in contracts, to avoid "
                               "getting locked in"),
                Option("reuse", "Check whether an existing tool can do it "
                                "before buying new"),
                Option("energy", "Consider energy and environmental cost"),
                Option("training", "Staff must be trained before they get "
                                   "access"),
                Option("roles", "Consider effects on staff roles before "
                                "it goes live"),
            ],
        ),
    ],
)


# ===========================================================================
# 07 — where the exposure lives
# ===========================================================================

#: Shown once they have admitted they do not fully know where their
#: information lives. "This is the highest-value advisory moment in the entire
#: module and it should not be buried in the generated document."
READINESS = {
    "shows_when": {"any": [
        {"all": [{"key": "data.where", "answered": True},
                 {"key": "data.where", "not": "documented"}]},
        {"all": [{"key": "data.systems", "answered": True},
                 {"key": "data.systems", "not": "documented"}]},
    ]},
    "title": "Before your first real AI project, three things pay for "
             "themselves",
    "body": [
        "Find out where your information lives. You do not need a full "
        "catalog, but a list of your major systems and what's in each one is "
        "extremely valuable.",
        "Connect what's separated. Most governments hold the same information "
        "in multiple places that can't talk to each other, which is why "
        "answering a simple question can take three days, two phone calls, "
        "and four emails.",
        "Tag it so a tool can find the right source. When each unit's "
        "information flows up into one governed layer — labeled, current, and "
        "query-ready — an AI tool can reach the right source instead of "
        "guessing. You get the right answer faster, the first time. And the "
        "silos that everyone has complained about for twenty years finally "
        "break.",
    ],
    "close": "Answering “partly” or “no” here doesn't stop you. It goes into "
             "your framework as a documented gap with an owner — which is the "
             "honest version, and the one that survives an audit.",
}

STEP_07 = Step(
    number="07",
    title="Your data ground rules",
    strapline="Where the exposure lives · 6 questions",
    writes="Data governance · Records",
    opening=[
        "An AI tool is only as good, and only as safe, as what you feed it. "
        "More governance failures start here than anywhere else.",
    ],
    questions=[
        Question(
            key="data.never", number="7.1",
            prompt="What kinds of information should never go into a "
                   "general-purpose AI tool?",
            kind="multi",
            # "Add more information that should never go in with a form field.
            # Just add a row." No list of eleven covers what every public body
            # holds.
            can_add="Add something else that should never go in",
            help="Everything here is offered to everyone. The ones already "
                 "ticked are the ones organizations like yours usually hold — "
                 "untick anything that isn't yours.",
            writes=["Data Governance"],
            options=[
                Option("personal", "Names, addresses, and other personal "
                                   "details of individuals", recommended=True),
                Option("medical", "Medical or health information"),
                Option("student", "Student records",
                       recommend_when=[{"if": {"key": "org.kind",
                                               "is": "school"}}]),
                Option("criminal", "Criminal justice information",
                       recommend_when=[{"if": {"key": "org.kind",
                                               "in": ["county", "city"]}}]),
                Option("tax", "Tax information"),
                Option("privileged",
                       "Anything covered by attorney–client privilege"),
                Option("infrastructure",
                       "Security details about buildings or infrastructure",
                       recommend_when=[{"if": {"key": "org.kind",
                                               "in": ["district",
                                                      "regional"]}}]),
                Option("personnel", "Personnel and disciplinary files"),
                Option("sealed",
                       "Sealed or confidential enforcement material"),
                Option("regulated",
                       "Confidential business information you received from "
                       "someone you regulate",
                       recommend_when=[{"if": {"key": "org.kind",
                                               "in": ["state", "federal",
                                                      "regional"]}}]),
                Option("nonpublic", "Anything not already public"),
            ],
        ),
        Question(
            key="data.where", number="7.2",
            prompt="Do you know where your information actually lives?",
            kind="single",
            writes=["Data Governance"],
            options=[
                Option("documented", "Yes, it is documented"),
                Option("undocumented", "Yes, but not documented"),
                Option("partly", "Partly"),
                Option("no", "No"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="data.systems", number="7.3",
            prompt="Do you know which systems hold which kinds of "
                   "information?",
            kind="single",
            writes=["Data Governance"],
            advice=READINESS,
            options=[
                Option("documented", "Yes, documented"),
                Option("partly", "Partly"),
                Option("no", "No"),
            ],
        ),
        Question(
            key="data.approver", number="7.4",
            prompt="Who approves using a particular set of information with "
                   "an AI tool?",
            # A choice, not a blank with a suggestion written above it. His
            # ticket: "you have the pre-filled structure listed under the
            # question, but it should be a 2 select option: 1. Pre-filled —
            # The Standing Group or 2. Someone else (fill in). This prevents
            # the system from registering the blank as missing."
            kind="single",
            writes=["Data Governance"],
            options=[
                # Capitalised: the label stands alone on a control rather
                # than sitting in a clause. The prose keeps the lower-case
                # form, because there it is mid-sentence.
                Option("decider", "{Decider}", recommended=True,
                       prose="{decider}"),
                Option("other", "Someone else",
                       then_text="Which role?"),
            ],
        ),
        Question(
            key="data.retention", number="7.5",
            prompt="Do you have a records retention schedule, and does it "
                   "cover documents AI helped produce?",
            kind="single",
            help="A document in this context is a public record based on what "
                 "it is and what it's used for, regardless of whether an AI "
                 "tool was used in the creation of or components within a "
                 "document.",
            writes=["Records"],
            options=[
                Option("covers",
                       "We have a schedule, and it covers AI-assisted "
                       "documents"),
                Option("silent",
                       "We have a schedule, but it does not mention "
                       "AI-assisted documents"),
                Option("none", "We do not have a retention schedule"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="data.prompts", number="7.6",
            prompt="If an employee types questions into an AI tool, are those "
                   "exchanges records?",
            kind="single",
            help="This is genuinely unsettled and varies by state. Deciding "
                 "it here, with your attorney's input if you have one, is far "
                 "better than deciding it during a records request. Whatever "
                 "you pick, the framework will state it, which is itself "
                 "protective.",
            writes=["Records"],
            options=[
                # "Change option 1 to add 'No, we treat them…'". The question
                # asks whether they are records, so an answer that starts by
                # describing the treatment makes the reader work out which
                # way it is answering.
                Option("relied", "No, we treat them as personal working "
                                 "notes — unless the answer was relied on "
                                 "for an official action"),
                Option("all", "Yes, we treat all of them as records"),
                Option("undecided", "We haven't decided"),
            ],
        ),
    ],
)


# ===========================================================================
# 08 — AI as an asset
# ===========================================================================

STEP_08 = Step(
    number="08",
    title="Your procurement rules",
    strapline="AI as an asset · 7 questions",
    writes="Procurement · Vendor governance",
    opening=[
        "You already have a way to buy things. This attaches to it. What "
        "follows is the short list of extra terms an AI purchase needs that a "
        "copier purchase does not.",
    ],
    questions=[
        Question(
            key="proc.today", number="8.1",
            prompt="How does your organization approve software purchases "
                   "today?",
            kind="short",
            placeholder="Name the process as your staff know it",
            also={"key": "thresholds",
                  "label": "And the amounts that change who has to approve it",
                  "kind": "short",
                  "placeholder": "Under $5,000 the director; above that, the "
                                 "board…"},
            help="Your framework will reference your actual process by name "
                 "rather than inventing a parallel one. That is the "
                 "difference between a framework people follow and one they "
                 "work around.",
            writes=["Procurement"],
        ),
        Question(
            key="proc.cooperative", number="8.2",
            prompt="Do you buy from state contracts, cooperative agreements, "
                   "or another government's contract?",
            kind="single",
            help="Buying off an existing contract is efficient, and it also "
                 "means AI can arrive without anyone in your organization "
                 "making a decision about it.",
            writes=["Procurement"],
            options=[
                Option("regularly", "Yes, regularly"),
                Option("sometimes", "Sometimes"),
                Option("no", "No"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="proc.terms", number="8.3",
            prompt="Which terms must be in every agreement for a tool with AI "
                   "in it?",
            kind="multi",
            writes=["Procurement", "Vendor Governance"],
            options=[
                Option("disclose", "Tell us what AI is in the product and who "
                                   "built it", recommended=True),
                Option("notice", "Tell us before changes go live",
                       recommended=True),
                Option("accuracy", "Commit to how accurate it is and how well "
                                   "it performs", recommended=True),
                Option("audit", "Let us inspect or audit how it's working",
                       recommended=True),
                Option("return", "Return and delete our information when we "
                                 "leave", recommended=True),
                Option("breach", "Notify us of a security breach within a set "
                                 "time", recommended=True,
                       then_text="Within how long?"),
                Option("staging", "Testing or staging environments for staff "
                                  "training and product testing before an "
                                  "update reaches everyone",
                       recommended=True),
                Option("accessibility", "Provide accessibility documentation",
                       recommended=True),
                Option("indemnity", "Cover us if someone claims the output "
                                    "infringes their rights"),
                Option("subcontractors",
                       "Disclose who else is involved — subcontractors and "
                       "the company whose AI is underneath the tool"),
            ],
        ),
        # 8.4, twice. Which one appears depends on whether 1.4 said there is a
        # legal function to send an agreement to. Same number and same
        # question; only the shape of the answer differs, because "name the
        # role" is not a question you can ask an organisation that has no such
        # role, and "this is a gap we need to close" is a real answer.
        Question(
            key="proc.checker", number="8.4",
            prompt="Who checks agreements for those terms?",
            # "8.4 — ability to add multiple roles. Only one role available."
            # More than one office reads an agreement in most organizations.
            kind="rows",
            shows_when={"key": "org.functions", "row": "legal", "not": "none"},
            writes=["Procurement"],
        ),
        Question(
            key="proc.checker_none", number="8.4",
            prompt="Who checks agreements for those terms?",
            kind="single",
            shows_when={"key": "org.functions", "row": "legal", "is": "none"},
            writes=["Procurement"],
            options=[
                Option("counsel", "We'd use outside counsel for this"),
                Option("purchasing", "Our purchasing staff check against a "
                                     "standard list"),
                Option("gap", "This is a gap we need to close",
                       "It will appear in your framework as a named gap with "
                       "an owner"),
            ],
        ),
        Question(
            key="proc.added_ai", number="8.5",
            prompt="A vendor adds AI to a product you already own. What "
                   "happens?",
            kind="single",
            above="This is the most common way AI arrives in a government "
                  "today, and the easiest to miss entirely.",
            writes=["Procurement", "Vendor Governance"],
            options=[
                Option("as_new", "Treat it as a new tool and review it like "
                                 "one", recommended=True),
                Option("risk_first", "Check it against your risk levels and "
                                     "decide from there"),
                Option("record", "Accept it, but write it down on the list"),
                Option("nothing", "Nothing — it's part of a product we "
                                  "already approved"),
            ],
        ),
        Question(
            key="proc.reuse", number="8.6",
            prompt="Before buying something new, must staff check whether an "
                   "existing tool you already have can resolve the problem?",
            kind="single",
            help="Most organizations do not realize the cross-utilization "
                 "capabilities of the AI tools already in place. Additional "
                 "purchases add cost, time, and ongoing management; "
                 "confirming a need first may save both.",
            writes=["Procurement"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("no", "No"),
            ],
        ),
        Question(
            key="proc.full_cost", number="8.7",
            prompt="Must the full cost be estimated before you commit?",
            kind="single",
            help="The sticker price is rarely the cost.",
            writes=["Procurement"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("no", "No"),
            ],
        ),
        Question(
            key="proc.cost_parts", number="8.7b",
            prompt="And what counts as cost?",
            kind="multi",
            shows_when={"key": "proc.full_cost", "is": "yes"},
            help="The last one is the item most organizations discover too "
                 "late.",
            writes=["Procurement"],
            options=[
                Option("licence", "The license or subscription",
                       recommended=True),
                Option("setup", "Setting it up", recommended=True),
                Option("training", "Training staff", recommended=True),
                Option("staff_time", "Staff time to run it", recommended=True),
                Option("data_prep", "Getting your data ready",
                       recommended=True),
                Option("integration", "Connecting it to other systems",
                       recommended=True),
                Option("monitoring", "Ongoing monitoring and review",
                       recommended=True),
                Option("exit", "What it costs to leave", recommended=True),
            ],
        ),
    ],
)


# ===========================================================================
# 09 — life after purchase
# ===========================================================================

STEP_09 = Step(
    number="09",
    title="Watching it work — and knowing when to stop",
    strapline="Life after purchase · 10 questions",
    writes="Performance · Public reporting · Sunset",
    opening=[
        "Governance that only happens when you buy something is policy. This "
        "is the part that keeps your systems honest after the excitement "
        "wears off.",
        "Monitoring and retirement are one step because the triggers for "
        "retiring a tool are mostly monitoring results. Splitting them makes "
        "retirement feel like an afterthought, which is exactly how it gets "
        "treated in practice.",
    ],
    questions=[
        Question(
            key="watch.worth", number="9.1",
            prompt="For a tool to be worth keeping, what would have to be "
                   "true?",
            kind="long",
            placeholder="Staff spend less time on it · the backlog is smaller "
                        "· fewer mistakes · people get answers faster · we "
                        "avoided a cost · complaints went down · staff can "
                        "spend time on something better",
            help="Those are prompts, not a list to pick from. Yours in your "
                 "own words is worth more than any of them.",
            writes=["Performance"],
        ),
        Question(
            key="watch.baseline", number="9.2",
            prompt="Do you write down a “before” measurement so you can "
                   "compare?",
            kind="single",
            help="Without a before number you cannot prove it worked; just as "
                 "importantly, you can't prove it didn't, which is how tools "
                 "nobody likes survive for years.",
            writes=["Performance"],
            options=[
                Option("always", "Yes, always", recommended=True),
                Option("sometimes", "Sometimes"),
                Option("no", "No"),
            ],
        ),
        Question(
            key="watch.cadence", number="9.3",
            prompt="How often do you check whether it's working?",
            kind="tiers",
            rows_from={"tiers": True},
            above="Once per level of scrutiny, filled in already so the "
                  "higher levels come back sooner. Change anything that isn't "
                  "right.",
            writes=["Performance"],
            tier_fields=[
                {"key": "every", "label": "Checked", "ask": "How often?",
                 "kind": "single",
                 "options": [{"value": "monthly", "label": "Monthly"},
                             {"value": "quarterly", "label": "Quarterly"},
                             {"value": "biannual", "label": "Twice a year"},
                             {"value": "annual", "label": "Once a year"}],
                 "defaults": {"routine": "annual", "elevated": "quarterly",
                              "minimal": "annual", "low": "annual",
                              "moderate": "biannual", "high": "quarterly"}},
            ],
        ),
        Question(
            key="watch.who", number="9.4",
            prompt="Who does that check and how is it documented?",
            kind="short", placeholder="One role title",
            also={"key": "where", "label": "And where the record lives",
                  "kind": "short",
                  "placeholder": "One location — a register, a folder, a "
                                 "system"},
            writes=["Performance"],
        ),
        Question(
            key="watch.what", number="9.5",
            prompt="Besides whether it works, what else do you watch?",
            kind="multi",
            writes=["Performance"],
            options=[
                Option("accuracy", "Whether it's still as accurate as it was",
                       "AI tools drift. The world changes, your data changes, "
                       "and a tool that was accurate a year ago may quietly "
                       "not be. Nothing tells you unless you look.",
                       recommended=True),
                Option("disparate", "Whether it affects some groups "
                                    "differently than others",
                       recommended=True),
                Option("cost", "Cost against what you expected"),
                Option("uptake", "Whether staff actually use it"),
                Option("complaints", "Complaints", recommended=True),
                Option("security", "Security", recommended=True),
                Option("vendor", "Whether the vendor changed anything",
                       recommended=True),
            ],
        ),
        Question(
            key="watch.failing", number="9.6",
            prompt="If it isn't delivering, what happens?",
            kind="single",
            writes=["Performance", "Sunset"],
            options=[
                Option("adjust", "Adjust it and test again"),
                Option("pause", "Pause it until it's fixed"),
                Option("retire", "Retire it"),
                Option("case", "Decide case by case"),
            ],
        ),
        Question(
            key="watch.triggers", number="9.7",
            prompt="What should automatically trigger a “should we keep "
                   "this?” review?",
            kind="multi",
            writes=["Sunset"],
            options=[
                Option("failed", "It failed its performance review",
                       recommended=True),
                Option("unsupported", "The vendor stopped supporting it",
                       recommended=True),
                Option("law", "A law or rule changed", recommended=True),
                Option("better", "Something better is available",
                       recommended=True),
                Option("funding", "The funding wasn't renewed",
                       recommended=True),
                Option("contract", "The contract is up", recommended=True),
                Option("incident", "There was a serious incident",
                       recommended=True),
            ],
        ),
        Question(
            key="watch.retire", number="9.8",
            prompt="Who decides to retire a tool?",
            kind="short", placeholder="One role title",
            also={"key": "records",
                  "label": "And what happens to the records and data when "
                           "it's shut off",
                  "kind": "long",
                  "placeholder": "What has to be kept and for how long, where "
                                 "it goes, who confirms it moved "
                                 "successfully, and what you'd need to "
                                 "explain a decision the tool touched two "
                                 "years from now"},
            writes=["Sunset", "Records"],
        ),
        Question(
            key="watch.notice", number="9.9",
            prompt="How much notice do staff and the public get before a tool "
                   "is turned off?",
            kind="single",
            writes=["Sunset"],
            options=[
                Option("30", "30 days"),
                Option("60", "60 days"),
                Option("90", "90 days"),
                Option("other", "Something else", then_text="How long?"),
                Option("none", "No set notice period"),
            ],
        ),
        Question(
            key="watch.publish", number="9.10",
            prompt="Do you want to publish anything about your AI use?",
            kind="multi",
            help="Publishing before you're asked is a materially better "
                 "position than publishing after.",
            writes=["Public Reporting"],
            options=[
                Option("annual_report",
                       "A yearly report on what we use and how it's working",
                       recommended=True),
                Option("tool_list", "A list of our AI tools on the website",
                       # Recommended once the public is already involved:
                       # either the work touches them directly, or somebody
                       # outside has started asking.
                       recommend_when=[
                           {"if": {"key": "risk.factors", "row": "public",
                                   "is": "major"}},
                           {"if": {"key": "have.asked",
                                   "in": ["public", "press", "board"]}},
                       ]),
                Option("framework", "This framework itself",
                       recommend_when=[
                           {"if": {"key": "have.asked",
                                   "in": ["public", "press", "board"]}},
                       ]),
                Option("nothing", "Nothing for now", exclusive=True),
            ],
        ),
    ],
)


# ===========================================================================
# 10 — when it goes wrong
# ===========================================================================

#: 10.3's three levels, pre-written for them to edit. "Editable defaults."
SEVERITIES = [
    Option("minor", "Minor"),
    Option("serious", "Serious"),
    Option("severe", "Severe"),
]

STEP_10 = Step(
    number="10",
    title="When it goes wrong",
    strapline="Incident response · 8 questions",
    writes="Incident response",
    opening=[
        "When a computer system goes down, everyone knows immediately. When "
        "an AI tool starts producing wrong answers, it can go unnoticed for "
        "months because the output may still look accurate.",
    ],
    questions=[
        Question(
            key="bad.existing", number="10.1",
            prompt="Do you already have a process for handling IT or security "
                   "incidents?",
            kind="single",
            writes=["Incident Response"],
            options=[
                Option("yes", "Yes"),
                Option("no", "No"),
                Option(UNKNOWN, "Not sure"),
            ],
        ),
        Question(
            key="bad.attach", number="10.1b",
            prompt="Add AI to it, or build a separate one?",
            kind="single",
            shows_when={"key": "bad.existing", "is": "yes"},
            help="People follow one process. They rarely follow two. Adding "
                 "AI-specific steps to what already exists beats a separate "
                 "plan nobody remembers.",
            writes=["Incident Response"],
            options=[
                Option("attach", "Add AI to what we already have",
                       recommended=True),
                Option("separate", "Build a separate one"),
            ],
        ),
        Question(
            key="bad.report_to", number="10.2",
            prompt="If an employee sees an AI tool produce a wrong or harmful "
                   "result, who do they tell and how?",
            kind="short",
            placeholder="A named role, an inbox, a phone number",
            help="Name a person or a channel that a new employee could find "
                 "in under a minute. If reporting is hard, it doesn't happen.",
            writes=["Incident Response"],
        ),
        Question(
            key="bad.levels", number="10.3",
            prompt="How would you rank how serious a problem is?",
            kind="tiers",
            rows=SEVERITIES,
            above="Written for you already. Change the wording to match how "
                  "your organization talks about it.",
            writes=["Incident Response"],
            tier_fields=[
                {"key": "meaning", "label": "What this level means",
                 "ask": "In your own words.", "kind": "short",
                 "defaults": {
                     "minor": "A wrong result that was caught before it "
                              "affected anyone.",
                     "serious": "It affected a person, influenced a decision, "
                                "or was visible to the public.",
                     "severe": "It affected someone's rights, benefits, or "
                               "safety; touched a delegated program; or "
                               "affected many people at once.",
                 }},
            ],
        ),
        Question(
            key="bad.speed", number="10.4",
            prompt="How fast does each level have to be reported?",
            kind="matrix",
            rows=SEVERITIES,
            writes=["Incident Response"],
            row_options=[
                Option("now", "Immediately"),
                Option("sameday", "Same day"),
                Option("3days", "Within three days"),
                Option("week", "Within a week"),
            ],
        ),
        Question(
            key="bad.stopper", number="10.5",
            prompt="Who can shut a tool off immediately, without waiting for "
                   "a meeting?",
            # "10.5 — add multi-field capability. Should have CTO, Agency
            # Director, etc." His own guidance is that more than one person
            # should be able to act alone, so one box was the wrong shape.
            kind="rows",
            help="Name at least one person who can act alone. Requiring a "
                 "quorum to stop a malfunctioning tool is how a small problem "
                 "becomes a large one over a weekend.",
            writes=["Incident Response"],
        ),
        Question(
            key="bad.lookback", number="10.6",
            prompt="After a serious problem, do you go back and check earlier "
                   "work the tool touched?",
            kind="single",
            help="If a tool was wrong today, it was probably wrong yesterday. "
                 "The question is how many decisions you need to go back and "
                 "look at.",
            writes=["Incident Response"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("no", "No"),
                Option("case", "Case by case"),
                Option(UNKNOWN, "Unsure, have not considered."),
            ],
        ),
        Question(
            key="bad.lookback_far", number="10.6b",
            prompt="How far back?",
            kind="single",
            shows_when={"key": "bad.lookback", "is": "yes"},
            writes=["Incident Response"],
            options=[
                Option("30", "30 days"),
                Option("90", "90 days"),
                Option("live", "Since it went live"),
                Option("needed", "As far as needed", recommended=True),
            ],
        ),
        Question(
            key="bad.tell", number="10.7",
            prompt="Who outside your organization must be told?",
            kind="multi",
            help="Where a delegated program is affected, your framework will "
                 "add a clause requiring a documented decision about whether "
                 "the delegating agency has to be notified.",
            writes=["Incident Response"],
            options=[
                Option("board", "Your board or elected officials"),
                Option("affected", "The person or people affected",
                       recommended=True),
                Option("state", "A state agency"),
                Option("federal", "A federal partner",
                       shows_when={"key": "org.delegated", "is": "yes"}),
                Option("insurer", "Your insurer"),
                Option("public", "The public"),
                Option("attorney", "Your attorney",
                       shows_when={"key": "org.functions", "row": "legal",
                                   "not": "none"}),
                Option("none", "No one outside", exclusive=True),
            ],
        ),
        Question(
            key="bad.writeup", number="10.8",
            prompt="Who writes up what happened?",
            kind="short", placeholder="One role title",
            also={"key": "where", "label": "And where that record lives",
                  "kind": "short",
                  "placeholder": "A register, a folder, a system"},
            writes=["Incident Response", "Records"],
        ),
    ],
)


# ===========================================================================
# 11 — why this framework exists
# ===========================================================================
#
# The client compared our output with a real adopted framework and said: "The
# questions we are asking should provide the inputs needed to create a draft
# that matches this."
#
# What his document has and ours did not is a Purpose and a Scope — why the
# organization is doing this, what standard it implements, which federal
# requirements apply, what happens when rules conflict, and how far the thing
# reaches. Module One asked none of that. The register it replaced asked all
# of it, having been mined from that very document, so these are its questions
# in Module One's plainer voice.
#
# Asked last and printed first. Somebody who has just spent ten steps deciding
# how they will govern can say why in a sentence; somebody on screen one
# cannot, and would write something they did not mean.

STEP_11 = Step(
    number="11",
    title="Why this framework exists",
    strapline="The opening pages · 10 questions",
    writes="Purpose · Scope · Legal and federal compliance",
    opening=[
        "You have decided the rules. These last few questions are about the "
        "document itself — what it is for, what it implements, and how far it "
        "reaches.",
        "They become the first two pages, which are the pages anybody deciding "
        "whether to sign it will actually read.",
    ],
    questions=[
        Question(
            key="why.reason", number="11.1",
            prompt="In a sentence or two, why is your organization doing "
                   "this?",
            kind="long",
            placeholder="To support the ethical, responsible and efficient "
                        "use of this technology for our staff and the people "
                        "we serve…",
            help="What should the public be able to believe about how you use "
                 "AI? This opens the document, and it is the one paragraph "
                 "most readers will remember.",
            writes=["Purpose"],
        ),
        # Brett, BUG-BE30FBD3: "Vision should be a module inside the
        # Framework. Where the framework asks what are you using AI for, that
        # is the vision question(s)." These are those questions, in Vision's
        # own terms — where the organization wants to be a year from now and
        # five years from now. Each line becomes a goal offered on the Vision
        # page, which is pre-filled from them rather than asked twice.
        Question(
            key="why.vision_year", number="11.1a",
            prompt="What do you want AI to help your organization achieve "
                   "within the next year?",
            kind="long",
            optional=True,
            placeholder="Answer permit questions faster; cut the backlog of "
                        "records requests…",
            help="One goal per line. Each becomes a goal on your Vision page, "
                 "where you can say who owns it and what would have to be "
                 "true.",
            writes=["Purpose"],
        ),
        Question(
            key="why.vision_five", number="11.1b",
            prompt="And within five years?",
            kind="long",
            optional=True,
            placeholder="Every resident can get an answer in plain language, "
                        "at any hour…",
            help="One goal per line, as above.",
            writes=["Purpose"],
        ),
        Question(
            key="why.state_strategy", number="11.2",
            prompt="Is there a statewide AI policy or strategy you have to "
                   "follow?",
            kind="single",
            writes=["Purpose", "Legal and Federal Compliance"],
            options=[
                Option("yes", "Yes",
                       then_text="Name it, and its guiding principles if it "
                                 "has any"),
                Option("no", "No — nothing statewide binds us"),
            ],
        ),
        Question(
            key="why.federal", number="11.3",
            prompt="Which federal requirements apply to you?",
            kind="multi",
            can_add="Add another that applies to you",
            help="The two below apply to most public bodies touching federal "
                 "money or programs. Untick anything that is not yours.",
            writes=["Legal and Federal Compliance"],
            options=[
                Option("omb", "OMB Memorandum M-25-21", recommended=True),
                Option("nist", "The NIST AI Risk Management Framework",
                       recommended=True),
                Option("ada", "ADA Title II, for anything public-facing",
                       recommended=True),
                Option("none", "None that we know of", exclusive=True),
            ],
        ),
        Question(
            key="why.conflict", number="11.4",
            prompt="When your rules and a state or federal rule disagree, "
                   "which one wins?",
            kind="single",
            help="Most frameworks say the stricter one, because it is the "
                 "answer that never leaves you short of a rule you were "
                 "supposed to meet.",
            writes=["Purpose", "Legal and Federal Compliance"],
            options=[
                Option("stricter", "Whichever is stricter", recommended=True,
                       prose="the more stringent standard controls"),
                Option("external", "The state or federal rule",
                       prose="the state or federal rule controls"),
                Option("ours", "This framework",
                       prose="this framework controls"),
            ],
        ),
        # 11.5 was one box asking two things — "What are your parts called,
        # and does this cover all of them?" — which is answerable only by an
        # organization that has parts, and gives nowhere to record an
        # exclusion. His structure, followed as written:
        #
        #   "11.5. Do you have organizational sub-units? 11.5.a. What do you
        #   call your organizational sub-units? 11.5.b. Will this governance
        #   framework apply to all sub-units? (Yes, No > 11.5.b.1 Which are
        #   excluded?)"
        #
        # `why.units` keeps its key so answers already given still read back;
        # only its number moves.
        Question(
            key="why.has_units", number="11.5",
            prompt="Do you have organizational sub-units?",
            kind="single",
            help="Departments, divisions, bureaus, programs, districts — "
                 "whatever you call them. A single-office organization "
                 "answers no, and the two questions after this one are not "
                 "asked.",
            writes=["Scope"],
            options=[
                Option("yes", "Yes", recommended=True),
                Option("no", "No — we are a single unit",
                       prose="a single unit"),
            ],
        ),
        Question(
            key="why.units", number="11.5a",
            prompt="What do you call your organizational sub-units?",
            shows_when={"key": "why.has_units", "is": "yes"},
            kind="short",
            placeholder="All divisions, bureaus and offices",
            help="Naming them is what stops somebody arguing later that "
                 "their unit was not included.",
            writes=["Scope"],
        ),
        Question(
            key="why.units_all", number="11.5b",
            prompt="Will this framework apply to all sub-units?",
            shows_when={"key": "why.has_units", "is": "yes"},
            kind="single",
            help="An exclusion is not a weakness — an unrecorded one is. "
                 "Whatever you answer, your framework will say so.",
            writes=["Scope"],
            options=[
                Option("yes", "Yes, all of them", recommended=True),
                Option("no", "No — some are excluded",
                       then_text="Which are excluded?"),
            ],
        ),
        Question(
            key="why.routes", number="11.6",
            prompt="How does AI arrive in your organization?",
            kind="multi",
            above="All of these count unless you say otherwise. The last one "
                  "is how it most often arrives without anybody deciding.",
            writes=["Scope"],
            options=[
                Option("built", "Built by your own staff", recommended=True,
                       prose="built by the organization's own staff"),
                Option("bought", "Bought from a vendor", recommended=True,
                       prose="procured from a vendor"),
                Option("embedded", "Already inside software you own",
                       recommended=True,
                       prose="embedded within software already owned"),
                Option("upgrade", "Arriving in an upgrade you did not ask for",
                       recommended=True,
                       prose="arriving in an upgrade nobody requested"),
                Option("cooperative",
                       "Through a state contract or cooperative agreement",
                       recommended=True,
                       prose="acquired through a state contract or "
                             "cooperative agreement"),
                Option("contractor", "Used by a contractor doing work for you",
                       recommended=True,
                       prose="used by a contractor doing work for the "
                             "organization"),
            ],
        ),
        Question(
            key="why.manual", number="11.7",
            prompt="Will there be a separate procedures document underneath "
                   "this one?",
            kind="single",
            also={"key": "owner", "label": "And who owns it",
                  "kind": "short", "placeholder": "A role title"},
            help="A framework states the rule; a procedures manual states how "
                 "the rule is carried out. Keeping them apart lets you change "
                 "the how without re-adopting the what.",
            writes=["Purpose"],
            options=[
                Option("yes", "Yes — a procedures manual sits beneath this",
                       recommended=True),
                Option("no", "No — this document holds everything"),
                Option("later", "Not yet, but we intend to write one"),
            ],
        ),
        Question(
            key="why.ambition", number="11.8",
            # "a model for others" is how his own register put it, and
            # "model" is the first word on his banned list — caught by the
            # guard rather than by reading it back. "Example" says the same
            # thing and cannot be mistaken for machine learning.
            prompt="Do you want to say you hope to set an example for "
                   "others?",
            kind="single",
            optional=True,
            help="Some organizations mean it and say so. Others would rather "
                 "not invite the comparison. Neither is wrong.",
            writes=["Purpose"],
            options=[
                Option("say", "Yes, say so"),
                Option("quiet", "Leave it out", recommended=True),
            ],
        ),
    ],
)


# ===========================================================================
# — review, adopt, publish
# ===========================================================================

STEP_DONE = Step(
    number="—",
    title="Review, adopt, publish",
    strapline="Assembly · no new policy questions",
    writes="The finished framework document",
    opening=[
        "No new decisions here. This step exists to make the document yours, "
        "catch what contradicts itself, and get it signed.",
        "An unadopted framework is a draft, and drafts don't govern anything.",
    ],
    questions=[
        Question(
            key="done.title", number="—.1",
            prompt="What do you want this document called?",
            kind="short",
            placeholder="Organization_Enterprise_AI_Governance_Framework",
            unknown_ok=False,
            writes=["The Framework"],
        ),
        Question(
            key="done.signs", number="—.2",
            prompt="Who signs it, and when does it take effect?",
            kind="single",
            also={"key": "effective", "label": "And the date it takes effect",
                  "kind": "short", "placeholder": "A date, or “on signature”"},
            help="Pre-filled from 1.3 and 4.8. Once it is signed, scan it and "
                 "upload it as your Active Framework — that upload, not this "
                 "screen, is what makes it official.",
            writes=["Authority"],
            options=[
                Option("board", "An elected board or council, by vote"),
                Option("elected", "A single elected official"),
                Option("appointed",
                       "An appointed director, administrator, or manager"),
                Option("cabinet", "A state-level executive or cabinet officer"),
            ],
            recommend_when=[
                {"if": {"key": "who.signs", "is": "board"}, "then": "board"},
                {"if": {"key": "who.signs", "is": "elected"},
                 "then": "elected"},
                {"if": {"key": "who.signs", "is": "appointed"},
                 "then": "appointed"},
                {"if": {"key": "who.signs", "is": "cabinet"},
                 "then": "cabinet"},
                {"if": {"key": "org.adopter", "is": "board"}, "then": "board"},
                {"if": {"key": "org.adopter", "is": "elected"},
                 "then": "elected"},
                {"if": {"key": "org.adopter", "is": "appointed"},
                 "then": "appointed"},
                {"if": {"key": "org.adopter", "is": "cabinet"},
                 "then": "cabinet"},
            ],
        ),
        Question(
            key="done.register", number="—.2b",
            prompt="How formal should the finished document be?",
            kind="single",
            help="Both say exactly the same thing and hold you to exactly the "
                 "same rules. The difference is how it reads to whoever picks "
                 "it up.",
            writes=["The Framework"],
            # The recommendation moves with their own answers — see
            # `register_for`, which also returns the reasons so the screen can
            # say why rather than simply asserting.
            options=[
                Option(SIMPLIFIED, "Simplified",
                       "Short, plain sentences. Reads like a set of rules a "
                       "small organization can actually follow. Fewer words "
                       "between the reader and the decision."),
                Option(FORMAL, "Formal",
                       "Full paragraphs in the register of an adopted "
                       "instrument — purpose, scope, and the standards it "
                       "implements, written to be signed and filed."),
            ],
        ),
        # The client's second question at the download, in his words: "How
        # would you like the language to appear: As written or Polished. As
        # written is just the raw output as you created, but polished uses an
        # LLM to run through, clean up, and do some of the editorial work to
        # closer match that north star we have."
        #
        # And his reasoning, which is the design brief: "I'm guessing they're
        # going to default to polished because they don't have the time to
        # run through it again and do a full rework. If it is going to take
        # more than an hour to rewrite it, they're not going to recommend to
        # others to use it."
        #
        # What the option must never do is change what the document *says*.
        # Every sentence in this module is assembled from an answer somebody
        # gave, and that is the whole claim the product makes. So polishing
        # is language only, clause by clause, their own typed words are left
        # alone, every clause is checked against its original before it is
        # accepted, and the document records that it was polished. See
        # app/polish.py.
        Question(
            key="done.language", number="—.2c",
            prompt="How would you like the language to read?",
            kind="single",
            help="This changes the wording, never the rules. Whichever you "
                 "pick, the document holds you to exactly the same "
                 "decisions, and anything you typed yourself is carried "
                 "through word for word.",
            writes=["The Framework"],
            options=[
                Option(AS_WRITTEN, "As written",
                       "Exactly what your answers assemble into. Plain, "
                       "literal, and nothing has been near it since you "
                       "answered.", recommended=True),
                # "Never write model. Write tool." — his rule, and his own
                # word for this feature was "LLM", which is on the same
                # banned list. So the copy says what it does rather than what
                # it is: an AI writing tool.
                Option(POLISHED, "Polished",
                       "An AI writing tool tidies the wording — smoother "
                       "sentences, consistent terms, the register of a "
                       "document somebody drafted rather than one a form "
                       "produced. It is not allowed to add a rule, remove "
                       "one, or change what any clause requires, and every "
                       "sentence is checked against the original before it "
                       "is kept. If no such tool is set up on this server "
                       "the document comes out as written, and says so."),
            ],
            # Shown the moment Polished is clicked, and only then.
            #
            # "We need to flash a disclaimer that the polished version uses
            # an LLM which may adjust or alter their statements (trying to
            # address the non-deterministic nature) and that additional
            # scrutiny should be provided when reviewing the output."
            #
            # The point he is making is the one worth saying plainly: the
            # same answers put through this twice will not come back word for
            # word identical. The checks hold every rewrite to the same
            # numbers, obligations, deadlines and names — that part is
            # deterministic — but which of several faithful wordings comes
            # back is not, and somebody signing this should know that before
            # they read it rather than after.
            consequences=[
                {"if": {"key": "done.language", "is": POLISHED},
                 "say": "Read the polished document carefully before it goes "
                        "anywhere. An AI writing tool rewrites the wording of "
                        "each clause, and it does not produce the same "
                        "wording twice — running this again would give you a "
                        "differently worded document holding you to the same "
                        "rules. Every rewrite is checked against your own "
                        "answer for changed numbers, changed obligations, "
                        "changed deadlines and dropped names, and anything "
                        "that fails is thrown away. Those checks are good and "
                        "they are not a substitute for reading it. The "
                        "as-written version stays in your version history so "
                        "you can compare the two."},
            ],
        ),
        Question(
            key="done.where", number="—.3",
            prompt="Where will it live?",
            kind="single",
            # "Fill in from previous section + give other options."
            #
            # 9.10 already asks whether they intend to publish this framework,
            # and the two answers are related closely enough that the module
            # carries a contradiction rule for them disagreeing — "You said
            # you'd publish this framework, and also that it lives internally
            # only. Which wins?" Asking the same thing twice without carrying
            # the first answer forward is what made the second one feel like
            # rework, and it is also what produced that contradiction.
            help="Pre-filled from 9.10.",
            recommend_when=[
                {"if": {"key": "watch.publish", "includes": "framework"},
                 "then": "public"},
                {"if": {"key": "watch.publish", "includes": "nothing"},
                 "then": "internal"},
            ],
            writes=["The Framework", "Public Reporting"],
            options=[
                Option("internal", "Internal only"),
                Option("public", "Public website"),
                Option("both", "Both"),
                # Distinct from "internal only" and from "public website", and
                # the position a good many public bodies actually hold: not
                # posted, but released to anyone who asks under open records.
                Option("request", "Available on request only",
                       "Not posted, but released to anyone who asks",
                       prose="available on request"),
                Option("notyet", "Not published yet"),
                Option("other", "Somewhere else", then_text="Where?"),
            ],
        ),
        Question(
            key="done.review", number="—.4",
            prompt="When does it come back for review?",
            kind="single",
            help="Pre-filled from 4.10.",
            writes=["Amendment"],
            options=[
                Option("annual", "Every year"),
                Option("biennial", "Every two years"),
                Option("onchange", "Only when something changes in the law"),
                Option("other", "Something else", then_text="How often?"),
            ],
            recommend_when=[
                {"if": {"key": "who.review", "is": "annual"},
                 "then": "annual"},
                {"if": {"key": "who.review", "is": "biennial"},
                 "then": "biennial"},
                {"if": {"key": "who.review", "is": "onchange"},
                 "then": "onchange"},
                {"if": {"key": "who.review", "is": "other"}, "then": "other"},
            ],
        ),
    ],
    closing={
        "title": "What comes next",
        "body": [
            "You now have the rules. Running each tool through them — from "
            "problem and use case identification and intake, review, "
            "approval, monitoring, and retirement — is the work that comes "
            "next.",
            "Please see the Premium Subscription page for access to the "
            "workflow system.",
        ],
        "after": "The framework says what the rules are. Which tool is where, "
                 "who signed off, and what's due for review this month is a "
                 "different job.",
    },
)


# ===========================================================================

STEPS: list[Step] = [STEP_00, STEP_01, STEP_02, STEP_03, STEP_04, STEP_05,
                     STEP_06, STEP_07, STEP_08, STEP_09, STEP_10, STEP_11,
                     STEP_DONE]

#: Their own paragraph, on every step that records a decision.
for _step in STEPS:
    _step.own_words = _step.asks and _step is not STEP_DONE

#: The steps still to build, listed rather than omitted so the interface can
#: show the whole path. A section that says "not yet" is honest in a way a
#: silently missing one is not. Empty now that Module One is whole — kept,
#: because the next module will need it and because both the interface and the
#: export are written to show it.
PENDING: list[tuple[str, str, str]] = []


#: Answers that change a question without appearing in any of its conditions.
#:
#: `—.2b`'s recommendation is computed by `register_for`, which weighs several
#: signals at once and so could not be written as a declarative rule. Nothing
#: walking the conditions can discover that, so the keys it reads are named
#: here — and if `register_for` starts reading another answer, it belongs in
#: this tuple too.
COMPUTED_FROM: tuple[str, ...] = (
    "org.size", "org.functions", "org.delegated", "who.shape", "risk.levels",
)


def _keys_in(condition: Any) -> set[str]:
    """Every answer a condition consults, however deeply combined."""
    found: set[str] = set()
    if not isinstance(condition, dict):
        return found
    for combiner in ("any", "all"):
        for inner in condition.get(combiner) or []:
            found |= _keys_in(inner)
    key = condition.get("key")
    if isinstance(key, str) and key:
        found.add(key)
    # `rows_from` and `needs` carry a nested condition under their own name.
    for nested in ("unless", "if", "when", "shows_when"):
        found |= _keys_in(condition.get(nested))
    return found


@functools.lru_cache(maxsize=1)
def drivers() -> frozenset[str]:
    """Answers that change what a later question asks, shows or suggests.

    The browser needs this list. When one of these is answered it reloads the
    module and redraws the open step, because a question whose options or
    visibility moved has to move on screen rather than at the next page load.

    Derived from the questions rather than listed by hand, which is the whole
    point of it. The list *was* written by hand — seven keys — and the client
    reported the consequence: "—.2b did not populate until after I saved. Is
    that the only way? Can it show up before saving and proceeding? Creates a
    feeling of rework. (happens in other places, too)."

    He was right about the "other places", and the hand-written list is why
    they exist. Anything gating a question that nobody remembered to add
    stayed stale until something else forced a reload — and two more had just
    been introduced without noticing: `why.has_units`, which reveals 11.5a and
    11.5b, and `floor.plain_scope`, which hides 6.8b. Both would have shipped
    with the same fault the ticket describes.
    """
    found: set[str] = set(COMPUTED_FROM)
    for step in STEPS:
        for question in step.questions:
            found |= _keys_in(question.shows_when)
            found |= _keys_in(question.needs)
            found |= _keys_in(question.rows_from)
            found |= _keys_in(question.advice)
            for rule in question.recommend_when:
                found |= _keys_in(rule.get("if"))
            for rule in question.instead_when:
                found |= _keys_in(rule.get("if"))
            for rule in question.consequences:
                found |= _keys_in(rule.get("if"))
            for spec in question.tier_fields:
                found |= _keys_in(spec.get("shows_when"))
            for option in list(question.options) + list(question.row_options):
                found |= _keys_in(option.shows_when)
                for rule in option.recommend_when:
                    found |= _keys_in(rule.get("if"))
    # A question does not drive itself: its own `consequences` line is shown
    # from the answer in hand and needs no round trip.
    return frozenset(found)


def by_number(number: str) -> Step | None:
    return next((s for s in STEPS if s.number == str(number)), None)


def by_key(key: str) -> Question | None:
    for step in STEPS:
        for question in step.questions:
            if question.key == key:
                return question
    return None


def all_questions() -> list[Question]:
    return [q for s in STEPS for q in s.questions]


#: Questions about how the finished document reads, rather than about what
#: the organization decided. They are asked at the download, and they are
#: not the framework — so an unanswered one says nothing about whether the
#: framework is finished.
DOCUMENT_PREFERENCES = frozenset({"done.register", "done.language"})


def policy_progress(answers: dict[str, Any]) -> tuple[int, int]:
    """(answered, total) over the questions that decide policy.

    What "the framework is complete" means for the adoption gate. It was
    every visible question, which counted the optional ones and the two about
    document style — so a framework with every decision made could not be
    adopted until somebody said whether they wanted the language formal.
    """
    counted = [q for s in STEPS for q in s.questions
               if visible(q, answers)
               and not getattr(q, "optional", False)
               and q.key not in DOCUMENT_PREFERENCES]
    return sum(1 for q in counted if answered(q, answers)), len(counted)


def summary(answers: dict[str, Any] | None = None) -> dict[str, Any]:
    """The whole module, adapted to what has been answered so far."""
    answers = answers or {}
    steps = [s.as_dict(answers) for s in STEPS]
    asked = [q for s in STEPS for q in s.questions if visible(q, answers)]
    return {
        "title": "Build Your AI Governance Framework",
        "blurb": "A guided sequence that takes you from a blank page to an "
                 "adopted governance framework written in your own words — not "
                 "a copy of someone else's.",
        # The gate's name. It read "Step 1 — Govern", and the spine forbids a
        # gate rendered as a number anywhere, in code or in copy.
        "lifecycle_stage": "Govern",
        "steps": steps,
        "pending": [{"number": n, "title": t, "writes": w}
                    for n, t, w in PENDING],
        "totals": {
            "steps_built": len(STEPS),
            "steps_total": len(STEPS) + len(PENDING),
            "questions": len(asked),
            "answered": sum(1 for q in asked if answered(q, answers)),
        },
        "gaps": gaps(answers),
        "contradictions": contradictions(answers),
        "floor": floor_state(answers),
        "review": review(answers),
        "register": {**register_for(answers),
                     "chosen": register_of(answers)},
        # Which answers the browser must reload after, so a question whose
        # options or visibility just moved moves on screen rather than at the
        # next page load. Sent rather than duplicated in the script: the copy
        # kept there was written by hand and fell behind, which is the fault
        # `drivers()` exists to stop.
        "drivers": sorted(drivers()),
    }


def review(answers: dict[str, Any]) -> list[dict[str, Any]]:
    """The framework read back, section by section, in their words.

    "Every choice traced to the question that produced it, so nothing appears
    that they can't account for." Which is also why this is built from the
    same `describe` the document uses: a review screen that renders answers by
    a different route than the export is a review of something else.
    """
    out = []
    for step in STEPS:
        # The assembly step is where the read-back is shown; including it
        # would have the screen read itself back to itself.
        if not step.asks or step.number == "—":
            continue
        rows = []
        for question in step.questions:
            if not visible(question, answers):
                continue
            said = describe(question, answers)
            rows.append({
                "key": question.key,
                "number": question.number,
                "prompt": _fill(question.prompt, answers),
                "state": said["state"],
                "lines": said["lines"],
                "owner": said["owner"],
            })
        out.append({
            "number": step.number,
            "title": step.title,
            "writes": step.writes,
            "rows": rows,
            "answered": sum(1 for r in rows if r["state"] == "answered"),
            "asked": len(rows),
            "own_words": str(_value(answers, own_words_key(step.number))
                             or ""),
        })
    return out







