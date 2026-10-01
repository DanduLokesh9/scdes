"""Registry — the catalog searched when somebody has a problem.

The whole surface turns on one field: which units here already hold each
tool, and what they use it for. A unit with a problem does not know what the
unit down the hall already owns, and that is the most expensive ignorance in
a government.

So most of these tests are about the search order and about the things the
surface refuses to do with it — no ranking inside a band, no recommended
badge, no collapsing an empty band, and never a recommendation of a vendor.
An empty second band is itself an answer, and hiding it would throw that
answer away.
"""

from __future__ import annotations

import pytest

from app import catalog, spine
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(catalog, "_file", lambda: tmp_path / "c.json")
    monkeypatch.setattr(catalog, "_record", lambda *a, **k: None)
    yield


def _tool(name: str, **over):
    made = catalog.add(name, WHO, **over)
    assert made["ok"], made
    return made["tool"]


# --------------------------------------------------------------- the form

def test_only_the_name_is_required() -> None:
    """A catalog that refuses a row until every box is filled is one nobody
    finishes."""
    assert catalog.add("Permit summarizer", WHO)["ok"]
    assert not catalog.add("  ", WHO)["ok"]


def test_a_tool_can_have_no_supplier() -> None:
    """One supplier sells several tools, and a tool can have no supplier at
    all where somebody built it."""
    assert _tool("Something we wrote")["supplier"] == ""


# ------------------------------------------------- the field it exists for

def test_holding_a_tool_records_the_unit_and_what_it_is_used_for() -> None:
    """"The planning office has this and uses it for permit summaries" is
    often what stops a purchase."""
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "the planning office", WHO,
                 used_for="permit summaries")
    held = catalog.one(tool["ref"])["held_by"]
    assert held == [{"unit": "the planning office",
                     "used_for": "permit summaries"}]


def test_recording_the_same_unit_twice_updates_rather_than_duplicates() -> None:
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "Planning", WHO, used_for="summaries")
    catalog.hold(tool["ref"], "planning", WHO, used_for="summaries and notes")
    held = catalog.one(tool["ref"])["held_by"]
    assert len(held) == 1
    assert held[0]["used_for"] == "summaries and notes"


def test_a_holding_needs_a_unit_named() -> None:
    tool = _tool("Summarizer")
    assert not catalog.hold(tool["ref"], "  ", WHO)["ok"]


# -------------------------------------------------------------- the search

def test_the_four_bands_come_back_in_hierarchy_order() -> None:
    """The ordering is how this surface gives its guidance — in that
    sequence rather than by relevance, price or alphabet."""
    bands = catalog.search("")
    assert [b["band"] for b in bands] == list(catalog.BANDS)
    assert [b["step"] for b in bands] == [2, 3, 4, 6]


def test_the_bands_match_the_hierarchy_steps_the_spine_sets() -> None:
    """Checked against the spine rather than trusted."""
    by_number = {s.number: s for s in spine.HIERARCHY}
    for band, step in catalog.BAND_STEPS.items():
        assert step in by_number, band
    assert by_number[2].name == "Fix it in house now"
    assert by_number[3].name == "Another business unit"
    assert by_number[6].name == "An external vendor's tool"


def test_a_tool_this_unit_holds_lands_in_the_first_band() -> None:
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "Planning", WHO, used_for="summaries")
    bands = {b["band"]: b["tools"] for b in catalog.search("", unit="Planning")}
    assert [t["ref"] for t in bands[catalog.BAND_ALREADY_RUN]] == [tool["ref"]]
    assert bands[catalog.BAND_ANOTHER_UNIT] == []


def test_a_tool_another_unit_holds_lands_in_the_second_band() -> None:
    """The most valuable band, and the reason the surface exists."""
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "Planning", WHO, used_for="permit summaries")
    bands = {b["band"]: b["tools"] for b in catalog.search("", unit="Works")}
    assert [t["ref"] for t in bands[catalog.BAND_ANOTHER_UNIT]] == [
        tool["ref"]]
    # And it carries what they use it for, which is the actionable part.
    assert bands[catalog.BAND_ANOTHER_UNIT][0]["held_by"][0]["used_for"] == (
        "permit summaries")


def test_a_piggyback_route_lands_in_the_third_band() -> None:
    _tool("Statewide thing", availability=[catalog.ON_COOPERATIVE])
    bands = {b["band"]: b["tools"] for b in catalog.search("")}
    assert len(bands[catalog.BAND_PIGGYBACK]) == 1
    assert bands[catalog.BAND_WOULD_BUY] == []


def test_everything_else_is_the_remainder() -> None:
    _tool("Something new")
    bands = {b["band"]: b["tools"] for b in catalog.search("")}
    assert len(bands[catalog.BAND_WOULD_BUY]) == 1


def test_an_empty_band_says_so_rather_than_closing_up() -> None:
    """An empty second band is itself an answer."""
    _tool("Something new")
    for band in catalog.search(""):
        assert band["empty_says"]
        if not band["tools"]:
            assert band["empty_says"].startswith("Nothing")


def test_a_one_unit_organisation_never_sees_the_second_band() -> None:
    """Its absence is never explained."""
    bands = catalog.search("", one_unit_organisation=True)
    names = [b["band"] for b in bands]
    assert catalog.BAND_ANOTHER_UNIT not in names
    assert len(names) == 3


def test_nothing_is_ranked_within_a_band() -> None:
    """No relevance score, no star, no recommended badge. Ranking happens at
    a purchase decision, on the organization's own weights, on the
    project."""
    for name in ("Alpha", "Beta", "Gamma"):
        _tool(name)
    band = [b for b in catalog.search("")
            if b["band"] == catalog.BAND_WOULD_BUY][0]
    for tool in band["tools"]:
        for scoring in ("score", "rank", "relevance", "recommended",
                        "stars", "rating"):
            assert scoring not in tool, scoring


def test_the_surface_never_recommends_a_vendor() -> None:
    said = catalog.NEVER_RECOMMENDS.lower()
    assert "does not recommend" in said
    assert "does not rank" in said


def test_search_terms_reach_what_a_unit_uses_it_for() -> None:
    """Somebody searching for their problem should find the tool another
    unit bought for that problem."""
    tool = _tool("Generic Platform")
    catalog.hold(tool["ref"], "Planning", WHO, used_for="permit summaries")
    found = catalog.search("permit")
    assert any(b["tools"] for b in found)


# ------------------------------------------------------------- counters

def test_held_on_no_project_is_the_honest_counter() -> None:
    """A tool the organization holds that no project accounts for is a tool
    nobody governs. The most common thing an organization discovers in its
    first month."""
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "Planning", WHO)
    got = catalog.counters()
    assert got["held_on_no_project"] == 1
    assert "ordinary way this starts" in got["says"]["held_on_no_project"]


def test_the_cross_utility_counter_explains_itself() -> None:
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "Planning", WHO)
    catalog.hold(tool["ref"], "Works", WHO)
    got = catalog.counters()
    assert got["held_by_more_than_one"] == 1
    assert "a third unit probably does not know" in (
        got["says"]["held_by_more_than_one"])


def test_a_one_unit_organisation_never_sees_that_counter() -> None:
    got = catalog.counters(one_unit_organisation=True)
    assert "held_by_more_than_one" not in got
    assert "held_by_more_than_one" not in got["says"]


def test_no_counter_is_a_score() -> None:
    _tool("A")
    got = catalog.counters()
    for key, value in got.items():
        if key == "says":
            continue
        assert isinstance(value, int), key


# -------------------------------------------------------------- findings

def test_a_held_tool_no_project_explains_is_named() -> None:
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "the planning office", WHO)
    found = catalog.findings()
    hit = [f for f in found if f["id"] == "finding.rg.held_ungoverned"]
    assert hit
    assert "the planning office" in hit[0]["says"]


def test_a_holder_the_framework_no_longer_lists_is_flagged() -> None:
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "the mapping bureau", WHO)
    found = catalog.findings(units=["Planning", "Works"])
    hit = [f for f in found if f["id"] == "finding.rg.holder_gone"]
    assert hit
    assert "the mapping bureau" in hit[0]["says"]


def test_a_known_holder_raises_nothing() -> None:
    tool = _tool("Summarizer")
    catalog.hold(tool["ref"], "Planning", WHO)
    found = {f["id"] for f in catalog.findings(units=["Planning"])}
    assert "finding.rg.holder_gone" not in found


def test_a_duplicate_purchase_is_never_a_reprimand() -> None:
    """There are good reasons to buy a second thing."""
    said = catalog.DUPLICATE_IS_NOT_A_REPRIMAND.lower()
    assert "good reasons to buy a second one" in said
    for blame in ("waste", "should not", "avoid", "mistake", "failure"):
        assert blame not in said


def test_no_finding_is_raised_against_anything_outside() -> None:
    for finding in catalog.OWN_FINDINGS:
        said = (finding.says + " " + finding.trigger).lower()
        for outside in ("industry", "benchmark", "best practice", "peers",
                        "maturity"):
            assert outside not in said, finding.id


def test_nothing_here_gates_anything() -> None:
    """No project is refused for anything recorded or missing here."""
    assert all(g.owner != "Registry" for g in spine.GATES)


# ------------------------------------------------------------- the list

def test_held_tools_sort_first_by_default() -> None:
    """The default sort applies the same hierarchy as the search."""
    _tool("Zebra")
    tool = _tool("Aardvark")
    held = _tool("Middle")
    catalog.hold(held["ref"], "Planning", WHO)
    assert [t["name"] for t in catalog.sorted_tools()] == [
        "Middle", "Aardvark", "Zebra"]


def test_held_by_is_shown_as_names_not_a_count() -> None:
    """The name is the actionable part."""
    assert "Held by" in catalog.COLUMNS
    assert "How many units" not in catalog.COLUMNS


def test_the_empty_state_says_where_to_start() -> None:
    said = catalog.empty_state().lower()
    assert "start with the tools you already pay for" in said


def test_seeded_tools_credit_their_own_framework() -> None:
    said = catalog.empty_state(seeded=5)
    assert "5 tools you already have" in said
    assert "came from your framework" in said


def test_the_whole_surface_serialises() -> None:
    import json
    _tool("A")
    json.dumps(catalog.report())
