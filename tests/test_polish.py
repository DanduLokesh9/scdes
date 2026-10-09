"""Tidying the wording without changing what the document requires.

The client asked for this: "How would you like the language to appear: As
written or Polished... polished uses an LLM to run through, clean up, and do
some of the editorial work to closer match that north star we have." And he
is right that nobody will hand-edit ninety-six clauses.

Almost every test here is about a rewrite being rejected. That is the point.
`prose.py` promises that every sentence comes from an answer somebody gave,
and a language tool let loose on a policy will eventually turn "may" into
"shall", drop a deadline, or lose the role a duty was assigned to. In a
document somebody signs those are not typos. So each rewrite is checked
against its original, and a rewrite that fails any check is discarded in
favor of the sentence the answers assembled.
"""

from __future__ import annotations

import pytest

from app import module_one as m1, polish, prose


# ------------------------------------------------------------ the checking

def test_an_honest_tidy_is_accepted() -> None:
    before = ("Where those holding responsibility do not agree, the "
              "determination rests with the District Manager.")
    after = ("Where those holding responsibility disagree, the determination "
             "rests with the District Manager.")
    ok, why = polish.check(before, after)
    assert ok, why


def test_an_unchanged_clause_is_accepted() -> None:
    text = "AI matters are considered quarterly."
    ok, why = polish.check(text, text)
    assert ok
    assert why == "unchanged"


@pytest.mark.parametrize("before,after,because", [
    # The one that matters most in a signed document.
    ("No AI tool shall finalize an action without a person.",
     "No AI tool may finalize an action without a person.",
     "shall"),
    ("Incidents must be reported within three days.",
     "Incidents should be reported within three days.",
     "must"),
    # A negation quietly dropped inverts the rule.
    ("Records are not published without review.",
     "Records are published without review.",
     "not"),
])
def test_a_changed_obligation_is_rejected(before, after, because) -> None:
    ok, why = polish.check(before, after)
    assert not ok
    assert because in why, why


# --------------------------------------------- raising the register, not the duty

def test_the_present_indicative_may_be_rendered_as_shall() -> None:
    """The single most common edit, and the one the client is paying for.

    In drafting convention the present indicative already states a rule in
    force, so "the register is checked" and "the register shall be checked"
    bind the organization identically — the second just reads like an adopted
    instrument. An earlier version of this module compared modal counts
    exactly and threw away half of every pass for this reason.
    """
    ok, why = polish.check(
        "The register is checked for accuracy twice a year.",
        "The register shall be checked for accuracy twice a year.")
    assert ok, why


def test_ai_may_be_spelled_out() -> None:
    """Consistency of terms, and it must not trip the length band.

    The expansion adds twenty-one characters every time it happens, which on
    a short clause is most of the clause.
    """
    ok, why = polish.check(
        "AI matters are considered quarterly.",
        "Artificial intelligence matters shall be considered quarterly.")
    assert ok, why


def test_spelling_out_ai_is_not_dropping_a_name() -> None:
    """"AI-assisted" is capitalized, so expanding it looked like losing a
    named thing."""
    ok, why = polish.check(
        "The schedule does not mention AI-assisted documents.",
        "The schedule does not address artificial intelligence-assisted "
        "documents.")
    assert ok, why


def test_expanding_ai_is_not_a_negation() -> None:
    """A real bug, and an invisible one.

    The negation check forgives a negation folded into a word ("not agree"
    becoming "disagree"), which it detects by stripping a negating prefix and
    looking for the stem in the original. Matching any shared prefix read
    "intelligence" as "in" plus a stem beginning "tell" — so every rewrite
    that expanded AI in a clause containing a same-length word was refused
    for inventing a negation that was never there.
    """
    ok, why = polish.check(
        "The obligations attached to those programs apply to AI used within "
        "them.",
        "The obligations attached to those programs shall apply to "
        "artificial intelligence used within them.")
    assert ok, why
    assert polish._absorbed("government", "intelligence") == 0


def test_a_recommendation_may_not_become_a_duty() -> None:
    """Mandatory may rise out of the indicative but not out of a "should"."""
    ok, why = polish.check("Incidents should be reported promptly.",
                           "Incidents shall be reported promptly.")
    assert not ok
    assert "recommendation" in why, why


def test_a_permission_may_not_become_a_duty() -> None:
    ok, why = polish.check("Staff may consult the register.",
                           "Staff shall consult the register.")
    assert not ok
    assert "permission" in why, why


def test_capability_may_not_become_permission() -> None:
    """"Can" in the assembled prose is always capability — "whether a tool
    already held can address the problem" — so it is not counted as a
    permission. "May" is, which keeps this drift caught."""
    ok, why = polish.check(
        "On recording a measurement so that effect can be compared: "
        "sometimes.",
        "With respect to recording a measurement so that effect may be "
        "compared: sometimes.")
    assert not ok
    assert "permission" in why, why


def test_a_formal_equivalent_is_accepted() -> None:
    """Substituting a formal word for a plain one is what copy-editing is.

    An earlier version banned any word not in the original, on the theory
    that a copy-edit introduces no new ideas. It rejected "cover" becoming
    "apply to" and "changed" becoming "amended", which is to say it rejected
    the entire feature.
    """
    for before, after in [
        ("This framework may be changed by the same authority that adopted "
         "it.",
         "This framework may be amended by the same authority that adopted "
         "it."),
        ("Accessibility is checked before purchase, before it goes live, and "
         "once a year.",
         "Accessibility shall be verified prior to procurement, prior to "
         "deployment, and annually thereafter."),
    ]:
        ok, why = polish.check(before, after)
        assert ok, f"{why}: {after}"


# ------------------------------------------------------- names and party
# ---------------------------------------------------------------- substitution

def test_an_invented_party_is_rejected() -> None:
    """The worst thing a measured pass produced.

    A clause about "our information" came back naming a body this
    organization does not have and the clause never mentioned. An invented
    party in a document somebody signs is not a wording problem.
    """
    ok, why = polish.check(
        "Every agreement provides that the vendor may not train on our "
        "information.",
        "Every agreement shall provide that the vendor may not train on the "
        "Council's information.")
    assert not ok
    assert "invented a name" in why, why


def test_capitalising_a_word_already_there_is_not_inventing_one() -> None:
    """"A state agency" becoming "a State agency" is house style, not a new
    party, so the check compares against every word of the original and not
    only its capitalized ones."""
    ok, why = polish.check(
        "Where an incident requires it, a state agency is told.",
        "Where an incident so requires, a State agency is notified.")
    assert ok, why


def test_a_substituted_subject_is_rejected() -> None:
    """Nothing else catches this one, which is why the vocabulary backstop
    stays: "It comes back for review every year" means the framework, and the
    rewrite made it the clause."""
    ok, why = polish.check("It comes back for review every year.",
                           "The clause shall be reviewed annually.")
    assert not ok


# ------------------------------------------------------------- definitions

def test_a_definition_may_not_acquire_a_duty() -> None:
    """A definition says what a term means and requires nothing of anybody.

    Polishing the definitions alongside the clauses did visible damage before
    they were told apart: "The Council. The body in which responsibility for
    decisions under this framework is vested" came back as "Responsibility
    for decisions under this framework shall be vested in an existing body",
    which defines nothing and restates the clause that vests it, under a
    headword it no longer describes.
    """
    before = ("The body in which responsibility for decisions under this "
              "framework is vested.")
    after = ("Responsibility for decisions under this framework shall be "
             "vested in an existing body.")
    ok, why = polish.check(before, after, defining=True)
    assert not ok
    assert "gained a duty" in why, why

    # And the same rewrite of a clause is fine, because raising the present
    # indicative is a change of register rather than of duty.
    assert polish.check(before, after)[0]


def test_a_definition_may_still_be_tidied() -> None:
    ok, why = polish.check(
        "The single record of every AI tool in use by this organization, "
        "kept by the Operations Lead.",
        "The single record of every artificial intelligence tool in use by "
        "this organization, maintained by the Operations Lead.",
        defining=True)
    assert ok, why


def test_a_stray_quotation_mark_is_rejected() -> None:
    """Nothing else caught this one.

    A definition came back as 'Impact tiers" means the categories by which…'
    — a defined-term construction with the front of it missing and an
    unmatched quote left in the document. The invented term sat at the start
    of a sentence, where capitalization says nothing, so the name check could
    not see it either.
    """
    ok, why = polish.check(
        "The categories by which this organization sorts an AI tool "
        "according to what it could affect: Routine and Elevated.",
        'Impact tiers" means the categories by which this organization sorts '
        'an artificial intelligence tool according to what it could affect: '
        'Routine and Elevated.',
        defining=True)
    assert not ok
    assert "quotation mark" in why, why


def test_a_defined_term_may_be_quoted() -> None:
    """How a definitions section is properly written.

    Refusing any new quotation mark also refused '"AI tool" means a tool
    that generates text…'. An odd count is the actual defect; a pair is
    idiomatic drafting.
    """
    ok, why = polish.check(
        "For the purposes of this framework, an AI tool means tools that "
        "write text, images or code.",
        'For the purposes of this framework, "AI tool" means a tool that '
        'generates text, images, or code.',
        defining=True)
    assert ok, why


def test_using_the_defined_term_is_not_measured_as_growth() -> None:
    """The length band must not notice which spelling of the term is used.

    The two forms differ by twenty-one characters. Measured by expanding
    rather than contracting, "Staff and the public are given 30 days before
    a tool is turned off" becoming "Staff and the public shall be given 30
    days' notice before an AI tool is withdrawn from service" — a 42%
    rewrite — was counted as 73% growth and thrown away.
    """
    ok, why = polish.check(
        "Staff and the public are given 30 days before a tool is turned "
        "off.",
        "Staff and the public shall be given 30 days' notice before an AI "
        "tool is withdrawn from service.")
    assert ok, why


def test_without_regard_to_is_not_a_new_negation() -> None:
    """"Without" counts as a negation, and "without regard to" is not one."""
    ok, why = polish.check(
        "A document is a public record regardless of whether an AI tool was "
        "involved in producing it.",
        "A document shall be a public record without regard to whether an AI "
        "tool was involved in producing it.")
    assert ok, why


def test_upon_is_accepted_for_when() -> None:
    """Same condition, different spelling. Counting only one refused the
    rewrite for dropping a condition it had kept."""
    ok, why = polish.check(
        "Our data is returned and deleted when we leave.",
        "Our data shall be returned and deleted upon our departure.")
    assert ok, why


def test_relied_upon_is_not_a_condition() -> None:
    """"Upon" is temporal in "upon termination" and part of the verb in
    "relied upon". Folding it to "when" without telling them apart read "the
    answer was relied upon" as a condition that appeared out of nowhere."""
    ok, why = polish.check(
        "We treat them as personal working notes unless the answer was "
        "relied on for an official action.",
        "Such exchanges shall be treated as personal working notes unless "
        "the answer was relied upon for an official action.")
    assert ok, why


def test_a_quoted_role_title_survives() -> None:
    """Single quotes are not counted, because the assembled prose uses them
    for a quoted role title and counting them would refuse every rewrite of
    that clause."""
    ok, why = polish.check(
        "Every tool has named against it someone in the program, commonly "
        "called a ‘product owner’.",
        "Every tool shall have named against it a person in the program, "
        "commonly referred to as a ‘product owner’.")
    assert ok, why


def test_a_closed_list_may_not_be_made_open() -> None:
    """Whether a list is exhaustive decides whether something absent from it
    is permitted. "Restricted information: names, addresses, personnel
    files" is closed; the same sentence with "includes" is not."""
    ok, why = polish.check(
        "Information that must never be placed into a general-purpose AI "
        "tool: names, addresses, and personnel files.",
        "Information that must never be placed into a general-purpose "
        "artificial intelligence tool includes: the names, addresses, and "
        "personnel files.",
        defining=True)
    assert not ok
    assert "closed list was made open" in why, why


def test_the_definitions_are_polished_with_the_clauses(monkeypatch) -> None:
    """Otherwise the document contradicts itself.

    Section 3 defined an AI tool as "tools that write text… that recognize
    things in photos" while section 2 required the framework to apply to
    "tools that generate text… that recognize content in photographs". Both
    are assembled from the same answer. A definition that does not match the
    clause it defines is worse than an unpolished one.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    monkeypatch.setattr(polish, "available", lambda: (True, ""))

    seen: list[bool] = []

    def fake(provider, text, *, defining=False):
        seen.append(defining)
        return text, "unchanged", text

    monkeypatch.setattr(polish, "one", fake)

    class Fake:
        name = "fake"
        model = "fake-1"

    import app.provider as provider_mod
    monkeypatch.setattr(provider_mod, "AnthropicProvider", Fake)

    answers = {"scope.covered": {"value": ["writes"]},
               "who.shape": {"value": "existing"}}
    built = prose.sections(answers)
    assert any(section.terms for section in built), "no definitions to polish"

    polish.sections(built, answers)
    assert any(seen), "nothing was sent at all"
    assert True in seen, "the definitions were not polished"
    assert False in seen, "the clauses were not polished"


# ----------------------------------------------------- timing and frequency

def test_a_review_cycle_cannot_appear_from_nowhere() -> None:
    """How often something happens is a requirement carrying no digits, so
    the number check cannot see it."""
    ok, why = polish.check(
        "The register lists every tool in use.",
        "The register shall list every tool in use and shall be reviewed "
        "annually.")
    assert not ok


def test_every_year_may_become_annually() -> None:
    ok, why = polish.check(
        "The report is published every year by the Clerk.",
        "The report shall be published annually by the Clerk.")
    assert ok, why


def test_prior_to_is_accepted_for_before() -> None:
    """Exact synonyms, and refusing the swap cost real rewrites."""
    ok, why = polish.check(
        "The full cost is estimated before any commitment.",
        "The full cost shall be estimated prior to any commitment.")
    assert ok, why


def test_a_place_is_not_a_deadline() -> None:
    """"Within" is two words. In "within 3 days" it is a deadline; in
    "someone within the program" it is a preposition and means nothing to the
    rule. Counting both refused a fair edit."""
    ok, why = polish.check(
        "Every tool has named against it someone in the program that uses "
        "it.",
        "Every tool shall have named against it a person within the program "
        "that uses it.")
    assert ok, why


def test_a_deadline_that_appears_from_nowhere_is_rejected() -> None:
    ok, why = polish.check(
        "A problem is reported to the Operations Lead.",
        "A problem shall be reported to the Operations Lead within 3 days.")
    assert not ok


def test_the_following_is_not_a_deadline() -> None:
    """"Prior to" folds to "before" so the two spellings compare equal, and
    "following" folds to "after" for the same reason. But "the following are
    told:" introduces a list and is not a temporal at all — without taking it
    out of the way first, that clause counted an "after" that was never
    there, and its rewrite was refused for dropping a deadline it never had.
    """
    ok, why = polish.check(
        "Where an incident requires it, the following are told: your board, "
        "the person affected, and a federal partner.",
        "Where an incident so requires, the following are notified: your "
        "board, the person affected, and a federal partner.")
    assert ok, why


def test_a_changed_number_is_rejected() -> None:
    """"Within three days" is not "within five days"."""
    ok, why = polish.check("Incidents must be reported within 3 days.",
                           "Incidents must be reported within 5 days.")
    assert not ok
    assert "numbers changed" in why


def test_a_dropped_role_is_rejected() -> None:
    """A duty with nobody attached to it is not the same duty."""
    ok, why = polish.check(
        "The register is kept by the Permitting Manager.",
        "The register is kept up to date.")
    assert not ok
    assert "dropped a name" in why or "length" in why, why


def test_a_rewrite_that_loses_half_the_clause_is_rejected() -> None:
    before = ("Where it is not clear whether a system falls within the scope "
              "of this framework, the determination is made by the District "
              "Manager, and that determination is final.")
    ok, why = polish.check(before, "The District Manager decides.")
    assert not ok


def test_a_rewrite_that_grows_a_new_requirement_is_rejected() -> None:
    before = "AI matters are considered quarterly."
    after = ("AI matters are considered quarterly, and the council shall "
             "publish an annual report summarizing every decision taken "
             "during the preceding twelve months, with minutes attached.")
    ok, why = polish.check(before, after)
    assert not ok


def test_a_model_answering_instead_of_rewriting_is_rejected() -> None:
    """Providers sometimes reply conversationally. That is not a clause."""
    for reply in ("Here is the rewritten clause: AI matters are considered "
                  "quarterly.",
                  "Sure! AI matters are considered quarterly.",
                  "I have improved the flow: AI matters are considered "
                  "quarterly."):
        ok, why = polish.check("AI matters are considered quarterly.", reply)
        assert not ok, reply
        assert "answered rather than rewriting" in why


def test_a_clause_turned_into_a_list_is_rejected() -> None:
    ok, why = polish.check(
        "Decisions are recorded in the minutes, kept by the Clerk.",
        "- Decisions are recorded in the minutes\n- The Clerk keeps them")
    assert not ok
    assert "list" in why


def test_an_empty_reply_is_rejected() -> None:
    ok, why = polish.check("Something.", "")
    assert not ok
    assert "returned nothing" in why


def test_a_completely_different_sentence_is_rejected() -> None:
    """Shares no vocabulary with the original, so it is not an edit of it."""
    ok, why = polish.check(
        "The register is checked for accuracy once a year by the Clerk.",
        "Every vendor agreement includes a breach notification period.")
    assert not ok


# ----------------------------------------------------------- what it will not do

def test_it_refuses_to_run_without_a_provider(monkeypatch) -> None:
    """Fails to the safe side: no tool, no polish, and the document says so
    rather than looking as though polishing ran and did nothing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    ok, why = polish.available()
    assert not ok
    # "Never write model. Write tool." — including in the sentence that
    # explains why polishing did not happen, which goes into the document.
    assert "writing tool" in why.lower()
    for word in m1.BANNED:
        assert word not in why.lower(), word

    outcome = polish.sections([], {})
    assert outcome.ran is False
    assert outcome.note
    assert "as your answers assemble it" in outcome.note


def test_their_own_words_are_never_sent(monkeypatch) -> None:
    """The clauses carrying text somebody typed are skipped outright.

    `prose.py` already refuses to re-case what they wrote; this refuses to
    rewrite it. Checked by counting what the pass skipped rather than by
    trusting the instruction given to the provider.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    sent = []

    class Fake:
        name = "fake"
        model = "fake-1"

        class client:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    sent.append(kwargs["messages"][0]["content"])
                    raise RuntimeError("no network in tests")

    monkeypatch.setattr(polish, "available", lambda: (True, ""))
    import app.provider as provider_mod
    monkeypatch.setattr(provider_mod, "AnthropicProvider", Fake)

    answers = {"who.tiebreak": {"value": "The District Manager"},
               "risk.levels": {"value": "two"}}
    built = prose.sections(answers)
    outcome = polish.sections(built, answers)

    # 4.3 is `kind="short"` — their own words — so its clause must not appear
    # in anything sent.
    assert outcome.skipped_their_words > 0
    for body in sent:
        assert "District Manager" not in body or "{" in body, body


def test_a_failed_rewrite_leaves_the_clause_exactly_as_assembled(
        monkeypatch) -> None:
    """The important guarantee: a rejection costs an unpolished sentence, not
    a wrong one."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    class Reply:
        stop_reason = "end_turn"
        content = [type("B", (), {"type": "text",
                                  "text": "It may be reported whenever."})()]

    class Fake:
        name = "fake"
        model = "fake-1"

        class client:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    return Reply()

    before = "Incidents must be reported within 3 days."
    text, why, attempted = polish.one(Fake(), before)
    assert text == before, "a rejected rewrite must not be used"
    assert why
    # And the rejected wording is handed back, so the log can show what was
    # refused rather than only that something was.
    assert attempted == "It may be reported whenever."


def test_a_provider_error_leaves_the_clause_alone(monkeypatch) -> None:
    class Fake:
        name = "fake"
        model = "fake-1"

        class client:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    raise TimeoutError("took too long")

    before = "AI matters are considered quarterly."
    text, why, _ = polish.one(Fake(), before)
    assert text == before
    assert "TimeoutError" in why


def test_a_refusal_leaves_the_clause_alone() -> None:
    class Reply:
        stop_reason = "refusal"
        content: list = []

    class Fake:
        name = "fake"
        model = "fake-1"

        class client:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def create(**kwargs):
                    return Reply()

    before = "AI matters are considered quarterly."
    text, why, _ = polish.one(Fake(), before)
    assert text == before
    assert "declined" in why


# ------------------------------------------------------------- the question

def test_the_default_is_as_written() -> None:
    """Nobody gets a language tool run over their policy because they did not
    read a question."""
    assert m1.language_of({}) == m1.AS_WRITTEN
    assert m1.language_of({"done.language": {"value": ""}}) == m1.AS_WRITTEN
    assert (m1.language_of({"done.language": {"value": "polished"}})
            == m1.POLISHED)


def test_the_question_is_asked_at_the_end() -> None:
    step = m1.by_number("—")
    numbers = [q.number for q in step.questions]
    assert "—.2c" in numbers
    # Immediately after the Simplified/Formal question, which is the other
    # half of the pair the client asked for at the download.
    assert numbers.index("—.2c") == numbers.index("—.2b") + 1


def test_the_question_carries_no_banned_jargon() -> None:
    """"Never write model. Write tool." His own word for this was "LLM",
    which is on the same list."""
    question = m1.by_key("done.language")
    copy = " ".join([question.prompt, question.help]
                    + [o.label + " " + o.note for o in question.options])
    for word in m1.BANNED:
        assert word not in copy.lower(), word


def test_the_outcome_reports_honestly() -> None:
    outcome = polish.Outcome(asked=40, changed=31, refused=3,
                             skipped_their_words=6, provider="x:y")
    said = outcome.summary()
    assert "31 of 40" in said
    assert "3 rewrites were rejected" in said
    assert "6 clauses in your own words were left untouched" in said


# ---------------------------------------------------- spelling, and the warning

def test_a_misspelling_in_their_own_words_is_corrected() -> None:
    """His report: "If they use the Polished version, it needs to catch
    things like spelling errors (I inentionally included a spelling error
    that translated over even after the polished version was selected)."

    It did survive, and the cause was the protection rather than the tool. A
    clause carrying text somebody typed is never sent anywhere, so the
    writing tool never saw the typo — twenty-one clauses were skipped on that
    rule in the run that reproduced this. Instructing the tool harder would
    have changed nothing; the correction has to be made here.
    """
    answers = {"who.tiebreak": {"value": "teh District Manager"}}
    built = prose.sections(answers)
    before = [c.text for s in built for c in s.clauses]
    assert any("teh District Manager" in t for t in before), "not reproduced"

    fixed, words = polish._fix_spelling(built)
    after = [c.text for s in built for c in s.clauses]
    assert fixed == 1
    assert words == ["teh"]
    assert any("the District Manager" in t for t in after)
    assert not any("teh " in t for t in after)


def test_spelling_is_corrected_without_a_writing_tool(monkeypatch) -> None:
    """It needs no provider, no network and no money, so a deployment with
    no tool configured still gets this much of what Polished promises."""
    monkeypatch.setattr(polish, "available",
                        lambda: (False, "No writing tool here."))
    built = prose.sections({"who.tiebreak": {"value": "teh Manager"}})
    outcome = polish.sections(built, {})
    assert outcome.spelled == 1
    assert outcome.ran, "a pass that corrected something did run"
    assert "No writing tool here." in outcome.note
    assert all("teh " not in c.text for s in built for c in s.clauses)


def test_the_document_names_the_words_it_corrected() -> None:
    outcome = polish.Outcome(asked=10, changed=8, spelled=2,
                             spelled_words=["teh", "recieve"])
    said = outcome.summary()
    assert "2 misspellings were corrected" in said
    assert "teh" in said and "recieve" in said


def test_correcting_a_spelling_cannot_change_a_word_into_another() -> None:
    """The guarantee that makes it safe to touch their sentences at all:
    every string replaced is a non-word, so there is no judgment in it."""
    from app import typos
    for wrong in typos.CORRECTIONS:
        assert wrong not in set(typos.CORRECTIONS.values()), wrong


def test_choosing_polished_warns_before_they_download() -> None:
    """"We need to flash a disclaimer that the polished version uses an LLM
    which may adjust or alter their statements (trying to address the
    non-deterministic nature) and that additional scrutiny should be
    provided when reviewing the output."
    """
    question = m1.by_key("done.language")
    fired = [rule for rule in question.consequences
             if (rule.get("if") or {}).get("is") == m1.POLISHED]
    assert fired, "nothing is said when Polished is chosen"
    said = fired[0]["say"].lower()
    # The two things he asked it to say.
    assert "not produce the same wording twice" in said
    assert "carefully" in said
    # And it must say them without the words he used. "Never write model.
    # Write tool."
    for word in m1.BANNED:
        assert word not in said, word


def test_the_warning_is_silent_for_as_written() -> None:
    question = m1.by_key("done.language")
    for rule in question.consequences:
        assert (rule.get("if") or {}).get("is") != m1.AS_WRITTEN
