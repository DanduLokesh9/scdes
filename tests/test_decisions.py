"""Oversight — the only surface where authority is recorded.

Two things dominate these tests.

**The four shapes.** An organization that chose one accountable person must
never meet the word council, quorum, seat, consensus, vote or session. The
outcome list is where that rule breaks most easily: one stored value renders
as "Put off for now" to a general manager who decided it in the yard and as
"Deferred to the next session" to a body that convenes.

**The concentration count.** In a twelve-person district one person holding
all three hats is the normal case. The count says so, as a number, once —
with no color, no threshold, no arrow, no advice and no link. A link from
that tile would be the beginning of advice, and the organization already
knows its own size.
"""

from __future__ import annotations

import pytest

from app import decisions, spine
from app.authz import Actor, Role

WHO = Actor("council.cto", "Jordan Doe", Role.COUNCIL, title="Director")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(decisions, "_file", lambda: tmp_path / "d.json")
    monkeypatch.setattr(decisions, "_record", lambda *a, **k: None)
    yield


# --------------------------------------------------------- the four shapes

@pytest.mark.parametrize("shape,expected", [
    (decisions.ONE_PERSON, "Put off for now"),
    (decisions.EXISTING_BODY, "Put off for now"),
    (decisions.SMALL_GROUP, "Deferred to the next session"),
    (decisions.COUNCIL, "Deferred to the next session"),
])
def test_the_deferred_outcome_renders_for_their_shape(shape, expected) -> None:
    """One stored value, two strings. Telling a general manager who decided
    it in the yard that it was "deferred to the next session" is the
    application describing a meeting that does not exist."""
    assert decisions.outcome_label(decisions.DEFERRED, shape) == expected


def test_a_single_decider_never_meets_the_meeting_vocabulary() -> None:
    """The rule that keeps this honest, and the one most easily broken."""
    for shape in (decisions.ONE_PERSON, decisions.EXISTING_BODY):
        said = " ".join(
            decisions.outcome_label(o, shape) for o in decisions.OUTCOMES
        ).lower()
        for word in decisions.SHAPE_WORDS:
            assert word not in said, f"{shape}: {word}"


def test_only_a_body_is_asked_who_was_present() -> None:
    assert decisions.asks_who_was_present(decisions.COUNCIL)
    assert decisions.asks_who_was_present(decisions.SMALL_GROUP)
    assert not decisions.asks_who_was_present(decisions.ONE_PERSON)
    assert not decisions.asks_who_was_present(decisions.EXISTING_BODY)


def test_presence_and_recusal_are_dropped_for_a_single_decider() -> None:
    """Not asked, so not stored. A field that quietly keeps what it never
    asked for is how a record acquires facts nobody gave it."""
    made = decisions.record(
        about="AI-1", what="approve", actor=WHO,
        shape=decisions.ONE_PERSON,
        present=["somebody"], recused=["somebody else"],
        minority="a dissent")
    row = made["decision"]
    assert row["present"] == []
    assert row["recused"] == []
    assert row["minority"] == ""


def test_an_existing_body_keeps_the_name_they_gave_it() -> None:
    """"The executive team" and "the safety committee" are not
    interchangeable to the people who sit on them."""
    assert decisions.body_name(decisions.EXISTING_BODY,
                               "the safety committee") == (
        "the safety committee")
    # And a council that named itself keeps its name too.
    assert decisions.body_name(decisions.COUNCIL,
                               "the Board of Commissioners") == (
        "the Board of Commissioners")


def test_a_shape_with_no_name_still_reads_as_a_sentence() -> None:
    for shape in decisions.SHAPES:
        got = decisions.body_name(shape)
        assert got and not got.startswith("None")


# ------------------------------------------------------------ the decision

def test_the_unit_is_one_thing_decided_on_one_date() -> None:
    made = decisions.record(about="AI-1", what="approve for use", actor=WHO,
                            outcome=decisions.APPROVED,
                            decided_on="2026-03-04")
    row = made["decision"]
    assert row["about"] == "AI-1"
    assert row["decided_on"] == "2026-03-04"
    # The date may be left for later; it is never filled in with today.
    later = decisions.record(about="AI-1", what="x", actor=WHO)["decision"]
    assert later["decided_on"] == ""
    assert row["recorded_by"] == "Jordan Doe"
    assert row["ref"].startswith("D-")


def test_every_decision_is_stamped_with_the_version_in_force(
        monkeypatch) -> None:
    """What lets somebody say, two years from now, what the rules were on
    the day something was approved rather than what they are today."""
    monkeypatch.setattr(decisions, "_framework_version", lambda: "Version 2")
    made = decisions.record(about="AI-1", what="approve", actor=WHO)
    assert made["decision"]["version"] == "Version 2"


def test_nothing_is_ever_removed_from_the_list() -> None:
    decisions.record(about="AI-1", what="turn down", actor=WHO,
                     outcome=decisions.TURNED_DOWN)
    assert len(decisions.all_decisions()) == 1
    assert decisions.counters()["recorded"] == 1


def test_an_unknown_outcome_is_refused_rather_than_stored() -> None:
    assert not decisions.record(about="x", what="y", actor=WHO,
                                outcome="outcome.maybe")["ok"]


# ------------------------------------------------------------ the counters

def test_asked_for_not_yet_decided_counts_the_stored_value() -> None:
    """The rule is stated against the stored value rather than the rendered
    string, because that string differs by governance shape."""
    decisions.record(about="A", what="x", actor=WHO,
                     outcome=decisions.APPROVED)
    decisions.record(about="B", what="x", actor=WHO)
    decisions.record(about="C", what="x", actor=WHO,
                     outcome=decisions.DEFERRED)
    assert decisions.counters()["asked_not_decided"] == 2


def test_that_counter_does_not_borrow_the_spine_state_name() -> None:
    """Two different objects with two different counts. A single name
    across both is the kind of ambiguity that survives review and then has
    to be unpicked in the middle of a build."""
    got = decisions.counters()
    said = " ".join(got["says"].values()).lower()
    assert "waiting on somebody" not in said
    shown = spine.BY_STATE[spine.WAITING_PERSON].shown_as
    assert shown.lower() not in said


def test_conditions_with_no_date_are_not_counted_as_overdue() -> None:
    decisions.record(about="A", what="x", actor=WHO,
                     conditions=[{"what": "get the documentation",
                                  "owner": "IT", "by": ""}])
    got = decisions.counters()
    assert got["conditions_open"] == 1
    assert got["conditions_overdue"] == 0


def test_a_condition_past_its_date_is_counted() -> None:
    decisions.record(about="A", what="x", actor=WHO,
                     conditions=[{"what": "get it", "owner": "IT",
                                  "by": "2020-01-01"}])
    assert decisions.counters()["conditions_overdue"] == 1


# ------------------------------------------------- the concentration count

def test_three_of_three_is_stated_once_and_nothing_else() -> None:
    got = decisions.concentration({"jo": [spine.OPERATOR, spine.TECHNOLOGY,
                                          spine.DECIDER]})
    assert got["shown_as"] == "3 of 3"
    assert got["says"] == "Three of three roles held by one person."
    assert got["is_a_link"] is False


def test_nobody_wearing_two_hats_reads_plainly() -> None:
    got = decisions.concentration({"jo": [spine.OPERATOR],
                                   "sam": [spine.DECIDER]})
    assert got["shown_as"] == "1 of 3"
    assert got["says"] == "Nobody here holds more than one hat."


def test_the_concentration_tile_carries_no_advice() -> None:
    """No color treatment, no threshold, no arrow, and no advice. It is a
    fact the organization already knows."""
    for hats in ({"jo": list(spine.ROLES)}, {"jo": [spine.OPERATOR]}):
        said = decisions.concentration(hats)["says"].lower()
        for advice in ("should", "risk", "consider", "recommend", "separate",
                       "concern", "warning", "too many"):
            assert advice not in said, advice


def test_an_empty_roster_does_not_divide_by_zero() -> None:
    assert decisions.concentration({})["held"] == 1


# ------------------------------------------------------- the adoption line

def test_nothing_adopted_says_nothing_binds_yet() -> None:
    said = decisions.adoption_line()
    assert "No framework adopted yet" in said
    assert "binds anybody" in said


def test_the_adopted_line_reads_their_own_title_and_cadence() -> None:
    said = decisions.adoption_line(
        adopted_on="14 March 2026", authority="the Board of Commissioners",
        version="2", in_effect="1 April 2026", cadence="every year",
        next_look="14 March 2027")
    assert "the Board of Commissioners" in said
    assert "You said it comes back every year" in said
    assert "next look 14 March 2027" in said


def test_no_signed_copy_is_said_rather_than_implied() -> None:
    said = decisions.adoption_line(
        adopted_on="14 March 2026", authority="the Director", version="2",
        in_effect="1 April 2026", signed_copy=False)
    assert "No signed copy on file" in said


def test_an_unnamed_authority_carries_the_gap_and_never_a_name() -> None:
    """Never rendered blank and never rendered with an invented name. "An
    elected board or council, by vote" is a category and reads as nothing in
    a sentence."""
    said = decisions.adoption_line(
        adopted_on="14 March 2026", version="2", in_effect="1 April 2026",
        gap_owner="the Clerk", gap_by="30 June 2026")
    assert "you said you were not sure" in said
    assert "Owned by the Clerk, by 30 June 2026." in said
    assert "by by " not in said


def test_a_gap_with_no_date_says_no_date_set() -> None:
    said = decisions.adoption_line(adopted_on="14 March 2026", version="2",
                                   gap_owner="the Clerk")
    assert "no date set" in said


def test_the_adoption_line_invents_no_title_date_or_cadence() -> None:
    said = decisions.adoption_line(adopted_on="14 March 2026",
                                   authority="the Director", version="1")
    for invented in ("annually", "every 12 months", "quarterly"):
        assert invented not in said


# ------------------------------------------------------------- findings

def test_put_off_twice_names_their_own_tiebreaker() -> None:
    for _ in range(2):
        decisions.record(about="AI-1", what="x", actor=WHO,
                         outcome=decisions.DEFERRED)
    found = decisions.findings(tiebreaker="the District Manager")
    hit = [f for f in found if f["id"] == "finding.oversight.deferred_twice"]
    assert hit
    assert "the District Manager" in hit[0]["says"]


def test_no_tiebreaker_named_means_no_finding_about_one() -> None:
    """A finding is raised only where the organization's own answer said
    somebody else must be involved."""
    for _ in range(3):
        decisions.record(about="AI-1", what="x", actor=WHO,
                         outcome=decisions.DEFERRED)
    found = {f["id"] for f in decisions.findings(tiebreaker="")}
    assert "finding.oversight.deferred_twice" not in found


def test_nobody_able_to_stop_a_tool_is_flagged_only_where_tools_run() -> None:
    assert not [f for f in decisions.findings(stop_authority="", in_use=0)
                if f["id"] == "finding.oversight.stop_authority_unnamed"]
    found = decisions.findings(stop_authority="", in_use=4)
    hit = [f for f in found
           if f["id"] == "finding.oversight.stop_authority_unnamed"]
    assert hit and "4 are in use" in hit[0]["says"]


def test_a_decision_before_adoption_is_a_fact_on_the_row_never_a_finding() \
        -> None:
    """The specification cut this finding by name: on that date there was
    no framework, so there was nothing to contradict, and it would put a
    finding on every row a new organization records on its first day. It
    was built anyway and has been taken out. The fact stays on the row."""
    decisions.record(about="A", what="x", actor=WHO,
                     decided_on="2026-01-01")
    found = decisions.findings(adopted_on="2026-03-01")
    assert not [f for f in found if "before_adoption" in f["id"]]
    assert "finding.oversight.before_adoption" not in decisions.BY_OWN_FINDING
    row = decisions.report(adopted_on="2026-03-01")["decisions"][0]
    assert row["before_framework"] is True
    assert "a decision dated before the framework took effect" in \
        decisions.CUT_FINDINGS


def test_the_eight_own_findings_are_the_specifications_eight() -> None:
    assert {f.id for f in decisions.OWN_FINDINGS} == {
        "finding.oversight.above_delegation",
        "finding.oversight.deferred_twice",
        "finding.oversight.cadence_missed",
        "finding.oversight.stop_authority_unnamed",
        "finding.oversight.notify_not_recorded",
        "finding.oversight.lookback_not_decided",
        "finding.oversight.amendment_unapproved",
        "finding.oversight.condition_no_date",
    }


def test_a_condition_with_an_owner_and_no_date_on_a_tool_in_use() -> None:
    """It will not come back on its own."""
    made = decisions.record(about="7QHC26", what="x", actor=WHO,
                            conditions=[{"what": "Train staff",
                                         "owner": "Clerk", "by": ""}])
    assert made["ok"]
    found = decisions.findings(in_use_records={"7QHC26"})
    hit = [f for f in found if f["id"] == "finding.oversight.condition_no_date"]
    assert hit and "nobody's date" in hit[0]["says"]


def test_not_when_the_tool_is_not_in_use() -> None:
    decisions.record(about="7QHC26", what="x", actor=WHO,
                     conditions=[{"what": "Train staff", "owner": "Clerk",
                                  "by": ""}])
    assert not [f for f in decisions.findings(in_use_records=set())
                if f["id"] == "finding.oversight.condition_no_date"]


def test_not_when_nobody_owns_it_that_is_another_findings_business() -> None:
    decisions.record(about="7QHC26", what="x", actor=WHO,
                     conditions=[{"what": "Train staff", "owner": "",
                                  "by": ""}])
    assert not [f for f in decisions.findings(in_use_records={"7QHC26"})
                if f["id"] == "finding.oversight.condition_no_date"]


# ---------------------------------------------------------- the standing watch

def _conditions(*dates: str) -> list[dict]:
    return [{"what": f"c{i}", "owner": "Clerk", "by": d}
            for i, d in enumerate(dates)]


def test_the_watch_counts_four_things() -> None:
    got = decisions.standing_watch(
        _conditions("2026-01-01", "2026-10-15", "2027-06-01", ""),
        cadence="quarterly", today="2026-09-24")
    assert got["with_a_date"] == 3
    assert got["past_their_date"] == 1
    assert got["no_date_set"] == 1
    assert got["coming_due"] == 1        # 15 October, inside the quarter


def test_the_window_is_their_own_cadence() -> None:
    held = _conditions("2027-01-10")
    assert decisions.standing_watch(held, cadence="quarterly",
                                    today="2026-09-24")["coming_due"] == 0
    assert decisions.standing_watch(held, cadence="annual",
                                    today="2026-09-24")["coming_due"] == 1


def test_as_requests_come_in_has_no_next_look() -> None:
    got = decisions.standing_watch(_conditions("2026-10-01"),
                                   cadence="onrequest", today="2026-09-24")
    assert got["coming_due_shown"] == "—"
    assert "no next look" in got["coming_due_note"]


def test_no_cadence_answered_invents_none() -> None:
    got = decisions.standing_watch(_conditions("2026-10-01"), cadence="",
                                   today="2026-09-24")
    assert got["coming_due"] is None


def test_the_watch_says_what_it_cannot_see() -> None:
    said = decisions.standing_watch([], today="2026-09-24")["cannot"]
    assert "nothing verifies a signature" in said
    assert "we assume it happened" in said


def test_closed_conditions_are_not_watched() -> None:
    held = _conditions("2026-01-01") + [{"what": "done", "owner": "Clerk",
                                         "by": "2026-01-01", "closed": "x"}]
    assert decisions.standing_watch(held, cadence="quarterly",
                                    today="2026-09-24")["past_their_date"] == 1


# ------------------------------------------- what you said happens when it goes wrong

def test_the_panel_is_their_own_words_and_read_only() -> None:
    answers = {"bad.report_to": "Call the district office on 555-0100"}
    panel = decisions.when_it_goes_wrong(answers)
    assert panel["editable"] is False
    tell = next(r for r in panel["rows"] if r["key"] == "bad.report_to")
    assert tell["answered"] is True
    assert any("555-0100" in line for line in tell["lines"])


def test_an_unanswered_stop_authority_renders_as_the_gap() -> None:
    panel = decisions.when_it_goes_wrong({})
    stop = next((r for r in panel["rows"] if r["key"] == "bad.stopper"), None)
    if stop is None:
        pytest.skip("not asked without earlier answers")
    assert stop["answered"] is False
    assert stop["lines"][0].startswith("Nobody named yet.")


def test_no_row_is_ever_blank() -> None:
    for row in decisions.when_it_goes_wrong({})["rows"]:
        assert row["lines"] and all(line.strip() for line in row["lines"])


def test_the_lookback_rule_binds_to_position_not_to_a_name() -> None:
    """Three ordered levels the organization may rename to anything. A
    renamed level keeps its position and the rule survives the rename."""
    assert decisions.LOOKBACK_LEVELS == (2, 3)
    trigger = decisions.BY_OWN_FINDING[
        "finding.oversight.lookback_not_decided"].trigger.lower()
    assert "second or third" in trigger
    for named in ("severe", "critical", "major", "high"):
        assert named not in trigger


def test_no_finding_is_raised_against_anything_outside() -> None:
    for finding in decisions.OWN_FINDINGS:
        said = (finding.says + " " + finding.trigger).lower()
        for outside in ("industry", "benchmark", "best practice",
                        "other organizations", "maturity", "peers"):
            assert outside not in said, finding.id


def test_the_shared_findings_are_not_redefined_here() -> None:
    for shared in decisions.SHARED_FINDINGS:
        assert shared in spine.BY_FINDING
        assert shared not in decisions.BY_OWN_FINDING


# ------------------------------------------------------- ranking weights

def test_setting_weights_is_a_decision_with_a_name_and_a_date() -> None:
    """The alternative is a number living in a formula that one person can
    change without telling anybody."""
    made = decisions.set_weights({"cost": 0.4, "fit": 0.6}, WHO,
                                 why="the board asked for cost to lead")
    assert made["ok"]
    held = decisions.weights()
    assert held["set_by"] == "Jordan Doe"
    assert held["on"]
    assert held["why"]


def test_nothing_is_ranked_until_the_weights_are_settled() -> None:
    assert decisions.weights() == {}
    assert "side by side rather than ranked" in decisions.UNWEIGHTED


def test_the_surface_says_which_of_the_two_scoring_rules_applies() -> None:
    """The two rules read as contradictory to anyone who has not been told
    which is which, so any surface touching either one says which."""
    said = decisions.SCORING_LINE.lower()
    assert "candidate solutions are ranked" in said
    assert "nothing in this application scores your organization" in said


def test_weights_need_something_to_weigh() -> None:
    assert not decisions.set_weights({}, WHO)["ok"]


# --------------------------------------------------------------- labels

def test_an_organisation_with_no_labels_never_learns_the_block_exists() -> None:
    """AI governance is not data governance. Nothing asks for a scheme,
    requires one, or treats its absence as a defect."""
    assert decisions.labels() == []
    assert decisions.has_labels() is False


def test_labels_are_kept_exactly_as_the_organisation_typed_them() -> None:
    decisions.set_labels(["Public", "Internal only", "  ", "Restricted"], WHO)
    assert decisions.labels() == ["Public", "Internal only", "Restricted"]


def test_the_whole_surface_serialises() -> None:
    import json
    decisions.record(about="A", what="x", actor=WHO)
    json.dumps(decisions.report(shape=decisions.COUNCIL,
                                named="the Board",
                                hats={"jo": list(spine.ROLES)}))
