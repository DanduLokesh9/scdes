"""Bug reports: what is kept, what is stripped, and who may do what.

The client asked for privacy to be part of v1 rather than added later, so most
of what is asserted here is absence — that a request body, a verification code
or a stray address did not survive the trip into a ticket.

One test exists because the first version got it wrong in an instructive way.
Scrubbing was applied to the reporter's own address along with everything else,
which turned every reporter into the string "[email removed]" — so all of them
compared equal, and any address could reopen any ticket. A privacy rule applied
without thinking became an access-control hole.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import bugs
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")
OPERATOR = Actor("liz.operator", "Operator", Role.OPERATOR)

CONTEXT = {"view": "Registry", "url": "/?email=jane.smith@des.sc.gov&code=482917",
           "browser": "Chrome/140", "screen": "1920x1080", "version": "test"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(bugs, "STORE", tmp_path / "bugs.jsonl")
    yield


def _file(**over):
    args = dict(expected="The registry to open", happened="It went blank.",
                context=CONTEXT, events=[], reporter="jane.smith@des.sc.gov",
                name="Jane Smith", agency="SCDES")
    args.update(over)
    return bugs.report(**args)


# ------------------------------------------------------------------- filing

def test_a_report_needs_only_what_happened() -> None:
    assert _file(expected="")["ok"]


def test_a_report_with_nothing_in_it_is_refused() -> None:
    result = _file(happened="   ")
    assert not result["ok"]
    assert "what happened" in result["error"].lower()


def test_the_context_is_captured_without_being_asked_for() -> None:
    ticket = bugs.ticket(_file()["id"])
    assert ticket["view"] == "Registry"
    assert ticket["browser"] == "Chrome/140"
    assert ticket["version"] == "test"


# ------------------------------------------------------------------ privacy

def test_addresses_and_codes_are_stripped_from_the_description() -> None:
    ticket = bugs.ticket(_file(
        happened="Broke. I am jane.smith@des.sc.gov, code 4829174.")["id"])
    assert "jane.smith@des.sc.gov" not in ticket["happened"]
    assert "4829174" not in ticket["happened"]


def test_the_url_is_stripped_too() -> None:
    """This application puts ?email= on every API call, so the URL is the most
    reliable way for an address to reach a ticket."""
    ticket = bugs.ticket(_file()["id"])
    assert "jane.smith" not in ticket["url"]
    assert "482917" not in ticket["url"]


def test_request_and_response_bodies_never_survive() -> None:
    """Bodies in this application carry framework answers and registrations."""
    ticket = bugs.ticket(_file(events=[{
        "kind": "network", "at": "now", "text": "/api/versions/answer",
        "method": "POST", "status": "200", "ms": "34",
        "body": "THE ANSWER", "response": "ALSO SECRET"}])["id"])
    event = ticket["events"][0]
    assert event["status"] == "200"          # the useful part is kept
    assert "body" not in event
    assert "response" not in event


def test_an_unknown_event_kind_is_dropped_rather_than_stored() -> None:
    """A client could send anything. Screenshots are Phase 2 and must not
    arrive early by being labeled something the server does not check."""
    ticket = bugs.ticket(_file(events=[
        {"kind": "screenshot", "at": "now", "text": "data:image/png;base64,AA"},
        {"kind": "error", "at": "now", "text": "TypeError"}])["id"])
    assert [e["kind"] for e in ticket["events"]] == ["error"]


def test_the_buffer_is_bounded() -> None:
    flood = [{"kind": "error", "at": "now", "text": f"boom {i}"}
             for i in range(2000)]
    ticket = bugs.ticket(_file(events=flood)["id"])
    assert len(ticket["events"]) <= bugs.MAX_EVENTS


def test_the_reporters_own_address_is_kept() -> None:
    """The exception, and the reason for it.

    Scrubbing this turned every reporter into the same string, so `mine()`
    showed everyone's tickets to anyone and any address could reopen any
    ticket. It is deliberate identity on their own ticket, not leakage.
    """
    ticket = bugs.ticket(_file()["id"])
    assert ticket["reporter"] == "jane.smith@des.sc.gov"


# ----------------------------------------------------------------- grouping

def test_the_same_fault_gets_the_same_fingerprint() -> None:
    """One bad deploy is one problem, however many people report it."""
    error = [{"kind": "error", "at": "now", "text": "TypeError: no gate"}]
    first = _file(events=error)
    second = _file(events=error, happened="Different words, same fault.")
    assert first["fingerprint"] == second["fingerprint"]
    assert second["seen_before"] == 1


def test_the_agency_name_does_not_split_a_group() -> None:
    """"No corpus for SCDES" and "no corpus for SCDE" are one fault."""
    a = _file(events=[{"kind": "error", "at": "n", "text": 'No corpus for "SCDES"'}])
    b = _file(events=[{"kind": "error", "at": "n", "text": 'No corpus for "SCDE"'}])
    assert a["fingerprint"] == b["fingerprint"]


def test_different_faults_stay_apart() -> None:
    a = _file(events=[{"kind": "error", "at": "n", "text": "TypeError: no gate"}])
    b = _file(events=[{"kind": "error", "at": "n", "text": "NetworkError: 500"}])
    assert a["fingerprint"] != b["fingerprint"]


# ----------------------------------------------------------------- workflow

def test_the_team_replies_and_moves_the_ticket() -> None:
    bug = _file()["id"]
    result = bugs.respond(bug, message="Fixed in the next deploy.",
                          status=bugs.FIXED, actor=OT)
    assert result["ok"]
    assert bugs.ticket(bug)["status"] == bugs.FIXED
    assert bugs.ticket(bug)["replies"][-1]["team"] is True


def test_an_operator_cannot_answer_tickets() -> None:
    bug = _file()["id"]
    assert not bugs.respond(bug, message="fixed", status=bugs.FIXED,
                            actor=OPERATOR)["ok"]


def test_only_the_reporter_may_reopen() -> None:
    bug = _file()["id"]
    bugs.respond(bug, message="Fixed.", status=bugs.FIXED, actor=OT)

    stranger = bugs.reopen(bug, message="me too", email="someone@else.gov")
    assert not stranger["ok"]
    assert "reported it" in stranger["error"]

    owner = bugs.reopen(bug, message="Still broken.",
                        email="jane.smith@des.sc.gov")
    assert owner["ok"]
    assert bugs.ticket(bug)["status"] == bugs.OPEN
    assert bugs.ticket(bug)["reopened"] == 1


def test_reopening_something_already_being_worked_on_is_refused() -> None:
    """Adds noise rather than information."""
    bug = _file()["id"]
    bugs.respond(bug, message="Looking.", status=bugs.OPEN, actor=OT)
    assert not bugs.reopen(bug, message="any news",
                           email="jane.smith@des.sc.gov")["ok"]


def test_a_reporter_sees_their_own_tickets_and_nobody_elses() -> None:
    _file()
    _file(reporter="bob.jones@des.sc.gov", name="Bob Jones")
    assert len(bugs.mine("jane.smith@des.sc.gov")) == 1
    assert bugs.mine("") == []
    assert bugs.mine("nobody@des.sc.gov") == []


# ---------------------------------------------------------------- retention

def test_old_capture_is_dropped_and_the_ticket_survives() -> None:
    """The conversation is a record. A minute of somebody's session is evidence
    for a fix, and once the fix is old it is only a liability."""
    bug = _file(events=[{"kind": "error", "at": "now", "text": "TypeError"}])["id"]
    assert bugs.ticket(bug)["events"]

    later = datetime.now(timezone.utc) + timedelta(days=bugs.RETENTION_DAYS + 1)
    result = bugs.purge(now=later)
    assert result["purged"] == 1

    after = bugs.ticket(bug)
    assert after["events"] == []
    assert after["happened"] == "It went blank.", "the ticket is not deleted"
    assert after["events_note"]


def test_purging_twice_does_not_keep_rewriting() -> None:
    _file(events=[{"kind": "error", "at": "now", "text": "TypeError"}])
    later = datetime.now(timezone.utc) + timedelta(days=bugs.RETENTION_DAYS + 1)
    assert bugs.purge(now=later)["purged"] == 1
    assert bugs.purge(now=later)["purged"] == 0


def test_the_summary_says_what_is_captured_and_for_how_long() -> None:
    info = bugs.summary()
    assert "no screen recording" in info["captures"].lower()
    assert str(bugs.RETENTION_DAYS) in info["keeps"]


# ------------------------------------------------------------ notifications

def test_a_team_reply_becomes_a_notification_for_the_reporter() -> None:
    """The loop the panel opens and the bell closes: without this the only way
    to learn whether anybody looked is to go hunting for the ticket."""
    bug = _file()["id"]
    bugs.respond(bug, message="Fixed this morning.", status=bugs.FIXED, actor=OT)

    news = bugs.notifications("jane.smith@des.sc.gov")
    assert news["total"] == 1
    item = news["items"][0]
    assert item["id"] == bug
    assert item["status"] == bugs.FIXED
    assert "Fixed this morning" in item["message"]
    assert item["about"], "it names which report is being answered"
    assert item["can_reopen"] is True


def test_nobody_else_is_notified() -> None:
    bugs.respond(_file()["id"], message="Fixed.", status=bugs.FIXED, actor=OT)
    assert bugs.notifications("someone@else.gov")["total"] == 0
    assert bugs.notifications("")["total"] == 0
    assert bugs.notifications("not-an-email")["total"] == 0


def test_your_own_words_are_not_news() -> None:
    """A reopen is the reporter talking. Notifying them of it would make the
    bell light every time they used it."""
    bug = _file()["id"]
    bugs.respond(bug, message="Fixed.", status=bugs.FIXED, actor=OT)
    bugs.reopen(bug, message="Still broken.", email="jane.smith@des.sc.gov")

    items = bugs.notifications("jane.smith@des.sc.gov")["items"]
    assert len(items) == 1, "the team reply only"
    assert all(i["message"] != "Still broken." for i in items)


def test_a_ticket_being_worked_on_offers_no_reopen() -> None:
    """Reopening something already open adds noise, so the button is only
    offered where pressing it would do something."""
    bug = _file()["id"]
    bugs.respond(bug, message="Looking into it.", status=bugs.OPEN, actor=OT)
    assert bugs.notifications("jane.smith@des.sc.gov")["items"][0]["can_reopen"] is False


def test_notifications_are_newest_first() -> None:
    bug = _file()["id"]
    bugs.respond(bug, message="Looking.", status=bugs.OPEN, actor=OT)
    bugs.respond(bug, message="Fixed.", status=bugs.FIXED, actor=OT)
    items = bugs.notifications("jane.smith@des.sc.gov")["items"]
    assert len(items) == 2
    assert items[0]["at"] >= items[1]["at"]
