"""Uploading the agency's existing policies, and matching them to questions.

The client's instruction was that uploads be "FULLY incorporated". This
implements the evidence reading of that — find the passage, quote it, name the
file, let a person confirm — rather than the absorbed reading, and the tests
that matter are the ones holding that line: nothing is answered automatically,
and a weak match is withheld rather than offered.
"""

from __future__ import annotations

import base64

import pytest

from app import intake
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")
OPERATOR = Actor("liz.operator", "Operator", Role.OPERATOR)

POLICY = """Anderson County Acceptable Use Policy

Human review of decisions. No automated or artificial intelligence system may
issue a final determination affecting a member of the public, a regulated
entity, or a County employee. A County employee with delegated authority must
review and be accountable for any such decision.

Conflicting requirements. Where this policy imposes requirements more stringent
than state or federal policy, the more stringent standard controls.

Determination of scope. The Chief Information Officer determines whether a given
tool falls within scope, subject to review by the County Administrator.
"""


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(intake, "STORE", tmp_path / "intake")
    monkeypatch.setattr(intake, "INDEX", tmp_path / "intake" / "index.json")
    yield


def _upload(name="policy.txt", body=POLICY, actor=OT, kind="Acceptable use"):
    return intake.upload(name, _b64(body), actor, kind=kind)


# ------------------------------------------------------------------ uploading

def test_a_policy_is_read_and_indexed() -> None:
    result = _upload()
    assert result["ok"], result.get("error")
    assert result["readable"]
    assert result["paragraphs"] >= 3
    assert intake.summary()["count"] == 1


def test_an_unreadable_type_is_refused_by_name() -> None:
    """"Invalid file" helps nobody; the message says what would work."""
    result = _upload("scan.tiff")
    assert not result["ok"]
    assert ".tiff" in result["error"]
    assert "Word document" in result["error"]


def test_an_empty_or_oversized_upload_is_refused() -> None:
    assert not intake.upload("empty.txt", _b64(""), OT)["ok"]
    huge = "word " * 3_000_000
    assert not intake.upload("huge.txt", _b64(huge), OT)["ok"]


def test_a_corrupt_payload_is_refused_rather_than_stored() -> None:
    result = intake.upload("policy.txt", "not base64 at all!!", OT)
    assert not result["ok"]
    assert intake.summary()["count"] == 0


def test_a_filename_cannot_escape_the_store() -> None:
    """The one input here that is a path. It is not treated as one."""
    result = _upload("../../etc/passwd.txt")
    assert result["ok"]
    stored = [d["file"] for d in intake.documents()]
    assert stored == ["passwd.txt"]
    assert not (intake.STORE / ".." / ".." / "etc").exists()


def test_an_operator_cannot_upload() -> None:
    assert not _upload(actor=OPERATOR)["ok"]


def test_re_uploading_replaces_rather_than_duplicates() -> None:
    _upload()
    _upload()
    assert intake.summary()["count"] == 1


def test_removing_takes_the_evidence_with_it() -> None:
    _upload()
    assert intake.evidence_for("more stringent standard controls")
    intake.remove("policy.txt", OT)
    assert intake.summary()["count"] == 0
    assert intake.evidence_for("more stringent standard controls") == []


# ------------------------------------------------------------------- matching

def test_a_clause_is_matched_to_the_question_it_answers() -> None:
    _upload()
    hits = intake.evidence_for(
        "When your rules and state or federal rules conflict, which controls?")
    assert hits, "the policy says exactly this"
    assert "more stringent standard controls" in hits[0]["quote"]
    assert hits[0]["file"] == "policy.txt"
    assert hits[0]["score"] >= intake.FLOOR


def test_a_question_the_policy_does_not_answer_gets_nothing() -> None:
    """A missing suggestion costs a minute of typing. A plausible wrong one gets
    confirmed and ends up in an adopted framework."""
    _upload()
    assert intake.evidence_for(
        "What is your annual budget for cloud hosting in euros?") == []


def test_matching_reports_which_words_it_matched_on() -> None:
    """The matching is lexical and will sometimes be wrong, so it has to be
    checkable rather than merely confident."""
    _upload()
    hit = intake.evidence_for("Chief Information Officer determines scope")[0]
    assert hit["matched"]
    assert "chief" in hit["matched"] or "officer" in hit["matched"]


def test_evidence_for_a_row_uses_the_question_and_its_source() -> None:
    from app import discretion
    _upload()
    row = next(r.as_dict() for s in discretion.SECTIONS for r in s.rows
               if r.key == "conflict.rule")
    hits = intake.evidence_for_row(row)
    assert hits
    assert "stringent" in hits[0]["quote"]


def test_structural_rows_are_not_offered_evidence() -> None:
    """They ask nothing, so there is nothing for a passage to answer."""
    from app import discretion
    _upload()
    row = next(r for s in discretion.SECTIONS for r in s.rows
               if not r.configurable)
    assert row.question == ""


# ------------------------------------------------------------------- honesty

def test_nothing_is_answered_automatically() -> None:
    """The whole design. Evidence is a suggestion with a source attached; the
    working answers stay untouched until a person saves one."""
    from app import versions
    _upload()
    hits = intake.evidence_for("more stringent standard controls")
    assert hits
    assert "answer" not in hits[0], "a hit must not carry an answer"
    assert set(hits[0]) == {"file", "kind", "paragraph", "quote", "score",
                            "matched"}


def test_the_summary_says_what_uploading_does_and_does_not_do() -> None:
    info = intake.summary()
    assert "checked against" in info["why"]
    assert "Nothing is answered on your behalf" in info["how"]
    assert ".docx" in info["accepts"]


def test_a_scan_with_no_text_is_stored_but_reported_as_unread() -> None:
    """Listing it as a source that contributes nothing would be worse than
    saying plainly that nothing could be read."""
    result = intake.upload("scan.pdf", _b64("%PDF-1.4 no text here"), OT)
    assert result["ok"]
    assert result["readable"] is False
    assert "recogniz" in result["note"]
    assert intake.summary()["count"] == 0
