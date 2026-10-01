"""Writing a project up — spec §4, §8 to §12 and §14.

What these pin: every answer is optional and kept in the proposer's words; a
section holds only its own fields; a project can close at Identify without a
tool and stays on the list; a version going live retires the one before it on
the same date; retiring the tool is the decision-maker's; GAIUS is seeded once
and never marks itself approved; and every finding quotes the organization's
own answer rather than an outside standard.
"""

from __future__ import annotations

import pytest

from app import projects, server, spine
from app.authz import Actor, Role

USER = Actor("u.one", "", Role.OPERATOR)
DECIDER = Actor("d.one", "", Role.COUNCIL)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    path = tmp_path / "projects.json"
    monkeypatch.setattr(projects, "_file", lambda: path)
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    yield


def _started(name: str = "Permit triage") -> str:
    made = projects.start(name, USER)
    assert made["ok"], made
    return made["project"]["ref"]


# ------------------------------------------------------------ sections

def test_a_section_keeps_only_its_own_fields() -> None:
    ref = _started()
    out = projects.save_section(ref, "problem", {
        "happening": "Applications sit for weeks", "confidence": "Confident",
        "gate": "gate.retire", "level": "High"}, USER)
    assert out["ok"]
    p = projects.one(ref)
    assert p["problem"]["happening"] == "Applications sit for weeks"
    assert "gate" not in p["problem"] and p["gate"] == spine.IDENTIFY
    assert p.get("level", "") in ("", None)


def test_an_unknown_section_is_refused() -> None:
    ref = _started()
    assert projects.save_section(ref, "anything", {"x": 1}, USER)["ok"] is False


def test_baseline_detail_leaves_the_plain_baseline_as_text() -> None:
    ref = _started()
    projects.save_section(ref, "baseline", {
        "today": "Two clerks sort by hand", "rows": [{"what": "Days", "figure": "14"}]}, USER)
    p = projects.one(ref)
    assert p["baseline"] == "Two clerks sort by hand"
    assert p["baseline_detail"]["rows"][0]["figure"] == "14"


def test_business_case_detail_leaves_the_plain_field_as_text() -> None:
    ref = _started()
    projects.save_section(ref, "business_case", {"expect_back": "Faster replies",
                                                "money_from": ["A grant"]}, USER)
    p = projects.one(ref)
    assert p["business_case"] == "Faster replies"
    assert p["case_detail"]["money_from"] == ["A grant"]


# ------------------------------------------------------------ verdicts

def test_verdicts_keep_only_the_shared_vocabulary() -> None:
    ref = _started()
    projects.save_verdicts(ref, categories={
        "process": {"verdict": "Taken", "why": "Reorder the queue"},
        "rule": {"verdict": "Brilliant", "why": ""}}, actor=USER)
    sol = projects.one(ref)["solution"]
    assert sol["process"]["verdict"] == "Taken"
    assert sol["rule"]["verdict"] == ""


def test_the_lowest_step_taken_is_the_chosen_step() -> None:
    ref = _started()
    projects.save_verdicts(ref, steps={
        "1": {"verdict": "Inadequate", "why": "Not enough"},
        "3": {"verdict": "Taken"}, "6": {"verdict": "Taken"}}, actor=USER)
    assert projects.one(ref)["chosen_step"] == 3


def test_closing_without_a_tool_keeps_it_on_the_list() -> None:
    ref = _started()
    out = projects.close_without_tool(ref, "process", USER, why="Reordered it")
    assert out["ok"], out
    assert out["says"] == projects.CLOSED_WITHOUT_TOOL
    p = projects.one(ref)
    assert p["state"] == spine.TURNED_DOWN and p["ended_category"] == "process"
    assert projects.counters()["ended_without_a_tool"] == 1


def test_a_technology_category_does_not_close_without_a_tool() -> None:
    ref = _started()
    assert projects.close_without_tool(ref, "simple_tech", USER)["ok"] is False


def test_summary_says_what_is_missing_rather_than_inventing_it() -> None:
    ref = _started()
    s = projects.summary(projects.one(ref))
    assert s["problem_statement"] == "Not written yet."
    assert s["sequence"] == ["Not written yet."]
    assert len(s["options_considered"]) == len(projects.CATEGORIES) + len(spine.HIERARCHY)


# ------------------------------------------------------------ versions

def test_a_version_needs_the_vendors_words() -> None:
    ref = _started()
    assert projects.open_version(ref, USER, what="  ")["ok"] is False


def test_going_live_retires_the_running_version_on_the_same_date() -> None:
    ref = _started()
    a = projects.open_version(ref, USER, what="First release")["version"]["ref"]
    projects.update_version(ref, a, USER, live="2026-09-01")
    b = projects.open_version(ref, USER, what="Second release",
                              not_told=True)["version"]["ref"]
    assert projects.one(ref)["version_pending"] is True
    projects.update_version(ref, b, USER, live="2026-09-20", tested_reason="No time")
    vs = {v["ref"]: v for v in projects.one(ref)["versions"]}
    assert vs[a]["retired"] == "2026-09-20"
    assert vs[b]["retired"] == "" and vs[b]["told_on"] == ""
    assert projects.one(ref)["version_pending"] is False


def test_a_version_live_with_nothing_tried_is_named() -> None:
    ref = _started()
    v = projects.open_version(ref, USER, what="Update")["version"]["ref"]
    projects.update_version(ref, v, USER, live="2026-09-01")
    ids = {f["id"] for f in projects.findings_all(projects.one(ref), inputs={})}
    assert "finding.pj.version_untracked" in ids


# ------------------------------------------------------------ sunset

def test_only_whoever_decides_closes_the_retirement_record() -> None:
    ref = _started()
    refused = server.api_project_sunset_close(USER, {"ref": ref}, {})
    assert refused["ok"] is False
    assert "whoever decides" in refused["error"]


def test_a_user_writes_the_record_but_not_the_decision() -> None:
    ref = _started()
    ok = server.api_project_sunset(USER, {"ref": ref, "fields": {
        "trigger": "Somebody proposed it", "records": "Kept seven years"}}, {})
    assert ok["ok"]
    refused = server.api_project_sunset(USER, {"ref": ref, "fields": {
        "decided_by": "Director"}}, {})
    assert refused["ok"] is False


def test_closing_retires_it_and_names_what_is_missing() -> None:
    ref = _started()
    projects.name_accountable(ref, "Director", DECIDER)
    projects._set_field(ref, "gate", spine.MEASURE)
    out = projects.close_sunset(ref, DECIDER)
    assert out["ok"], out
    p = projects.one(ref)
    assert p["state"] == spine.RETIRED and p["gate"] == spine.SUNSET
    ids = {f["id"] for f in projects.findings_all(p, inputs={})}
    assert {"finding.pj.retired_no_disposition", "finding.pj.retired_no_replacement",
            "finding.pj.final_measurement_missing"} <= ids
    assert projects.one(ref) is not None


# ------------------------------------------------------------ findings

def test_a_finding_quotes_their_own_single_factor_rule() -> None:
    ref = _started()
    projects.save_section(ref, "tool", {"factors": {"public": "yes"}}, USER)
    projects._set_field(ref, "level", "Low")
    inputs = {"single_factor": True, "levels": ["Low", "High"],
              "severe_keys": ["public"], "factors": [("public", "It faces the public")]}
    says = [f["says"] for f in projects.findings_all(projects.one(ref), inputs=inputs)]
    assert any("You said one severe factor lifts the whole thing" in s and
               "It faces the public" in s for s in says)


def test_nothing_is_raised_without_their_answer() -> None:
    ref = _started()
    projects.save_section(ref, "tool", {"factors": {"public": "yes"},
                                        "finalises": "yes"}, USER)
    ids = {f["id"] for f in projects.findings_all(projects.one(ref), inputs={})}
    assert "finding.pj.finalises" not in ids
    assert "finding.pj.level_below_own_rule" not in ids


def test_a_date_somebody_set_that_has_passed_is_named() -> None:
    ref = _started()
    projects._set_field(ref, "next_gate_by", "2026-01-01")
    ids = {f["id"] for f in projects.findings_all(projects.one(ref), inputs={},
                                                  today="2026-09-23")}
    assert "finding.pj.past_their_date" in ids


def test_the_list_check_is_raised_once_for_the_list() -> None:
    _started(); _started("Second")
    rows = projects.all_projects()
    inputs = {"list_days": 92, "list_words": "quarterly"}
    out = projects.list_findings(rows, inputs=inputs, today="2026-09-23")
    assert len(out) == 1 and "never been a check" in out[0]["says"]
    projects.list_checked(USER)
    out = projects.list_findings(rows, inputs=inputs,
                                 list_checked=projects.last_list_check())
    assert out == []


# ------------------------------------------------------------ GAIUS

def test_gaius_is_seeded_once_and_never_approves_itself() -> None:
    first = projects.seed_gaius(USER)
    assert first["seeded"] is True
    assert projects.seed_gaius(USER)["seeded"] is False
    p = projects.one(first["ref"])
    assert p["gate"] == spine.IDENTIFY and not p.get("passages")
    assert p["in_use"] == "yes"
    # Floor 7 is left open for the organisation; no name is pre-loaded.
    assert p["gaps"][0]["field"] == "floor.somebody_named"
    assert not p.get("accountable_person")


def test_gaius_words_avoid_the_banned_vocabulary() -> None:
    text = " ".join([projects.GAIUS_NAME, projects.GAIUS_DATA_LINE,
                     *projects.GAIUS_EVIDENCE.values()]).lower()
    for word in ("model", "algorithm", "llm", "inference", "machine learning"):
        assert word not in text
