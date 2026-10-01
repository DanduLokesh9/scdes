"""Integrity — does it work, and is it still working.

The two facts this surface exists to be able to state are that somebody
looked on a date, and that nobody has looked in eighteen months. Almost
every test below is about keeping the second one honest: never inventing an
interval, never inventing a look-back, never turning an unanswered question
into a failure, and never showing a tick that would mean the app had read
something it cannot read.
"""

from __future__ import annotations

import pytest

from app import checks, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Never touch a real register, and never write a real audit entry."""
    monkeypatch.setattr(checks, "_file", lambda: tmp_path / "checks.json")
    monkeypatch.setattr(checks, "_log", lambda *a, **k: None)
    yield


def _check(**over):
    over.setdefault("project", "7QHC26")
    made = checks.record_check(actor=WHO, **over)
    assert made["ok"], made
    return made["check"]


def _incident(**over):
    over.setdefault("what_happened", "It gave the wrong answer.")
    made = checks.report_incident(actor=WHO, **over)
    assert made["ok"], made
    return made["incident"]


# --------------------------------------------------------------- the record

def test_only_the_project_is_required() -> None:
    """A register that refuses a row until every box is filled is one nobody
    finishes."""
    assert checks.record_check(project="7QHC26", actor=WHO)["ok"]
    assert not checks.record_check(project="   ", actor=WHO)["ok"]


def test_an_incident_needs_either_the_tool_or_a_sentence() -> None:
    assert checks.report_incident(actor=WHO, tool="Permit triage")["ok"]
    assert checks.report_incident(actor=WHO, what_happened="It broke")["ok"]
    assert not checks.report_incident(actor=WHO)["ok"]


def test_both_kinds_share_one_register() -> None:
    """An incident is very often what triggers the next check, and filing
    them separately puts the answer on a different screen from the
    question."""
    _check()
    _incident()
    assert len(checks.all_entries()) == 2
    assert len(checks.checks()) == 1
    assert len(checks.incidents()) == 1


def test_the_reference_says_which_kind_it_is() -> None:
    assert _check()["ref"].startswith("CK-")
    assert _incident()["ref"].startswith("IN-")


def test_recording_late_keeps_both_dates() -> None:
    """Recording late is ordinary, and the row shows both rather than
    flattening them into one."""
    row = _check(at="2026-03-04")
    assert row["at"] == "2026-03-04"
    assert row["written_down"] != "2026-03-04"
    assert "happened 2026-03-04" in checks.date_column(row)
    assert "written down" in checks.date_column(row)


def test_the_date_column_says_one_date_when_they_match() -> None:
    row = _check()
    assert checks.date_column(row) == row["at"]


# ------------------------------------------------------- the two gates it owns

def test_the_first_look_is_test_and_every_look_after_it_is_measure() -> None:
    assert checks.gate_for(checks.FIRST_LOOK) == spine.TEST
    assert checks.gate_for(checks.REGULAR_LOOK) == spine.MEASURE
    assert checks.gate_for(checks.AFTER_AN_INCIDENT) == spine.MEASURE


def test_a_look_after_a_change_goes_back_to_test() -> None:
    """That is the loop, and it is why this surface stays busy after the
    first year."""
    assert checks.gate_for(checks.AFTER_A_CHANGE) == spine.TEST


def test_the_gate_is_never_rendered_as_a_number() -> None:
    surface = checks.report()
    text = repr(surface) + "".join(n + c for n, c in checks.COLUMNS)
    for banned in spine.BANNED_GATE_FORMS:
        assert banned not in text.lower()


# ------------------------------------------------------------ 8.8, the limits

def test_a_complete_check_cannot_have_empty_limits() -> None:
    """The one refusal on this form."""
    refused = checks.record_check(project="7QHC26", actor=WHO, complete=True)
    assert not refused["ok"]
    assert refused["field"] == "8.8"
    assert refused["error"] == checks.LIMITS_REQUIRED


def test_the_refusal_does_not_block_the_record() -> None:
    """The record still moves and the gate still passes with a gap
    attached. The app blocks at two gates and on seven obligations, and
    this is neither."""
    assert checks.record_check(project="7QHC26", actor=WHO)["ok"]


def test_either_way_of_answering_the_limits_lets_it_complete() -> None:
    assert _check(limits="Nobody tried it on Spanish forms.",
                  complete=True)["complete"]
    assert _check(limits_not_written=True, complete=True)["complete"]


def test_marking_complete_later_hits_the_same_refusal() -> None:
    row = _check()
    refused = checks.mark_complete(row["ref"], actor=WHO)
    assert not refused["ok"]
    assert refused["error"] == checks.LIMITS_REQUIRED


def test_marking_complete_works_once_the_limits_are_answered() -> None:
    row = _check(limits="Only one month of forms.")
    done = checks.mark_complete(row["ref"], actor=WHO)
    assert done["ok"] and done["check"]["complete"]


def test_the_ticked_box_raises_and_the_empty_field_cannot() -> None:
    """The finding fires on the ticked box alone. An empty field never
    becomes a complete check, so it never becomes a finding."""
    _check(limits_not_written=True, complete=True)
    _check(limits="We did not try it on appeals.", complete=True)
    raised = [f["id"] for f in checks.findings()]
    assert raised.count("finding.limits_absent") == 1


# ----------------------------------------------- a draft raises and blocks nothing

def test_a_draft_is_not_evidence_and_raises_nothing() -> None:
    _check(limits_not_written=True)
    assert checks.findings() == []
    assert checks.counters()["checks_recorded"] == 0


def test_the_confirmation_copy_never_thanks_anybody() -> None:
    """Nothing has been sent to anyone, and the copy does not suggest it
    has."""
    draft = checks.after_a_check(_check())
    done = checks.after_a_check(_check(limits="x", complete=True))
    for line in draft + done:
        assert "thank" not in line.lower()
        assert "notif" not in line.lower()
    assert "still being written" in draft[1]
    assert "evidence for a passage" in done[1]


def test_zero_findings_changed_is_not_rendered() -> None:
    row = _check(limits="x", complete=True)
    assert "0 findings" not in " ".join(checks.after_a_check(row))
    with_change = checks.after_a_check(row, findings_changed=2)
    assert "2 findings" in with_change[1]


def test_the_incident_confirmation_says_nobody_was_told() -> None:
    row = _incident()
    said = checks.after_an_incident(row, route="the duty officer")
    assert "has not told them" in said[1]


# ------------------------------------------------------- 3 · the five counters

def test_five_counters_always_five() -> None:
    got = checks.counters()
    for name in ("checks_recorded", "looked_at_this_cycle", "never_checked",
                 "past_due", "fifth"):
        assert name in got


def test_zero_is_a_true_reading() -> None:
    assert "nothing is recorded yet" in checks.counters()["zero_is_true"]


def test_a_running_tool_nobody_has_looked_at_counts_as_never_checked() -> None:
    """The condition that matters on a first day: it counts even though it
    has not reached Test."""
    got = checks.counters(projects={
        "7QHC26": {"gate": spine.IDENTIFY, "in_use": spine.IN_USE_YES}})
    assert got["never_checked"] == 1


def test_a_project_short_of_test_and_not_in_use_does_not_count() -> None:
    got = checks.counters(projects={
        "7QHC26": {"gate": spine.IDENTIFY, "in_use": spine.IN_USE_NO}})
    assert got["never_checked"] == 0


def test_a_checked_project_is_not_never_checked() -> None:
    _check(limits="x", complete=True)
    got = checks.counters(projects={
        "7QHC26": {"gate": spine.MEASURE, "in_use": spine.IN_USE_YES}})
    assert got["never_checked"] == 0


def test_no_interval_set_never_counts_as_past_due() -> None:
    """The application does not invent an interval, ever."""
    got = checks.counters(
        projects={"7QHC26": {"gate": spine.MEASURE, "level": "routine"}},
        intervals={})
    assert got["past_due"] == 0
    assert got["looked_at_this_cycle"] == 0


def test_past_due_reads_their_own_interval() -> None:
    _check(at="2020-01-01", limits="x", complete=True)
    got = checks.counters(
        projects={"7QHC26": {"gate": spine.MEASURE, "level": "routine"}},
        intervals={"routine": 365}, today="2026-09-22")
    assert got["past_due"] == 1


def test_a_recent_look_counts_as_looked_at_this_cycle() -> None:
    _check(at="2026-09-01", limits="x", complete=True)
    got = checks.counters(
        projects={"7QHC26": {"gate": spine.MEASURE, "level": "routine"}},
        intervals={"routine": 365}, today="2026-09-22")
    assert got["looked_at_this_cycle"] == 1
    assert got["past_due"] == 0


# --------------------------------------------- 3A · the counter that changes shape

def test_the_fifth_counter_has_a_label_for_every_answer() -> None:
    for answer in checks.LOOKBACK_ANSWER_VALUES:
        assert checks.FIFTH_COUNTER[answer]


def test_where_they_do_not_go_back_it_counts_something_else() -> None:
    """A look-back counter would sit at a permanent zero, so what is
    counted instead is the checks that recorded no limits."""
    _check(limits_not_written=True, complete=True)
    _incident()
    got = checks.fifth_counter(answer=checks.LOOKBACK_NO)
    assert got["label"] == "Checks with no limits written down"
    assert got["count"] == 1


def test_case_by_case_counts_decisions_waiting_not_failures() -> None:
    _incident()
    got = checks.fifth_counter(answer=checks.LOOKBACK_CASE_BY_CASE)
    assert got["label"] == "Look-backs not yet decided"
    assert got["count"] == 1
    assert "case by case" in got["says"]


def test_unsure_says_the_decision_has_not_been_made() -> None:
    got = checks.fifth_counter(answer=checks.LOOKBACK_UNSURE)
    assert "have not decided" in got["says"]


def test_the_swap_is_announced_rather_than_silent() -> None:
    said = checks.swap_announcement("Look-backs owed")
    assert "Your framework changed" in said
    assert "Look-backs owed" in said


# ---------------------------------------------------------- 4 · the findings

def test_every_finding_is_a_comparison_with_their_own_framework() -> None:
    assert "your own framework" in checks.FINDINGS_ARE_COMPARISONS
    assert "whether a tool is any good" in checks.FINDINGS_ARE_COMPARISONS


def test_the_fourteen_findings_are_all_here() -> None:
    assert len(checks.OWN_FINDINGS) == 14
    assert len({f.id for f in checks.OWN_FINDINGS}) == 14


def test_every_finding_is_raised_by_this_surface() -> None:
    for finding in checks.OWN_FINDINGS:
        assert finding.raised_by == "Integrity"
        assert finding.trigger and finding.says


def test_no_finding_reads_against_an_outside_standard() -> None:
    for finding in checks.OWN_FINDINGS:
        said = finding.says.lower()
        for word in ("industry", "benchmark", "best practice", "other "
                     "agencies", "peer"):
            assert word not in said


def test_watch_missing_only_asks_about_what_they_said_they_watch() -> None:
    _check(occasion=checks.REGULAR_LOOK, limits="x", complete=True,
           watched={"Complaints": "None this quarter."})
    raised = checks.findings(watches=["Complaints", "Security"])
    ids = [f["id"] for f in raised]
    assert ids.count("finding.watch_missing") == 1
    # Their word, lowered to sit mid-sentence.
    assert "watch security" in [f["says"] for f in raised
                                if f["id"] == "finding.watch_missing"][0]


def test_watching_nothing_is_never_shown_as_missing() -> None:
    _check(occasion=checks.REGULAR_LOOK, limits="x", complete=True)
    assert [f for f in checks.findings(watches=[])
            if f["id"] == "finding.watch_missing"] == []


def test_the_claim_is_only_unmeasured_where_a_baseline_exists() -> None:
    """Where the project carries no baseline that is Projects' finding, not
    this one."""
    _check(occasion=checks.REGULAR_LOOK, limits="x", complete=True)
    assert [f for f in checks.findings()
            if f["id"] == "finding.claim_unmeasured"] == []
    raised = checks.findings(baselines={"7QHC26": "it saves a day a week"})
    assert [f for f in raised if f["id"] == "finding.claim_unmeasured"]


def test_only_pause_and_retire_take_it_out_of_service() -> None:
    assert checks.TAKES_IT_OUT_OF_SERVICE == (checks.PAUSE_UNTIL_FIXED,
                                              checks.RETIRE_IT)
    assert checks.ADJUST_AND_TEST not in checks.TAKES_IT_OUT_OF_SERVICE
    assert checks.DECIDE_CASE_BY_CASE not in checks.TAKES_IT_OUT_OF_SERVICE


def test_determination_not_followed_reads_the_projects_state() -> None:
    _check(limits="x", complete=True, verdict=checks.DID_NOT_HOLD_UP,
           determination=checks.PAUSE_UNTIL_FIXED)
    raised = checks.findings(projects={
        "7QHC26": {"gate": spine.MEASURE, "state": spine.CLEARED}})
    said = [f for f in raised
            if f["id"] == "finding.determination_not_followed"]
    assert said and "still running" in said[0]["says"]


def test_it_closes_itself_the_moment_the_project_is_paused() -> None:
    """No grace period; nothing asked for an interval here, and the app
    does not invent one."""
    _check(limits="x", complete=True, verdict=checks.DID_NOT_HOLD_UP,
           determination=checks.RETIRE_IT)
    for held in ({"gate": spine.MEASURE, "state": spine.PAUSED},
                 {"gate": spine.SUNSET, "state": spine.CLEARED}):
        raised = checks.findings(projects={"7QHC26": held})
        assert [f for f in raised
                if f["id"] == "finding.determination_not_followed"] == []


def test_adjust_and_test_again_is_not_a_contradiction() -> None:
    _check(limits="x", complete=True, verdict=checks.DID_NOT_HOLD_UP,
           determination=checks.ADJUST_AND_TEST)
    raised = checks.findings(projects={
        "7QHC26": {"gate": spine.MEASURE, "state": spine.CLEARED}})
    assert [f for f in raised
            if f["id"] == "finding.determination_not_followed"] == []


# ------------------------------------------------------ the look-back branches

def test_a_lookback_is_owed_only_where_they_said_they_go_back() -> None:
    _incident()
    assert [f for f in checks.findings(lookback_answer=checks.LOOKBACK_YES)
            if f["id"] == "finding.lookback_owed"]
    for answer in (checks.LOOKBACK_NO, checks.LOOKBACK_CASE_BY_CASE,
                   checks.LOOKBACK_UNSURE):
        assert [f for f in checks.findings(lookback_answer=answer)
                if f["id"] == "finding.lookback_owed"] == []


def test_severity_is_never_read_for_a_lookback() -> None:
    """A mapping from a level to a look-back would be one the app
    invented."""
    _incident(severity="routine")
    _incident(severity="the serious one")
    raised = [f for f in checks.findings() if f["id"] ==
              "finding.lookback_owed"]
    assert len(raised) == 2
    assert "Severity is not read" in checks.NO_SEVERITY_MAPPING


def test_not_needed_for_this_one_closes_it() -> None:
    _incident(lookback=checks.LOOKBACK_NOT_NEEDED)
    assert [f for f in checks.findings()
            if f["id"] == "finding.lookback_owed"] == []


def test_not_yet_and_not_sure_are_still_owed() -> None:
    _incident(lookback=checks.LOOKBACK_NOT_YET)
    _incident(lookback=checks.LOOKBACK_UNSURE_HERE)
    assert len([f for f in checks.findings()
                if f["id"] == "finding.lookback_owed"]) == 2


# ---------------------------------------------------------- the other findings

def test_a_party_they_named_with_no_notification_recorded() -> None:
    _incident(told={"the affected person": "2026-09-02"})
    raised = checks.findings(must_be_told=["the affected person",
                                           "the privacy officer"])
    said = [f for f in raised if f["id"] == "finding.notified_missing"]
    assert len(said) == 1 and "privacy officer" in said[0]["says"]


def test_reporting_slower_than_stated_measures_from_detection() -> None:
    row = _incident(first_noticed="2026-08-01")
    checks._write({"entries": {row["ref"]: {**row,
                                            "written_down": "2026-09-01"}},
                   "stopping_rule": {}})
    raised = checks.findings(report_hours={"": 24})
    assert [f for f in raised
            if f["id"] == "finding.report_slower_than_stated"]


def test_nothing_is_computed_without_a_recorded_detection_date() -> None:
    _incident()
    assert [f for f in checks.findings(report_hours={"": 24})
            if f["id"] == "finding.report_slower_than_stated"] == []


def test_test_on_never_needs_the_holding_to_be_named() -> None:
    """Leave the holding blank and nothing here is ever flagged."""
    _check(limits="x", complete=True)
    assert [f for f in checks.findings(
        never_categories={"Enforcement files": "health information"})
        if f["id"] == "finding.test_on_never"] == []

    _check(limits="x", complete=True, holdings=["Enforcement files"])
    raised = checks.findings(
        never_categories={"Enforcement files": "health information"})
    said = [f for f in raised if f["id"] == "finding.test_on_never"]
    assert said and "health information" in said[0]["says"]


def test_the_stopping_rule_is_only_read_where_they_have_one() -> None:
    """Nothing in the framework asks for one, and its absence is never a
    defect."""
    _check(limits="x", complete=True)
    assert [f for f in checks.findings()
            if f["id"] == "finding.stopping_rule_unmet"] == []

    checks.set_stopping_rule(actor=WHO, have_one="Yes",
                             name="Enough is enough",
                             says="Two clean rounds.")
    assert [f for f in checks.findings()
            if f["id"] == "finding.stopping_rule_unmet"]


def test_a_no_answer_on_the_stopping_rule_leaves_it_alone() -> None:
    checks.set_stopping_rule(actor=WHO, have_one="No")
    _check(limits="x", complete=True)
    assert [f for f in checks.findings()
            if f["id"] == "finding.stopping_rule_unmet"] == []


# -------------------------------------------------- 4B · rendered from elsewhere

def test_findings_owned_elsewhere_are_never_redefined_here() -> None:
    ours = {f.id for f in checks.OWN_FINDINGS}
    for borrowed in checks.RENDERS_HERE:
        assert borrowed not in ours


def test_the_borrowed_findings_say_why_they_appear_here() -> None:
    for borrowed, because in checks.RENDERS_HERE.items():
        assert because.strip().endswith(".")
        assert len(because) > 40, borrowed


def test_framework_moved_only_renders_for_four_kinds_of_amendment() -> None:
    assert len(checks.FRAMEWORK_MOVES_THAT_SHOW_HERE) == 4
    because = checks.RENDERS_HERE["finding.framework_moved"]
    for moved in checks.FRAMEWORK_MOVES_THAT_SHOW_HERE:
        assert moved in because


# ------------------------------------------------------ 4D · what it will not raise

def test_a_declined_recommendation_is_never_a_finding() -> None:
    said = " ".join(checks.WILL_NOT_RAISE).lower()
    assert "declining the recommendation" in said
    for finding in checks.OWN_FINDINGS:
        assert "declin" not in finding.trigger.lower()


def test_having_no_staging_environment_is_never_a_finding() -> None:
    _check(limits="x", complete=True, where=checks.WHERE_NONE)
    assert checks.findings() == []
    assert "No staging" in checks.WHERE_COLUMN[checks.WHERE_NONE]


def test_concentration_of_roles_is_not_a_finding_here() -> None:
    said = " ".join(checks.WILL_NOT_RAISE)
    assert "Concentration of roles" in said
    assert "never a finding here" in said


def test_nothing_about_how_good_a_tool_is() -> None:
    said = " ".join(checks.WILL_NOT_RAISE).lower()
    assert "how good a tool is" in said


# --------------------------------------------------- 5 · the recommendation

def test_the_recommendation_comes_from_the_spine() -> None:
    assert checks.TRY_THE_UPDATE.where == spine.TEST
    assert checks.TRY_THE_UPDATE.because
    ok, why = checks.TRY_THE_UPDATE.valid()
    assert ok, why


def test_it_fires_on_a_version_check_once_per_version() -> None:
    row = _check(occasion=checks.AFTER_A_CHANGE, version="v3",
                 where=checks.WHERE_STAGING)
    assert checks.recommendation_fires(row)
    assert not checks.recommendation_fires(row, offered_for={"v3"})


def test_it_fires_in_production_and_where_there_is_nowhere_to_try() -> None:
    for where in (checks.WHERE_PRODUCTION, checks.WHERE_NONE):
        row = _check(occasion=checks.FIRST_LOOK, where=where)
        assert checks.recommendation_fires(row)


def test_it_does_not_fire_on_an_ordinary_first_look_in_staging() -> None:
    row = _check(occasion=checks.FIRST_LOOK, where=checks.WHERE_STAGING)
    assert not checks.recommendation_fires(row)


def test_the_recommendation_is_never_part_of_the_to_fix_number() -> None:
    assert checks.badge([], open_findings=0) == "Integrity 0"


def test_it_never_names_a_vendor_or_grades_anybody() -> None:
    said = (checks.TRY_THE_UPDATE.says + checks.TRY_THE_UPDATE.because
            + checks.NOWHERE_TO_TRY_IT).lower()
    for word in ("score", "grade", "rating", "should have"):
        assert word not in said


def test_nowhere_to_try_it_carries_the_fact_not_a_reprimand() -> None:
    assert "environment they do not have" in checks.NOWHERE_TO_TRY_IT
    assert "next agreement" in checks.NOWHERE_TO_TRY_IT
    assert "ordinary case" in checks.ORDINARY_CASE


# ------------------------------------------------------------- 1.2 · the badge

def test_a_badge_reading_zero_to_fix_is_a_nag() -> None:
    _check()
    assert checks.badge(open_findings=0) == "Integrity 1"
    assert checks.badge(open_findings=3) == "Integrity 1 · 3 to fix"


# --------------------------------------------------------- 6.1 · the due watch

def test_the_due_watch_counts_four_things() -> None:
    got = checks.due_watch(projects={
        "7QHC26": {"level": "routine"}, "BB4KD9": {"level": "elevated"}},
        intervals={"routine": 365})
    assert got["watched"] == 1
    assert got["no_interval_set"] == 1
    assert got["past_due"] + got["inside_your_window"] == 1


def test_a_level_with_no_interval_is_out_of_both_numbers() -> None:
    got = checks.due_watch(projects={"7QHC26": {"level": "routine"}},
                           intervals={})
    assert got["watched"] == 0
    assert got["past_due"] == 0
    assert got["lines"][0]["state"] == checks.NO_INTERVAL_SET
    # No days-over figure is invented where no interval exists.
    assert got["lines"][0]["days_over"] is None


def test_the_due_watch_says_how_many_days_over() -> None:
    _check(at="2024-09-22", limits="x", complete=True)
    got = checks.due_watch(projects={"7QHC26": {"level": "routine"}},
                           intervals={"routine": 365}, today="2026-09-22")
    assert got["lines"][0]["days_over"] == 365


def test_an_unreachable_baseline_sits_beside_the_date() -> None:
    """A look coming due is then not also a surprise."""
    got = checks.due_watch(projects={"7QHC26": {
        "level": "routine",
        "baseline_unreachable": "This cannot be retaken from Permit files."}},
        intervals={"routine": 365})
    assert "cannot be retaken" in got["lines"][0]["beside_the_date"]


def test_the_due_watch_never_emails() -> None:
    assert "never emails" in checks.NEVER_EMAILS


# ------------------------------------------------------ 6.3 · the change watch

def test_the_change_watch_counts_what_was_written_down() -> None:
    got = checks.change_watch(
        changes=[{"tool": "Permit triage", "mattered": "No"},
                 {"tool": "Permit triage"},
                 {"tool": "Appeal sorter"}])
    assert got["changes_recorded"] == 3
    assert got["tools_touched"] == 2
    assert got["answered"] == 1
    assert got["not_yet_answered"] == 2


def test_a_live_version_with_no_check_stays_on_the_watch() -> None:
    got = checks.change_watch(versions=[{"ref": "v3", "live": True}])
    assert got["live_with_no_check"] == 1
    _check(version="v3", limits="x", complete=True)
    got = checks.change_watch(versions=[{"ref": "v3", "live": True}])
    assert got["live_with_no_check"] == 0


def test_the_watches_say_what_they_cannot_do() -> None:
    said = checks.WHAT_THE_WATCHES_CANNOT_DO
    assert "They do not watch the tool" in said
    assert "still accurate" in said
    assert "invisible to this watch" in said


def test_the_change_watch_listens_for_four_things() -> None:
    assert len(checks.CHANGE_WATCH_LISTENS_FOR) == 4


# --------------------------------------------------------- 7 · the list view

def test_twelve_columns_and_grouped_by_default() -> None:
    assert len(checks.COLUMNS) == 12
    assert checks.DEFAULT_GROUPING == checks.GROUPED


def test_each_view_has_its_own_default_sort() -> None:
    assert checks.DEFAULT_SORT[checks.GROUPED] == "Longest since anyone looked"
    assert checks.DEFAULT_SORT[checks.FLAT] == "Most recent first"
    for default in checks.DEFAULT_SORT.values():
        assert default in checks.SORTS


def test_the_version_column_says_first_build_on_a_first_look() -> None:
    assert checks.version_column(
        _check(occasion=checks.FIRST_LOOK)) == "First build"
    assert checks.version_column(
        _check(occasion=checks.AFTER_A_CHANGE, version="v3")) == "v3"
    assert checks.version_column(_incident()) == ""


def test_the_limits_column_is_blank_on_an_incident() -> None:
    assert checks.limits_column(_incident()) == ""
    assert checks.limits_column(_check(limits="x")) == "Written down"
    assert checks.limits_column(_check()) == "Not yet"


def test_three_empty_states_and_none_of_them_blames_anybody() -> None:
    nothing = checks.empty_state()
    some = checks.empty_state(projects=4)
    unaccounted = checks.empty_state(projects=4, unaccounted=True)
    assert "already running" in nothing
    assert "decision about a person" in some
    assert "most useful one you can write" in unaccounted
    for said in (nothing, some, unaccounted):
        for word in ("should", "failed", "overdue", "must"):
            assert word not in said.lower()


def test_an_empty_register_contradicts_nothing() -> None:
    assert checks.EMPTY_CONTRADICTS_NOTHING == spine.NOTHING_TO_FLAG


# ------------------------------------------------- 9 · the example sentences

def test_eight_examples_one_per_organisation_type() -> None:
    assert len(checks.EXAMPLES) == 8
    for tried, affected in checks.EXAMPLES.values():
        assert tried.endswith(".") and affected.endswith(".")


def test_an_unanswered_organisation_type_falls_back() -> None:
    """No field on this surface waits on an organization type."""
    assert checks.example_for("") == checks.EXAMPLES["Other public body"]
    assert checks.example_for("Something else entirely") == \
        checks.EXAMPLES["Other public body"]


def test_no_example_is_a_placeholder() -> None:
    for tried, affected in checks.EXAMPLES.values():
        for said in (tried, affected):
            assert "[" not in said and "TBD" not in said
            assert "e.g." not in said


# ----------------------------------------------------- 10 · the version loop

def test_six_answers_are_always_asked_fresh() -> None:
    """A version check that copies the last one's answers into all six is a
    check nobody performed."""
    assert len(checks.ALWAYS_FRESH) == 6
    for field in checks.ALWAYS_FRESH:
        assert field not in checks.CARRIES_FORWARD


def test_nothing_carried_forward_is_silently_reaffirmed() -> None:
    _check(at="2025-09-01", limits="x", complete=True,
           against_baseline="Yes", manual_way="Yes, somebody did the work")
    carried = checks.carry_forward("7QHC26")
    assert carried["manual_way"]["answer"] == "Yes, somebody did the work"
    assert carried["manual_way"]["last_answered"] == "2025-09-01"
    assert carried["manual_way"]["state"] == checks.NOBODY_SAID_EITHER_WAY
    assert checks.STILL_TRUE in carried["manual_way"]["controls"]


def test_nothing_carries_forward_on_a_first_check() -> None:
    assert checks.carry_forward("7QHC26") == {}


def test_the_app_works_out_no_drift_figure() -> None:
    assert "no drift figure" in checks.NO_DRIFT_FIGURE
    assert "no trend line" in checks.NO_DRIFT_FIGURE


def test_a_version_that_went_live_unchecked_is_not_a_reprimand() -> None:
    assert "ordinary organization" in checks.WENT_LIVE_UNCHECKED
    assert "Write the check anyway" in checks.WENT_LIVE_UNCHECKED


# -------------------------------------------------- 11 · the incident record

def test_anybody_may_write_an_incident_down() -> None:
    """A reporting route that depends on holding a hat is a reporting route
    people go around."""
    row = _incident(signed_in=False)
    assert row["signed_in"] is False
    assert "no login" in checks.ANYONE_CAN_WRITE_IT


def test_a_report_counts_without_a_name() -> None:
    assert "Leave your name off" in checks.VISIBLE_TO_EVERYONE
    assert "the report still counts" in checks.VISIBLE_TO_EVERYONE


def test_the_stop_route_speaks_in_the_third_person_to_the_public() -> None:
    assert "you said" in checks.stop_route("the duty officer")
    public = checks.stop_route("the duty officer", signed_in=False,
                               organisation="Mesa County")
    assert "Mesa County recorded" in public
    assert "you said" not in public


def test_no_route_is_ever_invented() -> None:
    said = checks.stop_route("")
    assert "Nobody has written down where a problem goes" in said
    assert "[Role]" in said


def test_internal_role_titles_are_not_read_out_on_the_public_page() -> None:
    public = checks.stop_route("the front desk", signed_in=False,
                               organisation="Mesa County")
    assert "Chief of Staff" not in public


# --------------------------------------------------- what it never writes

def test_this_surface_never_writes_the_baseline() -> None:
    for never in checks.NEVER_WRITES:
        assert never
    said = " ".join(checks.NEVER_WRITES)
    assert "written at Procure" in said
    assert "Projects commits it" in said


def test_a_check_never_carries_a_baseline_field_of_its_own() -> None:
    row = _check(against_baseline="Yes")
    assert "baseline" not in [k for k in row if k == "baseline"]
    assert row["against_baseline"] == "Yes"


# ------------------------------------------------------------ house language

def test_no_banned_word_reaches_this_surface() -> None:
    surface = repr(checks.report())
    copy = " ".join([
        surface, checks.FINDINGS_ARE_COMPARISONS, checks.LIMITS_REQUIRED,
        checks.LIMITS_GUIDANCE, checks.ONLY_THE_PROJECT,
        checks.ANYONE_CAN_WRITE_IT, checks.WHAT_THE_WATCHES_CANNOT_DO,
        checks.NOWHERE_TO_TRY_IT, checks.NO_DRIFT_FIGURE,
        checks.WENT_LIVE_UNCHECKED, checks.STOPPING_RULE_GUIDANCE,
        " ".join(checks.WILL_NOT_RAISE),
    ]).lower()
    for banned in spine.BANNED_IN_COPY:
        # "Deploy" is a gate name and the only sanctioned use of that root.
        assert banned not in spine.banned_in(copy), banned


def test_no_other_organisation_is_ever_named() -> None:
    surface = repr(checks.report()).lower()
    for word in ("other agencies", "other organizations", "peer agency",
                 "across accounts", "benchmark"):
        assert word not in surface


def test_the_register_survives_a_corrupt_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "broken.json"
    path.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(checks, "_file", lambda: path)
    assert checks.all_entries() == []
    assert checks.counters()["checks_recorded"] == 0
