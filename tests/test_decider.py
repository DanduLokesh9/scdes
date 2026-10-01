"""Who decides — and what the application does with the answer.

The rule being defended here is the client's, stated plainly: the deciding body
is something an agency *creates while writing its framework*, not something the
software presumes. Some units will stand up a council. Others will have the CTO
make the calls and report out, and will never convene anything.

So the tests that matter most are the ones asserting the application says
nothing about a council to an agency that did not create one.
"""

from __future__ import annotations

import json

import pytest

from app import decider
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")
OPERATOR = Actor("liz.operator", "Operator", Role.OPERATOR)
COUNCIL = Actor("council.cto", "Council member", Role.COUNCIL)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never write the real answer, and never inherit a cached one."""
    monkeypatch.setattr(decider, "DECIDER_FILE", tmp_path / "decider.json")
    decider.invalidate()
    yield
    decider.invalidate()


@pytest.fixture
def unanswered(monkeypatch):
    """An agency with no corpus and no answer — the hardest case to get right."""
    monkeypatch.setattr(decider, "derive_from_corpus",
                        lambda: decider.Decider(shape=decider.UNSET))
    decider.invalidate()


# ------------------------------------------------------------ the two answers

def test_one_person_can_be_the_decider(unanswered) -> None:
    """The whole point: a unit with no staff for a council is not blocked."""
    result = decider.answer(decider.INDIVIDUAL, OT,
                            noun="Chief Technology Officer",
                            report_out="the agency director, monthly")
    assert result["ok"], result.get("error")
    d = decider.current()
    assert d.shape == decider.INDIVIDUAL
    assert d.confirmed


def test_a_group_can_be_the_decider(unanswered) -> None:
    result = decider.answer(decider.GROUP, OT, noun="Council", quorum=3)
    assert result["ok"], result.get("error")
    assert decider.current().is_group
    assert decider.quorum() == 3


@pytest.mark.parametrize("shape,noun,because", [
    ("group", "", "a body has to be called something"),
    ("individual", "", "a role has to be named"),
    ("committee", "Whatever", "not one of the two shapes"),
    ("", "Council", "no shape at all"),
])
def test_incomplete_answers_are_refused(unanswered, shape, noun, because) -> None:
    result = decider.answer(shape, OT, noun=noun)
    assert not result["ok"], f"should have been refused: {because}"
    assert result["error"]


def test_a_group_of_one_is_refused_and_points_at_the_other_answer(
        unanswered) -> None:
    """"Council with a quorum of 1" is the single-decider answer, badly spelled."""
    result = decider.answer(decider.GROUP, OT, noun="Council", quorum=1)
    assert not result["ok"]
    assert "one person decides" in result["error"].lower()


# -------------------------------------------------- nothing is presumed first

def test_before_anyone_answers_the_app_names_no_body(unanswered) -> None:
    d = decider.current()
    assert not d.decided
    assert not d.confirmed
    assert "council" not in d.body.lower(), (
        "an agency that has not chosen must not be told it has a council")
    assert "council" not in d.rail_label.lower()
    assert d.levels() == {}, "no decision levels exist until a decider does"


def test_the_unanswered_state_says_what_is_missing(unanswered) -> None:
    text = decider.current().sentence().lower()
    assert "nobody has been named" in text
    assert "nowhere to go" in text


# ------------------------------------------- the consequences of the answer

def test_a_single_decider_is_never_told_about_councils_or_quorums() -> None:
    """The regression this whole module exists to prevent."""
    decider.answer(decider.INDIVIDUAL, OT, noun="Chief Technology Officer")
    d = decider.current()

    surfaces = [d.rail_label, d.body, d.possessive, d.capacity_label,
                d.sentence(), *d.levels().values()]
    for text in surfaces:
        low = text.lower()
        assert "council" not in low, f"still says council: {text!r}"
        assert "quorum" not in low, f"still asks for a quorum: {text!r}"
        assert "convene" not in low, f"still convenes a session: {text!r}"

    assert decider.quorum() == 1, "there is nobody to reach a quorum with"
    assert d.rail_label == "Decisions"
    assert d.body == "the Chief Technology Officer"


def test_a_single_decider_has_exactly_one_decision_level() -> None:
    """72-hour concurrence needs someone to concur; a convened session needs a
    session. Neither exists, so neither is offered."""
    decider.answer(decider.INDIVIDUAL, OT, noun="Chief Technology Officer")
    assert list(decider.levels()) == ["a"]
    for band in ("low", "moderate", "high"):
        assert decider.level_for_band(band) == "a", (
            "risk cannot summon a body that does not exist")


def test_a_group_keeps_all_three_levels_graded_by_risk() -> None:
    decider.answer(decider.GROUP, OT, noun="Council", quorum=3)
    assert sorted(decider.levels()) == ["a", "b", "c"]
    assert decider.level_for_band("low") == "a"
    assert decider.level_for_band("moderate") == "b"
    assert decider.level_for_band("high") == "c"


def test_the_room_is_named_whatever_the_agency_named_it() -> None:
    decider.answer(decider.GROUP, OT, noun="AI Steering Board", quorum=4)
    d = decider.current()
    assert d.rail_label == "AI Steering Board"
    assert d.body == "the AI Steering Board"
    assert d.capacity_label == "AI Steering Board member"
    assert "AI Steering Board" in d.levels()["c"]


def test_reporting_out_is_recorded_and_shown() -> None:
    """"Make the calls and report out" — the reporting is half the arrangement."""
    decider.answer(decider.INDIVIDUAL, OT, noun="Chief Technology Officer",
                   report_out="the County Administrator, quarterly")
    assert "County Administrator" in decider.levels()["a"]
    assert "County Administrator" in decider.current().sentence()


# ------------------------------------------------------------- who may answer

def test_setting_it_the_first_time_belongs_to_ot(unanswered) -> None:
    """Requiring the decider's approval to appoint the first decider is a loop
    with no entrance."""
    assert decider.answer(decider.GROUP, OT, noun="Council")["ok"]


def test_an_operator_cannot_appoint_the_decider(unanswered) -> None:
    result = decider.answer(decider.GROUP, OPERATOR, noun="Council")
    assert not result["ok"]


def test_changing_an_answered_question_is_an_amendment() -> None:
    """Reassigning the authority the whole app defers to is not a settings tweak."""
    assert decider.answer(decider.GROUP, OT, noun="Council", quorum=3)["ok"]

    blocked = decider.answer(decider.INDIVIDUAL, OT, noun="CTO")
    assert not blocked["ok"], "OT must not quietly dissolve the council"
    assert blocked.get("requires_council")
    assert decider.current().is_group, "the refused change must not have applied"

    allowed = decider.answer(decider.INDIVIDUAL, COUNCIL, noun="CTO")
    assert allowed["ok"]
    assert decider.current().shape == decider.INDIVIDUAL


# ------------------------------------------------------------------- honesty

def test_a_derived_proposal_is_not_an_answer() -> None:
    """SCDES really does have a council, and the corpus shows it. That still is
    not the same as a person having said so."""
    derived = decider.derive_from_corpus()
    assert not derived.confirmed
    if derived.decided:
        assert derived.evidence, "a proposal must say what it was based on"


def test_the_scdes_corpus_proposes_its_council_with_evidence() -> None:
    derived = decider.derive_from_corpus()
    assert derived.shape == decider.GROUP, (
        "a signed charter is direct evidence a body was stood up")
    assert "charter" in derived.evidence.lower()


def test_the_answer_records_who_gave_it(unanswered) -> None:
    decider.answer(decider.INDIVIDUAL, OT, noun="Chief Technology Officer")
    d = decider.current()
    assert d.answered_by == "Office of Technology"
    assert d.answered_title == "CTO"
    assert d.answered_on


def test_the_answer_survives_a_restart(unanswered) -> None:
    decider.answer(decider.INDIVIDUAL, OT, noun="Chief Technology Officer")
    decider.invalidate()
    assert decider.current().noun == "Chief Technology Officer"
    saved = json.loads(decider.DECIDER_FILE.read_text(encoding="utf-8"))
    assert saved["shape"] == "individual"


def test_the_state_payload_tells_a_screen_what_the_change_affects() -> None:
    s = decider.state()
    assert s["question"]
    assert len(s["affects"]) >= 3
    assert {sh["key"] for sh in s["shapes"]} == {"group", "individual"}


# ---------------------------------------------- the answer reaches every screen
#
# decider.py getting this right is worth nothing if the modules that write the
# user-facing sentences carry their own hardcoded copy of SCDES's answer — which
# is exactly what they did. These assert the wording travels.

def _fresh():
    """Back to unanswered.

    Needed because switching shape once one is on record is an amendment, not a
    setting — these helpers each stand in for a different agency, not for one
    agency changing its mind. That the naive version of this failed is the rule
    in test_changing_an_answered_question_is_an_amendment doing its job.
    """
    if decider.DECIDER_FILE.exists():
        decider.DECIDER_FILE.unlink()
    decider.invalidate()


def _as_individual():
    _fresh()
    r = decider.answer(decider.INDIVIDUAL, OT, noun="Chief Technology Officer",
                       report_out="the County Administrator")
    assert r["ok"], r.get("error")


def _as_group(noun="Council", quorum=3):
    _fresh()
    r = decider.answer(decider.GROUP, OT, noun=noun, quorum=quorum)
    assert r["ok"], r.get("error")


def test_the_approval_path_names_the_decider_not_a_council() -> None:
    from app import scoring
    _as_individual()
    for band in ("Low", "Moderate", "High"):
        text = scoring.approval_for(band)
        assert "council" not in text.lower(), f"{band}: {text!r}"
    assert "Chief Technology Officer" in scoring.approval_for("Moderate")

    _as_group("AI Steering Board")
    assert "AI Steering Board" in scoring.approval_for("High")


def test_the_decision_levels_offered_match_the_shape() -> None:
    from app import council
    _as_individual()
    rules = council.tier_rules()
    assert list(rules) == ["A"], "one decider cannot concur or convene"
    assert "council" not in rules["A"].lower()
    assert "County Administrator" in rules["A"], "report-out is part of the rule"

    _as_group()
    assert sorted(council.tier_rules()) == ["A", "B", "C"]


def test_every_gate_decision_stays_with_a_single_decider() -> None:
    from app import council
    _as_individual()
    for band in ("Low", "Moderate", "High"):
        assert council.tier_for_band(band) == "A"
    assert council.quorum() == 1

    _as_group("Council", quorum=4)
    assert council.tier_for_band("High") == "C"


def test_a_single_decider_is_their_own_quorum_for_a_convened_session() -> None:
    """Tier C's quorum check must not strand the only person who can decide."""
    from app import council
    _as_individual()
    # There is no Tier C to reach under this shape, but the guard behind it must
    # still be satisfiable rather than permanently unmeetable.
    assert council.quorum() == 1


def test_the_sign_in_capacity_is_named_by_the_answer() -> None:
    from app import server
    _as_individual()
    labels = {c["label"] for c in server.capacities()}
    assert "Chief Technology Officer" in labels
    assert "Council member" not in labels

    _as_group("Board")
    assert "Board member" in {c["label"] for c in server.capacities()}


def test_the_framework_builder_asks_the_question_rather_than_naming_a_room() -> None:
    from app import framework
    screens = {d["screen"]: d["needs"] for d in framework.DEPENDENTS}
    assert "Council" not in screens, (
        "the framework cannot depend on a room the framework creates")
    assert "Decisions" in screens
    assert "who decides" in screens["Decisions"].lower()


def test_a_job_title_is_not_mangled_by_sentence_casing() -> None:
    """`.capitalize()` lower-cased the rest and printed "The chief technology
    officer" — a real person's job title, rendered wrong on every gate."""
    _as_individual()
    assert "Chief Technology Officer" in decider.levels()["a"]
