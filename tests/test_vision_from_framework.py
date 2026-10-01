"""Vision is part of the framework (Brett, BUG-BE30FBD3).

"Vision should be a module inside the Framework. Where the framework asks
what are you using AI for, that is the vision question(s). Once
incorporated, the vision section can be pre-filled from the framework."

Framework 11.1a and 11.1b ask what AI should help the organization achieve
within a year and within five years. Each line is offered on Vision with its
horizon set, and the framework document states them under Purpose.
"""

from __future__ import annotations

from app import goals, module_one as m1, prose, spine


def _q(number):
    return next(q for q in m1.all_questions() if q.number == number)


def test_the_vision_questions_are_in_the_framework():
    a, b = _q("11.1a"), _q("11.1b")
    assert a.key == "why.vision_year" and "within the next year" in a.prompt
    assert b.key == "why.vision_five" and "five years" in b.prompt
    assert a.optional and b.optional
    for q in (a, b):
        assert not spine.banned_in(q.prompt + " " + q.help + " " + q.placeholder)


def test_each_line_is_offered_as_a_goal_with_its_horizon():
    found = goals.from_framework("Answer permit questions faster\n\nCut the backlog in half.",
                                 "Plain-language answers at any hour", recorded=[])
    assert [(c["goal"], c["horizon"], c["from"]) for c in found] == [
        ("Answer permit questions faster", goals.WITHIN_A_YEAR, "Framework 11.1a"),
        ("Cut the backlog in half.", goals.WITHIN_A_YEAR, "Framework 11.1a"),
        ("Plain-language answers at any hour", goals.WITHIN_FIVE, "Framework 11.1b"),
    ]


def test_a_goal_already_written_down_is_not_offered_again():
    found = goals.from_framework("Cut the backlog in half", "",
                                 recorded=[{"goal": "Cut the backlog in half."}])
    assert found == []


def test_nothing_and_none_are_not_goals():
    assert goals.from_framework("None", "n/a", recorded=[]) == []


def test_the_document_states_them_under_purpose():
    answers = {"why.vision_year": {"value": "Answer permit questions faster.\nCut the backlog."},
               "why.vision_five": {"value": "Plain-language answers at any hour"}}
    year = prose._clause_for("why.vision_year", answers)
    five = prose._clause_for("why.vision_five", answers)
    assert year.text.endswith("Answer permit questions faster; Cut the backlog.")
    assert ".." not in year.text and five.text.endswith("at any hour.")
    purpose = next(s for s in prose.SECTIONS if s["title"] == "Purpose")
    assert purpose["keys"][1:3] == ["why.vision_year", "why.vision_five"]


def test_saying_nothing_prints_nothing():
    assert prose._clause_for("why.vision_year", {"why.vision_year": {"value": "None"}}) is None
