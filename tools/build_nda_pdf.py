"""Turn the client's NDA .docx into the PDF the platform shows before entry.

Run offline, and the PDF is committed. That is deliberate: `requirements.txt`
has three runtime dependencies and reportlab is not one of them, so generating
this on the server would mean adding a library to a production deployment for a
document that changes once a year. The build tool carries the dependency; the
application only serves a file.

It also means the served PDF is a fixed artefact with a stable hash, which
matters more here than convenience. `app/nda.py` records the hash of what a
person actually accepted, so "which version did they agree to" is answerable
years later. A PDF re-rendered per request would hash differently every time.

    pip install reportlab
    python -m tools.build_nda_pdf

Source:  C:/Users/dandu/Downloads/IIA_GAIUS_OneWay_NDA.docx
Output:  app/web/assets/legal/IIA_GAIUS_OneWay_NDA.pdf
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import docx
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.platypus import (BaseDocTemplate, Frame, PageTemplate,
                                Paragraph, Spacer)

SOURCE = Path(r"C:\Users\dandu\Downloads\IIA_GAIUS_OneWay_NDA.docx")
OUT = (Path(__file__).resolve().parent.parent
       / "app" / "web" / "assets" / "legal" / "IIA_GAIUS_OneWay_NDA.pdf")

INK = colors.HexColor("#0b2530")
ACCENT = colors.HexColor("#1c5f7a")
MUTED = colors.HexColor("#4f6167")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()["BodyText"]
    def s(name, **kw):
        return ParagraphStyle(name, parent=base, **kw)
    return {
        "org": s("org", fontName="Helvetica-Bold", fontSize=9.5, leading=13,
                 textColor=ACCENT, spaceAfter=2),
        "title": s("title", fontName="Helvetica-Bold", fontSize=15, leading=19,
                   textColor=INK, spaceBefore=6, spaceAfter=2),
        "subtitle": s("subtitle", fontName="Helvetica", fontSize=10.5,
                      leading=14, textColor=MUTED, spaceAfter=14),
        "heading": s("heading", fontName="Helvetica-Bold", fontSize=10.5,
                     leading=14, textColor=INK, spaceBefore=13, spaceAfter=4),
        "body": s("body", fontName="Helvetica", fontSize=9.5, leading=14,
                  textColor=INK, alignment=TA_JUSTIFY, spaceAfter=7),
        # Sub-clauses are indented so (a)…(g) read as a list rather than as
        # eight indistinguishable paragraphs.
        "clause": s("clause", fontName="Helvetica", fontSize=9.5, leading=14,
                    textColor=INK, alignment=TA_JUSTIFY, leftIndent=18,
                    spaceAfter=6),
        "emphatic": s("emphatic", fontName="Helvetica-Bold", fontSize=9.5,
                      leading=14, textColor=INK, alignment=TA_JUSTIFY,
                      spaceBefore=8, spaceAfter=7),
    }


#: A numbered section: "1.  DEFINITIONS", "12.  GENERAL PROVISIONS".
HEADING = re.compile(r"^\d+\.\s")
#: A lettered sub-clause: "(a)\tholds all Confidential Information…".
CLAUSE = re.compile(r"^\([a-z]\)\s")
#: A recital: "(A)\tIIA is the developer…". Capitals, so distinct from clauses.
RECITAL = re.compile(r"^\([A-Z]\)\s")


#: Corrections applied to the source .docx on the client's instruction.
#:
#: The subtitle read "HazMit — Confidential Product Materials", carried over
#: from IIA's HazMit NDA, while the body of the same document defines the
#: Product as GoverningAI.US. The client asked for it changed.
#:
#: Kept as an explicit, listed substitution rather than a find-and-replace over
#: the whole text. This is a legal instrument: a blind regex could silently
#: alter a clause nobody looked at, and the value of a list is that every edit
#: to the document is visible here, in one place, with the reason attached.
#:
#: Casing matches the body — GoverningAI.US, as paragraph 6 already writes it —
#: rather than the lower-case ".us" of the domain, so the document does not
#: name its own product two ways.
SUBSTITUTIONS: list[tuple[str, str]] = [
    ("HazMit — Confidential Product Materials",
     "GoverningAI.US — Confidential Product Materials"),
]


def _correct(text: str) -> str:
    for old, new in SUBSTITUTIONS:
        text = text.replace(old, new)
    return text


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;"))


def _classify(text: str, index: int) -> str:
    if index == 0:
        return "org"
    if index == 1:
        return "title"
    if index == 2 or index == 3:
        return "subtitle"
    if HEADING.match(text):
        return "heading"
    if CLAUSE.match(text) or RECITAL.match(text):
        return "clause"
    # Long stretches of capitals are the emphatic passages the document uses
    # for the warranty disclaimer and the acceptance statement.
    letters = [c for c in text if c.isalpha()]
    if letters and sum(c.isupper() for c in letters) / len(letters) > 0.85:
        return "emphatic"
    return "body"


def _chrome(canvas, doc) -> None:
    """Footer on every page: who it belongs to, and where you are in it."""
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(MUTED)
    canvas.drawString(0.9 * inch, 0.55 * inch,
                      "Innovative Infrastructure Advising, LLC  ·  iiac.ai  ·  "
                      "Charleston, SC")
    canvas.drawRightString(LETTER[0] - 0.9 * inch, 0.55 * inch,
                           f"One-Way NDA  ·  page {canvas.getPageNumber()}")
    canvas.setStrokeColor(colors.HexColor("#dde5e8"))
    canvas.setLineWidth(0.5)
    canvas.line(0.9 * inch, 0.72 * inch, LETTER[0] - 0.9 * inch, 0.72 * inch)
    canvas.restoreState()


def build() -> Path:
    source = docx.Document(str(SOURCE))
    styles = _styles()

    flow = []
    for i, para in enumerate(source.paragraphs):
        text = para.text.strip()
        if not text:
            continue
        text = _correct(text)
        kind = _classify(text, i)
        # Tabs after "(a)" render as a literal gap in reportlab; a space reads
        # better and the indent already carries the structure.
        text = _escape(text.replace("\t", "  "))
        flow.append(Paragraph(text, styles[kind]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    doc = BaseDocTemplate(
        str(OUT), pagesize=LETTER,
        leftMargin=0.9 * inch, rightMargin=0.9 * inch,
        topMargin=0.85 * inch, bottomMargin=0.95 * inch,
        title="One-Way Non-Disclosure Agreement",
        author="Innovative Infrastructure Advising, LLC",
        subject="GoverningAI.US — Confidential Product Materials",
    )
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height,
                  id="body")
    doc.addPageTemplates([PageTemplate(id="all", frames=[frame],
                                       onPage=_chrome)])
    doc.build(flow)

    # Assert the corrections actually landed. A substitution that silently
    # fails to match — a changed dash, a stray space — would republish the
    # document with the very text it was meant to remove, and nothing further
    # down the pipeline would notice.
    rendered = " ".join(_correct(p.text.strip())
                        for p in source.paragraphs if p.text.strip())
    for old_text, _ in SUBSTITUTIONS:
        head = old_text.split()[0]
        if head.lower() in rendered.lower():
            raise SystemExit(
                f"refusing to write: {head!r} still appears after substitution "
                f"— the pattern no longer matches the source document")

    digest = hashlib.sha256(OUT.read_bytes()).hexdigest()
    print(f"wrote {OUT}")
    for old_text, new_text in SUBSTITUTIONS:
        print(f"  corrected: {old_text!r}\n          -> {new_text!r}")
    print(f"  {OUT.stat().st_size / 1024:.1f} KB")
    print(f"  sha256 {digest}")
    print(f"\nRecord this hash in app/nda.py so an acceptance names the exact")
    print(f"version that was agreed to.")
    return OUT


if __name__ == "__main__":
    build()
