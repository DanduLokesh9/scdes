"""The Integrity pieces that were specified and not yet built.

Four findings (4.7 accessibility re-check, 4.8 a change unanswered, 4.9 the
level not looked at after an incident, and 4.13 gated on the Registry's own
general-purpose answer); editing while a record is still being written, and
never after (§13); reopening a closed incident rather than editing it; the
Stop it now control, which reads no title; attachments that are stored and
never read; and the public page's remaining fields.
"""

from __future__ import annotations

import pytest

from app import attachments, checks, projects, public_report, server, spine
from app.authz import Actor, Role

AUTHOR = Actor("a.one", "Author", Role.OPERATOR)
OTHER = Actor("b.two", "Other", Role.OPERATOR)
DECIDER = Actor("d.one", "Decider", Role.COUNCIL)


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(checks, "_file", lambda: tmp_path / "checks.json")
    monkeypatch.setattr(checks, "_log", lambda *a, **k: None)
    monkeypatch.setattr(projects, "_file", lambda: tmp_path / "projects.json")
    monkeypatch.setattr(projects, "_record", lambda *a, **k: None)
    monkeypatch.setattr(attachments, "_folder", lambda: tmp_path / "att")
    monkeypatch.setattr(public_report, "LINKS_FILE", tmp_path / "links.json")
    monkeypatch.setattr(public_report, "_log", lambda *a, **k: None)
    public_report._seen_address.clear()
    public_report._seen_link.clear()
    yield


def _check(project="P1", **over):
    out = checks.record_check(project=project, actor=AUTHOR,
                              limits="Only the happy path", **over)
    assert out["ok"], out
    return out["check"]


# ------------------------------------------------------------ 4.7

def test_a_public_tool_with_no_recent_accessibility_look_is_named() -> None:
    p = {"P1": {"ref": "P1", "tool": {"public_facing": "yes"}}}
    access = {"days": 366, "on_change": False, "words": "once a year"}
    got = checks.findings([], projects=p, access=access, today="2026-09-23")
    assert [f["id"] for f in got] == ["finding.accessibility_recheck_missing"]
    assert "You said accessibility gets checked once a year" in got[0]["says"]
    _check(accessibility=checks.ACCESS_ANSWERS[0], complete=True, at="2026-06-01")
    assert not checks.findings(projects=p, access=access, today="2026-09-23")


def test_a_tool_the_public_does_not_use_is_not_asked_about() -> None:
    p = {"P1": {"ref": "P1", "tool": {"public_facing": "no"}}}
    got = checks.findings([], projects=p, access={"days": 366, "words": "x"})
    assert not got


# ------------------------------------------------------------ 4.8

def test_a_change_with_nothing_since_is_named_only_where_they_said_so() -> None:
    p = {"P1": {"ref": "P1", "versions": [{"ref": "V-1", "opened": "2026-09-01"}]}}
    got = checks.findings([], projects=p,
                          change_words="treat it as a new tool and review it like one")
    assert got and got[0]["id"] == "finding.change_unanswered"
    assert "A change was recorded on 2026-09-01" in got[0]["says"]
    assert not checks.findings([], projects=p, change_words="")
    _check(complete=True, at="2026-09-10")
    assert not checks.findings(projects=p, change_words="whenever")


def test_change_words_come_from_their_answers() -> None:
    assert checks.framework_inputs({"proc.added_ai": "as_new"})["change_words"] \
        .startswith("treat it as a new tool")
    assert checks.framework_inputs({"risk.revisit": ["vendor_change"]})["change_words"] \
        == "whenever the vendor changes the tool"
    assert checks.framework_inputs({"proc.added_ai": "record"})["change_words"] == ""


# ------------------------------------------------------------ 4.9

def test_the_level_not_looked_at_after_an_incident_is_named() -> None:
    checks.report_incident(actor=AUTHOR, project="P1", what_happened="x",
                           at="2026-09-10")
    p = {"P1": {"ref": "P1", "level_set_at": "2026-08-01T00:00:00+00:00"}}
    got = checks.findings(projects=p, level_after_incident=True)
    assert [f["id"] for f in got if f["id"].startswith("finding.level")] == \
        ["finding.level_unreviewed_after_incident"]
    p["P1"]["level_set_at"] = "2026-09-12T00:00:00+00:00"
    assert not [f for f in checks.findings(projects=p, level_after_incident=True)
                if f["id"].startswith("finding.level")]


def test_setting_a_level_records_when() -> None:
    ref = projects.start("Permits", AUTHOR)["project"]["ref"]
    projects.set_level(ref, "Low", DECIDER, levels=["Low", "High"])
    assert projects.one(ref)["level_set_at"]


# ------------------------------------------------------------ 4.13

def test_test_on_never_needs_the_registry_to_say_general_purpose() -> None:
    _check(holdings=["DH-1"], complete=True)
    never = {"DH-1": "student records"}
    assert not checks.findings(never_categories=never,
                               general_purpose_projects=set())
    got = checks.findings(never_categories=never, general_purpose_projects={"P1"},
                          holding_names={"DH-1": "Enrollment file"})
    said = [f["says"] for f in got if f["id"] == "finding.test_on_never"]
    assert said == ["You said never for student records. This check was run on "
                    "real material from Enrollment file."]


# ------------------------------------------------------------ 13 · editing

def test_the_author_may_change_a_check_still_being_written() -> None:
    row = _check()
    assert checks.edit_entry(row["ref"], {"found": "It was fine"}, actor=AUTHOR)["ok"]
    assert checks.entry(row["ref"])["found"] == "It was fine"


def test_somebody_else_may_not_but_whoever_decides_may() -> None:
    row = _check()
    refused = checks.edit_entry(row["ref"], {"found": "x"}, actor=OTHER)
    assert refused["ok"] is False and refused["error"] == checks.NOT_YOURS_TO_EDIT
    assert checks.edit_entry(row["ref"], {"found": "y"}, actor=OTHER, decider=True)["ok"]


def test_a_complete_check_is_not_editable_by_anyone() -> None:
    row = _check(complete=True)
    out = checks.edit_entry(row["ref"], {"found": "x"}, actor=DECIDER, decider=True)
    assert out["ok"] is False and out["error"] == checks.NOT_EDITABLE_COMPLETE


def test_the_fixed_fields_never_move() -> None:
    row = _check()
    checks.edit_entry(row["ref"], {"author": "someone", "complete": True,
                                   "ref": "CK-XXXX"}, actor=AUTHOR)
    held = checks.entry(row["ref"])
    assert held["author"] == "a.one" and held["complete"] is False


def test_a_correction_names_the_one_it_corrects_and_both_stay() -> None:
    first = _check(complete=True)
    second = _check(corrects=first["ref"], complete=True)
    assert second["corrects"] == first["ref"]
    assert len(checks.checks()) == 2
    assert _check(corrects="CK-NOPE")["corrects"] == ""


# ------------------------------------------------------------ reopening

def test_a_closed_incident_reopens_rather_than_being_edited() -> None:
    made = checks.report_incident(actor=AUTHOR, what_happened="x",
                                  closed=checks.INCIDENT_CLOSED,
                                  closed_at="2026-09-01", closed_by="Director")
    ref = made["incident"]["ref"]
    assert checks.edit_entry(ref, {"cause": "y"}, actor=AUTHOR)["error"] == \
        checks.NOT_EDITABLE_CLOSED
    out = checks.reopen_incident(ref, actor=DECIDER, why="It happened again")
    assert out["ok"]
    row = checks.entry(ref)
    assert row["closed"] == checks.INCIDENT_OPEN
    assert row["reopened"][0]["was_closed_by"] == "Director"
    assert checks.reopen_incident(ref, actor=DECIDER)["ok"] is False


# ------------------------------------------------------------ stop it now

def test_stop_it_now_takes_a_named_role_and_pauses_the_project() -> None:
    ref = projects.start("Permits", AUTHOR)["project"]["ref"]
    inc = checks.report_incident(actor=AUTHOR, project=ref,
                                 what_happened="Wrong fees")["incident"]["ref"]
    refused = checks.stop_now(inc, role="Somebody", actor=AUTHOR,
                              stoppers=["Deputy Director"])
    assert refused["ok"] is False
    out = checks.stop_now(inc, role="Deputy Director", actor=AUTHOR,
                          stoppers=["Deputy Director"])
    assert out["ok"] and out["project_paused"]
    assert projects.one(ref)["state"] == spine.PAUSED
    assert projects.one(ref)["paused_by"] == "Deputy Director"
    assert checks.entry(inc)["stopped"] == checks.STOPPED_YES


# ------------------------------------------------------------ attachments

def test_an_attachment_is_stored_and_handed_back_unread() -> None:
    kept = attachments.store(b"a,b\n1,2\n", "../../etc/passwd", by="x")
    assert kept["ok"] and kept["name"] == ".._.._etc_passwd"
    back = attachments.fetch(kept["id"])
    import base64
    assert base64.b64decode(back["data"]) == b"a,b\n1,2\n"
    assert attachments.known([kept["id"], "AT-0000000000000000"]) == [kept["id"]]
    assert attachments.fetch("../index.json")["ok"] is False


def test_a_file_over_the_limit_is_refused() -> None:
    out = attachments.store(b"x" * (attachments.MAX_BYTES + 1), "big.bin")
    assert out["ok"] is False and out["error"] == attachments.TOO_LARGE


def test_nobody_outside_an_organisation_can_attach(monkeypatch) -> None:
    from app import tenant
    monkeypatch.setattr(server, "_verified_member", lambda actor: False)
    out = server.api_attachment_upload(AUTHOR, {"name": "a", "data": "YQ=="}, {})
    assert out["ok"] is False


# ------------------------------------------------------------ the public page

@pytest.fixture
def live_agency(monkeypatch):
    from app import tenancy
    monkeypatch.setattr(tenancy, "agency_state",
                        lambda code: {"active": code == "gc.county"})
    monkeypatch.setattr(tenancy, "_agency_names",
                        lambda code: {"agency_label": "Greenville County"})
    answers = {"bad.tell": ["board"], "bad.lookback": "yes",
               "bad.lookback_far": "90"}
    monkeypatch.setattr(public_report, "_inputs",
                        lambda agency: checks.framework_inputs(answers))
    return "gc.county"


def _multipart(fields: dict[str, str], files: list[tuple[str, bytes]]):
    boundary = "----gaiusboundary"
    out = b""
    for k, v in fields.items():
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{k}\""
                f"\r\n\r\n{v}\r\n").encode()
    for name, data in files:
        out += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; "
                f"filename=\"{name}\"\r\nContent-Type: text/plain\r\n\r\n").encode()
        out += data + b"\r\n"
    out += f"--{boundary}--\r\n".encode()
    return out, f"multipart/form-data; boundary={boundary}"


def test_the_public_page_carries_the_remaining_fields(live_agency) -> None:
    page = public_report.form(public_report.make_link(live_agency, AUTHOR))
    for words in ("Who has been told?", "Has anyone gone back over earlier work?",
                  "What caused it?", "What was done about it?", "Anything attached?",
                  'enctype="multipart/form-data"'):
        assert words in page, words
    assert "Greenville County said each of these must be told" in page
    assert "you said" not in page.lower()


def test_a_public_report_keeps_its_fields_and_files(live_agency) -> None:
    token = public_report.make_link(live_agency, AUTHOR)
    body, ctype = _multipart({"what_happened": "Wrong fee",
                              "told": "Your board or elected officials",
                              "told_on_0": "2026-09-20", "lookback": "their_scope",
                              "cause": "Not known yet"}, [("shot.txt", b"hello")])
    status, page = public_report.submit(token, body, "203.0.113.9", ctype)
    assert status == 200, page
    row = checks.all_entries()[0]
    assert row["cause"] == "Not known yet"
    assert row["lookback"] == checks.LOOKBACK_THEIR_SCOPE
    assert len(row["attachments"]) == 1
    assert row["told"] == {"Your board or elected officials": "2026-09-20"}


def test_the_public_page_takes_at_most_two_files(live_agency) -> None:
    token = public_report.make_link(live_agency, AUTHOR)
    body, ctype = _multipart({"what_happened": "x"},
                             [("a.txt", b"1"), ("b.txt", b"2"), ("c.txt", b"3")])
    status, page = public_report.submit(token, body, "203.0.113.9", ctype)
    assert status == 400 and "2 files" in page
    assert not checks.all_entries()


def test_the_routes_are_registered() -> None:
    for method, path in (("POST", "/api/entries/edit"),
                         ("POST", "/api/incidents/reopen"),
                         ("POST", "/api/incidents/stop"),
                         ("POST", "/api/attachments"),
                         ("GET", "/api/attachments/get")):
        assert (method, path) in server.ROUTES
