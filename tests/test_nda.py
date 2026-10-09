"""The NDA gate: accept, decline, confirm, lock, unlock.

The client's rule: after email verification the NDA appears with Accept or
Decline. Accept goes to the home screen. Decline notifies IIA immediately and
asks "Are you sure?". Decline again and the account is locked until IIA unlocks
it after speaking to the person.

The lock is the only state in this application a user can reach that they cannot
get out of on their own. That is the point of it, and it is also why every path
into and out of it is tested here rather than trusted.
"""

from __future__ import annotations

import json

import pytest

from app import nda

WHO = {"name": "Jane Smith", "title": "Deputy Director", "agency": "sc.des"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(nda, "STORE", tmp_path / "nda.json")
    # No SMTP in tests. The queue must still record the notification, which is
    # the property that matters — see test_a_decline_is_recorded_even_when...
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_FROM", raising=False)
    yield


# ------------------------------------------------------------------ the door

def test_nobody_gets_in_before_answering() -> None:
    state = nda.status("jane.smith@des.sc.gov")
    assert state["status"] == "pending"
    assert not state["may_enter"]
    assert not nda.may_enter("jane.smith@des.sc.gov")


def test_accepting_opens_the_door() -> None:
    result = nda.accept("jane.smith@des.sc.gov", **WHO)
    assert result["ok"], result.get("error")
    assert result["may_enter"]
    assert nda.may_enter("jane.smith@des.sc.gov")


def test_an_acceptance_records_the_version_that_was_accepted() -> None:
    """The document says acceptance is evidence of the agreement, so the
    evidence has to identify what was agreed to."""
    nda.accept("jane.smith@des.sc.gov", **WHO)
    state = nda.status("jane.smith@des.sc.gov")
    assert state["sha256"] == nda.document()["sha256"]
    assert len(state["sha256"]) == 64
    assert state["accepted_at"]
    assert state["accepted_name"] == "Jane Smith"


def test_a_changed_document_has_to_be_accepted_again(monkeypatch) -> None:
    """An old agreement must not silently cover new terms.

    Nothing here can tell a corrected typo from a new clause, so any change
    re-asks. The alternative is sometimes admitting someone under terms they
    never saw, which for a confidentiality agreement is not a close call.
    """
    nda.accept("jane.smith@des.sc.gov", **WHO)
    assert nda.may_enter("jane.smith@des.sc.gov")

    monkeypatch.setattr(nda, "document", lambda: {
        "available": True, "url": "/x.pdf", "sha256": "f" * 64, "bytes": 1})
    later = nda.status("jane.smith@des.sc.gov")
    assert later["superseded"]
    assert not later["may_enter"], "a stale acceptance must not open the door"
    assert not nda.may_enter("jane.smith@des.sc.gov")
    assert "earlier version" in later["note"]
    assert later["previously_accepted_at"], "the earlier acceptance still stands"


def test_reaccepting_keeps_the_earlier_acceptance_on_record() -> None:
    """The document calls the record evidence of the agreement. Overwriting it
    when the NDA is reissued would destroy the evidence of the earlier terms."""
    import json as _json
    nda.accept("jane.smith@des.sc.gov", **WHO)
    first = nda.status("jane.smith@des.sc.gov")["sha256"]

    nda.accept("jane.smith@des.sc.gov", **WHO)      # a second acceptance
    saved = _json.loads(nda.STORE.read_text(encoding="utf-8"))
    history = saved["people"]["jane.smith@des.sc.gov"]["history"]
    assert len(history) == 1
    assert history[0]["sha256"] == first
    assert history[0]["at"]


def test_agreement_is_never_recorded_against_a_missing_document(
        monkeypatch) -> None:
    monkeypatch.setattr(nda, "DOCUMENT", nda.ROOT / "does" / "not" / "exist.pdf")
    result = nda.accept("jane.smith@des.sc.gov", **WHO)
    assert not result["ok"]
    assert not nda.may_enter("jane.smith@des.sc.gov")


@pytest.mark.parametrize("address", ["", "not-an-email", "   "])
def test_a_nonsense_address_is_refused(address: str) -> None:
    assert not nda.accept(address, **WHO)["ok"]
    assert not nda.decline(address, **WHO)["ok"]


# -------------------------------------------------------- declining, twice

def test_the_first_decline_asks_rather_than_locks() -> None:
    """People misclick, and people hesitate over a legal document. Locking on
    the first press puts an unrecoverable state one accidental click away."""
    result = nda.decline("jane.smith@des.sc.gov", **WHO)
    assert result["status"] == "declined_once"
    assert result["confirm_required"]
    assert nda.status("jane.smith@des.sc.gov")["headline"] == "Are you sure?"


def test_you_can_still_accept_after_declining_once() -> None:
    nda.decline("jane.smith@des.sc.gov", **WHO)
    assert nda.accept("jane.smith@des.sc.gov", **WHO)["ok"]
    assert nda.may_enter("jane.smith@des.sc.gov")


def test_declining_twice_locks_the_account() -> None:
    nda.decline("jane.smith@des.sc.gov", **WHO)
    result = nda.decline("jane.smith@des.sc.gov", **WHO)
    assert result["status"] == "locked"
    state = nda.status("jane.smith@des.sc.gov")
    assert not state["may_enter"]
    assert state["locked_at"]


def test_a_locked_account_cannot_accept_its_way_out() -> None:
    """Otherwise the lock is a speed bump, not a lock."""
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)
    result = nda.accept("jane.smith@des.sc.gov", **WHO)
    assert not result["ok"]
    assert result["status"] == "locked"
    assert not nda.may_enter("jane.smith@des.sc.gov")


def test_the_locked_message_says_who_to_contact() -> None:
    """A dead end with no way forward is a support ticket nobody files."""
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)
    note = nda.status("jane.smith@des.sc.gov")["note"]
    assert nda.notify_address() in note
    assert "lifted by a person" in note


def test_declining_again_while_locked_changes_nothing() -> None:
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)
    before = nda.status("jane.smith@des.sc.gov")["locked_at"]
    nda.decline("jane.smith@des.sc.gov", **WHO)
    assert nda.status("jane.smith@des.sc.gov")["locked_at"] == before


# ------------------------------------------------------------ notifying IIA

def test_iia_is_notified_on_the_first_decline_not_only_on_the_lock() -> None:
    """Client: "If decline, it should notify us immediately". The hesitation is
    the case worth a conversation, so it is the case that must be heard."""
    nda.decline("jane.smith@des.sc.gov", **WHO)
    notices = nda.pending_notifications()
    assert len(notices) == 1
    assert notices[0]["kind"] == "declined"
    assert notices[0]["email"] == "jane.smith@des.sc.gov"
    assert notices[0]["name"] == "Jane Smith"


def test_the_lock_produces_its_own_notification() -> None:
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)
    kinds = [n["kind"] for n in nda.pending_notifications()]
    assert kinds == ["locked", "declined"], "newest first"


def test_a_decline_is_recorded_even_when_the_email_cannot_be_sent() -> None:
    """A notification that exists only as a failed send is not a notification."""
    result = nda.decline("jane.smith@des.sc.gov", **WHO)
    assert result["notified"]["sent"] is False, "no SMTP in the test environment"
    assert result["notified"]["queued"] is True
    assert nda.pending_notifications()[0]["emailed"] is False


def test_a_stated_reason_travels_with_the_notification() -> None:
    nda.decline("jane.smith@des.sc.gov", reason="Legal needs to review it first",
                **WHO)
    assert "Legal needs to review" in nda.pending_notifications()[0]["reason"]


# ------------------------------------------------------------------ unlocking

def test_unlocking_restores_the_question_not_the_answer() -> None:
    """Unlocking gives them the chance to answer again. It does not answer for
    them — IIA cannot accept an NDA on someone else's behalf."""
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)

    result = nda.unlock("jane.smith@des.sc.gov", by="Brett Butz",
                        note="Spoke on the phone; happy to proceed")
    assert result["ok"]
    assert nda.status("jane.smith@des.sc.gov")["status"] == "pending"
    assert not nda.may_enter("jane.smith@des.sc.gov"), (
        "unlocking must not grant access on its own")

    assert nda.accept("jane.smith@des.sc.gov", **WHO)["ok"]
    assert nda.may_enter("jane.smith@des.sc.gov")


def test_an_unlock_names_the_person_who_did_it() -> None:
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)
    assert not nda.unlock("jane.smith@des.sc.gov", by="")["ok"], (
        "an unlock with no name is not a record of anything")

    nda.unlock("jane.smith@des.sc.gov", by="Brett Butz", note="Call on 20 Aug")
    saved = json.loads(nda.STORE.read_text(encoding="utf-8"))
    history = saved["people"]["jane.smith@des.sc.gov"]["unlocks"]
    assert history[-1]["by"] == "Brett Butz"
    assert history[-1]["note"] == "Call on 20 Aug"
    assert history[-1]["at"]


def test_unlocking_something_that_is_not_locked_is_refused() -> None:
    assert not nda.unlock("nobody@des.sc.gov", by="Brett Butz")["ok"]
    nda.accept("jane.smith@des.sc.gov", **WHO)
    assert not nda.unlock("jane.smith@des.sc.gov", by="Brett Butz")["ok"]


def test_locked_accounts_are_listed_for_iia() -> None:
    nda.decline("a@des.sc.gov", name="A One", title="T")
    nda.decline("a@des.sc.gov", name="A One", title="T")
    nda.accept("b@des.sc.gov", name="B Two", title="T")
    locked = nda.locked_accounts()
    assert [p["email"] for p in locked] == ["a@des.sc.gov"]


# ------------------------------------------------------------------- the doc

def test_the_document_exists_and_is_a_pdf() -> None:
    doc = nda.document()
    assert doc["available"], doc.get("error")
    assert doc["url"].endswith(".pdf")
    assert nda.DOCUMENT.read_bytes()[:5] == b"%PDF-"


def test_the_hash_is_computed_from_the_file_not_hardcoded() -> None:
    """A constant would keep claiming a version after the PDF was replaced."""
    import hashlib
    assert nda.document()["sha256"] == hashlib.sha256(
        nda.DOCUMENT.read_bytes()).hexdigest()


# ------------------------------------------------------------------- the log

def test_every_transition_reaches_the_audit_log(tmp_path, monkeypatch) -> None:
    """Client: "WE NEED TO LOG ALL CHOICES, ACTIVITIES". Accepting or refusing
    a confidentiality agreement is squarely one of those."""
    from app.audit import JsonlAuditLog
    log = JsonlAuditLog(tmp_path / "log.jsonl")
    monkeypatch.setattr("app.audit.JsonlAuditLog", lambda *a, **k: log)

    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.decline("jane.smith@des.sc.gov", **WHO)
    nda.unlock("jane.smith@des.sc.gov", by="Brett Butz")
    nda.accept("jane.smith@des.sc.gov", **WHO)

    actions = [e.action for e in log.entries()]
    assert actions == ["nda_declined", "nda_locked", "nda_unlocked",
                       "nda_accepted"]
    outcomes = {e.action: e.outcome for e in log.entries()}
    assert outcomes["nda_declined"] == "denied"
    assert outcomes["nda_accepted"] == "allowed"
