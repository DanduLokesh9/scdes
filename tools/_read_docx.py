"""Print a .docx as text, so a spec can be read without Word.

    python -m tools._read_docx <path> [first] [last]
"""

from __future__ import annotations

import sys
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph


def blocks(doc: Document):
    """Paragraphs and tables in the order they appear on the page."""
    body = doc.element.body
    for child in body.iterchildren():
        tag = child.tag.split("}")[-1]
        if tag == "p":
            yield Paragraph(child, doc)
        elif tag == "tbl":
            yield Table(child, doc)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    doc = Document(Path(argv[0]))
    first = int(argv[1]) if len(argv) > 1 else 0
    last = int(argv[2]) if len(argv) > 2 else 10 ** 9

    line = 0
    for block in blocks(doc):
        if isinstance(block, Table):
            for row in block.rows:
                line += 1
                if first <= line <= last:
                    cells = [" ".join(c.text.split()) for c in row.cells]
                    print(f"{line:>5} | " + " | ".join(cells))
            continue
        text = " ".join(block.text.split())
        if not text:
            continue
        line += 1
        if first <= line <= last:
            style = (block.style.name if block.style else "") or ""
            mark = f"[{style}] " if style.lower().startswith("heading") else ""
            print(f"{line:>5} {mark}{text}")
    print(f"\n({line} lines total)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
