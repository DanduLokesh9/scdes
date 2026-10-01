"""The Data surface as a whole — spec Data §2 to §15.

What these pin: findings come only from the organization's own answers; the
overlap is computed from what projects at Identify said they need, and does
not appear with one unit; every "We are not sure" is a gap record; a watched
feed silent past their own tolerance is named, and never where they set none;
the three technical fields are the technology hat's only where 1.4 records a
technology function; classification exists only where labels are kept; and
nothing here refuses a project.
"""

from __future__ import annotations

import pytest

from app import holdings, server
from app.authz import Actor, Role

OT = Actor("t.one", "", Role.OT)
USER = Actor("u.one", "", Role.OPERATOR)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(holdings, "_file", lambda: tmp_path / "h.json")
    monkeypatch.setattr(holdings, "_record", lambda *a, **k: None)
    yield


def _held(name: str, **over):
    made = holdings.save({"name": name, **over}, OT)
    assert made.get("ok"), made
    return made["holding"]


def _project(ref="P1", name="Permit triage", **over):
    return {"ref": ref, "name": name, "state": "state.being_worked", **over}


# ------------------------------------------------------------ findings

def test_never_category_is_raised_only_where_a_live_project_reaches_it() -> None:
    row = _held("Case files", sensitive=["personal"])
    answers = {"data.never": ["personal"]}
    quiet = holdings.surface(answers=answers, projects=[])
    assert not [f for f in quiet["findings"] if f["id"] == "finding.never_category"]
    hit = holdings.surface(answers=answers, projects=[_project(holdings=[row["id"]])])
    said = [f["says"] for f in hit["findings"] if f["id"] == "finding.never_category"]
    assert said and said[0].startswith("You said never for") and "Permit triage reaches it" in said[0]


def test_a_turned_down_project_reaches_nothing() -> None:
    row = _held("Paper files", reachable="no")
    got = holdings.surface(answers={}, projects=[_project(state="state.turned_down",
                                                          holdings=[row["id"]])])
    assert not got["findings"]


def test_not_sure_is_a_gap_record_and_unowned_gaps_are_named() -> None:
    _held("The K drive", location="unknown")
    _held("Meter readings", freshness="unknown", owner="Operations Manager")
    got = holdings.surface(answers={}, projects=[])
    assert {g["name"] for g in got["gaps"]} == {"The K drive", "Meter readings"}
    unowned = [f for f in got["findings"] if f["id"] == "finding.gap_no_owner"]
    assert len(unowned) == 1 and "The K drive" in unowned[0]["says"]
    assert "nobody named to close it" in unowned[0]["says"]


def test_an_owner_recorded_as_absent_at_1_4_is_named() -> None:
    _held("Retention boxes", owner="Records management")
    got = holdings.surface(answers={"org.functions": {"records": "none", "it": "dedicated"}},
                           projects=[])
    assert [f for f in got["findings"] if f["id"] == "finding.dt.owner_gone"]
    assert got["inputs"]["absent_says"] == ["You said you have no records management."]


def test_a_silent_feed_is_named_only_past_their_own_tolerance() -> None:
    row = _held("Meter feed", feed="yes", feed_expected="daily", endpoint="https://x.test")
    check = {"state": "down", "history": [
        {"state": "down", "at": "2026-09-22T10:00:00+00:00"},
        {"state": "up", "at": "2026-09-20T09:00:00+00:00"}]}
    got = holdings.findings(checks={row["id"]: check}, now="2026-09-23T12:00:00+00:00")
    assert [f["says"] for f in got] == ["This has not answered since 2026-09-20."]
    soon = holdings.findings(checks={row["id"]: check}, now="2026-09-21T08:00:00+00:00")
    assert not soon


def test_no_expectation_set_tolerates_any_silence() -> None:
    row = _held("Old feed", feed="yes", feed_expected="none")
    check = {"state": "down", "history": [{"state": "up", "at": "2020-01-01T00:00:00+00:00"}]}
    assert not holdings.findings(checks={row["id"]: check})


# ------------------------------------------------------------ overlap

def test_the_overlap_reads_what_projects_said_they_need() -> None:
    _held("Permit register", utility=["deciding"], units=["Planning"])
    need = _project(problem={"info_for": ["deciding"], "unit": "Works"})
    got = holdings.surface(answers={}, projects=[need])
    assert got["overlap"]["count"] == 1
    assert got["overlap"]["says"] == ("1 holding is useful to somebody who does not "
                                      "know it exists.")


def test_with_one_unit_the_overlap_does_not_appear() -> None:
    _held("Permit register", utility=["deciding"], units=["Planning"])
    need = _project(problem={"info_for": ["deciding"], "unit": "Works"})
    got = holdings.surface(answers={"org.size": "u25"}, projects=[need])
    assert "overlap" not in got


def test_something_else_becomes_an_option_and_matches() -> None:
    _held("Grant files", utility=["custom:Grant reporting"], units=["Finance"])
    assert "Grant reporting" in holdings.added_utility()
    found = holdings.lookups(["custom:Grant reporting"])
    assert found[0]["holdings"][0]["name"] == "Grant files"
    got = holdings.overlap(wanted=[{"unit": "Parks", "utility": "custom:Grant reporting"}])
    assert got["count"] == 1


# ------------------------------------------------------------ the technology hat

def test_technical_fields_are_the_technology_hats_where_one_exists(monkeypatch) -> None:
    monkeypatch.setattr(server, "_framework_answers",
                        lambda: {"org.functions": {"it": "dedicated"}})
    monkeypatch.setattr(server, "_data_labels", lambda: [])
    refused = server.api_holding_save(USER, {"name": "Permits", "reachable": "api"}, {})
    assert refused["ok"] is False and "technology hat" in refused["error"]
    assert server.api_holding_save(USER, {"name": "Permits", "system": "Accela"}, {})["ok"]
    assert server.api_holding_save(OT, {"name": "Permits 2", "reachable": "api"}, {})["ok"]


def test_with_no_technology_function_the_fields_fold_to_whoever_is_here(monkeypatch) -> None:
    monkeypatch.setattr(server, "_framework_answers",
                        lambda: {"org.functions": {"it": "none"}})
    monkeypatch.setattr(server, "_data_labels", lambda: [])
    assert server.api_holding_save(USER, {"name": "Permits", "reachable": "api"}, {})["ok"]


# ------------------------------------------------------------ section 9

def test_classification_is_not_stored_without_labels() -> None:
    made = holdings.save({"name": "Permits", "classification": "Secret"}, OT, labels=[])
    raw = holdings._read()["holdings"][0]
    assert "classification" not in raw and "classification_why" not in raw
    assert "classification" not in holdings.listing()["holdings"][0]
    assert made["ok"]


def test_a_label_they_did_not_write_is_not_kept() -> None:
    holdings.save({"name": "Permits", "classification": "Made up"}, OT, labels=["Public"])
    assert holdings._read()["holdings"][0]["classification"] == ""
    holdings.save({"name": "Files", "classification": "Public"}, OT, labels=["Public"])
    assert holdings._read()["holdings"][1]["classification"] == "Public"


# ------------------------------------------------------------ 4.7

def test_confirming_a_feed_is_current_is_written_by_a_person() -> None:
    row = _held("Meter feed", feed="yes")
    assert holdings.confirm_current(row["id"], USER, on="2026-09-23")["on"] == "2026-09-23"
    assert holdings._read()["holdings"][0]["feed_confirmed"] == "2026-09-23"


# ------------------------------------------------------------ 15

def test_examples_follow_their_type_and_drop_where_none_is_given() -> None:
    assert "meter readings" in holdings.framework_inputs({"org.kind": "district"})["example"]
    assert holdings.framework_inputs({"org.kind": "tribal"})["example"] == ""
    assert holdings.framework_inputs({})["example"] == ""


def test_owner_roles_are_only_the_ones_they_said_exist() -> None:
    got = holdings.framework_inputs({"org.functions": {"it": "dedicated", "legal": "none"}})
    assert got["roles"] == ["Information technology"]
