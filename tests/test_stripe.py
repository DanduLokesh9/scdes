"""Paying by card through Stripe's Buy Button (Oct 2026, from IIA's CFO).

The button's public settings reach the Subscription page and nothing secret
does; a card order is raised first and its number travels to Stripe as the
client reference; Stripe's signed webhook marks that order paid — once, at
the right amount — and a forged or stale one is refused.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import threading
import time
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app import billing, server
from app.authz import Actor, Role

SECRET = "whsec_test_secret"


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "BILLING_FILE", tmp_path / "billing.json")
    for name in ("STRIPE_OFF", "STRIPE_PUBLISHABLE_KEY", "STRIPE_BUY_BUTTON_ID",
                 "STRIPE_PAYMENT_LINK", "STRIPE_WEBHOOK_SECRET"):
        monkeypatch.delenv(name, raising=False)
    return tmp_path


def _order(monkeypatch, amount=None):
    if amount is not None:
        monkeypatch.setattr(billing, "plan", lambda: {"amount": amount, "currency": "USD",
                            "term_months": 12, "amount_set": True, "name": "Annual"})
    who = Actor("u", "Jane Smith", Role.OPERATOR, email="jane@ed.sc.gov")
    out = billing.start_order("sc.ed", billing.BY_CARD, who)
    assert out["ok"], out
    return out["order"]["id"]


def _signed(event: dict, secret: str = SECRET, at: int | None = None) -> tuple[bytes, str]:
    raw = json.dumps(event).encode()
    t = str(at if at is not None else int(time.time()))
    sig = hmac.new(secret.encode(), t.encode() + b"." + raw, hashlib.sha256).hexdigest()
    return raw, f"t={t},v1={sig}"


def _completed(order: str, cents: int = 0, eid: str = "evt_1", status: str = "paid") -> dict:
    return {"id": eid, "type": "checkout.session.completed",
            "data": {"object": {"id": "cs_test_1", "client_reference_id": order,
                                "payment_status": status, "amount_total": cents,
                                "currency": "usd", "payment_intent": "pi_test_1"}}}


# ----------------------------------------------------------- the page

def test_the_page_gets_the_button_and_nothing_secret(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    sp = billing.listing("sc.ed")["stripe"]
    assert sp["available"] and sp["test_mode"] and sp["confirms_itself"]
    assert sp["buy_button_id"].startswith("buy_btn_") and sp["publishable_key"].startswith("pk_test_")
    assert sp["payment_link"].startswith("https://buy.stripe.com/")
    assert SECRET not in json.dumps(sp)


def test_live_keys_come_from_the_server_settings(store, monkeypatch):
    monkeypatch.setenv("STRIPE_PUBLISHABLE_KEY", "pk_live_abc")
    monkeypatch.setenv("STRIPE_BUY_BUTTON_ID", "buy_btn_live")
    sp = billing.stripe()
    assert sp["test_mode"] is False and sp["buy_button_id"] == "buy_btn_live"


def test_card_orders_can_be_raised(store, monkeypatch):
    assert billing.card_route_ready()
    assert _order(monkeypatch).startswith("ORD-")


def test_it_can_be_switched_off(store, monkeypatch):
    monkeypatch.setenv("STRIPE_OFF", "1")
    monkeypatch.delenv("BILLING_PROVIDER_KEY", raising=False)
    assert not billing.card_route_ready()


# ----------------------------------------------------------- the signature

def test_a_good_signature_passes_and_bad_ones_do_not(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    raw, header = _signed({"id": "evt"})
    assert billing.stripe_verify(raw, header)[0]
    assert not billing.stripe_verify(raw + b" ", header)[0]               # body changed
    assert not billing.stripe_verify(raw, _signed({"id": "evt"}, "whsec_other")[1])[0]
    old_raw, old = _signed({"id": "evt"}, at=int(time.time()) - 3600)
    assert "seconds old" in billing.stripe_verify(old_raw, old)[1]       # replay


def test_without_the_secret_nothing_is_trusted(store):
    raw, header = _signed({"id": "evt"})
    ok, why = billing.stripe_verify(raw, header)
    assert not ok and "No Stripe webhook secret" in why


# ----------------------------------------------------------- the event

def test_a_paid_checkout_marks_the_order_paid_once(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    order = _order(monkeypatch, amount=1200)
    raw, header = _signed(_completed(order, 120000))
    out = billing.stripe_event(raw, header)
    assert out.get("ok"), out
    held = json.loads(billing.BILLING_FILE.read_text())["orders"][order]
    assert held["state"] == billing.PAID and held.get("reference") == "pi_test_1"
    assert billing.stripe_event(raw, header)["duplicate"]


def test_the_wrong_amount_is_refused(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    order = _order(monkeypatch, amount=1200)
    out = billing.stripe_event(*_signed(_completed(order, 100)))
    assert out["ok"] is False and "amount" in out["error"]


def test_an_unpaid_checkout_waits(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    order = _order(monkeypatch)
    out = billing.stripe_event(*_signed(_completed(order, status="unpaid")))
    assert out["waiting"]


def test_a_payment_with_no_order_is_recorded_for_the_team(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    out = billing.stripe_event(*_signed(_completed("ORD-nothing")))
    assert out["ok"] is False and out["unmatched"]


def test_other_events_are_ignored(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    out = billing.stripe_event(*_signed({"id": "evt_x", "type": "customer.created"}))
    assert out["ignored"]


# ----------------------------------------------------------- over HTTP

def test_the_endpoint_answers_stripe_the_right_way(store, monkeypatch):
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", SECRET)
    order = _order(monkeypatch)
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{httpd.server_address[1]}"

    def call(raw, header):
        req = urllib.request.Request(base + "/api/billing/stripe", data=raw, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Stripe-Signature": header})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
    try:
        raw, header = _signed(_completed(order, eid="evt_http"))
        assert call(raw, "t=1,v1=forged") == 400
        assert call(raw, header) == 200
    finally:
        httpd.shutdown()
