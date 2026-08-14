"""The appendices must parse completely — a row the parser cannot classify is a
build failure, not something to skip silently.

These tests also pin the governance values the risk engine depends on, so if a
future edit to Appendix B changes a weight or a threshold, the suite says so.
"""

from __future__ import annotations

import pytest

from app.ingest_docx import parse_all as parse_docs
from app.ingest_xlsx import APPENDIX_DIR, parse_all as parse_appendices

EXPECTED_LETTERS = set("ABCDEFGHIJKLM")   # N is a .docx, covered by the docx suite


@pytest.fixture(scope="module")
def schemas():
    return parse_appendices()


def test_every_appendix_workbook_is_present(schemas):
    assert {s.letter for s in schemas} == EXPECTED_LETTERS


def test_no_row_is_left_unclassified(schemas):
    offenders = {
        s.letter: [u for sheet in s.sheets for u in sheet.unclassified]
        for s in schemas if s.unclassified_count
    }
    assert not offenders, (
        "the parser could not classify these rows:\n" +
        "\n".join(f"  {letter}: {rows[:3]}" for letter, rows in offenders.items())
    )


def test_every_appendix_yields_editable_fields(schemas):
    empty = [s.letter for s in schemas if s.field_count == 0]
    assert not empty, f"no fields parsed for appendix/appendices {empty}"


def test_fields_carry_a_writeback_address(schemas):
    for s in schemas:
        for sheet in s.sheets:
            for block in sheet.blocks:
                for field in block.fields:
                    assert field.value_cell, (
                        f"{s.letter}/{sheet.name}: field {field.label!r} has no "
                        f"cell to write back to"
                    )
                    assert field.sheet == sheet.name


def test_control_types_come_from_the_templates(schemas):
    """Appendix G declares its own options in the hint column."""
    g = next(s for s in schemas if s.letter == "G")
    selects = [f for sheet in g.sheets for b in sheet.blocks
               for f in b.fields if f.control == "select"]
    assert selects, "Appendix G should yield select controls from its [Select: ...] hints"
    bureau = next((f for f in selects if "bureau" in f.label.lower()), None)
    assert bureau is not None
    assert any("Water" in opt for opt in bureau.options), bureau.options


# ------------------------------------------------- the adopted risk parameters

EXPECTED_WEIGHTS = {
    "Regulatory Impact": 1.5,
    "Public-Facing Exposure": 1.0,
    "Data Sensitivity": 1.5,
    "Reversibility": 1.0,
    "Community Impact": 1.5,
    "Federal Program Nexus": 1.5,
}


@pytest.fixture(scope="module")
def risk_rows(schemas):
    b = next(s for s in schemas if s.letter == "B")
    block = next(bl for sheet in b.sheets for bl in sheet.blocks
                 if bl.kind == "param_table")
    return block.sample_rows


def test_appendix_b_weights_match_the_adopted_matrix(risk_rows):
    found = {
        row["Risk Factor"]: float(row["Weight"])
        for row in risk_rows
        if row.get("Risk Factor") and row.get("Weight")
    }
    assert found == EXPECTED_WEIGHTS


def test_appendix_b_declares_its_bands(risk_rows):
    labels = " ".join(
        (row.get("#") or "") + " " + (row.get("Risk Factor") or "")
        for row in risk_rows
    ).upper()
    for band in ("LOW RISK", "MODERATE RISK", "HIGH RISK"):
        assert band in labels, f"{band} band missing from Appendix B"


def test_max_possible_score_is_24(risk_rows):
    blob = " ".join(v for row in risk_rows for v in row.values() if v)
    assert "Max possible: 24" in blob


# ------------------------------------------------------------ narrative corpus

@pytest.fixture(scope="module")
def documents():
    return parse_docs()


def test_authoritative_documents_are_indexed(documents):
    labels = {d.doc_label for d in documents if d.authoritative}
    assert "SCDES AI Governance Framework" in labels
    assert "SCDES AI Operations Manual" in labels
    assert "Appendix N — Council Operating Procedures" in labels


def test_manual_sections_are_numbered_for_citation(documents):
    manual = next(d for d in documents if d.doc_label == "SCDES AI Operations Manual")
    numbered = [c for c in manual.chunks if c.section]
    assert len(numbered) > 50, "expected the Manual to chunk into numbered sections"

    incident = next((c for c in numbered if c.section == "22.4"), None)
    assert incident is not None, "Manual §22.4 (Level 2 Procedure) not found"
    assert incident.citation == "SCDES AI Operations Manual §22.4 (Level 2 Procedure)"


def test_every_chunk_can_cite_itself(documents):
    for doc in documents:
        for chunk in doc.chunks:
            assert chunk.citation.strip()
            assert doc.doc_label in chunk.citation


def test_corpus_directory_holds_the_thirteen_workbooks():
    workbooks = sorted(APPENDIX_DIR.glob("Appendix_*.xlsx"))
    assert len(workbooks) == 13
