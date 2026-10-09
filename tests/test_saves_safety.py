"""Making sure no client's work is lost the way Rebecca Valencia's was.

Sep 29: 111 answers saved under no organization from a browser whose session
had gone, while her screen looked normal; nobody knew for three days.

1. Every change comes from a proven sign-in — no falling back to the email
   the browser claims.
2. (browser) A refused change is kept and sent after signing back in — see
   tools/check_session_ended.js.
3. A session stays alive while it is used, and its end is reported.
4. The team hears the same day: refused saves and alarms are in the daily
   technical report, which is sent because of them.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import server, techreport, tenancy, tenant
from app.authz import Actor, Role


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.setattr(techreport, "REFUSED", tmp_path / "refused.jsonl")
    monkeypatch.setattr(techreport, "HOLDING", tmp_path / "agencies" / tenant.ANONYMOUS)
    return tmp_path


# ------------------------------------------------- 1. proven sign-in for changes

def test_a_change_with_only_a_claimed_email_is_refused(store):
    nobody = Actor("u", "S", Role.OPERATOR, email="")
    out = server._proven_session_gate("POST", "/api/versions/answer", nobody,
                                      {"email": ["rvalencia@ed.sc.gov"]})
    assert out and out["session_ended"]
    rows = [json.loads(l) for l in techreport.REFUSED.read_text().splitlines()]
    assert rows[-1]["email"] == "rvalencia@ed.sc.gov" and rows[-1]["why"] == "no signed-in session"


def test_getting_in_and_reading_need_no_session(store):
    nobody = Actor("u", "S", Role.OPERATOR, email="")
    for door in ("/api/agency/signin", "/api/agency/verify", "/api/terms/accept",
                 "/api/bugs/report", "/api/session/end", "/api/chat"):
        assert server._proven_session_gate("POST", door, nobody, {}) is None, door
    assert server._proven_session_gate("GET", "/api/framework", nobody, {}) is None


def test_a_proven_change_goes_ahead(store):
    who = Actor("u", "S", Role.OPERATOR, email="rvalencia@ed.sc.gov")
    assert server._proven_session_gate("POST", "/api/versions/answer", who, {}) is None


# ------------------------------------------------- 3. sessions that stay alive

def test_using_a_session_renews_it(store, monkeypatch):
    token = tenancy.issue_session("rvalencia@ed.sc.gov")
    first = tenancy.session_expires(token)
    later = datetime.now(timezone.utc) + timedelta(days=20)
    monkeypatch.setattr(tenancy, "_now", lambda: later)
    assert tenancy.session_email(token) == "rvalencia@ed.sc.gov"   # still valid, renewed
    assert tenancy.session_expires(token) > first
    much_later = later + timedelta(days=25)                        # 45 days after issue
    monkeypatch.setattr(tenancy, "_now", lambda: much_later)
    assert tenancy.session_email(token) == "rvalencia@ed.sc.gov", "renewal carried it past day 30"


def test_an_unused_session_still_ends(store, monkeypatch):
    token = tenancy.issue_session("rvalencia@ed.sc.gov")
    monkeypatch.setattr(tenancy, "_now", lambda: datetime.now(timezone.utc) + timedelta(days=31))
    assert tenancy.session_email(token) == ""
    assert tenancy.session_expires(token) == ""


def test_the_end_of_a_session_is_reported(store):
    from app import impersonate
    token = tenancy.issue_session("rvalencia@ed.sc.gov")
    held = impersonate.set_current(None, token)
    try:
        out = server.api_session_renew(Actor("u", "S", Role.OPERATOR, email="rvalencia@ed.sc.gov"), {}, {})
    finally:
        impersonate.reset(held)
    assert out["ok"] and out["session_expires"] > datetime.now(timezone.utc).isoformat()


# ------------------------------------------------- 4. the team hears the same day

def test_refused_saves_are_grouped_by_person(store):
    for _ in range(3):
        techreport.note_refused_save("rvalencia@ed.sc.gov", "sc.ed", "/api/versions/answer",
                                     "no signed-in session")
    got = techreport.refused_since(datetime.now(timezone.utc) - timedelta(hours=1))
    assert got[0]["count"] == 3 and got[0]["email"] == "rvalencia@ed.sc.gov"


def test_a_non_empty_holding_area_is_an_alarm(store):
    techreport.HOLDING.mkdir(parents=True)
    (techreport.HOLDING / "framework_versions.json").write_text("{}")
    (techreport.HOLDING / "framework_versions.json.recovered-20261002").write_text("{}")
    alarms = techreport.integrity_alarms(datetime.now(timezone.utc) - timedelta(days=1))
    assert any("holding area has 1 file" in a for a in alarms), alarms


def test_a_day_with_only_a_refused_save_still_sends(store, monkeypatch):
    sent = []
    from app import mailer
    monkeypatch.setattr(mailer, "send", lambda *a, **k: sent.append(a) or {"sent": True})
    monkeypatch.setattr(techreport, "STATE", store / "state.json")
    monkeypatch.setattr(techreport, "new_bugs", lambda since: [])
    monkeypatch.setattr(techreport, "stalled", lambda now: [])
    monkeypatch.setattr(techreport, "refusals", lambda since: [])
    monkeypatch.setattr(techreport, "integrity_alarms", lambda since: [])
    monkeypatch.setattr(techreport, "stuck_signups", lambda now: [])
    techreport.note_refused_save("rvalencia@ed.sc.gov", "sc.ed", "/api/versions/answer",
                                 "no signed-in session")
    five_pm = datetime.now(timezone.utc).replace(hour=22, minute=0, second=0, microsecond=0)
    out = techreport.run_once(five_pm)
    assert out["ran"] and sent, out
    assert "1 refused save" in sent[0][1]
    assert "SAVES REFUSED" in sent[0][2]
