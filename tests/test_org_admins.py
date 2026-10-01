"""The GAIUS team's permanent owners, and the organizations' admins.

brett@, lokesh@ and dev@iiac.ai appoint every organization's admins, in any
state, and clear sign-ups that never finished. People only — nothing here
reaches an organization's framework. A new registration has no admin until
they appoint one.
"""

from __future__ import annotations

import json

import pytest

from app import mailer, server, tenancy, tenant
from app.authz import Actor, Role

TEAM = "lokesh@iiac.ai"
REG = "jane.smith@des.sc.gov"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.delenv("GAIUS_ADMINS", raising=False)
    monkeypatch.delenv("IIA_REVIEW_REQUIRED", raising=False)
    data = tenancy._load()
    data["agencies"]["sc.des"] = {
        "code": "sc.des", "status": "active", "owner_email": REG,
        "owner_name": "Jane Smith", "identity": {"domain": "des.sc.gov"},
        "members": [{"email": REG, "name": "Jane Smith", "title": "Analyst",
                     "role": "member"}]}
    data["pending"]["anna.grondin@env.nm.gov"] = {
        "state": "nm.env", "name": "Anna Grondin", "title": "Chief",
        "email": "anna.grondin@env.nm.gov", "status": "pending_code",
        "created_at": "2026-09-16T12:00:00+00:00",
        "code_expires": "2026-09-16T13:00:00+00:00", "attempts": 0}
    tenancy._save(data)
    held = tenant.set_current("sc.des")
    yield
    tenant.reset(held)


def _as(email: str) -> Actor:
    return Actor("u", "Someone", Role.OPERATOR, email=email)


# ----------------------------------------------------------- who may do it

@pytest.mark.parametrize("fn,body", [
    ("api_admin_organizations", {}),
    ("api_admin_appoint", {"agency": "sc.des", "email": REG}),
    ("api_admin_member_role", {"agency": "sc.des", "email": REG, "role": "admin"}),
    ("api_admin_member_remove", {"agency": "sc.des", "email": REG}),
    ("api_admin_pending_remove", {"email": "anna.grondin@env.nm.gov"}),
])
def test_only_the_gaius_team(fn, body):
    for who in ("", REG, "brett.butz@des.sc.gov", "someone@iiac.ai"):
        out = getattr(server, fn)(_as(who), body, {})
        assert out["ok"] is False and "GAIUS team" in out["error"], (fn, who)
    held = tenancy._load()
    assert held["agencies"]["sc.des"]["members"][0]["role"] == "member"
    assert "anna.grondin@env.nm.gov" in held["pending"]


def test_all_three_are_permanent_owners():
    for who in ("brett@iiac.ai", "lokesh@iiac.ai", "dev@iiac.ai"):
        assert server.api_admin_organizations(_as(who), {}, {})["ok"] is True


# ----------------------------------------------------------- the screen

def test_the_list_is_people_only_and_flags_waiting():
    out = server.api_admin_organizations(_as(TEAM), {}, {})
    org = next(o for o in out["organizations"] if o["agency"] == "sc.des")
    assert org["needs_admin"] is True and out["waiting"] == 1
    assert org["people"][0] == {"email": REG, "name": "Jane Smith", "title": "Analyst",
                                "role": "member", "added_at": ""}
    assert set(org) == {"agency", "organization", "state", "status", "created_at",
                        "test", "needs_admin", "people"}
    pend = out["pending"][0]
    assert pend["name"] == "Anna Grondin" and pend["code_expired"] is True


# ----------------------------------------------------------- appointing

def test_appoint_promotes_the_registrant_who_can_then_add():
    out = server.api_admin_appoint(_as(TEAM), {"agency": "sc.des", "email": REG}, {})
    assert out["ok"], out
    assert tenancy.is_agency_admin("sc.des", REG)
    assert out["waiting"] == 0
    added = tenancy.add_member("sc.des", REG, "Bob Jones", "Analyst", "bob.jones@des.sc.gov")
    assert added["ok"], added


def test_appoint_opens_an_agency_nobody_registered():
    out = server.api_admin_appoint(_as(TEAM), {
        "agency": "sc.scdor", "name": "Pat Lee", "title": "Director",
        "email": "pat.lee@dor.sc.gov"}, {})
    assert out["ok"], out
    assert tenancy.is_agency_admin("sc.scdor", "pat.lee@dor.sc.gov")
    assert tenancy.access_for("pat.lee@dor.sc.gov")["allowed"]


def test_appoint_still_applies_the_email_rule():
    out = server.api_admin_appoint(_as(TEAM), {
        "agency": "sc.des", "name": "Pat Lee", "title": "Director",
        "email": "pat@gmail.com"}, {})
    assert out["ok"] is False
    assert tenancy.access_for("pat@gmail.com")["state"] == ""


def test_appoint_refuses_an_unknown_agency():
    out = server.api_admin_appoint(_as(TEAM), {
        "agency": "zz.nothing", "name": "Pat Lee", "title": "D", "email": "p@x.gov"}, {})
    assert out["ok"] is False


def test_the_team_can_remove_even_the_last_admin():
    server.api_admin_appoint(_as(TEAM), {"agency": "sc.des", "email": REG}, {})
    out = server.api_admin_member_role(_as(TEAM), {"agency": "sc.des", "email": REG,
                                                   "role": "member"}, {})
    assert out["ok"], out
    out = server.api_admin_member_remove(_as(TEAM), {"agency": "sc.des", "email": REG}, {})
    assert out["ok"], out
    assert tenancy.access_for(REG)["state"] == ""
    removed = tenancy._load()["agencies"]["sc.des"]["removed"][-1]
    assert removed["removed_by"] == TEAM and removed["removed_as"] == "GAIUS team"


# ----------------------------------------------------------- pending sign-ups

def test_a_pending_signup_is_removed_and_kept_on_record():
    out = server.api_admin_pending_remove(_as(TEAM), {"email": "anna.grondin@env.nm.gov"}, {})
    assert out["ok"], out
    held = tenancy._load()
    assert "anna.grondin@env.nm.gov" not in held["pending"]
    assert held["removed_pending"][-1]["removed_by"] == TEAM
    assert out["pending"] == []


def test_a_finished_signup_cannot_be_removed_this_way():
    out = server.api_admin_pending_remove(_as(TEAM), {"email": REG}, {})
    assert out["ok"] is False


# ----------------------------------------------------------- audit and notice

def test_every_change_is_on_the_audit_log(monkeypatch):
    logged = []

    class Log:
        def append(self, **kw):
            logged.append(kw)

    monkeypatch.setattr("app.authz.default_log", lambda: Log())
    server.api_admin_appoint(_as(TEAM), {"agency": "sc.des", "email": REG}, {})
    server.api_admin_pending_remove(_as(TEAM), {"email": "anna.grondin@env.nm.gov"}, {})
    actions = [(e["action"], e["detail"]["agency"], e["detail"]["by"]) for e in logged]
    assert ("appoint_admin", "sc.des", TEAM) in actions
    assert ("remove_pending_signup", "nm.env", TEAM) in actions


def test_the_team_is_told_when_an_organization_needs_an_admin(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None:
                        sent.append((to, subject, text)) or {"sent": True})

    class Now:
        def __init__(self, target, name, daemon):
            self.target = target

        def start(self):
            self.target()

    monkeypatch.setattr("threading.Thread", Now)
    server.notify_needs_admin("sc.des", "Jane Smith", "Analyst", REG)
    assert sorted(t for t, _, _ in sent) == ["brett@iiac.ai", "dev@iiac.ai", "lokesh@iiac.ai"]
    assert "needs an admin" in sent[0][1] and "Jane Smith" in sent[0][2]


def test_a_new_registration_has_no_admin(monkeypatch):
    monkeypatch.setattr(tenancy, "_may_send_code", lambda data, a: True)
    started = tenancy.start_registration(agency="sc.ed", name="Rebecca Valencia",
                                         title="Director",
                                         email="rvalencia@ed.sc.gov",
                                         phone="8035551234", attested=True)
    code = started.get("code")
    if not started.get("ok") or not code:
        pytest.skip(f"registration path needs mail: {started}")
    out = tenancy.verify_code("rvalencia@ed.sc.gov", code)
    assert out["ok"] and out["needs_admin"] is True
    assert not tenancy.is_agency_admin("sc.ed", "rvalencia@ed.sc.gov")
    assert not tenancy.add_member("sc.ed", "rvalencia@ed.sc.gov", "Bob Jones",
                                  "Analyst", "bjones@ed.sc.gov")["ok"]
