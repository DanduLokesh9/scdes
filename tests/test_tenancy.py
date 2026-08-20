"""Registration, identity matching and agency containers.

The rules under test are the client's, stated plainly:

  · the entered name, the email local part and the agency domain must all agree;
  · a verification code proves control of the mailbox;
  · the first verified registrant owns the agency container;
  · nobody else may register that agency;
  · only the owner may add people;
  · no access to anything until the registration is active.

One rule is deliberately *not* tested, because it is deliberately not
implemented: nothing here infers seniority from an email address. `seniority_flag`
is asserted to be advisory only — if a future change starts refusing people on a
title, these tests fail, which is the intent.
"""

from __future__ import annotations

import pytest

from app import tenancy


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    """Never touch the real tenancy file."""
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")


# ------------------------------------------------------- name / email matching

@pytest.mark.parametrize("name,email", [
    ("Jane Smith", "jane.smith@des.sc.gov"),
    ("JANE SMITH", "Jane.Smith@DES.SC.GOV"),          # case must not matter
    ("Mary O'Brien", "mary.obrien@des.sc.gov"),       # apostrophes drop out
    ("Anne-Marie Lopez", "anne-marie.lopez@des.sc.gov"),
    ("Jane Q Smith", "jane.smith@des.sc.gov"),        # middle name ignored
    ("Jane Smith", "jane.smith@mail.des.sc.gov"),     # subdomain is still theirs
])
def test_correct_address_for_the_agency_passes(name: str, email: str) -> None:
    check = tenancy.check_identity("sc.des", name, email)
    assert check.ok, check.reason
    assert check.confidence == "strict", "SC's convention is on record"


@pytest.mark.parametrize("name,email,because", [
    ("Jane Smith", "jsmith@des.sc.gov", "wrong convention for this agency"),
    ("Jane Smith", "bob.jones@des.sc.gov", "someone else's address"),
    ("Jane Smith", "jane.smith@gmail.com", "personal domain"),
    ("Jane Smith", "jsmith@des.sc.gov", "a different department's convention"),
    ("Jane", "jane.smith@des.sc.gov", "no surname to check against"),
    ("Jane Smith", "not-an-email", "not an address at all"),
])
def test_mismatches_are_refused(name: str, email: str, because: str) -> None:
    check = tenancy.check_identity("sc.des", name, email)
    assert not check.ok, f"should have been refused: {because}"
    assert check.reason, "a refusal has to say why"


def test_the_refusal_says_what_was_expected() -> None:
    """"Invalid" helps nobody; the message names the correct form."""
    check = tenancy.check_identity("sc.des", "Jane Smith", "jsmith@des.sc.gov")
    assert "jane.smith@des.sc.gov" in check.reason


def test_an_agency_with_no_recorded_convention_is_looser_and_says_so() -> None:
    """Guessing 51 conventions would refuse real people. Report the looseness."""
    check = tenancy.check_identity("tx.tceq", "Jane Smith", "jsmith@tceq.texas.gov")
    assert check.ok
    assert check.confidence == "loose", "must not claim strict knowledge"
    assert tenancy.check_identity("tx.tceq", "Jane Smith", "nope@tceq.texas.gov").ok is False


def test_known_conventions_are_evidenced_not_guessed() -> None:
    for code, entry in tenancy.KNOWN.items():
        assert entry.get("source"), f"{code} convention has no stated source"


# ------------------------------------------------------------ what registration
#                                                              requires up front

def _good(**over):
    args = dict(agency="sc.des", name="Jane Smith", title="Deputy Director",
                email="jane.smith@des.sc.gov", phone="8035550100",
                attested=True)
    args.update(over)
    return args


def test_a_complete_registration_is_accepted() -> None:
    result = tenancy.start_registration(**_good())
    assert result["ok"]
    assert result["code"], "a code must be issued"
    assert "no mail path" in result["delivery"], (
        "the response must admit the code was not emailed")


@pytest.mark.parametrize("over,missing", [
    ({"attested": False}, "authority"),
    ({"title": ""}, "title"),
    ({"phone": "555"}, "phone"),
    ({"name": "J"}, "name"),
])
def test_incomplete_registrations_are_refused(over: dict, missing: str) -> None:
    result = tenancy.start_registration(**_good(**over))
    assert not result["ok"]
    assert missing in result["error"].lower()


def test_a_title_is_recorded_but_never_decides() -> None:
    """Seniority cannot be inferred from an address, so it must not gate entry."""
    junior = tenancy.start_registration(**_good(title="Summer Intern"))
    assert junior["ok"], "a title must not refuse anyone — a reviewer decides"
    assert junior["registration"]["seniority"]["looks"] == "junior"
    assert "reviewer" in junior["registration"]["seniority"]["note"].lower()


# --------------------------------------------------------------- verification

def _registered(**over):
    result = tenancy.start_registration(**_good(**over))
    return result["code"], _good(**over)["email"]


def test_the_right_code_verifies_and_creates_the_container() -> None:
    code, email = _registered()
    result = tenancy.verify_code(email, code)
    assert result["ok"]
    assert result["status"] == "pending_approval"
    agency = tenancy.agency_state("sc.des")
    assert agency["exists"] and agency["owner"] == email
    assert not agency["active"], "mailbox control is not authority"


def test_a_wrong_code_is_refused_and_attempts_are_limited() -> None:
    code, email = _registered()
    for _ in range(6):
        assert not tenancy.verify_code(email, "000000")["ok"]
    result = tenancy.verify_code(email, code)
    assert not result["ok"], "must lock out after repeated failures"
    assert "too many" in result["error"].lower()


def test_an_expired_code_is_refused(monkeypatch) -> None:
    from datetime import datetime, timedelta, timezone
    code, email = _registered()
    later = datetime.now(timezone.utc) + timedelta(minutes=61)
    monkeypatch.setattr(tenancy, "_now", lambda: later)
    assert "expired" in tenancy.verify_code(email, code)["error"].lower()


def test_verifying_an_unknown_address_is_refused() -> None:
    assert not tenancy.verify_code("nobody@des.sc.gov", "123456")["ok"]


# ------------------------------------------------------------ the container

def test_no_access_until_a_reviewer_approves() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    access = tenancy.access_for(email)
    assert not access["allowed"], "verified is not approved"
    assert access["status"] == "pending_approval"

    tenancy.approve("sc.des", reviewer="IIA reviewer")
    approved = tenancy.access_for(email)
    assert approved["allowed"]
    assert approved["state"] == "sc.des" and approved["role"] == "owner"


def test_a_second_person_cannot_claim_the_same_agency() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    blocked = tenancy.start_registration(**_good(
        name="Bob Jones", email="bob.jones@des.sc.gov"))
    assert not blocked["ok"]
    assert "already been registered" in blocked["error"]
    assert "Jane Smith" in blocked["error"], "say who to ask"


def test_only_the_owner_may_add_people() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    tenancy.approve("sc.des", reviewer="IIA reviewer")

    refused = tenancy.add_member("sc.des", by_email="bob.jones@des.sc.gov",
                                 name="Bob Jones", title="Analyst",
                                 email="bob.jones@des.sc.gov")
    assert not refused["ok"]
    assert "only the person who registered" in refused["error"].lower()

    allowed = tenancy.add_member("sc.des", by_email=email, name="Bob Jones",
                                 title="Analyst", email="bob.jones@des.sc.gov")
    assert allowed["ok"]
    assert len(tenancy.agency_state("sc.des")["members"]) == 2


def test_added_members_face_the_same_convention_check() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    tenancy.approve("sc.des", reviewer="IIA reviewer")
    bad = tenancy.add_member("sc.des", by_email=email, name="Sue Ray",
                             title="Analyst", email="sray@des.sc.gov")
    assert not bad["ok"], "the owner cannot wave through a mismatched address"


def test_members_cannot_be_added_before_approval() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    result = tenancy.add_member("sc.des", by_email=email, name="Bob Jones",
                                title="Analyst", email="bob.jones@des.sc.gov")
    assert not result["ok"]


def test_a_stranger_sees_nothing() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    tenancy.approve("sc.des", reviewer="IIA reviewer")
    outside = tenancy.access_for("someone@elsewhere.gov")
    assert not outside["allowed"]
    assert outside["state"] == "", "no agency may leak to a non-member"


def test_a_member_of_one_agency_cannot_see_another() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    tenancy.approve("sc.des", reviewer="IIA reviewer")
    assert tenancy.access_for(email)["state"] == "sc.des"
    assert not tenancy.agency_state("tx.tceq")["exists"]


# ------------------------------------------------------------------- honesty

def test_the_summary_admits_what_is_not_proven() -> None:
    notes = tenancy.summary()["notes"]
    assert "mailbox" in notes["mailbox"].lower()
    assert "seniority" in notes["authority"].lower()
    assert "no mail path" in notes["delivery"].lower()


def test_codes_are_not_stored_in_the_clear() -> None:
    import json
    code, email = _registered()
    raw = json.loads(tenancy.STORE.read_text(encoding="utf-8"))
    stored = raw["pending"][email]
    assert "code" not in stored, "the code itself must not be persisted"
    assert stored["code_hash"] != code
