"""Does the reporter get a bell when their ticket is answered?

The client's instruction when the bell was built: "if any user reported an
issue, if action takes place, that user should get notification pop up through
the bell icon". Thirty-one tickets were just answered, so there should be
thirty-one notifications waiting for the person who filed them.

Read as the reporter, with a real session — the notifications endpoint keys off
the *proved* address, not one passed in a query string, so asking without a
session correctly returns nothing and tells you nothing.

Usage:  python -m tools._check_bell [base-url] [email]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

DEFAULT_BASE = "https://app.staging.governingai.us"
WHO = "brett@iiac.ai"


def _post(base: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def _get(base: str, path: str, session: str) -> dict:
    request = urllib.request.Request(base.rstrip("/") + path)
    request.add_header("X-GAIUS-Session", session)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def main(argv: list[str]) -> int:
    base = (argv[0] if argv else DEFAULT_BASE).rstrip("/")
    who = argv[1] if len(argv) > 1 else WHO

    asked = _post(base, "/api/agency/signin", {"email": who})
    code = asked.get("code")
    if not code:
        print(f"could not get a sign-in code for {who}: "
              f"{asked.get('error') or asked}")
        return 1
    done = _post(base, "/api/agency/verify", {"email": who, "code": code})
    session = done.get("session")
    if not session:
        print(f"could not verify {who}: {done}")
        return 1

    found = _get(base, "/api/notifications", session)
    items = (found.get("notifications") or found.get("items")
             or found.get("unread") or [])
    print(f"{who}\n")
    print(f"  keys returned : {list(found)}")
    print(f"  waiting       : {len(items)}")
    for item in items[:6]:
        print(f"    {json.dumps(item)[:130]}")

    _post(base, "/api/session/end", {"session": session})

    if not items:
        print("\nFAIL — the replies were posted but the reporter is not told")
        return 1
    print("\nPASS — the reporter is notified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
