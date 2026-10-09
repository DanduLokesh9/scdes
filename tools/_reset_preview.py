"""What Start Over would clear, for one agency. Read-only — previews only.

The client asked for a button to erase everything he has built in his own
tenant, so he can demo consistently and test from zero. Worth showing him what
it would take before he presses it, and worth checking it names his own files
rather than the reference agency's.

Usage:  python -m tools._reset_preview [base-url] [email]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "https://app.staging.governingai.us"
WHO = "brett@iiac.ai"


def main(argv: list[str]) -> int:
    base = (argv[0] if argv else DEFAULT_BASE).rstrip("/")
    who = argv[1] if len(argv) > 1 else WHO

    query = urllib.parse.urlencode({"user": "sean.ot", "email": who})
    try:
        with urllib.request.urlopen(
                f"{base}/api/reset/preview?{query}", timeout=30) as response:
            found = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}")
        return 1

    print(f"Start Over, as {who}\n")
    print(f"  allowed to      : {found.get('can_reset')}")
    print(f"  confirm phrase  : {found.get('phrase', 'START OVER')}")
    print(f"  audit entries   : {found.get('audit_entries')} — kept, entire")
    print()
    print("  what goes")
    for item in found.get("clears", []):
        mark = "has content" if item.get("present") else "already empty"
        print(f"    {mark:<14} {item.get('label')}")
        detail = str(item.get("detail") or "")
        if detail:
            print(f"                   {detail[:76]}")
    print()
    print("  what stays")
    for item in found.get("keeps", []) or []:
        label = item if isinstance(item, str) else item.get("label", "")
        print(f"    {label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
