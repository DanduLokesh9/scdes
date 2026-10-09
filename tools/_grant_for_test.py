"""Grant or revoke a local entitlement, to test the gate it controls.

`settle_invoice` is admin-only and an admin is an address somebody has
*proven*, not one passed in a query string — which is why settling over HTTP
with `?email=brett@iiac.ai` is correctly refused. That refusal is the control
working, so this tests the other half instead: given an entitlement, does the
paid gate open, and given none, does it shut?

Local only, and it says which file it touched.

    python -m tools._grant_for_test gaius.harness grant
    python -m tools._grant_for_test gaius.harness revoke
"""

from __future__ import annotations

import sys

from app import billing


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    agency, what = argv[0], argv[1]

    if what == "grant":
        billing.set_plan({"amount": 4800, "currency": "USD",
                          "term_months": 12}, _Admin())
        out = billing.start_order(agency, billing.BY_INVOICE, _Admin())
        order = out["order"]
        billing.settle_invoice(order["id"], _Admin(),
                               reference="LOCAL-TEST-ONLY")
    elif what == "revoke":
        held = billing._read()
        held["entitlements"].pop(agency, None)
        billing._write(held)
    else:
        print(f"unknown action {what!r}")
        return 1

    print(f"file    : {billing.BILLING_FILE}")
    print(f"agency  : {agency}")
    print(f"state   : {billing.entitlement(agency)}")
    return 0


class _Admin:
    """The first of the three addresses the client named as administrators."""
    user_id = "gaius.admin"
    name = "local test"
    email = "brett@iiac.ai"
    role = type("R", (), {"value": "ot"})()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
