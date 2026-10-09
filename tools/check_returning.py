"""Can someone who registered, and then signed out, get back in?

They could not. Register claims an agency and refuses if it is taken, so the
person who registered SCDES and signed out was told "this agency has already
been registered by lokesh dandu — ask them to add you" about themselves, with
no other door on the screen.

This walks the whole round trip against the running server: register, verify,
sign out, sign back in with a fresh code, and confirm the second code grants
access without creating a second container or claiming the agency again.

    python -m tools.check_returning
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8765"
EMAIL = "jane.smith@des.sc.gov"
AGENCY = "sc.des"


def post(path: str, payload: dict) -> dict:
    request = urllib.request.Request(
        BASE + path + ("&" if "?" in path else "?") + "user=sean.ot",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"})
    try:
        return json.load(urllib.request.urlopen(request))
    except urllib.error.HTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.code}"}


def get(path: str) -> dict:
    return json.load(urllib.request.urlopen(BASE + path))


def main() -> int:
    print("1. register")
    reg = post("/api/agency/register", {
        "agency": AGENCY, "name": "Jane Smith", "title": "Deputy Director",
        "email": EMAIL, "phone": "8035550100", "attested": True})
    if not reg.get("ok") and "already been registered" not in str(reg.get("error", "")):
        print(f"   refused: {reg.get('error')}")
    code = reg.get("code")
    if code:
        verified = post("/api/agency/verify", {"email": EMAIL, "code": code})
        print(f"   registered and verified: {verified.get('status')}")
    else:
        print("   already registered from an earlier run — carrying on")

    print("\n2. registering the same agency again, as the same person")
    again = post("/api/agency/register", {
        "agency": AGENCY, "name": "Jane Smith", "title": "Deputy Director",
        "email": EMAIL, "phone": "8035550100", "attested": True})
    print(f"   refused    : {not again.get('ok')}")
    print(f"   is_you     : {again.get('is_you')}  <- points at sign-in, not "
          f"at themselves")
    print(f"   says       : {again.get('error')}")

    print("\n3. signing in instead")
    signin = post("/api/agency/signin", {"email": EMAIL})
    print(f"   ok         : {signin.get('ok')}")
    print(f"   emailed    : {signin.get('emailed')}")
    fresh = signin.get("code")
    if not fresh:
        print("   no code returned — SMTP must be configured here")
        return 1

    done = post("/api/agency/verify", {"email": EMAIL, "code": fresh})
    print(f"   verified   : {done.get('ok')} status={done.get('status')} "
          f"signin={done.get('signin')}")

    access = get(f"/api/agency/access?email={EMAIL}")
    print(f"   allowed    : {access.get('allowed')} on {access.get('state')} "
          f"as {access.get('role')}")

    print("\n4. an address nobody registered")
    stranger = post("/api/agency/signin", {"email": "nobody@des.sc.gov"})
    print(f"   refused    : {not stranger.get('ok')}")
    print(f"   says       : {stranger.get('error')}")
    leaks = "lokesh" in str(stranger).lower() or "jane" in str(stranger).lower()
    print(f"   names names: {leaks}  <- must be False; the sign-in box must "
          f"not map an agency's staff")

    ok = (again.get("is_you") and done.get("ok") and access.get("allowed")
          and not stranger.get("ok") and not leaks)
    print(f"\n{'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

