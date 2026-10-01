"""The Vendors surface, brought back in line with Module One and the spec.

Three defects are pinned here so they cannot return. The screen could not
open a vendor saved after the terms became Present / Absent / Not asked,
because old rows were read as a list and new ones as a record. Two of the
term keys and two of the cost categories had drifted from Module One's, so
a term marked under one key was invisible to anything reading the other.
And the training warning used the one word this product never writes.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app import holdings, module_one, spine, tenant, vendors, versions
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    monkeypatch.setattr(vendors, "VENDORS_FILE",
                        tmp_path / "corpus" / "config" / "vendors.json")
    monkeypatch.setattr(holdings, "HOLDINGS_FILE",
                        tmp_path / "corpus" / "config" / "holdings.json")
    monkeypatch.setattr(versions, "VERSIONS_FILE",
                        tmp_path / "corpus" / "config" / "versions.json")
    yield


def _store(rows: list[dict]) -> None:
    path = vendors._file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"vendors": rows}), encoding="utf-8")


# -------------------------------------------------- saved rows still open

def test_a_row_saved_with_terms_as_a_list_still_reads() -> None:
    """Before this, the first line asking which terms were absent broke on
    it — the screen's own summary among them."""
    _store([{"id": "VN-OLD", "name": "Old Co", "terms": ["notice", "what_ai"],
             "costed": ["licence"]}])
    listed = vendors.listing()
    row = listed["vendors"][0]
    assert row["terms"] == {"notice": vendors.PRESENT,
                            "disclose": vendors.PRESENT}
    assert row["terms_absent"] == []


def test_a_row_saved_under_an_old_key_is_moved_to_module_ones_key() -> None:
    _store([{"id": "VN-OLD", "name": "Old Co",
             "terms": {"return_delete": "absent"}}])
    row = vendors.listing()["vendors"][0]
    assert row["terms"] == {"return": vendors.ABSENT}


def test_a_row_with_keys_this_version_does_not_know_still_reads() -> None:
    _store([{"id": "VN-X", "name": "X", "tier": {"tier": 2}, "extra": 1}])
    assert vendors.listing()["vendors"][0]["name"] == "X"


# ------------------------------------------------ one set of keys, Module One's

def test_the_terms_are_module_ones_terms_with_module_ones_keys() -> None:
    question = module_one.by_key("proc.terms")
    theirs = [o.value for o in question.options
              if o.value != module_one.UNKNOWN]
    assert [k for k, _ in vendors.TERMS] == theirs


def test_the_cost_categories_are_module_ones() -> None:
    question = module_one.by_key("proc.cost_parts")
    theirs = [o.value for o in question.options
              if o.value != module_one.UNKNOWN]
    assert [k for k, _ in vendors.COST_CATEGORIES] == theirs


def test_what_a_vendor_must_tell_you_uses_their_list_and_their_words() -> None:
    required = [{"value": "notice", "label": "Tell us before changes are "
                 "deployed", "required": True},
                {"value": "own", "label": "Tell us who hosts it",
                 "required": True},
                {"value": "audit", "label": "Let us audit it",
                 "required": False}]
    got = vendors.must_tell_you("high", "public", required=required)
    assert got["applies"] == ["notice", "own"]
    assert "tell us who hosts it" in got["says"]
    assert "audit" not in got["says"]


# --------------------------------------------------------- the findings

def test_an_opt_out_nobody_exercised_is_the_same_as_no_term() -> None:
    with_optout = vendors._clean({"name": "V", "training": "opt_out",
                                  "status": "in_use"})
    assert any(f["id"] == "finding.vd.trains_on_us"
               for f in vendors.findings([with_optout]))
    exercised = vendors._clean({"name": "V", "training": "opt_out",
                                "opted_out": "yes", "status": "in_use"})
    assert not any(f["id"] == "finding.vd.trains_on_us"
                   for f in vendors.findings([exercised]))


def test_only_a_required_term_marked_absent_is_a_finding() -> None:
    row = vendors._clean({"name": "V", "terms": {"audit": "absent",
                                                 "indemnity": "absent"}})
    found = [f["term"] for f in vendors.findings([row], required={"audit"})
             if f["id"] == "finding.term_absent"]
    assert found == ["audit"]


def test_a_vendor_linked_to_a_project_is_accounted_for() -> None:
    row = vendors._clean({"name": "V", "route": "found", "projects": ["7QHC26"]})
    assert not any(f["id"] == "finding.vd.arrived_undecided"
                   for f in vendors.findings([row]))


def test_a_renewal_with_nothing_measured_is_named() -> None:
    row = vendors._clean({"name": "V", "renewal": "2026-10-01"})
    found = vendors.findings([row], renewals_unmeasured={row.id})
    assert any(f["id"] == "finding.vd.renewal_no_review" for f in found)


def test_nobody_named_against_a_vendor_is_the_shared_gap_finding() -> None:
    """Spec §3: finding.gap_no_owner is raised where 8.12 is empty."""
    unowned = vendors._clean({"name": "V"})
    owned = vendors._clean({"name": "V", "owner": "The Clerk"})
    assert any(f["id"] == "finding.gap_no_owner"
               for f in vendors.findings([unowned]))
    assert not any(f["id"] == "finding.gap_no_owner"
                   for f in vendors.findings([owned]))


# ------------------------------------------------------------ the money line

def test_the_money_line_reads_as_the_spec_writes_it() -> None:
    rows = [vendors._clean({"name": "A", "status": "in_use", "amount": "1200",
                            "basis": "year"}),
            vendors._clean({"name": "B", "status": "in_use"})]
    assert vendors.money_line(rows) == ("$1,200 a year across what is in use "
                                        "or in a pilot, and 1 with no cost "
                                        "recorded.")


def test_a_per_person_price_is_not_called_unpriced_or_added_in() -> None:
    rows = [vendors._clean({"name": "A", "status": "in_use", "amount": "900",
                            "basis": "per_user"})]
    said = vendors.money_line(rows)
    assert said.startswith("$0 a year")
    assert "no cost recorded" not in said
    assert "cannot be added up" in said


# ----------------------------------------------------- the renewal window

def test_the_window_is_their_own_notice_period() -> None:
    got = vendors.renewal_window({"watch.notice": "60"})
    assert got["days"] == 60 and got["theirs"] is True
    assert got["says"] == "You said 60 days' notice."


def test_with_no_period_set_it_says_so_rather_than_passing_ninety_as_theirs() \
        -> None:
    got = vendors.renewal_window({})
    assert got["days"] == vendors.NO_WINDOW_DAYS
    assert got["theirs"] is False
    assert got["label"] == "Renewing, no window set"


def test_renewing_soon_reads_the_window_given() -> None:
    soon = (date.today() + timedelta(days=45)).isoformat()
    with_row = [vendors._clean({"name": "V", "status": "in_use",
                                "renewal": soon})]
    assert vendors.renewing_soon(with_row, within_days=30) == []
    assert len(vendors.renewing_soon(with_row, within_days=60)) == 1


# --------------------------------------------------------------- the form

def test_the_opt_out_and_behaviour_fields_are_kept() -> None:
    row = vendors._clean({"name": "V", "training": "opt_out",
                          "opted_out": "yes", "opted_out_on": "2026-03-04",
                          "opted_out_by": "Clerk", "behaved_notice": "sometimes",
                          "behaved_staging": "extra", "behaved_answers": "partly",
                          "behaved_renewal": "raised",
                          "behaved_note": "Raised 12% at renewal."})
    assert (row.opted_out, row.opted_out_on, row.opted_out_by) == \
        ("yes", "2026-03-04", "Clerk")
    assert row.behaved_staging == "extra"
    assert row.behaved_note == "Raised 12% at renewal."


def test_an_answer_not_on_the_list_is_not_kept() -> None:
    row = vendors._clean({"name": "V", "behaved_notice": "brilliant"})
    assert row.behaved_notice == ""


def test_no_renewal_is_a_fact_not_a_blank() -> None:
    assert vendors._clean({"name": "V", "no_renewal": True}).no_renewal is True


# ---------------------------------------------------------- house language

def test_the_training_warning_says_tool_not_the_banned_word() -> None:
    said = vendors.TRAINING_CONSEQUENCE.lower()
    assert "taught their tool" in said
    for banned in spine.BANNED_IN_COPY:
        assert banned not in spine.banned_in(said), banned


def test_nothing_in_the_listing_is_a_score_or_a_tier() -> None:
    _store([{"id": "VN-1", "name": "V", "behaved_renewal": "raised"}])
    blob = json.dumps(vendors.listing()).lower()
    for word in ("tier ", "score", "rating", "stars", "grade"):
        assert word not in blob, word
