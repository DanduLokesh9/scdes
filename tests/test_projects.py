"""Projects — the only surface that may write a project's state.

Most of what follows is about the things this surface is careful *not* to
do. It does not blame somebody for a tool that was already running. It does
not rate a project, a person or the organization. It does not pretend a
passage recorded after the fact happened first. It does not refuse a
passage anywhere the spine does not say it may.

And it counts the projects that ended without buying anything, deliberately,
because an organization that declined four AI purchases on the evidence can
show that record to anybody who asks.
"""

from __future__ import annotations

import pytest

from app import projects, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")
BOSS = Actor("council.cto", "Jordan Doe", Role.COUNCIL, title="Director")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never touch a real register, and never write a real audit entry."""
    path = tmp_path / "projects.json"
    monkeypatch.setattr(projects, "_file", lambda: path)
    monkeypatch.setattr(projects, "_record",
                        lambda *a, **k: None)
    yield


def _started(name: str = "Permit triage", **over):
    made = projects.start(name, WHO, **over)
    assert made["ok"], made
    return made["project"]


# ------------------------------------------------------------- the reference

def test_only_the_name_is_required() -> None:
    """A register that refuses a row until every box is filled is one
    nobody finishes."""
    assert projects.start("Permit triage", WHO)["ok"]
    assert not projects.start("   ", WHO)["ok"]


def test_the_reference_carries_nothing_in_its_shape() -> None:
    """Short, opaque, permanent, never reused, and carrying no
    classification, no year and no department code."""
    import datetime
    year = str(datetime.date.today().year)
    refs = sorted({projects.reference(set()) for _ in range(200)})
    assert len(refs) > 190, "references collide too often"
    for ref in refs:
        assert len(ref) == projects.REFERENCE_LENGTH
        assert year not in ref
        # No vowels, so nothing spells a word by accident.
        assert not set(ref) & set("AEIOU")
        # Nothing a reader could mistake over a phone.
        assert not set(ref) & set("01OIL")

    # Not sequential. An earlier version of this test also forbade the
    # two-digit year appearing anywhere in the string, which was wrong in an
    # instructive way: "26" turns up by chance in a random six-character
    # reference, and excluding it would have put a pattern into a value
    # whose whole job is to have none. What matters is that nothing can be
    # *inferred* from the shape, so this checks the thing that would betray
    # a sequence — a shared leading character across consecutive issues.
    leading = {ref[0] for ref in refs}
    assert len(leading) > 10, "references look sequential"


def test_a_reference_is_never_reused() -> None:
    taken = {projects.reference(set()) for _ in range(50)}
    for _ in range(50):
        fresh = projects.reference(taken)
        assert fresh not in taken
        taken.add(fresh)


def test_the_organisation_may_set_a_prefix() -> None:
    assert projects.reference(set(), "AI").startswith("AI-")


def test_a_project_opens_at_identify_proposed() -> None:
    project = _started()
    assert project["gate"] == spine.IDENTIFY
    assert project["state"] == spine.PROPOSED


def test_already_running_is_answered_honestly_and_not_judged() -> None:
    """A tool nobody approved is the ordinary way this starts and nothing
    here treats it as a fault."""
    assert _started("A", already_running="yes")["in_use"] == spine.IN_USE_YES
    assert _started("B", already_running="no")["in_use"] == spine.IN_USE_NO
    assert _started("C")["in_use"] == spine.IN_USE_UNKNOWN


# --------------------------------------------------------------- the tracker

def test_the_tracker_always_shows_all_seven_gates() -> None:
    """A mall map: the whole layout, the dot showing where you are, and the
    thing standing between you and the next room."""
    got = projects.tracker(_started())
    assert [g["name"] for g in got["gates"]] == [
        "Govern", "Identify", "Procure", "Test", "Deploy", "Measure",
        "Sunset"]
    assert sum(1 for g in got["gates"] if g["current"]) == 1


def test_the_tracker_shows_no_percentage_or_estimate() -> None:
    """The application does not know how long a decision takes in a given
    organization, and a guessed estimate would be wrong often enough that
    people stop trusting the tracker."""
    got = projects.tracker(_started())
    import json
    said = json.dumps(got).lower()
    for guess in ("percent", "%", "estimate", "days left", "eta",
                  "complete", "progress"):
        assert guess not in said, guess


def test_an_office_they_do_not_have_is_never_shown_as_missing() -> None:
    project = _started()
    projects.set_state(project["ref"], spine.WAITING_PERSON, WHO)
    got = projects.tracker(projects.one(project["ref"]),
                           missing_function="a legal function")
    assert "you recorded as not present here" in got["waiting_on"]


def test_nothing_holding_it_up_says_so() -> None:
    project = _started()
    projects.set_state(project["ref"], spine.BEING_WORKED, WHO)
    assert projects.waiting_on(projects.one(project["ref"])) == (
        "Nothing is holding this up")


# ------------------------------------------------------------- the passage

def test_identify_refuses_a_project_with_nobody_named() -> None:
    """One of the two refusals in the whole application."""
    project = _started()
    answer = projects.move(project["ref"], spine.PROCURE, WHO)
    assert not answer["ok"]
    assert answer["error"] == spine.REFUSE_IDENTIFY
    # And the refusal is navigable rather than a dead end.
    assert answer["legal_moves"]
    assert "floor.somebody_named" in answer["unmet"]


def test_a_refused_passage_writes_nothing() -> None:
    """No field holds an attempt."""
    project = _started()
    projects.move(project["ref"], spine.PROCURE, WHO)
    after = projects.one(project["ref"])
    assert after["gate"] == spine.IDENTIFY
    assert after["passages"] == []


def test_a_named_project_passes_and_lands_cleared() -> None:
    """Cleared is the handoff: the gate behind it is passed and nobody has
    picked it up at the next one."""
    project = _started()
    _name_and_satisfy(project["ref"], ["floor.somebody_named"])
    answer = projects.move(project["ref"], spine.PROCURE, WHO)
    assert answer["ok"]
    after = projects.one(project["ref"])
    assert after["gate"] == spine.PROCURE
    assert after["state"] == spine.CLEARED


def _name_and_satisfy(ref: str, floors: list[str]) -> None:
    held = projects._read()
    held["projects"][ref]["accountable"] = "the Permitting Manager"
    held["projects"][ref]["satisfied"] = floors
    projects._write(held)


def test_deploy_refuses_until_all_six_point_at_something() -> None:
    project = _started()
    six = list(spine.binding(spine.DEPLOY, spine.SATISFIED))
    _name_and_satisfy(project["ref"], six)
    held = projects._read()
    held["projects"][project["ref"]]["gate"] = spine.DEPLOY
    held["projects"][project["ref"]]["satisfied"] = six[:-1]
    projects._write(held)

    answer = projects.move(project["ref"], spine.MEASURE, WHO)
    assert not answer["ok"]
    assert answer["error"] == spine.REFUSE_DEPLOY

    _name_and_satisfy(project["ref"], six)
    assert projects.move(project["ref"], spine.MEASURE, WHO)["ok"]


def test_a_passage_recorded_after_the_fact_keeps_both_dates() -> None:
    """Order is recorded, never enforced. Rewriting history to make the
    register look tidy would destroy what the register is for."""
    project = _started()
    _name_and_satisfy(project["ref"], ["floor.somebody_named"])
    projects.move(project["ref"], spine.PROCURE, WHO,
                  happened="2026-01-04T09:00:00+00:00")
    passage = projects.one(project["ref"])["passages"][0]
    assert passage["happened"] == "2026-01-04T09:00:00+00:00"
    assert passage["at"] != passage["happened"]
    got = projects.tracker(projects.one(project["ref"]))
    assert any(g["recorded_after_the_fact"] for g in got["gates"])


def test_skipping_forward_is_refused_with_the_spine_wording() -> None:
    project = _started()
    _name_and_satisfy(project["ref"], ["floor.somebody_named"])
    answer = projects.move(project["ref"], spine.DEPLOY, WHO)
    assert answer["error"] == spine.REFUSE_NOT_AVAILABLE
    assert answer["error"] in spine.REASONS


def test_a_condition_travels_with_the_passage() -> None:
    """Conditions are the mechanism that keeps this application from
    blocking."""
    project = _started()
    _name_and_satisfy(project["ref"], ["floor.somebody_named"])
    projects.move(project["ref"], spine.PROCURE, WHO, conditions=[
        {"what": "accessibility documentation", "owner": "the IT Lead",
         "by": "2026-12-01"}])
    after = projects.one(project["ref"])
    assert len(after["conditions"]) == 1
    assert after["conditions"][0]["closed"] is None


# ------------------------------------------------------------ state, paused

def test_a_pause_is_reversible_to_what_it_was_doing() -> None:
    """A pause that cannot be reversed is a retirement."""
    project = _started()
    projects.set_state(project["ref"], spine.BEING_WORKED, WHO)
    projects.set_state(project["ref"], spine.PAUSED, WHO)
    assert projects.one(project["ref"])["state"] == spine.PAUSED
    projects.start_again(project["ref"], WHO)
    assert projects.one(project["ref"])["state"] == spine.BEING_WORKED


def test_nothing_moves_from_a_pause_until_it_is_reversed() -> None:
    project = _started()
    _name_and_satisfy(project["ref"], ["floor.somebody_named"])
    projects.set_state(project["ref"], spine.PAUSED, WHO)
    answer = projects.move(project["ref"], spine.PROCURE, WHO)
    assert answer["error"] == spine.REFUSE_STOPPED


def test_a_turned_down_project_stays_on_the_list_and_can_come_back() -> None:
    """Nothing is ever deleted, and a proposal that comes back next year
    joins its own history rather than starting a second one."""
    project = _started()
    projects.set_state(project["ref"], spine.TURNED_DOWN, WHO)
    assert projects.one(project["ref"]) is not None
    projects.pick_up_again(project["ref"], WHO)
    assert projects.one(project["ref"])["state"] == spine.BEING_WORKED


# ------------------------------------------------------------- the counters

def test_running_ahead_is_counted_and_never_accused() -> None:
    """This counter will be nearly everything on the first day of a small
    organization's use."""
    _started("A", already_running="yes")
    _started("B", already_running="yes")
    _started("C", already_running="no")
    got = projects.counters()
    assert got["running_ahead"] == 2
    said = got["says"]["running_ahead"].lower()
    assert "not a list of mistakes" in said
    for blame in ("violation", "unauthorised", "unauthorized", "failure",
                  "should not", "breach"):
        assert blame not in said


def test_ended_without_a_tool_is_counted_on_purpose() -> None:
    """These are the problems you solved without buying anything."""
    project = _started("Process change")
    held = projects._read()
    held["projects"][project["ref"]]["chosen_step"] = 1
    held["projects"][project["ref"]]["state"] = spine.TURNED_DOWN
    projects._write(held)

    bought = _started("Bought one")
    held = projects._read()
    held["projects"][bought["ref"]]["chosen_step"] = 6
    held["projects"][bought["ref"]]["state"] = spine.TURNED_DOWN
    projects._write(held)

    got = projects.counters()
    assert got["ended_without_a_tool"] == 1
    assert "without buying anything" in got["says"]["ended_without_a_tool"]


def test_no_counter_is_a_proportion_or_a_grade() -> None:
    _started()
    got = projects.counters()
    for key, value in got.items():
        if key == "says":
            continue
        assert isinstance(value, int), key


def test_a_turned_down_project_is_not_counted_as_open() -> None:
    project = _started()
    assert projects.counters()["open"] == 1
    projects.set_state(project["ref"], spine.TURNED_DOWN, WHO)
    assert projects.counters()["open"] == 0
    # And it is still on the list.
    assert len(projects.all_projects()) == 1


# --------------------------------------------------------------- findings

def test_a_problem_that_names_a_product_is_flagged() -> None:
    project = _started()
    held = projects._read()
    held["projects"][project["ref"]]["problem"] = {
        "happening": "We need Copilot licenses for the permit team."}
    projects._write(held)
    found = {f["id"] for f in projects.findings(
        projects.one(project["ref"]))}
    assert "finding.pj.problem_is_a_solution" in found


def test_the_parked_idea_block_never_raises_that_finding() -> None:
    """Parking the solution somebody walked in with is the point of that
    block — dismissing it is what the walkthrough is written to avoid."""
    project = _started()
    held = projects._read()
    held["projects"][project["ref"]]["problem"] = {
        "happening": "Applications sit for three weeks before anybody looks.",
        "parked": "Somebody suggested Copilot might help."}
    projects._write(held)
    found = {f["id"] for f in projects.findings(
        projects.one(project["ref"]))}
    assert "finding.pj.problem_is_a_solution" not in found


def test_nobody_named_is_raised_from_identify_onward() -> None:
    project = _started()
    found = {f["id"] for f in projects.findings(
        projects.one(project["ref"]))}
    assert "finding.no_owner" in found


def test_retired_and_still_in_use_is_a_contradiction_worth_saying() -> None:
    project = _started("X", already_running="yes")
    held = projects._read()
    held["projects"][project["ref"]]["state"] = spine.RETIRED
    projects._write(held)
    found = {f["id"] for f in projects.findings(
        projects.one(project["ref"]))}
    assert "finding.pj.retired_still_in_use" in found


def test_no_finding_is_raised_for_a_declined_recommendation() -> None:
    """Declining is a complete answer, and this surface records it without
    comment."""
    assert "a recommendation was declined" in projects.NO_FINDING_FOR


def test_every_finding_quotes_their_own_framework_and_no_benchmark() -> None:
    project = _started()
    held = projects._read()
    held["projects"][project["ref"]]["problem"] = {
        "happening": "We need a platform."}
    projects._write(held)
    for finding in projects.findings(projects.one(project["ref"])):
        said = finding["says"].lower()
        for outside in ("industry", "benchmark", "best practice", "peers",
                        "other organizations", "maturity"):
            assert outside not in said, finding["id"]


# ------------------------------------------------- what this surface is not

def test_it_is_not_a_project_management_tool() -> None:
    listed = " ".join(projects.NOT_THIS).lower()
    for absent in ("task list", "percentage complete", "dependency graph",
                   "scorecard"):
        assert absent in listed


def test_it_says_plainly_that_nothing_watches_your_vendors() -> None:
    said = projects.NO_VENDOR_FEED.lower()
    assert "nothing here watches your vendors" in said
    assert "no feed anywhere" in said
    assert "rather than presenting itself as complete" in said


def test_the_empty_state_does_not_ask_for_a_solution() -> None:
    said = projects.empty_state().lower()
    assert "you do not need a solution in mind" in said


def test_seeded_tools_are_not_called_a_problem() -> None:
    said = projects.empty_state(seeded=7).lower()
    assert "7 things you already have" in said
    assert "none of them is a problem" in said


def test_the_whole_surface_serialises() -> None:
    import json
    _started()
    json.dumps(projects.report())
