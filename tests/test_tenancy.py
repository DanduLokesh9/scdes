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

import json

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


def test_a_complete_registration_is_accepted(monkeypatch) -> None:
    # No SMTP in the test environment, so the code falls back to being shown —
    # and the response has to say so. test_mailer covers the configured case,
    # where the code must NOT come back.
    for name in ("SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(name, raising=False)
    result = tenancy.start_registration(**_good())
    assert result["ok"]
    assert result["code"], "a code must be issued"
    assert result["emailed"] is False
    assert "shown here" in result["delivery_note"].lower(), (
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


def test_the_right_code_verifies_and_opens_the_container() -> None:
    """Client's call: register and verify is enough, for today."""
    code, email = _registered()
    result = tenancy.verify_code(email, code)
    assert result["ok"]
    assert result["status"] == "active"
    agency = tenancy.agency_state("sc.des")
    assert agency["exists"] and agency["owner"] == email
    assert agency["active"]


def test_opening_on_verification_alone_says_so_on_the_record() -> None:
    """Dropping the reviewer is a decision with a cost. The cost is recorded, not
    hidden — a blank approver reads as "pending", which would be a lie."""
    code, email = _registered()
    result = tenancy.verify_code(email, code)
    assert result["authority_verified"] is False
    assert "nobody has checked" in result["next"].lower()

    raw = json.loads(tenancy.STORE.read_text(encoding="utf-8"))
    container = raw["agencies"]["sc.des"]
    assert container["authority_verified"] is False
    assert container["approved_by"], "an empty approver reads as pending"
    assert "not reviewed" in container["approved_by"].lower()


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

def test_verifying_grants_access(monkeypatch) -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    access = tenancy.access_for(email)
    assert access["allowed"]
    # Registering no longer makes you the admin: the GAIUS team appoints one.
    assert access["state"] == "sc.des" and access["role"] == "member"
    assert tenancy.agency_state("sc.des")["needs_admin"] is True


def test_the_reviewer_queue_can_be_switched_back_on(monkeypatch) -> None:
    """It is a switch, not a deletion. When the client wants the queue back it
    is one environment variable, not a code change and a redeploy."""
    monkeypatch.setenv("IIA_REVIEW_REQUIRED", "1")
    code, email = _registered()
    result = tenancy.verify_code(email, code)
    assert result["status"] == "pending_approval"
    assert not tenancy.access_for(email)["allowed"], "verified is not approved"

    tenancy.approve("sc.des", reviewer="IIA reviewer")
    approved = tenancy.access_for(email)
    assert approved["allowed"]
    assert approved["state"] == "sc.des" and approved["role"] == "member"


def test_a_second_person_cannot_claim_the_same_agency() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    blocked = tenancy.start_registration(**_good(
        name="Bob Jones", email="bob.jones@des.sc.gov"))
    assert not blocked["ok"]
    assert "already been registered" in blocked["error"]
    assert "GAIUS team is appointing its admin" in blocked["error"], "say who to ask"
    tenancy.appoint("sc.des", "brett@iiac.ai", "Jane Smith", "Director",
                    "jane.smith@des.sc.gov")
    blocked = tenancy.start_registration(**_good(
        name="Bob Jones", email="bob.jones@des.sc.gov"))
    assert "Jane Smith" in blocked["error"], "once there is an admin, name them"


def test_only_an_admin_may_add_people() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)

    refused = tenancy.add_member("sc.des", by_email="bob.jones@des.sc.gov",
                                 name="Bob Jones", title="Analyst",
                                 email="bob.jones@des.sc.gov")
    assert not refused["ok"]
    assert "only an admin" in refused["error"].lower()
    # Nor the registrant, until the GAIUS team makes them admin.
    assert not tenancy.add_member("sc.des", by_email=email, name="Bob Jones",
                                  title="Analyst", email="bob.jones@des.sc.gov")["ok"]
    assert tenancy.appoint("sc.des", "lokesh@iiac.ai", "", "", email)["ok"]

    allowed = tenancy.add_member("sc.des", by_email=email, name="Bob Jones",
                                 title="Analyst", email="bob.jones@des.sc.gov")
    assert allowed["ok"]
    assert len(tenancy.agency_state("sc.des")["members"]) == 2


def test_added_members_face_the_same_convention_check() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    tenancy.approve("sc.des", reviewer="IIA reviewer")
    tenancy.appoint("sc.des", "dev@iiac.ai", "", "", email)
    bad = tenancy.add_member("sc.des", by_email=email, name="Sue Ray",
                             title="Analyst", email="sray@des.sc.gov")
    assert not bad["ok"], "the owner cannot wave through a mismatched address"


def test_members_cannot_be_added_before_approval(monkeypatch) -> None:
    """Only relevant while the queue is on — an unreleased container is not a
    container anyone may start filling with colleagues."""
    monkeypatch.setenv("IIA_REVIEW_REQUIRED", "1")
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


def test_the_delivery_note_reports_reality_rather_than_a_fixed_string(
        monkeypatch) -> None:
    """It used to claim "no mail path" forever, including after SMTP was set up.

    An interface confidently stating the opposite of what the server does is
    worse than one that says nothing, so the note is derived, not asserted.
    """
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    off = tenancy.summary()
    assert off["email_configured"] is False
    assert "shown on screen" in off["notes"]["delivery"].lower()

    monkeypatch.setenv("SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    on = tenancy.summary()
    assert on["email_configured"] is True
    assert "emailed" in on["notes"]["delivery"].lower()


def test_codes_are_not_stored_in_the_clear() -> None:
    import json
    code, email = _registered()
    raw = json.loads(tenancy.STORE.read_text(encoding="utf-8"))
    stored = raw["pending"][email]
    assert "code" not in stored, "the code itself must not be persisted"
    assert stored["code_hash"] != code


# ------------------------------------------------------------- getting back in

def test_someone_already_registered_can_sign_in_again() -> None:
    """Register was the only door.

    It claims an agency and refuses if that agency is taken, so the person who
    registered it and then signed out was told the agency "has already been
    registered by <their own name>. Ask them to add you." A one-way door into a
    product is a product nobody gets back into.
    """
    code, email = _registered()
    tenancy.verify_code(email, code)
    assert tenancy.access_for(email)["allowed"]

    again = tenancy.start_signin(email)
    assert again["ok"]
    assert again["code"], "a fresh code, since SMTP is off in tests"
    assert again["state"] == "sc.des"

    done = tenancy.verify_code(email, again["code"])
    assert done["ok"]
    assert done["signin"] is True
    assert tenancy.access_for(email)["allowed"]


def test_signing_in_creates_no_second_container() -> None:
    """It proves the mailbox and nothing else. The container already exists."""
    code, email = _registered()
    tenancy.verify_code(email, code)
    before = tenancy.agency_state("sc.des")

    tenancy.verify_code(email, tenancy.start_signin(email)["code"])
    after = tenancy.agency_state("sc.des")
    assert after["owner"] == before["owner"]
    assert len(after["members"]) == len(before["members"])
    assert after["created_at"] == before["created_at"]


def test_registering_your_own_agency_again_points_at_signing_in() -> None:
    """Telling someone to ask themselves for access reads as a broken product."""
    code, email = _registered()
    tenancy.verify_code(email, code)

    again = tenancy.start_registration(**_good())
    assert not again["ok"]
    assert again["is_you"] is True
    assert "sign in" in again["error"].lower()


def test_someone_else_is_still_told_to_ask_the_owner() -> None:
    code, email = _registered()
    tenancy.verify_code(email, code)
    other = tenancy.start_registration(**_good(
        name="Bob Jones", email="bob.jones@des.sc.gov"))
    assert not other["ok"]
    assert other.get("taken") is True
    assert not other.get("is_you")
    assert "GAIUS team" in other["error"]


def test_signing_in_with_an_unknown_address_names_nobody() -> None:
    """Confirming which addresses exist would let anyone map an agency's staff
    from the sign-in box."""
    code, email = _registered()
    tenancy.verify_code(email, code)

    stranger = tenancy.start_signin("nobody@des.sc.gov")
    assert not stranger["ok"]
    assert "Jane" not in stranger["error"]
    assert "jane.smith" not in stranger["error"]


@pytest.mark.parametrize("address", ["", "   ", "not-an-email"])
def test_a_nonsense_address_cannot_request_a_code(address: str) -> None:
    assert not tenancy.start_signin(address)["ok"]


# -------------------------------------------------- the second state to open

def test_new_mexico_is_open_and_offers_its_agency() -> None:
    """The first state opened after South Carolina, at the client's request:
    "add new state which New Mexico Dept of the Environment, email of this
    state must end with this @env.nm.gov"."""
    from app import states

    assert states.is_open("NM")
    offered = states.agencies_for("NM")
    assert len(offered) == 1
    agency = offered[0]
    assert agency["id"] == "nm.env"
    assert agency["domain"] == "env.nm.gov"
    # Registration refuses an agency id it does not know, so the dropdown and
    # the registry have to agree about this one existing.
    assert "nm.env" in states.agency_ids()


def test_the_new_agency_is_named_the_same_everywhere() -> None:
    """One agency, one name.

    The map takes its label from `AGENCIES` and the dropdown from
    `STATE_AGENCIES`, and the two disagreed — the map said "New Mexico
    Environment Department" while the registration form said "Department of
    the Environment". Whichever name is right, a product that uses both is
    wrong, and the name reaches the front page of a document somebody adopts.
    """
    from app import states

    on_the_map = states.entry("NM").as_dict()["agency"]
    in_the_dropdown = states.agencies_for("NM")[0]["name"]
    in_the_registry = tenancy.CONFIRMED["nm.env"]["label"]
    assert on_the_map == in_the_dropdown == in_the_registry


@pytest.mark.parametrize("address", [
    "jane.doe@env.nm.gov",
    # No convention was confirmed, so the local part is not checked. A guessed
    # rule that refuses a real deputy director is worse than no rule.
    "jdoe@env.nm.gov",
    "j.doe@ENV.NM.GOV",
])
def test_a_new_mexico_address_may_register(address: str) -> None:
    assert tenancy.check_identity("nm.env", "Jane Doe", address).ok, address


@pytest.mark.parametrize("address", [
    "jane.doe@des.sc.gov",
    "jane@gmail.com",
    # The state's own domain is not the agency's domain.
    "jane@nm.gov",
    # A lookalike. The check is the domain, not a suffix of the address.
    "jane@env.nm.gov.example.com",
    "jane@notenv.nm.gov",
])
def test_another_domain_may_not_register_as_new_mexico(address: str) -> None:
    checked = tenancy.check_identity("nm.env", "Jane Doe", address)
    assert not checked.ok, address
    # Says which domain was expected, so a refusal is actionable rather than
    # just a no.
    assert "env.nm.gov" in checked.reason


def test_the_two_real_agencies_cannot_register_as_each_other() -> None:
    """Two real agencies in two states is the case the isolation rule exists
    for — until now there was one real agency and some test containers.

        "THE ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE OR HAVE ACCESS
         TO OTHER AGENCIES."
    """
    assert not tenancy.check_identity(
        "sc.des", "Jane Doe", "jane.doe@env.nm.gov").ok
    assert not tenancy.check_identity(
        "nm.env", "Jane Doe", "jane.doe@des.sc.gov").ok


def test_the_unconfirmed_convention_is_recorded_as_unconfirmed() -> None:
    """He gave the domain and not the naming rule. The loose setting is the
    honest one, and saying so on the record is what stops it being read later
    as a confirmed convention nobody confirmed."""
    entry = tenancy.CONFIRMED["nm.env"]
    assert entry["convention"] == "any"
    assert "not yet confirmed" in entry["source"]
    from app import states
    assert states.agencies_for("NM")[0]["confidence"] == "none"
