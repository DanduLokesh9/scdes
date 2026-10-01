"""Take a copy, wipe, put it back.

The client wanted to erase his tenant so he could demo from zero. A one-way
wipe does that once; doing it repeatedly means losing a fortnight of answers
every time. So: snapshot, wipe, demo, restore.

The properties that matter are all about what a snapshot must *not* be able to
do — reach another agency, rewind the audit log, or restore an agency to a
state it was never in.
"""

from __future__ import annotations

import json

import pytest

from app import reset as reset_mod, snapshot, tenant, versions
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every agency's directory under a temporary root, so the real one is
    never touched and one test cannot see another's snapshots."""
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    monkeypatch.setattr(versions, "VERSIONS_FILE",
                        tmp_path / "corpus" / "config"
                        / "framework_versions.json")
    yield


def as_agency(code: str):
    class Bound:
        def __enter__(self):
            self.token = tenant.set_current(code)
            return self
        def __exit__(self, *_):
            tenant.reset(self.token)
    return Bound()


def _answer(key: str, value: str) -> None:
    versions.answer(key, value, WHO)


# ------------------------------------------------------------- the round trip

def test_a_snapshot_survives_a_wipe() -> None:
    """The whole point. Answer, snapshot, clear, restore, and the answers are
    back exactly as they were."""
    with as_agency("iia.test"):
        _answer("org.kind", "district")
        _answer("who.tiebreak", "The District Manager")

        taken = snapshot.take(WHO, label="Before the demo")
        assert taken["ok"], taken

        # Wipe it the way Start Over does.
        for target in reset_mod._targets():
            if target.path.is_file():
                target.path.unlink()
        assert versions.working() == {}

        out = snapshot.restore(taken["id"], WHO)
        assert out["ok"], out
        back = versions.working()
        assert back["org.kind"]["value"] == "district"
        assert back["who.tiebreak"]["value"] == "The District Manager"


def test_restoring_replaces_rather_than_merges() -> None:
    """A half-restored agency — this snapshot's answers beside today's — is a
    state nobody chose and nobody could reason about."""
    with as_agency("iia.test"):
        _answer("org.kind", "district")
        taken = snapshot.take(WHO, label="Just the one answer")

        _answer("org.size", "u25")
        assert len(versions.working()) == 2

        snapshot.restore(taken["id"], WHO)
        held = versions.working()
        assert "org.kind" in held
        assert "org.size" not in held, "an answer from after the snapshot"


def test_a_snapshot_is_named_and_dated_so_it_can_be_told_apart() -> None:
    with as_agency("iia.test"):
        _answer("org.kind", "city")
        taken = snapshot.take(WHO, label="Before the board demo")
        found = snapshot.listing()["snapshots"]
        assert len(found) == 1
        assert found[0]["label"] == "Before the board demo"
        assert found[0]["taken_by"] == "Dana Reed"
        assert found[0]["taken_at"]
        assert "Framework answers and version history" in found[0]["holds"]
        assert found[0]["id"] == taken["id"]


def test_one_can_be_deleted_without_touching_the_others() -> None:
    with as_agency("iia.test"):
        _answer("org.kind", "city")
        first = snapshot.take(WHO, label="One")
        second = snapshot.take(WHO, label="Two")
        snapshot.forget(first["id"], WHO)
        left = [s["id"] for s in snapshot.listing()["snapshots"]]
        assert left == [second["id"]]


# ----------------------------------------------------- what it must not do

def test_a_snapshot_cannot_reach_another_agency() -> None:
    """Taken from and restored into the caller's own container. The paths come
    from `reset._targets()`, which is already scoped — one definition of
    "this agency's work", so snapshot and reset cannot drift apart."""
    with as_agency("iia.test"):
        _answer("org.kind", "district")
        mine = snapshot.take(WHO, label="Mine")

    with as_agency("sc.ed"):
        assert snapshot.listing()["snapshots"] == [], "saw another's snapshot"
        # And cannot restore one by guessing its name.
        out = snapshot.restore(mine["id"], WHO)
        assert not out["ok"]

    with as_agency("iia.test"):
        assert versions.working()["org.kind"]["value"] == "district"


def test_a_snapshot_id_cannot_escape_the_directory() -> None:
    """It reaches a filesystem path, so `../../` has to be refused rather than
    resolved."""
    with as_agency("iia.test"):
        for nasty in ("../../etc", "..", "a/b", "a\\b"):
            out = snapshot.restore(nasty, WHO)
            assert not out["ok"], nasty
            assert snapshot.forget(nasty, WHO)["ok"] is False, nasty


def test_the_audit_log_is_never_in_a_snapshot() -> None:
    """"Log should survive absolutely." A snapshot that could roll it back
    would make it a draft rather than a record."""
    with as_agency("iia.test"):
        _answer("org.kind", "city")
        taken = snapshot.take(WHO, label="Check")
        folder = tenant.data_dir() / "snapshots" / taken["id"]
        held = {p.name for p in folder.iterdir()}
        assert "log.jsonl" not in held
        assert "audit" not in held
        # And nothing a reset protects is in the copy either.
        for protected in reset_mod.PROTECTED:
            assert protected.name not in held or protected.name == "about.json"


def test_taking_and_restoring_are_both_audited(tmp_path, monkeypatch) -> None:
    """The log ends up with more in it, never less. What it shows is the
    truth: that on this date these answers were replaced with an earlier
    copy."""
    from app import audit
    import app.authz as authz

    log = audit.JsonlAuditLog(tmp_path / "log.jsonl")
    monkeypatch.setattr(authz, "_default_log", log)

    with as_agency("iia.test"):
        _answer("org.kind", "city")
        taken = snapshot.take(WHO, label="Audited")
        snapshot.restore(taken["id"], WHO)
        snapshot.forget(taken["id"], WHO)

    actions = [e.action for e in log.entries()]
    assert "take_snapshot" in actions
    assert "restore_snapshot" in actions
    assert "forget_snapshot" in actions


def test_there_is_a_ceiling_on_how_many_are_kept() -> None:
    """These are full copies, and nobody prunes something the interface never
    mentions filling up."""
    with as_agency("iia.test"):
        _answer("org.kind", "city")
        for i in range(snapshot.LIMIT):
            assert snapshot.take(WHO, label=f"Number {i}")["ok"]
        refused = snapshot.take(WHO, label="One too many")
        assert not refused["ok"]
        assert "limit" in refused["error"]
        assert snapshot.listing()["room"] == 0


def test_a_label_cannot_become_a_path() -> None:
    with as_agency("iia.test"):
        _answer("org.kind", "city")
        taken = snapshot.take(WHO, label="../../oops /etc/passwd")
        assert taken["ok"]
        assert ".." not in taken["id"]
        assert "/" not in taken["id"]
        # Their words are kept on the record even though the folder is safe.
        assert "oops" in snapshot.listing()["snapshots"][0]["label"]
