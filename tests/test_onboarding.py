"""Portal eligibility.

The rule exists twice — once in app/onboarding.py and once in onboard.js so the
field can answer while you type. These tests cover the server's copy, because
that is the one that decides; the browser's is a convenience that can be edited
away in a console.

What is being tested is *eligibility*, not identity. Nothing here proves anyone
works where they say they do, and the module says so at length. These tests
guard the boundary that does exist: which claims are accepted, and that an
accepted one is recorded as unverified.
"""

from __future__ import annotations

import json

import pytest

from app import onboarding


# ------------------------------------------------------------------- portals

def test_three_portals_are_offered() -> None:
    keys = {p["key"] for p in onboarding.portals()}
    assert keys == {"government", "other", "business"}


# ------------------------------------------------ a public body on another address

@pytest.mark.parametrize("email", [
    "mju@cityofmonticello.net",       # the report that opened this
    "clerk@scalc.net",
    "admin@townofexample.com",
    "gm@harriscountymud12.com",
])
def test_a_public_body_on_any_address_can_come_in_as_other(email: str) -> None:
    verdict = onboarding.check_email(email, portal="other")
    assert verdict.ok, verdict.reason
    assert verdict.evidence == "other"


def test_other_takes_a_personal_mailbox_and_says_so() -> None:
    """The same rule as the unlisted registration it leads to: a small
    district may run on a personal mailbox. Recorded as such."""
    verdict = onboarding.check_email("clerk.smalltown@gmail.com", portal="other")
    assert verdict.ok and verdict.evidence == "other-personal"


def test_the_government_option_points_a_personal_mailbox_to_other() -> None:
    verdict = onboarding.check_email("someone@gmail.com")
    assert not verdict.ok and "Other public body" in verdict.reason


def test_the_government_refusal_points_to_other() -> None:
    """It used to dead-end a city on .net with "needs a .gov address"."""
    verdict = onboarding.check_email("mju@cityofmonticello.net")
    assert not verdict.ok
    assert "Other public body" in verdict.reason


def test_an_other_registration_is_recorded_as_other(tmp_path, monkeypatch) -> None:
    store = tmp_path / "registrations.jsonl"
    monkeypatch.setattr(onboarding, "STORE", store)
    out = onboarding.register("mju@cityofmonticello.net", portal="other",
                              organisation="City of Monticello")
    assert out["ok"]
    entry = json.loads(store.read_text(encoding="utf-8").strip())
    assert entry["portal"] == "other" and entry["evidence"] == "other"
    assert entry["verified"] is False


def test_the_business_portal_is_announced_but_closed() -> None:
    """Shown rather than hidden — knowing it is planned is the useful part."""
    business = onboarding.PORTALS["business"]
    assert business["open"] is False
    assert business["blurb"], "a closed portal still has to explain itself"


def test_the_business_portal_refuses_registration() -> None:
    verdict = onboarding.check_email("someone@vendor.com", portal="business")
    assert not verdict.ok
    assert "not open" in verdict.reason.lower()
    # …and a valid public-sector address does not sneak in through it either.
    assert not onboarding.check_email("a@agency.gov", portal="business").ok


def test_an_unknown_portal_is_refused() -> None:
    assert not onboarding.check_email("a@agency.gov", portal="nonsense").ok


# --------------------------------------------------------------- eligibility

@pytest.mark.parametrize("email", [
    "commissioner@tceq.texas.gov",
    "analyst@epa.ohio.gov",
    "staff@deq.state.mt.us",          # suffix match must reach through subdomains
    "clerk@scdes.sc.gov",
    "officer@army.mil",
    "researcher@university.edu",
    "director@riverkeeper.org",
    "team@example.us",
])
def test_public_sector_and_non_profit_addresses_pass(email: str) -> None:
    verdict = onboarding.check_email(email)
    assert verdict.ok, f"{email} was refused: {verdict.reason}"


@pytest.mark.parametrize("email", [
    "someone@vendor.com",
    "sales@consultancy.net",
    "hello@startup.io",
    "team@agency.co",
])
def test_commercial_addresses_are_refused(email: str) -> None:
    verdict = onboarding.check_email(email)
    assert not verdict.ok
    # Pointed somewhere, never a dead end.
    assert "other public body" in verdict.reason.lower()


@pytest.mark.parametrize("email", [
    "someone@gmail.com", "someone@outlook.com", "someone@proton.me",
    "someone@yahoo.com", "someone@icloud.com",
])
def test_personal_mailboxes_get_a_useful_refusal(email: str) -> None:
    """"Use your organization's address" beats "invalid domain"."""
    verdict = onboarding.check_email(email)
    assert not verdict.ok
    assert "personal mailbox" in verdict.reason.lower()


@pytest.mark.parametrize("email", [
    "", "   ", "not-an-email", "@agency.gov", "someone@", "a b@agency.gov",
    "someone@agency", "someone@@agency.gov",
])
def test_malformed_input_is_refused_without_raising(email: str) -> None:
    verdict = onboarding.check_email(email)
    assert not verdict.ok
    assert verdict.reason, "a refusal must say why"


def test_case_and_whitespace_do_not_matter() -> None:
    assert onboarding.check_email("  Commissioner@TCEQ.Texas.GOV  ").ok


# --------------------------------------------------- strength of the evidence

def test_restricted_registries_are_distinguished_from_open_ones() -> None:
    """.gov is evidence. .org is a purchase. The record keeps them apart."""
    assert onboarding.check_email("a@agency.gov").evidence == "restricted"
    assert onboarding.check_email("a@base.mil").evidence == "restricted"
    assert onboarding.check_email("a@school.edu").evidence == "restricted"
    assert onboarding.check_email("a@charity.org").evidence == "open"
    assert onboarding.check_email("a@group.us").evidence == "open"


# ------------------------------------------------------------- registration

def test_registering_records_an_unverified_claim(tmp_path, monkeypatch) -> None:
    store = tmp_path / "registrations.jsonl"
    monkeypatch.setattr(onboarding, "STORE", store)

    result = onboarding.register("commissioner@tceq.texas.gov",
                                 organisation="TCEQ")
    assert result["ok"]
    lines = store.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1

    entry = json.loads(lines[0])
    assert entry["email"] == "commissioner@tceq.texas.gov"
    assert entry["domain"] == "tceq.texas.gov"
    assert entry["portal"] == "government"
    assert entry["organisation"] == "TCEQ"
    assert entry["evidence"] == "restricted"
    # The crucial field: nothing here has been confirmed.
    assert entry["verified"] is False
    assert "not verified" in entry["note"]
    assert entry["at"], "an entry without a time is not a record"


def test_an_ineligible_registration_writes_nothing(tmp_path, monkeypatch) -> None:
    store = tmp_path / "registrations.jsonl"
    monkeypatch.setattr(onboarding, "STORE", store)

    assert not onboarding.register("someone@gmail.com")["ok"]
    assert not onboarding.register("someone@vendor.com")["ok"]
    assert not onboarding.register("a@agency.gov", portal="business")["ok"]
    assert not store.exists(), "a refused registration must leave no trace"


def test_registrations_append_rather_than_replace(tmp_path, monkeypatch) -> None:
    store = tmp_path / "registrations.jsonl"
    monkeypatch.setattr(onboarding, "STORE", store)

    onboarding.register("one@agency.gov")
    onboarding.register("two@charity.org")
    assert len(store.read_text(encoding="utf-8").strip().splitlines()) == 2


def test_a_long_organisation_name_is_bounded(tmp_path, monkeypatch) -> None:
    """Unbounded free text from an unauthenticated endpoint is a bad idea."""
    monkeypatch.setattr(onboarding, "STORE", tmp_path / "r.jsonl")
    result = onboarding.register("a@agency.gov", organisation="x" * 500)
    assert len(result["registered"]["organisation"]) <= 120


# ------------------------------------------------------------------- summary

def test_the_summary_states_that_nothing_is_verified() -> None:
    """The UI renders this text; if it stops being honest, that shows here."""
    notice = onboarding.summary()["notice"].lower()
    assert "not verified" in notice or "checked, not verified" in notice
    assert onboarding.summary()["eligible_suffixes"], "the UI needs the list"


def test_summary_suffixes_match_the_rule_actually_applied() -> None:
    """The screen must not advertise a suffix the check would reject."""
    for suffix in onboarding.summary()["eligible_suffixes"]:
        assert onboarding.check_email(f"someone@example{suffix}").ok, (
            f"{suffix} is advertised but refused")
