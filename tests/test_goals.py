"""Vision — where you are trying to get to.

Two things carry most of the weight here. The first is that nothing on this
surface is computed from a measurement: a goal is reached when a person says
it is, and there is no progress figure anywhere on the page.

The second is that a goal with nothing against it, and a tool that was
retired without getting there, are both stated plainly and never softened. A
tool that did not get there is the single most useful thing this application
can tell an organization, so that finding is never suppressed.
"""

from __future__ import annotations

import pytest

from app import goals, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")
BOSS = Actor("council.cto", "Jordan Doe", Role.COUNCIL, title="Director")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never touch a real register, and never write a real audit entry."""
    monkeypatch.setattr(goals, "_file", lambda: tmp_path / "goals.json")
    monkeypatch.setattr(goals, "_log", lambda *a, **k: None)
    yield


def _goal(text: str = "Permits decided within the time we publish", **over):
    made = goals.write(goal=text, actor=WHO, **over)
    assert made["ok"], made
    return made["goal"]


def _project(ref: str = "7QHC26", **over):
    return {"ref": ref, "name": over.pop("name", "Permit triage"),
            "gate": over.pop("gate", spine.MEASURE),
            "state": over.pop("state", spine.CLEARED), **over}


# ------------------------------------------------------------- the record

def test_only_the_goal_is_required() -> None:
    assert goals.write(goal="Fewer repeat work orders", actor=WHO)["ok"]
    assert not goals.write(goal="   ", actor=WHO)["ok"]


def test_a_goal_is_not_a_project_and_holds_no_tool_numbers() -> None:
    """The baseline lives on the project, written at Procure."""
    row = _goal()
    for never in ("baseline", "before", "figure", "target", "measurement"):
        assert never not in row, never


def test_four_horizons_and_two_of_them_are_not_dates() -> None:
    assert len(goals.HORIZONS) == 4
    assert goals.LONGER in goals.HORIZONS
    assert goals.NO_DATE in goals.HORIZONS


def test_four_states_and_none_of_them_computed() -> None:
    assert len(goals.STANDINGS) == 4
    assert "a person says it is" in goals.NEVER_COMPUTED
    assert set(goals.CLOSED) == set(goals.STANDINGS) - {goals.OPEN}


# ------------------------------------------------- the placeholder by type

def test_the_placeholder_adapts_by_organisation_type() -> None:
    assert goals.placeholder("Special district") == \
        "Fewer repeat work orders on the same asset"
    assert goals.placeholder("School district or education agency") == \
        "Every family gets an enrollment answer the same week"
    assert goals.placeholder("City, town, or village").startswith(
        "Service calls answered")


def test_an_unanswered_type_drops_the_example_rather_than_inventing_one() \
        -> None:
    """The clause carrying the example is dropped rather than filled with a
    word this application chose."""
    assert goals.placeholder("") == ""
    assert goals.placeholder("Something else entirely") == ""


def test_no_placeholder_names_a_tool() -> None:
    for said in goals.PLACEHOLDERS.values():
        for word in ("AI", "tool", "system", "software", "vendor"):
            assert word not in said


# ------------------------------------------------------------- who may act

def test_anybody_may_propose_a_goal() -> None:
    assert goals.write(goal="A goal", actor=WHO)["ok"]
    assert "propose a goal" in goals.ANYONE_MAY


def test_only_whoever_decides_may_reword_a_goal() -> None:
    """If anybody could reword a goal, goals would quietly be rewritten to
    match whatever was achieved."""
    row = _goal()
    refused = goals.reword(row["ref"], actor=WHO, goal="Something easier")
    assert not refused["ok"] and refused["proposed"] is True
    assert goals.goal(row["ref"])["goal"] == row["goal"]

    done = goals.reword(row["ref"], actor=BOSS, goal="Something else")
    assert done["ok"] and done["goal"]["goal"] == "Something else"


def test_only_whoever_decides_may_close_a_goal() -> None:
    row = _goal()
    refused = goals.close(row["ref"], actor=WHO, stands=goals.REACHED)
    assert not refused["ok"] and refused["proposed"] is True
    assert goals.close(row["ref"], actor=BOSS, stands=goals.REACHED)["ok"]
    assert goals.goal(row["ref"])["stands"] == goals.REACHED


def test_a_goal_cannot_be_closed_into_a_state_that_does_not_exist() -> None:
    row = _goal()
    assert not goals.close(row["ref"], actor=BOSS, stands="Nearly")["ok"]


def test_the_reason_the_wording_is_held_is_written_down() -> None:
    assert "rewritten to match whatever was achieved" in \
        goals.WHY_THE_WORDING_IS_HELD


# -------------------------------------------------------- the tie, one way

def test_a_goal_never_claims_a_project() -> None:
    """Otherwise two surfaces could disagree about what a project is for."""
    row = _goal()
    assert "projects" not in row
    assert goals.goal_of(_project(goal=row["ref"])) == [row["ref"]]


def test_the_tie_reads_a_single_goal_or_a_list() -> None:
    assert goals.goal_of({"goal": "GL-1"}) == ["GL-1"]
    assert goals.goal_of({"goals": ["GL-1", "GL-2"]}) == ["GL-1", "GL-2"]
    assert goals.goal_of({"goal": ""}) == []
    assert goals.goal_of({}) == []


# ------------------------------------------------------- 2 · the stat row

def test_five_counters_with_plain_english_labels() -> None:
    assert len(goals.COUNTER_NAMES) == 5
    got = goals.counters()
    for name in ("recorded", "being_worked_on", "nothing_against_them",
                 "serving_no_goal", "closed"):
        assert name in got


def test_a_goal_with_nothing_against_it_is_counted_not_blamed() -> None:
    row = _goal()
    got = goals.counters(projects=[])
    assert got["nothing_against_them"] == 1
    assert got["being_worked_on"] == 0
    # The copy names the word only to rule it out.
    assert "neither is a fault" in got["two_halves"]
    for word in ("failure", "should", "overdue"):
        assert word not in got["two_halves"].lower()
    assert row["ref"]


def test_the_two_absence_counters_are_the_same_question() -> None:
    said = goals.TWO_HALVES
    assert "what you said you wanted and are not doing" in said
    assert "what you are doing and did not say you wanted" in said
    assert "neither is a fault" in said


def test_a_live_project_makes_a_goal_worked_on() -> None:
    row = _goal()
    got = goals.counters(projects=[_project(goal=row["ref"])])
    assert got["being_worked_on"] == 1
    assert got["nothing_against_them"] == 0


def test_a_retired_project_does_not_make_a_goal_worked_on() -> None:
    row = _goal()
    got = goals.counters(projects=[
        _project(goal=row["ref"], state=spine.RETIRED)])
    assert got["being_worked_on"] == 0
    # It is not "nothing against them" either — something was done about it.
    assert got["nothing_against_them"] == 0


def test_projects_serving_no_goal_counts_only_live_ones() -> None:
    assert goals.counters(projects=[_project()])["serving_no_goal"] == 1
    assert goals.counters(projects=[
        _project(state=spine.TURNED_DOWN)])["serving_no_goal"] == 0


def test_closed_goals_stay_on_the_list_and_are_counted() -> None:
    row = _goal()
    goals.close(row["ref"], actor=BOSS, stands=goals.NO_LONGER_WANTED)
    got = goals.counters()
    assert got["closed"] == 1
    assert got["recorded"] == 1


# --------------------------------------------------------- 3 · the findings

def test_eight_findings_of_its_own_and_one_shared() -> None:
    assert len(goals.OWN_FINDINGS) == 8
    assert goals.RAISED_HERE_FROM_THE_SPINE == ("finding.gap_no_owner",)
    for finding in goals.OWN_FINDINGS:
        assert finding.raised_by == "Vision"
        assert finding.id.startswith("finding.vs.")


def test_the_shared_finding_is_not_redefined_here() -> None:
    ours = {f.id for f in goals.OWN_FINDINGS}
    for shared in goals.RAISED_HERE_FROM_THE_SPINE:
        assert shared not in ours
        assert shared in spine.BY_FINDING


def test_no_finding_reads_against_an_outside_standard() -> None:
    for finding in goals.OWN_FINDINGS:
        said = finding.says.lower()
        for word in ("industry", "benchmark", "best practice", "peer"):
            assert word not in said


def test_naming_no_goal_is_ordinary_unless_they_required_otherwise() -> None:
    """Where the mission tie was not adopted, a project naming no goal is
    ordinary and the counter is shown without a finding behind it."""
    _goal()
    live = [_project()]
    assert [f for f in goals.findings(projects=live)
            if f["id"] == "finding.vs.no_goal_named"] == []
    raised = goals.findings(projects=live, mission_tie=True)
    said = [f for f in raised if f["id"] == "finding.vs.no_goal_named"]
    assert said and "Permit triage" in said[0]["says"]


def test_a_passed_horizon_asks_the_question_rather_than_answering_it() -> None:
    row = _goal(horizon=goals.WITHIN_A_YEAR)
    goals._write({"goals": {row["ref"]: {**row, "written_on": "2024-01-01"}},
                  "published": {}})
    raised = goals.findings(today="2026-09-22")
    said = [f for f in raised if f["id"] == "finding.vs.goal_horizon_passed"]
    assert said and "Nothing here says whether you got there" in said[0]["says"]


def test_a_closed_or_extended_goal_does_not_flag_its_horizon() -> None:
    row = _goal(horizon=goals.WITHIN_A_YEAR)
    goals._write({"goals": {row["ref"]: {
        **row, "written_on": "2024-01-01", "stands": goals.REACHED}},
        "published": {}})
    assert [f for f in goals.findings(today="2026-09-22")
            if f["id"] == "finding.vs.goal_horizon_passed"] == []

    goals._write({"goals": {row["ref"]: {
        **row, "written_on": "2024-01-01", "extended_to": "2028-01-01"}},
        "published": {}})
    assert [f for f in goals.findings(today="2026-09-22")
            if f["id"] == "finding.vs.goal_horizon_passed"] == []


def test_no_date_set_and_longer_than_that_are_never_overdue() -> None:
    """Neither is a date, and this application does not invent one."""
    for horizon in (goals.NO_DATE, goals.LONGER):
        row = _goal(horizon=horizon)
        goals._write({"goals": {row["ref"]: {**row,
                                             "written_on": "2010-01-01"}},
                      "published": {}})
        assert [f for f in goals.findings(today="2026-09-22")
                if f["id"] == "finding.vs.goal_horizon_passed"] == []


def test_a_retirement_that_did_not_get_there_is_stated_plainly() -> None:
    """A tool that did not get there is the single most useful thing this
    application can tell an organization."""
    row = _goal()
    retired = _project(goal=row["ref"], state=spine.RETIRED,
                       final_measurement="nine days", reached=False,
                       was_looking_for="five days")
    raised = goals.findings(projects=[retired])
    said = [f for f in raised if f["id"] == "finding.vs.retired_against_goal"]
    assert said
    assert "nine days" in said[0]["says"] and "five days" in said[0]["says"]
    for word in ("failed", "poor", "unacceptable", "should"):
        assert word not in said[0]["says"].lower()


def test_that_finding_is_named_as_never_suppressed() -> None:
    assert goals.NEVER_SUPPRESSED == "finding.vs.retired_against_goal"
    assert goals.NEVER_SUPPRESSED in {f.id for f in goals.OWN_FINDINGS}


def test_a_retirement_that_got_there_raises_nothing() -> None:
    row = _goal()
    got_there = _project(goal=row["ref"], state=spine.RETIRED,
                         final_measurement="four days", reached=True)
    assert [f for f in goals.findings(projects=[got_there])
            if f["id"] == "finding.vs.retired_against_goal"] == []


def test_a_goal_whose_every_project_has_gone_says_so() -> None:
    row = _goal()
    raised = goals.findings(projects=[
        _project(goal=row["ref"], state=spine.TURNED_DOWN)])
    said = [f for f in raised if f["id"] == "finding.vs.goal_orphaned"]
    assert said and row["goal"] in said[0]["says"]


def test_a_goal_with_nothing_ever_against_it_is_not_orphaned() -> None:
    """Never worked on and no longer worked on are different facts."""
    _goal()
    assert [f for f in goals.findings(projects=[])
            if f["id"] == "finding.vs.goal_orphaned"] == []


def test_value_unmeasured_only_where_they_said_value_or_retire() -> None:
    row = _goal()
    live = [_project(goal=row["ref"], gate=spine.MEASURE,
                     expected_by="2025-01-01")]
    assert [f for f in goals.findings(projects=live, today="2026-09-22")
            if f["id"] == "finding.vs.value_unmeasured"] == []
    raised = goals.findings(projects=live, value_or_retire="retire it",
                            today="2026-09-22")
    assert [f for f in raised if f["id"] == "finding.vs.value_unmeasured"]


def test_a_missed_outcome_with_nothing_decided_reads_their_answer() -> None:
    row = _goal()
    missed = [_project(goal=row["ref"], outcome_recorded=True,
                       reached=False)]
    raised = goals.findings(projects=missed,
                            not_delivering="pause it until it is fixed")
    said = [f for f in raised
            if f["id"] == "finding.vs.outcome_missed_no_decision"]
    assert said and "pause it until it is fixed" in said[0]["says"]


def test_a_missed_outcome_somebody_decided_about_raises_nothing() -> None:
    row = _goal()
    decided = [_project(goal=row["ref"], outcome_recorded=True,
                        reached=False, what_now="Paused on 3 September.")]
    assert [f for f in goals.findings(projects=decided)
            if f["id"] == "finding.vs.outcome_missed_no_decision"] == []


def test_a_goal_they_no_longer_want_with_the_tool_still_running() -> None:
    row = _goal()
    goals.close(row["ref"], actor=BOSS, stands=goals.NO_LONGER_WANTED)
    raised = goals.findings(projects=[
        _project(goal=row["ref"], in_use=spine.IN_USE_YES)])
    said = [f for f in raised
            if f["id"] == "finding.vs.goal_gone_tool_running"]
    assert said and "still running" in said[0]["says"]


def test_publishing_is_only_overdue_where_they_said_they_publish() -> None:
    assert [f for f in goals.findings()
            if f["id"] == "finding.vs.publish_overdue"] == []
    raised = goals.findings(publishes_yearly=True, last_published="2024-01-01",
                            today="2026-09-22")
    assert [f for f in raised if f["id"] == "finding.vs.publish_overdue"]


def test_publishing_inside_twelve_months_raises_nothing() -> None:
    assert [f for f in goals.findings(publishes_yearly=True,
                                      last_published="2026-03-01",
                                      today="2026-09-22")
            if f["id"] == "finding.vs.publish_overdue"] == []


# ------------------------------------------------------- 4 · the list view

def test_goals_group_by_horizon_nearest_first() -> None:
    _goal("Five year thing", horizon=goals.WITHIN_FIVE)
    _goal("This year thing", horizon=goals.WITHIN_A_YEAR)
    got = goals.grouped()
    assert [g["horizon"] for g in got] == [goals.WITHIN_A_YEAR,
                                           goals.WITHIN_FIVE]


def test_the_group_heading_is_announced_before_the_goals() -> None:
    _goal("One", horizon=goals.WITHIN_A_YEAR)
    _goal("Two", horizon=goals.WITHIN_A_YEAR)
    assert goals.grouped()[0]["heading"] == "Within a year, 2 goals"


def test_a_single_goal_reads_as_one_goal() -> None:
    _goal(horizon=goals.WITHIN_A_YEAR)
    assert goals.grouped()[0]["heading"].endswith("1 goal")


def test_goals_with_nothing_against_them_sort_to_the_top() -> None:
    """They are the ones somebody needs to look at."""
    worked = _goal("Being worked on", horizon=goals.WITHIN_A_YEAR)
    _goal("Nothing against this", horizon=goals.WITHIN_A_YEAR)
    got = goals.grouped(projects=[_project(goal=worked["ref"])])
    assert got[0]["goals"][0]["goal"] == "Nothing against this"


def test_an_empty_horizon_is_not_rendered_as_a_group() -> None:
    _goal(horizon=goals.WITHIN_A_YEAR)
    assert len(goals.grouped()) == 1


def test_the_empty_state_asks_for_an_outcome_not_a_project() -> None:
    assert "not the project or the tool that gets you there" in \
        goals.EMPTY_STATE


def test_a_goal_with_nothing_against_it_says_so_in_words() -> None:
    """Rather than being conveyed by an empty space where other goals have
    content."""
    row = _goal()
    assert goals.portfolio(row["ref"], projects=[])["summary"] == \
        goals.NOTHING_AGAINST_IT


# ----------------------------------------------- 6 · the portfolio read-back

def test_the_portfolio_is_prose_and_a_list_never_a_chart() -> None:
    row = _goal()
    got = goals.portfolio(row["ref"], projects=[
        _project("A", name="Permit triage"),
        _project("B", name="Appeal sorter", goal=row["ref"])])
    assert isinstance(got["summary"], str)
    assert isinstance(got["lines"], list)
    assert "no progress figure" in got["no_progress_figure"]


def test_each_project_is_a_sentence_naming_its_gate_and_state() -> None:
    row = _goal()
    got = goals.portfolio(row["ref"], projects=[
        _project(goal=row["ref"], gate=spine.MEASURE,
                 state=spine.WAITING_DECISION)])
    assert got["lines"][0].startswith("Permit triage, at ")
    assert got["lines"][0].endswith(".")
    for banned in spine.BANNED_GATE_FORMS:
        assert banned not in got["lines"][0].lower()


def test_retired_and_turned_down_projects_stay_in_the_read_back() -> None:
    """A goal's history is more useful than its current state."""
    row = _goal()
    got = goals.portfolio(row["ref"], projects=[
        _project("A", name="Kept", goal=row["ref"]),
        _project("B", name="Dropped", goal=row["ref"],
                 state=spine.TURNED_DOWN),
        _project("C", name="Retired one", goal=row["ref"],
                 state=spine.RETIRED, retired_on="2026-03-04",
                 reached=False)])
    assert got["counts"] == {"all": 3, "live": 1, "waiting": 0,
                            "retired": 1, "turned_down": 1}
    assert "Retired one was retired in 2026-03" in got["summary"]
    assert "did not reach what you were looking for" in got["summary"]
    assert "was turned down" in got["summary"]
    assert "history is more useful" in goals.HISTORY_STAYS


def test_the_portfolio_counts_and_states_and_nothing_more() -> None:
    row = _goal()
    got = goals.portfolio(row["ref"], projects=[
        _project("A", goal=row["ref"]),
        _project("B", goal=row["ref"], state=spine.WAITING_DECISION)])
    assert "two projects name this goal" in got["summary"].lower()
    assert "waiting on a decision" in got["summary"]
    for word in ("%", "score", "progress", "on track"):
        assert word not in got["summary"].lower()


def test_the_heading_carries_the_horizon_and_the_owner() -> None:
    row = _goal(horizon=goals.WITHIN_A_YEAR, owner="Permitting director")
    got = goals.portfolio(row["ref"])
    assert "By Within a year." in got["heading"]
    assert "Owned by Permitting director." in got["heading"]


def test_a_goal_with_no_owner_omits_the_clause() -> None:
    row = _goal()
    assert "Owned by" not in goals.portfolio(row["ref"])["heading"]


def test_an_unknown_goal_returns_nothing() -> None:
    assert goals.portfolio("GL-NOTHING") == {}


# ------------------------------------------------------ 7 · the public view

def test_nothing_is_published_from_this_application() -> None:
    got = goals.set_public_view(actor=BOSS, publishes=goals.PUBLISH_YES,
                               appears=["The goal"], where="A yearly report")
    assert got["ok"]
    assert "composes nothing, sends nothing and hosts nothing" in got["says"]


def test_publishing_nothing_states_it_rather_than_disappearing() -> None:
    assert "That is recorded. You can change it here." in \
        goals.PUBLISHES_NOTHING_TODAY


def test_five_things_may_appear_publicly_including_nothing() -> None:
    assert len(goals.APPEARS_PUBLICLY) == 5
    assert "Nothing" in goals.APPEARS_PUBLICLY


def test_the_public_view_survives_being_unset() -> None:
    assert goals.public_view() == {}


# ------------------------------------------ 9 · what this surface is not

def test_it_gates_nothing_and_owns_no_gate() -> None:
    assert goals.OWNS_NO_GATE is True
    assert "No project is refused for naming no goal." in \
        " ".join(goals.WHAT_IT_IS_NOT)
    for gate in spine.GATES:
        assert gate.owner != "Vision"


def test_it_is_the_required_reader_at_sunset() -> None:
    assert goals.REQUIRED_READER_AT == spine.SUNSET
    assert spine.SUNSET in goals.SERVES


def test_it_holds_no_measurement_of_any_tool() -> None:
    said = " ".join(goals.WHAT_IT_IS_NOT)
    assert "written at Procure and read at Measure" in said
    assert "none of the numbers behind it" in said


def test_it_is_not_a_plan_and_carries_no_milestones() -> None:
    said = " ".join(goals.WHAT_IT_IS_NOT)
    assert "No tasks, no milestones, no owners of steps" in said


def test_governance_settings_are_read_elsewhere() -> None:
    """Loading this surface with them would make it the second place every
    answer lives."""
    assert len(goals.NOT_RENDERED_HERE) == 4
    surface = repr(goals.report()).lower()
    for elsewhere in goals.NOT_RENDERED_HERE:
        assert f"'{elsewhere}'" not in surface


def test_an_existing_planning_document_is_read_first() -> None:
    assert "upload it first" in goals.UPLOAD_FIRST


# ------------------------------------------------------------ house language

def test_no_banned_word_reaches_this_surface() -> None:
    copy = " ".join([
        repr(goals.report()), goals.EMPTY_STATE, goals.TWO_HALVES,
        goals.NEVER_COMPUTED, goals.NO_PROGRESS_FIGURE, goals.HISTORY_STAYS,
        goals.PUBLISHES_NOTHING, goals.UPLOAD_FIRST,
        goals.WHY_THE_WORDING_IS_HELD, " ".join(goals.WHAT_IT_IS_NOT),
        " ".join(goals.PLACEHOLDERS.values()),
    ]).lower()
    for banned in spine.BANNED_IN_COPY:
        assert banned not in spine.banned_in(copy), banned


def test_no_gate_is_rendered_as_a_number() -> None:
    copy = repr(goals.report()).lower()
    for banned in spine.BANNED_GATE_FORMS:
        assert banned not in copy


def test_no_other_organisation_is_ever_named() -> None:
    copy = repr(goals.report()).lower()
    for word in ("other agencies", "other organizations", "peer agency",
                 "across accounts", "benchmark"):
        assert word not in copy


def test_the_register_survives_a_corrupt_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(goals, "_file", lambda: path)
    assert goals.all_goals() == []
    assert goals.counters()["recorded"] == 0
