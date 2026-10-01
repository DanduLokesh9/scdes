"""Lifecycle — how the seven steps work.

This surface has no database and writes nothing, so almost every test is a
test about copy: whether it stays true, whether it stays in step with the
spine, and whether it survives being pasted into an email to a director who
has never opened the application.

The spine controls. Where a name or a rule appears on this page, it is
derived from the spine rather than typed out again, and the tests check the
derivation rather than the transcription.
"""

from __future__ import annotations

from app import lifecycle, spine


# ------------------------------------------------- it holds and writes nothing

def test_this_surface_writes_nothing() -> None:
    assert lifecycle.WRITES == ()
    assert lifecycle.HOLDS_NO_RECORDS is True
    assert lifecycle.OWNS_NO_GATE is True


def test_there_is_no_store_behind_this_page() -> None:
    """No table, no unit, no writes, no state. If a ticket asks this page
    to store something, that ticket belongs to Projects."""
    for never in ("_file", "_write", "_read", "_LOCK", "FILENAME"):
        assert not hasattr(lifecycle, never), never


def test_it_owns_none_of_the_seven_gates() -> None:
    for gate in spine.GATES:
        assert gate.owner != "Lifecycle"


def test_nothing_here_rates_progress_or_predicts_a_duration() -> None:
    said = " ".join(lifecycle.WHAT_IT_DOES_NOT_DO)
    assert "does not rate progress" in said
    assert "how long a step should take" in said
    assert "this application does not know" in said


def test_it_supplies_no_number_and_no_default() -> None:
    assert lifecycle.SUPPLIES_NO_NUMBER is True
    assert "links to the gap rather than filling it in" in \
        lifecycle.RENDER_THE_GAP


# ----------------------------------------------------- 2 · the shape of the page

def test_all_seven_are_expanded_at_rest() -> None:
    """A person who lands here needs to scan the whole thing and then read
    one part."""
    assert lifecycle.ALL_SEVEN_EXPANDED is True
    assert len(lifecycle.NOT_THIS) == 3
    assert any("accordion" in n for n in lifecycle.NOT_THIS)
    assert any("stepper" in n for n in lifecycle.NOT_THIS)


def test_the_standing_panel_sends_people_to_projects() -> None:
    assert "Projects is where you do them" in lifecycle.STANDING_PANEL


def test_five_parts_in_the_same_order_in_every_block() -> None:
    assert len(lifecycle.PARTS) == 5
    names = [p for p, _ in lifecycle.PARTS]
    assert names[0] == "The name and the question"
    assert names[-1] == "Where the work is done"


# ----------------------------------------------------------- 3 · the seven steps

def test_seven_steps_in_the_spines_order() -> None:
    assert [s.gate for s in lifecycle.STEPS] == list(spine.GATE_ORDER)


def test_every_step_carries_all_five_parts() -> None:
    for found in lifecycle.STEPS:
        assert found.question.endswith("?")
        assert found.says
        assert found.asks
        assert found.who_decides
        assert found.holds_people_up
        assert found.work_is_done_on


def test_every_step_name_comes_from_the_spine() -> None:
    for found in lifecycle.STEPS:
        assert found.name == spine.BY_GATE[found.gate].name


def test_no_step_is_ever_rendered_as_a_number() -> None:
    copy = repr(lifecycle.page()).lower()
    for banned in spine.BANNED_GATE_FORMS:
        assert banned not in copy, banned


def test_what_holds_people_up_names_two_or_three_things() -> None:
    """Named honestly, and not padded out to a round number."""
    for found in lifecycle.STEPS:
        assert 2 <= len(found.holds_people_up) <= 3, found.gate


def test_the_two_refusals_are_flagged_at_the_right_two_steps() -> None:
    refusing = set(spine.REFUSING_GATES)
    assert refusing == {spine.IDENTIFY, spine.DEPLOY}
    assert "declines to record a passage" in \
        lifecycle.BY_STEP[spine.IDENTIFY].flag
    assert "decline to record a passage" in \
        lifecycle.BY_STEP[spine.DEPLOY].says


def test_no_other_step_claims_it_can_refuse() -> None:
    for found in lifecycle.STEPS:
        if found.gate in spine.REFUSING_GATES:
            continue
        said = (found.says + found.flag).lower()
        assert "decline" not in said, found.gate
        assert "refuse" not in said, found.gate


def test_identify_says_most_projects_correctly_end_there() -> None:
    said = lifecycle.BY_STEP[spine.IDENTIFY].says
    assert "end here, correctly" in said
    assert "process change or a form" in said


def test_procure_includes_building_it_yourselves() -> None:
    said = lifecycle.BY_STEP[spine.PROCURE].says
    assert "including building it yourselves" in said


def test_a_tool_that_arrived_inside_something_else_still_passes() -> None:
    found = lifecycle.BY_STEP[spine.PROCURE]
    assert any("arrived inside something you already owned" in h
               for h in found.holds_people_up)
    assert found.flag == "The gate still applies to that tool."


def test_test_says_the_part_people_skip() -> None:
    said = lifecycle.BY_STEP[spine.TEST].says
    assert "what you did not test and therefore do not know" in said
    assert "An account with no limits in it is not accepted here." in said


def test_a_tool_that_cannot_be_tried_small_lifts_the_level() -> None:
    """Recording that fact raises the scrutiny level and does not waive the
    step."""
    assert "does not waive the step" in lifecycle.BY_STEP[spine.TEST].flag


def test_measure_is_where_most_projects_live() -> None:
    assert "live for years" in lifecycle.BY_STEP[spine.MEASURE].says


def test_sunset_distinguishes_a_version_from_the_tool() -> None:
    said = lifecycle.BY_STEP[spine.SUNSET].says
    assert "A version sunsets" in said and "which is bookkeeping" in said
    assert "judgment against the reason you got it" in said


def test_turning_a_tool_off_is_separate_from_deciding_to() -> None:
    assert "separate from deciding to, and anyone may do that" in \
        lifecycle.BY_STEP[spine.SUNSET].who_decides


def test_an_unknown_gate_returns_nothing() -> None:
    assert lifecycle.step("gate.nonesuch") is None


# --------------------------------------------- where the work is done, folded

def test_every_link_says_where_it_goes() -> None:
    for found in lifecycle.STEPS:
        said = lifecycle.where_the_work_is_done(found.gate)
        assert said.startswith("Where the work is done: ")
        for never in ("click here", "here ›", "more"):
            assert never not in said.lower()


def test_it_never_routes_to_an_office_they_do_not_have() -> None:
    said = lifecycle.where_the_work_is_done(
        spine.GOVERN, folds_to={"Oversight": "the general manager"})
    assert "the general manager" in said
    assert "Oversight" not in said


def test_no_technology_function_is_echoed_rather_than_flagged() -> None:
    page = lifecycle.page(has_technology_function=False)
    identify = next(s for s in page["steps"] if s["gate"] == spine.IDENTIFY)
    assert "building it yourselves is not one of the places" in \
        identify["adaptive"]
    for word in ("missing", "should", "defect", "required"):
        assert word not in identify["adaptive"].lower()


def test_where_the_function_exists_nothing_is_added() -> None:
    page = lifecycle.page(has_technology_function=True)
    identify = next(s for s in page["steps"] if s["gate"] == spine.IDENTIFY)
    assert "adaptive" not in identify


# --------------------------------------------------------- 4 · the loop

def test_the_loop_says_the_seven_are_a_circle() -> None:
    assert lifecycle.LOOP.startswith("The seven steps are a circle, not a "
                                     "line.")


def test_the_loop_goes_back_through_test_and_deploy() -> None:
    assert lifecycle.LOOP_GOES_THROUGH == (spine.TEST, spine.DEPLOY)
    assert "back through Test and Deploy" in lifecycle.LOOP


def test_the_project_does_not_start_over() -> None:
    assert "does not start over" in lifecycle.LOOP
    assert "keeps its whole history and gains a version" in lifecycle.LOOP


def test_the_loop_names_the_two_terms_that_prevent_the_surprise() -> None:
    assert "tell you before anything changes" in lifecycle.LOOP
    assert "somewhere to try it" in lifecycle.LOOP
    assert "you find out by noticing" in lifecycle.LOOP


def test_a_missing_notice_term_names_the_vendor_and_where_it_is_fixed() \
        -> None:
    """Rather than leaving it as a general warning."""
    plain = lifecycle.loop()
    named = lifecycle.loop(vendor_without_notice="Northbridge Systems")
    assert plain == lifecycle.LOOP
    assert "Northbridge Systems" in named
    assert "Vendors entry" in named


def test_the_text_version_of_the_loop_is_authoritative() -> None:
    """A description of the picture does not satisfy this."""
    assert lifecycle.TEXT_IS_AUTHORITATIVE is True
    assert lifecycle.DIAGRAM_IS_DECORATIVE is True


# ------------------------------------------------- 5.1 · the states

def test_the_eight_states_come_from_the_spine() -> None:
    got = lifecycle.states()
    assert len(got) == len(spine.STATES) == 8
    assert [s["id"] for s in got] == list(spine.STATE_ORDER)
    for row in got:
        assert row["shown_as"] and row["means"]


def test_two_facts_are_named_as_not_being_states() -> None:
    """Frequently confused for them."""
    assert len(lifecycle.NOT_STATES) == 2
    facts = dict(lifecycle.NOT_STATES)
    assert "Independent of how far it has got" in \
        facts["Whether a tool is in use"]
    assert "attaches to a passage rather than to a project" in \
        facts["Whether conditions are open"].lower()


def test_in_use_and_early_is_the_ordinary_way_this_starts() -> None:
    said = lifecycle.IN_USE_AND_EARLY
    assert "ordinary way this starts" in said
    assert "not a list of mistakes" in said


# --------------------------------------------------- 5.2 · the three hats

def test_three_hats_named_as_the_spine_names_them() -> None:
    got = lifecycle.hats()
    assert len(got) == 3
    assert [h["id"] for h in got] == list(spine.ROLES)
    for row in got:
        assert row["name"] == spine.ROLE_NAMES[row["id"]]


def test_one_person_wearing_all_three_is_said_without_advice() -> None:
    said = lifecycle.ONE_PERSON_ALL_THREE
    assert "Nothing here requires a second signature you did not ask for" \
        in said
    assert "which hat you were wearing each time" in said
    assert lifecycle.NO_ADVICE_ABOUT_CONCENTRATION is True
    for word in ("should", "risk", "recommend", "advise"):
        assert word not in said.lower()


def test_the_paragraph_appears_for_every_organisation() -> None:
    """Only its position changes with headcount."""
    for headcount in (0, 12, 2000):
        assert lifecycle.page(headcount=headcount)["one_person_all_three"]
    assert lifecycle.hats_first(12) is True
    assert lifecycle.hats_first(2000) is False


# ----------------------------------------------------- 5.3 · the floors table

def test_eight_floors_derived_from_the_spine() -> None:
    got = lifecycle.floors()
    assert len(got) == len(spine.FLOORS) == 8
    assert [f["id"] for f in got] == [f.id for f in spine.FLOORS]


def test_every_floor_says_where_it_is_set_and_where_it_comes_back() -> None:
    for row in lifecycle.floors():
        binds = [g for g in spine.GATE_ORDER
                 if row["id"] in spine.BINDS.get(g, {})]
        assert row["set_at"] == (spine.BY_GATE[binds[0]].name if binds
                                 else "")
        assert len(row["comes_back_at"]) == max(len(binds) - 1, 0)


def test_the_floors_table_names_gates_never_numbers() -> None:
    for row in lifecycle.floors():
        for where in [row["set_at"]] + row["comes_back_at"]:
            assert not where[:1].isdigit()
            assert where in [g.name for g in spine.GATES] + [""]


def test_only_the_refusing_gates_appear_as_refusing() -> None:
    names = {spine.BY_GATE[g].name for g in spine.REFUSING_GATES}
    for row in lifecycle.floors():
        assert set(row["refuses_at"]) <= names


def test_the_sentence_above_the_table_counts_what_is_actually_there() -> None:
    """An earlier draft of this copy said "most of these come back more than
    once", which the spine's own table contradicts."""
    said = lifecycle.why_the_floors_table()
    again = sum(1 for r in lifecycle.floors() if r["comes_back_at"])
    at_launch = len(spine.binding(spine.DEPLOY, spine.SATISFIED))
    assert f"{at_launch} of them have to be satisfied" in said
    assert f"{again} are checked again" in said
    assert "most" not in said.lower()


def test_it_says_governance_is_not_settled_at_purchase() -> None:
    assert "not settled at purchase" in lifecycle.why_the_floors_table()


# ------------------------------------- 5.4 · findings, gaps, recommendations

def test_three_objects_three_plain_sentences() -> None:
    """They look similar on screen and mean different things."""
    assert len(lifecycle.THREE_OBJECTS) == 3
    said = dict(lifecycle.THREE_OBJECTS)
    assert "quotes your own answer back at you" in said["A finding"]
    assert "Recording a gap is an acceptable answer" in said["A gap"]
    assert "declining one is a complete answer" in said["A recommendation"]


def test_a_recommendation_never_stops_anybody() -> None:
    said = dict(lifecycle.THREE_OBJECTS)["A recommendation"]
    assert "never stops you doing anything" in said
    assert "nothing will hold against you" in said


# ------------------------------------------------------------- 6 · adaptive

def test_the_example_adapts_by_organisation_type() -> None:
    assert lifecycle.example_for("Special district") == "work orders"
    assert lifecycle.example_for("City, town, or village") == "service calls"
    assert lifecycle.example_for(
        "School district or education agency") == "enrollment"
    assert lifecycle.example_for("County government") == "permits"


def test_an_unanswered_type_drops_the_clause() -> None:
    """Rather than being filled with a word this application chose."""
    assert lifecycle.example_for("") == ""
    assert lifecycle.example_for("Something else") == ""


# ------------------------------------------------------------ house language

def test_no_banned_word_reaches_this_page() -> None:
    copy = " ".join([
        repr(lifecycle.page()), lifecycle.LOOP, lifecycle.STANDING_PANEL,
        lifecycle.IN_USE_AND_EARLY, lifecycle.ONE_PERSON_ALL_THREE,
        lifecycle.NO_TECHNOLOGY_FUNCTION, lifecycle.RENDER_THE_GAP,
        " ".join(lifecycle.WHAT_IT_DOES_NOT_DO),
    ]).lower()
    for banned in spine.BANNED_IN_COPY:
        assert banned not in spine.banned_in(copy), banned


def test_the_loop_says_tool_rather_than_the_banned_word() -> None:
    """The specification's own draft of this paragraph read "a different
    model", which is the one word this product never writes."""
    assert "a different tool" in lifecycle.LOOP
    assert "model" not in lifecycle.LOOP.lower()


def test_no_other_organisation_is_ever_named() -> None:
    copy = repr(lifecycle.page()).lower()
    for word in ("other agencies", "other organizations", "peer agency",
                 "across accounts", "benchmark", "industry standard"):
        assert word not in copy


def test_no_copy_depends_on_having_seen_another_screen() -> None:
    """This is the page people screenshot. It will end up pasted into an
    email to a director who has never opened this application."""
    copy = " ".join(
        [s.says for s in lifecycle.STEPS]
        + [lifecycle.LOOP, lifecycle.IN_USE_AND_EARLY,
           lifecycle.STANDING_PANEL]).lower()
    for pointer in ("as above", "as described above", "see the previous",
                    "on the last screen", "as you saw"):
        assert pointer not in copy


def test_the_page_renders_with_nothing_answered() -> None:
    page = lifecycle.page()
    assert len(page["steps"]) == 7
    assert page["example"] == ""
    assert page["loop"] == lifecycle.LOOP
