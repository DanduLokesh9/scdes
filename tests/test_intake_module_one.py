"""An organization's own uploaded policies, matched to Module One's questions.

The upload panel says every question is checked against what was uploaded.
Until this, that was not true — the matching was attached only to the
retired Discretion Register. What these pin:

* a passage is shown beside a question only where it shares enough of that
  question's own specific words — never on the generic governance words
  every policy contains ("tool", "information", "framework");
* something is offered to fill in only where it is clear, and on the
  option's own words, never the question's;
* nothing is answered on anybody's behalf — using a passage is a choice, and
  the answer records which document it came from;
* a named source has to be a passage this organization actually uploaded.
"""

from __future__ import annotations

import base64

import pytest

from app import intake, module_one, server, versions
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")

CONFLICT = {"key": "why.conflict", "kind": "single",
            "prompt": "When your rules and a state or federal rule disagree, "
                      "which one wins?", "help": "", "above": "",
            "options": [{"value": "stricter", "label": "Whichever is stricter"},
                        {"value": "external", "label": "The state or federal rule"},
                        {"value": "ours", "label": "This framework"}]}


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "STORE", tmp_path / "intake")
    monkeypatch.setattr(intake, "INDEX", tmp_path / "intake" / "index.json")
    monkeypatch.setattr(versions, "VERSIONS_FILE", tmp_path / "v.json")
    yield


def _upload(body: str, name: str = "policy.txt") -> None:
    assert intake.upload(name, _b64(body), OT, kind="Acceptable use")["ok"]


def _as_dict(key: str) -> dict:
    q = module_one.by_key(key)
    return {"key": q.key, "prompt": q.prompt, "help": q.help or "",
            "above": getattr(q, "above", "") or "", "kind": q.kind,
            "options": [{"value": o.value, "label": o.label}
                        for o in (q.options or [])]}


# ------------------------------------------------------------ matching

def test_nothing_is_shown_without_documents() -> None:
    assert intake.evidence_for_question(CONFLICT) == []


def test_generic_governance_words_never_make_a_match() -> None:
    """ "Chief Information Officer" once matched the question about what
    information must never go into a tool."""
    _upload("Determination of scope. The Chief Information Officer determines "
            "whether a given tool falls within scope, subject to review by the "
            "County Administrator.")
    assert intake.evidence_for_question(_as_dict("data.never")) == []
    assert intake.evidence_for_question(_as_dict("proc.reuse")) == []


def test_a_passage_on_the_question_is_shown_with_its_file() -> None:
    _upload("Conflicting requirements. Where state or federal rules conflict "
            "with this policy, whichever is stricter controls.")
    hits = intake.evidence_for_question(CONFLICT)
    assert hits and hits[0]["file"] == "policy.txt"
    assert "stricter controls" in hits[0]["quote"]
    assert {"state", "federal"} <= set(hits[0]["matched"])


def test_an_option_is_offered_on_its_own_words() -> None:
    _upload("Conflicting requirements. Where state or federal rules conflict "
            "with this policy, whichever is stricter controls.")
    hit = intake.evidence_for_question(CONFLICT)[0]
    assert hit["suggest"] == {"value": "stricter",
                              "labels": ["Whichever is stricter"]}


def test_the_questions_own_words_never_pick_an_option() -> None:
    """ "The state or federal rule" once won only because the question
    itself says "state or federal"."""
    _upload("Conflicting requirements. Where this policy differs from state "
            "or federal policy on procurement, the Chief Procurement Officer "
            "reports the difference.")
    for hit in intake.evidence_for_question(CONFLICT):
        assert not hit["suggest"] or hit["suggest"]["value"] != "external"


def test_stringent_and_stricter_are_the_same_word() -> None:
    assert intake._norm("stringent") == intake._norm("stricter") == "strict"


def test_case_by_case_is_not_found_in_every_use_case() -> None:
    q = {"key": "x", "kind": "single", "prompt": "How are exceptions to the "
         "incident lookback decided after incidents?", "help": "", "above": "",
         "options": [{"value": "yes", "label": "Always"},
                     {"value": "case", "label": "Case by case"}]}
    _upload("Every incident use case is recorded, and the lookback after "
            "incidents is decided by the council for each use case.")
    for hit in intake.evidence_for_question(q):
        assert not hit["suggest"]


def test_multiple_choice_needs_two_of_an_options_own_words() -> None:
    q = _as_dict("data.never")
    _upload("Never enter information into a general-purpose tool if it is "
            "medical or health information, or student records of any kind. "
            "The Chief Information Officer keeps the list.")
    hit = intake.evidence_for_question(q)[0]
    assert hit["suggest"], hit
    assert "medical" in hit["suggest"]["value"]
    assert "tax" not in hit["suggest"]["value"]


def test_a_text_question_is_offered_the_passage() -> None:
    _upload("Final action. A final action is any decision that grants, "
            "denies or conditions a permit, license, benefit or service for a "
            "member of the public, and every final action is taken by a named "
            "employee.")
    hits = intake.evidence_for_question(_as_dict("floor.final_action"))
    assert hits and hits[0]["suggest"]
    assert hits[0]["suggest"]["value"].startswith("Final action.")


def test_a_grid_is_never_filled_from_prose() -> None:
    q = {**CONFLICT, "kind": "matrix"}
    _upload("Where state or federal rules conflict with this policy, "
            "whichever is stricter controls.")
    assert all(h["suggest"] is None for h in intake.evidence_for_question(q))


# ------------------------------------------------------------ the server

def test_a_step_carries_what_the_documents_say() -> None:
    _upload("Conflicting requirements. Where state or federal rules conflict "
            "with this policy, whichever is stricter controls.")
    step = module_one.by_key("why.conflict").number.split(".")[0]
    number = next(s.number for s in module_one.STEPS
                  if any(q.key == "why.conflict" for q in s.questions)) \
        if hasattr(module_one, "STEPS") else step
    payload = server.api_module(OT, {}, {"step": [number]})
    q = next(q for q in payload["questions"] if q["key"] == "why.conflict")
    assert q["evidence"] and q["evidence"][0]["file"] == "policy.txt"


def test_using_a_passage_records_its_source_and_answers_nothing_else() -> None:
    _upload("Conflicting requirements. Where state or federal rules conflict "
            "with this policy, whichever is stricter controls.")
    hit = intake.evidence_for_question(CONFLICT)[0]
    saved = server.api_version_answer(OT, {
        "key": "why.conflict", "value": "stricter",
        "from_document": {"file": hit["file"], "paragraph": hit["paragraph"]}}, {})
    assert saved["ok"]
    # The store wraps every answer with who gave it and when.
    stored = versions.working()["why.conflict"]["value"]
    assert stored["value"] == "stricter"
    assert stored["from_document"]["file"] == "policy.txt"
    assert "stricter controls" in stored["from_document"]["quote"]
    assert module_one.value_of(versions.working(), "why.conflict")[0] == "stricter"
    # Nothing else was answered on the way.
    assert set(versions.working()) == {"why.conflict"}


def test_a_source_that_was_never_uploaded_is_not_recorded() -> None:
    saved = server.api_version_answer(OT, {
        "key": "why.conflict", "value": "stricter",
        "from_document": {"file": "../../etc/passwd", "paragraph": 0}}, {})
    assert saved["ok"]
    assert versions.working()["why.conflict"]["value"] == "stricter"


def test_the_upload_panel_says_what_the_app_does() -> None:
    said = intake.summary()
    assert "Nothing is answered on your behalf" in said["how"]
    assert "beside that question" in said["why"]
