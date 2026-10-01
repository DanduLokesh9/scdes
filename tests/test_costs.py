"""Budget — and the four numbers it refuses to compute.

Every figure on this surface is a place the software could have produced an
impressive number by inventing an input nobody agreed to. There is no
lifetime total, because that needs a number of years nobody has given it.
There is no return, no payback period and no ratio. Hours of staff time are
never turned into money, because an hour needs a rate. And a line that
cannot be annualized is excluded *and counted in a line that says so*,
rather than quietly dropped from a total somebody will quote in a meeting.

Most of what follows tests those refusals, because a total that silently
omits something is worse than no total at all.
"""

from __future__ import annotations

import pytest

from app import costs, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(costs, "_file", lambda: tmp_path / "c.json")
    monkeypatch.setattr(costs, "_record", lambda *a, **k: None)
    yield


def _line(**over):
    made = costs.add(actor=WHO, **{"kind": "licence", **over})
    assert made["ok"], made
    return made["line"]


# --------------------------------------------------------- the arithmetic

def test_a_year_is_taken_as_it_stands() -> None:
    assert costs.a_year(_line(basis="year", estimate=1200))[0] == 1200


def test_a_month_is_multiplied_by_twelve() -> None:
    assert costs.a_year(_line(basis="month", estimate=100))[0] == 1200


def test_per_person_reads_the_headcount_on_that_line() -> None:
    row = _line(basis="per_person_month", estimate=10, headcount=30)
    assert costs.a_year(row)[0] == 3600


def test_a_one_off_is_never_annualised() -> None:
    year, once, why = costs.a_year(_line(basis="one_off", estimate=5000))
    assert year == 0
    assert once == 5000
    assert why == ""


def test_the_actual_beats_the_estimate_wherever_both_exist() -> None:
    row = _line(basis="year", estimate=1000, actual=1450)
    assert costs.figure(row) == 1450
    assert costs.a_year(row)[0] == 1450


def test_one_of_the_two_numbers_is_read_where_only_one_exists() -> None:
    assert costs.figure(_line(basis="year", estimate=900)) == 900
    assert costs.figure(_line(basis="year", actual=900)) == 900


# ------------------------------------------------- what it will not guess

@pytest.mark.parametrize("over,why", [
    ({"basis": "per_person_month", "estimate": 10},
     costs.NO_HEADCOUNT),
    ({"basis": "by_use", "estimate": 500}, costs.BY_USE_WHY),
    ({"basis": "unsure", "estimate": 500}, costs.NO_BASIS),
    ({"estimate": 500}, costs.NO_BASIS),
    ({"basis": "year"}, costs.NO_NUMBER),
])
def test_a_line_it_cannot_annualise_says_why(over, why) -> None:
    """Excluded and counted, never quietly dropped. A figure that silently
    omitted something would understate the money the organization carries."""
    year, once, said = costs.a_year(_line(**over))
    assert year == 0 and once == 0
    assert said == why


def test_the_application_will_not_guess_a_headcount() -> None:
    """It does not have the organization's headcount."""
    assert costs.a_year(
        _line(basis="per_person_month", estimate=10, headcount=0))[0] == 0


def test_an_amount_without_a_basis_could_be_a_month_or_a_decade() -> None:
    assert costs.a_year(_line(estimate=99999))[2] == costs.NO_BASIS


def test_no_charge_contributes_zero_and_is_included() -> None:
    year, once, why = costs.a_year(_line(basis="no_charge"))
    assert (year, once, why) == (0.0, 0.0, "")


def test_hours_are_never_turned_into_money() -> None:
    """An hour needs a rate, and this application does not have one."""
    got = costs.totals([_line(basis="year", estimate=1000,
                              hours_a_year=200, hours_one_off=40)])
    assert got["a_year"] == 1000
    assert got["hours_a_year"] == 200
    assert got["hours_one_off"] == 40


def test_hours_with_no_money_are_still_reported() -> None:
    """An hour that was captured and then reported nowhere is an hour the
    register lost."""
    _line(kind="staff_time", hours_a_year=300)
    strip = costs.money_strip()
    assert any("hours of staff time with no money" in s
               for s in strip["conditional"])


# --------------------------------------------------------- the money strip

def test_the_three_headline_sentences_always_render() -> None:
    _line(basis="year", estimate=1200, committed=True, not_one_project=True)
    strip = costs.money_strip()
    assert len(strip["headline"]) == 3
    assert "committed on everything you are running or trialling" in (
        strip["headline"][0])
    assert "committed or not" in strip["headline"][1]
    assert "what it would cost to leave" in strip["headline"][2]


def test_a_conditional_line_renders_only_above_zero() -> None:
    _line(basis="year", estimate=1200, committed=True, not_one_project=True)
    strip = costs.money_strip()
    assert not any("still committed on tools you have retired" in s
                   for s in strip["conditional"])


def test_money_on_a_retired_tool_is_said_out_loud() -> None:
    _line(basis="year", estimate=800, committed=True, project="P1")
    strip = costs.money_strip(
        projects={"P1": {"state": spine.RETIRED, "gate": spine.SUNSET}})
    assert any("still committed on tools you have retired" in s
               for s in strip["conditional"])


def test_a_trialled_tool_counts_because_the_money_is_being_spent() -> None:
    """A tool being trialled has reached Test, and the money on it is being
    spent whatever the trial concludes."""
    _line(basis="year", estimate=500, committed=True, project="P1")
    strip = costs.money_strip(
        projects={"P1": {"gate": spine.TEST, "state": spine.BEING_WORKED,
                         "in_use": spine.IN_USE_NO}})
    assert strip["committed_running"]["a_year"] == 500


def test_a_cost_with_no_project_is_money_carried_today() -> None:
    """The money it takes to run the governance work itself has no project
    to read, and dropping it would understate what is carried."""
    _line(basis="year", estimate=400, committed=True, not_one_project=True)
    assert costs.money_strip()["committed_running"]["a_year"] == 400


def test_what_a_change_cost_is_told_apart_from_what_it_cost_to_buy() -> None:
    _line(basis="year", estimate=300, version="v2")
    strip = costs.money_strip()
    assert any("arrived with a change a vendor made" in s
               for s in strip["conditional"])


def test_only_open_lines_reach_a_figure() -> None:
    """Money that has stopped is history rather than a commitment."""
    row = _line(basis="year", estimate=1000, committed=True,
                not_one_project=True)
    held = costs._read()
    held["lines"][row["ref"]]["status"] = costs.ENDED
    costs._write(held)
    assert costs.money_strip()["everything"]["a_year"] == 0
    # And it is still on the register.
    assert costs.counters()["recorded"] == 1


# ------------------------------------------------- the refusals, in words

def test_there_is_no_lifetime_total_anywhere() -> None:
    """A total built on a guessed life span would be the number quoted back
    in the meeting."""
    said = costs.NO_LIFETIME_TOTAL.lower()
    assert "no lifetime total" in said
    assert "nobody has told this application how long" in said
    assert "multiply the yearly figure by the number of years" in said

    # Checked against the report's *field names* rather than its text. An
    # earlier version matched substrings and tripped on `no_lifetime_total`
    # — the disclaimer saying there is no lifetime total — which is the one
    # place those words are supposed to appear.
    def keys(blob, found=None):
        found = found if found is not None else set()
        if isinstance(blob, dict):
            for key, value in blob.items():
                found.add(str(key).lower())
                keys(value, found)
        elif isinstance(blob, list):
            for item in blob:
                keys(item, found)
        return found

    named = keys(costs.report())
    for invented in ("lifetime_total", "lifetime", "total_cost_of_ownership",
                     "tco", "payback", "roi", "return_on", "net_benefit"):
        assert invented not in named, invented


def test_it_computes_no_return_and_no_ratio() -> None:
    said = costs.NO_RETURN.lower()
    assert "not turned into a figure here" in said
    assert "payback period" in said
    assert "one half of that question" in said


def test_the_business_case_figure_is_computed_not_typed() -> None:
    """A business case with its own editable cost box disagrees with the
    register by the second week."""
    _line(basis="year", estimate=1200, project="P1")
    got = costs.full_cost("P1")
    assert got["a_year"] == 1200
    assert "no_lifetime_total" in got
    # Nothing a person could key a number into.
    assert "input" not in got


def test_a_ticked_kind_with_nothing_recorded_is_named() -> None:
    """Rather than presenting a total that quietly left something out."""
    _line(kind="licence", basis="year", estimate=1000, project="P1")
    got = costs.full_cost("P1", counts_as_cost=["licence", "training",
                                                "exit"])
    missing = {m["kind"] for m in got["nothing_recorded"]}
    assert missing == {"training", "exit"}
    assert all(m["says"] == "Nothing recorded"
               for m in got["nothing_recorded"])


def test_a_recorded_gap_counts_as_an_answer_and_a_blank_does_not() -> None:
    _line(kind="licence", basis="year", estimate=1000, project="P1")
    got = costs.full_cost("P1", counts_as_cost=["licence", "training"],
                          gaps=["training"])
    assert got["nothing_recorded"] == []


# ------------------------------------------------------------- counters

def test_the_register_never_shrinks() -> None:
    row = _line(basis="year", estimate=100)
    held = costs._read()
    held["lines"][row["ref"]]["status"] = costs.WITHDRAWN
    costs._write(held)
    assert costs.counters()["recorded"] == 1


def test_with_no_list_of_kinds_the_counter_drops_its_denominator() -> None:
    """It never measures a project against a list of kinds the organization
    did not tick."""
    _line(basis="year", estimate=100, project="P1")
    got = costs.counters()
    assert got["full_cost_estimated"] == 1
    assert "have not said what counts as cost" in (
        got["says"]["full_cost_estimated"])


def test_with_a_list_every_kind_must_be_answered() -> None:
    _line(kind="licence", basis="year", estimate=100, project="P1")
    got = costs.counters(counts_as_cost=["licence", "exit"])
    assert got["full_cost_estimated"] == 0
    got = costs.counters(counts_as_cost=["licence", "exit"],
                         gaps_by_project={"P1": ["exit"]})
    assert got["full_cost_estimated"] == 1


def test_the_cost_of_leaving_is_counted_whether_or_not_they_ticked_it() -> None:
    """The one most organizations find out about late. Nothing here will be
    flagged for it."""
    _line(kind="licence", basis="year", estimate=100, project="P1")
    got = costs.counters()
    assert got["no_cost_of_leaving"] == 1
    said = got["says"]["no_cost_of_leaving"].lower()
    assert "whether or not you said it counts as cost" in said
    assert "nothing here will be flagged for it" in said


def test_no_number_against_it_is_this_surfaces_own_phrase() -> None:
    """The obvious phrase from the shared bank is already taken by another
    surface over a different population. Two surfaces showing one counter
    name over two populations is the confusion the bank exists to
    prevent."""
    assert costs.OWN_COUNTER_NAME == "No number against it"
    assert costs.OWN_COUNTER_NAME not in spine.ABSENCE_COUNTERS
    assert "Recorded as unknown" in spine.ABSENCE_COUNTERS


def test_every_counter_is_a_plain_count() -> None:
    _line(basis="year", estimate=100)
    for key, value in costs.counters().items():
        if key == "says":
            continue
        assert isinstance(value, int), key


# -------------------------------------------------------------- findings

def test_costing_more_than_estimated_is_stated_without_blame() -> None:
    _line(basis="year", estimate=1000, actual=1400)
    # 3.3 exists only where they adopted lifetime-cost tracking, and fires
    # only past the difference they said is worth a conversation.
    assert not costs.findings()
    found = costs.findings(tracks_lifetime=True,
                           difference={"mode": "Any difference at all"})
    hit = [f for f in found if f["id"] == "finding.budget.over_estimate"]
    assert hit
    said = hit[0]["says"].lower()
    for blame in ("overspend", "failure", "should", "poor", "overrun"):
        assert blame not in said


def test_a_disagreement_with_the_supplier_is_shown_not_resolved() -> None:
    """The application has no way of knowing which of the two numbers you
    typed is the right one."""
    _line(kind="licence", basis="year", estimate=1200, project="P1")
    found = costs.findings(vendor_price={"P1": 1500})
    hit = [f for f in found
           if f["id"] == "finding.budget.price_disagrees"]
    assert hit
    assert "$1,200" in hit[0]["says"] and "$1,500" in hit[0]["says"]


def test_a_line_still_open_on_a_retired_tool_is_a_finding() -> None:
    _line(basis="year", estimate=900, committed=True, project="P1")
    found = {f["id"] for f in costs.findings(
        projects={"P1": {"state": spine.RETIRED}})}
    assert "finding.budget.line_open_after_retirement" in found


def test_no_finding_is_raised_against_anything_outside() -> None:
    for finding in costs.OWN_FINDINGS:
        said = (finding.says + " " + finding.trigger).lower()
        for outside in ("industry", "benchmark", "market rate", "peers",
                        "typical", "average for"):
            assert outside not in said, finding.id


# ------------------------------------------------------------ the record

def test_a_line_proposed_and_never_committed_is_still_a_line() -> None:
    row = _line(basis="year", estimate=100, committed=False)
    assert row["status"] == costs.OPEN
    assert costs.counters()["recorded"] == 1


def test_an_unknown_kind_is_refused() -> None:
    assert not costs.add(kind="vibes", actor=WHO)["ok"]


def test_the_kinds_are_module_ones_keys_in_its_order() -> None:
    """They had drifted: "leaving" here, "exit" in the framework, so a kind
    the framework ticked was invisible to this surface."""
    from app import module_one
    q = module_one.by_key("proc.cost_parts")
    theirs = [o.value for o in q.options if o.value != module_one.UNKNOWN]
    assert list(costs.FRAMEWORK_KINDS) == theirs


def test_a_row_saved_under_an_old_kind_is_read_under_the_framework_key() -> None:
    held = costs._read()
    held["lines"]["C-OLD"] = {"ref": "C-OLD", "kind": "leaving",
                              "status": costs.OPEN, "project": "P1"}
    held["lines"]["C-OLD2"] = {"ref": "C-OLD2", "kind": "storage",
                               "status": costs.OPEN}
    costs._write(held)
    rows = {r["ref"]: r for r in costs.all_lines()}
    assert rows["C-OLD"]["kind"] == "exit"
    assert rows["C-OLD"]["projects"] == ["P1"]
    assert rows["C-OLD2"]["kind"] == "other"
    assert rows["C-OLD2"]["other_kind"] == "Storage and infrastructure"


def test_this_surface_gates_nothing() -> None:
    assert all(g.owner != "Budget" for g in spine.GATES)


def test_the_whole_surface_serialises() -> None:
    import json
    _line(basis="year", estimate=100, project="P1")
    json.dumps(costs.report())
