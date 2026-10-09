"""Is New Mexico actually open on this deployment, and gated correctly?

A scratch check, run on the server after a deploy. The tests prove the rules;
this proves the rules are the ones running on the box somebody is about to
register through.
"""

from __future__ import annotations

from app import states, tenancy


def main() -> int:
    print("open states:", sorted(states.LAUNCH_STATES))
    for agency in states.agencies_for("NM"):
        print(f"  {agency['id']}  @{agency['domain']}  {agency['name']}")
        print(f"  convention: {agency['convention']}  "
              f"confidence: {agency['confidence']}")

    print("\nregistration gate:")
    for address in ("jane.doe@env.nm.gov", "jdoe@env.nm.gov",
                    "jane@gmail.com", "jane@nm.gov",
                    "jane@env.nm.gov.example.com", "jane.doe@des.sc.gov"):
        checked = tenancy.check_identity("nm.env", "Jane Doe", address)
        mark = "OK " if checked.ok else "NO "
        print(f"  {mark} {address:<30} {checked.reason[:52]}")

    print("\nthe other agency still refuses a New Mexico address:")
    crossed = tenancy.check_identity("sc.des", "Jane Doe",
                                     "jane.doe@env.nm.gov")
    print(f"  sc.des <- @env.nm.gov : {'OK' if crossed.ok else 'refused'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
