"""Print one section of a document, so its register can be judged.

The client's ask is that the generated framework "read like a formal document
which could be handed to someone and signed off on". Whether it does is a
question about sentences, not about structure — so this prints a section of
the generated document beside the corresponding section of the reference, and
the answer is whichever one a reader cannot tell apart.

Usage:  python -m tools._read_section <path> "<heading starts with>" [lines]
"""

from __future__ import annotations

import sys
from pathlib import Path

import docx


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    path, wanted = Path(argv[0]), argv[1]
    lines = int(argv[2]) if len(argv) > 2 else 14

    document = docx.Document(str(path))
    paras = [(p.style.name, " ".join(p.text.split()))
             for p in document.paragraphs]
    # The heading, not the contents line that carries the same words. Falls
    # back to any match, for documents whose headings are not styled as such.
    start = next((i for i, (style, text) in enumerate(paras)
                  if text.startswith(wanted) and style.startswith("Heading")),
                 None)
    if start is None:
        start = next((i for i, (_, text) in enumerate(paras)
                      if text.startswith(wanted)), None)
    if start is None:
        print(f"no heading starting {wanted!r} in {path.name}")
        return 1

    print(f"=== {path.name} — {wanted!r}\n")
    shown = 0
    for style, text in paras[start:]:
        if not text:
            continue
        print(f"[{style[:9]:9}] {text[:160]}")
        shown += 1
        if shown >= lines:
            break
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
