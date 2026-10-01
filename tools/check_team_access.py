"""Everyone at IIA can test; nobody outside can, and real agencies stay closed.

Run:  python tools/check_team_access.py
"""

import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from app import tenancy as t                                    # noqa: E402

t.STORE = pathlib.Path(tempfile.mkdtemp()) / "tenancy.json"

print("=== who is a tester, by default ===")
for address in ("lokesh@iiac.ai", "brett@iiac.ai", "anyone.at.all@iiac.ai",
                "someone@des.sc.gov", "outsider@gmail.com"):
    print(f"  {'YES' if t.is_tester(address) else 'no ':<4} {address}")


def join(email, name):
    started = t.start_registration(
        agency="iia.test", name=name, title="Tester", email=email,
        phone="8035550100", attested=True)
    if not started.get("ok"):
        return f"REFUSED — {started.get('error', '')[:60]}"
    done = t.verify_code(email, started["code"])
    return ("joined" if done.get("ok") else
            f"REFUSED — {done.get('error', '')[:60]}")


print("\n=== three colleagues share the test container ===")
for email, name in (("lokesh@iiac.ai", "Lokesh Dandu"),
                    ("brett@iiac.ai", "Brett Butz"),
                    ("sam@iiac.ai", "Sam Tester")):
    print(f"  {email:<20} {join(email, name)}")

container = t.agency_state("iia.test")
print(f"  members now: {len(container['members'])}"
      f"  ({', '.join(m['email'] for m in container['members'])})")
print(f"  owner stays : {container['owner']}")

print("\n=== a real agency is NOT shared ===")
first = t.start_registration(
    agency="sc.des", name="Jane Smith", title="Deputy Director",
    email="jane.smith@des.sc.gov", phone="8035550111", attested=True)
t.verify_code("jane.smith@des.sc.gov", first["code"])
second = t.start_registration(
    agency="sc.des", name="Bob Jones", title="Director",
    email="bob.jones@des.sc.gov", phone="8035550122", attested=True)
print("  second registrant:", second.get("error", "ACCEPTED")[:70])

print("\n=== an IIA address cannot walk into a real agency ===")
print("  lokesh@iiac.ai on sc.des:",
      t.check_identity("sc.des", "Lokesh Dandu", "lokesh@iiac.ai").reason[:64])

print("\n=== narrowing and closing it ===")
os.environ["IIA_TESTERS"] = "lokesh@iiac.ai"
print("  IIA_TESTERS=lokesh@iiac.ai -> brett:", t.is_tester("brett@iiac.ai"),
      "| lokesh:", t.is_tester("lokesh@iiac.ai"))
os.environ["IIA_TESTERS"] = "none"
print("  IIA_TESTERS=none           -> lokesh:", t.is_tester("lokesh@iiac.ai"))
os.environ.pop("IIA_TESTERS")
print("  unset                      -> anyone@iiac.ai:",
      t.is_tester("anyone@iiac.ai"))
