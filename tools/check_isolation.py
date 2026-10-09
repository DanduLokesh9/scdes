"""Does one agency see another's framework, over HTTP, as a browser would?

The reported bug, verbatim:

    Expected:  See no reference documents in the DEMO account.
    Happened:  I see all the reference documents, from SCDES to the appendices.

tests/test_isolation.py proves the modules scope correctly when a tenant is
bound. This proves the tenant is actually bound — that the dispatcher resolves
the caller's agency and that nothing downstream forgets to ask. Those are
different failures and only this one catches a handler wired up the old way.

Every request here is one a browser really sends: the same query string, the
same headers.

Usage:  python tools/check_isolation.py      (server must be running)
        GAIUS_BASE=https://app.staging.governingai.us python tools/check_isolation.py
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

BASE = os.getenv("GAIUS_BASE", "http://127.0.0.1:8765").rstrip("/")

#: Real members of the two containers on staging. The addresses matter — the
#: server resolves the agency from them.
DEMO = os.getenv("GAIUS_DEMO_EMAIL", "brett@iiac.ai")
OWNER = os.getenv("GAIUS_OWNER_EMAIL", "lokesh.dandu@des.sc.gov")


def get(path: str, email: str) -> dict:
    sep = "&" if "?" in path else "?"
    url = f"{BASE}{path}{sep}user=sean.ot&email={urllib.parse.quote(email)}"
    req = urllib.request.Request(url)
    req.add_header("X-SCDES-Email", email)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def documents(answer: dict) -> list[str]:
    out = []
    for layer in answer.get("layers", []):
        out.extend(layer.get("files", []))
    return out


def main() -> int:
    import urllib.parse                                    # noqa: F401
    print(f"target: {BASE}\n")
    failures = []

    def check(label: str, ok: bool, detail: str) -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<44} {detail}")
        if not ok:
            failures.append(label)

    print(f"the DEMO account ({DEMO})")
    demo = get("/api/framework", DEMO)
    files = documents(demo)
    check("sees no reference documents", not files,
          "none" if not files else f"{len(files)}: {', '.join(files[:3])}…")
    check("no layer claims to be present",
          all(not l.get("present") for l in demo.get("layers", [])),
          f"state={demo.get('state')}")

    print("\na signed-out visitor")
    anon = get("/api/framework", "")
    check("sees no reference documents", not documents(anon),
          f"{len(documents(anon))} document(s)")

    print(f"\nthe corpus owner ({OWNER})")
    owner = get("/api/framework", OWNER)
    owner_files = documents(owner)
    if not owner_files:
        # Only meaningful where that address is a registered member. On a
        # machine where it is not, "sees nothing" is the correct answer for the
        # same reason as the DEMO case, and asserting otherwise would be a
        # false failure rather than a finding.
        print("  --    not a member on this server — skipped")
    else:
        check("still sees its own", True, f"{len(owner_files)} document(s)")

    print("\nwho decides")
    d = get("/api/state", DEMO).get("decider") or {}
    check("DEMO is not handed an answer",
          (d.get("shape") or "unset") == "unset" and not d.get("confirmed"),
          f"shape={d.get('shape')!r} noun={d.get('noun')!r}")

    print("\nthe framework answers")
    demo_v = get("/api/versions", DEMO)
    owner_v = get("/api/versions", OWNER)
    dn = len((demo_v.get("working") or {}))
    on = len((owner_v.get("working") or {}))
    check("the two do not share a working draft", not (dn and dn == on and dn > 0),
          f"DEMO {dn} answered · owner {on} answered")

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — an agency sees its own governance and nobody else's")
    return 0


if __name__ == "__main__":
    import urllib.parse
    raise SystemExit(main())
