"""The findings that were specified but could not be computed until the
record held what they read.

Process 3.4 and 3.7 read the project's disclosure answer and its wording;
Budget 3.12 reads who approved the Procure passage off the passage itself;
Registry 4.3 and 4.4 read the project's chosen step and the functions the
framework records as absent. Each quotes the organization's own answer, and
none blocks anything.
"""

from __future__ import annotations

from app import catalog, costs, procedures, spine


# ------------------------------------------------------------ Process

def _record(**over):
    return {"ref": "P1", "gate": spine.DEPLOY, "level": "", "in_use": "",
            "route_to_person": False, "public_facing": False,
            "own_wording": False, **over}


def test_no_route_to_person_where_the_public_sees_it() -> None:
    got = procedures.findings([], records=[_record(public_facing=True)])
    assert [f["id"] for f in got] == ["finding.process.no_route_to_person"]
    assert not procedures.findings([], records=[_record(public_facing=True,
                                                        route_to_person=True)])
    assert not procedures.findings([], records=[_record(public_facing=True,
                                                        gate=spine.PROCURE)])


def test_own_wording_is_named_only_where_wording_lives_in_one_place() -> None:
    rec = [_record(own_wording=True)]
    assert not procedures.findings([], records=rec)
    got = procedures.findings([], records=rec, wording_lives_in_one_place=True)
    assert [f["says"] for f in got] == [
        "You said approved wording lives in one place so everyone says the "
        "same thing. This record has its own."]


def test_the_surface_reads_the_project_disclosure(monkeypatch) -> None:
    monkeypatch.setattr(procedures, "all_procedures", lambda: [])
    monkeypatch.setattr(procedures, "events", lambda: [])
    project = {"ref": "P1", "gate": spine.DEPLOY, "name": "Permits",
               "tool": {"public_facing": "output", "disclosure_text": "A tool helped."}}
    got = procedures.surface(answers={"floor.disclose_home": "the comms office"},
                             projects=[project])
    ids = {f["id"] for f in got["raised"]}
    assert {"finding.process.no_route_to_person",
            "finding.process.wording_off_book"} <= ids
    pointed = {**project, "tool": {**project["tool"], "disclosure_ref": "PR-1"}}
    got = procedures.surface(answers={"floor.disclose_home": "the comms office"},
                             projects=[pointed])
    assert "finding.process.wording_off_book" not in {f["id"] for f in got["raised"]}


# ------------------------------------------------------------ Budget

def _budget(hat: str, *, amounts=(3000, 3000), limit=5000.0):
    inputs = costs.framework_inputs({})
    inputs["delegation_amount"] = limit
    project = {"ref": "P1", "gate": spine.TEST, "passages": [
        {"from": spine.PROCURE, "to": spine.TEST, "hat": hat,
         "by_title": "Program Manager"}]}
    rows = [{"ref": f"CL-{i}", "project": "P1", "basis": costs.A_YEAR,
             "estimate": a, "committed": True, "status": costs.OPEN}
            for i, a in enumerate(amounts)]
    return [f for f in costs.project_findings(rows=rows, projects={"P1": project},
                                              inputs=inputs, gaps=[])
            if f["id"] == "finding.budget.threshold_crossed"]


def test_instalments_under_the_limit_still_cross_it() -> None:
    """Four two-thousand-dollar lines are an eight-thousand-dollar decision."""
    got = _budget("operator")
    assert len(got) == 1
    assert "approved by Program Manager" in got[0]["says"]
    assert "$6,000" in got[0]["says"] or "6,000" in got[0]["says"]


def test_whoever_decides_approving_is_not_a_crossing() -> None:
    assert not _budget("council")
    assert not _budget("operator", amounts=(1000, 1000))


# ------------------------------------------------------------ Registry

def _tool(**over):
    return {"ref": "RG-1", "name": "Summarizer", "held_by": [{"unit": "Planning"}],
            "projects": [], **over}


def test_a_duplicate_purchase_names_both_and_blocks_nothing() -> None:
    project = {"ref": "P1", "name": "Permit triage", "gate": spine.PROCURE,
               "chosen_step": 6, "problem": {"unit": "Works"},
               "hierarchy": {"3": {"verdict": "Inadequate",
                                   "candidate": "Summarizer, but license will not extend"}}}
    got = [f for f in catalog.findings([_tool()], projects=[project])
           if f["id"] == "finding.rg.duplicate_purchase"]
    assert [f["says"] for f in got] == [
        "Planning already has Summarizer for this. Permit triage is buying "
        "something new."]


def test_no_duplicate_where_it_did_not_go_to_a_vendor_or_the_holder_is_itself() -> None:
    base = {"ref": "P1", "name": "x", "gate": spine.PROCURE,
            "hierarchy": {"3": {"candidate": "Summarizer"}}}
    assert not [f for f in catalog.findings([_tool()], projects=[{**base, "chosen_step": 3}])
                if f["id"] == "finding.rg.duplicate_purchase"]
    mine = {**base, "chosen_step": 6, "problem": {"unit": "Planning"}}
    assert not [f for f in catalog.findings([_tool()], projects=[mine])
                if f["id"] == "finding.rg.duplicate_purchase"]


def test_a_holder_the_framework_records_as_absent_is_named() -> None:
    tool = _tool(held_by=[{"unit": "Records management"}])
    got = [f for f in catalog.findings([tool], absent=["Records management"])
           if f["id"] == "finding.rg.holder_gone"]
    assert got and "Records management" in got[0]["says"]
    assert not [f for f in catalog.findings([_tool()], absent=["Records management"])
                if f["id"] == "finding.rg.holder_gone"]


def test_absent_functions_come_from_1_4() -> None:
    got = catalog.framework_inputs({"org.functions": {"records": "none", "it": "part"}})
    assert got["absent"] == ["Records management"]
