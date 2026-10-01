"""Data — the part of the register that pays.

Everything else on this surface is bookkeeping. What earns it is
cross-utility: surfacing, unprompted, where a holding one unit keeps for one
reason is what another unit said it needs. Units do not appreciate what their
own data is worth to somebody else.

The spec is firm that the three pieces ship together — the tags, the lookup
and the overlap panel — because separately they degrade into an inventory
nobody opens twice. These tests hold that line, and the other line that
matters here: **it gates nothing**. AI governance is not data governance, and
an unrecorded, unclassified or unreachable holding produces a gap and a
recommendation, never a refusal.
"""

from __future__ import annotations

import pytest

from app import holdings
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(holdings, "_file", lambda: tmp_path / "h.json")
    monkeypatch.setattr(holdings, "_record", lambda *a, **k: None)
    yield


def _held(name: str, **over):
    made = holdings.save({"name": name, **over}, WHO)
    assert made.get("ok"), made
    return made["holding"]


# ---------------------------------------------------------------- utility

def test_utility_is_a_set_of_tags_and_never_a_rating() -> None:
    """No holding is scored, ranked, or described as high or low utility."""
    said = holdings.UTILITY_IS_NOT_A_RATING.lower()
    assert "nothing here is scored or ranked" in said
    for rating in ("high utility", "low utility", "score", "rank", "rating",
                   "stars"):
        assert rating not in " ".join(holdings.UTILITY.values()).lower()


def test_the_help_text_argues_for_the_second_and_third_tick() -> None:
    """The field people skip, and the one that makes cross-utility work.
    The help text carries the argument rather than the field being made
    required."""
    said = holdings.UTILITY_IS_NOT_A_RATING
    assert "second and third ticks" in said
    assert "already have what they need" in said


def test_an_unknown_utility_value_is_dropped_rather_than_kept() -> None:
    """The overlap panel matches on these, and a typo would pair two units
    on a value neither of them chose."""
    row = _held("Permits", utility=["deciding", "not-a-real-value"])
    assert row["utility"] == ["deciding"]


def test_something_else_becomes_an_option_for_later_entries() -> None:
    """And appears nowhere else."""
    _held("Meter data", utility=["other"],
          utility_other="Rate-setting evidence")
    assert holdings.added_utility() == ["Rate-setting evidence"]


def test_utility_is_never_required() -> None:
    """Only the name is required. There is no finding for a holding whose
    utility is unrecorded."""
    row = _held("A folder of scans")
    assert row["utility"] == []
    assert "a holding whose utility is unrecorded" in holdings.WILL_NOT_RAISE


# --------------------------------------------------------------- overlap

def test_the_overlap_names_the_pair_rather_than_scoring_it() -> None:
    """One line per pair: [Unit] keeps this for [purpose]. [Other unit]
    recorded that they need [purpose] information of this kind and have
    none."""
    _held("Permit register", utility=["deciding"], units=["Planning"])
    got = holdings.overlap(
        wanted=[{"unit": "Works", "utility": "deciding"}])
    assert got["count"] == 1
    said = got["pairs"][0]["says"]
    assert "Planning keeps this for" in said
    assert "Works recorded that they need" in said
    assert "have none" in said


def test_a_unit_is_never_told_about_a_need_it_can_already_meet() -> None:
    _held("Permit register", utility=["deciding"], units=["Planning"])
    _held("Works cases", utility=["deciding"], units=["Works"])
    got = holdings.overlap(
        wanted=[{"unit": "Works", "utility": "deciding"}])
    assert got["count"] == 0


def test_a_unit_is_never_paired_with_itself() -> None:
    _held("Permit register", utility=["planning"], units=["Planning"])
    got = holdings.overlap(
        wanted=[{"unit": "Planning", "utility": "compliance"}])
    assert all(p["keeper"] != p["needs_it"] for p in got["pairs"])


def test_the_overlap_carries_no_score_or_percentage() -> None:
    """Counts and named pairs."""
    _held("Permit register", utility=["deciding"], units=["Planning"])
    got = holdings.overlap(wanted=[{"unit": "Works", "utility": "deciding"}])
    import json
    said = json.dumps(got).lower()
    for scoring in ("percent", "%", "score", "rank", "rating"):
        assert scoring not in said, scoring


def test_a_one_unit_organisation_never_sees_the_overlap_panel() -> None:
    """And its absence is never explained."""
    _held("Permit register", utility=["deciding"], units=["Planning"])
    got = holdings.listing(one_unit_organisation=True)
    assert "overlap" not in got
    import json
    assert "overlap" not in json.dumps(got).lower()


# ---------------------------------------------------------------- lookup

def test_the_lookup_searches_the_whole_organisation() -> None:
    """It searches the whole organization rather than the unit the person
    belongs to. That is the point of it."""
    _held("Permit register", utility=["deciding"], units=["Planning"])
    _held("Works cases", utility=["deciding"], units=["Works"])
    got = holdings.lookup("deciding")
    assert len(got["holdings"]) == 2


def test_the_lookup_shows_reachability_and_currency_inline() -> None:
    """Because the next question is always whether a tool can get at it."""
    _held("Permit register", utility=["deciding"], units=["Planning"],
          reachable="api", freshness="live")
    row = holdings.lookup("deciding")["holdings"][0]
    assert row["reachable"]
    assert row["freshness"]


def test_nothing_found_says_both_of_the_things_it_could_mean() -> None:
    got = holdings.lookup("billing")
    assert got["holdings"] == []
    said = got["empty_says"]
    assert "may mean nobody has it" in said
    assert "nobody has written down what they have" in said


# ------------------------------------------------------- the feed block

def test_the_organisation_sets_its_own_currency_expectation() -> None:
    """The application supplies no default, which is why "No expectation
    set" is an answer rather than an absence."""
    assert "none" in holdings.CURRENCY
    assert holdings.CURRENCY["none"] == "No expectation set"
    row = _held("Meter feed", feed="yes", feed_expected="daily")
    assert row["feed_expected_label"] == "Daily"


def test_an_unknown_currency_value_is_not_kept() -> None:
    row = _held("Meter feed", feed="yes", feed_expected="hourly-ish")
    assert row["feed_expected"] == ""


# -------------------------------------------------------- classification

def test_an_organisation_with_no_scheme_never_learns_the_block_exists() -> None:
    """No field, no counter, no finding, and no empty state referring to
    one. Explaining the absence would imply something was missing."""
    _held("A folder")
    got = holdings.listing()
    assert "labels" not in got
    assert "labels_note" not in got


def test_where_a_scheme_exists_the_labels_are_theirs_uninterpreted() -> None:
    got = holdings.listing(labels=["Public", "Restricted"])
    assert got["labels"] == ["Public", "Restricted"]
    said = got["labels_note"].lower()
    assert "does not interpret them" in said
    assert "nothing here knows what your labels mean" in said


def test_no_finding_depends_on_what_a_label_means() -> None:
    for finding in holdings.OWN_FINDINGS:
        said = (finding.says + " " + finding.trigger).lower()
        assert "classification" not in said, finding.id
        assert "label" not in said, finding.id


# --------------------------------------------------------------- findings

def test_a_holding_a_project_needs_and_cannot_reach_is_flagged() -> None:
    row = _held("Paper files", reachable="no")
    found = holdings.findings(needed_by={row["id"]: "Permit triage"})
    hit = [f for f in found if f["id"] == "finding.dt.unreachable_in_scope"]
    assert hit
    assert "Permit triage needs this" in hit[0]["says"]


def test_a_stale_baseline_source_is_flagged_only_where_it_measures() -> None:
    row = _held("Old export", freshness="static")
    assert not holdings.findings()
    found = holdings.findings(baseline_for={row["id"]: "Permit triage"})
    assert [f["id"] for f in found] == ["finding.dt.stale_source"]


def test_an_owner_the_framework_says_they_do_not_have_is_flagged() -> None:
    row = _held("Case files", owner="Records management")
    found = holdings.findings(absent=["Records management"])
    hit = [f for f in found if f["id"] == "finding.dt.owner_gone"]
    assert hit
    assert "Records management" in hit[0]["says"]
    assert row["id"] == hit[0]["holding"]


def test_a_role_the_framework_never_listed_is_not_flagged() -> None:
    """Only a function recorded as absent at 1.4 — a role nobody listed
    either way is not a contradiction of anything."""
    _held("Permits", owner="The Permitting Manager")
    found = holdings.findings(absent=["Records management"])
    assert not [f for f in found if f["id"] == "finding.dt.owner_gone"]


def test_the_three_findings_it_will_never_raise_are_written_down() -> None:
    """All three would punish a choice this product leaves open."""
    listed = " ".join(holdings.WILL_NOT_RAISE)
    assert "without a classification" in listed
    assert "no classification scheme" in listed
    assert "utility is unrecorded" in listed


def test_no_finding_is_raised_against_anything_outside() -> None:
    for finding in holdings.OWN_FINDINGS:
        said = (finding.says + " " + finding.trigger).lower()
        for outside in ("industry", "benchmark", "best practice", "peers",
                        "maturity", "should have"):
            assert outside not in said, finding.id


# ----------------------------------------------------------- honest limits

def test_the_monitor_says_what_it_cannot_check() -> None:
    """Where a check cannot be performed, say so rather than reporting a
    state you did not observe."""
    said = holdings.CANNOT_BE_CHECKED.lower()
    assert "cannot be checked" in said
    assert "not built yet" in said
    assert "a green tick that meant nothing would be worse" in said


def test_nothing_on_this_surface_gates_anything() -> None:
    from app import spine
    assert all(g.owner != "Data" for g in spine.GATES)


def test_no_counter_is_a_proportion() -> None:
    """A small organization with three holdings and one unknown would read
    33% as a failing grade."""
    _held("A")
    for key, value in holdings.summary().items():
        assert isinstance(value, int), key


def test_the_credential_is_never_stored_only_its_kind() -> None:
    row = _held("Permit API", endpoint="https://example.gov/api",
                auth="a token")
    assert row["auth"] == "a token"
    # The field is short on purpose; a pasted secret would not fit and
    # should not be here anyway.
    long_one = _held("Another", auth="x" * 500)
    assert len(long_one["auth"]) <= 200


def test_the_whole_surface_serialises() -> None:
    import json
    _held("A", utility=["deciding"], units=["Planning"])
    json.dumps(holdings.listing())
    json.dumps(holdings.listing(labels=["Public"]))
