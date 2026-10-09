"""The framework as a document somebody would adopt, rather than a transcript.

The client, on the first export::

    "It is fine to keep it as a log with each question asked/answered, but is
     the intent to additionally create a unified, proper document upon
     completion? I would think the download would have the 'good' version that
     could be adopted with the question audit trail at the end."

He is right, and the distinction is the whole point of this module. What the
export produced was::

    5.3  For each level, what has to happen?
    Low · Who reviews it: Whoever has authority to approve it — typically IT

A board does not adopt that. It reads as what it is — the output of a form —
and it invites the reader to audit the process instead of the policy. What a
board adopts reads::

    4.3  Levels of scrutiny
    Tools in the lowest level are reviewed by whoever has authority to approve
    them, typically IT. A line on the list of tools, what it does, and who
    owns it must exist before approval. They are re-checked once a year and
    may be approved without a meeting.

So this module turns answers into clauses. Every sentence below is assembled
from something the organization actually chose; nothing is invented, and a
question they did not answer produces no sentence at all — it produces a line
in the gaps section instead, which is the honest version.

Two things this deliberately does not do
----------------------------------------

**It does not write policy they did not choose.** Every template here is a
frame around their own answer. Where there is no answer there is no sentence,
rather than a sensible-sounding default that nobody decided.

**It does not replace the audit trail.** The question-by-question record still
appears, at the back, where he asked for it. The prose is what governs; the
trail is how you check it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app import module_one as m1


def _join(parts: list[str], keep_stops: bool = False) -> str:
    """A list, as English rather than as a comma-separated dump."""
    kept = [p.strip() if keep_stops else p.strip().rstrip(".")
            for p in parts if p and p.strip()]
    if not kept:
        return ""
    if len(kept) == 1:
        return kept[0]
    # Items that already contain "and" cannot also be joined by "and" —
    # "spreadsheet formulas and calculations and spellcheck and grammar tools"
    # has four things in it as far as a reader can tell, and two as far as the
    # answer is concerned.
    if any(" and " in item for item in kept):
        # Semicolons alone, with no "and" before the last item — adding one
        # back gives "free tools and trials; and short pilots", which is the
        # same problem wearing a semicolon.
        return "; ".join(kept)
    if len(kept) == 2:
        return f"{kept[0]} and {kept[1]}"
    return ", ".join(kept[:-1]) + f", and {kept[-1]}"


def _lower_first(text: str) -> str:
    """Lower-case a *choice* being dropped into mid-sentence.

    Only ever applied to option labels, which this project writes and which
    start with a capital because they sit above a radio button. Never applied
    to anything the organization typed: lower-casing their free text turned
    "We run a joint treatment plant" into "we run a joint treatment plant" and
    "District Manager" into "district Manager", which is this module editing
    their words, which it has no business doing.

    Acronyms are left alone — and the test for one has to be that *both*
    leading characters are upper-case letters. `"A "[:2].isupper()` is True,
    because a space is uncased, so "A technical contact" was read as an
    acronym and kept its capital mid-sentence.
    """
    if not text or text[:1].islower():
        return text
    if text[:2].isalpha() and text[:2].isupper():
        return text
    return text[0].lower() + text[1:]


def _fits_midsentence(text: str) -> str:
    """Their own words, with a leading article lowered and nothing else.

    "Where there is disagreement, The District Manager has the final say" —
    the capital belongs to the role title, not to the determiner in front of
    it. This lowers "The", "A" and "An" where they open the answer, and leaves
    every other word exactly as they typed it.
    """
    for article in ("The ", "A ", "An "):
        if text.startswith(article):
            return article.lower() + text[len(article):]
    return text


def mid_sentence(text: str) -> str:
    """A label from this project's own option lists, lowered to sit inside a
    sentence. Public because the export builds sentences too — its signature
    clause read "adopted by An elected board or council" and "takes effect On
    signature", because it dropped a label in raw.

    Their own words are left alone: see `_lower_first` for why.
    """
    return _lower_first(text)


@dataclass
class Clause:
    """One statement in the finished framework, and where it came from."""
    text: str
    #: The question number, for the reader who wants to check it.
    source: str = ""


@dataclass
class Section:
    number: str
    title: str
    #: One line on what this section is for, in the document's own voice.
    purpose: str = ""
    clauses: list[Clause] = field(default_factory=list)
    #: Their own paragraph, verbatim, from the step this section draws on.
    own_words: str = ""
    #: Rendered as a small table rather than a sentence — the tier grids.
    tables: list[dict[str, Any]] = field(default_factory=list)
    #: (term, meaning) pairs, for the definitions section. Rendered as a
    #: definition list rather than as numbered clauses.
    terms: list[tuple[str, str]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.clauses or self.own_words or self.tables
                    or self.terms)


# --------------------------------------------------------------- the sentences
#
# One entry per question that contributes a statement. `{answer}` is the
# organization's own words — the labels they clicked, or the text they typed.
# Anything absent from this map contributes no sentence, which is deliberate:
# the interview asks things that shape later questions without themselves
# belonging in the document (1.2, "about how many people work here", is
# context, not policy).

SENTENCES: dict[str, str] = {
    # --- purpose
    "why.reason":
        "{answer}",
    # 11.1a and 11.1b — the Vision questions (BUG-BE30FBD3).
    "why.vision_year":
        "What this organization wants AI to help it achieve within the next "
        "year: {answer}.",
    "why.vision_five":
        "And within five years: {answer}.",
    "why.ambition_say":
        "This organization intends this framework to serve as an example for "
        "others.",
    "why.state_strategy_yes":
        "This framework is this organization's implementation of {detail}.",
    "why.state_strategy_no":
        "No statewide AI policy or strategy binds this organization. This "
        "framework stands on its own.",
    "why.federal":
        "It is designed to comply with {answer}, as those stand at the date "
        "of adoption.",
    "why.conflict":
        "Where this framework and a state or federal requirement disagree, "
        "{answer}.",
    "why.manual_yes":
        "Procedural detail implementing this framework is set out in a "
        "separate procedures document, owned by {also}. Where this framework "
        "states a rule, that document states how the rule is carried out, and "
        "it may be updated without amending this framework provided it stays "
        "consistent with the rules established here.",
    "why.manual_later":
        "A separate procedures document is intended but not yet written. "
        "Until it exists, this framework is the whole of the rule.",
    "why.manual_no":
        "There is no separate procedures document. This framework states both "
        "the rule and how it is carried out.",

    # --- scope
    "why.units":
        "This framework applies across {answer}.",
    # 11.5 and 11.5b are branched: whether there are sub-units at all, and
    # whether any are excluded, are both statements a reader needs made
    # plainly rather than inferred from a list of names.
    "why.has_units_no":
        "This organization has no sub-units. This framework applies to the "
        "organization as a whole.",
    "why.units_all_yes":
        "It applies to every one of those units without exception.",
    "why.units_all_no":
        "It applies to those units with the following excepted: {detail}.",
    "why.routes":
        "Its requirements attach to artificial intelligence however it "
        "arrives: {answer}.",
    "scope.covered":
        "These rules cover {answer}.",
    "scope.excluded":
        "They do not cover {answer}.",
    # No trailing verb. His answer was "The Chief Technology Officer decides,
    # subject to Agency Director review", and the template appended another
    # "decides" to it — "…subject to Agency Director review decides." A role
    # title and a whole sentence both have to fit here, so the frame ends
    # before the verb rather than supplying one.
    "scope.arbiter":
        "Where it is not clear whether something falls within these rules: "
        "{answer}.",
    "scope.review_yes":
        "That decision is reviewed afterward.",
    "scope.review_standalone":
        "That decision stands on its own and is not reviewed afterward.",
    "org.delegated_yes":
        "This organization runs programs delegated or funded by another level "
        "of government, and the obligations attached to those programs apply "
        "to AI used within them.",
    "org.open_records_yes":
        "This organization is subject to open records and open meetings laws, "
        "and records created with the assistance of AI are public records on "
        "the same terms as any other.",
    # 1.7. Only "yes" earns a sentence, and only once the authority is named;
    # "no central IT authority" states nothing a reader needs.
    "org.it_authority_yes":
        "This organization's IT program coordinates with a centralized IT "
        "authority, {detail}, and AI use under this framework is coordinated "
        "with that authority.",
    # 1.8 is the optional catch-all, and a bare "No" printed as clause 1.8 is
    # a fragment in a formal document. Only a real answer earns a sentence.
    "org.unusual":
        "{answer}",

    # --- authority
    "who.shape":
        "Responsibility for AI decisions sits with {answer}.",
    "who.seats":
        "The roles holding that responsibility are {answer}. Where one person "
        "holds more than one of these, the framework records the "
        "concentration rather than concealing it.",
    "who.tiebreak":
        "Where there is disagreement, {answer} has the final say.",
    "who.consulted":
        "Before an AI tool is approved for use, {answer} must be asked.",
    "who.cadence":
        "AI matters are considered {answer}.",
    "who.without":
        "The following may proceed without that approval: {answer}.",
    "who.record":
        "Decisions are recorded in {answer}.",

    # --- risk
    "risk.levels":
        "This organization applies {answer}.",
    "risk.worst_yes":
        "A tool rated high on any single factor receives the highest level of "
        "scrutiny, whatever its other ratings. Averaging is not used: a tool "
        "that is low-risk in seven respects and severe in one is a "
        "severe-risk tool.",
    "risk.worst_no":
        "A tool's level of scrutiny is set on the overall picture rather than "
        "on its highest single factor.",
    "risk.revisit":
        "A tool's risk level is looked at again {answer}.",

    # --- the floor
    "floor.final_action":
        "For the purposes of this framework, a final action is: {answer}",
    "floor.ai_finalises_none":
        "No AI tool finalizes an action affecting a person's rights, money, "
        "standing or employment. AI may draft, sort, flag and recommend; a "
        "person decides.",
    "floor.ai_finalises_some":
        "This organization permits AI to finalize certain decisions without a "
        "person, as recorded below. Each carries a written justification and "
        "is routed to the highest level of scrutiny automatically.",
    # The third answer, and the one that needs the most said about it: a
    # case-by-case permission with nobody named and no test written down is
    # not a rule, so the clause states both and the question asks for both.
    "floor.ai_finalises_case_by_case":
        "This organization permits AI to finalize a decision without a person "
        "only where that has been decided for the particular case. That "
        "decision rests with {detail}, is recorded with its reasons, and "
        "routes the tool to the highest level of scrutiny automatically.",
    "floor.list_owner":
        "A single register of every AI tool in use is maintained by {answer}.",
    "floor.list_fields":
        "For each tool the register records {answer}.",
    "floor.list_checked":
        "The register is checked for accuracy {answer}.",
    "floor.unlisted":
        "Use of a tool that is not on the register is handled as follows: "
        "{answer}.",
    "floor.disclose_where":
        "Where a member of the public interacts with an AI tool, or receives "
        "something an AI tool produced, they are told. Disclosure appears on "
        "{answer}.",
    "floor.reach_human":
        "A person can always be reached instead: {answer}.",
    "floor.disclose_who":
        "Disclosure wording is written by {answer} and approved by {also}.",
    "floor.disclose_home":
        "The approved wording is held at {answer}, so that one version is in "
        "use everywhere.",
    "floor.access_owner":
        "Responsibility for checking accessibility rests with {answer}.",
    "floor.access_when":
        "Accessibility is checked {answer}.",
    "floor.access_docs_yes":
        "Vendors must provide accessibility documentation before purchase. "
        "Public-facing AI tools meet WCAG 2.1 Level AA, the technical "
        "standard applying to state and local government under the ADA "
        "Title II web rule.",
    "floor.access_docs_no":
        "This organization does not require vendors to provide accessibility "
        "documentation before purchase. Note that public-facing tools remain "
        "subject to WCAG 2.1 Level AA under the ADA Title II web rule "
        "regardless; this decision affects how the obligation is verified, "
        "not whether it applies.",
    "floor.fallback_scope":
        "A written way to do the work without the tool is required for "
        "{answer}.",
    "floor.fallback_tested":
        "That fallback is tested {answer}.",
    "floor.data_terms":
        "Every agreement for a tool with AI in it provides that {answer}.",
    "floor.named":
        "Every tool has named against it {answer}.",
    # Branched, because "no" is now an answer. A shared template produced
    # "…is required for no tool", which is a sentence nobody would sign.
    "floor.plain_scope_all":
        "A plain-language description — what the tool does, what information "
        "it uses, and how it affects decisions — is required for every tool.",
    "floor.plain_scope_higher_risk":
        "A plain-language description — what the tool does, what information "
        "it uses, and how it affects decisions — is required for tools in "
        "the higher levels of scrutiny.",
    "floor.plain_scope_none":
        "This organization does not require a plain-language description of "
        "a tool as a condition of using it.",
    "floor.plain_who":
        "That description is written by {answer} and approved by {also}.",
    "floor.optional":
        "This organization additionally adopts the following as practice: "
        "{answer}.",

    # --- data
    "data.never":
        "The following must never be placed into a general-purpose AI tool: "
        "{answer}.",
    "data.approver":
        "Use of a particular set of information with an AI tool is approved "
        "by {answer}.",
    "data.retention":
        "On records retention: {answer}. A document is a public record based "
        "on what it is and what it is used for, regardless of whether an AI "
        "tool was involved in producing it.",
    "data.prompts":
        "On whether an employee's exchanges with an AI tool are records: "
        "{answer}.",

    # --- procurement
    "proc.today":
        "AI purchases follow this organization's existing process for "
        "approving software: {answer}. Approval thresholds are {also}. The "
        "requirements in this section attach to that process rather than "
        "replacing it.",
    "proc.cooperative":
        "On buying from state contracts, cooperative agreements or another "
        "government's contract: {answer}. Where AI arrives by that route it "
        "is still subject to this framework.",
    "proc.terms":
        "Every agreement for a tool with AI in it requires the vendor to: "
        "{answer}.",
    "proc.checker":
        "Agreements are checked against those terms by {answer}.",
    "proc.checker_none":
        "Agreements are checked against those terms as follows: {answer}.",
    "proc.added_ai":
        "Where a vendor adds AI to a product this organization already owns: "
        "{answer}.",
    "proc.reuse_yes":
        "Before buying something new, staff must establish whether a tool "
        "already held can address the problem.",
    "proc.full_cost_yes":
        "The full cost of an AI tool is estimated before any commitment.",
    "proc.cost_parts":
        "Cost includes {answer}.",

    # --- performance and retirement
    "watch.worth":
        "A tool is worth keeping where the following holds true: {answer}",
    "watch.baseline":
        "On recording a measurement before it goes live so that effect can be "
        "compared: {answer}.",
    "watch.who":
        "That review is carried out by {answer}, and recorded in {also}.",
    "watch.what":
        "Alongside whether it works, the following are monitored: {answer}.",
    "watch.failing":
        "Where a tool is not delivering: {answer}.",
    "watch.triggers":
        "A review of whether to keep a tool is triggered automatically by "
        "{answer}.",
    "watch.retire":
        "The decision to retire a tool rests with {answer}. When a tool is "
        "shut off: {also}",
    "watch.notice":
        "Staff and the public are given {answer} before a tool is turned off.",
    "watch.publish":
        "This organization publishes {answer}.",

    # --- incidents
    "bad.attach":
        "AI incidents are handled through the existing incident process: "
        "{answer}. One process is followed; a separate plan nobody remembers "
        "is not a plan.",
    "bad.existing_no":
        "This organization has no existing IT or security incident process. "
        "The arrangements in this section stand on their own until one "
        "exists.",
    "bad.report_to":
        "An employee who sees an AI tool produce a wrong or harmful result "
        "reports it to {answer}.",
    "bad.stopper":
        "{answer} may shut a tool off immediately, without waiting for a "
        "meeting.",
    "bad.lookback_yes":
        "After a serious problem, earlier work the tool touched is reviewed. "
        "If a tool was wrong today it was probably wrong yesterday.",
    "bad.lookback_far":
        "That review reaches back {answer}.",
    "bad.lookback_no":
        "Earlier work the tool touched is not reviewed after a problem.",
    "bad.tell":
        "Where an incident requires it, the following are told: {answer}.",
    "bad.writeup":
        "What happened is written up by {answer}, and that record is held in "
        "{also}.",

    # --- adoption
    "who.amend":
        "This framework may be changed by {answer}.",
    "who.review":
        "It comes back for review {answer}.",
    "done.where":
        "It is held: {answer}.",
}

#: Answers that produce a different sentence depending on what was chosen.
#: The key in SENTENCES is then `question.value`, so a yes and a no can each
#: say the thing that is actually true rather than sharing one hedged clause.
BRANCHED = {
    "org.delegated", "org.open_records", "org.it_authority",
    "risk.worst", "floor.ai_finalises",
    "floor.access_docs", "proc.reuse", "proc.full_cost", "bad.existing",
    "bad.lookback", "scope.review", "floor.plain_scope",
    "why.state_strategy", "why.manual", "why.ambition",
    "why.has_units", "why.units_all",
}

#: The formal register: the same statement, in the voice of an instrument.
#:
#: Only where the two genuinely differ. A key absent from here uses the
#: sentence above in both registers, which is deliberate — sixty duplicated
#: templates would drift, and most of these sentences are already the right
#: shape for either document. What changes is the framing of the sections a
#: reader meets first, and the clauses that carry an obligation.
#:
#: Both say exactly the same thing and bind the organization to exactly the
#: same rules. The client's instruction was about how it reads to whoever
#: picks it up, not about what it requires.
#:
#: One term throughout: "AI tool", which is what the definitions section
#: defines. These clauses previously read "artificial intelligence system",
#: which is a second name for a defined thing and so the exact ambiguity a
#: definitions section exists to prevent — a document defining "AI tool" and
#: then never using the phrase invites two readers to decide for themselves
#: whether the two mean the same.
FORMAL_SENTENCES: dict[str, str] = {
    "scope.covered":
        "This framework applies to {answer}.",
    "scope.excluded":
        "It does not apply to {answer}. Nothing in this exclusion relieves "
        "any AI tool of obligations arising under other policy.",
    # 3.3 asks for a role title — "Name one role, not a committee". So the
    # determination is made *by* somebody. "The determination is made as
    # follows: the District Manager." is the phrasing of a template that was
    # written for a process and handed a person.
    "scope.arbiter":
        "Where it is not clear whether a system falls within the scope of "
        "this framework, the determination is made by {answer}.",
    "scope.review_yes":
        "That determination is subject to subsequent review.",
    "scope.review_standalone":
        "That determination is final and is not subject to subsequent "
        "review.",
    "org.delegated_yes":
        "This organization administers programs delegated or funded by "
        "another level of government. The obligations attached to those "
        "programs apply to any AI tool used within them, in addition to the "
        "requirements of this framework.",
    "org.open_records_yes":
        "This organization is subject to open records and open meetings law. "
        "Records created with the assistance of an AI tool are public "
        "records on the same terms as any other record.",
    "org.it_authority_yes":
        "This organization's information technology program coordinates with "
        "a centralized information technology authority, {detail}. The use of "
        "any AI tool under this framework is coordinated with that authority.",

    "who.shape":
        "Responsibility for decisions under this framework is vested in "
        "{answer}.",
    "who.tiebreak":
        "Where those holding responsibility do not agree, the determination "
        "rests with {answer}.",
    # Phrased to avoid subject-verb agreement with a list. "…until legal
    # counsel, and the program that will actually use it *has* been consulted"
    # needs "have", and the answer can be one office or six — so the sentence
    # is built not to care.
    "who.consulted":
        "No AI tool may be approved for use without prior consultation with "
        "{answer}.",
    "who.without":
        "The following may proceed without that approval: {answer}.",

    "risk.worst_yes":
        "An AI tool rated high against any single factor is assigned the "
        "highest level of scrutiny, irrespective of its rating against the "
        "remaining factors. Averaging is not applied: a tool that is "
        "low-risk in seven respects and severe in one is a severe-risk "
        "tool.",
    "floor.ai_finalises_none":
        "No AI tool finalizes an action affecting a person's rights, money, "
        "standing or employment. Such tools may draft, sort, flag and "
        "recommend; the decision rests with a person.",
    "floor.access_docs_yes":
        "Vendors are required to provide accessibility documentation prior to "
        "purchase. Public-facing AI tools conform to WCAG 2.1 Level AA, the "
        "technical standard applicable to state and local government under "
        "the ADA Title II web rule.",
    "floor.list_owner":
        "A single register of every AI tool in use is maintained by "
        "{answer}.",
    "proc.terms":
        "Every agreement for a product containing an AI tool requires the "
        "vendor to: {answer}.",
}


#: Sections written as flowing paragraphs. All of them, in both registers.
#:
#: This was {"1", "2"}: Purpose and Scope as prose, and every section after
#: them as one numbered sentence per line — "4.1 … 4.2 … 4.3 …", on to 6.20.
#: The client, on the DEMO export: "Improved initial output on first couple
#: of pages, but then returns to numbered sequential output." He was right
#: about what it reads as. A policy is paragraphs under numbered sections; a
#: numbered line per sentence is a transcript of the answers with the
#: questions taken out, which is the thing the first export was faulted for.
#:
#: The sections keep their numbers, so "section 6" is still citable. What
#: went is the number on every sentence. Kept as a set so the two preview
#: tools that read it still work, and so narrowing it back is one line.
FLOWING = {s for s in (str(n) for n in range(1, 50))}

#: How sentences are gathered into a paragraph. See `paragraphs`.
PARAGRAPH_SENTENCES = 3
PARAGRAPH_CHARS = 460


#: Answers that are a refusal, and produce no clause at all.
#:
#: 1.8 is the optional catch-all — "is there anything unusual about your
#: organization?" — and "No" is a perfectly good answer to it. Printed as
#: clause 1.8 of a formal instrument it is a fragment: a numbered paragraph
#: that says only "No". The question was answered; there is simply nothing for
#: the document to say.
NOTHING_TO_SAY = {
    "org.unusual": {"no", "none", "nothing", "nope", "n/a", "na", "-"},
    "why.vision_year": {"no", "none", "nothing", "n/a", "na", "-"},
    "why.vision_five": {"no", "none", "nothing", "n/a", "na", "-"},
}

#: Answers written one item per line, printed as one list.
LINE_LISTS = {"why.vision_year", "why.vision_five"}

#: The document's own structure. Not the interview's — a reader looking for
#: the data rules should not have to know they were step 07.
SECTIONS: list[dict[str, Any]] = [
    # Purpose and Scope are separate sections, as they are in a real adopted
    # framework — the client's comparison. Purpose says why the document
    # exists and what it implements; Scope says how far it reaches. Running
    # them together produced a section that opened with "these rules cover
    # tools that write text", which is a scope statement standing in for a
    # purpose the module had never asked for.
    {"number": "1", "title": "Purpose",
     "purpose": "Why this framework exists, and what it implements.",
     "from_step": "11",
     "keys": ["why.reason", "why.vision_year", "why.vision_five",
              "why.ambition", "why.state_strategy",
              "why.federal", "why.conflict", "why.manual"]},
    {"number": "2", "title": "Scope",
     "purpose": "What this framework governs, and what it does not.",
     "from_step": "03",
     "keys": ["why.has_units", "why.units", "why.units_all",
              "why.routes", "scope.covered", "scope.excluded",
              "scope.arbiter", "scope.review", "org.delegated",
              "org.open_records", "org.unusual"]},
    # Third, where the reference framework puts it. A definitions clause is
    # what stops two people reading the same sentence differently a year
    # later, and it is the section a reader checks first to see whether a
    # document was drafted or assembled. Its content is built from answers
    # already given — nothing here asks a new question.
    {"number": "3", "title": "Definitions",
     "purpose": "The terms this framework fixes, and what each means here.",
     "from_step": "",
     "definitions": True,
     "keys": []},
    {"number": "4", "title": "Authority and governance",
     "purpose": "Who decides, who is consulted, and who has the final say.",
     "from_step": "04",
     "keys": ["who.shape", "who.seats", "who.tiebreak", "who.consulted",
              "who.cadence", "who.without", "who.record",
              "org.it_authority"]},
    {"number": "5", "title": "Levels of scrutiny",
     "purpose": "How this organization tells a low-stakes tool from a "
                "high-stakes one, and what each requires.",
     "from_step": "05",
     "keys": ["risk.levels", "risk.worst", "risk.revisit"],
     # Captioned as statements, not as the questions that produced them. A
     # table headed "For each level, what has to happen?" is the form showing
     # through the document again.
     "tiers": ("risk.tiers", "What each level requires")},
    {"number": "6", "title": "Operating principles",
     "purpose": "The eight requirements that are not optional, and how "
                "strictly this organization applies each.",
     "from_step": "06",
     "keys": ["floor.ai_finalises", "floor.final_action", "floor.list_owner",
              "floor.list_fields", "floor.list_checked", "floor.unlisted",
              "floor.disclose_where", "floor.reach_human",
              "floor.disclose_who", "floor.disclose_home",
              "floor.access_owner", "floor.access_when", "floor.access_docs",
              "floor.fallback_scope", "floor.fallback_tested",
              "floor.data_terms", "floor.named", "floor.plain_scope",
              "floor.plain_who", "floor.optional"]},
    {"number": "7", "title": "Information and records",
     "purpose": "What may be placed into an AI tool, and what becomes a "
                "record when it is.",
     "from_step": "07",
     "keys": ["data.never", "data.approver", "data.retention",
              "data.prompts"]},
    {"number": "8", "title": "Procurement",
     "purpose": "The terms an AI purchase requires that an ordinary purchase "
                "does not.",
     "from_step": "08",
     "keys": ["proc.today", "proc.cooperative", "proc.terms", "proc.checker",
              "proc.checker_none", "proc.added_ai", "proc.reuse",
              "proc.full_cost", "proc.cost_parts"]},
    {"number": "9", "title": "Performance, reporting and retirement",
     "purpose": "How this organization knows a tool is working, and how it "
                "stops using one that is not.",
     "from_step": "09",
     "keys": ["watch.worth", "watch.baseline", "watch.who", "watch.what",
              "watch.failing", "watch.triggers", "watch.retire",
              "watch.notice", "watch.publish"],
     "tiers": ("watch.cadence", "How often each level is reviewed")},
    {"number": "10", "title": "When something goes wrong",
     "purpose": "How a problem is reported, ranked, stopped and recorded.",
     "from_step": "10",
     "keys": ["bad.existing", "bad.attach", "bad.report_to", "bad.stopper",
              "bad.lookback", "bad.lookback_far", "bad.tell", "bad.writeup"],
     "tiers": ("bad.levels", "How serious a problem is"),
     "matrix": ("bad.speed", "How quickly each level must be reported")},
    {"number": "11", "title": "Amendment, review and publication",
     "purpose": "How this framework changes, and when it is looked at again.",
     "from_step": "",
     "keys": ["who.amend", "who.review", "done.where"]},
]


#: Question kinds whose answer the organization typed. Their words go in as
#: they wrote them — no re-casing, no reflowing.
THEIR_OWN_WORDS = ("short", "long", "rows")


def _answer_text(question: m1.Question, answers: dict[str, Any]) -> str:
    """The organization's answer, as a phrase that can sit in a sentence."""
    said = m1.phrase_pairs(question, answers)
    if not said:
        return ""
    if question.kind in THEIR_OWN_WORDS:
        # Their sentence keeps its full stop; a role title does not gain one.
        keep = question.kind == "long"
        return _join([_fits_midsentence(line) for line, _ in said],
                     keep_stops=keep)
    # A label this project wrote can be lowered to fit the sentence. A choice
    # they typed cannot — that is their wording, and it goes in as written.
    return _join([line if theirs else _lower_first(line)
                  for line, theirs in said])


#: Sentences chosen by an answer other than their own. First match wins.
#:
#: `BRANCHED` already covers a clause that turns on what *this* question was
#: answered. This covers a clause that turns on what an earlier one was —
#: which 4.2 and 4.3 need, because both are now asked differently depending
#: on whether responsibility sits with one person or with a body.
#:
#: Without it, an organization that named one accountable person and one role
#: got "The roles holding that responsibility are Utilities Director. Where
#: one person holds more than one of these…" — the plural template reading a
#: single answer back, which is the complaint that produced the adaptive
#: question in the first place, reappearing in the finished document.
SENTENCES_WHEN: dict[str, list[dict[str, Any]]] = {
    "who.seats": [
        {"if": {"key": "who.shape", "is": "one"},
         "text": "The role holding that responsibility is {answer}."},
    ],
    "who.tiebreak": [
        {"if": {"key": "who.shape", "is": "one"},
         "text": "Where that person is unavailable, the decision rests with "
                 "{answer}."},
    ],
}


def _template(key: str, answers: dict[str, Any]) -> str | None:
    """The sentence for this key, in the register the document is written in.

    Falls back to the plain one where there is no formal variant, so a key
    only appears in `FORMAL_SENTENCES` when the two genuinely differ.
    """
    formal = m1.register_of(answers) == m1.FORMAL
    for rule in SENTENCES_WHEN.get(key, []):
        if m1.holds(rule.get("if"), answers):
            if formal and rule.get("formal"):
                return str(rule["formal"])
            return str(rule.get("text") or "") or None
    if formal and key in FORMAL_SENTENCES:
        return FORMAL_SENTENCES[key]
    return SENTENCES.get(key)


def _clause_for(key: str, answers: dict[str, Any]) -> Clause | None:
    question = m1.by_key(key)
    if question is None or not m1.visible(question, answers):
        return None
    said = m1.describe(question, answers)
    if said["state"] != "answered":
        return None

    # A branching question picks its sentence by what was chosen, so a "no"
    # states what is true rather than sharing a clause written for "yes".
    if key in BRANCHED:
        value, _ = m1.value_of(answers, key)
        template = _template(f"{key}_{value}", answers)
        if template is None:
            return None
        # A branched sentence can still carry what they typed: 11.2's "yes"
        # opens a box for the name of the strategy, and a clause that says
        # "this organization's implementation of" and then stops is worse
        # than no clause.
        _, extras = m1.value_of(answers, key)
        typed = str(extras.get("detail", "")).strip()
        paired = m1.paired(question, answers)
        if "{detail}" in template and not typed:
            return None
        if "{also}" in template and not paired:
            paired = "a role not yet named"
        return Clause(template.replace("{detail}", typed)
                              .replace("{also}", _fits_midsentence(paired)),
                      question.number)

    template = _template(key, answers)
    if template is None:
        return None
    text = _answer_text(question, answers)
    if not text:
        return None
    # Answered, and the answer is "nothing to add". No clause.
    if text.strip().strip(".").lower() in NOTHING_TO_SAY.get(key, set()):
        return None
    # A two-part question — "who writes it, and who approves it" — puts its
    # second half where the template asks for it, rather than having the
    # field's own label appended, which produced "written and approved by the
    # Manager and and who approves it: The board."
    # 11.1a and 11.1b ask for one goal per line. In the document the lines
    # are one list, in their own words and order.
    if key in LINE_LISTS:
        text = "; ".join(line.strip().rstrip(".;") for line in text.splitlines()
                         if line.strip())
    # A template that closes the sentence after their words, handed words
    # that already end in a full stop, would print two.
    if template.endswith("{answer}.") and text.endswith("."):
        text = text[:-1]
    filled = template.replace("{answer}", text)
    if "{also}" in filled:
        # Always mid-sentence, so a leading article they typed is lowered —
        # "approved by The board." was the second half of a sentence keeping
        # a capital that belonged to the start of an answer box. Nothing else
        # in their words is touched.
        filled = filled.replace("{also}", _fits_midsentence(
            m1.paired(question, answers) or "nobody recorded"))
    return Clause(filled, question.number)


def _tier_table(key: str, answers: dict[str, Any]) -> dict[str, Any] | None:
    """A grid stays a grid. Four things about each of three levels is a table
    in any document a person would write by hand."""
    question = m1.by_key(key)
    if question is None or not m1.visible(question, answers):
        return None
    held, _ = m1.value_of(answers, key)
    if not isinstance(held, dict) or not held:
        return None

    shown = question.as_dict(answers)
    fields = [f for f in shown["tier_fields"] if f["key"] != "name"]
    rows = []
    for tier in shown["rows"]:
        got = held.get(tier["value"]) or {}
        if not got:
            continue
        # Their own name for the level, where they gave one.
        label = str(got.get("name") or tier["label"])
        cells = []
        for spec in fields:
            said = got.get(spec["key"], "")
            labels = {o["value"]: o["label"] for o in spec.get("options", [])}
            cells.append(str(labels.get(said, said)))
        rows.append([label] + cells)
    if not rows:
        return None
    return {"title": m1._fill(question.prompt, answers),
            "source": question.number,
            "head": ["Level"] + [f["label"] for f in fields],
            "rows": rows}


def _matrix_table(key: str, answers: dict[str, Any]) -> dict[str, Any] | None:
    question = m1.by_key(key)
    if question is None or not m1.visible(question, answers):
        return None
    held, _ = m1.value_of(answers, key)
    if not isinstance(held, dict) or not held:
        return None
    picks = {o.value: o.label for o in question.row_options}
    rows = [[r.label, picks.get(str(held[r.value]), str(held[r.value]))]
            for r in m1.rows_for(question, answers) if r.value in held]
    if not rows:
        return None
    return {"title": m1._fill(question.prompt, answers),
            "source": question.number,
            "head": ["", ""], "rows": rows}


def _family(source: str) -> str:
    """The question a clause belongs to, without its sub-part.

    6.2a, 6.2b, 6.2c and 6.2d are four parts of one obligation — who keeps the
    register, what it records, how often it is checked, what happens to a tool
    not on it — and they belong in one paragraph. 4.1 and 4.2 are two
    different questions.
    """
    return source.rstrip("abcdefghijklmnopqrstuvwxyz")


def paragraphs(section: Section) -> list[list[Clause]]:
    """A section's clauses, gathered into paragraphs a person would write.

    Two rules, in this order.

    A question that produced more than one sentence is one paragraph on its
    own. Those are the parts of a single obligation, and splitting them, or
    running them into the next obligation, both read worse than keeping them
    together — Operating principles comes out as one paragraph per principle,
    which is how the reference framework sets it.

    Questions that produced a single sentence each are run together, up to
    `PARAGRAPH_SENTENCES` or `PARAGRAPH_CHARS`, whichever comes first. Joining
    a whole section with no limit produced a nine-sentence wall under Scope,
    which is why this has a ceiling; one sentence per paragraph is the
    transcript this replaces, which is why it has a floor.

    The order is never changed. A reader checking the document against their
    answers finds them in the sequence they gave them.
    """
    families: list[list[Clause]] = []
    for clause in section.clauses:
        key = _family(clause.source)
        if families and _family(families[-1][0].source) == key and key:
            families[-1].append(clause)
        else:
            families.append([clause])

    out: list[list[Clause]] = []
    pending: list[Clause] = []
    # Which paragraphs in `out` were gathered from single sentences, so that a
    # lone sentence left at the end can join one of those rather than a
    # paragraph that is a single obligation.
    gathered: set[int] = set()

    def flush() -> None:
        if pending:
            gathered.add(len(out))
            out.append(list(pending))
            pending.clear()

    for group in families:
        if len(group) > 1:
            flush()
            out.append(group)
            continue
        pending.extend(group)
        length = sum(len(c.text) for c in pending)
        if len(pending) >= PARAGRAPH_SENTENCES or length >= PARAGRAPH_CHARS:
            flush()

    # One sentence left over reads as an afterthought standing alone. It joins
    # the paragraph before it when that paragraph was gathered the same way
    # and there is room; otherwise it stands, because attaching it to a
    # different obligation would say something the organization did not.
    if len(pending) == 1 and out and (len(out) - 1) in gathered \
            and len(out[-1]) < PARAGRAPH_SENTENCES + 1:
        out[-1].extend(pending)
        pending.clear()
    flush()
    return out


def definitions(answers: dict[str, Any]) -> list[tuple[str, str]]:
    """The terms this framework fixes, and what each one means here.

    A definitions clause is what separates a policy from a memo: it is the
    section that stops two people reading the same sentence differently
    eighteen months later, and the reference framework has one at section 3.

    Every entry is assembled from an answer, on the same rule as every other
    sentence in this module. A term whose meaning nobody has decided is left
    out rather than filled with a plausible sentence — an invented definition
    is the most damaging kind of invention there is, because everything
    downstream is then read through it.
    """
    out: list[tuple[str, str]] = []

    covered = _answer_text(m1.by_key("scope.covered"), answers)
    excluded = _answer_text(m1.by_key("scope.excluded"), answers)
    if covered:
        meaning = (f"For the purposes of this framework, an AI tool means "
                   f"{covered}.")
        if excluded:
            meaning += (f" It does not include {excluded}, which this "
                        f"framework does not govern.")
        out.append(("AI tool", meaning))

    # What they call the body or person that decides. Read from the decider
    # module, which is where that one answer lives for the whole application.
    #
    # Not wrapped in a bare `except`: this called a `decider.label()` that has
    # never existed, and the except swallowed the AttributeError and dropped
    # the definition without a word. A missing file is a real condition worth
    # tolerating; a misspelled function is a bug, and should behave like one.
    from app import decider
    try:
        named = str(decider.body() or "").strip()
    except (OSError, ValueError):
        named = ""
    shape = _answer_text(m1.by_key("who.shape"), answers)
    if named and shape:
        # `decider.body()` carries its article — "the Council" — which is
        # right mid-sentence and wrong as the headword of a definition.
        term = named[0].upper() + named[1:] if named[:1].islower() else named
        out.append((term, f"The body in which responsibility for decisions "
                          f"under this framework is vested. It is {shape}."))

    levels = _tier_table("risk.tiers", answers)
    if levels and levels.get("rows"):
        named_levels = _join([str(row[0]) for row in levels["rows"]])
        out.append(("Levels of scrutiny",
                    f"The categories by which this organization sorts an AI "
                    f"tool according to what it could affect: {named_levels}. "
                    f"What each level requires is set out in the section on "
                    f"levels of scrutiny."))

    owner = _answer_text(m1.by_key("floor.list_owner"), answers)
    if owner:
        out.append(("The list of AI tools",
                    f"The single record of every AI tool in use by this "
                    f"organization, kept by {owner}. No tool is in use unless "
                    f"it is on the list."))

    never = _answer_text(m1.by_key("data.never"), answers)
    if never:
        out.append(("Restricted information",
                    f"Information this organization has determined must never "
                    f"be placed into a general-purpose AI tool: {never}."))

    return out


def sections(answers: dict[str, Any]) -> list[Section]:
    """The framework, section by section, as statements."""
    out = []
    for spec in SECTIONS:
        section = Section(number=spec["number"], title=spec["title"],
                          purpose=spec["purpose"])
        if spec.get("definitions"):
            section.terms = definitions(answers)
        for key in spec["keys"]:
            clause = _clause_for(key, answers)
            if clause is not None:
                section.clauses.append(clause)
        for name in ("tiers", "matrix"):
            found = spec.get(name)
            if not found:
                continue
            key, caption = found
            table = (_tier_table if name == "tiers" else _matrix_table)(
                key, answers)
            if table is not None:
                section.tables.append({**table, "title": caption})
        step = spec.get("from_step")
        if step:
            section.own_words = str(
                m1.value_of(answers, m1.own_words_key(step))[0] or "").strip()
        out.append(section)
    return out


def gaps(answers: dict[str, Any],
         built: list[Section] | None = None) -> list[dict[str, str]]:
    """What this organization has not settled, with who owns settling it.

    Its own section rather than scattered "not yet decided" lines, because a
    reader deciding whether to adopt needs to see the whole list at once.

    Every "We don't know" is listed, and so is every question left unanswered
    in a section that came out with nothing in it. An empty section prints
    "Not yet decided. Listed in the section on matters not yet settled" — and
    that list used to hold only the "We don't know" answers, so a section
    nobody had reached yet sat above "Nothing. Every question this framework
    asked has an answer." The document contradicted itself.
    """
    out = list(m1.gaps(answers))
    listed = {g.get("key") for g in out}
    built = built if built is not None else sections(answers)
    for spec, section in zip(SECTIONS, built):
        if not section.empty:
            continue
        keys = list(spec["keys"]) + [spec[n][0] for n in ("tiers", "matrix")
                                     if spec.get(n)]
        added = False
        for key in keys:
            question = m1.by_key(key)
            if question is None or key in listed:
                if key in listed:
                    added = True        # already there as a "We don't know"
                continue
            if not m1.visible(question, answers) or \
                    m1.answered(question, answers):
                continue
            out.append({"key": key, "number": question.number,
                        "step": key.split(".")[0], "question": question.prompt,
                        "owner": "", "needs_owner": True, "unanswered": True})
            listed.add(key)
            added = True
        if not added:
            # Nothing to point at — every question in it hidden or answered in
            # a way that writes no clause. The section itself is named, so
            # the line under its heading is still true.
            out.append({"key": f"section.{section.number}",
                        "number": f"Section {section.number}",
                        "step": "", "question": f"{section.title} — nothing "
                        "decided here yet", "owner": "", "needs_owner": True,
                        "unanswered": True})
    return out


def title_of(answers: dict[str, Any], agency: str) -> str:
    """What they called it, or a sensible name built from the agency's."""
    chosen = str(m1.value_of(answers, "done.title")[0] or "").strip()
    if chosen:
        return chosen
    return f"{agency} — AI Governance Framework"


def coverage(answers: dict[str, Any]) -> tuple[int, int]:
    """(sections with something in them, sections in the framework)."""
    built = sections(answers)
    return sum(1 for s in built if not s.empty), len(built)






