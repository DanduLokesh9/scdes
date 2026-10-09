"""Noticing a misspelling, and refusing to be clever about it.

The client's ticket, on 11.1: "Noting to test this. I intentionally mis-spelled
'the' to 'teh' to see if the system notices and correct." BUG-305E491D.

Two properties matter more than the catching, and most of what follows is
about them. Nothing is changed without somebody accepting it, because
`prose.py` carries these answers into an adopted document word for word. And
nothing correctly-spelled is ever flagged, because a warning that is wrong
four times in five teaches the reader to dismiss the time it is right — and in
this module the words a dictionary does not hold are the agency's own name,
its role titles, its ordinances and its places.
"""

from __future__ import annotations

import pytest

from app import typos


def test_it_notices_the_one_he_tested_with() -> None:
    found = typos.found("teh framework applies to all units")
    assert [s["word"] for s in found] == ["teh"]
    assert found[0]["suggest"] == "the"


def test_it_carries_the_capitalisation_across() -> None:
    """A suggestion that introduces a second error is worse than none."""
    assert typos.found("Teh Council decides")[0]["suggest"] == "The"
    assert typos.found("TEH COUNCIL")[0]["suggest"] == "THE"
    assert typos.found("teh council")[0]["suggest"] == "the"


def test_one_entry_per_word_however_often_it_appears() -> None:
    """Somebody who typed it four times wants telling once, and all four
    fixed."""
    found = typos.found("teh one, teh other, and teh third")
    assert len(found) == 1
    assert found[0]["times"] == 3
    assert typos.corrected("teh a teh b") == "the a the b"


def test_it_changes_nothing_by_itself() -> None:
    """The guarantee. `found` reports; only `corrected` rewrites, and it is
    called after somebody has clicked."""
    text = "teh framework"
    typos.found(text)
    assert text == "teh framework"
    # And the note says so out loud, because the answer is already stored by
    # the time anybody reads it.
    assert "Nothing has been changed" in typos.note(typos.found(text))


# ------------------------------------------------- what it must never flag

@pytest.mark.parametrize("text", [
    # British spellings are correctly spelled words. Telling an American
    # agency its British-spelled word is an error would be this application
    # having a view about somebody's prose.
    "the organisation uses a licence",
    "our programme of work",
    "in our judgement",
    "we analyse and categorise",
    # The words a governance document is full of that no dictionary holds.
    "Tidewater Water District",
    "the Permitting Manager and the District Manager",
    "SCDES, NMED and the ADA Title II web rule",
    "WCAG 2.1 Level AA",
    "Berkeley County Ordinance 2024-14",
    # Ordinary correct prose.
    "No AI tool finalises an action affecting a person's rights.",
    "Records created with the assistance of an AI tool are public records.",
])
def test_it_flags_nothing_that_is_correct(text: str) -> None:
    assert typos.found(text) == [], text


def test_the_list_holds_no_real_words() -> None:
    """The property the whole design rests on: every key is a non-word.

    Checked structurally rather than against a dictionary — no entry may be
    the correct spelling of anything else in the list, no entry may map to
    itself, and no entry may be a word this project's own copy uses.
    """
    corrections = set(typos.CORRECTIONS.values())
    for wrong, right in typos.CORRECTIONS.items():
        assert wrong != right, wrong
        assert wrong not in corrections, (
            f"{wrong!r} is offered as a correction elsewhere")
        assert wrong.islower(), f"{wrong!r} should be keyed in lower case"

    # Nothing in the module's own user-facing copy is on the list. If a real
    # word ever gets added, this is what notices.
    from app import module_one as m1
    words = set()
    for question in m1.all_questions():
        for text in (question.prompt, question.help, question.above):
            words |= {w.strip(".,;:()'“”?").lower()
                      for w in (text or "").split()}
    collisions = sorted(words & set(typos.CORRECTIONS))
    assert not collisions, collisions


def test_a_correction_keeps_everything_else_untouched() -> None:
    before = ("teh District Manager, the Permitting Manager and WCAG 2.1 "
              "Level AA")
    after = typos.corrected(before)
    assert after.startswith("the District Manager")
    assert "Permitting Manager" in after
    assert "WCAG 2.1 Level AA" in after


def test_it_stops_short_of_becoming_a_proofreading_report() -> None:
    """Past a handful it is not a note any more."""
    many = " ".join(list(typos.CORRECTIONS)[:20])
    assert len(typos.found(many)) == typos.MOST


# ----------------------------------------------------------- through the API

def test_a_saved_answer_carries_the_note(monkeypatch, tmp_path) -> None:
    """The answer is stored as typed, and the suggestion travels beside it."""
    from app import server, versions
    from app.authz import Actor, Role

    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    who = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")

    saved = server.api_version_answer(
        who, {"key": "who.tiebreak", "value": "teh District Manager"}, {})
    assert saved["ok"]
    assert saved["spelling"][0]["word"] == "teh"
    # Stored exactly as typed. Nothing corrected it on the way in.
    held, _ = __import__("app.module_one", fromlist=["value_of"]).value_of(
        versions.working(), "who.tiebreak")
    assert held == "teh District Manager"


def test_a_clean_answer_carries_no_note(monkeypatch, tmp_path) -> None:
    from app import server, versions
    from app.authz import Actor, Role

    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    who = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")

    saved = server.api_version_answer(
        who, {"key": "who.tiebreak", "value": "The District Manager"}, {})
    assert saved["ok"]
    assert "spelling" not in saved
