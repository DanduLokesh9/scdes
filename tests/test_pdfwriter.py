"""The standard-library PDF writer behind the framework answers report."""

from __future__ import annotations

import re

from app import pdfwriter


def _valid(pdf: bytes) -> None:
    xref = int(re.search(rb"startxref\n(\d+)", pdf).group(1))
    assert pdf[xref:xref + 4] == b"xref"
    for i, off in enumerate(re.findall(rb"(\d{10}) 00000 n", pdf[xref:]), start=1):
        assert pdf[int(off):].startswith(f"{i} 0 obj".encode()), i
    for m in re.finditer(rb"<< /Length (\d+) >>\nstream\n(.*?)\nendstream", pdf, re.S):
        assert len(m.group(2)) == int(m.group(1))


def test_a_document_is_well_formed_and_titled():
    doc = pdfwriter.Document("Framework answers — City of X", footer_note="Confidential")
    doc.text("Hello (world) \\ back", size=12, bold=True)
    pdf = doc.build()
    _valid(pdf)
    assert b"/Title (Framework answers \x97 City of X)" in pdf      # cp1252 em dash
    assert b"/Lang (en-US)" in pdf
    assert b"Hello \\(world\\) \\\\ back" in pdf                    # escaped, not broken
    assert b"Page 1 of 1" in pdf


def test_long_text_wraps_and_paginates():
    doc = pdfwriter.Document("Long")
    for n in range(120):
        doc.text(f"Question {n} " + "word " * 40)
    pdf = doc.build()
    _valid(pdf)
    pages = pdf.count(b"/Type /Page ")
    assert pages > 3 and f"Page {pages} of {pages}".encode() in pdf
    widest = max(pdfwriter.text_width(s.decode("cp1252"), 10)
                 for s in re.findall(rb"\((Question.*?)\) Tj", pdf))
    assert widest <= pdfwriter.PAGE_W - 2 * pdfwriter.MARGIN


def test_characters_outside_the_encoding_do_not_break_it():
    doc = pdfwriter.Document("Unicode")
    doc.text("Smart “quotes” — and an emoji 🙂 and 中文")
    _valid(doc.build())
