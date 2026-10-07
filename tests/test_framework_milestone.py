"""A framework passing 70% is reported to the team, like a bug report.

"Whoever completed 70% of their framework in their agency, send a report to
the mailbox, same as the bug report." It rides in the 5 PM technical report,
to the same people; the email goes on a day an organization first passes the
mark even with no bugs; and each organization is reported once.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import mailer, techreport, tenancy, usage


@pytest.fixture
def world(tmp_path, monkeypatch):
    monkeypatch.setattr(techreport, "STATE", tmp_path / "state.json")
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    for name in ("new_bugs", "refused_since", "integrity_alarms", "server_errors_since",
                 "refusals", "stuck_signups", "stalled"):
        monkeypatch.setattr(techreport, name, lambda *a, **k: [])
    monkeypatch.setattr(techreport, "backlog", lambda now: {"open": 0, "oldest_days": 0})
    monkeypatch.delenv("GAIUS_REPORT_OFF", raising=False)
    monkeypatch.delenv("GAIUS_REPORT_HOUR", raising=False)
    monkeypatch.delenv("GAIUS_MILESTONE_PERCENT", raising=False)
    data = tenancy._load()
    for code, name in (("sc.ed", "Rebecca Valencia"), ("sc.des", "Brett Butz"),
                       ("co.env", "Chad Whitlock"), ("iia.test", "Dev")):
        data["agencies"][code] = {"code": code, "status": "active",
                                  "members": [{"email": f"{code}@x.gov", "name": name, "role": "admin"}]}
    tenancy._save(data)
    progress = {"sc.ed": 98, "sc.des": 81, "co.env": 12, "iia.test": 90}
    monkeypatch.setattr(usage, "progress_of", lambda code: {
        "percent": progress[code], "answered": progress[code], "asked": 100, "adopted": False})
    monkeypatch.setattr(techreport, "_steps_left", lambda code: ["Step 11 · Why this framework exists: 2 open"])
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None, attachments=None:
                        sent.append((to, subject, text, html, attachments or [])) or {"sent": True})
    from app import framework_report
    monkeypatch.setattr(framework_report, "_answers", lambda org: {
        "org.kind": {"value": "state"}, "org.size": {"value": "500-2000"}})
    from app import audit
    monkeypatch.setattr(audit, "DEFAULT_LOG", tmp_path / "master.jsonl")
    return sent


FIVE_PM = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)      # 5 PM EDT


def test_the_ones_past_70_are_listed_test_organizations_left_out(world):
    got = techreport.frameworks_reached()
    assert [r["agency"] for r in got] == ["sc.ed", "sc.des"]
    assert got[0]["people"] == ["Rebecca Valencia"] and got[0]["left"]


def test_the_day_it_happens_the_email_goes_even_with_no_bugs(world):
    out = techreport.run_once(FIVE_PM)
    assert out["ran"] and world, out
    to = sorted({m[0] for m in world})
    assert to == ["dev@iiac.ai", "lokesh@iiac.ai"]
    subject, text, html = world[0][1], world[0][2], world[0][3]
    assert "2 frameworks past 70%" in subject
    assert "REACHED 70% OF THE FRAMEWORK" in text and "Rebecca Valencia" in text and "98%" in text
    assert "Step 11" in text
    assert "Reached 70% of the framework" in html


def test_each_organization_is_reported_once(world):
    techreport.run_once(FIVE_PM)
    world.clear()
    techreport.run_once(FIVE_PM + timedelta(days=1))
    assert world == [], "nothing new the next day, so nothing is sent"


def test_a_failed_send_reports_it_again_tomorrow(world, monkeypatch):
    monkeypatch.setattr(mailer, "send", lambda *a, **k: {"sent": False, "reason": "smtp down"})
    techreport.run_once(FIVE_PM)
    assert techreport.frameworks_reached(set((techreport._state().get("milestones") or {}))) != []


def test_each_organizations_answers_are_attached_as_a_pdf(world):
    import re
    techreport.run_once(FIVE_PM)
    files = world[0][4]
    names = sorted(f[0] for f in files)
    assert names == ["Framework-answers-sc-des-2026-10-02.pdf", "Framework-answers-sc-ed-2026-10-02.pdf"] \
        or len(names) == 2, names
    name, pdf, mime = files[0]
    assert mime == "application/pdf" and pdf.startswith(b"%PDF-1.4") and pdf.rstrip().endswith(b"%%EOF")
    text = " ".join(s.decode("cp1252") for s in re.findall(rb"\((.*?)\) Tj", pdf))
    assert "1.1  What kind of organization are you?" in text
    assert "State agency or department" in text             # the label they clicked, not "state"
    assert "Not answered yet" in text
    assert "Confidential" in text


def test_the_email_says_how_to_read_them_inside_gaius(world):
    techreport.run_once(FIVE_PM)
    assert "View as" in world[0][2] and "Admin → Organizations" in world[0][2]


def test_answers_that_left_by_email_are_logged(world):
    import json
    from app import audit
    techreport.run_once(FIVE_PM)
    rows = [json.loads(l) for l in audit.DEFAULT_LOG.read_text().splitlines()]
    sent = [r for r in rows if r["action"] == "framework_answers_emailed"]
    assert sorted(r["detail"]["about"] for r in sent) == ["sc.des", "sc.ed"]
    assert sent[0]["detail"]["to"] == ["lokesh@iiac.ai", "dev@iiac.ai"]


def test_the_mark_can_be_set(world, monkeypatch):
    monkeypatch.setenv("GAIUS_MILESTONE_PERCENT", "90")
    assert [r["agency"] for r in techreport.frameworks_reached()] == ["sc.ed"]
