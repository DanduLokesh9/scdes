"""What shape is the adopted framework, as a PDF?

The client, sending both the .docx and the .pdf: "Final output/draft needs to
look like this in style, structure, and tone. FWIW PDF is better version."

So the PDF is the target. This reads it the way the docx reader reads the
Word version — page geometry, fonts actually used, the outline if it has one,
and the text of each page with its first lines — so the generator can be
built to match rather than to approximate.

Usage:  python -m tools._read_pdf_structure <path> [--pages 1-4] [--full]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pypdf


def font_names(reader: pypdf.PdfReader, upto: int = 6) -> set[str]:
    """Which fonts the document actually uses, from the resource dictionaries."""
    found: set[str] = set()
    for page in reader.pages[:upto]:
        try:
            fonts = page["/Resources"]["/Font"]
        except Exception:                                 # noqa: BLE001
            continue
        for ref in fonts.values():
            try:
                name = str(ref.get_object().get("/BaseFont", ""))
            except Exception:                             # noqa: BLE001
                continue
            if name:
                found.add(name.lstrip("/"))
    return found


def outline_of(reader: pypdf.PdfReader) -> list[str]:
    """The PDF's bookmarks, which are what a heading becomes on export."""
    out: list[str] = []

    def walk(items, depth=0):
        for item in items:
            if isinstance(item, list):
                walk(item, depth + 1)
            else:
                try:
                    out.append("  " * depth + str(item.title))
                except Exception:                         # noqa: BLE001
                    pass

    try:
        walk(reader.outline)
    except Exception:                                     # noqa: BLE001
        pass
    return out


#: A line that looks like a numbered section heading, in any of the forms the
#: reference uses: "1.", "6.1", "6A.", "6A.1".
HEADING = re.compile(r"^(\d{1,2}[A-Z]?(?:\.\d{1,2})?)\.?\s+([A-Z][^.]{2,70})$")


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 1
    path = Path(args[0])
    full = "--full" in argv

    reader = pypdf.PdfReader(str(path))
    print(f"=== {path.name}")
    print(f"    {len(reader.pages)} pages")

    box = reader.pages[0].mediabox
    print(f"    page {float(box.width) / 72:.2f} x "
          f"{float(box.height) / 72:.2f} in")
    print(f"    fonts: {sorted(font_names(reader)) or '(none read)'}")

    marks = outline_of(reader)
    print(f"    bookmarks: {len(marks)}")
    for mark in marks[:40]:
        print(f"      {mark}")

    print("\n--- headings found in the text")
    seen: list[tuple[int, str]] = []
    for number, page in enumerate(reader.pages, 1):
        for line in (page.extract_text() or "").splitlines():
            stripped = " ".join(line.split())
            match = HEADING.match(stripped)
            if match:
                seen.append((number, stripped))
    for page_no, text in seen:
        print(f"  p{page_no:<3} {text[:88]}")

    print("\n--- the first page, verbatim")
    for line in (reader.pages[0].extract_text() or "").splitlines():
        if line.strip():
            print(f"  {line.strip()[:100]}")

    if full:
        for number, page in enumerate(reader.pages, 1):
            print(f"\n--- page {number}")
            print((page.extract_text() or "").strip()[:2600])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
