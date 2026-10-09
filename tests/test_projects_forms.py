"""The forms that move a project — and the one that makes moving possible.

Before these existed nothing could leave Identify. The spine refuses that
passage unless a role is named against the project and Floor 7 is satisfied;
the record had fields for both and no way to write either. So the one rule
Identify enforces could never be met from any screen.

These pin the fix and the rules it keeps: naming somebody is what lets a
project leave Identify, and nothing else is; an obligation is met by
pointing at something, never by saying yes; a level is one of the
organization's own; and nobody marks a project Retired from a menu.
"""

from __future__ import annotations

import pytest

from app import projects, server, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    path = tmp_path / "projects.json"
    monkeypatch.setattr(projects, "_file", lambda: path)
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    yield


def _started(name: str = "Permit triage") -> str:
    made = projects.start(name, WHO, already_running="yes")
    assert made["ok"], made
    return made["project"]["ref"]


# ---------------------------------------------------- leaving Identify

def test_nothing_leaves_identify_with_nobody_named() -> None:
    ref = _started()
    refused = projects.move(ref, spine.PROCURE, WHO)
    assert refused["ok"] is False
    assert refused["error"] == spine.REFUSE_IDENTIFY


def test_naming_who_is_accountable_lets_it_leave_identify() -> None:
    """The fix. Before it, this passage was impossible from any screen."""
    ref = _started()
    assert projects.name_accountable(ref, "General Manager", WHO)["ok"]
    moved = projects.move(ref, spine.PROCURE, WHO)
    assert moved["ok"], moved
    assert moved["project"]["gate"] == spine.PROCURE


def test_naming_them_is_what_the_record_points_at() -> None:
    ref = _started()
    projects.name_accountable(ref, "General Manager", WHO, person="Pat Lee")
    held = projects.one(ref)
    assert "floor.somebody_named" in held["satisfied"]
    assert "General Manager" in held["evidence"]["floor.somebody_named"]["points_at"]
    assert held["accountable_person"] == "Pat Lee"


def test_a_role_is_required_a_person_is_not() -> None:
    ref = _started()
    assert not projects.name_accountable(ref, "   ", WHO)["ok"]
    assert projects.name_accountable(ref, "Clerk", WHO)["ok"]


# ------------------------------------------------- pointing at something

def test_an_obligation_is_met_by_pointing_at_something() -> None:
    ref = _started()
    got = projects.point_at(ref, "floor.turn_it_off",
                            "Procedure PR-4F2K9M, turning off the permit "
                            "assistant", WHO)
    assert got["ok"]
    held = projects.one(ref)
    assert "floor.turn_it_off" in held["satisfied"]
    assert held["evidence"]["floor.turn_it_off"]["points_at"].startswith(
        "Procedure PR-4F2K9M")


@pytest.mark.parametrize("assertion", ["yes", "Yes.", "done", "OK", "n/a", ""])
def test_saying_yes_is_not_pointing_at_anything(assertion) -> None:
    ref = _started()
    refused = projects.point_at(ref, "floor.turn_it_off", assertion, WHO)
    assert refused["ok"] is False
    assert "floor.turn_it_off" not in projects.one(ref)["satisfied"]


def test_only_real_floor_obligations_can_be_pointed_at() -> None:
    ref = _started()
    assert not projects.point_at(ref, "floor.made_up",
                                 "Some document somewhere", WHO)["ok"]


def test_deploy_still_refuses_until_all_six_are_pointed_at() -> None:
    ref = _started()
    projects.name_accountable(ref, "General Manager", WHO)
    for gate in (spine.PROCURE, spine.TEST, spine.DEPLOY):
        assert projects.move(ref, gate, WHO)["ok"]
    refused = projects.move(ref, spine.MEASURE, WHO)
    assert refused["error"] == spine.REFUSE_DEPLOY
    for floor in spine.binding(spine.DEPLOY, spine.SATISFIED):
        projects.point_at(ref, floor, f"The document that meets {floor}", WHO)
    assert projects.move(ref, spine.MEASURE, WHO)["ok"]


# --------------------------------------------- what the tracker says is passed

def _gate(project: dict, gate: str) -> dict:
    return next(g for g in projects.tracker(project)["gates"]
                if g["id"] == gate)


def test_passing_identify_marks_identify_passed_not_procure() -> None:
    """The date was filed under the gate a passage arrived at, so passing
    Identify stamped Procure — hidden under "here now" — and Identify read
    "not yet" for ever. No gate on any tracker ever showed as passed."""
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    projects.move(ref, spine.PROCURE, WHO)
    held = projects.one(ref)
    assert _gate(held, spine.IDENTIFY)["passed_on"]
    assert _gate(held, spine.PROCURE)["current"] is True
    assert _gate(held, spine.PROCURE)["passed_on"] == ""


def test_moving_back_takes_the_later_gates_out_of_passed() -> None:
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    for gate in (spine.PROCURE, spine.TEST, spine.DEPLOY):
        projects.move(ref, gate, WHO)
    projects.move(ref, spine.TEST, WHO)                    # evidence failed
    held = projects.one(ref)
    assert _gate(held, spine.PROCURE)["passed_on"]
    assert _gate(held, spine.TEST)["current"] is True
    assert _gate(held, spine.DEPLOY)["passed_on"] == ""


def test_recorded_after_the_fact_belongs_to_the_gate_that_was_left() -> None:
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    projects.move(ref, spine.PROCURE, WHO, happened="2025-11-04")
    held = projects.one(ref)
    assert _gate(held, spine.IDENTIFY)["recorded_after_the_fact"] is True
    assert _gate(held, spine.PROCURE)["recorded_after_the_fact"] is False


# ------------------------------------- leaving Deploy without passing it

def test_a_tool_that_failed_its_launch_checks_can_go_back_to_test() -> None:
    """The spine's own reason for the move: Deploy to Test where evidence
    failed. It was refused with "cannot be recorded as past Deploy"."""
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    for gate in (spine.PROCURE, spine.TEST, spine.DEPLOY):
        projects.move(ref, gate, WHO)
    assert projects.move(ref, spine.TEST, WHO)["ok"]


def test_a_tool_that_failed_its_launch_checks_can_be_retired() -> None:
    """Otherwise it is held at Deploy with no way to switch it off."""
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    for gate in (spine.PROCURE, spine.TEST, spine.DEPLOY):
        projects.move(ref, gate, WHO)
    assert projects.move(ref, spine.SUNSET, WHO)["ok"]


def test_passing_deploy_still_needs_all_six() -> None:
    """The refusal itself is untouched — only its reach is corrected."""
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    for gate in (spine.PROCURE, spine.TEST, spine.DEPLOY):
        projects.move(ref, gate, WHO)
    assert projects.move(ref, spine.MEASURE, WHO)["error"] == \
        spine.REFUSE_DEPLOY


# ---------------------------------------------------------- the level

def test_a_level_is_one_of_their_own() -> None:
    ref = _started()
    assert projects.set_level(ref, "elevated", WHO,
                              levels=["routine", "elevated"])["ok"]
    assert projects.one(ref)["level"] == "elevated"
    refused = projects.set_level(ref, "high", WHO,
                                 levels=["routine", "elevated"])
    assert refused["ok"] is False and "routine, elevated" in refused["error"]


def test_no_levels_are_offered_before_the_framework_sets_them() -> None:
    ref = _started()
    refused = projects.set_level(ref, "Low", WHO, levels=[])
    assert refused["ok"] is False
    assert "has not set its levels" in refused["error"]


# ---------------------------------------------------- what the screen offers

def test_the_screen_is_offered_only_the_spines_moves() -> None:
    ref = _started()
    options = projects.passage_options(projects.one(ref))
    assert [m["id"] for m in options["moves"]] == \
        list(spine.legal_moves(spine.IDENTIFY, spine.PROPOSED))
    for move in options["moves"]:
        assert move["name"] == spine.BY_GATE[move["id"]].name


def test_the_screen_is_told_what_binds_and_whether_it_refuses() -> None:
    ref = _started()
    projects.name_accountable(ref, "Clerk", WHO)
    for gate in (spine.PROCURE, spine.TEST, spine.DEPLOY):
        projects.move(ref, gate, WHO)
    binds = projects.passage_options(projects.one(ref))["binds"]
    assert len(binds) == 6
    assert all(b["refuses"] for b in binds)
    named = next(b for b in binds if b["id"] == "floor.somebody_named")
    assert named["satisfied"] is True


def test_a_stopped_project_offers_the_way_back_not_a_move() -> None:
    ref = _started()
    projects.set_state(ref, spine.PAUSED, WHO)
    options = projects.passage_options(projects.one(ref))
    assert options["stopped"] is True
    assert options["moves"] == []
    assert options["restart"] == spine.START_AGAIN


# ------------------------------------------------------- the endpoints

def test_retired_cannot_be_set_from_the_screen() -> None:
    """Retirement goes through Sunset and its record. A menu item that set
    it would skip both."""
    ref = _started()
    refused = server.api_project_state(WHO, {"ref": ref,
                                             "to": spine.RETIRED}, {})
    assert refused["ok"] is False
    assert projects.one(ref)["state"] == spine.PROPOSED


def test_cleared_cannot_be_set_from_the_screen_either() -> None:
    ref = _started()
    assert not server.api_project_state(WHO, {"ref": ref,
                                              "to": spine.CLEARED}, {})["ok"]


def test_waiting_on_somebody_needs_the_somebody() -> None:
    ref = _started()
    assert not server.api_project_state(
        WHO, {"ref": ref, "to": spine.WAITING_PERSON}, {})["ok"]
    assert server.api_project_state(
        WHO, {"ref": ref, "to": spine.WAITING_PERSON,
              "waiting_for": "the Clerk"}, {})["ok"]


def test_a_pause_can_be_reversed_through_the_endpoint() -> None:
    ref = _started()
    projects.set_state(ref, spine.WAITING_DECISION, WHO)
    projects.set_state(ref, spine.PAUSED, WHO)
    back = server.api_project_restart(WHO, {"ref": ref,
                                            "how": spine.START_AGAIN}, {})
    assert back["ok"]
    assert projects.one(ref)["state"] == spine.WAITING_DECISION


def test_levels_are_not_offered_while_the_framework_is_unanswered(
        monkeypatch) -> None:
    monkeypatch.setattr(server, "_framework_answers", lambda: {})
    assert server._their_levels() == []


def test_levels_are_their_own_once_answered(monkeypatch) -> None:
    monkeypatch.setattr(server, "_framework_answers",
                        lambda: {"risk.levels": "two"})
    assert server._their_levels() == ["Routine", "Elevated"]


def test_the_routes_are_registered() -> None:
    for path, fn in (("/api/projects/accountable", server.api_project_accountable),
                     ("/api/projects/point", server.api_project_point),
                     ("/api/projects/level", server.api_project_level),
                     ("/api/projects/restart", server.api_project_restart)):
        assert server.ROUTES[("POST", path)] is fn
