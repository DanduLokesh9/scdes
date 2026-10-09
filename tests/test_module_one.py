"""Module One — the questions, and the rules the copy is held to.

The spec ends with a page of instructions for whoever builds it. Most of them
are testable, and the ones that are get tested here rather than being read once
and forgotten:

  * never "model", "algorithm", "LLM", "inference", "training data",
    "deployment" in anything a user reads;
  * one idea per question, under twenty words for the prompt itself;
  * "we don't know" always available, always producing a documented gap with an
    owner — never a blank;
  * never disable a recommended-against answer;
  * do not reference other agencies, users or frameworks.

That last one is why this module exists at all. Its predecessor quoted SCDES's
own sentences above every question, which was the rule the client had drawn
hardest against, arriving by a route nobody was watching.
"""

from __future__ import annotations

import re

import pytest

from app import module_one as m1

# Everything a user reads: prompts, help, framing, options and their notes.
def _copy() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for step in m1.STEPS:
        out.append((f"step {step.number} title", step.title))
        out.append((f"step {step.number} strapline", step.strapline))
        for i, line in enumerate(step.opening):
            out.append((f"step {step.number} opening[{i}]", line))
        for q in step.questions:
            out.append((f"{q.number} prompt", q.prompt))
            out.append((f"{q.number} help", q.help))
            out.append((f"{q.number} above", q.above))
            out.append((f"{q.number} placeholder", q.placeholder))
            for o in q.options + q.rows + q.row_options:
                out.append((f"{q.number} option {o.value}", o.label))
                out.append((f"{q.number} note {o.value}", o.note))
                out.append((f"{q.number} then {o.value}", o.then_text))
    return [(where, text) for where, text in out if text]


# --------------------------------------------------------- the copy rules

def test_no_jargon_reaches_the_user() -> None:
    """"Never write model. Write tool." The subject is assets and
    accountability, not machine learning."""
    offences = []
    for where, text in _copy():
        low = text.lower()
        for word in m1.BANNED:
            # Word-boundary, so "modelling" is caught but "models" inside a
            # longer legitimate word is not silently missed either.
            if re.search(rf"\b{re.escape(word)}", low):
                offences.append(f"{where}: “{word}” in “{text[:60]}”")
    assert not offences, "\n".join(offences[:8])


def test_the_question_itself_never_says_deployment() -> None:
    """"Never 'deployment' in a question the user reads."

    Scoped exactly as he scoped it. His own reviewed copy uses the word in the
    statement of floor 5 and in two response sets, where "before changes are
    deployed" is the term a contract clause actually uses — and his ruling was
    "stick to what I wrote". So the guard holds over the question and the
    nuance under it, which is what his rule covers.
    """
    offences = []
    for q in m1.all_questions():
        for label, text in (("prompt", q.prompt), ("help", q.help),
                            ("above", q.above)):
            for word in m1.BANNED_IN_QUESTIONS:
                if re.search(rf"\b{re.escape(word)}", text.lower()):
                    offences.append(f"{q.number} {label}: “{word}”")
    assert not offences, "\n".join(offences[:8])


def test_prompts_are_short() -> None:
    """"Ideally, under twenty words for the question itself."

    *Ideally* — and it is the client's own guideline, from the same document
    whose question 1.5 runs to twenty-one. He then said: "Stick to what I wrote
    to the best of your ability. I reviewed every question, response set, and
    recommendation individually."

    So his reviewed copy outranks his own rule of thumb, and this became a trap
    rather than a guard: four prompts had already been quietly shortened to
    satisfy it, which is the opposite of what he asked for. The limit is his
    longest — 5.4 at twenty-five, where the length is the point, since the
    question has to name the case it is asking about ("high on any single
    factor... even if everything else is low"). Loose enough for his wording,
    tight enough that a genuinely rambling new question still fails.
    """
    long = [(q.number, len(q.prompt.split()), q.prompt)
            for q in m1.all_questions() if len(q.prompt.split()) > 25]
    assert not long, long


VERBATIM = {
    "1.1": "What kind of organization are you?",
    "1.2": "About how many people work for your organization?",
    "1.3": "Who has the authority to adopt a policy like this one?",
    "1.4": "For each of these, how is it handled in your organization today?",
    "1.5": "Do you run any programs that a state or federal agency delegated "
           "to you, or that they pay for?",
    "1.6": "Are you subject to open records and open meetings laws?",
    # His new 1.7 (BUG-41D9BD0A); the old 1.7 moved to 1.8 at his instruction.
    "1.7": "Does your IT program coordinate with a centralized IT authority?",
    "1.8": "Is there anything unusual about your organization we should know "
           "before we start?",
    "2.1": "Has anyone in your organization used AI tools for work?",
    "2.3": "Do you have any written rule today about staff using AI?",
    "2.4": "Has anyone outside your organization asked you about AI?",
    "2.5": "Is there an AI project someone wants to start right now?",
    "3.1": "Which of these should your rules cover?",
    "3.2": "And which of these should not count?",
    "3.3": "When it isn't clear whether something counts, who decides?",
    "3.4": "Should that call be reviewed by anyone afterward?",
    "4.1": "Which of these shapes fits your organization?",
    "4.3": "Who has the final say when there's disagreement?",
    "4.4": "Before an AI tool is approved for use, who has to be asked?",
    "4.5": "How often does this person or group look at AI matters?",
    "4.6": "What can move forward without them?",
    "4.7": "Where do these decisions get written down, and who keeps them?",
    "4.8": "Who signs or adopts this framework to make it official?",
    "4.9": "Who can change this framework later, and how?",
    "4.10": "How often should the framework itself come back for review?",
    "5.1": "How much does each of these matter in your work?",
    "5.2": "How many levels of scrutiny do you want?",
    "5.3": "For each level, what has to happen?",
    "5.4": "If a tool rates high on any single factor, should it automatically "
           "get the highest level of scrutiny — even if everything else is low?",
    "5.5": "When should the risk level be looked at again?",
}


def test_the_prompts_are_his_word_for_word() -> None:
    """"Stick to what I wrote to the best of your ability."

    Four had drifted — 1.4, 1.5, 1.7 and 4.4 — every one of them shortened to
    get under a word limit that was his own soft guideline. This pins them, so
    the next tidy-up has to be a deliberate decision rather than a side effect.

    4.2 is absent on purpose: he later ruled that the framework names roles and
    the workflow system names people, which changed that prompt by instruction.
    """
    drifted = []
    for q in m1.all_questions():
        expected = VERBATIM.get(q.number)
        if expected and " ".join(q.prompt.split()) != expected:
            drifted.append(f"{q.number}: “{q.prompt}”")
    assert not drifted, drifted


def test_his_own_not_sure_wording_is_kept() -> None:
    """He wrote a "Not sure" into eleven response sets and reviewed each one.
    The first version replaced all of them with a generic tick-box."""
    his = {"org.adopter": "Not sure", "org.delegated": "Not sure",
           "org.open_records": "Not sure", "have.used": "We honestly do not know",
           "have.software": "Not sure", "have.policy": "Not sure",
           "have.project": "Not sure"}
    for key, label in his.items():
        q = m1.by_key(key)
        found = [o.label for o in m1.options_for(q, {})
                 if o.value == m1.UNKNOWN]
        assert found == [label], f"{q.number}: {found} != [{label!r}]"


def test_where_he_wrote_none_a_generic_one_is_offered() -> None:
    """The build note is firm that it is always available."""
    q = m1.by_key("who.shape")
    labels = [o.label for o in m1.options_for(q, {}) if o.value == m1.UNKNOWN]
    assert labels == [m1.GENERIC_UNKNOWN]


def test_the_unknown_is_never_offered_twice() -> None:
    for q in m1.all_questions():
        offered = [o for o in m1.options_for(q, {}) if o.value == m1.UNKNOWN]
        assert len(offered) <= 1, f"{q.number} offers {len(offered)}"


def test_prompts_ask_one_thing() -> None:
    """"Who approves it and how often do they review?" is two questions wearing
    a coat. A prompt with two question marks is the shape that goes wrong.

    Quoted material does not count. His 9.7 asks what should trigger a
    "should we keep this?" review — one question, containing the name of the
    thing it triggers. Counting the marks inside the quotation flagged his own
    reviewed copy, which is the trap this file has fallen into before.
    """
    quoted = re.compile("[“\"'‘][^”\"'’]*[”\"'’]")
    doubled = [q.number for q in m1.all_questions()
               if quoted.sub("", q.prompt).count("?") > 1]
    assert not doubled, doubled


def test_the_framework_asks_for_roles_not_people() -> None:
    """The client's ruling, when asked whether 4.2 should collect names:

        "Workflow process will be the operational component which covers the
         names. Framework sets rules meant to outlast individual people."

    So no question here asks who somebody is. It applies to steps 05–10 as much
    as to 04, which is why it is a test rather than a note — an optional name
    field is an invitation, and the document would go stale the first time
    anybody left.
    """
    offences = []
    for q in m1.all_questions():
        blob = " ".join([q.prompt, q.help, q.above, q.placeholder]).lower()
        # "name" is fine in "name a role", "name the department", "role title";
        # a person's name is not. Note that this also catches copy telling the
        # user *not* to give a name — 3.3 said "use the title rather than the
        # person's name", which is the right instruction phrased backwards. Say
        # what the field is for, not what it is not for.
        for phrase in ("their name", "person's name", "name optional",
                       "full name", "name and title", "who is that person"):
            if phrase in blob:
                offences.append(f"{q.number}: “{phrase}”")
    assert not offences, offences


def test_the_seats_question_collects_one_field() -> None:
    """A role title, and nothing beside it."""
    q = m1.by_key("who.seats")
    assert q.kind == "rows"
    assert "role" in q.prompt.lower() or "role" in q.above.lower()
    assert "outlast" in q.above.lower() or "move on" in q.above.lower()
    # Says where the names do belong, rather than leaving it a mystery.
    assert "workflow" in q.help.lower()


def test_an_adoption_is_the_one_place_a_person_is_named() -> None:
    """Not an exception to the rule so much as a different kind of fact. A rule
    outlasts people; a signature is the moment one person took responsibility.
    Recorded by app/versions.py, not asked for here."""
    from app import versions
    assert "adopted_by" in versions.Version.__dataclass_fields__


def test_nothing_references_another_organisation() -> None:
    """The rule the predecessor broke. No agency, no other framework, no
    corpus — this module has no field that could carry one."""
    for where, text in _copy():
        for name in ("SCDES", "South Carolina", "Environmental Services",
                     "Appendix", "Operations Manual"):
            assert name not in text, f"{where} mentions {name}"
    assert not hasattr(m1.Question, "source_phrase")


def test_no_question_is_a_dead_end() -> None:
    """"Every question earns its place. If an answer doesn't change a line in
    the output document or a later branch, cut it." """
    branch_keys = set()
    for q in m1.all_questions():
        conditions = [q.shows_when] + [o.shows_when for o in q.options] \
            + [r.get("if") for r in q.recommend_when] \
            + [r.get("if") for o in q.rows for r in o.preset_when] \
            + [(q.advice or {}).get("shows_when")]
        for cond in conditions:
            if cond and cond.get("key"):
                branch_keys.add(cond["key"])
        if q.rows_from:
            # A grid drawn from the levels of scrutiny is driven by 5.2, which
            # names no key of its own — the tier set *is* that answer.
            branch_keys.add(q.rows_from.get("key")
                            or ("risk.levels" if q.rows_from.get("tiers")
                                else ""))

    idle = [q.number for q in m1.all_questions()
            if not q.writes and q.key not in branch_keys]
    assert not idle, f"these change nothing: {idle}"


# ------------------------------------------------- we don't know, never blank

def test_we_dont_know_is_available_almost_everywhere() -> None:
    without = [q.number for q in m1.all_questions() if not q.unknown_ok]
    # Three, and each one for a reason he wrote down:
    #   1.8  the optional free-text catch-all — an empty box is already an
    #        answer there, so a separate "don't know" would be noise (it was
    #        1.7 until his central-IT question took that number);
    #   6.3b "required, no opt-out" — how a member of the public reaches a
    #        person instead of the AI. "Case by case" is acceptable; silence
    #        is not, because floor 3 is a promise made to the public;
    #   6.9  the optional additions — "they're good practice, not
    #        requirements", so adding none is a complete answer;
    #   —.1  what the document is called. A framework titled "we don't know"
    #        is not a gap with an owner, it is a filename.
    assert without == ["1.8", "6.3b", "6.9", "—.1"], without


def test_an_unknown_answer_becomes_a_gap_with_an_owner() -> None:
    answers = {"org.kind": "county", "org.size": m1.UNKNOWN}
    found = m1.gaps(answers)
    assert [g["number"] for g in found] == ["1.2"]
    assert found[0]["needs_owner"] is True
    assert found[0]["question"]


def test_a_gap_with_an_owner_stops_needing_one() -> None:
    answers = {"org.size": {"value": m1.UNKNOWN, "owner": "Finance Director"}}
    found = m1.gaps(answers)
    assert found[0]["owner"] == "Finance Director"
    assert found[0]["needs_owner"] is False


def test_a_gap_on_a_hidden_question_is_not_reported() -> None:
    """A question nobody was asked cannot be a gap in their framework."""
    answers = {"org.functions": None, "who.missing": m1.UNKNOWN}
    assert m1.gaps(answers) == []


# ----------------------------------------------------------- the branching

def test_the_offices_you_lack_are_not_offered_later() -> None:
    """1.4 is the most important question in the module. Nothing makes a tool
    feel written for somebody else faster than asking a town clerk to route
    something to their General Counsel."""
    q = m1.by_key("who.consulted")
    small = {"org.functions": {"legal": "none", "it": "part",
                               "security": "none", "purchasing": "part",
                               "records": "none", "finance": "part",
                               "hr": "none", "comms": "none"}}
    offered = [o.value for o in m1.options_for(q, small)]
    assert "legal" not in offered
    assert "security" not in offered
    assert "it" in offered
    assert "program" in offered, "always offered — it is not an office"


def test_a_big_agency_is_offered_everything() -> None:
    q = m1.by_key("who.consulted")
    big = {"org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS}}
    offered = [o.value for o in m1.options_for(q, big)
               if o.value != m1.UNKNOWN]
    assert len(offered) == len(q.options)


def test_the_missing_offices_question_lists_exactly_those() -> None:
    q = m1.by_key("who.missing")
    answers = {"org.functions": {"legal": "none", "it": "part",
                                 "security": "none"}}
    rows = [r.value for r in m1.rows_for(q, answers)]
    assert rows == ["legal", "security"]


def test_the_shape_recommendation_follows_size() -> None:
    """Leans, never insists."""
    q = m1.by_key("who.shape")
    assert m1.recommended_for(q, {"org.size": "u25"}) == "one"
    assert m1.recommended_for(q, {"org.size": "100-500"}) == "group"
    assert m1.recommended_for(q, {"org.size": "2000+"}) == "council"


def test_a_delegated_programme_raises_the_recommendation() -> None:
    q = m1.by_key("who.shape")
    assert m1.recommended_for(
        q, {"org.size": "u25", "org.delegated": "yes"}) == "council"


def test_every_shape_stays_selectable() -> None:
    """"Never disable a recommended-against answer. The moment the module
    refuses something, it becomes someone else's framework." """
    q = m1.by_key("who.shape")
    for size in ("u25", "25-100", "100-500", "500-2000", "2000+"):
        offered = [o.value for o in m1.options_for(q, {"org.size": size})
                   if o.value != m1.UNKNOWN]
        assert offered == ["one", "group", "council", "existing"], size


def test_the_group_you_already_have_is_a_first_class_option() -> None:
    """"Option D deserves equal visual weight with the others. For most
    organizations it is the right answer and it is the one nobody thinks of." """
    q = m1.by_key("who.shape")
    existing = next(o for o in q.options if o.value == "existing")
    assert existing.note
    assert len(existing.note) > 80, "described as fully as the other three"


def test_who_signs_is_prefilled_from_who_may_adopt() -> None:
    q = m1.by_key("who.signs")
    assert m1.recommended_for(q, {"org.adopter": "board"}) == "board"
    assert m1.recommended_for(q, {"org.adopter": "cabinet"}) == "cabinet"


# ------------------------------------------- 05, how much scrutiny and when

def test_the_delegated_factor_only_appears_where_there_is_one() -> None:
    """"The delegated-program factor appears only if 1.5 is yes." """
    q = m1.by_key("risk.factors")
    yes = [r.value for r in m1.rows_for(q, {"org.delegated": "yes"})]
    no = [r.value for r in m1.rows_for(q, {"org.delegated": "no"})]
    assert "delegated" in yes
    assert "delegated" not in no
    assert len(yes) == len(no) + 1, "nothing else moved"


def test_safety_arrives_pre_weighted_for_the_bodies_that_run_the_pipes() -> None:
    """"For a water district this is the factor that matters most, and
    defaulting it low would be a serious miss." """
    q = m1.by_key("risk.factors")
    district = {r.value: r.preset for r in m1.rows_for(q, {"org.kind": "district"})}
    assert district["safety"] == "major"
    # And nowhere else, because a pre-set answer they did not give is a claim
    # made on their behalf.
    school = {r.value: r.preset for r in m1.rows_for(q, {"org.kind": "school"})}
    assert school["safety"] == ""
    assert set(district.values()) - {"major", ""} == set()


def test_a_small_organisation_is_steered_to_two_levels() -> None:
    """"Default to two levels under 25 employees. More tiers than an
    organization can staff is a common failure." """
    q = m1.by_key("risk.levels")
    assert m1.recommended_for(q, {"org.size": "u25"}) == "two"
    assert m1.recommended_for(q, {"org.size": "500-2000"}) == "three"
    assert m1.recommended_for(q, {}) == "three"


def test_all_three_level_counts_stay_selectable() -> None:
    q = m1.by_key("risk.levels")
    offered = [o.value for o in m1.options_for(q, {"org.size": "u25"})
               if o.value != m1.UNKNOWN]
    assert offered == ["two", "three", "four"]


def test_the_tier_grid_follows_how_many_levels_they_chose() -> None:
    q = m1.by_key("risk.tiers")
    assert [r.value for r in m1.rows_for(q, {"risk.levels": "two"})] \
        == ["routine", "elevated"]
    assert [r.value for r in m1.rows_for(q, {"risk.levels": "three"})] \
        == ["low", "moderate", "high"]
    assert len(m1.rows_for(q, {"risk.levels": "four"})) == 4
    # Before 5.2 is answered it still has to render something.
    assert m1.rows_for(q, {})


def test_every_level_arrives_pre_filled_in_their_own_structure() -> None:
    """"Populate sensible defaults for each tier based on the shape chosen in
    4.1, so the user is editing rather than composing." """
    q = m1.by_key("risk.tiers")
    for shape, phrase in (("one", "the accountable person"),
                          ("council", "the council")):
        answers = {"risk.levels": "three", "who.shape": shape}
        shown = q.as_dict(answers)
        tiers = [r["value"] for r in shown["rows"]]
        for field_ in shown["tier_fields"]:
            missing = [t for t in tiers if not field_["defaults"].get(t)]
            assert not missing, f"{field_['key']} has no default for {missing}"
        reviews = next(f for f in shown["tier_fields"] if f["key"] == "reviews")
        assert phrase in reviews["defaults"]["high"], shape


def test_the_worst_factor_rule_explains_itself() -> None:
    """"Explain the reason, briefly." A rule the user does not understand is
    one they will overrule the first time it is inconvenient."""
    q = m1.by_key("risk.worst")
    assert m1.recommended_for(q, {}) == "yes"
    assert "averaging" in q.help.lower()


def test_the_re_look_triggers_start_ticked() -> None:
    """"Multi · defaults checked." """
    q = m1.by_key("risk.revisit")
    assert all(o.recommended for o in q.options)


def test_the_word_matrix_is_never_shown_to_anyone() -> None:
    """"Define risk in one sentence and never use the word 'matrix' in front of
    the user." It is a control type in the source, not a word anybody reads."""
    assert "matrix" in m1.BANNED
    for where, text in _copy():
        assert "matrix" not in text.lower(), where


# ------------------------------------------------------- 06, the floor

def test_the_floor_says_out_loud_that_it_is_directive() -> None:
    """"Everything so far has been your choice. These eight are different...
    you are deciding how strict your version is, not whether you have one."
    The one place the module is directive, and it should say so rather than
    sneaking it in."""
    step = m1.by_number("06")
    opening = " ".join(step.opening)
    assert "not whether you have one" in opening
    required = [g for g in step.groups if "required" in g["badge"].lower()]
    assert len(required) == 8, "eight floors, all of them required"


def test_every_floor_states_the_rule_and_why_it_exists() -> None:
    """"Each is presented the same way: the rule in plain words, one line on
    why it exists, then the choices that genuinely are theirs." """
    step = m1.by_number("06")
    for group in step.groups:
        assert group["title"], group["key"]
        assert len(group["why"]) > 60, f"{group['key']} has no reason given"
        owned = [q for q in step.questions if q.group == group["key"]]
        assert owned, f"{group['key']} asks nothing"


def test_accessibility_is_carried_as_law_not_as_preference() -> None:
    """"Required by law... the technical standard is WCAG 2.1 Level AA under
    the ADA Title II web rule." The client's standing position is that this is
    an acceptance criterion for everything, so the framework says which
    standard rather than gesturing at one."""
    floor = next(g for g in m1.by_number("06").groups if g["key"] == "f4")
    assert "law" in floor["badge"].lower()
    assert "WCAG 2.1 Level AA" in floor["why"]
    assert "ADA Title II" in floor["why"]


def test_the_only_question_with_no_opt_out_is_reaching_a_person() -> None:
    """"Required, no opt-out." Floor 3 is a promise made to the public, and a
    promise with "we don't know" against it is not one."""
    assert m1.by_key("floor.reach_human").unknown_ok is False


def test_floor_seven_offers_only_the_contacts_they_could_name() -> None:
    """"Offers only roles that exist per 1.4, and explicitly permits one person
    to hold several." """
    q = m1.by_key("floor.named")
    small = {"org.functions": {"it": "none", "legal": "none",
                               "finance": "part"}}
    offered = [o.value for o in m1.options_for(q, small)]
    assert "owner" in offered, "the using program is always there"
    assert "technical" not in offered and "legal" not in offered
    assert "budget" in offered
    assert "several" in q.help, "the concentration is acknowledged, not hidden"


def test_nothing_is_withheld_before_they_have_said_what_they_have() -> None:
    """A contact offered on the strength of an unanswered question is a guess.
    Withholding one is worse — it silently narrows their framework."""
    q = m1.by_key("floor.named")
    offered = [o.value for o in m1.options_for(q, {})]
    assert {"owner", "technical", "legal", "budget"} <= set(offered)


def test_a_two_part_question_keeps_both_halves_together() -> None:
    """"Who writes it, and who approves it?" is one question in his document.
    Two keys would let the halves drift apart in the store."""
    for key in ("floor.disclose_who", "floor.plain_who"):
        q = m1.by_key(key)
        assert q.also and q.also["key"] == "approver", key
    q = m1.by_key("floor.disclose_who")
    said = m1.describe(q, {q.key: {"value": "Communications Manager",
                                   "approver": "The Town Attorney"}})
    assert said["state"] == "answered"
    assert "Communications Manager" in said["lines"][0]
    assert "The Town Attorney" in said["lines"][1]


def test_the_untested_fallback_is_nudged_and_not_blocked() -> None:
    """"If they answer 'never', show one line... and let the answer stand." """
    q = m1.by_key("floor.fallback_tested")
    assert "never" in [o.value for o in m1.options_for(q, {})]


def test_the_optional_additions_are_marked_optional() -> None:
    """"They're good practice, not requirements." Adding none is a complete
    answer, which is why this one has no "we don't know"."""
    q = m1.by_key("floor.optional")
    assert q.optional is True
    assert q.unknown_ok is False
    assert "not requirements" in q.above


def test_the_floor_shows_when_each_obligation_comes_back() -> None:
    """"The most common misunderstanding about governance is that it happens at
    purchase." One row per floor, or the point is not made."""
    closing = m1.by_number("06").closing
    assert len(closing["table"]["rows"]) == 8
    assert all(len(r) == 3 for r in closing["table"]["rows"])


# ------------------------------------- 07, where the exposure lives

def test_every_kind_of_protected_information_is_offered_to_everyone() -> None:
    """His note says student records "surface" for school districts and
    criminal justice information for counties and cities. Read as *hide the
    rest* it would collide with his firmest rule — "the moment the module
    refuses something, it becomes someone else's framework" — and a county
    that runs a health clinic would lose the medical category.

    So every category is offered to everybody, and the ones that match arrive
    already ticked. The adaptation is in what is pre-chosen, not in what
    exists.
    """
    q = m1.by_key("data.never")
    for kind in ("state", "county", "city", "district", "school", "regional",
                 "tribal", ""):
        offered = [o.value for o in m1.options_for(q, {"org.kind": kind})
                   if o.value != m1.UNKNOWN]
        assert len(offered) == 11, kind


def test_the_categories_that_match_arrive_already_ticked() -> None:
    q = m1.by_key("data.never")

    def ticked(kind: str) -> set[str]:
        return {o.value for o in m1.options_for(q, {"org.kind": kind})
                if o.recommended}

    assert "student" in ticked("school")
    assert "student" not in ticked("district")
    assert "criminal" in ticked("county")
    assert "infrastructure" in ticked("district")
    assert "regulated" in ticked("state")
    # And one that is true of everybody, whoever they are.
    assert "personal" in ticked("school") & ticked("state") & ticked("")


def test_the_readiness_advice_waits_until_they_admit_the_gap() -> None:
    """"The highest-value advisory moment in the entire module." Shown from
    the start it is a lecture; shown at the moment they say "partly" it is the
    advice."""
    q = m1.by_key("data.systems")
    assert "advice" not in q.as_dict({}), "not before they have answered"
    assert "advice" not in q.as_dict({"data.systems": "documented",
                                      "data.where": "documented"})
    shown = q.as_dict({"data.systems": "partly"})
    assert "advice" in shown
    assert len(shown["advice"]["body"]) == 3
    assert "documented gap with an owner" in shown["advice"]["close"]
    # Either question can trigger it — they are two halves of one worry.
    assert "advice" in q.as_dict({"data.where": "no"})


def test_a_prompt_log_decision_is_forced_before_a_records_request() -> None:
    """"Deciding it here... is far better than deciding it during a records
    request." Including deciding that you have not decided."""
    q = m1.by_key("data.prompts")
    assert "undecided" in [o.value for o in m1.options_for(q, {})]
    assert "records request" in q.help


# ----------------------------------------------- 08, AI as an asset

def test_procurement_attaches_to_the_process_they_already_have() -> None:
    """"The generated framework references the user's actual process by name
    rather than inventing a parallel one." """
    q = m1.by_key("proc.today")
    assert q.also and q.also["key"] == "thresholds"
    assert "your actual process by name" in q.help


def test_who_checks_agreements_changes_shape_with_no_legal_office() -> None:
    """"If 1.4 shows no legal function, offer: 'We'd use outside counsel' /
    'Our purchasing staff check against a standard list' / 'This is a gap we
    need to close'." Asking an organization with no lawyer to name its lawyer
    produces a blank, and a blank is the one thing this module does not
    accept."""
    has = {"org.functions": {"legal": "dedicated"}}
    hasnt = {"org.functions": {"legal": "none"}}
    typed = m1.by_key("proc.checker")
    chosen = m1.by_key("proc.checker_none")

    assert m1.visible(typed, has) and not m1.visible(chosen, has)
    assert m1.visible(chosen, hasnt) and not m1.visible(typed, hasnt)
    assert typed.number == chosen.number == "8.4", "one question, two shapes"
    assert typed.prompt == chosen.prompt
    assert "gap" in [o.value for o in m1.options_for(chosen, hasnt)]


def test_only_one_version_of_a_question_is_ever_asked() -> None:
    """Two questions sharing a number must be mutually exclusive, or the step
    counts one question twice and the document prints it twice."""
    for answers in ({"org.functions": {"legal": "dedicated"}},
                    {"org.functions": {"legal": "none"}},
                    {"org.functions": {"legal": "part"}},
                    {}):
        shown = [q.number for step in m1.STEPS for q in step.questions
                 if m1.visible(q, answers)]
        assert len(shown) == len(set(shown)), sorted(
            n for n in shown if shown.count(n) > 1)


def test_the_vendor_slipping_ai_in_is_flagged_on_screen() -> None:
    """"The most common way AI enters a government today and the easiest to
    miss entirely. Worth a sentence of emphasis in the interface." """
    q = m1.by_key("proc.added_ai")
    assert "easiest to miss" in q.above
    assert m1.recommended_for(q, {}) == "as_new"


def test_what_it_costs_to_leave_is_one_of_the_costs() -> None:
    """"The last item is the one most organizations discover too late." """
    q = m1.by_key("proc.cost_parts")
    values = [o.value for o in m1.options_for(q, {}) if o.value != m1.UNKNOWN]
    assert values[-1] == "exit"
    assert not m1.visible(q, {"proc.full_cost": "no"})
    assert m1.visible(q, {"proc.full_cost": "yes"})


# -------------------------------------------- 09, life after purchase

def test_monitoring_and_retirement_are_one_step() -> None:
    """"The triggers for retiring a tool are mostly monitoring results.
    Splitting them makes retirement feel like an afterthought, which is
    exactly how it gets treated in practice." """
    step = m1.by_number("09")
    writes = {w for q in step.questions for w in q.writes}
    assert {"Performance", "Sunset"} <= writes


def test_how_often_you_check_is_asked_once_per_level() -> None:
    """"Asked once per risk level from 5.2, pre-filled so higher levels
    default to more frequent review." """
    q = m1.by_key("watch.cadence")
    shown = q.as_dict({"risk.levels": "three"})
    assert [r["value"] for r in shown["rows"]] == ["low", "moderate", "high"]
    every = shown["tier_fields"][0]["defaults"]
    assert every["high"] == "quarterly"
    assert every["low"] == "annual"


def test_drift_is_explained_where_it_is_asked_about() -> None:
    """"AI tools drift... a tool that was accurate a year ago may quietly not
    be. Nothing tells you unless you look." Without the line, "whether it's
    still as accurate as it was" reads as a formality."""
    q = m1.by_key("watch.what")
    accuracy = next(o for o in q.options if o.value == "accuracy")
    assert "drift" in accuracy.note.lower()
    assert accuracy.recommended


def test_publishing_is_pressed_once_the_public_is_already_involved() -> None:
    """"Recommended when 5.1 shows meaningful public-facing exposure, or when
    2.4 indicates press, board, or public inquiries have already started." """
    q = m1.by_key("watch.publish")

    def ticked(answers):
        return {o.value for o in m1.options_for(q, answers) if o.recommended}

    assert ticked({}) == {"annual_report"}, "his own default, always"
    assert "tool_list" in ticked({"risk.factors": {"public": "major"}})
    assert "framework" in ticked({"have.asked": ["press"]})
    assert "framework" not in ticked({"have.asked": ["auditor"]})


# ------------------------------------------------ 10, when it goes wrong

def test_the_incident_step_opens_with_why_it_is_separate() -> None:
    """"When a computer system goes down, everyone knows immediately. When an
    AI tool starts producing wrong answers, it can go unnoticed for months." """
    opening = " ".join(m1.by_number("10").opening)
    assert "goes down, everyone knows immediately" in opening
    assert "may still look accurate" in opening


def test_attaching_to_the_process_they_have_is_only_asked_if_they_have_one():
    """"People follow one process. They rarely follow two." """
    q = m1.by_key("bad.attach")
    assert not m1.visible(q, {})
    assert not m1.visible(q, {"bad.existing": "no"})
    assert m1.visible(q, {"bad.existing": "yes"})
    assert m1.recommended_for(q, {}) == "attach"


def test_the_three_severities_arrive_written_for_them() -> None:
    """"Editable defaults · 3 levels." Facing three empty boxes labeled
    minor, serious and severe is how a severity scale ends up copied off the
    internet."""
    shown = m1.by_key("bad.levels").as_dict({})
    assert [r["value"] for r in shown["rows"]] == ["minor", "serious",
                                                   "severe"]
    meanings = shown["tier_fields"][0]["defaults"]
    assert all(len(meanings[level]) > 40 for level in
               ("minor", "serious", "severe"))
    assert "rights, benefits, or safety" in meanings["severe"]


def test_how_fast_is_asked_about_the_same_three_levels() -> None:
    q = m1.by_key("bad.speed")
    assert [r.value for r in m1.rows_for(q, {})] == ["minor", "serious",
                                                     "severe"]


def test_somebody_can_stop_it_without_a_meeting() -> None:
    """"Requiring a quorum to stop a malfunctioning tool is how a small
    problem becomes a large one over a weekend." """
    q = m1.by_key("bad.stopper")
    assert "act alone" in q.help


def test_who_must_be_told_follows_who_they_actually_answer_to() -> None:
    """"Federal partner appears only if 1.5 is yes." """
    q = m1.by_key("bad.tell")
    with_fed = [o.value for o in m1.options_for(q, {"org.delegated": "yes"})]
    without = [o.value for o in m1.options_for(q, {"org.delegated": "no"})]
    assert "federal" in with_fed and "federal" not in without
    # And no attorney to tell if 1.4 said there isn't one.
    nolaw = [o.value for o in m1.options_for(
        q, {"org.functions": {"legal": "none"}})]
    assert "attorney" not in nolaw
    assert "affected" in nolaw, "the people affected, always"


def test_the_delegated_notification_clause_is_promised_in_writing() -> None:
    """"Where a delegated program is affected, the framework adds a clause
    requiring a documented determination of whether the delegating agency
    must be notified — a real obligation that is easy to overlook." """
    assert "delegating agency" in m1.by_key("bad.tell").help


# --------------------------------------- —, review, adopt, publish

def test_the_assembly_step_asks_no_new_policy_question() -> None:
    """"No new decisions here." Four fields, all of them about the document
    rather than about how the organization will govern."""
    step = m1.by_number("—")
    # —.2b and —.2c are about the document, not about how they will govern:
    # whether it reads as plain rules or as a formal instrument, and whether
    # the wording is tidied. Both say exactly the same thing and hold the
    # organization to exactly the same rules.
    assert [q.number for q in step.questions] == ["—.1", "—.2", "—.2b",
                                                  "—.2c", "—.3", "—.4"]
    assert "No new decisions here" in " ".join(step.opening)


def test_who_signs_and_when_it_comes_back_are_already_filled_in() -> None:
    """"Pre-filled from 1.3 and 4.8", and "pre-filled from 4.10". A step whose
    whole job is assembly should not ask them to say the same thing twice."""
    signs = m1.by_key("done.signs")
    assert m1.recommended_for(signs, {"who.signs": "cabinet"}) == "cabinet"
    # 4.8 first, then 1.3 — the later answer is the more considered one.
    assert m1.recommended_for(
        signs, {"org.adopter": "board", "who.signs": "appointed"}) \
        == "appointed"
    assert m1.recommended_for(signs, {"org.adopter": "board"}) == "board"

    review = m1.by_key("done.review")
    assert m1.recommended_for(review, {"who.review": "biennial"}) == "biennial"


def test_the_handoff_is_a_straight_sentence_not_a_pitch() -> None:
    """"A user who just finished ten steps of honest work has earned a
    straight sentence, not a pitch." """
    closing = m1.by_number("—").closing
    said = " ".join(closing["body"])
    assert "Premium Subscription page" in said
    assert "!" not in said


def test_the_read_back_does_not_read_itself_back() -> None:
    sections = [s["number"] for s in m1.review({})]
    assert sections == ["01", "02", "03", "04", "05", "06", "07", "08", "09",
                        "10", "11"]


def test_the_read_back_traces_every_line_to_its_question() -> None:
    """"Every choice traced to the question that produced it, so nothing
    appears that they can't account for." """
    answers = {"org.kind": "district", "who.tiebreak": "The Administrator"}
    rows = {r["number"]: r for s in m1.review(answers) for r in s["rows"]}
    assert rows["1.1"]["state"] == "answered"
    label = next(o.label for o in m1.by_key("org.kind").options
                 if o.value == "district")
    assert rows["1.1"]["lines"] == [label], "the words they clicked"
    assert rows["1.1"]["prompt"] == m1.by_key("org.kind").prompt
    assert rows["1.2"]["state"] == "blank"


def test_their_own_words_are_offered_on_every_deciding_section() -> None:
    """"A free-text box per section." Not on orientation, which decides
    nothing, and not on assembly, which decides nothing new."""
    offering = [s.number for s in m1.STEPS if s.own_words]
    assert offering == ["01", "02", "03", "04", "05", "06", "07", "08", "09",
                        "10", "11"]
    shown = m1.by_number("03").as_dict({"words.03": "Our board asked for it."})
    assert shown["own_words"]["value"] == "Our board asked for it."
    assert shown["own_words"]["key"] == "words.03"


def test_their_own_words_are_not_counted_as_an_answer() -> None:
    """It is never required and never scored. A section is not more finished
    because somebody wrote a paragraph in it."""
    plain = m1.by_number("03").as_dict({})
    written = m1.by_number("03").as_dict({"words.03": "Anything at all."})
    assert plain["answered"] == written["answered"]
    assert m1.own_words_key("03") not in [q.key for q in m1.all_questions()]


# ---------------------------------------------- what disagrees with what

def test_a_contradiction_is_named_and_never_blocked() -> None:
    """His own example — "nothing gets approved without the committee, and
    also free tools don't need approval" — is prevented at the click now, on
    his instruction, so it can no longer be produced.

    What is left for this screen is the clash a single control cannot stop
    because it spans two steps: you re-check risk whenever the vendor changes
    the tool, and also do nothing when a vendor adds AI to something you own.
    """
    found = m1.contradictions({"risk.revisit": ["vendor_change"],
                               "proc.added_ai": "nothing"})
    assert len(found) == 1
    assert "Which wins?" in found[0]["line"]
    assert found[0]["at"] == ["5.5", "8.5"]


def test_what_the_interface_prevents_is_not_also_flagged() -> None:
    """A rule that can never fire looks like coverage and is not. The three
    that became exclusive options were removed rather than left in."""
    gone = {"everything-and-not-everything", "publish-nothing-and-something",
            "tell-no-one-and-someone"}
    assert not gone & {r["key"] for r in m1.CONTRADICTIONS}
    # And the thing each of them used to catch is now impossible to enter.
    assert m1.contradictions({"who.without": ["nothing", "free"]}) == []


def test_a_consistent_framework_is_flagged_for_nothing() -> None:
    """A check that fires on something merely unusual teaches people to skip
    the one screen that has to be read."""
    settled = {
        "who.without": ["free", "short_pilot"],
        "risk.revisit": ["incident", "vendor_change"],
        "proc.added_ai": "as_new",
        "watch.publish": ["annual_report"],
        "bad.tell": ["affected", "board"],
        "bad.lookback": "yes",
        "floor.fallback_scope": "all",
        "floor.fallback_tested": "annual",
        "floor.access_when": ["purchase"],
        "floor.access_docs": "yes",
        "done.where": "both",
    }
    assert m1.contradictions(settled) == []


def test_every_contradiction_points_back_at_real_questions() -> None:
    numbers = {q.number for q in m1.all_questions()} | {"—"}
    for rule in m1.CONTRADICTIONS:
        assert rule["at"], rule["key"]
        for where in rule["at"]:
            assert where in numbers, f"{rule['key']} points at {where}"
        assert rule["line"].endswith("?"), rule["key"]


def test_the_vendor_who_slips_ai_in_is_caught_against_your_own_rule() -> None:
    found = m1.contradictions({"proc.added_ai": "nothing",
                               "risk.revisit": ["vendor_change"]})
    assert [f["key"] for f in found] == ["vendor-adds-ai-but-we-re-look"]


# ------------------------------------------------------ the floor, honestly

def test_the_floor_reports_all_eight_whatever_was_answered() -> None:
    """"A short checklist showing all eight requirements are addressed." """
    assert [f["key"] for f in m1.floor_state({})] == [
        "f1", "f2", "f3", "f4", "f5", "f6", "f7", "f8"]
    assert all(not f["settled"] for f in m1.floor_state({}))


def test_a_weakened_floor_is_shown_and_not_hidden() -> None:
    """"If the user weakened one, it's shown, not hidden." """
    softened = m1.floor_state({"floor.ai_finalises": "some",
                               "floor.access_docs": "no",
                               "floor.fallback_tested": "never",
                               # His correction: "change from public facing to
                               # the higher risk tiered categories (those will
                               # almost always be public-facing)".
                               "floor.plain_scope": "higher_risk"})
    weak = {f["key"]: f["weakened_note"] for f in softened if f["weakened"]}
    assert set(weak) == {"f1", "f4", "f5", "f8"}
    assert all(note for note in weak.values()), "each says how"


def test_the_strictest_answers_weaken_nothing() -> None:
    strict = m1.floor_state({"floor.ai_finalises": "none",
                             "floor.access_docs": "yes",
                             "floor.fallback_tested": "annual",
                             "floor.plain_scope": "all"})
    assert not any(f["weakened"] for f in strict)


# ------------------------------------------------------------ the structure

def test_every_step_is_either_built_or_named() -> None:
    """The steps still to come are listed rather than omitted, so the interface
    can show the whole path. A section that says "not yet" is honest in a way a
    silently missing one is not."""
    built = [s.number for s in m1.STEPS]
    pending = [n for n, _, _ in m1.PENDING]
    assert built + pending == ["00", "01", "02", "03", "04", "05", "06", "07",
                               "08", "09", "10", "11", "—"]
    assert not set(built) & set(pending), "a step cannot be both"


def test_orientation_asks_nothing() -> None:
    step = m1.by_number("00")
    assert step.asks is False
    assert step.questions == []
    assert step.opening, "it is all framing"


def test_the_asset_analogy_opens_the_module() -> None:
    """The premise everything rests on. If it is not in the first screen the
    user arrives believing this is a technical subject they are unqualified to
    have opinions about."""
    opening = " ".join(m1.by_number("00").opening).lower()
    assert "asset" in opening
    assert "truck" in opening or "vehicle" in opening


def test_the_question_counts_match_the_spec() -> None:
    # Seven in the spec, plus 1.4b — "if IT is selected, have a sub drop down
    # of 'is your cybersecurity team a part of the IT team?'", which he asked
    # for after reviewing the build, and his 1.7 on a central IT authority
    # (BUG-41D9BD0A).
    assert len(m1.by_number("01").questions) == 9
    assert len(m1.by_number("02").questions) == 5
    assert len(m1.by_number("03").questions) == 4
    # Ten in the spec, plus 4.4b — the follow-up the spec describes in prose
    # under 4.4 rather than numbering.
    assert len(m1.by_number("04").questions) == 11


def test_every_question_key_is_unique() -> None:
    keys = [q.key for q in m1.all_questions()]
    assert len(keys) == len(set(keys))


def test_the_summary_adapts_to_the_answers() -> None:
    empty = m1.summary({})
    answered = m1.summary({"org.kind": "city", "org.size": "u25"})
    assert answered["totals"]["answered"] == 2
    assert empty["totals"]["answered"] == 0
    # The gate's name, and never a number: the spine forbids rendering a gate
    # as one anywhere. This asserted "Step 1 — Govern".
    assert answered["lifecycle_stage"] == "Govern"
    assert not any(ch.isdigit() for ch in answered["lifecycle_stage"])


def test_a_hidden_question_is_not_counted_as_unanswered() -> None:
    """Progress has to mean something. Counting questions nobody will be asked
    makes it permanently short of complete."""
    total_when_hidden = m1.summary({})["totals"]["questions"]
    shown = m1.summary({"org.functions": {"legal": "none"}})
    assert shown["totals"]["questions"] == total_when_hidden + 1


def test_defaults_are_pre_selected_where_the_spec_says_so() -> None:
    """3.1 and 3.2 arrive checked. "Most users will accept the default, which
    is fine; the ones who change it are the ones who needed to." """
    for key in ("scope.covered", "scope.excluded"):
        q = m1.by_key(key)
        assert all(o.recommended for o in q.options), key




def test_the_copy_is_american(tmp_path, monkeypatch) -> None:
    """"Use American spelling" — BUG-15744B13, after "Program" appeared in a
    seeded answer. The audience is US state and local government; British
    spelling reads as a document written for somebody else, which is the one
    impression this product cannot afford to give.

    Checked over everything a reader sees, including the sentences the export
    assembles, because that is where it crept in.
    """
    import re
    from app import prose

    british = ["organisation", "programme", "recognise", "authorise",
               "prioritise", "centre", "licence", "defence", "behaviour",
               "labour", "catalogue", "analyse", "summarise", "minimise",
               "utilise", "enrolment", "judgement", "offence"]

    said: list[tuple[str, str]] = []
    for key, sentence in prose.SENTENCES.items():
        said.append((f"prose:{key}", sentence))
    for section in prose.SECTIONS:
        said.append(("section", section["title"] + " " + section["purpose"]))
    for q in m1.all_questions():
        for part in (q.prompt, q.help, q.above, q.placeholder):
            said.append((q.number, part))
        for o in q.options + q.rows + q.row_options:
            said.append((q.number, f"{o.label} {o.note} {o.prose}"))
    for step in m1.STEPS:
        said.append((step.number, " ".join(
            [step.title, step.strapline, step.writes] + list(step.opening))))

    offences = [f"{where}: {word}" for where, text in said
                for word in british
                if re.search(rf"\b{word}", str(text), re.I)]
    assert not offences, offences[:6]


# ------------------------------------- a response set they can extend

def test_they_can_add_a_choice_where_he_asked_for_it() -> None:
    """Four tickets, one request:

        ED813720  3.1-3.2  "Add 'Other' and a fillable line."
        9B298881  5.1      "Locked in only options now. Let them add their own."
        29BBB23A  6.2b     "Provide ability to add rows."
        58AC00FF  6.6      "Self-add fields."
    """
    for key in ("scope.covered", "scope.excluded", "risk.factors",
                "floor.list_fields", "floor.data_terms"):
        assert m1.by_key(key).can_add, key


def test_a_choice_they_added_comes_back_as_a_choice() -> None:
    """Stored as the answer itself behind a prefix, so it needs no second list
    that could fall out of step with the first."""
    q = m1.by_key("scope.covered")
    answers = {"scope.covered": ["generative", "custom:Meter reading models"]}
    offered = {o.value: o.label for o in m1.options_for(q, answers)}
    assert offered["custom:Meter reading models"] == "Meter reading models"
    # And it reads back as their words, not as the storage.
    said = m1.describe(q, answers)
    assert "Meter reading models" in said["lines"]
    assert not any("custom:" in line for line in said["lines"])


def test_a_factor_they_added_becomes_a_row_they_can_weight() -> None:
    """5.1 is a grid, so adding one has to produce a row — a choice with
    nothing to weight it against would be an answer they cannot give."""
    q = m1.by_key("risk.factors")
    answers = {"risk.factors": {"public": "some",
                                "custom:Chlorine dosing": "major"}}
    rows = {r.value: r.label for r in m1.rows_for(q, answers)}
    assert rows["custom:Chlorine dosing"] == "Chlorine dosing"
    said = m1.describe(q, answers)
    assert "Chlorine dosing — Major" in said["lines"]


def test_a_closed_response_set_stays_closed() -> None:
    """Most questions are his, reviewed one by one. Opening one he did not ask
    to open is a change to his framework, not a feature."""
    q = m1.by_key("org.kind")
    assert not q.can_add
    offered = [o.value for o in m1.options_for(
        q, {"org.kind": "custom:Something else"})]
    assert "custom:Something else" not in offered


def test_what_they_added_reaches_the_document() -> None:
    """The point of adding it. A choice that does not appear in the framework
    was decoration."""
    from app import prose
    answers = {"scope.covered": ["generative", "custom:Meter reading models"]}
    clauses = [c.text for s in prose.sections(answers) for c in s.clauses]
    assert any("Meter reading models" in c for c in clauses)
    assert not any("custom:" in c for c in clauses)


# --------------------------------------- the tickets he filed on 28 August

def test_executive_leadership_is_offerable() -> None:
    """"4.4, wanted to select Executive Leadership or Administration, but not
    listed. Add 'Administration/Executive Leadership', then Information
    Technology, then Legal Counsel." — his order, and 4.4 only offers offices
    named at 1.4, so it had to be added there too."""
    assert [f.value for f in m1.FUNCTIONS][:3] == ["exec", "it", "legal"]
    q = m1.by_key("who.consulted")
    have = {"org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS}}
    offered = [o.value for o in m1.options_for(q, have)]
    assert offered[:3] == ["exec", "it", "legal"]


def test_cybersecurity_folds_into_it_when_they_say_so() -> None:
    """"If IT is selected, have a sub drop down of 'Is your cybersecurity team
    a part of the IT team?' Yes/No. If yes, then IT covers cybersecurity and
    we do not need individually call out the Cybersecurity team." """
    sub = m1.by_key("org.cyber_in_it")
    assert sub.number == "1.4b"
    assert not m1.visible(sub, {"org.functions": {"it": "none"}})
    assert m1.visible(sub, {"org.functions": {"it": "part"}})

    both = {"org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS}}
    consulted = m1.by_key("who.consulted")
    assert "security" in [o.value for o in m1.options_for(consulted, both)]
    merged = {**both, "org.cyber_in_it": "yes"}
    assert "security" not in [o.value
                              for o in m1.options_for(consulted, merged)]


def test_a_missing_cyber_team_is_not_a_gap_if_it_covers_it() -> None:
    """The other half of the same instruction: 1.4 recorded no separate team,
    but there is no hole to ask about if IT holds it."""
    q = m1.by_key("who.missing")
    answers = {"org.functions": {"it": "dedicated", "security": "none"}}
    assert "security" in [r.value for r in m1.rows_for(q, answers)]
    assert "security" not in [r.value for r in m1.rows_for(
        q, {**answers, "org.cyber_in_it": "yes"})]


def test_a_grid_with_nothing_to_ask_is_hidden() -> None:
    """"4.4b — if it is not relevant based on previous answers, hide the
    component. It's sitting there with nothing for me to do and is
    confusing." """
    q = m1.by_key("who.missing")
    everything = {"org.functions": {f.value: "dedicated"
                                    for f in m1.FUNCTIONS}}
    assert not m1.visible(q, everything), "nothing is missing"
    assert m1.visible(q, {"org.functions": {"hr": "none"}})


def test_what_happens_to_an_unlisted_tool_takes_several_answers() -> None:
    """"6.2d — allow for multi-select." More than one is usually true: it is a
    violation *and* IT blocks it *and* it must be registered."""
    q = m1.by_key("floor.unlisted")
    assert q.kind == "multi"
    said = m1.describe(q, {"floor.unlisted": ["violation", "blocked"]})
    assert len(said["lines"]) == 2


def test_an_exclusive_answer_rules_out_the_others() -> None:
    """"Good catch. If they click nothing, then gray out and make all others
    un-clickable." Not a refusal — one answer that means the absence of the
    rest, said at the moment of clicking rather than argued about later."""
    for key, value in (("who.without", "nothing"),
                       ("watch.publish", "nothing"),
                       ("bad.tell", "none")):
        q = m1.by_key(key)
        only = [o.value for o in m1.options_for(q, {}) if o.exclusive]
        assert only == [value], key


def test_a_dependent_question_waits_rather_than_guessing() -> None:
    """"If someone says in 5.2 'We don't know', then 5.3 cannot be filled out.
    Gray out boxes, do not allow for editing (because 5.3 requires 5.2)." """
    q = m1.by_key("risk.tiers")
    assert q.as_dict({})["waiting_on"], "nothing chosen yet"
    assert q.as_dict({"risk.levels": m1.UNKNOWN})["waiting_on"]
    ready = q.as_dict({"risk.levels": "two"})
    assert ready["waiting_on"] is None
    # And it still says which question to answer first.
    assert "5.2" in q.as_dict({})["waiting_on"]["say"]



# ------------------------------------- the tickets he filed on 2 September

def test_a_typed_dont_know_is_a_gap_like_a_clicked_one() -> None:
    """His question, BUG-4C598D50: "If I type Unknown right now in 9.4, does
    the system flag that in the output or write to the output unknown?"

    The answer was inconsistent and bad. Lower-case "unknown" was caught
    because it happens to equal the sentinel; "Unknown", "TBD", "don't know"
    and "n/a" went into the framework as if they were roles — "That review is
    carried out by TBD" as adopted policy.
    """
    q = m1.by_key("watch.who")
    for typed in ("unknown", "Unknown", "UNKNOWN", "TBD", "n/a",
                  "don't know", "to be decided", "?"):
        said = m1.describe(q, {q.key: typed})
        assert said["state"] == "gap", typed
        assert [g["number"] for g in m1.gaps({q.key: typed})] == ["9.4"], typed


def test_a_real_role_that_looks_like_a_shrug_survives() -> None:
    """Matched against the whole answer only. Somebody's actual job title must
    not be swallowed because it starts with the same letters."""
    q = m1.by_key("watch.who")
    for real in ("TBD Coordination Office", "The NA Regional Liaison",
                 "Unknown Waters Project Lead"):
        assert m1.describe(q, {q.key: real})["state"] == "answered", real


def test_an_untested_fallback_gets_his_line() -> None:
    """"Nudge, don't block — if they answer 'never', show one line, 'An
    untested fallback is a document, not a plan', and let the answer stand."

    It showed nothing, because the interface knew about 4.1's consequence and
    no others. BUG-D48EE440.
    """
    q = m1.by_key("floor.fallback_tested")
    lines = q.as_dict({})["consequences"]
    assert lines, "6.5b has no consequence at all"
    said = lines[0]["say"]
    assert "not a plan" in said
    assert "Your answer stands" in said
    assert lines[0]["if"] == {"key": "floor.fallback_tested", "is": "never"}


def test_who_approves_data_use_is_a_choice_not_a_blank() -> None:
    """"7.4 — you have the pre-filled structure listed under the question, but
    it should be a 2 select option... This prevents the system from
    registering the blank as missing." BUG-4E0C7B79."""
    q = m1.by_key("data.approver")
    assert q.kind == "single"
    offered = [o.value for o in m1.options_for(q, {}) if o.value != m1.UNKNOWN]
    assert offered == ["decider", "other"]
    # The first option names the structure they chose, filled in — and
    # capitalised, because it is the label on a control and not a phrase in
    # the middle of a clause. BUG-25753D8D: "7.4 - Capitalize '[T]he
    # accountable person'". The prose keeps the lower-case form, which is
    # what `test_..._reads_back_what_they_typed` below is about.
    shown = m1.options_for(q, {"who.shape": "group"})[0]
    assert shown.label == "The standing group"
    assert "{" not in shown.label, "the placeholder reached the screen"
    assert shown.prose == "the standing group", (
        "the clause needs the lower-case form — it sits mid-sentence")


def test_a_choice_that_opens_a_blank_reads_back_what_they_typed() -> None:
    """"Approved by someone else — the Records Officer" is the audit trail's
    job. The framework says "approved by the Records Officer", which is the
    rule somebody has to follow."""
    q = m1.by_key("data.approver")
    said = m1.phrases(q, {q.key: {"value": "other",
                                  "detail": "The Records Officer"}})
    assert said == ["The Records Officer"]


def test_several_roles_can_check_an_agreement_or_stop_a_tool() -> None:
    """"8.4 — ability to add multiple roles." "10.5 — add multi-field
    capability. Should have CTO, Agency Director, etc." """
    for key in ("proc.checker", "bad.stopper"):
        assert m1.by_key(key).kind == "rows", key
    said = m1.describe(m1.by_key("bad.stopper"),
                       {"bad.stopper": [{"role": "CTO"},
                                        {"role": "Agency Director"}]})
    assert said["lines"] == ["CTO", "Agency Director"]


def test_they_can_add_a_kind_of_information_we_did_not_list() -> None:
    """"Add more information that should never go in with a form field. Just
    add a row." BUG-07844C63."""
    assert m1.by_key("data.never").can_add


# ------------------------------------ simplified or formal, their choice

def test_a_modest_organization_is_steered_to_plain_language() -> None:
    """"If their governance inputs are 'modest' — e.g. 2 risk categories, only
    one or two people, no council — the default will be KISS, recommend
    'Simplified'." """
    modest = {"org.size": "u25", "who.shape": "one", "risk.levels": "two",
              "org.functions": {"legal": "contracted", "it": "part",
                                "security": "none"},
              "org.delegated": "no"}
    found = m1.register_for(modest)
    assert found["suggested"] == m1.SIMPLIFIED
    assert found["because"], "a recommendation it cannot explain"


def test_a_large_agency_is_steered_to_a_formal_instrument() -> None:
    """"Bigger agencies where they have dedicated staff for legal,
    procurement, IT, multiple people and inputs, recommend 'Formal'." """
    big = {"org.size": "2000+", "who.shape": "council", "risk.levels": "four",
           "org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS},
           "org.delegated": "yes"}
    found = m1.register_for(big)
    assert found["suggested"] == m1.FORMAL
    assert any("dedicated" in w for w in found["because"])


def test_open_records_is_not_treated_as_a_signal() -> None:
    """Nearly every public body is subject to it, so it says nothing about how
    large or formal this one is. Counting it tipped a mid-size city into
    Formal on its own — the recommendation being made by something true of
    everybody."""
    base = {"org.size": "u25", "who.shape": "one", "risk.levels": "two",
            "org.functions": {"legal": "none"}}
    without = m1.register_for(base)["suggested"]
    with_it = m1.register_for({**base, "org.open_records": "yes"})["suggested"]
    assert without == with_it == m1.SIMPLIFIED


def test_the_recommendation_is_never_imposed() -> None:
    """The rule everywhere else in this module. A twelve-person district that
    wants a formal instrument for its board is entitled to one."""
    modest = {"org.size": "u25", "who.shape": "one", "risk.levels": "two"}
    assert m1.register_of(modest) == m1.SIMPLIFIED
    assert m1.register_of({**modest, "done.register": m1.FORMAL}) == m1.FORMAL

    big = {"org.size": "2000+", "who.shape": "council",
           "org.functions": {f.value: "dedicated" for f in m1.FUNCTIONS}}
    assert m1.register_of(big) == m1.FORMAL
    assert m1.register_of({**big,
                           "done.register": m1.SIMPLIFIED}) == m1.SIMPLIFIED


def test_nothing_answered_yet_still_produces_a_document() -> None:
    """Nobody should have to answer a question about document style before
    they can download anything."""
    assert m1.register_of({}) == m1.SIMPLIFIED


def test_both_registers_bind_the_same_rules() -> None:
    """"Both say exactly the same thing and hold you to exactly the same
    rules." The difference is how it reads, not what it requires — so every
    question that contributes a clause must contribute one either way."""
    from app import prose

    answers = {"scope.covered": ["generative"], "scope.excluded": ["formulas"],
               "scope.arbiter": "The CTO", "scope.review": "standalone",
               "org.delegated": "yes", "who.shape": "council",
               "who.tiebreak": "The Director", "risk.worst": "yes",
               "floor.ai_finalises": "none", "floor.access_docs": "yes"}

    def sourced(register):
        return {c.source for s in prose.sections({**answers,
                                                  "done.register": register})
                for c in s.clauses}

    assert sourced(m1.SIMPLIFIED) == sourced(m1.FORMAL)


def test_the_formal_register_actually_reads_differently() -> None:
    """Otherwise the choice is decoration."""
    from app import prose

    answers = {"scope.covered": ["generative"], "who.shape": "council"}
    plain = [c.text for s in prose.sections(
        {**answers, "done.register": m1.SIMPLIFIED}) for c in s.clauses]
    formal = [c.text for s in prose.sections(
        {**answers, "done.register": m1.FORMAL}) for c in s.clauses]
    assert plain != formal
    assert any("This framework applies to" in t for t in formal)
    assert any("These rules cover" in t for t in plain)



# ---------------------------- 11, the pages that make it an instrument

def test_the_framing_questions_exist_at_all() -> None:
    """The client, holding our output beside a real adopted framework: "The
    questions we are asking should provide the inputs needed to create a draft
    that matches this."

    What his document had and ours did not was a Purpose and a Scope — why the
    organization is doing this, what standard it implements, which federal
    requirements apply, what happens when rules conflict, how far it reaches.
    Module One asked none of it. The register it replaced asked all of it,
    having been mined from that very document.
    """
    step = m1.by_number("11")
    assert step is not None, "step 11 is missing"
    # 11.5 is his own three-part structure, from BUG-01326CF4: whether there
    # are sub-units at all, what they are called, and whether any are
    # excluded. One box asking "what are your parts called, and does this
    # cover all of them?" was answerable only by an organization that has
    # parts, and gave nowhere to record an exclusion.
    # 11.1a and 11.1b are the Vision questions, from BUG-BE30FBD3: "Vision
    # should be a module inside the Framework."
    assert [q.number for q in step.questions] == [
        "11.1", "11.1a", "11.1b", "11.2", "11.3", "11.4", "11.5", "11.5a",
        "11.5b", "11.6", "11.7", "11.8"]


def test_the_federal_requirements_he_named_are_offered() -> None:
    """"OMB M-25-21 and the NIST AI Risk Management Framework" — his own
    answer in August, and the two that apply to most public bodies."""
    q = m1.by_key("why.federal")
    offered = {o.value: o for o in m1.options_for(q, {})}
    assert "omb" in offered and "M-25-21" in offered["omb"].label
    assert "nist" in offered and "NIST" in offered["nist"].label
    assert offered["omb"].recommended and offered["nist"].recommended
    # And a list of three cannot be complete for everybody.
    assert q.can_add


def test_the_stricter_rule_wins_by_default() -> None:
    """"Where this framework imposes requirements more stringent than state or
    federal policy, the more stringent standard controls." His words, and the
    answer that never leaves an organization short of a rule."""
    q = m1.by_key("why.conflict")
    assert m1.recommended_for(q, {}) == "stricter"
    said = m1.phrases(q, {"why.conflict": "stricter"})
    assert said == ["the more stringent standard controls"]


def test_asked_last_and_printed_first() -> None:
    """Somebody who has spent ten steps deciding how they will govern can say
    why in a sentence. Somebody on screen one cannot, and would write
    something they did not mean."""
    from app import prose

    numbers = [s.number for s in m1.STEPS]
    assert numbers.index("11") > numbers.index("10")
    assert numbers[-1] == "—", "the assembly is still last"

    # And it is section 1 of the document.
    purpose = prose.SECTIONS[0]
    assert purpose["title"] == "Purpose"
    assert purpose["from_step"] == "11"
    assert "why.reason" in purpose["keys"]


def test_purpose_and_scope_are_separate_sections() -> None:
    """Running them together produced a section that opened with "these rules
    cover tools that write text" — a scope statement standing in for a purpose
    the module had never asked for."""
    from app import prose

    titles = [s["title"] for s in prose.SECTIONS]
    assert titles[0] == "Purpose"
    assert titles[1] == "Scope"


def test_the_document_speaks_in_the_third_person() -> None:
    """His option labels address the reader — "tools that write text, images,
    or code *for you*" — which is right above a checkbox and wrong in an
    adopted instrument. `Option.prose` carries the third-person form; the
    label itself is untouched."""
    from app import prose

    answers = {"scope.covered": ["generative", "retrieval", "contractor"],
               "why.routes": ["built", "bought", "upgrade"],
               "done.register": m1.FORMAL}
    said = " ".join(c.text for s in prose.sections(answers)
                    for c in s.clauses)
    assert "for you" not in said, said[:160]
    assert "your own staff" not in said
    # And the labels on screen are exactly as he wrote them.
    label = next(o.label for o in m1.by_key("scope.covered").options
                 if o.value == "generative")
    assert label == "Tools that write text, images, or code for you"


def test_a_strategy_with_no_name_produces_no_clause() -> None:
    """"This framework is this organization's implementation of" followed by
    nothing is worse than saying nothing at all."""
    from app import prose

    named = {"why.state_strategy": {"value": "yes", "detail": "the SC State "
                                    "Agencies AI Strategy"}}
    blank = {"why.state_strategy": "yes"}
    assert any("SC State Agencies" in c.text
               for s in prose.sections(named) for c in s.clauses)
    assert not any(c.source == "11.2"
                   for s in prose.sections(blank) for c in s.clauses)


# ------------------------------------------- what an answer changes downstream

def test_every_gating_answer_is_a_driver() -> None:
    """The browser reloads the module after a "driver" is answered, so a
    question whose visibility or options just moved moves on screen.

    That list used to be seven keys written by hand in builder.js, and the
    client reported what it cost: "--2b did not populate until after I saved.
    Is that the only way? Can it show up before saving and proceeding?
    Creates a feeling of rework. (happens in other places, too)."

    He was right about the other places — there were thirteen. This is the
    test that keeps the list honest: anything a condition consults is a
    driver, derived from the questions rather than remembered.
    """
    found = m1.drivers()
    missed = []
    for question in m1.all_questions():
        for key in m1._keys_in(question.shows_when):
            if key not in found:
                missed.append(f"{question.number} shows_when {key}")
        for option in question.options:
            for key in m1._keys_in(option.shows_when):
                if key not in found:
                    missed.append(f"{question.number} option {key}")
        for rule in question.instead_when:
            for key in m1._keys_in(rule.get("if")):
                if key not in found:
                    missed.append(f"{question.number} instead_when {key}")
    assert not missed, missed


def test_the_answers_that_gate_the_newest_questions_are_drivers() -> None:
    """Both of these were added without being added to the hand-written list,
    which is how the fault reproduces rather than being a story about it."""
    found = m1.drivers()
    # Reveals 11.5a and 11.5b.
    assert "why.has_units" in found
    # Hides 6.8b when nobody has to write a plain-language description.
    assert "floor.plain_scope" in found
    # Swaps 4.2 from a grid of roles to one box, and rewords 4.3.
    assert "who.shape" in found


def test_a_computed_recommendation_names_what_it_reads() -> None:
    """—.2b's suggestion is computed rather than declarative, so walking the
    conditions cannot discover what it depends on. Those keys are named, and
    this is what notices if the computation grows a new one."""
    import inspect
    source = inspect.getsource(m1.register_for)
    for key in ("org.size", "who.shape", "risk.levels"):
        if key in source:
            assert key in m1.drivers(), key


def test_the_driver_list_goes_to_the_browser() -> None:
    sent = m1.summary({})["drivers"]
    assert isinstance(sent, list) and sent
    assert sorted(sent) == sent, "sent sorted, so a diff of the API is stable"
    assert "who.shape" in sent


# ------------------------------------------------ the five he reported at once

def test_a_case_by_case_permission_is_offered() -> None:
    """"6.1 - add option 2, yes, decided on a case-by-case basis."

    Between "none" and a list written in advance sits the answer most
    organizations actually give. Offering only the other two made them either
    overstate the prohibition or invent a list they do not have.
    """
    q = m1.by_key("floor.ai_finalises")
    offered = [o.value for o in m1.options_for(q, {})]
    assert "case_by_case" in offered
    # And it asks who decides, because a case-by-case permission with nobody
    # named against it is not a rule.
    chosen = next(o for o in q.options if o.value == "case_by_case")
    assert chosen.then_text


def test_a_case_by_case_permission_reaches_the_document() -> None:
    from app import prose
    answers = {"floor.ai_finalises": {
        "value": "case_by_case",
        "detail": "the District Manager, against the written safety test"}}
    said = [c.text for s in prose.sections(answers) for c in s.clauses]
    assert said, "no clause at all"
    assert "District Manager" in said[0]
    assert "highest level of scrutiny" in said[0]


def test_where_it_will_live_is_filled_from_what_they_said_at_9_10() -> None:
    """"Non-numbered section -3; fill in from previous section + give other
    options."

    9.10 already asks whether they intend to publish this framework. Asking
    again at —.3 without carrying that forward is what made the second one
    feel like rework — and it is what produced the contradiction rule the
    module already holds for the two disagreeing.
    """
    q = m1.by_key("done.where")
    assert m1.recommended_for(q, {}) == ""
    assert m1.recommended_for(
        q, {"watch.publish": {"value": ["framework"]}}) == "public"
    assert m1.recommended_for(
        q, {"watch.publish": {"value": ["nothing"]}}) == "internal"


def test_where_it_will_live_offers_more_than_three_places() -> None:
    """"Give other options." On request only is a real position and a
    different one from both "internal" and "public website"."""
    offered = [o.value for o in m1.options_for(m1.by_key("done.where"), {})]
    for value in ("internal", "public", "both", "request", "notyet", "other"):
        assert value in offered, value
