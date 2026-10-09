"""The GAIUS team's half of the invoice route.

An organization could request an invoice and the server could record one as
paid, but nothing listed the orders anybody at IIA would settle from — so no
organization could become subscribed through the application. These tests
pin the listing, the lock on it, and the whole round trip: an organization
asks, an admin marks it paid with a reference, and the organization is
subscribed.
"""

from __future__ import annotations

import pytest

from app import billing, server, tenant
from app.authz import Actor, Role

STAFF = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff",
              email="dana.reed@des.sc.gov")
ADMIN = Actor("gaius.admin", "Brett Butz", Role.OT, title="IIA",
              email="brett@iiac.ai")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "BILLING_FILE", tmp_path / "billing.json")
    monkeypatch.delenv("IIA_SUBSCRIPTION", raising=False)
    yield


def _order(agency: str) -> str:
    token = tenant.set_current(agency)
    try:
        made = billing.start_order(agency, "invoice", STAFF)
    finally:
        tenant.reset(token)
    assert made["ok"], made
    return made["order"]["id"]


def test_the_listing_is_refused_to_anybody_but_the_gaius_team() -> None:
    refused = server.api_billing_admin(STAFF, {}, {})
    assert refused["ok"] is False
    assert "orders" not in refused


def test_the_listing_shows_every_organizations_orders_to_an_admin() -> None:
    _order("sc.des")
    _order("tx.env")
    got = server.api_billing_admin(ADMIN, {}, {})
    assert got["ok"] is True
    assert {o["agency"] for o in got["orders"]} == {"sc.des", "tx.env"}
    assert got["pending"] == 2


def test_each_order_carries_the_organizations_name() -> None:
    _order("tx.env")
    order = server.api_billing_admin(ADMIN, {}, {})["orders"][0]
    assert order["agency_label"] == \
        "Texas Commission on Environmental Quality"


def test_the_listing_leaks_no_internals() -> None:
    """No fingerprints — the idempotency key is not a screen's business."""
    _order("sc.des")
    order = server.api_billing_admin(ADMIN, {}, {})["orders"][0]
    assert "fingerprint" not in order
    assert "history" not in order


def test_an_organization_still_sees_only_its_own_orders() -> None:
    """The admin listing crosses organizations; nothing else may."""
    _order("sc.des")
    _order("tx.env")
    mine = billing.listing("tx.env")["orders"]
    assert len(mine) == 1


def test_the_round_trip_subscribes_the_organization() -> None:
    """Ask, settle with a reference, subscribed — the thing that could not
    happen through the application before."""
    order_id = _order("iia.test")
    assert not billing.entitled("iia.test")
    settled = server.api_billing_settle(
        ADMIN, {"order": order_id, "reference": "ACH 0042"}, {})
    assert settled["ok"], settled
    assert billing.entitled("iia.test")
    listed = server.api_billing_admin(ADMIN, {}, {})
    assert listed["pending"] == 0
    assert any(e["agency"] == "iia.test" and e["state"] == "active"
               for e in listed["entitlements"])


def test_settling_still_needs_a_reference() -> None:
    order_id = _order("iia.test")
    refused = server.api_billing_settle(ADMIN, {"order": order_id}, {})
    assert refused["ok"] is False
    assert not billing.entitled("iia.test")


def test_settling_is_still_refused_to_anybody_but_the_gaius_team() -> None:
    order_id = _order("iia.test")
    refused = server.api_billing_settle(
        STAFF, {"order": order_id, "reference": "ACH 0042"}, {})
    assert refused["ok"] is False
    assert not billing.entitled("iia.test")


def test_the_route_is_registered() -> None:
    assert server.ROUTES[("GET", "/api/billing/admin")] is \
        server.api_billing_admin
