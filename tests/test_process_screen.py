"""The Process screen: the framework read in, the requirement rule, the
seeding offer, and who may put a procedure in force.

The register itself is pinned in test_procedures.py. These pin what the
screen needed on top of it. Every requirement comes from the organization's
own answer and nowhere else; their level names are the only ones ever shown;
seeding writes drafts and never puts anything in force; and putting a
procedure in force sits with whoever decides, or with a User only inside the
delegation the organization itself wrote down.
"""

from __future__ import annotations

import pytest

from app import module_one, procedures, server, spine
from app.authz import Actor, Role

USER = Actor("u", "Pat Lee", Role.OPERATOR, title="Clerk")
TECH = Actor("t", "Sam Roe", Role.OT, title="IT Manager")
DECIDER = Actor("c", "Jo Kim", Role.COUNCIL, title="General Manager")

ANSWERS = {
    "risk.levels": "two",
    "risk.tiers": {"routine": {"written": "A one-page note"},
                   "elevated": {"written": "A risk assessment; a named owner"}},
    "who.without": ["lowest_risk"],
    "who.shape": "one", "who.cadence": "quarterly",
    "floor.fallback_scope": "mod_high", "floor.fallback_tested": "annual",
    "floor.reach_human": "the front desk, 555-0100",
    "bad.stopper": [{"role": "IT Manager"}],
    "risk.revisit": ["vendor_change"], "watch.triggers": ["funding"],
}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(procedures, "_file", lambda: tmp_path / "p.json")
    monkeypatch.setattr(procedures, "_log", lambda *a, **k: None)
    monkeypatch.setattr(server, "_framework_answers", lambda: dict(ANSWERS))
    yield


# ---------------------------------------------------------- their own words

def test_levels_are_theirs_and_only_theirs() -> None:
    got = procedures.framework_inputs(ANSWERS)
    assert got["levels"] == ["Routine", "Elevated"]
    blob = str(procedures.surface(answers=ANSWERS)).lower()
    assert "moderate" not in blob


def test_a_four_level_organisation_sees_the_names_it_typed() -> None:
    answers = {"risk.levels": "four", "risk.tiers": {
        "t1": {"name": "Everyday"}, "t4": {"name": "Board-level"}}}
    names = [n for _, n in module_one.level_names(answers)]
    assert names[0] == "Everyday" and names[-1] == "Board-level"


def test_no_levels_before_they_choose_how_many() -> None:
    assert module_one.level_names({}) == []


def test_the_fallback_answer_renders_as_their_level_names() -> None:
    got = procedures.framework_inputs(ANSWERS)
    # Two levels, "moderate and high only": the top of two, in their word.
    assert got["fallback_levels"] == ["Elevated"]
    assert got["fallback_phrase"] == "Elevated"


def test_only_the_triggers_they_ticked_are_offered() -> None:
    got = procedures.framework_inputs(ANSWERS)["triggers"]
    assert got == ["Whenever the vendor changes the tool it covers",
                   "When its funding is not renewed"]


# ------------------------------------------------------ the requirement rule

def test_each_requirement_comes_from_an_answer() -> None:
    req = procedures.required_kinds(procedures.framework_inputs(ANSWERS))
    assert procedures.MANUAL_WAY in req and procedures.TURN_IT_OFF in req
    # 6.3b is required with no opt-out, and carries their route.
    assert "the front desk" in req[procedures.ROUTE_TO_PERSON]
    # Not asked for, so not required.
    assert procedures.TRAINING not in req and procedures.WORDING not in req
    assert procedures.ROUTE_IN not in req


def test_the_four_never_required_kinds_never_appear() -> None:
    req = procedures.required_kinds(procedures.framework_inputs(ANSWERS))
    for kind in procedures.NEVER_REQUIRED:
        assert kind not in req


def test_one_checklist_ghost_row_per_level_not_per_gate() -> None:
    ghosts = [g for g in procedures.surface(answers=ANSWERS)["ghosts"]
              if g["kind"] == procedures.CHECKLIST]
    assert [g["level"] for g in ghosts] == ["Routine", "Elevated"]
    assert "a risk assessment; a named owner has to exist before approval " \
           "at Elevated" in ghosts[1]["says"]


def test_a_checklist_at_every_gate_closes_its_level_row() -> None:
    made = procedures.write(name="Routine paper", actor=DECIDER,
                            kind=procedures.CHECKLIST,
                            gates=[procedures.EVERY_GATE], levels=["Routine"],
                            status=procedures.IN_FORCE)
    assert made["ok"]
    ghosts = [g["level"] for g in procedures.surface(answers=ANSWERS)["ghosts"]
              if g["kind"] == procedures.CHECKLIST]
    assert ghosts == ["Elevated"]


def test_the_counter_counts_ghost_rows() -> None:
    found = procedures.surface(answers=ANSWERS)
    assert found["counters"]["required_not_written"] == len(found["ghosts"])


# ------------------------------------------------------------ the seeding offer

def test_seeding_writes_drafts_and_puts_nothing_in_force() -> None:
    inputs = procedures.framework_inputs(ANSWERS)
    preview = procedures.seed_preview(inputs)
    assert [p["kind"] for p in preview].count(procedures.CHECKLIST) == 2
    procedures.seed(inputs, actor=USER)
    rows = procedures.all_procedures()
    assert len(rows) == len(preview)
    assert all(r["status"] == procedures.DRAFTED for r in rows)


def test_a_seeded_checklist_is_prefilled_from_their_paper_answer() -> None:
    procedures.seed(procedures.framework_inputs(ANSWERS), actor=USER)
    elevated = next(r for r in procedures.all_procedures()
                    if r["levels"] == ["Elevated"])
    assert [i["item"] for i in elevated["items"]] == ["A risk assessment",
                                                      "a named owner"]


def test_seeding_is_offered_only_to_an_empty_register() -> None:
    procedures.write(name="Something", actor=USER)
    assert procedures.surface(answers=ANSWERS)["seed"] == []
    assert not server.api_procedure_seed(USER, {}, {})["ok"]


# ---------------------------------------------------- who may put it in force

def _drafted(**over) -> str:
    return procedures.write(name="A procedure", actor=USER, **over)[
        "procedure"]["ref"]


def test_whoever_decides_may_put_a_procedure_in_force() -> None:
    ref = _drafted()
    assert server.api_procedure_status(
        DECIDER, {"ref": ref, "status": procedures.IN_FORCE}, {})["ok"]
    assert procedures.procedure(ref)["status"] == procedures.IN_FORCE


def test_the_technology_hat_approves_nothing_on_its_own() -> None:
    ref = _drafted(levels=["Routine"])
    out = server.api_procedure_status(
        TECH, {"ref": ref, "status": procedures.IN_FORCE}, {})
    assert not out["ok"]


def test_a_user_may_only_within_their_own_delegation() -> None:
    lowest = _drafted(levels=["Routine"])
    higher = _drafted(levels=["Elevated"])
    assert server.api_procedure_status(
        USER, {"ref": lowest, "status": procedures.IN_FORCE}, {})["ok"]
    refused = server.api_procedure_status(
        USER, {"ref": higher, "status": procedures.IN_FORCE}, {})
    assert not refused["ok"]
    assert "lowest level of scrutiny" in refused["error"]


def test_where_everything_flows_through_the_user_puts_nothing_in_force(
        monkeypatch) -> None:
    monkeypatch.setattr(server, "_framework_answers",
                        lambda: {**ANSWERS, "who.without": ["nothing"]})
    ref = _drafted(levels=["Routine"])
    assert not server.api_procedure_status(
        USER, {"ref": ref, "status": procedures.IN_FORCE}, {})["ok"]


def test_only_whoever_decides_may_withdraw() -> None:
    ref = _drafted()
    procedures.set_status(ref, procedures.IN_FORCE, actor=DECIDER)
    assert not server.api_procedure_status(
        USER, {"ref": ref, "status": procedures.WITHDRAWN}, {})["ok"]
    assert server.api_procedure_status(
        DECIDER, {"ref": ref, "status": procedures.WITHDRAWN}, {})["ok"]
    # Nothing is deleted.
    assert procedures.procedure(ref)["status"] == procedures.WITHDRAWN


# ------------------------------------------------------- the version rule

def test_saving_one_in_force_writes_a_new_version() -> None:
    ref = _drafted(covers="Only the ones I pick", covered_records=["P1"])
    procedures.set_status(ref, procedures.IN_FORCE, actor=DECIDER)
    out = server.api_procedure_save(USER, {"ref": ref, "steps": "New steps"}, {})
    assert out["new_version"] is True
    assert procedures.procedure(ref)["status"] == procedures.REPLACED


def test_records_left_on_the_old_version_are_a_finding_until_moved() -> None:
    ref = _drafted(covers="Only the ones I pick", covered_records=["P1"])
    procedures.set_status(ref, procedures.IN_FORCE, actor=DECIDER)
    procedures.save(ref, actor=USER, steps="New steps")
    ids = [f["id"] for f in procedures.surface(answers=ANSWERS)["raised"]]
    assert "finding.process.superseded_still_followed" in ids
    assert server.api_procedure_move(DECIDER, {"ref": ref}, {})["ok"]
    ids = [f["id"] for f in procedures.surface(answers=ANSWERS)["raised"]]
    assert "finding.process.superseded_still_followed" not in ids


# ------------------------------------------------ the fallback, and events

def test_a_fallback_tried_long_ago_is_named_with_its_date() -> None:
    ref = _drafted(kind=procedures.MANUAL_WAY)
    procedures.set_status(ref, procedures.IN_FORCE, actor=DECIDER)
    procedures.mark_tried(ref, actor=USER, answer=procedures.TRIED_YES,
                          on="2024-01-05")
    said = [f["says"] for f in procedures.surface(answers=ANSWERS)["raised"]
            if f["id"] == "finding.process.fallback_never_tried"]
    assert said == ["You said the backup gets tried once a year. This one was "
                    "last tried 2024-01-05."]


def test_a_fallback_that_cannot_be_tried_is_not_flagged() -> None:
    ref = _drafted(kind=procedures.MANUAL_WAY)
    procedures.set_status(ref, procedures.IN_FORCE, actor=DECIDER)
    procedures.mark_tried(ref, actor=USER, answer=procedures.TRIED_CANNOT)
    assert not any(f["id"] == "finding.process.fallback_never_tried"
                   for f in procedures.surface(answers=ANSWERS)["raised"])


def test_a_recorded_event_overtakes_a_procedure_carrying_that_trigger() -> None:
    ref = _drafted(look_again=["When its funding is not renewed"])
    procedures.set_status(ref, procedures.IN_FORCE, actor=DECIDER)
    procedures.confirm(ref, actor=USER, on="2026-01-01")
    procedures.record_event(actor=USER, trigger="When its funding is not renewed",
                            on="2026-06-01")
    check = procedures.surface(answers=ANSWERS)["standing_check"]
    assert check["overtaken"] == 1


def test_an_event_nobody_offered_is_refused() -> None:
    assert not procedures.record_event(actor=USER, trigger="The moon")["ok"]


# ------------------------------------------------------------- the routes

def test_the_routes_are_registered() -> None:
    for path in ("/api/procedures", "/api/procedures/status",
                 "/api/procedures/confirm", "/api/procedures/tried",
                 "/api/procedures/event", "/api/procedures/move",
                 "/api/procedures/seed"):
        assert ("POST", path) in server.ROUTES
    assert ("GET", "/api/process") in server.ROUTES


def test_the_process_page_no_longer_serves_another_agencys_appendices() -> None:
    blob = str(server.api_process(DECIDER, {}, {})).lower()
    for word in ("appendix", "scdes", "band"):
        assert word not in blob, word
