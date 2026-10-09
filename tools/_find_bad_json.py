"""Which JSON file under the corpus or data directory will not parse.

Sixty-two tests started failing at once with "Extra data: line 1 column 3",
which is a file that was written twice or written badly rather than a code
fault. Read-only — it names the file and shows the first line.

Usage:  python -m tools._find_bad_json
"""

from __future__ import annotations

import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent


def main() -> int:
    bad = []
    for folder in ("corpus", "data", "council"):
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in base.rglob("*.json"):
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except ValueError as why:
                bad.append((path, why))
            except OSError:
                continue

    if not bad:
        print("every JSON file parses")
        return 0

    print(f"{len(bad)} file(s) will not parse\n")
    for path, why in bad:
        rel = path.relative_to(ROOT)
        raw = path.read_text(encoding="utf-8", errors="replace")
        print(f"  {rel}")
        print(f"    {why}")
        print(f"    {len(raw)} bytes, starts: {raw[:90]!r}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
