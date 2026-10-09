"""Mint or retire a session token, on the machine the store lives on.

The normal way to get one is to sign in: the verification code proves the
mailbox and the server issues the token. This is for the two cases that sits
outside that — checking the admin boundary from outside the browser, and
getting an admin back in when mail delivery is not working yet.

It is deliberately a separate script rather than an endpoint. Minting a token
without a code is exactly the thing the token exists to prevent, so it should
require a shell on the server, not a URL.

    python3 deploy/session_tool.py mint brett@iiac.ai
    python3 deploy/session_tool.py retire <token>
    python3 deploy/session_tool.py retire-all brett@iiac.ai
    python3 deploy/session_tool.py list
"""

from __future__ import annotations

import sys

from app import admin, tenancy


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    what = argv[1]

    if what == "mint":
        if len(argv) < 3:
            print("mint needs an address")
            return 2
        address = argv[2].strip().lower()
        token = tenancy.issue_session(address)
        print(token)
        if not admin.is_admin(address):
            print(f"note: {address} is not an admin — this token proves the "
                  f"address and nothing more", file=sys.stderr)
        return 0

    if what == "retire":
        if len(argv) < 3:
            print("retire needs a token")
            return 2
        tenancy.end_session(argv[2])
        print("retired")
        return 0

    if what == "retire-all":
        # Only hashes are stored, so a token that has been lost cannot be
        # handed back to revoke it. Testing leaves exactly that: working
        # credentials nobody holds and nobody could cancel.
        if len(argv) < 3:
            print("retire-all needs an address")
            return 2
        n = tenancy.end_sessions_for(argv[2])
        print(f"retired {n} session(s) for {argv[2]}")
        return 0

    if what == "list":
        rows = tenancy._load().get("sessions", {})
        print(f"{len(rows)} live session(s)")
        for row in rows.values():
            flag = " (admin)" if admin.is_admin(row.get("email")) else ""
            print(f"  {row.get('email')}{flag}  expires {row.get('expires')}")
        return 0

    print(f"unknown command {what!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
