"""Process — intake and the gates.

The load-bearing tests here are about two things. The first is the one
refusal: six obligations bind at Deploy, and nowhere else does a checklist
item stop a passage, because a checklist that behaved as though it could
would be describing software that does not exist.

The second is the word *moderate*. The framework's fallback question is a
fixed three-option question asked before the organization's level names are
in play, and left alone that word leaks out of the answer and into a finding
in front of an organization that never wrote it. The mapping is tested from
both ends.
"""

from __future__ import annotations

import pytest

from app import procedures, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never touch a real register, and never write a real audit entry."""
    monkeypatch.setattr(procedures, "_file",
                        lambda: tmp_path / "procedures.json")
    monkeypatch.setattr(procedures, "_log", lambda *a, **k: None)
    yield


def _written(name: str = "Turning off the permit assistant", **over):
    made = procedures.write(name=name, actor=WHO, **over)
    assert made["ok"], made
    return made["procedure"]


# ------------------------------------------------------------- the record

def test_only_the_name_is_required() -> None:
    """A half-written procedure that exists is worth more than a complete
    one that was abandoned at field nine."""
    assert procedures.write(name="The way in", actor=WHO)["ok"]
    assert not procedures.write(name="   ", actor=WHO)["ok"]


def test_twelve_kinds_shown_as_full_phrases() -> None:
    assert len(procedures.KINDS) == 12
    for kind in procedures.KINDS:
        assert len(kind) > 12, kind
        assert kind[0].isupper()


def test_eight_kinds_can_be_required_and_four_never_are() -> None:
    assert len(procedures.CAN_BE_REQUIRED) == 8
    assert len(procedures.NEVER_REQUIRED) == 4
    assert not set(procedures.CAN_BE_REQUIRED) & set(procedures.NEVER_REQUIRED)
    assert set(procedures.CAN_BE_REQUIRED) | set(procedures.NEVER_REQUIRED) \
        == set(procedures.KINDS)


def test_each_never_required_kind_says_why() -> None:
    """Named so that their absence reads as a decision rather than an
    oversight."""
    for kind, because in procedures.NEVER_REQUIRED.items():
        assert because.strip().endswith(".")
        assert len(because) > 50, kind


def test_trying_an_update_is_never_required_here() -> None:
    """They required a term in an agreement, not a written instruction on
    this surface."""
    because = procedures.NEVER_REQUIRED[procedures.TRY_AN_UPDATE]
    assert "term in an agreement" in because
    assert "inventing an obligation they never took on" in because


# --------------------------------------------------- the tier mapping, §6.3.1

def test_all_tools_renders_every_level_at_any_number_of_levels() -> None:
    for levels in (["routine", "elevated"],
                   ["low", "middle", "high"],
                   ["one", "two", "three", "four"]):
        assert procedures.levels_that_bind(procedures.ALL_TOOLS, levels) == \
            [procedures.EVERY_LEVEL]
        assert procedures.level_phrase(procedures.ALL_TOOLS, levels) == \
            "every level"


def test_with_two_levels_both_narrower_tiers_land_on_the_top_one() -> None:
    """Excluding the bottom of two leaves the top of two, and that is the
    only reading of their answer that is theirs."""
    two = ["routine", "elevated"]
    for tier in (procedures.MIDDLE_AND_UP, procedures.TOP_ONLY):
        assert procedures.levels_that_bind(tier, two) == ["elevated"]
        assert procedures.level_phrase(tier, two) == "elevated"


def test_with_three_levels_the_middle_tier_takes_the_top_two() -> None:
    three = ["routine", "raised", "high"]
    assert procedures.levels_that_bind(procedures.MIDDLE_AND_UP, three) == \
        ["raised", "high"]
    assert procedures.levels_that_bind(procedures.TOP_ONLY, three) == ["high"]


def test_with_four_levels_the_middle_tier_takes_three() -> None:
    four = ["a", "b", "c", "d"]
    assert procedures.levels_that_bind(procedures.MIDDLE_AND_UP, four) == \
        ["b", "c", "d"]
    assert procedures.levels_that_bind(procedures.TOP_ONLY, four) == ["d"]


def test_the_word_moderate_never_leaves_the_mapping() -> None:
    """That rule is absolute, and the mapping is what makes it keepable."""
    for tier in procedures.TIERS:
        for levels in (["routine", "elevated"], ["low", "mid", "top"]):
            said = procedures.level_phrase(tier, levels)
            assert "moderate" not in said
            assert tier not in said


def test_the_tier_string_is_never_rendered() -> None:
    for tier in procedures.TIERS:
        said = procedures.level_phrase(tier, ["routine", "elevated"])
        assert "high_only" not in said and "moderate_and_high" not in said


def test_no_levels_recorded_falls_back_to_every_level() -> None:
    """Nothing here invents a level name the organization did not write."""
    assert procedures.levels_that_bind(procedures.TOP_ONLY, []) == \
        [procedures.EVERY_LEVEL]


def test_several_levels_read_as_a_sentence() -> None:
    said = procedures.level_phrase(procedures.MIDDLE_AND_UP,
                                   ["a", "b", "c", "d"])
    assert said == "b, c and d"


# ---------------------------------------------- the six locked rows at Deploy

def test_six_things_bind_at_deploy_and_they_are_the_spines_six() -> None:
    assert len(procedures.LOCKED_AT_DEPLOY) == 6
    ours = {floor for floor, _ in procedures.LOCKED_AT_DEPLOY}
    assert ours == set(spine.binding(spine.DEPLOY, spine.SATISFIED))


def test_every_locked_row_names_a_real_floor() -> None:
    for floor, says in procedures.LOCKED_AT_DEPLOY:
        assert floor in spine.BY_FLOOR
        assert says.endswith(".")


def test_the_locked_rows_cannot_be_set_to_anything_else() -> None:
    made = procedures.checklist_for(spine.DEPLOY)
    assert len(made["locked"]) == 6
    for row in made["locked"]:
        assert row["consequence"] == procedures.MUST_EXIST
        assert row["locked"] is True


def test_no_other_gate_carries_a_locked_row() -> None:
    for gate in spine.GATE_ORDER:
        if gate == spine.DEPLOY:
            continue
        assert procedures.checklist_for(gate)["locked"] == []


def test_the_copy_under_the_six_names_the_other_refusal() -> None:
    said = procedures.UNDER_THE_SIX
    assert "cannot be recorded as having passed Deploy" in said
    assert "The only other refusal is at Identify" in said
    assert "you did not choose whether to have them, and neither did we" \
        in said


def test_not_answered_is_unavailable_on_the_seven_obligations() -> None:
    """This surface supplies the Identify checklist as well as the Deploy
    one, so the exception has to name both."""
    for floor, _ in procedures.LOCKED_AT_DEPLOY:
        got = procedures.resolutions_for(spine.DEPLOY, floor)
        assert procedures.NOT_ANSWERED not in got
        assert procedures.AS_A_CONDITION in got

    seventh = spine.binding(spine.IDENTIFY, spine.SATISFIED)[0]
    assert procedures.NOT_ANSWERED not in procedures.resolutions_for(
        spine.IDENTIFY, seventh)


def test_every_other_item_may_be_left_not_answered() -> None:
    assert procedures.resolutions_for(spine.PROCURE) == procedures.RESOLUTIONS
    assert procedures.resolutions_for(spine.DEPLOY, "") == \
        procedures.RESOLUTIONS


def test_the_consequence_does_not_decide_whether_a_passage_happens() -> None:
    assert "does not stop the passage being recorded" in \
        procedures.CONSEQUENCE_GUIDANCE
    assert "cannot stop anyone using a tool" in procedures.OUTSIDE_DEPLOY
    assert "software that does not exist" in procedures.OUTSIDE_DEPLOY


def test_the_version_row_at_deploy_does_not_bind() -> None:
    """The person confirming a checklist is entitled to know which version
    they are confirming it against."""
    row = procedures.version_row("v4", "v3")
    assert row["binds"] is False
    assert "v4" in row["says"] and "v3" in row["says"]


# --------------------------------------------- what the checklist supplies

def test_a_checklist_is_matched_by_gate_and_by_their_level_name() -> None:
    _written("Before it goes live", kind=procedures.CHECKLIST,
             status=procedures.IN_FORCE, gates=[spine.DEPLOY],
             levels=["elevated"], items=[{"item": "A signed agreement"}])
    at_level = procedures.checklist_for(spine.DEPLOY, "elevated")
    assert [i["item"] for i in at_level["items"]] == ["A signed agreement"]
    assert procedures.checklist_for(spine.DEPLOY, "routine")["items"] == []
    assert procedures.checklist_for(spine.TEST, "elevated")["items"] == []


def test_every_gate_and_every_level_are_values_rather_than_blanks() -> None:
    _written("Everywhere", kind=procedures.CHECKLIST,
             status=procedures.IN_FORCE, gates=[procedures.EVERY_GATE],
             levels=[procedures.EVERY_LEVEL],
             items=[{"item": "Somebody's name"}])
    for gate in (spine.PROCURE, spine.SUNSET):
        assert procedures.checklist_for(gate, "routine")["items"]


def test_a_drafted_checklist_supplies_nothing() -> None:
    _written("Not adopted", kind=procedures.CHECKLIST,
             status=procedures.DRAFTED, gates=[spine.DEPLOY],
             items=[{"item": "A signed agreement"}])
    assert procedures.checklist_for(spine.DEPLOY)["items"] == []


def test_this_surface_says_it_does_not_commit_the_passage() -> None:
    said = procedures.checklist_for(spine.TEST)["supplies_only"]
    assert "Projects commits the passage and writes the state" in said


# ------------------------------------------------------- 2 · the stat row

def test_five_counters_and_the_first_never_goes_down() -> None:
    first = _written("One", status=procedures.IN_FORCE)
    procedures.save(first["ref"], actor=WHO, name="One, revised")
    got = procedures.counters()
    assert got["written_down"] == 2
    assert got["in_force"] == 1


def test_never_checked_is_deliberately_not_taken_here() -> None:
    """A third surface shipping the same phrase against a third object
    would teach the user that the phrase means nothing in particular."""
    for name in procedures.COUNTER_NAMES:
        assert "Never checked" not in name
    assert "Never confirmed since it was written" in procedures.COUNTER_NAMES


def test_never_confirmed_is_honest_and_raises_nothing() -> None:
    _written("The manual way", kind=procedures.MANUAL_WAY,
             status=procedures.IN_FORCE, owner="Operations lead")
    assert procedures.counters()["never_confirmed"] == 1
    # No cadence recorded, so nothing is flagged for never trying it.
    assert procedures.findings() == []


def test_confirming_it_clears_the_count() -> None:
    row = _written("The manual way", status=procedures.IN_FORCE,
                   owner="Operations lead")
    procedures.confirm(row["ref"], actor=WHO, by="Operations lead")
    assert procedures.counters()["never_confirmed"] == 0


def test_past_its_date_counts_the_date_the_owner_chose() -> None:
    _written("Old", status=procedures.IN_FORCE,
             look_again_date="2020-01-01", owner="Records officer")
    assert procedures.counters(today="2026-09-22")["past_its_date"] == 1
    _written("Later", status=procedures.IN_FORCE,
             look_again_date="2030-01-01", owner="Records officer")
    assert procedures.counters(today="2026-09-22")["past_its_date"] == 1


def test_required_and_not_written_reads_their_own_answers() -> None:
    required = {procedures.ROUTE_IN: "You said nothing moves without it."}
    assert procedures.counters(required=required)["required_not_written"] == 1
    _written("The way in", kind=procedures.ROUTE_IN,
             status=procedures.IN_FORCE, owner="Records officer")
    assert procedures.counters(required=required)["required_not_written"] == 0


def test_an_organisation_with_nothing_public_is_never_counted_short() -> None:
    """The required set is different for every organization."""
    assert procedures.counters(required={})["required_not_written"] == 0


# --------------------------------------------------- 2.6 · the waiting line

def test_the_waiting_line_has_three_quiet_variants() -> None:
    assert "no written route in yet" in procedures.waiting_line(
        route_exists=False)
    assert "it has not been used" in procedures.waiting_line(
        ever_arrived=False)
    assert procedures.waiting_line([]) == "Nothing is waiting to be picked up."


def test_the_waiting_line_states_the_age_without_a_verdict() -> None:
    said = procedures.waiting_line(
        [{"route": "PR-1", "written_on": "2026-09-11"},
         {"route": "PR-1", "written_on": "2026-09-20"}], today="2026-09-22")
    assert "2 written down" in said
    assert "11 days" in said
    for word in ("late", "overdue", "should", "target"):
        assert word not in said.lower()


def test_only_what_came_in_through_the_route_is_counted() -> None:
    """Counting seeded tools here would report a queue nobody formed."""
    said = procedures.waiting_line([{"written_on": "2026-09-11"}],
                                   today="2026-09-22")
    assert said == "Nothing is waiting to be picked up."


def test_one_waiting_project_reads_as_one() -> None:
    said = procedures.waiting_line(
        [{"route": "PR-1", "written_on": "2026-09-21"}], today="2026-09-22")
    assert said.startswith("one written down")
    assert "picked it up" in said
    assert "1 day." in said


# --------------------------------------------------------- 3 · the findings

def test_thirteen_findings_of_its_own() -> None:
    assert len(procedures.OWN_FINDINGS) == 13
    assert len({f.id for f in procedures.OWN_FINDINGS}) == 13
    for finding in procedures.OWN_FINDINGS:
        assert finding.raised_by == "Process"
        assert finding.id.startswith("finding.process.")


def test_no_finding_reads_against_an_outside_standard() -> None:
    for finding in procedures.OWN_FINDINGS:
        said = finding.says.lower()
        for word in ("industry", "benchmark", "best practice", "peer"):
            assert word not in said


def test_two_of_the_spines_findings_are_raised_here_not_redefined() -> None:
    ours = {f.id for f in procedures.OWN_FINDINGS}
    for borrowed in procedures.RAISES_FROM_THE_SPINE:
        assert borrowed not in ours
        assert borrowed in spine.BY_FINDING


def test_the_floor_finding_is_one_object_in_both_places() -> None:
    because = procedures.RAISES_FROM_THE_SPINE["finding.floor_missing"]
    assert "six of the seven gates it is a finding and nothing else" in because
    assert "what differs is whether the passage gets recorded" in because


def test_a_stale_description_claims_nothing_about_correctness() -> None:
    assert "does not say the description is wrong" in \
        procedures.DESCRIPTION_STALE_CLAIMS_NOTHING
    assert "confirm it, and this closes" in \
        procedures.DESCRIPTION_STALE_CLAIMS_NOTHING


def test_an_unowned_procedure_is_a_document_not_a_procedure() -> None:
    _written("Nobody's", status=procedures.IN_FORCE)
    raised = procedures.findings()
    assert [f for f in raised
            if f["id"] == "finding.process.procedure_no_owner"]


def test_a_drafted_procedure_with_no_owner_raises_nothing() -> None:
    _written("Still drafting", status=procedures.DRAFTED)
    assert procedures.findings() == []


def test_the_missing_route_in_reads_their_own_delegation_answer() -> None:
    required = {procedures.ROUTE_IN: "You said nothing moves without it."}
    raised = procedures.findings(required=required)
    said = [f for f in raised if f["id"] == "finding.process.no_route_in"]
    assert said and "no route written here" in said[0]["says"]


def test_a_fallback_they_said_they_do_not_test_raises_nothing() -> None:
    """Flagging an answer the application invited teaches the user to lie
    to it."""
    _written("Doing it by hand", kind=procedures.MANUAL_WAY,
             status=procedures.IN_FORCE, owner="Operations lead")
    assert [f for f in procedures.findings()
            if f["id"] == "finding.process.fallback_never_tried"] == []
    raised = procedures.findings(fallback_cadence="twice a year")
    said = [f for f in raised
            if f["id"] == "finding.process.fallback_never_tried"]
    assert said and "twice a year" in said[0]["says"]


def test_a_fallback_that_has_been_tried_is_not_flagged() -> None:
    _written("Doing it by hand", kind=procedures.MANUAL_WAY,
             status=procedures.IN_FORCE, owner="Operations lead",
             last_tried="2026-06-01")
    assert [f for f in procedures.findings(fallback_cadence="twice a year")
            if f["id"] == "finding.process.fallback_never_tried"] == []


def test_wording_is_only_unapproved_where_they_named_an_approver() -> None:
    _written("What the public sees", kind=procedures.WORDING,
             status=procedures.IN_FORCE, owner="Communications")
    assert [f for f in procedures.findings()
            if f["id"] == "finding.process.wording_unapproved"] == []
    raised = procedures.findings(wording_approver="the communications lead")
    assert [f for f in raised
            if f["id"] == "finding.process.wording_unapproved"]


def test_a_superseded_procedure_only_flags_where_records_remain() -> None:
    """A fact rather than a fault: there are good reasons to let a pilot
    finish under the rules it started with."""
    row = _written("The old way", status=procedures.IN_FORCE,
                   owner="Records officer", in_force_from="2024-01-01")
    procedures.save(row["ref"], actor=WHO, name="The new way")
    assert [f for f in procedures.findings()
            if f["id"] == "finding.process.superseded_still_followed"] == []
    raised = procedures.findings(pointing_at={row["ref"]: 3})
    said = [f for f in raised
            if f["id"] == "finding.process.superseded_still_followed"]
    assert said and "3 records still point at the old one" in said[0]["says"]
    assert "fact rather than a fault" in procedures.MOVING_IS_A_CHOICE


def test_the_route_to_a_person_is_only_owed_on_a_public_record() -> None:
    live = [{"ref": "7QHC26", "gate": spine.MEASURE, "public_facing": True}]
    raised = procedures.findings(records=live)
    assert [f for f in raised
            if f["id"] == "finding.process.no_route_to_person"]
    private = [{"ref": "7QHC26", "gate": spine.MEASURE}]
    assert [f for f in procedures.findings(records=private)
            if f["id"] == "finding.process.no_route_to_person"] == []


def test_nothing_short_of_deploy_is_owed_the_operating_paper() -> None:
    early = [{"ref": "7QHC26", "gate": spine.PROCURE,
              "public_facing": True, "fallback_binds": True}]
    raised = procedures.findings(required={procedures.TRAINING: "x"},
                                 records=early)
    assert raised == []


def test_the_fallback_finding_renders_their_level_name() -> None:
    live = [{"ref": "7QHC26", "gate": spine.DEPLOY, "fallback_binds": True,
             "fallback_levels": "elevated", "level": "elevated"}]
    raised = procedures.findings(records=live)
    said = [f for f in raised if f["id"] == "finding.process.no_fallback"]
    assert said and "elevated" in said[0]["says"]
    assert "moderate" not in said[0]["says"]


def test_turn_off_is_only_owed_where_they_named_somebody() -> None:
    live = [{"ref": "7QHC26", "gate": spine.DEPLOY,
             "in_use": spine.IN_USE_YES}]
    assert [f for f in procedures.findings(records=live)
            if f["id"] == "finding.process.turnoff_unwritten"] == []
    raised = procedures.findings(records=live,
                                 may_stop_it=["the general manager"])
    said = [f for f in raised
            if f["id"] == "finding.process.turnoff_unwritten"]
    assert said and "general manager" in said[0]["says"]


# ---------------------------------------------- 3C · what raises nothing

def test_a_tool_found_already_running_is_never_a_fault() -> None:
    said = " ".join(procedures.WILL_NOT_RAISE)
    assert "governance that arrives after the tool did" in said
    assert "the normal case" in said


def test_a_declined_recommendation_is_never_a_finding_anywhere() -> None:
    said = " ".join(procedures.WILL_NOT_RAISE)
    assert "none anywhere in this application, whose trigger is a declined " \
        "recommendation" in said


def test_concentration_of_roles_is_not_a_finding_here() -> None:
    said = " ".join(procedures.WILL_NOT_RAISE)
    assert "plain count on Oversight and is never a finding here" in said


def test_no_finding_is_about_the_size_of_the_organisation() -> None:
    said = " ".join(procedures.WILL_NOT_RAISE)
    assert "heavy or light for the size of the organization" in said


# -------------------------------------------------- 4 · the standing check

def test_the_standing_check_writes_nothing_but_counts() -> None:
    assert procedures.CHECK_WRITES_NOTHING is True
    assert len(procedures.WATCH_COUNTS) == 4


def test_only_watched_procedures_are_counted() -> None:
    _written("No trigger", status=procedures.IN_FORCE, owner="x")
    assert procedures.standing_check()["watched"] == 0
    _written("Dated", status=procedures.IN_FORCE, owner="x",
             look_again_date="2030-01-01")
    assert procedures.standing_check()["watched"] == 1


def test_a_procedure_past_its_date_is_not_also_current() -> None:
    _written("Old", status=procedures.IN_FORCE, owner="x",
             look_again_date="2020-01-01")
    got = procedures.standing_check(today="2026-09-22")
    assert got["past_their_date"] == 1
    assert got["current"] == 0


def test_a_fired_trigger_shows_as_overtaken_by_something() -> None:
    row = _written("Against the tool as it was", status=procedures.IN_FORCE,
                   owner="x",
                   look_again=["Whenever the vendor changes the tool it "
                               "covers"])
    got = procedures.standing_check(
        fired={row["ref"]: ["a vendor changed the tool this procedure "
                            "covers"]})
    assert got["overtaken"] == 1
    assert got["current"] == 0


def test_opting_out_of_looking_again_is_not_a_watch() -> None:
    _written("Settled", status=procedures.IN_FORCE, owner="x",
             look_again=[procedures.NO_LOOK_AGAIN])
    assert procedures.standing_check()["watched"] == 0


def test_six_triggers_and_none_this_application_invented() -> None:
    assert len(procedures.TRIGGERS) == 6
    assert len(procedures.NOT_TRIGGERS) == 2
    for gone in procedures.NOT_TRIGGERS:
        assert gone not in procedures.TRIGGERS.values()


def test_two_triggers_belong_to_the_project_not_the_instruction() -> None:
    for elsewhere in procedures.BELONGS_TO_THE_PROJECT:
        assert elsewhere not in procedures.TRIGGERS.values()


def test_the_check_says_what_it_cannot_see() -> None:
    said = procedures.WHAT_THE_CHECK_CANNOT_SEE
    assert "whether the document at that address still exists" in said
    assert "a tick that meant nothing" in said
    assert "watching the statute book" in said


# ------------------------------------------------------- 5 · the list view

def test_seven_columns_and_none_of_them_a_colour_alone() -> None:
    assert len(procedures.COLUMNS) == 7
    status = dict(procedures.COLUMNS)["Status"]
    assert "never a color alone" in status


def test_an_unowned_cell_reads_nobody_named() -> None:
    assert procedures.owner_cell({}) == "Nobody named"
    assert procedures.owner_cell({"owner": "Records officer"}) == \
        "Records officer"


def test_zero_records_pointing_at_it_is_not_rendered_as_zero() -> None:
    """Zero on a newly written procedure means something different from
    zero on a three-year-old one."""
    assert procedures.pointing_cell(0) == procedures.NOTHING_POINTS_AT_THIS
    assert procedures.pointing_cell(4) == "4"


def test_the_last_confirmed_column_uses_the_short_form() -> None:
    assert procedures.confirmed_cell({}) == "Never confirmed"
    assert procedures.confirmed_cell({"confirmed_on": "2026-03-04"}) == \
        "2026-03-04"


def test_the_default_sort_puts_what_is_missing_at_the_top() -> None:
    assert "required and not written" in procedures.SORT_ORDER[0]
    assert "alphabetically" in procedures.SORT_ORDER[-1]


# ------------------------------------------------------------ ghost rows

def test_a_required_kind_with_nothing_in_force_becomes_a_ghost_row() -> None:
    ghosts = procedures.ghost_rows(required={
        procedures.ROUTE_IN: "You said nothing moves without your "
                             "framework and process."})
    assert len(ghosts) == 1
    assert ghosts[0]["action"] == procedures.WRITE_IT
    assert ghosts[0]["ghost"] is True


def test_writing_it_closes_the_ghost_row() -> None:
    _written("The way in", kind=procedures.ROUTE_IN,
             status=procedures.IN_FORCE, owner="Records officer")
    assert procedures.ghost_rows(
        required={procedures.ROUTE_IN: "You said so."}) == []


def test_a_kind_that_is_never_required_never_ghosts() -> None:
    for kind in procedures.NEVER_REQUIRED:
        assert procedures.ghost_rows(required={kind: "invented"}) == []


def test_one_ghost_row_per_level_never_one_per_gate_per_level() -> None:
    """A four-level organization would otherwise open the register to
    twenty-eight ghost rows on its first morning and close it."""
    ghosts = procedures.ghost_rows(
        required={procedures.CHECKLIST: "You said paper has to exist."},
        levels_needing_a_checklist={
            "routine": [spine.PROCURE, spine.DEPLOY],
            "elevated": [spine.TEST, spine.DEPLOY, spine.SUNSET]})
    assert len(ghosts) == 2
    assert {g["level"] for g in ghosts} == {"routine", "elevated"}
    assert len(ghosts[0]["gates"]) == 2


def test_a_level_with_every_gate_covered_carries_no_ghost_row() -> None:
    ghosts = procedures.ghost_rows(
        required={procedures.CHECKLIST: "You said paper has to exist."},
        levels_needing_a_checklist={"routine": []})
    assert ghosts == []


# ------------------------------------------------------- 5.4 · empty states

def test_four_empty_states_and_none_of_them_scolds() -> None:
    plain = procedures.empty_state()
    already = procedures.empty_state(already_using=True)
    named = procedures.empty_state(project="the permit assistant")
    no_tech = procedures.empty_state(no_technology=True)
    assert "downstream of that one" in plain
    assert "keep finding out last" in already
    assert "the permit assistant" in named
    assert "the thing you actually rely on" in no_tech
    for said in (plain, already, named, no_tech):
        assert said.startswith("Nothing written down yet.")
        for word in ("failed", "must", "violation"):
            assert word not in said.lower()


# ------------------------------------------------------ 5.5 · the route in

def test_the_route_in_is_behind_an_account() -> None:
    assert procedures.WHO_MAY_RAISE == "Any signed-in person, in any hat"
    assert "no login is an incident report" in \
        procedures.NOT_OPEN_TO_THE_WORLD


def test_this_surface_does_not_create_the_project() -> None:
    assert "same class of defect as one that writes state" in \
        procedures.PROJECTS_WRITES_THE_RECORD


def test_the_route_asks_three_things_and_the_first_is_fixed() -> None:
    assert len(procedures.DEFAULT_ASKS) == 3
    first = procedures.DEFAULT_ASKS[0]
    assert first["fixed"] is True and first["required"] is True
    for row in procedures.DEFAULT_ASKS[1:]:
        assert row["fixed"] is False


def test_a_route_that_takes_forty_minutes_is_walked_past() -> None:
    assert "forty minutes" in procedures.THREE_QUESTIONS


def test_an_already_running_tool_is_the_ordinary_way_this_starts() -> None:
    running = procedures.DEFAULT_ASKS[1]
    assert "nothing here treats it as a fault" in running["help"]


def test_the_solution_side_questions_moved_rather_than_vanished() -> None:
    """Asking them first invited exactly the answer the walkthrough is
    built to walk somebody back from."""
    assert len(procedures.ASKED_ELSEWHERE) == 5
    for question, where in procedures.ASKED_ELSEWHERE.items():
        assert where and len(where) > 20, question


def test_what_they_are_told_says_no_message_was_sent() -> None:
    said = procedures.what_they_are_told(
        record_id="7QHC26", shape="the general manager",
        cadence="once a quarter")
    assert "7QHC26" in said
    assert "sends no messages and no email" in said


def test_as_requests_come_in_is_a_complete_answer() -> None:
    said = procedures.what_they_are_told(
        record_id="7QHC26", shape="the general manager",
        cadence="as requests come in")
    assert "there is no set meeting, so it goes to them now" in said


def test_their_own_words_keep_the_identifier() -> None:
    """The identifier is the only way that person has of finding out what
    happened."""
    said = procedures.what_they_are_told(
        record_id="7QHC26", shape="x",
        their_words="Logged as [record id]. Somebody will call you.")
    assert "7QHC26" in said
    assert "[record id]" not in said


# ------------------------------------------------- 7 · versions on save

def test_a_drafted_procedure_is_edited_in_place() -> None:
    row = _written("Draft", status=procedures.DRAFTED)
    got = procedures.save(row["ref"], actor=WHO, name="Draft, tidied")
    assert got["new_version"] is False
    assert procedures.procedure(row["ref"])["name"] == "Draft, tidied"
    assert len(procedures.all_procedures()) == 1


def test_a_procedure_in_force_gets_a_new_version_instead() -> None:
    row = _written("In force", status=procedures.IN_FORCE, owner="x")
    got = procedures.save(row["ref"], actor=WHO, name="In force, revised")
    assert got["new_version"] is True
    assert got["procedure"]["replaces"] == row["ref"]
    old = procedures.procedure(row["ref"])
    assert old["status"] == procedures.REPLACED
    assert old["replaced_by"] == got["procedure"]["ref"]
    assert old["name"] == "In force"


def test_nothing_that_already_happened_changes() -> None:
    assert "Nothing that already happened changes" in procedures.VERSION_RULE
    assert "every record that passed under it keeps pointing at it" in \
        procedures.VERSION_RULE


def test_a_new_version_is_not_confirmed_by_inheritance() -> None:
    row = _written("In force", status=procedures.IN_FORCE, owner="x",
                   confirmed_on="2025-01-01", confirmed_by="Records officer")
    got = procedures.save(row["ref"], actor=WHO, steps="Different steps")
    assert got["procedure"]["confirmed_on"] == ""


def test_the_button_states_which_act_it_is() -> None:
    assert procedures.submit_label(None) == procedures.ADD_IT
    assert procedures.submit_label({"status": procedures.DRAFTED}) == \
        procedures.ADD_IT
    assert procedures.submit_label({"status": procedures.IN_FORCE}) == \
        procedures.SAVE_A_NEW_VERSION


def test_replaced_and_withdrawn_procedures_stay_on_the_list() -> None:
    row = _written("In force", status=procedures.IN_FORCE, owner="x")
    procedures.save(row["ref"], actor=WHO, name="Revised")
    assert len(procedures.all_procedures()) == 2
    assert procedures.counters()["written_down"] == 2


# ------------------------------------------------------------ 8 · gaps

def test_three_answers_produce_a_gap_rather_than_a_blank() -> None:
    assert len(procedures.GAP_ANSWERS) == 3
    assert procedures.NO_OWNER_IS_NOT_A_GAP is True


def test_where_no_owner_can_be_named_there_are_two_answers() -> None:
    assert procedures.HANDLE_INTERNALLY
    assert "outside help" in procedures.NEED_OUTSIDE_HELP


# ------------------------------------------------------------ house language

def test_no_banned_word_reaches_this_surface() -> None:
    copy = " ".join([
        repr(procedures.report()), procedures.SCOPE, procedures.UNDER_THE_SIX,
        procedures.ONLY_THE_NAME, procedures.VERSION_RULE,
        procedures.WHAT_THE_CHECK_CANNOT_SEE, procedures.CONSEQUENCE_GUIDANCE,
        procedures.OUTSIDE_DEPLOY, procedures.NOTHING_IS_PRIVATE,
        " ".join(procedures.WILL_NOT_RAISE),
        " ".join(procedures.NEVER_REQUIRED.values()),
    ]).lower()
    for banned in spine.BANNED_IN_COPY:
        assert banned not in spine.banned_in(copy), banned


def test_a_gate_is_never_rendered_as_a_number() -> None:
    copy = (repr(procedures.report())
            + " ".join(n + c for n, c in procedures.COLUMNS)).lower()
    for banned in spine.BANNED_GATE_FORMS:
        assert banned not in copy


def test_gate_names_are_names_rather_than_numbers() -> None:
    said = dict(procedures.COLUMNS)["Where it applies"]
    assert "Gate names" in said
    assert "Every gate" in said


def test_no_other_organisation_is_ever_named() -> None:
    copy = repr(procedures.report()).lower()
    for word in ("other agencies", "other organizations", "peer agency",
                 "across accounts", "benchmark"):
        assert word not in copy


def test_the_scope_line_states_the_one_enforcement() -> None:
    assert "cannot stop anyone using a tool" in procedures.SCOPE
    assert "six things that bind there" in procedures.SCOPE
    assert "does not write a record's state" in procedures.SCOPE


def test_the_register_survives_a_corrupt_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(procedures, "_file", lambda: path)
    assert procedures.all_procedures() == []
    assert procedures.counters()["written_down"] == 0
