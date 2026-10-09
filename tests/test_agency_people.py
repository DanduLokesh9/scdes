"""People in an organization, and its admins adding colleagues.

Reported: a colleague tried to register an agency that was already
registered and was told "ask them to add you" — but no screen let the owner
add anybody. Building that turned up two holes, pinned here:

* the add-member endpoint took the owner's address and the organization
  from the request body, so anybody who knew an owner's address could add
  themselves to that organization;
* the public registration lookup returned the whole member list — every
  name, title and email address — to anybody, signed in or not.
"""

from __future__ import annotations

import pytest

from app import server, tenancy, tenant
from app.authz import Actor, Role

OWNER = "brett.butz@des.sc.gov"
MEMBER = "lokesh.dandu@des.sc.gov"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.setattr(server, "_verified_member", lambda actor: bool(actor.email))
    data = tenancy._load()
    for code, owner, members in (
            ("sc.des", OWNER, [(OWNER, "Brett Butz", "owner"),
                               (MEMBER, "Lokesh Dandu", "member")]),
            ("sc.ed", "rebecca.valencia@ed.sc.gov",
             [("rebecca.valencia@ed.sc.gov", "Rebecca Valencia", "owner")])):
        data["agencies"][code] = {
            "code": code, "status": "active", "owner_email": owner,
            "owner_name": members[0][1], "owner_title": "Owner",
            "identity": {"domain": owner.split("@")[1]},
            "members": [{"email": e, "name": n, "title": "Title", "role": r,
                         "added_at": "2026-09-01T12:00:00+00:00"}
                        for e, n, r in members]}
    tenancy._save(data)
    held = tenant.set_current("sc.des")
    yield
    tenant.reset(held)


def _as(email: str) -> Actor:
    return Actor("u", "Someone", Role.OPERATOR, email=email)


def test_the_owner_adds_a_colleague() -> None:
    out = server.api_agency_add_member(_as(OWNER), {
        "name": "Jordan Doe", "title": "Deputy Director",
        "email": "jordan.doe@des.sc.gov"}, {})
    assert out["ok"], out
    names = [p["name"] for p in out["people"]]
    assert "Jordan Doe" in names
    assert "nothing is sent to them from here" in out["says"]
    assert tenancy.access_for("jordan.doe@des.sc.gov")["state"] == "sc.des"


def test_only_the_owner_may_add() -> None:
    out = server.api_agency_add_member(_as(MEMBER), {
        "name": "Jordan Doe", "title": "Deputy", "email": "jordan.doe@des.sc.gov"}, {})
    assert out["ok"] is False
    assert tenancy.access_for("jordan.doe@des.sc.gov")["state"] == ""


def test_the_request_body_cannot_name_another_owner_or_organization() -> None:
    """The hole: "agency" and "by" came from the body."""
    stranger = _as("mallory@des.sc.gov")
    out = server.api_agency_add_member(stranger, {
        "agency": "sc.des", "by": OWNER, "name": "Mallory Smith",
        "title": "Nobody", "email": "mallory@des.sc.gov"}, {})
    assert out["ok"] is False
    assert tenancy.access_for("mallory@des.sc.gov")["state"] == ""
    # And the owner of one organization adds only to their own.
    out = server.api_agency_add_member(_as(OWNER), {
        "agency": "sc.ed", "name": "Jordan Doe", "title": "Deputy",
        "email": "jordan.doe@des.sc.gov"}, {})
    assert out["ok"]
    assert tenancy.access_for("jordan.doe@des.sc.gov")["state"] == "sc.des"


def test_nobody_signed_out_can_add() -> None:
    out = server.api_agency_add_member(_as(""), {
        "name": "Jordan Doe", "title": "Deputy", "email": "jordan.doe@des.sc.gov"}, {})
    assert out["ok"] is False


def test_an_address_off_the_agencys_domain_is_refused() -> None:
    out = server.api_agency_add_member(_as(OWNER), {
        "name": "Jordan Doe", "title": "Deputy", "email": "jordan@gmail.com"}, {})
    assert out["ok"] is False and "des.sc.gov" in out["error"]


def test_admins_see_addresses_and_members_do_not() -> None:
    mine = server.api_agency_people(_as(OWNER), {}, {})
    assert mine["is_admin"] and all("email" in p for p in mine["people"])
    theirs = server.api_agency_people(_as(MEMBER), {}, {})
    assert not theirs["is_admin"] and not any("email" in p for p in theirs["people"])
    # "owner" is what the one-admin model called it; it reads as Admin.
    assert {p["role"] for p in theirs["people"]} == {"Admin", "Member"}
    assert theirs["admin_names"] == ["Brett Butz"]


def test_nobody_signed_out_sees_who_is_in_it() -> None:
    assert server.api_agency_people(_as(""), {}, {})["ok"] is False


def test_the_public_lookup_no_longer_lists_members() -> None:
    """It handed every name, title and address to anybody who asked."""
    out = server.api_tenancy(_as(""), {}, {"agency": ["sc.des"]})
    said = repr(out["agency"])
    assert out["agency"]["exists"] and out["agency"]["active"]
    for leaked in (OWNER, MEMBER, "Brett Butz", "Lokesh Dandu", "members"):
        assert leaked not in said, leaked


# ------------------------------------------------ removing, and handing over

def test_the_owner_removes_somebody_and_they_are_signed_out() -> None:
    token = tenancy.issue_session(MEMBER)
    assert tenancy.session_email(token) == MEMBER
    out = server.api_agency_remove_member(_as(OWNER), {"email": MEMBER}, {})
    assert out["ok"], out
    assert "signed out" in out["says"]
    assert MEMBER not in [p.get("email") for p in out["people"]]
    assert tenancy.access_for(MEMBER)["state"] == ""
    assert tenancy.session_email(token) == ""
    removed = tenancy._load()["agencies"]["sc.des"]["removed"][0]
    assert removed["email"] == MEMBER and removed["removed_by"] == OWNER


def test_the_last_admin_cannot_be_removed_or_demoted() -> None:
    assert server.api_agency_remove_member(_as(MEMBER), {"email": OWNER}, {})["ok"] is False
    out = server.api_agency_remove_member(_as(OWNER), {"email": OWNER}, {})
    assert out["ok"] is False and "only admin" in out["error"]
    out = server.api_agency_role(_as(OWNER), {"email": OWNER, "role": "member"}, {})
    assert out["ok"] is False and "only admin" in out["error"]
    assert tenancy.access_for(OWNER)["state"] == "sc.des"


def test_nobody_is_removed_from_another_organization() -> None:
    out = server.api_agency_remove_member(
        _as(OWNER), {"agency": "sc.ed", "email": "rebecca.valencia@ed.sc.gov"}, {})
    assert out["ok"] is False
    assert tenancy.access_for("rebecca.valencia@ed.sc.gov")["state"] == "sc.ed"


def test_an_admin_makes_another_admin_who_can_then_manage() -> None:
    out = server.api_agency_role(_as(OWNER), {"email": MEMBER, "role": "admin"}, {})
    assert out["ok"], out
    assert "is an admin now" in out["says"]
    held = tenancy._load()["agencies"]["sc.des"]
    assert held["role_history"][-1]["to"] == "admin"
    # Now two admins: either may step down or remove the other.
    out = server.api_agency_role(_as(MEMBER), {"email": OWNER, "role": "member"}, {})
    assert out["ok"], out
    assert server.api_agency_remove_member(_as(MEMBER), {"email": OWNER}, {})["ok"]


def test_a_member_cannot_change_roles() -> None:
    out = server.api_agency_role(_as(MEMBER), {"email": MEMBER, "role": "admin"}, {})
    assert out["ok"] is False
    assert not tenancy.is_agency_admin("sc.des", MEMBER)


def test_an_admin_can_add_somebody_as_an_admin() -> None:
    out = server.api_agency_add_member(_as(OWNER), {
        "name": "Jordan Doe", "title": "Deputy", "email": "jordan.doe@des.sc.gov",
        "role": "admin"}, {})
    assert out["ok"] and "as an admin" in out["says"]
    assert tenancy.is_agency_admin("sc.des", "jordan.doe@des.sc.gov")


def test_roles_change_only_in_your_own_organization() -> None:
    out = server.api_agency_role(_as(OWNER), {"agency": "sc.ed",
        "email": "rebecca.valencia@ed.sc.gov", "role": "member"}, {})
    assert out["ok"] is False
    assert tenancy.is_agency_admin("sc.ed", "rebecca.valencia@ed.sc.gov")


def test_an_address_in_another_organization_cannot_be_added(monkeypatch) -> None:
    data = tenancy._load()
    data["agencies"]["sc.ed"]["members"].append(
        {"email": "jordan.doe@des.sc.gov", "name": "Jordan Doe", "role": "member"})
    tenancy._save(data)
    out = server.api_agency_add_member(_as(OWNER), {
        "name": "Jordan Doe", "title": "Deputy", "email": "jordan.doe@des.sc.gov"}, {})
    assert out["ok"] is False and "another organization" in out["error"]
    assert "sc.ed" not in out["error"] and "Education" not in out["error"]


# ------------------------------------------- picked one agency, belongs to another

def test_the_people_list_names_the_organization_it_belongs_to(monkeypatch) -> None:
    monkeypatch.setattr(tenancy, "_agency_names",
                        lambda code: {"agency_label": f"Label for {code}"})
    out = server.api_agency_people(_as(OWNER), {}, {})
    assert out["organization"] == "Label for sc.des"


def test_signing_in_to_an_agency_the_address_is_not_registered_to_is_refused(monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(tenancy, "start_signin", lambda email: sent.append(email) or {"ok": True})
    monkeypatch.setattr(tenancy, "_agency_names",
                        lambda code: {"agency_label": {"sc.des": "SC Environmental Services",
                                                       "sc.ed": "SC Education"}.get(code, code)})
    out = server.api_signin_agency(_as(""), {"email": OWNER, "agency": "sc.ed"}, {})
    assert out["ok"] is False and out["wrong_agency"]
    assert "not registered to SC Education" in out["error"]
    # It never says where the address IS registered — the endpoint is open.
    assert "Environmental" not in out["error"] and "sc.des" not in out["error"]
    assert sent == []


def test_an_iia_address_is_pointed_to_iias_own_organization(monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(tenancy, "start_signin", lambda email: sent.append(email) or {"ok": True})
    data = tenancy._load()
    data["agencies"]["iia.test"] = {"code": "iia.test", "status": "active",
        "members": [{"email": "lokesh@iiac.ai", "name": "Lokesh", "role": "owner"}]}
    tenancy._save(data)
    out = server.api_signin_agency(_as(""), {"email": "lokesh@iiac.ai", "agency": "sc.des"}, {})
    assert out["ok"] is False and out["iia"] is True
    assert "DEMO agency — Innovative Infrastructure Advising" in out["error"]
    assert "Organizations" in out["error"] and sent == []
    # Anybody else still gets the answer that names nowhere.
    out = server.api_signin_agency(_as(""), {"email": OWNER, "agency": "sc.ed"}, {})
    assert "iia" not in out and "DEMO" not in out["error"]


def test_signing_in_to_the_right_agency_sends_the_code(monkeypatch) -> None:
    sent = []
    monkeypatch.setattr(tenancy, "start_signin", lambda email: sent.append(email) or {"ok": True})
    assert server.api_signin_agency(_as(""), {"email": OWNER, "agency": "sc.des"}, {})["ok"]
    assert server.api_signin_agency(_as(""), {"email": OWNER}, {})["ok"]
    assert sent == [OWNER, OWNER]


def test_the_shell_is_told_which_organization_it_is_serving(monkeypatch) -> None:
    monkeypatch.setattr(tenancy, "_agency_names", lambda code: {"agency_label": "SC Environmental Services"})
    assert server._own_organization() == {"code": "sc.des", "label": "SC Environmental Services"}
    held = tenant.set_current(tenant.ANONYMOUS)
    try:
        assert server._own_organization() == {"code": "", "label": ""}
    finally:
        tenant.reset(held)
