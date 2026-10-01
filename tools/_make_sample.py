"""Write a sample framework to disk so its shape can be inspected.

`check_document` asserts things about the text. This just produces the file,
so `_read_structure` and `_read_front` can be pointed at it and compared,
side by side, with the reference framework in corpus/framework — which is the
document the client asked the output to match.

Usage:  python -m tools._make_sample [out.docx] [--register formal|simplified]
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from app import export
from tools.check_document import ANSWERS


def main(argv: list[str]) -> int:
    out = Path(next((a for a in argv if not a.startswith("--")),
                    "sample_framework.docx"))
    register = "formal"
    if "--register" in argv:
        register = argv[argv.index("--register") + 1]

    # `build` reads the working answers out of the versions file, so the
    # sample is written by putting a full set of answers there — in a
    # throwaway directory, never a real tenant's.
    import tempfile
    from app import versions

    scratch = Path(tempfile.mkdtemp(prefix="gaius-sample-"))
    versions.VERSIONS_FILE = scratch / "framework_versions.json"
    held = versions.state()
    held["working"] = {**ANSWERS, "done.register": {"value": register}}
    versions._write(held)

    blob = export.build("Tidewater Water District", today=date(2026, 9, 5))
    out.write_bytes(blob)
    print(f"{out}  {len(blob) / 1024:,.0f} KB  (register: {register})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
