"""Can a user reach the bug queue by picking a grander capacity?

Until now: yes. The queue keyed off `actor.is_ot`, and every signed-in person is
offered "Office of Technology" in the header dropdown, so one click showed
anybody every report filed from every agency.

This is the critic's version of that — it runs the attacks against a live
server rather than asserting the fix in the abstract:

  1. no identity at all
  2. the OT capacity, which anyone can select
  3. the Council capacity
  4. an admin's address *claimed* in the query string, with no proof
  5. a made-up session token
  6. a real token belonging to somebody who is not an admin
  7. a real token belonging to an admin — the only one that should work

All seven are pure HTTP and work against any deployment. Steps 6 and 7 need
real tokens, and those are obtained the way a person obtains one — ask for a
code, read it, verify — rather than minted out of the tenancy store. Minting
worked only where this process and the server shared a filesystem: pointed at
staging it produced tokens that server had never issued, and the check reported
two ways in that did not exist. A security check crying wolf is worse than no
check, so it now uses the same door everybody else does.

Usage:  python -m tools.check_admin
        GAIUS_BASE=https://app.staging.governingai.us python -m tools.check_admin
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.getenv("GAIUS_BASE", "http://127.0.0.1:8765").rstrip("/")
ADMIN = "brett@iiac.ai"

#: Deliberately an @iiac.ai address, and deliberately not one of the three.
#:
#: It has to be somebody who can actually get a session, so it joins the shared
#: test container like any colleague would — which makes this a sharper test
#: than an outsider: a *tester*, on the same domain as all three admins, inside
#: the same container, still gets nothing. Admin is three named addresses, not
#: a domain and not a container.
STRANGER = "stranger.check@iiac.ai"


def get(path: str, session: str = "") -> dict:
    req = urllib.request.Request(BASE + path)
    if session:
        req.add_header("X-GAIUS-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def post(path: str, body: dict, session: str = "") -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    if session:
        req.add_header("X-GAIUS-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def session_for(email: str) -> str:
    """A session for `email`, obtained the way a person obtains one.

    Ask for a code, read it out of the response, verify. Only works while SMTP
    is unconfigured, which is exactly when the code comes back at all — when
    email is wired up this needs another route in, and that is the right moment
    to notice.
    """
    asked = post("/api/agency/signin", {"email": email})
    if not asked.get("code"):
        asked = post("/api/agency/register", {
            "agency": "iia.test", "name": "Admin check", "title": "Harness",
            "email": email, "phone": "(843) 555 0100", "attested": True})
    code = asked.get("code")
    if not code:
        raise SystemExit(f"could not get a code for {email}: "
                         f"{asked.get('error') or asked}")
    done = post("/api/agency/verify", {"email": email, "code": code})
    if not done.get("session"):
        raise SystemExit(f"could not verify {email}: "
                         f"{done.get('error') or done}")
    return str(done["session"])


def end(token: str) -> None:
    post("/api/session/end", {"session": token})


def tickets(answer: dict) -> str:
    """What this attempt actually got back."""
    if answer.get("team"):
        return f"THE WHOLE QUEUE — {answer.get('total', '?')} tickets"
    n = len(answer.get("tickets") or [])
    return f"refused (own reports only: {n})"


def main() -> int:
    print(f"target: {BASE}\n")
    failures = []

    def attempt(label: str, answer: dict, *, should_pass: bool) -> None:
        got = tickets(answer)
        ok = answer.get("team") is True if should_pass else not answer.get("team")
        print(f"  {'ok ' if ok else 'FAIL'}  {label:<46} {got}")
        if not ok:
            failures.append(label)

    print("reading the queue")
    attempt("no identity at all",
            get("/api/bugs?status="), should_pass=False)
    attempt("capacity=Office of Technology",
            get("/api/bugs?status=&user=sean.ot"), should_pass=False)
    attempt("capacity=Council member",
            get("/api/bugs?status=&user=council.cto"), should_pass=False)
    attempt("an admin address claimed, not proved",
            get(f"/api/bugs?status=&user=sean.ot&email={ADMIN}"),
            should_pass=False)
    attempt("a made-up session token",
            get("/api/bugs?status=&user=sean.ot", session="not-a-real-token"),
            should_pass=False)

    # Real tokens, from the server being tested.
    #
    # These were minted straight out of the tenancy store, which works only
    # where this process and the server share a filesystem. Pointed at staging
    # it produced tokens that server had never issued, so the two steps below
    # failed and the check reported two ways in that did not exist — a false
    # alarm on a security check, which is worse than no check.
    stranger_token = session_for(STRANGER)
    admin_token = session_for(ADMIN)

    attempt("a real token, but not an admin's",
            get("/api/bugs?status=&user=sean.ot", session=stranger_token),
            should_pass=False)
    attempt("a real token belonging to an admin",
            get("/api/bugs?status=", session=admin_token), should_pass=True)

    print("\nanswering a ticket")
    queue = get("/api/bugs?status=", session=admin_token)
    first = (queue.get("tickets") or [{}])[0].get("id", "")
    if not first:
        print("  (no tickets to try against — skipped)")
    else:
        blocked = post("/api/bugs/respond",
                       {"id": first, "status": "open", "message": "test"})
        ok = not blocked.get("ok")
        print(f"  {'ok ' if ok else 'FAIL'}  without proof{'':<34} "
              f"{'refused' if ok else 'ACCEPTED — wrong'}")
        if not ok:
            failures.append("respond without proof")

    print("\nthe rail")
    for label, session, expected in (
            ("a plain user is not offered Admin", stranger_token, False),
            ("an admin is", admin_token, True)):
        state = get("/api/state?user=sean.ot", session=session)
        got = bool(state.get("admin"))
        ok = got is expected
        print(f"  {'ok ' if ok else 'FAIL'}  {label:<46} admin={got}")
        if not ok:
            failures.append(label)

    end(stranger_token)
    end(admin_token)

    print()
    if failures:
        print(f"FAIL — {len(failures)} way(s) in: " + "; ".join(failures))
        return 1
    print("PASS — the queue is reachable only with a proved admin address")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
