"""Governmental units that are not on the list.

"Don't see your governmental unit? Click here to create your framework —
and then walk them through the onboarding anyway. There just won't be an @
domain requirement."

These pin what the door does: a unit is recorded and registered the ordinary
way with no domain rule, the mailbox is still proven, and the door cannot be
used to register a listed agency around its email rule. And what it does not
do: offer somebody's self-described unit to anybody else.
"""

from __future__ import annotations

import pytest

from app import server, states, tenancy, unlisted

FORM = {"state": "TX", "unit": "Harris County Municipal Utility District No. 12",
        "name": "Jane Doe", "title": "General Manager",
        "email": "jane.doe@gmail.com", "phone": "713-555-0100",
        "attested": True}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    from app import mailer
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": False, "reason": "test"})
    monkeypatch.setattr(mailer, "may_show_code_to", lambda address: True)
    monkeypatch.setattr(mailer, "note_for", lambda d: "test")
    # These are about the unlisted door, not the Terms of Use — every address
    # here is taken to have accepted them. tests/test_terms.py covers the gate.
    from app import terms
    monkeypatch.setattr(terms, "STORE", tmp_path / "terms.json")
    monkeypatch.setattr(terms, "may_register", lambda email: True)
    yield


def _register(**over):
    return server.api_register_unlisted(None, {**FORM, **over}, {})


# ------------------------------------------------------------- the door

def test_a_unit_not_on_the_list_can_register_with_any_address() -> None:
    """No @ domain requirement — a twelve-person district may run on a
    consumer mailbox."""
    got = _register()
    assert got["ok"], got
    assert got["agency"]["name"] == FORM["unit"]
    assert got["agency"]["unlisted"] is True
    assert got["identity"]["confidence"] == "unlisted"


def test_the_mailbox_is_still_proven_with_a_code() -> None:
    """The one check that still means something here."""
    got = _register()
    assert got["ok"]
    unit_id = got["agency"]["id"]
    assert tenancy.access_for(FORM["email"])["status"] == "pending_code"
    verified = tenancy.verify_code(FORM["email"], got["code"])
    assert verified["ok"], verified
    access = tenancy.access_for(FORM["email"])
    assert access["state"] == unit_id


def test_a_wrong_code_does_not_open_it() -> None:
    _register()
    assert not tenancy.verify_code(FORM["email"], "000000")["ok"]


def test_the_unit_gets_an_id_of_its_own_scoped_to_its_state() -> None:
    unit_id = _register()["agency"]["id"]
    assert unit_id.startswith("tx" + unlisted.MARK)
    assert unlisted.is_unlisted(unit_id)
    assert not any(unlisted.is_unlisted(a) for a in states.agency_ids())


def test_the_id_is_safe_to_use_as_a_directory_name() -> None:
    unit_id = _register(unit="Town of St. Mary's / Harbor & Port")["agency"]["id"]
    assert all(c.isalnum() or c in ".-" for c in unit_id)


# ------------------------------------------------ the ordinary checks still apply

def test_the_attestation_is_still_required() -> None:
    assert not _register(attested=False)["ok"]


def test_a_title_is_still_required() -> None:
    assert not _register(title="")["ok"]


def test_a_phone_number_is_still_required() -> None:
    assert not _register(phone="12")["ok"]


def test_an_organization_name_is_required() -> None:
    assert not _register(unit="")["ok"]
    assert not _register(unit="12")["ok"]


def test_a_state_is_required() -> None:
    assert not _register(state="ZZ")["ok"]


def test_a_refused_form_leaves_no_empty_unit_behind() -> None:
    """Minted and then refused would leave an organization with nobody in
    it, occupying an id."""
    assert not _register(phone="12")["ok"]
    assert unlisted._read()["units"] == {}


# ------------------------------------------- it cannot get round the list

def test_a_listed_agency_cannot_be_registered_through_this_door() -> None:
    """Otherwise its name, typed here with a consumer address, walks past
    the domain check the listed entry exists to apply."""
    got = _register(unit="Texas Commission on Environmental Quality")
    assert not got["ok"]
    assert got["listed"] == "tx.env"
    assert "on our list" in got["error"]


def test_nor_by_its_abbreviation() -> None:
    assert not _register(unit="TCEQ")["ok"]


def test_nor_by_changing_the_case_and_the_small_words() -> None:
    assert not _register(unit="TEXAS COMMISSION ENVIRONMENTAL QUALITY")["ok"]


def test_a_different_organization_with_a_similar_word_is_fine() -> None:
    assert _register(unit="Texas City Environmental Quality Board")["ok"]


def test_a_listed_agency_in_another_state_is_not_confused_with_this_one() \
        -> None:
    """Refusal is per state: a name listed in Pennsylvania is not listed in
    Texas."""
    got = _register(unit="Pennsylvania Department of Environmental Protection")
    assert got["ok"]


# ------------------------------------------------------ it stays private

def test_an_unlisted_unit_is_never_offered_in_anybodys_dropdown() -> None:
    unit_id = _register()["agency"]["id"]
    offered = {a["id"] for a in states.agencies_for("TX")}
    assert unit_id not in offered


def test_the_same_person_twice_gets_the_same_unit() -> None:
    """A double click or a second attempt does not mint a second
    organization with a second container."""
    first = _register()["agency"]["id"]
    second = _register()
    assert second["agency"]["id"] == first
    assert len(unlisted._read()["units"]) == 1


def test_two_people_naming_the_same_unit_get_separate_units() -> None:
    """A self-described name is not a claim on anybody else's container."""
    first = _register()["agency"]["id"]
    second = _register(email="someone.else@outlook.com",
                       name="Someone Else")["agency"]["id"]
    assert first != second


# --------------------------------------------- signing back in names the unit

def test_signing_back_in_reports_the_units_own_name() -> None:
    """The dropdown never lists it, so a new browser has only the server to
    ask. Without this the header named the state's environmental agency."""
    got = _register()
    tenancy.verify_code(FORM["email"], got["code"])
    access = tenancy.access_for(FORM["email"])
    assert access["unlisted"] is True
    assert access["agency_label"] == FORM["unit"]
    assert access["agency_abbrev"] == got["agency"]["abbrev"]


def test_a_listed_agency_member_is_reported_as_listed() -> None:
    access = tenancy._agency_names("tx.env")
    assert access["unlisted"] is False
    assert access["agency_label"] == \
        "Texas Commission on Environmental Quality"


def test_the_record_says_the_name_was_not_checked() -> None:
    unit = unlisted.get(_register()["agency"]["id"])
    assert "has not been checked" in unit["provenance"]
    assert "no email domain applies" in unit["provenance"]


def test_the_route_is_registered() -> None:
    assert server.ROUTES[("POST", "/api/agency/register-unlisted")] is \
        server.api_register_unlisted


# ---------------------------------------------------------- abuse limits
#
# The door accepts any address and every registration sends an email. These
# are what stop it being used to flood somebody's inbox or fill the store.

def test_one_address_cannot_be_sent_more_than_a_handful_of_codes() -> None:
    """Pressing Register over and over with a stranger's address would
    otherwise make this application's mail account do the flooding."""
    for _ in range(tenancy.CODES_PER_HOUR):
        assert _register()["ok"]
    refused = _register()
    assert refused["ok"] is False
    assert refused.get("throttled") is True
    assert "flood" in refused["error"]


def test_the_harness_address_has_no_inbox_to_protect() -> None:
    """Its domain does not exist and nothing is mailed to it. The browser
    walks spent its four codes an hour and locked the leak scan out."""
    assert tenancy._is_harness_address("walk@harness.gaius.test")
    assert not tenancy._is_harness_address("walk@harness.gaius.test.evil.com")
    assert not tenancy._is_harness_address("someone@outlook.com")
    data = {"sent": {"walk@harness.gaius.test": [
        tenancy._now().isoformat(timespec="seconds")] * 10}}
    assert tenancy._may_send_code(data, "walk@harness.gaius.test")


def test_the_limit_is_per_recipient_not_per_form() -> None:
    for _ in range(tenancy.CODES_PER_HOUR):
        _register()
    assert _register(email="someone.else@outlook.com",
                     name="Someone Else")["ok"]


def test_the_limit_forgets_after_an_hour(monkeypatch) -> None:
    from datetime import timedelta
    for _ in range(tenancy.CODES_PER_HOUR):
        _register()
    real = tenancy._now
    monkeypatch.setattr(tenancy, "_now", lambda: real() + timedelta(hours=1,
                                                                    minutes=1))
    assert _register()["ok"]


def test_a_refused_send_mints_no_unit() -> None:
    for _ in range(tenancy.CODES_PER_HOUR):
        _register()
    before = len(unlisted._read()["units"])
    _register(unit="A Different District Entirely")
    assert len(unlisted._read()["units"]) == before


def test_one_address_cannot_describe_endless_units(monkeypatch) -> None:
    monkeypatch.setattr(tenancy, "CODES_PER_HOUR", 1000)
    for n in range(unlisted.PER_PERSON):
        assert _register(unit=f"Rural Water District No. {n + 1}")["ok"]
    refused = _register(unit="Rural Water District No. 99")
    assert refused["ok"] is False and refused.get("limited") is True


def test_the_deployment_has_an_hourly_ceiling(monkeypatch) -> None:
    """The limit a run from many addresses meets, which the per-address
    limits cannot see."""
    monkeypatch.setattr(unlisted, "PER_HOUR", 3)
    for n in range(3):
        assert _register(email=f"person{n}@example.test",
                         name="Jane Doe", unit=f"District {n} Board")["ok"]
    refused = _register(email="person9@example.test", unit="District 9 Board")
    assert refused["ok"] is False
    assert refused["error"] == unlisted.BUSY


def test_a_unit_nobody_verified_is_cleared_after_a_week(monkeypatch) -> None:
    got = _register()
    unit_id = got["agency"]["id"]
    held = unlisted._read()
    held["units"][unit_id]["created_at"] = "2026-01-01T00:00:00+00:00"
    unlisted._write(held)
    _register(email="next.person@example.test", unit="Another District")
    assert not unlisted.exists(unit_id)


def test_a_verified_unit_is_never_cleared_however_old() -> None:
    """Somebody's work is in it."""
    got = _register()
    tenancy.verify_code(FORM["email"], got["code"])
    unit_id = got["agency"]["id"]
    held = unlisted._read()
    held["units"][unit_id]["created_at"] = "2020-01-01T00:00:00+00:00"
    unlisted._write(held)
    _register(email="next.person@example.test", unit="Another District")
    assert unlisted.exists(unit_id)
