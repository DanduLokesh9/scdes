"""File a bug carrying things that must never be stored, then look at the store.

The client asked for privacy to be part of v1 rather than added later, so the
check is not "does a report arrive" — it is "does a report arrive with the
address, the verification code and the request body stripped out".

Deliberately sends all three. The widget already redacts before anything enters
its buffer; this bypasses the widget entirely, because a rule that only holds
when the client behaves is not a rule.

    python -m tools.check_bugs
"""

from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8765"

LEAKY = {
    "expected": "The registry to open",
    "happened": ("It went blank. My address is jane.smith@des.sc.gov and the "
                 "code was 4829174."),
    "context": {
        "view": "Registry",
        "url": "/?email=jane.smith@des.sc.gov&code=482917",
        "browser": "Mozilla/5.0 Chrome/140",
        "screen": "1920x1080",
        "version": "2026-08-22",
    },
    "events": [
        {"kind": "error", "at": "2026-08-22T10:00:00Z",
         "text": "TypeError: cannot read 'name' of undefined"},
        {"kind": "network", "at": "2026-08-22T10:00:01Z",
         "text": "/api/registry?email=jane.smith@des.sc.gov",
         "method": "GET", "status": "500", "ms": "42",
         "body": "THE WHOLE FRAMEWORK ANSWER", "response": "SECRET"},
        {"kind": "screenshot", "at": "2026-08-22T10:00:02Z",
         "text": "data:image/png;base64,AAAA"},
    ],
    "reporter": "jane.smith@des.sc.gov",
    "name": "Jane Smith",
    "agency": "SCDES",
}


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path + "?user=sean.ot",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(request))


def get(path: str) -> dict:
    return json.load(urllib.request.urlopen(BASE + path))


def main() -> int:
    filed = post("/api/bugs/report", LEAKY)
    print(f"filed          : {filed.get('ok')}  {filed.get('id')}  "
          f"fingerprint={filed.get('fingerprint')}")
    if not filed.get("ok"):
        print(f"  {filed.get('error')}")
        return 1

    queue = get("/api/bugs?user=sean.ot")
    ticket = next(t for t in queue["tickets"] if t["id"] == filed["id"])
    blob = json.dumps(ticket)

    print("\nwhat was stored:")
    print(f"  happened     : {ticket['happened']}")
    print(f"  url          : {ticket['url']}")
    print(f"  reporter     : {ticket['reporter']}")
    for event in ticket["events"]:
        extra = (f"  [{event.get('method', '')} {event.get('status', '')}]"
                 if event.get("status") else "")
        print(f"  {event['kind']:9}    : {event['text'][:70]}{extra}")

    # The reporter's own address is kept on purpose — it is how they are
    # notified, and how "only you may reopen this" is enforced. Everything else
    # is scanned; that field is not, and that exemption is the whole rule.
    without_reporter = json.dumps({k: v for k, v in ticket.items()
                                   if k != "reporter"})

    print("\nprivacy:")
    checks = {
        "no stray email addresses":
            "jane.smith@des.sc.gov" not in without_reporter,
        "the reporter's own address is kept":
            ticket["reporter"] == "jane.smith@des.sc.gov",
        "no verification code": "4829174" not in blob and "482917" not in blob,
        "no request body": "THE WHOLE FRAMEWORK ANSWER" not in blob,
        "no response body": "SECRET" not in blob,
        "no screenshot smuggled in": "data:image" not in blob,
        "status codes kept (useful)": '"500"' in blob,
        "error message kept (useful)": "TypeError" in blob,
    }
    for label, ok in checks.items():
        print(f"  {'ok  ' if ok else 'FAIL'} {label}")

    print("\ngrouping:")
    second = post("/api/bugs/report", {**LEAKY, "happened": "Blank again."})
    print(f"  same fault filed twice -> same fingerprint: "
          f"{second['fingerprint'] == filed['fingerprint']}")
    print(f"  second report knows of {second['seen_before']} like it")

    print("\nworkflow:")
    done = post("/api/bugs/respond", {"id": filed["id"], "status": "fixed",
                                      "message": "Fixed in the next deploy."})
    print(f"  team reply + status  : {done.get('ok')} -> "
          f"{done.get('ticket', {}).get('status')}")
    again = post("/api/bugs/reopen", {"id": filed["id"],
                                      "email": "jane.smith@des.sc.gov",
                                      "message": "Still blank for me."})
    print(f"  reporter reopens     : {again.get('ok')} -> "
          f"{again.get('ticket', {}).get('status')}  "
          f"{'' if again.get('ok') else again.get('error')}")
    # Put it back into a reopenable state first. The first version of this
    # check ran the stranger against an already-open ticket, so it was refused
    # for being open rather than for being somebody else's — and passed while
    # every address in the world could in fact reopen every ticket.
    post("/api/bugs/respond", {"id": filed["id"], "status": "fixed",
                               "message": "Fixed again."})
    stranger = post("/api/bugs/reopen", {"id": filed["id"],
                                         "email": "someone@else.gov",
                                         "message": "me too"})
    right_reason = "reported it" in str(stranger.get("error", ""))
    print(f"  a stranger cannot    : {not stranger.get('ok')}"
          f"  ({'right reason' if right_reason else 'WRONG REASON: ' + str(stranger.get('error'))})")

    owner = post("/api/bugs/reopen", {"id": filed["id"],
                                      "email": "jane.smith@des.sc.gov",
                                      "message": "Still broken."})
    print(f"  the owner still can  : {owner.get('ok')}")

    only_mine = get("/api/bugs?user=liz.operator&email=someone@else.gov")
    print(f"  a stranger sees      : {len(only_mine.get('tickets', []))} "
          f"ticket(s)  (must be 0)")

    ok = (all(checks.values())
          and second["fingerprint"] == filed["fingerprint"]
          and right_reason and owner.get("ok")
          and not only_mine.get("tickets"))
    print(f"\n{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
