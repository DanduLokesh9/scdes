"""Changes a vendor made, recorded on the vendor entry.

Integrity 4.8 is raised where "a change is recorded against the tool or
against its vendor entry" and nothing has been checked since. Vendors had
nowhere to record one, so only project version records counted. What these
pin: the change is kept in the vendor's own words and never rewritten by an
edit; it can open a version record on each project the vendor serves; and
Integrity counts it against those projects.
"""

from __future__ import annotations

import pytest

from app import checks, projects, vendors
from app.authz import Actor, Role

WHO = Actor("u.one", "Dana Reed", Role.OPERATOR)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(vendors, "_file", lambda: tmp_path / "vendors.json")
    monkeypatch.setattr(vendors, "_record", lambda *a, **k: None)
    monkeypatch.setattr(projects, "_file", lambda: tmp_path / "projects.json")
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    yield


def _vendor(**over) -> dict:
    out = vendors.save({"name": "Acme Permits", **over}, WHO)
    assert out["ok"], out
    return out["vendor"]


def test_a_change_needs_words() -> None:
    v = _vendor()
    assert vendors.record_change(v["id"], WHO, what="  ")["ok"] is False


def test_a_change_is_kept_in_their_words_with_who_and_when() -> None:
    v = _vendor()
    out = vendors.record_change(v["id"], WHO, what="We moved the export button.",
                                told_on="2026-09-20")
    assert out["ok"]
    c = out["vendor"]["changes"][0]
    assert c["what"] == "We moved the export button."
    assert c["told_on"] == "2026-09-20" and not c["not_told"]
    assert c["by"] == "Dana Reed" and c["recorded_on"]


def test_not_told_keeps_no_told_date() -> None:
    v = _vendor()
    c = vendors.record_change(v["id"], WHO, what="Pricing changed.", told_on="2026-09-20",
                              not_told=True)["change"]
    assert c["not_told"] and c["told_on"] == ""


def test_it_opens_a_version_record_on_each_project_it_serves() -> None:
    a = projects.start("Permit triage", WHO)["project"]["ref"]
    b = projects.start("Inspection notes", WHO)["project"]["ref"]
    v = _vendor(projects=[a, b])
    c = vendors.record_change(v["id"], WHO, what="New summarizer version.")["change"]
    assert {x["project"] for x in c["versions"]} == {a, b}
    held = projects.one(a)
    assert held["version_pending"] is True
    assert held["versions"][0]["what"] == "From Acme Permits: New summarizer version."


def test_opening_version_records_is_a_choice() -> None:
    a = projects.start("Permit triage", WHO)["project"]["ref"]
    v = _vendor(projects=[a])
    c = vendors.record_change(v["id"], WHO, what="Minor fix.", open_versions=False)["change"]
    assert c["versions"] == [] and not projects.one(a).get("versions")


def test_editing_the_vendor_never_rewrites_the_change_log() -> None:
    v = _vendor()
    vendors.record_change(v["id"], WHO, what="First change.")
    edited = vendors.save({"id": v["id"], "name": "Acme Permits Inc.",
                           "changes": []}, WHO)["vendor"]
    assert [c["what"] for c in edited["changes"]] == ["First change."]


def test_integrity_counts_a_vendor_change_against_its_projects() -> None:
    a = projects.start("Permit triage", WHO)["project"]["ref"]
    v = _vendor(projects=[a])
    vendors.record_change(v["id"], WHO, what="Changed it.", open_versions=False)
    by_project = vendors.changes_by_project()
    assert list(by_project) == [a]
    found = checks.findings([], projects={a: {"ref": a}},
                            change_words="treat it as a new tool and review it like one",
                            vendor_changes=by_project)
    assert [f["id"] for f in found] == ["finding.change_unanswered"]
    assert f"A change was recorded on {by_project[a][0]}" in found[0]["says"]


def test_a_check_after_the_change_answers_it(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(checks, "_file", lambda: tmp_path / "checks.json")
    monkeypatch.setattr(checks, "_log", lambda *a, **k: None)
    found = checks.findings([], projects={"P1": {"ref": "P1"}},
                            change_words="whenever the vendor changes the tool",
                            vendor_changes={"P1": ["2026-09-10"]})
    assert found
    checks.record_check(project="P1", actor=WHO, limits="Only the export",
                        at="2026-09-12", complete=True)
    assert not checks.findings(projects={"P1": {"ref": "P1"}},
                               change_words="whenever the vendor changes the tool",
                               vendor_changes={"P1": ["2026-09-10"]})
