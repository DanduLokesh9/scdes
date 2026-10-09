"""Walk the registration flow against the running server.

Run:  python tools/check_registration.py
"""

import json
import pathlib
import sys
import urllib.request

BASE = "http://127.0.0.1:8765"
STORE = pathlib.Path(__file__).resolve().parent.parent / "data" / "tenancy.json"


def post(path, body):
    request = urllib.request.Request(
        BASE + path, data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    return json.loads(urllib.request.urlopen(request).read())


def get(path):
    return json.loads(urllib.request.urlopen(BASE + path).read())


if STORE.exists():
    STORE.unlink()
    print("cleared any container left by an earlier run")
    print("(restart the server so it re-reads the file)\n")

print("=== the tester's path ===")
started = post("/api/agency/register", {
    "agency": "iia.test", "name": "Lokesh Dandu", "title": "QA",
    "email": "lokesh@iiac.ai", "phone": "8035550100", "attested": True})
print("  1. register :", started["ok"], "| code issued:", bool(started.get("code")))

verified = post("/api/agency/verify",
                {"email": "lokesh@iiac.ai", "code": started["code"]})
print("  2. verify   :", verified["ok"], "| status:", verified["status"],
      "| tester:", verified.get("tester"))

access = get("/api/agency/access?email=lokesh@iiac.ai")
print("  3. access   :", access["allowed"], "| container:", access["state"],
      "| role:", access["role"])

print("\n=== a real agency waits for a reviewer ===")
real = post("/api/agency/register", {
    "agency": "sc.des", "name": "Jane Smith", "title": "Deputy Director",
    "email": "jane.smith@des.sc.gov", "phone": "8035550111", "attested": True})
real_verified = post("/api/agency/verify",
                     {"email": "jane.smith@des.sc.gov", "code": real["code"]})
print("  status after verifying:", real_verified["status"])
print("  access allowed        :",
      get("/api/agency/access?email=jane.smith@des.sc.gov")["allowed"])

print("\n=== nobody else can claim that agency ===")
blocked = post("/api/agency/register", {
    "agency": "sc.des", "name": "Bob Jones", "title": "Director",
    "email": "bob.jones@des.sc.gov", "phone": "8035550122", "attested": True})
print(" ", blocked.get("error", "")[:88])

print("\n=== refusals a user will actually hit ===")
for label, body in [
    ("wrong convention", {"agency": "sc.ed", "name": "Ann Lee",
                          "email": "ann.lee@ed.sc.gov"}),
    ("personal mailbox", {"agency": "sc.ed", "name": "Ann Lee",
                          "email": "annlee@gmail.com"}),
    ("no attestation", {"agency": "sc.ed", "name": "Ann Lee",
                        "email": "alee@ed.sc.gov", "attested": False}),
]:
    payload = {"agency": "sc.ed", "name": "Ann Lee", "title": "Chief of Staff",
               "phone": "8035550133", "attested": True}
    payload.update(body)
    result = post("/api/agency/register", payload)
    print(f"  {label:<17} {result.get('error', 'ACCEPTED')[:64]}")
