"""Turn on "add your own" for the questions the client asked for.

Four of his tickets are the same request in four places:

    ED813720  3.1-3.2   "Add 'Other' and a fillable line."
    9B298881  5.1       "Locked in only options now. Let them add their own."
    29BBB23A  6.2b      "Provide ability to add rows."
    58AC00FF  6.6       "Self-add fields."

A one-off edit, kept because it records which questions were opened and on
whose instruction. Run once; it is a no-op afterward.
"""

from __future__ import annotations

import pathlib
import re

SOURCE = pathlib.Path(__file__).resolve().parent.parent / "app" / "module_one.py"

#: key -> the wording on the control that adds one.
WANTED = {
    "scope.covered": "Add a use of your own",
    "scope.excluded": "Add something else that should not count",
    "risk.factors": "Add a factor of your own",
    "floor.list_fields": "Add something else to record",
    "floor.data_terms": "Add a term of your own",
}


def main() -> int:
    text = SOURCE.read_text(encoding="utf-8")
    added, already, missed = [], [], []

    for key, label in WANTED.items():
        if f'key="{key}"' not in text:
            missed.append(key)
            continue
        pattern = re.compile(
            rf'(\n(\s+)key="{re.escape(key)}", number="[^"]+",[^\n]*\n)')
        found = pattern.search(text)
        if not found:
            missed.append(key)
            continue
        after = text[found.end(1):found.end(1) + 400]
        if "can_add=" in after.split("Question(")[0]:
            already.append(key)
            continue
        indent = found.group(2)
        text = (text[:found.end(1)]
                + f'{indent}can_add="{label}",\n'
                + text[found.end(1):])
        added.append(key)

    SOURCE.write_text(text, encoding="utf-8")
    print(f"added:   {added}")
    print(f"already: {already}")
    print(f"missed:  {missed}")
    return 1 if missed else 0


if __name__ == "__main__":
    raise SystemExit(main())
