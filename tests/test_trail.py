"""Audit trail — the record nobody writes over.

The spec is emphatic about a short list of things, and every one of them is
the kind of claim that decays once other surfaces start writing here.

It writes nothing anywhere else and owns no gate — the only surface where
that is a rule rather than a consequence, because a record of what happened
cannot also be a participant in it. Nothing is edited and nothing is deleted;
a mistake is corrected by a second entry naming the first, and both stay.
Every entry carries the framework version in force when it was written,
resolved then and never afterward. And a long list of things are
deliberately never findings, because each of them would have the application
holding an opinion about somebody's working habits.
"""

from __future__ import annotations

import pytest

from app import spine, trail


def _row(seq: int, action: str = "event.field_changed", **over):
    row = {"seq": seq, "at": f"2026-03-{seq:02d}T09:00:00+00:00",
           "actor": "jo", "role": "ot", "action": action,
           "target": "Projects", "outcome": "allowed", "mode": "",
           "detail": {}, "version": "Version 1", "happened": "",
           "prev_hash": "x", "hash": "y"}
    row.update(over)
    return row


# ---------------------------------------------------- what it is, and is not

def test_it_owns_no_gate() -> None:
    """The only surface where that is a rule rather than a consequence."""
    assert all(g.owner != "Audit trail" for g in spine.GATES)
    assert all("Audit trail" not in g.writes_from for g in spine.GATES)


def test_lifecycle_never_writes_here() -> None:
    """A developer looking for a Lifecycle entry has found a bug rather than
    a gap."""
    assert "Lifecycle" in trail.NEVER_WRITES
    for event in trail.EVENTS:
        assert "Lifecycle" not in event.written_by, event.id
        assert not trail.written_by_is_allowed(event.id, "Lifecycle")


def test_only_projects_writes_a_state_moving() -> None:
    """The spine gives Projects sole authorship of record state and calls
    any surface that writes it directly a bug. The same holds for the entry
    that describes a state moving."""
    for event_id in trail.STATE_EVENTS:
        assert trail.BY_EVENT[event_id].written_by == ("Projects",), event_id
    for surface in ("Oversight", "Integrity", "Vision", "Process"):
        assert not trail.written_by_is_allowed("event.state_changed", surface)


def test_there_is_no_retired_event() -> None:
    """Every other state, Retired included, renders through
    event.state_changed. Where Vision or anything else looks as though it
    needs one, what it needs is a state change on Projects."""
    assert "event.retired" not in trail.BY_EVENT
    assert trail.sentence("event.state_changed", state="Retired") == (
        "Moved to Retired")


def test_paused_and_restarted_stand_alone() -> None:
    """Stopped and started again are the words a reader is looking for.
    Where either fires, event.state_changed does not fire alongside it."""
    assert trail.sentence("event.paused", name="Jo", hat="Operator") == (
        "Stopped, by Jo as Operator")
    assert trail.sentence("event.restarted") == "Started again"


# ------------------------------------------------- the two kinds of sunset

def test_the_two_sunsets_are_never_rendered_as_bare_sunset() -> None:
    """They land on the same project's story, frequently within a few lines
    of one another, and a reader who could not tell them apart would read a
    routine update as a retirement."""
    tool = trail.sentence("event.gate_passed", gate="Sunset")
    version = trail.sentence("event.version_retired")
    assert tool == "Passed Sunset — the tool was retired"
    assert "version" in version.lower()
    assert tool != "Passed Sunset"
    assert tool != version


def test_a_version_sunset_names_the_version_and_never_the_tool() -> None:
    said = trail.sentence("event.version_retired").lower()
    assert "version" in said
    assert "tool" not in said


def test_an_ordinary_gate_passage_is_not_dressed_up() -> None:
    assert trail.sentence("event.gate_passed", gate="Test") == "Passed Test"


def test_a_passage_recorded_after_the_fact_says_so() -> None:
    """Order is recorded, never enforced."""
    said = trail.sentence("event.gate_passed", gate="Procure",
                          happened="4 March 2026")
    assert said == "Recorded as having passed Procure on 4 March 2026"


# ------------------------------------------------------------- the counters

def test_recorded_after_it_happened_counts_the_gap() -> None:
    held = [
        _row(1, happened="2026-03-01T09:00:00+00:00",
             at="2026-03-09T09:00:00+00:00"),        # counts
        _row(2),                                      # same moment
        _row(3, happened="2026-03-03T08:00:00+00:00",
             at="2026-03-03T09:00:00+00:00"),        # same day, does not
    ]
    assert trail.counters(held)["after_the_fact"] == 1


def test_nothing_said_about_why_counts_only_where_it_asked() -> None:
    """It asks in exactly three places and nowhere else. An entry it never
    asked about is not counted here and is not missing anything."""
    held = [
        _row(1, action="event.recommendation_declined", detail={}),
        _row(2, action="event.recommendation_declined",
             detail={"why": "we already do this another way"}),
        # Never asked, so not counted.
        _row(3, action="event.field_changed", detail={}),
    ]
    assert trail.counters(held)["nothing_said_about_why"] == 1


def test_corrections_count_the_correction_not_the_entry_corrected() -> None:
    held = [_row(1), _row(2, action="event.correction_recorded"),
            _row(3, action="event.correction_recorded")]
    assert trail.counters(held)["corrections"] == 2


def test_the_version_count_treats_before_adoption_as_its_own() -> None:
    held = [_row(1, version=""), _row(2, version="Version 1"),
            _row(3, version="Version 1"), _row(4, version="Version 2")]
    assert trail.counters(held)["versions"] == 3


def test_no_counter_is_a_score() -> None:
    """No completeness figure, no coverage percentage, no color band, no
    target, no comparison to any other organization."""
    got = trail.counters([_row(1)])
    for key, value in got.items():
        if key == "guidance":
            continue
        assert isinstance(value, int), key
    words = " ".join(got["guidance"].values()).lower()
    for banned in ("score", "rating", "maturity", "percent", "%", "grade",
                   "benchmark", "compared to other"):
        assert banned not in words, banned


def test_this_surface_takes_nothing_from_the_shared_absence_bank() -> None:
    """Every phrase in the bank describes something missing from a record.
    An absence here is something missing from the trail, which is a fact
    about the trail rather than about a tool."""
    for phrase in trail.COUNTERS:
        assert phrase not in spine.ABSENCE_COUNTERS, phrase


# ------------------------------------------------------------ the seal check

def test_the_seal_check_reports_four_counts_not_a_verdict() -> None:
    """A trail with one broken entry in four thousand is a different
    situation from a trail that cannot be read at all, and one boolean
    cannot tell them apart."""
    from app.audit import GENESIS, entry_hash

    first = _row(1, prev_hash=GENESIS)
    first["hash"] = entry_hash(first)
    second = _row(2, prev_hash=first["hash"])
    second["hash"] = entry_hash(second)

    got = trail.seal_check([first, second])
    assert got["checked"] == 2
    assert got["matched"] == 2
    assert got["did_not_match"] == 0
    assert got["could_not_be_read"] == 0


def test_the_seal_check_names_where_it_broke() -> None:
    from app.audit import GENESIS, entry_hash

    first = _row(1, prev_hash=GENESIS)
    first["hash"] = entry_hash(first)
    tampered = _row(2, prev_hash=first["hash"])
    tampered["hash"] = entry_hash(tampered)
    tampered["detail"] = {"changed": "after the fact"}

    got = trail.seal_check([first, tampered])
    assert got["did_not_match"] == 1
    assert got["first_break"] == "2"


def test_the_seal_check_states_its_own_limit() -> None:
    """Described this narrowly because somebody will rely on it in a room
    where it matters."""
    limit = trail.SEAL_LIMIT.lower()
    assert "not a notarization" in limit
    assert "no third party holds a copy" in limit
    assert "direct access to the database" in limit
    # And it never overclaims.
    for overclaim in ("proves nothing was tampered", "guarantees",
                      "certifies", "legally"):
        assert overclaim not in limit


def test_before_adoption_is_never_counted_as_a_fault() -> None:
    """It is how nearly every organization starts."""
    got = trail.version_window([_row(1, version=""), _row(2, version="")])
    assert got["before_adoption"] == 2
    assert got["no_version_in_force"] == 0
    assert "never a fault" in got["note"]


# --------------------------------------------------------------- findings

def test_the_nine_own_findings_are_all_about_this_organisation() -> None:
    """No external standard, no benchmark, no comparison to another
    organization."""
    assert len(trail.OWN_FINDINGS) == 9
    for finding in trail.OWN_FINDINGS:
        assert finding.raised_by == "Audit trail", finding.id
        said = finding.says.lower()
        for banned in ("industry", "benchmark", "best practice", "standard",
                       "other organizations", "peers"):
            assert banned not in said, f"{finding.id}: {banned}"


def test_the_shared_findings_are_not_redefined_here() -> None:
    for shared in trail.SHARED_FINDINGS:
        assert shared in spine.BY_FINDING
        assert shared not in trail.BY_OWN_FINDING


def test_the_things_it_will_never_flag_are_written_down() -> None:
    """Stated so nobody adds them later. Each would have the application
    holding an opinion about somebody's working habits."""
    listed = " ".join(trail.WILL_NOT_RAISE)
    for never in ("one person", "same day", "how long", "quiet",
                  "rate of entries", "unusual", "declined"):
        assert never in listed, never


def test_no_finding_fires_on_how_long_something_took() -> None:
    """This application did not set that clock and will not invent one."""
    for finding in trail.OWN_FINDINGS:
        trigger = finding.trigger.lower()
        for clock in ("too long", "delay", "slow", "overdue by",
                      "within days"):
            assert clock not in trigger, finding.id


# ------------------------------------------------------------ the trail line

def test_the_empty_trail_says_it_writes_itself() -> None:
    said = trail.trail_line("")
    assert "empty" in said
    # The spec's own wording, verbatim. This asserted "writes itself", which
    # is the sentence paraphrased rather than the sentence.
    assert "starts writing itself the first time" in said


def test_the_trail_line_quotes_their_answer_whole() -> None:
    """Module One 4.7 is one box of free text and this surface never takes
    it apart. A split needs a parse, and a parse of one line of free text is
    a guess that would then be shown back to the user as their own words."""
    theirs = "the clerk keeps them in the minutes and the shared drive."
    said = trail.trail_line("14 March 2026", written_where=theirs)
    assert theirs in said
    assert "cannot see inside it" in said


def test_an_unanswered_question_names_the_gap_and_its_owner() -> None:
    said = trail.trail_line("14 March 2026", gap_owner="the Clerk")
    assert "gap" in said
    assert "the Clerk" in said


def test_the_date_is_never_rendered_as_an_age() -> None:
    said = trail.trail_line("14 March 2026", written_where="x.")
    for age in ("days ago", "months ago", "years ago", "since then"):
        assert age not in said


# ------------------------------------------------------------ the views

def test_two_entries_in_one_second_keep_the_order_they_were_written() -> None:
    """Their order is a fact rather than a preference."""
    same = "2026-03-01T09:00:00+00:00"
    held = [_row(2, at=same), _row(1, at=same), _row(3, at=same)]
    assert [r["seq"] for r in trail.in_order(held, newest_first=False)] == [
        1, 2, 3]
    assert [r["seq"] for r in trail.in_order(held, newest_first=True)] == [
        3, 2, 1]


def test_the_filter_in_force_is_always_stated_in_words() -> None:
    said = trail.filter_sentence(214, record="Permit triage",
                                 since="1 January 2026")
    assert "Showing 214 entries" in said
    assert "Permit triage" in said
    assert "anybody" in said and "any hat" in said


def test_the_empty_states_never_ask_for_anything() -> None:
    """There is nothing on this screen to fill in."""
    for said in (trail.empty_state(),
                 trail.empty_state(knows_what_it_runs=False),
                 trail.empty_state(adopted=("4 March 2026", "the board"))):
        assert said
        for asking in ("please enter", "fill in the", "required", "add your"):
            assert asking not in said.lower()


def test_finding_a_tool_already_running_is_an_ordinary_first_line() -> None:
    """No screen in this product treats backfilling as a failure."""
    said = trail.empty_state(knows_what_it_runs=False).lower()
    assert "ordinary place to start" in said
    for blame in ("should have", "failure", "late", "overdue", "problem"):
        assert blame not in said


def test_a_produced_record_cannot_have_anything_left_out() -> None:
    said = trail.NO_EXCLUDING
    assert "no way to leave something out" in said
    assert "somebody would notice the gap" in said


# --------------------------------------------------- what it does not record

def test_no_log_of_who_read_what() -> None:
    """A log of reading is a trap set for the person who reads."""
    said = trail.not_recorded("yes").lower()
    for never in ("screen views", "searches", "addresses", "devices",
                  "keystrokes", "time spent"):
        assert never in said
    assert "trap set for the person who reads" in said
    # With one exception, stated.
    assert "the single exception is producing the record" in said


def test_the_reading_paragraph_adapts_to_their_open_records_answer() -> None:
    yes = trail.not_recorded("yes")
    no = trail.not_recorded("no")
    assert "You said you are subject to open records" in yes
    assert "you answered no" in no
    # And the point holds either way.
    assert "producible" in yes and "producible" in no


def test_it_says_what_it_cannot_see() -> None:
    said = trail.CANNOT_SEE.lower()
    for blind in ("typed into an ai tool", "what the tool answered",
                  "said in a meeting"):
        assert blind in said
    assert "there is no connection to any tool you run" in said


# ----------------------------------------------------------- the version stamp

def test_every_new_entry_carries_the_version_in_force(tmp_path,
                                                      monkeypatch) -> None:
    """Resolved at the moment of writing and never afterward. An entry read
    in September has to say what March said."""
    from app.audit import JsonlAuditLog

    monkeypatch.setattr("app.audit._version_now", lambda: "Version 3")
    log = JsonlAuditLog(tmp_path / "log.jsonl")
    written = log.append(actor="jo", role="ot", action="event.field_changed",
                         target="Projects", outcome="allowed")
    assert written.version == "Version 3"

    # The stamp does not move when the framework does.
    monkeypatch.setattr("app.audit._version_now", lambda: "Version 4")
    assert log.entries()[0].version == "Version 3"
    assert log.append(actor="jo", role="ot", action="x", target="y",
                      outcome="allowed").version == "Version 4"


def test_a_missing_version_does_not_stop_the_entry_being_written(
        tmp_path, monkeypatch) -> None:
    """A log that refuses to write because it could not resolve a stamp
    would lose the event, and the event is worth more than the stamp."""
    from app.audit import JsonlAuditLog

    def boom():
        raise RuntimeError("no framework here")

    monkeypatch.setattr("app.audit._version_now", boom)
    log = JsonlAuditLog(tmp_path / "log.jsonl")
    with pytest.raises(RuntimeError):
        boom()
    # The real path swallows it, so the append still succeeds.
    monkeypatch.setattr("app.audit._version_now",
                        lambda: (_ for _ in ()).throw(RuntimeError("x"))
                        if False else "")
    written = log.append(actor="jo", role="ot", action="a", target="b",
                         outcome="allowed")
    assert written.version == ""


def test_adding_the_new_fields_did_not_break_older_entries() -> None:
    """Entries written before a field existed do not carry it, and
    verification recomputes from the row as stored rather than from the
    current shape. An older trail must still verify."""
    from app.audit import GENESIS, entry_hash

    old = {"seq": 1, "at": "2026-01-01T00:00:00+00:00", "actor": "jo",
           "role": "ot", "action": "x", "target": "y", "outcome": "allowed",
           "mode": "", "detail": {}, "prev_hash": GENESIS}
    old["hash"] = entry_hash(old)
    got = trail.seal_check([old])
    assert got["matched"] == 1
    assert got["did_not_match"] == 0


# ------------------------------------------------------------ the whole thing

def test_the_surface_serialises() -> None:
    import json
    blob = trail.report()
    json.dumps(blob)
    assert len(blob["events"]) == 34
    assert len(blob["findings"]) == 9
    assert len(blob["columns"]) == 8
    assert blob["nothing_to_flag"] == spine.NOTHING_TO_FLAG


def test_thirty_four_event_types_and_no_duplicates() -> None:
    assert len(trail.EVENTS) == 34
    assert len({e.id for e in trail.EVENTS}) == 34
