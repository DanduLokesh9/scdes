"""Chunk the narrative governance documents on heading boundaries.

The Framework and Operations Manual are cleanly styled with numbered headings
(Heading1/2/3), so a chunk boundary *is* a citation boundary. Every chunk knows
its own section number, which is what lets an answer say

    SCDES AI Operations Manual §22.4 (Level 2 Procedure)

rather than guessing at a page or a paragraph.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field as dc_field, asdict
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

# Documents whose text the app quotes. Supporting docs are context, not authority,
# so they are indexed but marked non-authoritative.
#: Which folders hold documents of authority, as opposed to context. This is a
#: property of the corpus layout, not of any particular agency — a document is
#: authoritative because of where the agency filed it, and `profile.py` refines
#: the classification afterwards by reading what each document says it is.
AUTHORITATIVE_DIRS = {"framework", "manual", "charter", "appendices"}


def _label_for(path: Path) -> tuple[str, bool]:
    """Human label and authority, derived from the file rather than a lookup."""
    stem = path.stem.replace("_", " ").strip()
    stem = re.sub(r"\s+", " ", stem)
    stem = re.sub(r"\b(Final|Draft|v\d+(\.\d+)?|SIGNED|\d{4}-\d{2}-\d{2})\b",
                  "", stem, flags=re.I).strip(" -–—")
    m = re.match(r"Appendix\s+([A-Z0-9]+)\s+(.*)", stem, re.I)
    if m:
        stem = f"Appendix {m.group(1).upper()} — {m.group(2)}"
    return stem, path.parent.name.lower() in AUTHORITATIVE_DIRS

SEARCH_DIRS = ["framework", "manual", "appendices", "charter", "supporting",
               "worked_example"]

# "6.2 Classification Thresholds"  ·  "3.2A - Tier A Workflow"  ·  "1A. Relationship..."
_HEADING_NUM = re.compile(
    r"^(?P<num>\d+[A-Z]?(?:\.\d+[A-Z]?)*)\s*[-–—.:]?\s+(?P<title>.+)$"
)
_SECTION_WORD = re.compile(r"^(section|article|part)\s+(?P<num>[\dIVXLC]+[A-Z]?)",
                           re.I)


def _norm(text: str) -> str:
    return re.sub(r"[ \t]+", " ", (text or "").replace("\xa0", " ")).strip()


@dataclass
class Chunk:
    doc_id: str
    doc_label: str
    authoritative: bool
    section: str          # "22.4" — empty for unnumbered headings
    heading: str          # "Level 2 Procedure"
    level: int
    breadcrumb: str       # "§22 Incident Response Procedure › §22.4 Level 2 Procedure"
    text: str
    order: int

    @property
    def citation(self) -> str:
        if self.section:
            return f"{self.doc_label} §{self.section} ({self.heading})"
        if self.heading:
            return f"{self.doc_label} — {self.heading}"
        return self.doc_label

    @property
    def anchor(self) -> str:
        return f"{self.doc_id}#{self.section or self.order}"


@dataclass
class DocumentIndex:
    doc_id: str
    doc_label: str
    authoritative: bool
    source_path: str
    chunks: list[Chunk] = dc_field(default_factory=list)


def _iter_blocks(doc: Document):
    """Yield paragraphs and tables in true document order."""
    body = doc.element.body
    for child in body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, doc)
        elif child.tag == qn("w:tbl"):
            yield Table(child, doc)


def _heading_level(para: Paragraph) -> int:
    """0 if the paragraph is body text, else the heading depth (1-based)."""
    style = (para.style.name or "") if para.style is not None else ""
    m = re.match(r"heading\s*(\d+)", style, re.I)
    if m:
        return int(m.group(1))
    if style.lower() in ("title", "subtitle"):
        return 1
    return 0


def _split_heading(text: str) -> tuple[str, str]:
    """Return (section_number, title) for a heading line."""
    m = _HEADING_NUM.match(text)
    if m:
        return m.group("num"), _norm(m.group("title")).rstrip(".")
    m = _SECTION_WORD.match(text)
    if m:
        rest = text[m.end():].strip(" -–—.:")
        return m.group("num"), _norm(rest) or text
    return "", text.rstrip(".")


def _table_text(table: Table) -> str:
    lines = []
    for row in table.rows:
        cells = [_norm(c.text) for c in row.cells]
        # A merged row repeats the same text across cells; collapse it.
        deduped = []
        for c in cells:
            if not deduped or deduped[-1] != c:
                deduped.append(c)
        line = " | ".join(c for c in deduped if c)
        if line:
            lines.append(line)
    return "\n".join(lines)


def parse_document(path: Path) -> DocumentIndex:
    label, authoritative = _label_for(path)
    doc = Document(str(path))
    index = DocumentIndex(
        doc_id=path.stem, doc_label=label, authoritative=authoritative,
        source_path=str(path.relative_to(CORPUS.parent)),
    )

    stack: list[tuple[int, str, str]] = []   # (level, section, heading)
    cur_section = cur_heading = ""
    cur_level = 0
    buffer: list[str] = []
    order = 0

    def flush() -> None:
        nonlocal buffer, order
        body = "\n".join(b for b in buffer if b).strip()
        if not (body or cur_heading):
            buffer = []
            return
        crumbs = [f"§{s} {h}" if s else h for _, s, h in stack]
        index.chunks.append(Chunk(
            doc_id=index.doc_id, doc_label=label, authoritative=authoritative,
            section=cur_section, heading=cur_heading, level=cur_level,
            breadcrumb=" › ".join(crumbs), text=body, order=order,
        ))
        order += 1
        buffer = []

    for block in _iter_blocks(doc):
        if isinstance(block, Table):
            text = _table_text(block)
            if text:
                buffer.append(text)
            continue

        text = _norm(block.text)
        level = _heading_level(block)

        if level and text:
            flush()
            section, heading = _split_heading(text)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, section, heading))
            cur_section, cur_heading, cur_level = section, heading, level
            continue

        if text:
            buffer.append(text)

    flush()
    return index


def parse_all(authoritative_only: bool = False) -> list[DocumentIndex]:
    indices: list[DocumentIndex] = []
    for folder in SEARCH_DIRS:
        directory = CORPUS / folder
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.docx")):
            if path.name.startswith("~$"):
                continue
            idx = parse_document(path)
            if authoritative_only and not idx.authoritative:
                continue
            indices.append(idx)
    return indices


def report(indices: list[DocumentIndex]) -> str:
    lines = ["DOCUMENT SECTIONISER COVERAGE", "=" * 78]
    lines.append(f"{'Document':<44}{'Chunks':>7}{'Numbered':>10}{'Words':>9}")
    lines.append("-" * 78)
    for idx in indices:
        numbered = sum(1 for c in idx.chunks if c.section)
        words = sum(len(c.text.split()) for c in idx.chunks)
        flag = "" if idx.authoritative else "  (context)"
        lines.append(f"{idx.doc_label[:42]:<44}{len(idx.chunks):>7}"
                     f"{numbered:>10}{words:>9}{flag}")
    lines.append("-" * 78)
    lines.append(f"{'TOTAL':<44}{sum(len(i.chunks) for i in indices):>7}"
                 f"{sum(1 for i in indices for c in i.chunks if c.section):>10}"
                 f"{sum(len(c.text.split()) for i in indices for c in i.chunks):>9}")
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    indices = parse_all()
    if not indices:
        print(f"No .docx found under {CORPUS}", file=sys.stderr)
        return 1

    if "--json" in argv:
        out = CORPUS / "index" / "document_chunks.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps([asdict(i) for i in indices], indent=2), encoding="utf-8"
        )
        print(f"wrote {out}")
        return 0

    if "--sections" in argv:
        for idx in indices:
            if not idx.authoritative:
                continue
            print(f"\n{idx.doc_label}")
            for c in idx.chunks:
                if c.section:
                    print(f"   §{c.section:<8} {c.heading[:60]:<62}"
                          f"{len(c.text.split()):>5}w")
        return 0

    if "--cite" in argv:
        needle = argv[argv.index("--cite") + 1].lower()
        for idx in indices:
            for c in idx.chunks:
                if needle in c.text.lower() or needle in c.heading.lower():
                    print(f"{c.citation}\n    {c.text[:220]}...\n")
        return 0

    print(report(indices))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
