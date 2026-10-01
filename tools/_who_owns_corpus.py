"""Which agency the corpus belongs to, and what each address resolves to.

The client's screenshot shows the DEMO account's Agency Profile displaying
"South Carolina Department of Environmental Services (SCDES)". The guard added
for that ticket keys off `tenant.owns_corpus()`, and a leak sweep run as the
harness's own address passed — so either DEMO is being treated as the corpus
owner, or the guard is not on the path the screen actually uses.

Read-only.

Usage:  python -m tools._who_owns_corpus
"""

from __future__ import annotations

from app import profile, tenant, tenancy

ADDRESSES = ["brett@iiac.ai", "lokesh@iiac.ai", "dev@iiac.ai",
             "walk@harness.gaius.test", "someone@des.sc.gov"]


def main() -> int:
    loaded = profile.load()
    print("the corpus on disk")
    print(f"  name       : {getattr(loaded, 'name', '')!r}")
    print(f"  short_name : {getattr(loaded, 'short_name', '')!r}")
    print(f"  owner code : {tenant.corpus_owner()!r}")
    print()

    print("what each address resolves to")
    for email in ADDRESSES:
        code = str(tenancy.access_for(email).get("state", "") or "") or "—"
        tenant.set_current(code if code != "—" else tenant.ANONYMOUS)
        try:
            owns = tenant.owns_corpus()
        finally:
            tenant.reset()
        mark = "OWNS THE CORPUS" if owns else "scoped to itself"
        print(f"  {email:<28} {code:<16} {mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
