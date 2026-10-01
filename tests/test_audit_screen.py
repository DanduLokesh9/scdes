"""The Audit trail screen, and the privacy fix underneath it.

Before this, every organization wrote into one shared log and the audit
screen served its last sixty lines — names, actions and details — to
whoever asked. That was one agency's activity in front of another. These
pin the fix: each organization writes its own trail, the shared file keeps
a back-end copy of everything so no record is lost, and no screen reads the
shared file on anybody's behalf.

They also pin the screen's promises: nothing is edited or removed, a
correction and a note are entries beside the one they concern, producing
the record writes itself down and leaves nothing out, and the trail is not
behind the subscription.
"""

from __future__ import annotations

import base64

import pytest

from app import audit, authz, server, tenant, trail
from app.authz import Actor, Role

USER = Actor("u", "Pat Lee", Role.OPERATOR, title="Clerk")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "DEFAULT_LOG", tmp_path / "shared" / "log.jsonl")
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    monkeypatch.setattr(authz, "_default_log", None)
    monkeypatch.setattr(tenant, "corpus_owner", lambda: "sc.des")
    monkeypatch.setattr(server, "_framework_answers", lambda: {})
    yield


def _as(code: str):
    return tenant.set_current(code)


def _write(code: str, what: str) -> None:
    token = _as(code)
    try:
        authz.default_log().append(actor="x", role="operator", action=what,
                                   target="Projects", outcome="allowed",
                                   detail={"ref": "P1", "actor_name": code})
    finally:
        tenant.reset(token)


def test_each_organisation_writes_its_own_trail() -> None:
    _write("town.a", "event.record_created")
    _write("town.b", "event.field_changed")
    token = _as("town.a")
    try:
        mine = [r["action"] for r in trail.rows()]
    finally:
        tenant.reset(token)
    assert mine == ["event.record_created"]


def test_the_corpus_owner_does_not_read_everyone_elses_history() -> None:
    _write("town.b", "event.field_changed")
    token = _as("sc.des")
    try:
        assert trail.rows() == []
    finally:
        tenant.reset(token)


def test_the_back_end_copy_keeps_everything_and_says_whose() -> None:
    _write("town.a", "event.record_created")
    _write("town.b", "event.field_changed")
    shared = audit.JsonlAuditLog(audit.DEFAULT_LOG)
    organisations = [e.detail.get("organisation") for e in shared.entries()]
    assert organisations == ["town.a", "town.b"]
    assert shared.verify()[0]


def test_the_audit_screen_shows_only_this_organisations_entries() -> None:
    _write("town.a", "event.record_created")
    _write("town.b", "event.field_changed")
    token = _as("town.b")
    try:
        found = server.api_audit(USER, {}, {})
    finally:
        tenant.reset(token)
    assert [e["action"] for e in found["entries"]] == ["event.field_changed"]
    assert "town.a" not in str(found)


def test_a_correction_is_an_entry_beside_the_one_it_corrects() -> None:
    _write("town.a", "event.record_created")
    token = _as("town.a")
    try:
        first = trail.rows()[0]
        assert trail.correct(actor=USER, of=first["seq"],
                             wrong="The date was wrong")["ok"]
        after = trail.rows()
        assert after[0] == first
        assert after[1]["action"] == "event.correction_recorded"
        assert after[1]["detail"]["of"] == first["seq"]
        assert trail.counters(after)["corrections"] == 1
    finally:
        tenant.reset(token)


def test_a_note_never_changes_the_entry() -> None:
    _write("town.a", "event.record_created")
    token = _as("town.a")
    try:
        first = trail.rows()[0]
        assert trail.add_note(actor=USER, of=first["seq"], text="Context",
                              kind=trail.STILL_NEEDED)["ok"]
        assert trail.rows()[0] == first
        assert not trail.add_note(actor=USER, of=first["seq"], text=" ")["ok"]
    finally:
        tenant.reset(token)


def test_something_recorded_from_elsewhere_says_so_and_keeps_both_dates() -> None:
    token = _as("town.a")
    try:
        assert not trail.record_elsewhere(actor=USER, what=" ")["ok"]
        trail.record_elsewhere(actor=USER, what="The board voted to adopt it",
                               happened="2026-01-05",
                               how_known="I was there")
        row = trail.rows()[-1]
        shown = trail.shown(row)
        assert shown["from_elsewhere"] is True
        assert shown["when"].startswith("happened 2026-01-05")
        assert trail.counters()["after_the_fact"] == 1
    finally:
        tenant.reset(token)


def test_producing_the_record_leaves_nothing_out_and_writes_itself_down(
        ) -> None:
    _write("town.a", "event.record_created")
    _write("town.a", "event.field_changed")
    token = _as("town.a")
    try:
        out = server.api_trail_produce(USER, {"filter": {}}, {})
        assert out["ok"] and out["count"] == 2
        html = base64.b64decode(out["html"]).decode()
        csv = base64.b64decode(out["csv"]).decode()
        assert "Seal check at the moment this was produced" in html
        assert csv.count("\n") >= 4
        assert trail.rows()[-1]["action"] == "event.exported"
    finally:
        tenant.reset(token)


def test_the_seal_check_still_holds_across_notes_and_corrections() -> None:
    _write("town.a", "event.record_created")
    token = _as("town.a")
    try:
        first = trail.rows()[0]
        trail.add_note(actor=USER, of=first["seq"], text="x")
        seal = trail.seal_check()
        assert seal["checked"] == seal["matched"] == 2
    finally:
        tenant.reset(token)


def test_an_unresolved_browser_gets_no_trail_of_its_own() -> None:
    token = _as(tenant.ANONYMOUS)
    try:
        authz.default_log().append(actor="?", role="", action="event.x",
                                   target="t", outcome="allowed")
        assert trail.rows() == []
    finally:
        tenant.reset(token)
    # And what it caused is still kept.
    assert audit.JsonlAuditLog(audit.DEFAULT_LOG).entries()


def test_the_trail_is_not_behind_the_subscription() -> None:
    assert server.ROUTES[("GET", "/api/audit")] is server.api_audit
    for path in ("/api/trail/elsewhere", "/api/trail/note",
                 "/api/trail/correct", "/api/trail/produce"):
        assert ("POST", path) in server.ROUTES
