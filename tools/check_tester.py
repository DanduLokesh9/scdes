"""Prove what the tester bypass does and, more importantly, what it does not.

Run:  python tools/check_tester.py
"""

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import tenancy as t                                    # noqa: E402

t.STORE = pathlib.Path(tempfile.mkdtemp()) / "tenancy.json"

print("=== who counts as a tester ===")
for address in ("lokesh@iiac.ai", "LOKESH@IIAC.AI", "brett@iiac.ai",
                "lokesh@des.sc.gov", "someone@gmail.com"):
    print(f"  {'YES' if t.is_tester(address) else 'no ':<4} {address}")

print("\n=== the tester still faces every other check ===")
wrong_domain = t.start_registration(
    agency="iia.test", name="Lokesh Dandu", title="Tester",
    email="lokesh@gmail.com", phone="8035550100", attested=True)
print("  wrong domain refused    :", not wrong_domain["ok"])

# The TEST container is domain-only, so any local part on iiac.ai is fine.
# A real agency is not: the same person on SC DES must match first.last.
real_agency = t.start_registration(
    agency="sc.des", name="Lokesh Dandu", title="Tester",
    email="lokesh@des.sc.gov", phone="8035550100", attested=True)
print("  real agency convention  :", "refused" if not real_agency["ok"] else "ACCEPTED")
print("  test container any-local:", t.check_identity("iia.test", "Lokesh Dandu",
      "ldandu@iiac.ai").ok)

no_attestation = t.start_registration(
    agency="iia.test", name="Lokesh Dandu", title="Tester",
    email="lokesh@iiac.ai", phone="8035550100", attested=False)
print("  attestation still needed:", not no_attestation["ok"])

print("\n=== what it actually skips: the wait for a reviewer ===")
started = t.start_registration(
    agency="iia.test", name="Lokesh Dandu", title="Tester",
    email="lokesh@iiac.ai", phone="8035550100", attested=True)
print("  wrong code still refused:",
      not t.verify_code("lokesh@iiac.ai", "000000")["ok"])

verified = t.verify_code("lokesh@iiac.ai", started["code"])
print("  status after verifying  :", verified["status"],
      "| tester:", verified.get("tester"))

access = t.access_for("lokesh@iiac.ai")
print("  allowed immediately     :", access["allowed"],
      "| container:", access["state"])

container = t.agency_state("iia.test")
print("  container status        :", container["status"])
print("  recorded on the container:",
      t._load()["agencies"]["iia.test"]["approved_by"])

print("\n=== container rules still hold for a tester ===")
blocked = t.start_registration(
    agency="iia.test", name="Someone Else", title="Analyst",
    email="someone.else@iiac.ai", phone="8035550111", attested=True)
print("  nobody else can claim it:", not blocked["ok"])
print("  outsider sees nothing   :",
      t.access_for("stranger@des.sc.gov")["state"] == "")

print("\n=== switching it off for production ===")
os.environ["IIA_TESTERS"] = "none"
print("  IIA_TESTERS=none ->", t.is_tester("lokesh@iiac.ai"))
os.environ.pop("IIA_TESTERS")
print("  restored          ->", t.is_tester("lokesh@iiac.ai"))
