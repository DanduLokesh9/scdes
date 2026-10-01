"""The vendor registry — who you buy from, what it costs, what else it does.

The client: "Module will contain a list of vendors, costs, and use case
potential." Most of this file is about the third of those and about the
pairing that makes the register worth keeping: their own procurement rules,
checked one agreement at a time.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from app import holdings, tenant, vendors, versions
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


def as_agency(code: str):
    class Bound:
        def __enter__(self):
            self.token = tenant.set_current(code)
            return self
        def __exit__(self, *_):
            tenant.reset(self.token)
    return Bound()


SUMMARISER = {
    "name": "Northbridge Software",
    "product": "CaseNote",
    "what_for": "Summarizing inspection reports for the weekly review",
    "could_also": "Drafting letters, and searching across old reports",
    "status": "in_use", "involvement": "core",
    "owner": "The Permitting Manager",
    "amount": "$41,500 / yr", "basis": "year",
    "contract": "PO-2024-118", "renewal": "2026-11-01",
    "criticality": "low", "facing": "internal",
    "training": "no", "accessibility": "report",
}

#: Everything their framework asks for, so a test can subtract one thing and
#: know exactly what it is testing.
EVERY_TERM = ["disclose", "notice", "accuracy", "audit", "return", "breach",
              "staging", "accessibility"]
EVERY_PART = ["licence", "setup", "training", "staff_time", "data_prep",
              "integration", "monitoring", "exit"]

#: A framework that has answered step 8 and 7.1.
DECIDED = {
    "proc.terms": EVERY_TERM,
    "proc.full_cost": "yes",
    "proc.cost_parts": EVERY_PART,
    "proc.added_ai": "as_new",
    "data.never": ["personal"],
}


def complete(**over):
    """A vendor with nothing outstanding, so each test breaks one thing."""
    return {**SUMMARISER, "terms": list(EVERY_TERM),
            "costed": list(EVERY_PART), **over}


# ------------------------------------------------------------- the registry

def test_a_vendor_can_be_written_down_and_read_back() -> None:
    with as_agency("iia.test"):
        out = vendors.save(SUMMARISER, WHO)
        assert out["ok"], out
        rows = vendors.listing()["vendors"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Northbridge Software"
        assert rows[0]["id"].startswith("VN-")
        assert rows[0]["status_label"] == "In use today"


def test_a_vendor_needs_a_name_and_nothing_else() -> None:
    with as_agency("iia.test"):
        assert not vendors.save({"product": "CaseNote"}, WHO)["ok"]
        assert vendors.save({"name": "Northbridge Software"}, WHO)["ok"]


def test_a_price_survives_being_typed_by_a_person() -> None:
    """"$41,500/yr" is what somebody writes in a box. Refusing it is how a
    register acquires a column of zeroes."""
    with as_agency("iia.test"):
        saved = vendors.save(SUMMARISER, WHO)["vendor"]
        assert saved["amount"] == 41500.0
        assert saved["a_year"] == 41500.0


def test_a_monthly_price_is_annualised_and_the_rest_is_not() -> None:
    """A one-off and a usage-based bill are real answers and neither is an
    annual figure. Returning 0 and counting it separately is the only honest
    thing to do with them."""
    with as_agency("iia.test"):
        vendors.save({"name": "A", "status": "in_use", "amount": "500",
                      "basis": "month"}, WHO)
        vendors.save({"name": "B", "status": "in_use", "amount": "9000",
                      "basis": "once"}, WHO)
        vendors.save({"name": "C", "status": "in_use", "amount": "12",
                      "basis": "per_user"}, WHO)
        found = vendors.listing()["summary"]
        assert found["a_year"] == 6000.0, "only the ones that can be annualized"
        assert found["not_totalled"] == 2


def test_a_nonsense_date_is_dropped_rather_than_guessed() -> None:
    """A wrong renewal date is worse than none, because somebody plans
    around it."""
    with as_agency("iia.test"):
        saved = vendors.save({"name": "A", "renewal": "next spring"},
                             WHO)["vendor"]
        assert saved["renewal"] == ""


def test_one_agencys_registry_is_invisible_to_another() -> None:
    with as_agency("iia.test"):
        vendors.save(SUMMARISER, WHO)
    with as_agency("sc.ed"):
        assert vendors.listing()["vendors"] == []
    with as_agency("iia.test"):
        assert len(vendors.listing()["vendors"]) == 1


def test_what_is_coming_up_for_renewal() -> None:
    soon = (date.today() + timedelta(days=30)).isoformat()
    later = (date.today() + timedelta(days=300)).isoformat()
    with as_agency("iia.test"):
        vendors.save({"name": "Soon", "status": "in_use", "renewal": soon}, WHO)
        vendors.save({"name": "Later", "status": "in_use", "renewal": later},
                     WHO)
        vendors.save({"name": "Gone", "status": "retired", "renewal": soon},
                     WHO)
        found = vendors.renewing_soon()
        assert [r["name"] for r in found] == ["Soon"], found


# ------------------------------------------- what the vendor has to tell you
#
# Five tests stood here over a tier model: four numbered disclosure tiers
# with names, derived from one agency's vendor-disclosure appendix. The
# tiers are gone and the tests with them.
#
# What replaced them is a prose panel, and three rules bind it. It never
# renders a tier name, a number or a letter, because all three collide with
# the organisation's own scrutiny levels — a screen showing "Tier 2" beside
# a framework whose levels are Routine and Elevated asks a reader to hold
# two numbering schemes at once, and that collision is what made the
# earlier construction unusable. It never names another organisation's
# framework, appendix or lettering.
#
# The two questions survive. They were always the right questions; it was
# the answer that was wrong.

def test_what_a_vendor_must_disclose_is_sentences_not_a_tier() -> None:
    got = vendors.must_tell_you("high", "public")
    said = got["says"].lower()
    assert "tell you" in said
    for numbered in ("tier", "level 1", "level 2", "category a",
                     "appendix"):
        assert numbered not in said, numbered


def test_the_panel_never_renders_a_number_or_a_letter() -> None:
    """All three collide with the organization's own scrutiny levels."""
    import re
    for criticality in ("high", "low", "unknown"):
        for facing in ("public", "internal", "unknown"):
            got = vendors.must_tell_you(criticality, facing)
            said = got["says"] + " " + got["because"]
            assert not re.search(r"\bTier\s*\d", said)
            assert not re.search(r"\bTier\s*[A-D]\b", said)
            assert "Appendix" not in said


def test_the_panel_says_why_in_the_same_breath() -> None:
    got = vendors.must_tell_you("high", "public")
    assert "informs decisions about people" in got["says"]
    assert "the public sees its output" in got["says"]
    assert "question 8.3" in got["because"]


def test_an_organisation_requiring_nothing_is_told_so_plainly() -> None:
    """Rather than being shown this application's opinion of what a vendor
    owes."""
    got = vendors.must_tell_you("high", "public", required=[])
    assert got["applies"] == []
    assert "does not require anything specific" in got["says"]
    assert "applies to new agreements from that day" in got["says"]


def test_an_unanswered_dimension_says_so_rather_than_assuming() -> None:
    got = vendors.must_tell_you("unknown", "unknown")
    assert "you have not said what it decides or who sees it" in got["says"]


# ------------------------------------ where the registry meets the framework

def test_a_missing_required_term_is_a_finding() -> None:
    """Their own 8.3, checked one agreement at a time. This is the whole
    reason the registry is worth more than a spreadsheet."""
    with as_agency("iia.test"):
        vendors.save(complete(terms=[t for t in EVERY_TERM if t != "breach"]),
                     WHO)
        found = vendors.concerns(DECIDED)
        against = [c for c in found if c["against"].startswith("8.3")]
        assert against, found
        assert "security breach" in against[0]["says"]


def test_nothing_is_required_that_they_did_not_require() -> None:
    with as_agency("iia.test"):
        vendors.save(complete(terms=[]), WHO)
        found = vendors.concerns({**DECIDED, "proc.terms": []})
        assert not [c for c in found if c["against"].startswith("8.3")]


def test_a_vendor_that_can_see_what_must_never_go_in() -> None:
    """The join between the two paid modules, and the reason the data
    register was built first."""
    with as_agency("iia.test"):
        held = holdings.save({"name": "Permit system", "reachable": "api",
                              "owner": "The Permitting Manager",
                              "sensitive": ["personal"]}, WHO)["holding"]
        vendors.save(complete(training="yes", holdings=[held["id"]]), WHO)
        found = [c for c in vendors.concerns(DECIDED)
                 if c["against"].startswith("7.1")]
        assert found, vendors.concerns(DECIDED)
        assert "Permit system" in found[0]["says"]
        assert "improve their product" in found[0]["says"]


def test_a_vendor_that_does_not_train_on_it_is_not_flagged_for_it() -> None:
    with as_agency("iia.test"):
        held = holdings.save({"name": "Permit system", "reachable": "api",
                              "owner": "The Permitting Manager",
                              "sensitive": ["personal"]}, WHO)["holding"]
        vendors.save(complete(training="no", holdings=[held["id"]]), WHO)
        assert not [c for c in vendors.concerns(DECIDED)
                    if c["against"].startswith("7.1")]


def test_not_having_asked_is_flagged_like_a_yes() -> None:
    """"We have not asked" is not a defense. It is the same exposure with
    less paperwork."""
    with as_agency("iia.test"):
        held = holdings.save({"name": "Permit system", "reachable": "api",
                              "owner": "The Permitting Manager",
                              "sensitive": ["personal"]}, WHO)["holding"]
        vendors.save(complete(training="unknown", holdings=[held["id"]]), WHO)
        found = [c for c in vendors.concerns(DECIDED)
                 if c["against"].startswith("7.1")]
        assert found
        assert "nobody has asked" in found[0]["says"]


def test_a_public_facing_tool_with_no_accessibility_on_file() -> None:
    """The client's standing requirement. Every product IIA builds has to
    meet WCAG 2.1 AA; a framework that does not ask the same of what an
    agency buys is not defensible. Named against the organization's own
    Floor 4, never another agency's appendix."""
    with as_agency("iia.test"):
        vendors.save(complete(facing="public", accessibility="unknown"), WHO)
        found = [c for c in vendors.concerns(DECIDED)
                 if c["against"].startswith("Floor 4")]
        assert found, vendors.concerns(DECIDED)
        assert not any("Appendix" in c["against"] or "Tier" in c["against"]
                       for c in vendors.concerns(DECIDED))


def test_an_internal_tool_is_not_held_to_the_public_standard() -> None:
    with as_agency("iia.test"):
        vendors.save(complete(facing="internal", accessibility="unknown"), WHO)
        assert not [c for c in vendors.concerns(DECIDED)
                    if "Tier 3" in c["against"]]


def test_ai_added_to_something_already_owned() -> None:
    """8.5 — the most common way AI arrives in a government, and the easiest
    to miss."""
    with as_agency("iia.test"):
        vendors.save(complete(involvement="added"), WHO)
        found = [c for c in vendors.concerns(DECIDED)
                 if c["against"].startswith("8.5")]
        assert found, vendors.concerns(DECIDED)


def test_it_says_nothing_about_added_ai_where_they_decided_otherwise() -> None:
    """They are allowed to decide that a vendor adding AI needs no review.
    The registry reports against their rules, not against ours."""
    with as_agency("iia.test"):
        vendors.save(complete(involvement="added"), WHO)
        answers = {**DECIDED, "proc.added_ai": "nothing"}
        assert not [c for c in vendors.concerns(answers)
                    if c["against"].startswith("8.5")]


def test_a_cost_they_said_counts_but_never_estimated() -> None:
    with as_agency("iia.test"):
        vendors.save(complete(costed=[p for p in EVERY_PART if p != "exit"]),
                     WHO)
        found = [c for c in vendors.concerns(DECIDED)
                 if c["against"].startswith("8.7")]
        assert found, vendors.concerns(DECIDED)
        assert "what it costs to leave" in found[0]["says"]


def test_a_retired_vendor_is_a_record_not_an_exposure() -> None:
    with as_agency("iia.test"):
        vendors.save(complete(status="retired", terms=[], owner=""), WHO)
        assert vendors.concerns(DECIDED) == []


def test_an_unowned_vendor_is_a_finding() -> None:
    with as_agency("iia.test"):
        vendors.save(complete(owner=""), WHO)
        assert any("nobody named against it" in c["says"]
                   for c in vendors.concerns(DECIDED))


def test_a_clean_agreement_produces_nothing() -> None:
    """The other half of every check above. A register that always finds
    something is a register people stop reading."""
    with as_agency("iia.test"):
        vendors.save(complete(), WHO)
        assert vendors.concerns(DECIDED) == []


# ------------------------------------------------------------- the writing

def test_every_write_is_recorded() -> None:
    """The client: "WE NEED TO LOG ALL CHOICES, ACTIVITIES, and Framework
    versions on the back end"."""
    from app.authz import default_log
    with as_agency("iia.test"):
        vendors.save(SUMMARISER, WHO)
        entries = [json.loads(line) for line in
                   default_log().path.read_text(encoding="utf-8").splitlines()
                   if line.strip()]
        mine = [e for e in entries if e.get("action") == "record_vendor"]
        assert mine, "a vendor was written with no audit entry"
        assert mine[-1]["detail"]["name"] == "Northbridge Software"


def test_editing_keeps_the_same_entry() -> None:
    with as_agency("iia.test"):
        first = vendors.save(SUMMARISER, WHO)["vendor"]
        again = vendors.save({**SUMMARISER, "id": first["id"],
                              "owner": "The Deputy Director"}, WHO)
        assert len(vendors.listing()["vendors"]) == 1
        assert again["vendor"]["owner"] == "The Deputy Director"
        assert again["vendor"]["added_at"] == first["added_at"]


def test_unticking_the_last_term_clears_it() -> None:
    """Terms became a mapping of Present / Absent / Not asked, so an empty
    one is `{}` rather than `[]`. The behavior under test is unchanged:
    clearing every answer leaves nothing recorded rather than leaving the
    last one behind."""
    with as_agency("iia.test"):
        first = vendors.save(complete(), WHO)["vendor"]
        assert first["terms"]
        again = vendors.save({"id": first["id"], "name": first["name"],
                              "terms": {}}, WHO)
        assert again["vendor"]["terms"] == {}


def test_an_older_list_of_terms_is_read_as_present() -> None:
    """The shape changed under rows that already existed. Everything on an
    old list becomes Present; everything else is simply unrecorded, which is
    honest, because the old shape never held the answer."""
    got = vendors._marked(["notice", "staging"])
    assert got == {"notice": vendors.PRESENT, "staging": vendors.PRESENT}


def test_absent_and_never_asked_are_not_the_same_answer() -> None:
    """The distinction the old list could not carry. One is a decision and
    the other is a gap in the file."""
    assert vendors.ABSENT != vendors.NOT_ASKED
    assert set(vendors.TERM_ANSWERS) == {
        vendors.PRESENT, vendors.ABSENT, vendors.NOT_ASKED}
    # And there is no fourth. A term the organisation required and did not
    # get is exactly what this register has to record.
    assert len(vendors.TERM_ANSWERS) == 3
    assert "not_applicable" not in vendors.TERM_ANSWERS


def test_an_unrecognised_answer_is_not_stored() -> None:
    assert vendors._marked({"notice": "maybe"}) == {}


# ----------------------------------------------------------- the route

def test_the_route_that_matters_most_is_offered() -> None:
    """The most common way AI enters a government, and the easiest to
    miss."""
    assert "found" in vendors.ROUTE
    said = vendors.ROUTE["found"].lower()
    assert "nobody in the organization decided anything" in said


def test_building_it_yourself_still_makes_an_entry() -> None:
    """Otherwise "we built it ourselves" becomes the hole every rule falls
    through."""
    assert "built" in vendors.ROUTE
    assert "the entry still exists" in vendors.ROUTE["built"]


def test_arriving_undecided_is_flagged_only_where_no_project_owns_it() -> None:
    with as_agency("iia.test"):
        made = vendors.save({"name": "Something", "route": "found"},
                            WHO)["vendor"]
        found = {f["id"] for f in vendors.findings()}
        assert "finding.vd.arrived_undecided" in found
        quiet = {f["id"] for f in vendors.findings(
            on_a_project={made["id"]: True})}
        assert "finding.vd.arrived_undecided" not in quiet


# --------------------------------------------------- the training question

def test_the_training_consequence_is_stated_when_the_answer_is_not_no() -> None:
    """The one term that cannot be fixed afterward, so the consequence is
    stated when the answer is given rather than at sunset."""
    said = vendors.TRAINING_CONSEQUENCE.lower()
    assert "cannot get back what it taught" in said
    assert "nothing to return" in said


def test_the_surface_says_the_term_is_not_on_their_list() -> None:
    """Rather than asserting the requirement bare."""
    said = vendors.TRAINING_IS_NOT_IN_THE_LIST.lower()
    assert "does not include one forbidding" in said
    assert "that is a different term" in said


def test_training_on_our_information_is_a_finding() -> None:
    with as_agency("iia.test"):
        vendors.save({"name": "V", "training": "yes", "status": "in_use"},
                     WHO)
        found = {f["id"] for f in vendors.findings()}
        assert "finding.vd.trains_on_us" in found


def test_never_having_asked_is_its_own_finding() -> None:
    """A gap in the file, not a decision."""
    with as_agency("iia.test"):
        vendors.save({"name": "V", "training": "unknown",
                      "status": "in_use"}, WHO)
        found = {f["id"] for f in vendors.findings()}
        assert "finding.vd.never_asked" in found
        assert "finding.vd.trains_on_us" not in found


# ------------------------------------------------------------ the money line

def test_the_money_line_totals_what_was_typed_and_never_estimates() -> None:
    with as_agency("iia.test"):
        vendors.save({"name": "Priced", "status": "in_use",
                      "amount": 1200, "basis": "year"}, WHO)
        vendors.save({"name": "Unpriced", "status": "in_use"}, WHO)
        said = vendors.money_line()
        assert "a year across what is in use or in a pilot" in said
        assert "1 with no cost recorded" in said
