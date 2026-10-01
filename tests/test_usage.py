"""Who is using GAIUS, and what this page may and may not claim.

The client asked for "which state, how many hours he logged in, track every
single user and what they have worked on and their progress", for whoever
signs in on an ``@iiac.ai`` address.

Most of what follows is about two things rather than about the counting.

**It crosses the line, so the gate has to hold.** Every other screen is
scoped to one agency because reading another agency's work is the thing this
product must never do — *"THE ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE
OR HAVE ACCESS TO OTHER AGENCIES."* This one reads all of them, on the same
terms as the bug queue: a proven email address, never a capacity somebody
picks from a dropdown.

**It must not overstate what it knows.** There was no record of signing in
when the page was asked for, so "hours logged in" was not a thing the log
could answer. The figure is inferred for the history and measured from now
on, and the page says which. A usage page whose numbers cannot be trusted is
worse than none.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app import usage


def _row(name: str, action: str, at: datetime, *, agency: str = "sc.des",
         outcome: str = "allowed") -> dict:
    return {
        "action": action,
        "actor": "sean.ot",
        "at": at.isoformat(timespec="seconds"),
        "outcome": outcome,
        "detail": {"actor_name": name, "agency": agency, "actor_title": "CTO"},
    }


START = datetime(2026, 9, 18, 9, 0, tzinfo=timezone.utc)


def _only(rows: list[dict], name: str = "Jo Bloggs") -> usage.Person:
    found = [p for p in usage.people(rows) if p.name == name]
    assert found, f"no person called {name}"
    return found[0]


# --------------------------------------------------------------- the counting

def test_actions_close_together_are_one_sitting() -> None:
    rows = [_row("Jo Bloggs", "answer_framework_question",
                 START + timedelta(minutes=m)) for m in (0, 5, 12, 25)]
    person = _only(rows)
    assert len(person.sittings) == 1
    assert person.active_seconds == 25 * 60


def test_a_long_silence_starts_a_new_sitting() -> None:
    """Without a sign-in to say otherwise, silence is absence."""
    rows = [_row("Jo Bloggs", "answer_framework_question", START),
            _row("Jo Bloggs", "answer_framework_question",
                 START + timedelta(minutes=5)),
            _row("Jo Bloggs", "answer_framework_question",
                 START + timedelta(hours=3))]
    person = _only(rows)
    assert len(person.sittings) == 2


def test_one_action_alone_is_credited_rather_than_zeroed() -> None:
    """Somebody who answers one question and leaves did use the product."""
    person = _only([_row("Jo Bloggs", "answer_framework_question", START)])
    assert person.active_seconds == usage.LONE_ACTION.total_seconds()


def test_what_they_worked_on_is_grouped() -> None:
    rows = [_row("Jo Bloggs", "answer_framework_question", START),
            _row("Jo Bloggs", "answer_who_decides",
                 START + timedelta(minutes=1)),
            _row("Jo Bloggs", "take_snapshot", START + timedelta(minutes=2))]
    person = _only(rows)
    assert person.worked_on["Answering the framework"] == 2
    assert person.worked_on["Keeping a copy"] == 1


def test_a_refusal_is_counted_separately() -> None:
    rows = [_row("Jo Bloggs", "adopt_framework_version", START,
                 outcome="refused")]
    assert _only(rows).refused == 1


# ------------------------------------------- measured rather than inferred

def test_a_sign_in_makes_reading_time_count() -> None:
    """The whole reason the events were added.

    Somebody signs in, reads their framework for ninety minutes, changes one
    thing and signs out. The gap rule alone reports two sittings of almost no
    length, because nothing was recorded in between. The bracket reports the
    ninety minutes that happened.
    """
    rows = [
        _row("Jo Bloggs", "sign_in", START),
        _row("Jo Bloggs", "answer_framework_question",
             START + timedelta(minutes=90)),
        _row("Jo Bloggs", "sign_out", START + timedelta(minutes=95)),
    ]
    person = _only(rows)
    assert len(person.sittings) == 1
    assert person.sittings[0].measured
    assert person.active_seconds == 95 * 60
    assert person.sign_ins == 1


def test_a_bracket_nobody_closed_cannot_run_away() -> None:
    """Most people close the tab rather than signing out.

    An open bracket that swallowed everything afterward would report a
    week-long sitting, and one absurd figure discredits every other number on
    the page.
    """
    rows = [
        _row("Jo Bloggs", "sign_in", START),
        _row("Jo Bloggs", "answer_framework_question",
             START + timedelta(minutes=10)),
        # Next day. No sign-out ever came.
        _row("Jo Bloggs", "answer_framework_question",
             START + timedelta(days=1)),
    ]
    person = _only(rows)
    assert len(person.sittings) == 2
    assert person.sittings[0].seconds == 10 * 60
    assert person.active_seconds < usage.MAX_SITTING.total_seconds()


def test_two_sign_ins_are_two_sittings() -> None:
    """Even close together: an explicit start ends whatever preceded it."""
    rows = [_row("Jo Bloggs", "sign_in", START),
            _row("Jo Bloggs", "sign_in", START + timedelta(minutes=2))]
    assert len(_only(rows).sittings) == 2


def test_a_sitting_cannot_exceed_the_ceiling() -> None:
    rows = [_row("Jo Bloggs", "sign_in", START),
            _row("Jo Bloggs", "answer_framework_question",
                 START + timedelta(hours=1)),
            _row("Jo Bloggs", "answer_framework_question",
                 START + timedelta(hours=20))]
    person = _only(rows)
    for sitting in person.sittings:
        assert sitting.seconds <= usage.MAX_SITTING.total_seconds()


# ------------------------------------------------------ people and robots

@pytest.mark.parametrize("name", [
    "Test", "Test Officer", "Tester", "Boot check", "Switch check",
    "QA Bot", "Dana Reed", "Jane Smith", "Council member",
])
def test_a_fixture_is_not_a_user(name: str) -> None:
    """A usage page reporting the test suite as its busiest user is not
    reporting usage."""
    assert _only([_row(name, "answer_framework_question", START)],
                 name).robot, name


@pytest.mark.parametrize("name", [
    "Brett Butz", "lokesh dandu", "Campbell Jennie", "Maria Testerman",
])
def test_a_person_is_not_a_fixture(name: str) -> None:
    """Substring matching made a robot of anyone named Testerman."""
    assert not _only([_row(name, "answer_framework_question", START)],
                     name).robot, name


def test_the_harness_container_is_always_a_fixture() -> None:
    rows = [_row("Brett Butz", "answer_framework_question", START,
                 agency="gaius.harness")]
    assert _only(rows, "Brett Butz").robot


def test_a_capacity_is_not_a_second_person() -> None:
    """The header lets one person move between capacities deliberately. Those
    are recorded against them, not treated as different people."""
    rows = [_row("Jo Bloggs", "answer_framework_question", START),
            {**_row("Jo Bloggs", "adopt_framework_version",
                    START + timedelta(minutes=1)), "actor": "council.cto"}]
    everyone = [p for p in usage.people(rows) if p.name == "Jo Bloggs"]
    assert len(everyone) == 1
    assert everyone[0].actors == {"sean.ot", "council.cto"}


def test_an_entry_with_no_name_is_not_attributed_to_anybody() -> None:
    rows = [{"action": "inspect", "actor": "sean.ot",
             "at": START.isoformat(), "detail": {}}]
    assert usage.people(rows) == []


# -------------------------------------------------------------- the report

def test_the_report_says_what_it_does_not_know(monkeypatch) -> None:
    """The caveat is part of the answer, not a footnote to it."""
    monkeypatch.setattr(usage, "_read", lambda path: [
        _row("Jo Bloggs", "answer_framework_question", START),
        {"action": "inspect", "actor": "x", "at": START.isoformat(),
         "detail": {}},
        _row("Jo Bloggs", "answer_framework_question",
             START + timedelta(minutes=1), agency=""),
    ])
    monkeypatch.setattr(usage, "progress_of",
                        lambda a: {"answered": 1, "asked": 2, "percent": 50,
                                   "versions": 0, "adopted": False})
    report = usage.report()
    caveats = report["caveats"]
    assert caveats["time_is_inferred"] is True
    assert caveats["sign_ins_recorded"] == 0
    assert caveats["unattributed_entries"] == 1
    # Two: the unattributed one, and the one carrying a name but no agency.
    # The counts overlap on purpose — they answer different questions, "whose
    # was this" and "which agency was this", and an entry can fail both.
    assert caveats["entries_without_agency"] == 2
    assert "not time signed in" in caveats["note"]
    assert caveats["idle_gap_minutes"] == 30


def test_the_report_stops_calling_it_inferred_once_it_is_measured(
        monkeypatch) -> None:
    monkeypatch.setattr(usage, "_read", lambda path: [
        _row("Jo Bloggs", "sign_in", START),
        _row("Jo Bloggs", "sign_out", START + timedelta(minutes=30)),
    ])
    monkeypatch.setattr(usage, "progress_of",
                        lambda a: {"answered": 0, "asked": 0, "percent": 0,
                                   "versions": 0, "adopted": False})
    caveats = usage.report()["caveats"]
    assert caveats["sign_ins_recorded"] == 1
    assert caveats["time_is_inferred"] is False


def test_no_email_address_reaches_the_report(monkeypatch) -> None:
    """Privacy is a control inside the framework this product sells, so it
    cannot be broken by the product's own admin screen. An address is the one
    thing here that identifies somebody outside this application, and nothing
    on the page needs it."""
    import json

    monkeypatch.setattr(usage, "_read", lambda path: [
        _row("Jo Bloggs", "sign_in", START),
        _row("Jo Bloggs", "answer_framework_question",
             START + timedelta(minutes=2)),
    ])
    monkeypatch.setattr(usage, "progress_of",
                        lambda a: {"answered": 0, "asked": 0, "percent": 0,
                                   "versions": 0, "adopted": False})
    assert "@" not in json.dumps(usage.report())


def test_progress_comes_from_the_agency_own_answers(monkeypatch, tmp_path
                                                    ) -> None:
    """Not counted from the log: an answer changed twice is one answer, and a
    question that stopped being asked should stop being counted."""
    from app import module_one, tenant, versions
    from app.authz import Actor, Role

    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    who = Actor("sean.ot", "Jo Bloggs", Role.OT, title="CTO")

    versions.answer("who.tiebreak", "The Manager", who)
    versions.answer("who.tiebreak", "The Director", who)   # changed his mind

    got = usage.progress_of("")
    assert got["answered"] == 1, "one answer, changed twice"
    assert got["asked"] == len(
        [q for s in module_one.STEPS for q in s.questions
         if module_one.visible(q, versions.working())])


# ------------------------------------------------------------- the gate

def test_only_a_proven_admin_address_may_read_it(monkeypatch) -> None:
    from app import admin, server
    from app.authz import Actor, Role

    monkeypatch.setattr(usage, "_read", lambda path: [])

    for email in ("", "someone@des.sc.gov", "brett@iiac.ai.example.com",
                  "notbrett@iiac.ai"):
        actor = Actor("sean.ot", "Jo", Role.OT, title="CTO", email=email)
        answer = server.api_usage(actor, {}, {})
        assert answer["allowed"] is False, email
        assert "people" not in answer, email
        assert "agencies" not in answer, email

    for email in sorted(admin.admins()):
        actor = Actor("sean.ot", "Jo", Role.OT, title="CTO", email=email)
        answer = server.api_usage(actor, {}, {})
        assert answer["allowed"] is True, email
        assert "people" in answer and "agencies" in answer


def test_a_capacity_cannot_stand_in_for_an_address(monkeypatch) -> None:
    """The bug queue leaked exactly this way: it keyed off `is_ot`, and every
    user can become OT from the header dropdown."""
    from app import server
    from app.authz import Actor, Role

    monkeypatch.setattr(usage, "_read", lambda path: [])
    for role in (Role.OT, Role.COUNCIL):
        actor = Actor("sean.ot", "Jo", role, title="CTO", email="")
        assert server.api_usage(actor, {}, {})["allowed"] is False
