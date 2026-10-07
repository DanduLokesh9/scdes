"""The development team's daily technical report.

5 PM Eastern, once a day, only when somebody reported a bug; what it says;
and that it survives restarts and a server that was down at five.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from app import bugs, mailer, spine, techreport, tenancy


def _utc(y, m, d, h, mi=0):
    return datetime(y, m, d, h, mi, tzinfo=timezone.utc)


# Summer: 5 PM EDT is 21:00 UTC. Winter: 5 PM EST is 22:00 UTC.
SUMMER_5PM = _utc(2026, 9, 25, 21, 0)
WINTER_5PM = _utc(2026, 12, 3, 22, 0)


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(bugs, "STORE", tmp_path / "bugs.jsonl")
    monkeypatch.setattr(techreport, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(techreport, "SERVER_ERRORS", tmp_path / "errors.jsonl")
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.setattr(techreport, "stalled", lambda now: [])
    monkeypatch.setattr(techreport, "refusals", lambda since: [])
    monkeypatch.setattr(techreport, "REFUSED", tmp_path / "refused.jsonl")
    monkeypatch.setattr(techreport, "HOLDING", tmp_path / "holding")
    monkeypatch.setattr(techreport, "integrity_alarms", lambda since: [])
    monkeypatch.setattr(techreport, "frameworks_reached", lambda already=None: [])
    for name in ("GAIUS_REPORT_TO", "GAIUS_REPORT_HOUR", "GAIUS_REPORT_OFF"):
        monkeypatch.delenv(name, raising=False)
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None:
                        sent.append({"to": to, "subject": subject, "text": text,
                                     "html": html}) or {"sent": True})
    return sent


def _bug(at, **extra):
    row = {"id": extra.pop("id", f"B{abs(hash(at)) % 10**6:06d}"),
           "at": at.isoformat(timespec="seconds"), "status": "new",
           "expected": "It saves", "happened": "Spinner forever",
           "reporter": "pat@city.gov", "name": "Pat Doe", "agency": "sc.x",
           "view": "Framework Builder", "url": "/#builder",
           "browser": "Edge", "screen": "1920x1080",
           "events": [{"kind": "error", "text": "TypeError: x is undefined"},
                      {"kind": "network", "method": "POST",
                       "text": "/api/versions/answer", "status": "500"},
                      {"kind": "network", "method": "GET",
                       "text": "/api/state", "status": "200"}],
           **extra}
    with bugs.STORE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return row


# ------------------------------------------------------------------ schedule

def test_recipients_are_the_development_team():
    assert techreport.recipients() == ["lokesh@iiac.ai", "dev@iiac.ai"]


def test_eastern_follows_daylight_saving():
    assert techreport.eastern(SUMMER_5PM).hour == 17
    assert techreport.eastern(WINTER_5PM).hour == 17


def test_nothing_before_five_eastern(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=3))
    assert techreport.run_once(SUMMER_5PM - timedelta(minutes=1)) == {"ran": False}
    assert sandbox == []


def test_sends_at_five_to_both_when_a_bug_was_reported(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=3))
    out = techreport.run_once(SUMMER_5PM)
    assert out["bugs"] == 1
    assert sorted(m["to"] for m in sandbox) == ["dev@iiac.ai", "lokesh@iiac.ai"]
    assert "1 new bug report" in sandbox[0]["subject"]


def test_quiet_day_sends_nothing_but_moves_on(sandbox):
    out = techreport.run_once(SUMMER_5PM)
    assert out == {"ran": True, "day": "2026-09-25", "bugs": 0}
    assert sandbox == []
    state = json.loads(techreport.STATE.read_text())
    assert state["last_day"] == "2026-09-25"


def test_once_a_day_even_across_restarts(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1))
    techreport.run_once(SUMMER_5PM)
    techreport.run_once(SUMMER_5PM + timedelta(minutes=5))
    techreport.run_once(SUMMER_5PM + timedelta(hours=2))
    assert len(sandbox) == 2                       # one email, two recipients


def test_each_bug_is_reported_once(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1), id="OLD")
    techreport.run_once(SUMMER_5PM)
    sandbox.clear()
    next_day = SUMMER_5PM + timedelta(days=1)
    _bug(next_day - timedelta(hours=2), id="NEW")
    techreport.run_once(next_day)
    assert "NEW" in sandbox[0]["text"] and "OLD" not in sandbox[0]["text"]


def test_catches_up_when_the_server_was_down_at_five(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1))
    late = SUMMER_5PM + timedelta(hours=4)          # 9 PM, back up
    assert techreport.run_once(late)["bugs"] == 1
    assert sandbox


def test_can_be_switched_off(sandbox, monkeypatch):
    monkeypatch.setenv("GAIUS_REPORT_OFF", "1")
    _bug(SUMMER_5PM - timedelta(hours=1))
    assert techreport.run_once(SUMMER_5PM) == {"ran": False}


def test_hour_and_recipients_are_settable(sandbox, monkeypatch):
    monkeypatch.setenv("GAIUS_REPORT_HOUR", "9")
    monkeypatch.setenv("GAIUS_REPORT_TO", "a@iiac.ai, b@iiac.ai")
    _bug(SUMMER_5PM - timedelta(hours=10))
    techreport.run_once(_utc(2026, 9, 25, 13, 0))   # 9 AM EDT
    assert sorted(m["to"] for m in sandbox) == ["a@iiac.ai", "b@iiac.ai"]


def test_a_failed_send_is_recorded(sandbox, monkeypatch):
    monkeypatch.setattr(mailer, "send", lambda *a, **k: {"sent": False,
                                                          "reason": "no smtp"})
    _bug(SUMMER_5PM - timedelta(hours=1))
    techreport.run_once(SUMMER_5PM)
    last = json.loads(techreport.STATE.read_text())["history"][-1]
    assert last["sent_to"] == [] and "no smtp" in last["failed"][0]


# ------------------------------------------------------------------ content

def test_report_carries_the_evidence(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1))
    report = techreport.build(SUMMER_5PM - timedelta(days=1), SUMMER_5PM)
    body = techreport.text(report)
    assert "Pat Doe <pat@city.gov>" in body
    assert "Framework Builder" in body
    assert "TypeError: x is undefined" in body
    assert "POST /api/versions/answer → 500" in body
    assert "/api/state" not in body                 # a call that worked is not evidence
    assert "Spinner forever" in body


def test_test_accounts_are_marked_and_left_out_of_screen_counts(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1), agency="gaius.harness", view="Integrity")
    report = techreport.build(SUMMER_5PM - timedelta(days=1), SUMMER_5PM)
    assert report["bugs"][0]["test"] is True
    assert report["screens"] == []
    assert "TEST ACCOUNT" in techreport.text(report)


def test_html_is_escaped(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1), happened="<script>alert(1)</script>")
    html = techreport.html_body(techreport.build(SUMMER_5PM - timedelta(days=1),
                                                 SUMMER_5PM))
    assert "<script>" not in html and "&lt;script&gt;" in html


def test_server_errors_are_kept_scrubbed_and_grouped(sandbox):
    for n in range(3):
        try:
            raise ValueError(f"bad row 12345678{n} for someone@agency.gov")
        except ValueError as exc:
            techreport.note_server_error("POST /api/versions/answer", exc, "sc.x")
    groups = techreport.server_errors_since(datetime.now(timezone.utc) - timedelta(hours=1))
    assert len(groups) == 1 and groups[0]["count"] == 3
    raw = techreport.SERVER_ERRORS.read_text()
    assert "someone@agency.gov" not in raw and "123456780" not in raw
    assert "test_techreport.py" in groups[0]["at_line"]


def test_note_server_error_never_raises(sandbox, monkeypatch):
    monkeypatch.setattr(techreport, "SERVER_ERRORS", techreport.STATE.parent / "no" / "\0bad")
    techreport.note_server_error("GET /x", RuntimeError("boom"))


def test_stuck_signups_are_named(sandbox):
    old = (SUMMER_5PM - timedelta(days=3)).isoformat(timespec="seconds")
    tenancy.STORE.write_text(json.dumps({"agencies": {}, "pending": {
        "ann@nm.gov": {"status": "pending_code", "state": "nm.x", "name": "Ann",
                       "created_at": old},
        "t@x.test": {"status": "pending_code", "state": "nm.demo.test",
                     "name": "T", "created_at": old},
        "new@nm.gov": {"status": "pending_code", "state": "nm.x", "name": "Fresh",
                       "created_at": SUMMER_5PM.isoformat()}}}))
    stuck = techreport.stuck_signups(SUMMER_5PM)
    assert [s["name"] for s in stuck] == ["Ann"]
    assert stuck[0]["days"] == 3.0


def test_wording_has_no_banned_words(sandbox):
    _bug(SUMMER_5PM - timedelta(hours=1))
    report = techreport.build(SUMMER_5PM - timedelta(days=1), SUMMER_5PM)
    for body in (techreport.text(report), techreport.html_body(report)):
        assert not spine.banned_in(body)
