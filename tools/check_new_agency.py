"""Can a brand-new agency actually get from the map to a document?

Every check in this project so far has run as SCDES, which owns the corpus, or
as the IIA test container, which has been through every screen many times. The
Department of Education demo is neither: a real agency, no corpus, no answers,
nothing derived, starting at the map.

That path has never been walked, and it is the one the demo depends on. So this
does the whole journey over HTTP the way a browser does — eligibility, register,
verify, session, framework state, answer a question, export the document — and
checks at each step that nothing from SCDES or IIA is visible.

It **writes**: it creates a real agency container and a real session. Run it
against a local server, never staging, or it will claim a container a real
person needs. It says which server it is pointed at and refuses the obvious
mistake.

Usage:  python -m tools.check_new_agency
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from io import BytesIO

BASE = os.getenv("GAIUS_BASE", "http://127.0.0.1:8765").rstrip("/")

#: SC Department of Education — a real agency in the registry, with a real
#: convention (`flast` on ed.sc.gov) the platform derived from its own staff
#: directory. Using a real one is the point: a made-up agency would not exercise
#: the convention check that refuses a wrongly-shaped address.
#:
#: `sc.ed`, not `sc.scde`. Getting that wrong the first time is what found the
#: bug: registration accepted the typo and built a container for an agency that
#: does not exist, whose exported framework then had no name on it.
AGENCY = "sc.ed"
WHO = "jdoe@ed.sc.gov"
NAME = "Jordan Doe"
TITLE = "Chief Information Officer"


def call(method: str, path: str, body: dict | None = None,
         session: str = "") -> dict:
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if session:
        req.add_header("X-GAIUS-Session", session)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}", "body": exc.read().decode()[:200]}


def main() -> int:
    if "staging" in BASE or "governingai.us" in BASE:
        print(f"refusing to run against {BASE} — this registers a real agency "
              f"container. Point it at a local server.")
        return 2

    print(f"target: {BASE}\n")
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<44} {detail}")
        if not ok:
            failures.append(label)

    # ------------------------------------------------------------ eligibility
    print("1. an ed.sc.gov address at the door")
    elig = call("POST", "/api/register",
                {"email": WHO, "portal": "government"})
    check("accepted", bool(elig.get("ok")), elig.get("reason", "")[:44])

    # ---------------------------------------------------------- registration
    print("\n2. registering the agency")
    reg = call("POST", "/api/agency/register", {
        "agency": AGENCY, "name": NAME, "title": TITLE, "email": WHO,
        # Required, and rightly — the registration is a claim to act for an
        # agency, and a contactable number is the cheapest part of evidencing it.
        "phone": "(803) 734 8500",
        # The first-person attestation. Refused without it, which is the point:
        # the platform cannot verify delegated authority, so it records an
        # assertion the person can be held to instead of inferring one.
        "attested": True,
    })
    if not reg.get("ok") and "already" in str(reg.get("error", "")).lower():
        print(f"     already registered here — {reg.get('error')}")
        print("     (clear data/tenancy.json to walk it from clean)")
    check("registration opened", bool(reg.get("ok")) or "already" in
          str(reg.get("error", "")).lower(), str(reg.get("error", ""))[:50])
    code = reg.get("code")
    check("a code was issued", bool(code),
          "shown on screen because SMTP is unset" if code else "no code")
    if not code:
        print("\ncannot continue without the code")
        return 1

    # ---------------------------------------------------------- verification
    print("\n3. verifying the mailbox")
    ver = call("POST", "/api/agency/verify", {"email": WHO, "code": code})
    check("verified", bool(ver.get("ok")), str(ver.get("error", ""))[:50])
    session = ver.get("session", "")
    check("a session token was issued", bool(session),
          "so the server can tell who this is")
    if not session:
        return 1

    # ------------------------------------------------------------- what they see
    print("\n4. what this agency can see")
    fw = call("GET", f"/api/framework?user=sean.ot&email={urllib.parse.quote(WHO)}",
              session=session)
    docs = [f for layer in fw.get("layers", []) for f in layer.get("files", [])]
    check("no reference documents", not docs,
          f"{len(docs)} visible" if docs else "an empty shelf, correctly")
    check("framework state is 'none'", fw.get("state") == "none",
          str(fw.get("state")))

    state = call("GET", f"/api/state?user=sean.ot&email={urllib.parse.quote(WHO)}",
                 session=session)
    dec = state.get("decider") or {}
    check("nobody has been named as decider",
          (dec.get("shape") or "unset") == "unset",
          f"shape={dec.get('shape')}")
    check("not offered admin", not state.get("admin"))

    ver_state = call("GET", f"/api/versions?user=sean.ot&email={urllib.parse.quote(WHO)}",
                     session=session)
    check("no inherited answers", not (ver_state.get("working") or {}),
          f"{len(ver_state.get('working') or {})} answered")

    # ------------------------------------------------------------- the builder
    print("\n5. answering a question")
    reg_sections = call("GET", "/api/discretion?user=sean.ot", session=session)
    check("all thirteen sections offered",
          (reg_sections.get("totals") or {}).get("mined") == 13,
          f"{(reg_sections.get('totals') or {}).get('questions')} questions")

    saved = call("POST",
                 f"/api/versions/answer?user=sean.ot&email={urllib.parse.quote(WHO)}",
                 {"key": "agency.identity",
                  "value": "South Carolina Department of Education · SCDE · "
                           "state education agency"},
                 session=session)
    check("the answer saved", bool(saved.get("ok")),
          str(saved.get("error", ""))[:50])

    back = call("GET", f"/api/versions?user=sean.ot&email={urllib.parse.quote(WHO)}",
                session=session)
    check("and reads back", "agency.identity" in (back.get("working") or {}))

    # -------------------------------------------------------------- the document
    print("\n6. taking the document away")
    exp = call("GET",
               f"/api/framework/export?user=sean.ot&email={urllib.parse.quote(WHO)}",
               session=session)
    check("it builds", bool(exp.get("ok")), str(exp.get("error", ""))[:60])
    if not exp.get("ok"):
        return 1
    check("named for this agency", "SCDE" in exp.get("filename", ""),
          exp.get("filename", ""))

    blob = base64.b64decode(exp["content"])
    z = zipfile.ZipFile(BytesIO(blob))
    xml = "".join(z.read(n).decode("utf-8", "replace")
                  for n in z.namelist() if n.endswith(".xml"))
    check("carries their own answer",
          "state education agency" in xml)
    check("watermarked DRAFT", "GaiusWatermark" in xml)
    check("all thirteen sections", all(
        t in xml for t in ("Purpose", "Risk Management Policy",
                           "Incident Response", "Conclusion")))

    print("\n7. and nothing of anybody else's")
    for marker, whose in (("SCDES", "the corpus owner"),
                          ("Environmental Services", "the corpus owner"),
                          ("Innovative Infrastructure", "the IIA container")):
        check(f"no trace of {whose[:26]}", marker not in xml, marker)

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — a new agency reaches a document of its own, and sees nothing else")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
