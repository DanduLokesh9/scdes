"""The Oversight screen: the decision record against the organization's own
answers.

These pin what the screen needed on top of the register in
test_decisions.py: the shape vocabulary (never "session" or "council" to an
organization that did not choose a body), the seven outcomes, the findings
that read their own answers, the delegation line that shows one line of
consequence instead of blocking, and the move a decision proposes — which
Projects commits or refuses, while the decision row stays either way.
"""

from __future__ import annotations

import pytest

from app import decisions, projects, server, spine
from app.authz import Actor, Role

USER = Actor("u", "Pat Lee", Role.OPERATOR, title="Clerk")
DECIDER = Actor("c", "Jo Kim", Role.COUNCIL, title="General Manager")

ANSWERS = {
    "who.shape": "one", "who.cadence": "quarterly",
    "who.without": ["lowest_risk"], "risk.levels": "two",
    "who.consulted": ["legal", "it"],
    "org.functions": {"legal": "none", "it": "dedicated"},
    "who.missing": {"legal": "outside"},
    "who.amend": "same", "who.review": "annual",
    "bad.lookback": "yes", "bad.lookback_far": "90",
    "bad.tell": ["board", "attorney"],
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "_file", lambda: tmp_path / "d.json")
    monkeypatch.setattr(decisions, "_record", lambda *a, **k: None)
    monkeypatch.setattr(projects, "_file", lambda: tmp_path / "p.json")
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    monkeypatch.setattr(server, "_framework_answers", lambda: dict(ANSWERS))
    yield


def _save(actor=DECIDER, **body):
    body.setdefault("what", "Approved the permit triage pilot")
    return server.api_decision_save(actor, body, {})


# ------------------------------------------------------ the shape vocabulary

def test_one_person_never_sees_session_or_council() -> None:
    found = decisions.surface(answers=ANSWERS)
    blob = str(found["options"]).lower()
    assert "session" not in blob and "council" not in blob
    assert [o["label"] for o in found["options"]["how_decided"]] == [
        "One person decided", "Decided under the delegation, without a meeting"]


def test_a_body_uses_its_own_name_and_the_session_string() -> None:
    answers = {**ANSWERS, "who.shape": "council", "who.tiebreak": "the Chair"}
    found = decisions.surface(answers=answers)
    labels = [o["label"] for o in found["options"]["outcomes"]]
    assert "Deferred to the next session" in labels
    how = [o["label"] for o in found["options"]["how_decided"]]
    assert "The council could not agree, so the Chair decided" in how


def test_the_seven_outcomes_are_the_specifications() -> None:
    assert len(decisions.OUTCOMES) == 7
    assert decisions.outcome_label(decisions.SENT_BACK, "one") == \
        "Sent back for more"
    assert decisions.outcome_label("", "one") == "Not decided yet"


def test_only_what_was_decided_is_required() -> None:
    assert not _save(what="  ")["ok"]
    assert _save(what="Kept the old way for now")["ok"]


# ------------------------------------------------------------- the findings

def test_an_office_they_do_not_have_is_never_asked_for() -> None:
    inputs = decisions.framework_inputs(ANSWERS)
    assert inputs["must_consult"] == ["Information technology"]
    # Where they said outside help would be needed, one line says so.
    assert inputs["consult_outside"] == ["Legal counsel"]
    # And an attorney is not listed to be told where there is no legal office.
    assert "Your attorney" not in inputs["must_tell"]


def test_an_approval_nobody_consulted_on_is_raised_after_adoption() -> None:
    _save(kind=decisions.KIND_FRAMEWORK, what="Adopted the framework",
          framework_what=decisions.FRAMEWORK_WHAT[0],
          adopted_by_title="the Board", decided_on="2026-01-01",
          effective_on="2026-01-01")
    _save(outcome=decisions.APPROVED, decided_on="2026-02-01")
    ids = [f["id"] for f in decisions.surface(answers=ANSWERS)["raised"]]
    assert "finding.consulted_missing" in ids


def test_nothing_is_raised_on_a_decision_before_the_framework_took_effect(
        ) -> None:
    _save(outcome=decisions.APPROVED, decided_on="2025-06-01")
    ids = [f["id"] for f in decisions.surface(answers=ANSWERS)["raised"]]
    assert "finding.consulted_missing" not in ids
    row = decisions.surface(answers=ANSWERS)["decisions"][0]
    assert row["before_framework"] is True


def test_an_amendment_owed_to_the_adopting_authority_is_named() -> None:
    _save(kind=decisions.KIND_FRAMEWORK, what="Adopted it",
          framework_what=decisions.FRAMEWORK_WHAT[0], decided_on="2026-01-01")
    _save(kind=decisions.KIND_FRAMEWORK, what="Changed the notice period",
          framework_what="Changing it", owed="Not yet", decided_on="2026-03-01")
    said = [f["says"] for f in decisions.surface(answers=ANSWERS)["raised"]
            if f["id"] == "finding.oversight.amendment_unapproved"]
    assert said and "same authority that adopted it" in said[0]


def test_no_amendment_finding_where_the_group_changes_it_alone() -> None:
    answers = {**ANSWERS, "who.amend": "group_alone"}
    decisions.record(about="framework", what="Adopted", actor=DECIDER,
                     decided_on="2026-01-01",
                     extra={"kind": decisions.KIND_FRAMEWORK,
                            "framework_what": decisions.FRAMEWORK_WHAT[0]})
    decisions.record(about="framework", what="Changed", actor=DECIDER,
                     decided_on="2026-02-01",
                     extra={"kind": decisions.KIND_FRAMEWORK,
                            "framework_what": "Changing it", "owed": "Not yet"})
    assert not any(f["id"] == "finding.oversight.amendment_unapproved"
                   for f in decisions.surface(answers=answers)["raised"])


def test_a_serious_problem_with_no_lookback_is_raised_by_position() -> None:
    _save(kind=decisions.KIND_FRAMEWORK, what="Adopted",
          framework_what=decisions.FRAMEWORK_WHAT[0], decided_on="2026-01-01")
    _save(kind=decisions.KIND_WENT_WRONG, what="Paused the chat tool",
          severity="Serious", decided_on="2026-02-01")
    said = [f["says"] for f in decisions.surface(answers=ANSWERS)["raised"]
            if f["id"] == "finding.oversight.lookback_not_decided"]
    assert said == ["You said you go back 90 days after a serious problem. "
                    "This decision does not say whether that was done."]


def test_a_party_that_must_be_told_and_was_not_is_named() -> None:
    _save(kind=decisions.KIND_FRAMEWORK, what="Adopted",
          framework_what=decisions.FRAMEWORK_WHAT[0], decided_on="2026-01-01")
    _save(kind=decisions.KIND_WENT_WRONG, what="Stopped it",
          severity="Minor", decided_on="2026-02-01", told=[])
    ids = [f["id"] for f in decisions.surface(answers=ANSWERS)["raised"]]
    assert "finding.oversight.notify_not_recorded" in ids


# -------------------------------------------------------- the delegation line

def test_outside_the_delegation_asks_for_a_reason_rather_than_blocking() -> None:
    ref = projects.start("Chat assistant", USER, already_running="yes")[
        "project"]["ref"]
    projects.set_level(ref, "Elevated", USER, levels=["Routine", "Elevated"])
    first = _save(USER, about=ref, outcome=decisions.APPROVED,
                  hat_worn="operator")
    assert first["ok"] is False and first["needs_reason"] is True
    assert "lowest level of scrutiny" in first["error"]
    again = _save(USER, about=ref, outcome=decisions.APPROVED,
                  hat_worn="operator",
                  anyway_reason="The manager said yes in the yard")
    assert again["ok"]


# ------------------------------------------------------------ the move proposed

def test_an_approval_proposes_the_move_and_projects_may_refuse_it() -> None:
    ref = projects.start("Permit triage", DECIDER, already_running="yes")[
        "project"]["ref"]
    out = _save(about=ref, outcome=decisions.APPROVED,
                gate=spine.IDENTIFY)
    # Nobody is named, so the spine refuses to leave Identify — and the
    # decision row stays, because the decision happened.
    assert out["ok"] and out["move"]["ok"] is False
    assert out["move"]["says"] == spine.REFUSE_IDENTIFY
    assert len(decisions.all_decisions()) == 1


def test_stopping_it_pauses_the_project() -> None:
    ref = projects.start("Permit triage", DECIDER, already_running="yes")[
        "project"]["ref"]
    out = _save(about=ref, outcome=decisions.STOPPED)
    assert out["move"]["ok"]
    assert projects.one(ref)["state"] == spine.PAUSED


def test_a_weights_decision_proposes_nothing_and_sets_the_weights() -> None:
    out = _save(kind=decisions.KIND_WEIGHTS, what="Set the weights",
                axes=[{"axis": "Cost over five years", "weight": "3",
                       "why": "It is what the board asks"}])
    assert out["ok"] and "move" not in out
    assert decisions.weights()["axes"] == {"Cost over five years": 3.0}


# ------------------------------------------------------------- conditions

def test_a_user_closes_only_conditions_they_own() -> None:
    _save(what="Approved with a fallback", outcome=decisions.APPROVED_WITH,
          conditions=[{"what": "Write the fallback", "owner": "Clerk",
                       "by": "2026-12-01"},
                      {"what": "Train staff", "owner": "IT Manager"}])
    ref = decisions.all_decisions()[0]["ref"]
    assert server.api_condition_close(USER, {"decision": ref, "index": 0},
                                      {})["ok"]
    assert not server.api_condition_close(USER, {"decision": ref,
                                                 "index": 1}, {})["ok"]
    assert server.api_condition_close(DECIDER, {"decision": ref, "index": 1},
                                      {})["ok"]
    # Nothing is removed.
    assert len(decisions.conditions()) == 2


# ------------------------------------------------------------ the adoption line

def test_the_adoption_line_names_their_title_and_their_cadence() -> None:
    _save(kind=decisions.KIND_FRAMEWORK, what="Adopted the framework",
          framework_what=decisions.FRAMEWORK_WHAT[0],
          adopted_by_title="the Board of Commissioners",
          decided_on="2026-03-14", effective_on="2026-04-01")
    line = decisions.surface(answers=ANSWERS)["adoption_line"]
    assert line.startswith("Adopted 2026-03-14 by the Board of Commissioners")


def test_before_adoption_the_line_says_nothing_binds() -> None:
    line = decisions.surface(answers=ANSWERS)["adoption_line"]
    assert line.startswith("No framework adopted yet")


# ------------------------------------------------------------------ labels

def test_labels_are_a_setting_not_a_decision() -> None:
    server.api_labels(USER, {"on": True, "labels": ["Public", "Internal"]}, {})
    assert decisions.labels() == ["Public", "Internal"]
    assert decisions.all_decisions() == []


# ------------------------------------------------------------------ routes

def test_the_old_incident_route_is_retired() -> None:
    assert ("POST", "/api/oversight/incident") not in server.ROUTES
    for path in ("/api/decisions", "/api/decisions/condition/close",
                 "/api/decisions/labels"):
        assert ("POST", path) in server.ROUTES


def test_the_page_serves_no_other_agencys_incident_levels() -> None:
    blob = str(server.api_oversight(DECIDER, {}, {})).lower()
    for word in ("level 2", "scdes", "monitoring register"):
        assert word not in blob, word
