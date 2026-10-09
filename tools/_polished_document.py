"""Build one whole framework with the language polished, and read it.

The checks in `tests/test_polish.py` prove the rules work. The measurement in
`tools/_polish_cost.py` proves the pass is affordable and quick. Neither
shows the thing the client actually asked about: whether the finished
document reads like the adopted instrument he sent as the north star.

    python -m tools._polished_document [--as-written]

Writes the file next to the plain one so the two can be opened side by side.
Spends money unless --as-written.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from app import env, export, module_one, versions
from tools.check_document import ANSWERS, WHO, readable

env.load()

OUT = Path.home() / "Downloads"


def main(argv: list[str]) -> int:
    polished = "--as-written" not in argv
    for key, value in ANSWERS.items():
        versions.answer(key, value, WHO)
    versions.answer("done.register", module_one.FORMAL, WHO)
    versions.answer("done.language",
                    module_one.POLISHED if polished else module_one.AS_WRITTEN,
                    WHO)

    blob = export.build("Tidewater Water District", today=date(2026, 9, 15))
    name = f"framework_{'polished' if polished else 'as_written'}.docx"
    (OUT / name).write_bytes(blob)

    print(readable(blob))
    print(f"\n{len(blob):,} bytes → {OUT / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
