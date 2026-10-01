"""The Budget screen: cost lines against the organization's own answers.

The arithmetic is pinned in test_costs.py. These pin what the screen needed
on top: only the first line is required; committing is its own act, stamped
once, never undone, and inside the organization's own delegation for a User;
an amount somebody committed to is superseded rather than edited; the
findings read the organization's own list of what counts as cost; and a
whole kind can be recorded as unknown, with an owner.
"""

from __future__ import annotations

import pytest

from app import costs, projects, server, spine
from app.authz import Actor, Role

USER = Actor("u", "Pat Lee", Role.OPERATOR, title="Clerk")
TECH = Actor("t", "Sam Roe", Role.OT, title="IT Manager")
DECIDER = Actor("c", "Jo Kim", Role.COUNCIL, title="General Manager")

ANSWERS = {"proc.full_cost": "yes",
           "proc.cost_parts": ["licence", "training", "exit"],
           "floor.optional": ["lifetime", "roi"],
           "floor.named": ["budget"],
           "who.without": {"value": ["under_amount"], "amount": "5000"}}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(costs, "_file", lambda: tmp_path / "c.json")
    monkeypatch.setattr(costs, "_record", lambda *a, **k: None)
    monkeypatch.setattr(projects, "_file", lambda: tmp_path / "p.json")
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    monkeypatch.setattr(server, "_framework_answers", lambda: dict(ANSWERS))
    yield


def _save(actor=USER, **body):
    body.setdefault("what_for", "The annual license")
    return server.api_cost_save(actor, body, {})


def _project(gate=spine.PROCURE, **over):
    ref = projects.start("Permit triage", DECIDER, already_running="yes")[
        "project"]["ref"]
    held = projects._read()
    held["projects"][ref].update({"gate": gate, **over})
    projects._write(held)
    return ref


# ---------------------------------------------------------------- the form

def test_only_the_first_line_is_required() -> None:
    assert not _save(what_for=" ")["ok"]
    out = _save()
    assert out["ok"] and out["line"]["status"] == costs.OPEN
    assert out["line"]["committed"] is False


def test_a_typed_amount_that_is_not_a_number_is_refused_in_place() -> None:
    out = _save(estimate="about twelve hundred")
    assert out["ok"] is False and out["field"] == "estimate"


def test_a_shared_line_is_listed_under_both_projects_and_counted_once() -> None:
    a, b = _project(), _project()
    _save(projects=[a, b], kind="licence", basis="year", estimate="1200")
    found = costs.surface(answers=ANSWERS, projects=projects.all_projects())
    assert sum(1 for g in found["groups"] if g["lines"]) == 2
    assert found["money"]["everything"]["a_year"] == 1200


# ---------------------------------------------------------- committing

def test_the_add_form_commits_nothing_and_committing_is_stamped() -> None:
    ref = _save(kind="licence", basis="year", estimate="1200")["line"]["ref"]
    out = server.api_cost_commit(DECIDER, {"ref": ref}, {})
    line = out["line"]
    assert line["committed"] and line["committed_on"]
    assert line["committed_by_hat"] == "council-member"
    assert line["committed_by_person"] == "Jo Kim"
    # Uncommitting is not offered.
    assert not costs.commit(ref, DECIDER)["ok"]


def test_the_technology_hat_commits_no_money() -> None:
    ref = _save(basis="year", estimate="100")["line"]["ref"]
    assert not server.api_cost_commit(TECH, {"ref": ref}, {})["ok"]


def test_a_user_commits_within_their_own_amount_and_not_above_it() -> None:
    p = _project()
    small = _save(projects=[p], basis="year", estimate="3000")["line"]["ref"]
    assert server.api_cost_commit(USER, {"ref": small}, {})["ok"]
    big = _save(projects=[p], basis="year", estimate="2500")["line"]["ref"]
    refused = server.api_cost_commit(USER, {"ref": big}, {})
    assert not refused["ok"]
    # The committed total on the project, not the single line.
    assert "$5,500" in refused["error"] and "$5,000" in refused["error"]


def test_a_committed_amount_is_superseded_not_edited() -> None:
    ref = _save(basis="year", estimate="1000")["line"]["ref"]
    server.api_cost_commit(DECIDER, {"ref": ref}, {})
    assert not _save(ref=ref, estimate="1500")["ok"]
    newer = _save(what_for="The license, corrected", basis="year",
                  estimate="1500", supersedes=ref)["line"]
    old = next(l for l in costs.all_lines() if l["ref"] == ref)
    assert old["status"] == costs.SUPERSEDED
    assert old["superseded_by"] == newer["ref"]
    assert costs.counters()["recorded"] == 2


def test_a_user_withdraws_only_their_own_uncommitted_line() -> None:
    mine = _save()["line"]["ref"]
    theirs = _save(DECIDER)["line"]["ref"]
    assert server.api_cost_status(USER, {"ref": mine,
                                         "status": costs.WITHDRAWN}, {})["ok"]
    assert not server.api_cost_status(USER, {"ref": theirs,
                                             "status": costs.WITHDRAWN}, {})["ok"]
    assert server.api_cost_status(DECIDER, {"ref": theirs,
                                            "status": costs.WITHDRAWN}, {})["ok"]


# ------------------------------------------------------------- findings

def test_kinds_they_said_count_and_nothing_records_are_named() -> None:
    p = _project()
    _save(projects=[p], kind="licence", basis="year", estimate="1200",
          owner="Clerk")
    said = [f["says"] for f in costs.surface(
        answers=ANSWERS, projects=projects.all_projects())["raised"]
        if f["id"] == "finding.budget.not_estimated"]
    assert said == ["You said the full cost has to be estimated before you "
                    "commit. Nothing is recorded here for: training staff, "
                    "what it costs to leave."]


def test_a_recorded_gap_answers_a_kind() -> None:
    p = _project()
    _save(projects=[p], kind="licence", basis="year", estimate="1200")
    costs.record_kind_gap(p, "training", USER, owner="Clerk")
    costs.record_kind_gap(p, "exit", USER, owner="Clerk")
    ids = [f["id"] for f in costs.surface(
        answers=ANSWERS, projects=projects.all_projects())["raised"]]
    assert "finding.budget.not_estimated" not in ids
    assert "finding.budget.exit_cost_missing" not in ids


def test_money_with_nobody_named_against_it_where_a_contact_is_required() -> None:
    p = _project()
    _save(projects=[p], kind="licence", basis="year", estimate="100")
    ids = [f["id"] for f in costs.surface(
        answers=ANSWERS, projects=projects.all_projects())["raised"]]
    assert "finding.budget.no_budget_contact" in ids


def test_nothing_is_flagged_for_incompleteness_where_they_said_it_need_not_be(
        ) -> None:
    answers = {**ANSWERS, "proc.full_cost": "no", "proc.cost_parts": []}
    p = _project()
    _save(projects=[p], kind="licence", basis="year", estimate="100",
          owner="Clerk")
    found = costs.surface(answers=answers, projects=projects.all_projects())
    assert not any(f["id"] == "finding.budget.not_estimated"
                   for f in found["raised"])
    assert "Nothing here will be flagged" in found["copy"]["not_required"]


def test_over_estimate_waits_for_their_own_difference_setting() -> None:
    _save(basis="year", estimate="1000", actual="1100")
    ids = [f["id"] for f in costs.surface(answers=ANSWERS)["raised"]]
    assert "finding.budget.over_estimate" not in ids
    costs.set_difference("More than an amount", 50, DECIDER)
    ids = [f["id"] for f in costs.surface(answers=ANSWERS)["raised"]]
    assert "finding.budget.over_estimate" in ids


def test_only_whoever_decides_sets_the_difference() -> None:
    assert not server.api_cost_difference(USER, {"mode": "Any difference at all"},
                                          {})["ok"]
    assert server.api_cost_difference(DECIDER, {"mode": "Any difference at all"},
                                      {})["ok"]


# ------------------------------------------------------------ comparison

def test_the_five_estimate_counts_add_up_to_every_open_line() -> None:
    _save(basis="year", estimate="100", actual="100")
    _save(basis="year", estimate="100", actual="150")
    _save(basis="year", estimate="100")
    _save(basis="year", actual="100")
    _save(basis="by_use", estimate="100")
    counts = [n for n, _ in costs.comparison()["estimate_actual"]]
    assert counts == [1, 1, 1, 1, 1]
    assert sum(counts) == len(costs.open_lines())


# --------------------------------------------------------------- routes

def test_the_routes_are_registered() -> None:
    assert ("GET", "/api/costs") in server.ROUTES
    for path in ("/api/costs", "/api/costs/commit", "/api/costs/status",
                 "/api/costs/gap", "/api/costs/difference"):
        assert ("POST", path) in server.ROUTES


def test_the_page_serves_no_other_agencys_budget_pools() -> None:
    blob = str(server.api_costs(DECIDER, {}, {})).lower()
    for word in ("pool", "scdes", "foundation"):
        assert word not in blob, word
