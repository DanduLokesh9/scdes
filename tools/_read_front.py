"""The first and last paragraphs of a document, verbatim.

`_read_structure` prints the spine and skips whatever sits outside a heading —
which is exactly where a title block, an adoption line and a signature block
live. This shows the two ends raw.

Usage:  python -m tools._read_front <path> [count]
"""

from __future__ import annotations

import sys
from pathlib import Path

import docx


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    path = Path(argv[0])
    count = int(argv[1]) if len(argv) > 1 else 14
    document = docx.Document(str(path))
    paras = document.paragraphs

    print(f"=== {path.name}  ({len(paras)} paragraphs)\n")
    print(f"--- first {count}")
    for i, para in enumerate(paras[:count]):
        text = " ".join(para.text.split())
        bold = any(r.bold for r in para.runs if r.bold is not None)
        size = next((r.font.size.pt for r in para.runs
                     if r.font.size is not None), None)
        print(f"  {i:>3} [{para.style.name}{' b' if bold else ''}"
              f"{f' {size:.0f}pt' if size else ''}"
              f" {para.alignment}] {text[:110]}")

    print(f"\n--- last {count}")
    for i, para in enumerate(paras[-count:], len(paras) - count):
        text = " ".join(para.text.split())
        print(f"  {i:>3} [{para.style.name}] {text[:110]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
