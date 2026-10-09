"""View as — the GAIUS team sees an organization as one of its people.

Only brett@, lokesh@ and dev@iiac.ai; only from their own proven session;
view only; nothing reaches the organization; and it can always be ended.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app import audit, impersonate, server, tenancy, tenant

TEAM = "lokesh@iiac.ai"
JANE = "jane.smith@des.sc.gov"


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    monkeypatch.setattr(audit, "DEFAULT_LOG", tmp_path / "master.jsonl")
    monkeypatch.delenv("GAIUS_ADMINS", raising=False)
    data = tenancy._load()
    data["agencies"]["iia.test"] = {"code": "iia.test", "status": "active",
        "members": [{"email": TEAM, "name": "Lokesh", "role": "admin"}]}
    data["agencies"]["sc.ed"] = {"code": "sc.ed", "status": "active",
        "identity": {"domain": "ed.sc.gov"},
        "members": [{"email": JANE, "name": "Jane Smith", "title": "Director",
                     "role": "admin"}]}
    tenancy._save(data)
    impersonate._ACTIVE.clear()
    yield tmp_path
    impersonate._ACTIVE.clear()


def _serve():
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd, f"http://127.0.0.1:{httpd.server_address[1]}"


def _call(base, path, token, body=None):
    req = urllib.request.Request(base + path, method="POST" if body is not None else "GET",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json",
                                          "X-GAIUS-Session": token})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


# ----------------------------------------------------------- the module

def test_only_the_three_can_start(world):
    for who in ("", JANE, "someone@iiac.ai"):
        assert impersonate.start("tok", who, JANE)["ok"] is False
    for who in ("brett@iiac.ai", "lokesh@iiac.ai", "dev@iiac.ai"):
        assert impersonate.start(f"tok-{who}", who, JANE)["ok"] is True


def test_the_session_must_still_be_the_admins(world):
    impersonate.start("tok", TEAM, JANE)
    assert impersonate.for_session("tok", JANE) is None        # somebody else's proof
    assert impersonate.for_session("tok", TEAM) is None        # and it was dropped
    impersonate.start("tok", TEAM, JANE)
    assert impersonate.for_session("tok", TEAM)["email"] == JANE


def test_only_reads_go_through_while_viewing(world):
    impersonate.start("tok", TEAM, JANE)
    held = impersonate.set_current(impersonate.for_session("tok", TEAM), "tok")
    try:
        assert impersonate.refused("GET", "/api/framework") is None
        blocked = impersonate.refused("POST", "/api/versions/answer")
        assert blocked["view_only"] and "view only" in blocked["error"]
        assert impersonate.refused("POST", "/api/admin/impersonate/stop") is None
        assert impersonate.refused("POST", "/api/session/end") is None
    finally:
        impersonate.reset(held)


def test_nothing_is_written_into_the_viewed_organizations_history(world):
    impersonate.start("tok", TEAM, JANE)
    held_t = tenant.set_current("sc.ed")
    held = impersonate.set_current(impersonate.for_session("tok", TEAM), "tok")
    try:
        audit.OrganisationLog().append(actor="x", role="operator", action="event.exported",
                                       target="Audit trail", outcome="allowed", detail={})
        assert audit.OrganisationLog().entries() == []        # their own trail: empty
    finally:
        impersonate.reset(held)
        tenant.reset(held_t)
    master = [json.loads(l) for l in audit.DEFAULT_LOG.read_text().splitlines()]
    last = master[-1]["detail"]
    assert last["while_viewing_as"] == JANE and last["viewed_by"] == TEAM


def test_start_and_end_are_logged_on_the_teams_side(world):
    impersonate.start("tok", TEAM, JANE)
    impersonate.for_session("tok", TEAM)
    out = impersonate.stop("tok")
    assert out["ended"] is True
    lines = [json.loads(l) for l in audit.DEFAULT_LOG.read_text().splitlines()]
    actions = {l["action"]: l["detail"] for l in lines}
    assert actions["impersonation_started"]["viewed_person"] == JANE
    assert actions["impersonation_ended"]["agency"] == "iia.test"
    assert actions["impersonation_ended"]["screens_opened"] == 1


def test_stopping_twice_is_harmless(world):
    assert impersonate.stop("nothing")["ended"] is False


# ----------------------------------------------------------- over HTTP

def test_end_to_end_view_only_and_exit(world):
    token = tenancy.issue_session(TEAM)
    httpd, base = _serve()
    try:
        status, out = _call(base, "/api/admin/impersonate/start", token, {"email": JANE})
        assert status == 200 and out["ok"], out
        status, st = _call(base, "/api/state", token)
        assert st["impersonating"]["name"] == "Jane Smith"
        assert st["impersonating"]["organization"]
        assert st["admin"] is False                     # the screen is theirs, not the team's
        status, out = _call(base, "/api/agency/people", token)
        assert out["organization"] and any(p["name"] == "Jane Smith" for p in out["people"])
        status, out = _call(base, "/api/agency/member", token,
                            {"name": "Bob Jones", "title": "Analyst", "email": "bjones@ed.sc.gov"})
        assert status == 403 and out["view_only"]
        assert tenancy.access_for("bjones@ed.sc.gov")["state"] == ""
        status, out = _call(base, "/api/admin/impersonate/stop", token, {})
        assert out["ended"] is True
        status, st = _call(base, "/api/state", token)
        assert st["impersonating"] is None and st["admin"] is True
    finally:
        httpd.shutdown()


def test_signing_out_ends_it(world):
    token = tenancy.issue_session(TEAM)
    httpd, base = _serve()
    try:
        _call(base, "/api/admin/impersonate/start", token, {"email": JANE})
        status, out = _call(base, "/api/session/end", token, {"session": token})
        assert status == 200
        assert impersonate.for_session(token, TEAM) is None
    finally:
        httpd.shutdown()


def test_a_non_admin_session_cannot_start_it(world, monkeypatch):
    from app import terms
    monkeypatch.setattr(terms, "STORE", world / "terms.json")
    # Past the Terms of Use, so it is the admin rule that refuses.
    assert terms.accept(email=JANE, name="Jane Smith", title="Director",
                        unit="SC Education", authority=True, scrolled=True)["ok"]
    token = tenancy.issue_session(JANE)
    httpd, base = _serve()
    try:
        status, out = _call(base, "/api/admin/impersonate/start", token, {"email": TEAM})
        assert out["ok"] is False and "GAIUS team" in out["error"]
    finally:
        httpd.shutdown()
