"""The Vision screen: goals, the portfolio under each, and who may change
what a goal says.

The register is pinned in test_goals.py. These pin what the screen needed:
a goal's wording, horizon and standing are whoever decides' to change, and
anyone else's change is recorded as a proposal rather than dropped; the tie
between a project and a goal is written on the project and nowhere else;
the public view is set by whoever decides; and a planning document can be
read to offer goals without anything being stored from it.
"""

from __future__ import annotations

import base64

import pytest

from app import goals, projects, server
from app.authz import Actor, Role

USER = Actor("u", "Pat Lee", Role.OPERATOR, title="Clerk")
DECIDER = Actor("c", "Jo Kim", Role.COUNCIL, title="General Manager")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(goals, "_file", lambda: tmp_path / "g.json")
    monkeypatch.setattr(goals, "_log", lambda *a, **k: None)
    monkeypatch.setattr(projects, "_file", lambda: tmp_path / "p.json")
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    monkeypatch.setattr(server, "_framework_answers",
                        lambda: {"floor.optional": ["mission"],
                                 "watch.publish": ["annual_report"]})
    yield


def _goal(actor=USER, **body):
    body.setdefault("goal", "Permits decided within the time we publish")
    return server.api_goal_save(actor, body, {})


def test_anybody_may_write_a_goal_and_only_the_goal_is_required() -> None:
    assert not _goal(goal=" ")["ok"]
    assert _goal()["ok"]


def test_a_users_rewording_is_recorded_as_a_proposal_not_dropped() -> None:
    ref = _goal()["goal"]["ref"]
    out = server.api_goal_save(USER, {"ref": ref, "goal": "Faster permits",
                                      "would_be_true": "Under ten days"}, {})
    assert out["ok"] and out["proposed"]
    held = goals.goal(ref)
    assert held["goal"] == "Permits decided within the time we publish"
    assert held["would_be_true"] == "Under ten days"
    assert goals.proposals()[0]["goal"] == "Faster permits"


def test_whoever_decides_settles_a_proposal() -> None:
    ref = _goal()["goal"]["ref"]
    server.api_goal_save(USER, {"ref": ref, "stands": goals.REACHED}, {})
    assert not server.api_goal_settle(USER, {"index": 0, "accept": True},
                                      {})["ok"]
    assert server.api_goal_settle(DECIDER, {"index": 0, "accept": True},
                                  {})["ok"]
    assert goals.goal(ref)["stands"] == goals.REACHED
    assert goals.proposals() == []


def test_whoever_decides_changes_the_wording_directly() -> None:
    ref = _goal()["goal"]["ref"]
    out = server.api_goal_save(DECIDER, {"ref": ref, "goal": "Faster permits",
                                         "horizon": goals.WITHIN_FIVE}, {})
    assert out["ok"]
    assert goals.goal(ref)["goal"] == "Faster permits"
    assert goals.goal(ref)["horizon"] == goals.WITHIN_FIVE


def test_the_tie_is_written_on_the_project() -> None:
    ref = _goal()["goal"]["ref"]
    p = projects.start("Permit triage", USER, already_running="yes")[
        "project"]["ref"]
    assert server.api_project_goal(USER, {"ref": p, "goal": ref}, {})["ok"]
    assert projects.one(p)["goal"] == ref
    assert "goal" not in goals.goal(ref) or goals.goal(ref)["goal"] != p


def test_a_project_naming_no_goal_is_named_where_they_required_a_tie() -> None:
    _goal()
    projects.start("Permit triage", USER, already_running="yes")
    ids = [f["id"] for f in server.api_goals(USER, {}, {})["raised"]]
    assert "finding.vs.no_goal_named" in ids


def test_what_appears_publicly_is_set_by_whoever_decides() -> None:
    assert not server.api_goal_public(USER, {"publishes": "Yes"}, {})["ok"]
    out = server.api_goal_public(DECIDER, {"publishes": "Yes",
                                           "appears": ["The goal", "Nope"]}, {})
    assert out["ok"] and out["published"]["appears"] == ["The goal"]


def test_a_planning_document_offers_goals_and_stores_nothing() -> None:
    text = ("Our mission is to serve every resident well.\n\n"
            "Goal: by 2027 we will decide every permit within twenty days.\n\n"
            "The weather was fine.")
    out = server.api_goal_read(USER, {
        "filename": "plan.txt",
        "content": base64.b64encode(text.encode()).decode()}, {})
    assert out["ok"]
    said = [c["goal"] for c in out["candidates"]]
    assert any("twenty days" in s for s in said)
    assert not any("weather" in s for s in said)
    assert goals.all_goals() == []


def test_an_unreadable_file_type_is_refused() -> None:
    out = server.api_goal_read(USER, {"filename": "plan.exe",
                                      "content": "AAAA"}, {})
    assert not out["ok"]


def test_the_page_serves_no_other_agencys_pillars() -> None:
    blob = str(server.api_goals(USER, {}, {})).lower()
    for word in ("pillar", "maturity", "scdes", "category 1"):
        assert word not in blob, word


def test_the_routes_are_registered() -> None:
    assert ("GET", "/api/goals") in server.ROUTES
    for path in ("/api/goals", "/api/goals/settle", "/api/goals/public",
                 "/api/goals/read", "/api/projects/goal"):
        assert ("POST", path) in server.ROUTES
