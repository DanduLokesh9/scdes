"""Look at what actually came out of the printer.

A PDF that is the right size and the wrong shape — a heading orphaned at the
bottom of a page, a screenshot broken across two, a page of nothing but a
caption — is the kind of fault you only find by opening it. This prints the
page count, how many images landed on each page, and the first line of text,
which is enough to catch all three from here.

Usage:  python -m tools._pdf_check
"""

from __future__ import annotations

import pathlib
import sys

import pypdf

DOCS = pathlib.Path(__file__).resolve().parent.parent / "docs"


def main() -> int:
    found = sorted(DOCS.glob("*.pdf"))
    if not found:
        print("No PDFs in docs/ — run tools\\make_pdfs.ps1 first.")
        return 1

    for path in found:
        reader = pypdf.PdfReader(str(path))
        size = path.stat().st_size / 1024
        print(f"\n=== {path.name}")
        print(f"    {len(reader.pages)} pages · {size:,.0f} KB")
        for number, page in enumerate(reader.pages, 1):
            text = " ".join((page.extract_text() or "").split())
            try:
                images = len(page.images)
            except Exception:                             # noqa: BLE001
                images = -1
            flag = ""
            if len(text) < 120 and images == 0:
                flag = "  <-- nearly empty"
            print(f"    p{number:<3} {images} img  {len(text):>5} chars  "
                  f"{text[:82]}{flag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
