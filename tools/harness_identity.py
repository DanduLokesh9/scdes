"""Refuse to run a destructive check against anybody's real container.

The browser harnesses answer real questions through the real endpoints, and
they begin by blanking a list of keys so the walk is deterministic. That is the
right way to test the thing — and it means the scripts are, by design, willing
to destroy answers.

Run against `iia.test` on staging they did exactly that to the client's own
work: five answers blanked, nine overwritten. The audit log could not say what
had been there, because it records which question was answered and by whom, but
not the answer.

So: before a check writes anything it asks the server which container its
writes will land in, and stops unless that container exists solely for the
checks. The guard lives on the server's answer, not on what the script believes
about itself — a script that thinks it is signed in as somebody harmless is
exactly how this happened.

Usage, from a check:

    from tools.harness_identity import demand_scratch_container
    demand_scratch_container(BASE, email)

Usage, to look before running anything:

    python -m tools.harness_identity                     # local
    python -m tools.harness_identity <base-url> <email>
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_BASE = "http://127.0.0.1:8765"

#: The container the checks own, and the address that belongs to it.
HARNESS_AGENCY = "gaius.harness"
HARNESS_EMAIL = "walk@harness.gaius.test"


class WrongContainer(RuntimeError):
    """Raised rather than returned, so a check cannot ignore it by mistake."""


def _post(base: str, path: str, body: dict) -> dict:
    request = urllib.request.Request(
        base.rstrip("/") + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}


def session_for(base: str, email: str = HARNESS_EMAIL,
                agency: str = HARNESS_AGENCY) -> str:
    """A session for the harness, obtained the way a person obtains one.

    Ask for a code, read it out of the response, verify. Deliberately not
    minted out of the tenancy store: a locally minted token is one staging
    never issued, which produced five false failures — two of them on the
    security check — before anyone noticed the harness was testing itself.
    """
    # The harness accepts the Terms of Use like anybody else: registering
    # needs it, and so does any write once signed in.
    _post(base, "/api/terms/accept", {
        "email": email, "name": "Automated walk", "title": "Harness",
        "unit": "GAIUS harness", "agency": agency,
        "authority": True, "scrolled": True})
    asked = _post(base, "/api/agency/signin", {"email": email})
    if not asked.get("code"):
        asked = _post(base, "/api/agency/register", {
            "agency": agency, "name": "Automated walk", "title": "Harness",
            "email": email, "phone": "(843) 555 0100", "attested": True})
    code = asked.get("code")
    if not code:
        raise WrongContainer(
            f"could not get a sign-in code for {email}: "
            f"{asked.get('error') or asked}")
    done = _post(base, "/api/agency/verify", {"email": email, "code": code})
    if not done.get("session"):
        raise WrongContainer(f"could not verify {email}: "
                             f"{done.get('error') or done}")
    return str(done["session"])


def whose_container(base: str, email: str = "") -> dict:
    url = base.rstrip("/") + "/api/whose-container"
    if email:
        url += "?" + urllib.parse.urlencode({"email": email})
    with urllib.request.urlopen(url, timeout=30) as response:
        return json.load(response)


def demand_scratch_container(base: str, email: str = "") -> dict:
    """Return the container, or refuse to let the caller continue."""
    found = whose_container(base, email)
    if found.get("safe_to_overwrite"):
        return found
    raise WrongContainer(
        f"\n  Refusing to run.\n"
        f"  These writes would land in: {found.get('agency')!r}\n"
        f"  as: {email or 'an unidentified caller'}\n"
        f"  against: {base}\n\n"
        f"  This check blanks answers to make its walk deterministic, so it\n"
        f"  may only run in a container kept for the checks. Point it at one,\n"
        f"  or run it locally.\n")


def main(argv: list[str]) -> int:
    base = argv[0] if argv else DEFAULT_BASE
    email = argv[1] if len(argv) > 1 else HARNESS_EMAIL
    # Registering is what puts the address in the container in the first place,
    # so it happens before the container is read back.
    try:
        session_for(base, email)
    except WrongContainer as why:
        print(f"could not sign in: {why}")
    found = whose_container(base, email)
    print(f"base      : {base}")
    print(f"as        : {email or '(no address given)'}")
    print(f"container : {found.get('agency')}")
    print(f"resolved  : from the {found.get('resolved_from')}")
    print(f"test      : {found.get('is_test_container')}")
    print(f"harness   : {found.get('is_harness_container')}")
    print()
    if found.get("safe_to_overwrite"):
        print("Safe — this container exists for the checks.")
        return 0
    print("NOT SAFE — a check would overwrite somebody's answers here.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
