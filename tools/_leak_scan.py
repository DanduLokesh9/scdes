"""Ask every read endpoint as a stranger, and look for somebody else's name.

The client's ticket A5033FAE: "Click on Agency Profile, would see information
about the DEMO account agency. Still Showing SCDES." The isolation checks read
the framework, the answers and the decider; this sweeps the rest, because the
leak that reaches a person is the one nobody thought to look at — the page
title was in the browser tab for a fortnight.

Read-only. Every request is made as an address belonging to the harness's own
container, so anything naming another agency is a leak by definition.

Usage:  python -m tools._leak_scan [base-url]
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from tools.harness_identity import HARNESS_EMAIL, DEFAULT_BASE, session_for

#: Names that belong to the reference agency and to nobody who registers.
LEAKS = ("SCDES", "South Carolina Department", "Environmental Services",
         "des.sc.gov", "AI Governance Council of SCDES",
         # Corpus *content*, not only the corpus owner's name. /api/council
         # served forty of the reference agency's decisions to a stranger and
         # passed a name-only check, because a decision cites "Appendix H —
         # Gate Review Checklists" rather than saying who wrote it.
         #
         # Deliberately not the bare "Appendix B" or "Operations Manual":
         # those are also the labels of the slots an agency uploads its *own*
         # documents into, and flagging them made /api/framework fail for
         # offering somebody a place to put their own manual. A marker that
         # fires on correct behaviour gets switched off.
         "Gate Review Checklists", "Classification Thresholds",
         "AI Governance Council of SCDES")

#: Every GET a signed-in browser makes. Kept here rather than derived so that
#: a new endpoint has to be added deliberately and gets swept.
ENDPOINTS = [
    "/api/state", "/api/profile", "/api/framework",
    "/api/module", "/api/versions", "/api/whose-container",
    "/api/notifications", "/api/discretion",
    "/api/registry", "/api/council", "/api/vision", "/api/budget",
    "/api/oversight", "/api/intake",
    # The data warehouse. Nothing in it comes from the corpus, which is
    # exactly why it is swept: "it cannot leak, by construction" is the
    # sentence that preceded every leak found so far.
    "/api/holdings", "/api/vendors", "/api/snapshots",
    # Billing. `/api/billing` shows one agency its own orders out of a
    # register that is shared, which is precisely the shape of endpoint that
    # has leaked before. `/api/billing/reconcile` reports across every
    # agency by design, so this proves a non-admin gets none of it.
    "/api/billing", "/api/billing/reconcile",
    # Integrity's own register, and the Projects and Lifecycle pages it reads
    # beside. The screen Integrity replaced audited the reference agency's
    # corpus by name.
    "/api/checks", "/api/projects", "/api/lifecycle",
    # Process served the reference agency's appendix map and risk bands.
    "/api/process",
    # Registry's catalog. The screen it replaced was the reference agency's
    # systems register.
    "/api/catalog",
    # Budget's cost lines. The screen they replaced served the reference
    # agency's budget pools.
    "/api/costs",
    # Vision's goals. The screen they replaced served the reference agency's
    # strategic map and pillars.
    "/api/goals",
    # The audit trail. It served the last sixty lines of one log every
    # organisation wrote into — and it was not on this list, which is how
    # nobody noticed.
    "/api/audit",
    # Every organization's people, for the GAIUS team only. A stranger must
    # get a refusal and nobody's name.
    "/api/admin/organizations",
]

#: Two endpoints name the reference agency legitimately, and are excluded
#: rather than quietly passing:
#:
#: `/api/states` is the "select your agency" list — every SC agency and 334
#: federal ones. SCDES appears in it because somebody from SCDES has to be
#: able to pick it, and a registry that hid one agency from the list would be
#: a worse product.
#:
#: `/api/tenancy` returns email-convention examples during registration, one
#: of which is `first.last@des.sc.gov`. That is a published convention rather
#: than anybody's content — but it is a stranger's domain in front of a
#: stranger, so it is on the list to revisit with a neutral example.
ALLOWED = ["/api/states", "/api/tenancy"]


def main(argv: list[str]) -> int:
    base = (argv[0] if argv else DEFAULT_BASE).rstrip("/")
    try:
        token = session_for(base)
    except Exception as why:                        # noqa: BLE001
        print(f"could not sign in: {why}")
        return 1

    query = urllib.parse.urlencode({"user": "sean.ot",
                                    "email": HARNESS_EMAIL})
    failures = []
    for path in ENDPOINTS:
        request = urllib.request.Request(f"{base}{path}?{query}")
        request.add_header("X-GAIUS-Session", token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            print(f"  --    {path:<26} HTTP {exc.code}")
            continue
        except OSError as why:
            print(f"  --    {path:<26} {why}")
            continue

        found = [name for name in LEAKS if name in body]
        mark = "FAIL" if found else "ok  "
        print(f"  {mark}  {path:<26} {len(body):>8} bytes"
              + (f"   LEAKS: {found}" if found else ""))
        if found:
            failures.append((path, found))
            # Show enough to find it, not enough to fill the screen.
            where = body.find(found[0])
            print(f"        …{body[max(0, where - 90):where + 90]}…")

    print()
    if failures:
        print(f"FAIL — {len(failures)} endpoint(s) name another agency")
        return 1
    print("PASS — no endpoint names another agency")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


