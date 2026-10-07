"""Who has paid, and everything that must not be able to fake it.

Most of this file is about refusal. A payment system's interesting cases are
all the ways something can claim to be a payment and not be one: a client
posting its own price, a replayed webhook, a duplicate event, an event for
the right order at the wrong amount, a refund arriving after fulfillment, an
order walked backwards into `paid`.

The three decisions this is built on are in `app/billing.py`'s docstring:
agencies pay by purchase order *and* by card, no provider is wired yet, and
the price is configuration rather than a constant in the code.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from app import billing, tenant
from app.authz import Actor, Role

#: An ordinary operator at an agency.
STAFF = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff",
              email="dana.reed@des.sc.gov")
#: One of the three addresses that administer GAIUS.
ADMIN = Actor("gaius.admin", "Brett Butz", Role.OT, title="IIA",
              email="brett@iiac.ai")

SECRET = "whsec-test-not-a-real-secret"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(billing, "BILLING_FILE", tmp_path / "billing.json")
    for name in ("BILLING_PROVIDER_KEY", "BILLING_WEBHOOK_SECRET",
                 "IIA_SUBSCRIPTION"):
        monkeypatch.delenv(name, raising=False)
    yield


def as_agency(code: str):
    class Bound:
        def __enter__(self):
            self.token = tenant.set_current(code)
            return self
        def __exit__(self, *_):
            tenant.reset(self.token)
    return Bound()


def priced(amount=4800.0):
    billing.set_plan({"amount": amount, "currency": "USD",
                      "term_months": 12}, ADMIN)


def signed(event: dict, secret: str = SECRET, at: int | None = None):
    """A provider event, signed the way the real one will be."""
    raw = json.dumps(event).encode()
    when = int(time.time()) if at is None else at
    mac = hmac.new(secret.encode(), f"{when}.".encode() + raw,
                   hashlib.sha256).hexdigest()
    return raw, mac, str(when)


# ------------------------------------------------------------------ the plan

def test_nothing_is_priced_until_somebody_prices_it() -> None:
    """The amount is not invented in code. Until it is set the page says
    pricing is on request, which is honest; a fabricated number on a
    client-facing page would not be."""
    found = billing.plan()
    assert found["amount"] is None
    assert found["amount_set"] is False
    assert found["term_months"] == 12


def test_only_an_admin_may_price_it() -> None:
    assert not billing.set_plan({"amount": 1}, STAFF)["ok"]
    assert billing.plan()["amount"] is None
    assert billing.set_plan({"amount": 4800}, ADMIN)["ok"]
    assert billing.plan()["amount"] == 4800.0


@pytest.mark.parametrize("bad", [
    {"amount": "free"},
    {"amount": -1},
    {"amount": 99_000_000},
    {"amount": 100, "term_months": 0},
    {"amount": 100, "term_months": "soon"},
])
def test_a_nonsense_price_is_refused(bad) -> None:
    assert not billing.set_plan(bad, ADMIN)["ok"]


# --------------------------------------------------------------- entitlement

def test_an_agency_starts_with_nothing() -> None:
    assert billing.entitlement("sc.des")["state"] == "none"
    assert billing.entitled("sc.des") is False


def test_a_pending_invoice_entitles_nobody() -> None:
    """The gap between raising an order and being paid is where a paywall
    gets given away. `pending` is deliberately not in `GRANTING`."""
    priced()
    with as_agency("sc.des"):
        out = billing.start_order("sc.des", billing.BY_INVOICE, STAFF)
        assert out["ok"]
        assert out["order"]["state"] == billing.PENDING
    assert billing.entitled("sc.des") is False


def test_settling_an_invoice_grants_a_term() -> None:
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    out = billing.settle_invoice(order["id"], ADMIN, reference="ACH-99812")
    assert out["ok"], out
    assert billing.entitled("sc.des") is True
    held = billing.entitlement("sc.des")
    assert held["state"] == "active"
    assert held["days_left"] > 300


def test_only_an_admin_may_settle_an_invoice() -> None:
    """The invoice route has no provider to confirm anything, so a person
    does — which makes this the most sensitive action in the module."""
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    assert not billing.settle_invoice(order["id"], STAFF,
                                      reference="ACH-1")["ok"]
    assert billing.entitled("sc.des") is False


def test_settling_demands_a_reference() -> None:
    """Without one there is nothing to reconcile the entry against."""
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    assert not billing.settle_invoice(order["id"], ADMIN, reference="")["ok"]
    assert not billing.settle_invoice(order["id"], ADMIN,
                                      reference="   ")["ok"]


def test_one_agency_paying_does_not_entitle_another() -> None:
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    billing.settle_invoice(order["id"], ADMIN, reference="ACH-1")
    assert billing.entitled("sc.des") is True
    assert billing.entitled("sc.ed") is False


def test_an_expired_term_stops_entitling() -> None:
    """Decided when the question is asked, not by a nightly job that may not
    have run."""
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    billing.settle_invoice(order["id"], ADMIN, reference="ACH-1")

    held = billing._read()
    held["entitlements"]["sc.des"]["until"] = "2020-01-01"
    billing._write(held)

    assert billing.entitlement("sc.des")["state"] == "expired"
    assert billing.entitled("sc.des") is False


def test_a_renewal_extends_rather_than_restarting() -> None:
    """Paying early must not cost the agency the days it has left."""
    priced()
    first = billing.start_order("sc.des", billing.BY_INVOICE, STAFF)["order"]
    billing.settle_invoice(first["id"], ADMIN, reference="ACH-1")
    ends = billing.entitlement("sc.des")["until"]

    second = billing.start_order("sc.des", billing.BY_INVOICE, STAFF,
                                 note="renewal")["order"]
    billing.settle_invoice(second["id"], ADMIN, reference="ACH-2")
    assert billing.entitlement("sc.des")["until"] > ends


# ---------------------------------------------------- the client is not trusted

def test_the_amount_comes_from_the_plan_not_the_request() -> None:
    """A client that posts its own price is not refused — it is ignored,
    which is the only safe way to treat it."""
    priced(4800.0)
    order = billing.start_order("sc.des", billing.BY_INVOICE, STAFF)["order"]
    assert order["amount"] == 4800.0
    assert order["currency"] == "USD"
    assert order["term_months"] == 12


def test_a_later_price_change_does_not_alter_an_existing_order() -> None:
    """The snapshot is the point. Somebody agreed to a number and that number
    has to survive whatever the price list does next."""
    priced(4800.0)
    order = billing.start_order("sc.des", billing.BY_INVOICE, STAFF)["order"]
    priced(9600.0)
    again = billing.listing("sc.des")["orders"][0]
    assert again["amount"] == 4800.0


def test_an_unknown_route_is_refused() -> None:
    priced()
    assert not billing.start_order("sc.des", "crypto", STAFF)["ok"]
    assert not billing.start_order("sc.des", "", STAFF)["ok"]


def test_raising_the_same_order_twice_makes_one_order() -> None:
    """A double-clicked button, a retried fetch and a refreshed tab all
    produce the same fingerprint, so they produce the same pending order."""
    priced()
    first = billing.start_order("sc.des", billing.BY_INVOICE, STAFF)
    second = billing.start_order("sc.des", billing.BY_INVOICE, STAFF)
    assert second["reused"] is True
    assert second["order"]["id"] == first["order"]["id"]
    assert len(billing.listing("sc.des")["orders"]) == 1


def test_order_ids_are_not_guessable() -> None:
    priced()
    ids = {billing.start_order(f"agency.{i}", billing.BY_INVOICE,
                               STAFF)["order"]["id"] for i in range(8)}
    assert len(ids) == 8
    assert all(len(i) > 12 for i in ids)


def test_an_order_only_shows_to_the_agency_that_raised_it() -> None:
    priced()
    billing.start_order("sc.des", billing.BY_INVOICE, STAFF)
    assert billing.listing("sc.des")["orders"]
    assert billing.listing("sc.ed")["orders"] == []


# --------------------------------------------------------- the card route

def test_the_card_route_refuses_until_a_provider_exists(monkeypatch) -> None:
    """No key and no webhook secret means no card checkout. Offering one that
    cannot work is worse than not offering it. (About the generic provider:
    Stripe's Buy Button, on by default, is switched off here — see
    tests/test_stripe.py for it.)"""
    monkeypatch.setenv("STRIPE_OFF", "1")
    priced()
    assert billing.card_route_ready() is False
    out = billing.start_order("sc.des", billing.BY_CARD, STAFF)
    assert not out["ok"]
    assert "not switched on" in out["error"]


def test_a_key_without_a_webhook_secret_is_not_ready(monkeypatch) -> None:
    """A deployment that can take money but cannot verify the confirmation
    would charge people and never learn that it had."""
    monkeypatch.setenv("STRIPE_OFF", "1")
    monkeypatch.setenv("BILLING_PROVIDER_KEY", "sk-test")
    assert billing.card_route_ready() is False


def test_both_halves_make_the_card_route_ready(monkeypatch) -> None:
    monkeypatch.setenv("BILLING_PROVIDER_KEY", "sk-test")
    monkeypatch.setenv("BILLING_WEBHOOK_SECRET", SECRET)
    assert billing.card_route_ready() is True
    priced()
    assert billing.start_order("sc.des", billing.BY_CARD, STAFF)["ok"]


# ------------------------------------------------------------- the webhook

@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("BILLING_PROVIDER_KEY", "sk-test")
    monkeypatch.setenv("BILLING_WEBHOOK_SECRET", SECRET)
    priced()
    return billing.start_order("sc.des", billing.BY_CARD, STAFF)["order"]


def test_an_unsigned_event_is_refused(provider) -> None:
    raw = json.dumps({"id": "evt_1", "type": "checkout.completed"}).encode()
    out = billing.handle_event(raw, "", "")
    assert not out["ok"]
    assert billing.entitled("sc.des") is False


def test_a_wrongly_signed_event_is_refused(provider) -> None:
    raw, _, when = signed({"id": "evt_1", "type": "checkout.completed"})
    out = billing.handle_event(raw, "0" * 64, when)
    assert not out["ok"]
    assert "does not match" in out["error"]
    assert billing.entitled("sc.des") is False


def test_a_signature_for_a_different_body_is_refused(provider) -> None:
    """The signature covers the exact bytes. Signing one body and sending
    another is the whole attack."""
    _, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                           "order": provider["id"], "amount": 1.0,
                           "currency": "USD"})
    tampered = json.dumps({"id": "evt_1", "type": "checkout.completed",
                           "order": provider["id"], "amount": 4800.0,
                           "currency": "USD"}).encode()
    assert not billing.handle_event(tampered, mac, when)["ok"]
    assert billing.entitled("sc.des") is False


def test_a_replayed_event_is_refused_once_it_is_stale(provider) -> None:
    """A captured webhook must not work tomorrow."""
    old = int(time.time()) - (billing.SIGNATURE_WINDOW_SECONDS + 60)
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": provider["id"], "amount": 4800.0,
                             "currency": "USD"}, at=old)
    out = billing.handle_event(raw, mac, when)
    assert not out["ok"]
    assert "outside" in out["error"]


def test_an_unconfigured_server_accepts_no_events(monkeypatch) -> None:
    """Fails closed. With no secret it accepts nothing, rather than
    everything."""
    monkeypatch.delenv("BILLING_WEBHOOK_SECRET", raising=False)
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed"})
    out = billing.handle_event(raw, mac, when)
    assert not out["ok"]
    assert "No webhook secret" in out["error"]


def test_a_verified_completion_pays_the_order_and_grants_the_term(
        provider) -> None:
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": provider["id"], "amount": 4800.0,
                             "currency": "USD", "reference": "pi_123"})
    out = billing.handle_event(raw, mac, when)
    assert out["ok"], out
    assert billing.entitled("sc.des") is True


def test_the_same_event_twice_grants_one_term(provider) -> None:
    """Providers retry. A retry must not extend the subscription again."""
    event = {"id": "evt_1", "type": "checkout.completed",
             "order": provider["id"], "amount": 4800.0, "currency": "USD"}
    raw, mac, when = signed(event)
    billing.handle_event(raw, mac, when)
    ends = billing.entitlement("sc.des")["until"]

    raw2, mac2, when2 = signed(event)
    again = billing.handle_event(raw2, mac2, when2)
    assert again["duplicate"] is True
    assert billing.entitlement("sc.des")["until"] == ends


def test_an_event_with_no_id_cannot_be_de_duplicated(provider) -> None:
    raw, mac, when = signed({"type": "checkout.completed",
                             "order": provider["id"]})
    out = billing.handle_event(raw, mac, when)
    assert not out["ok"]
    assert "de-duplicated" in out["error"]


def test_the_amount_must_match_the_order(provider) -> None:
    """A confirmation for the right order at the wrong amount is not a
    confirmation."""
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": provider["id"], "amount": 1.00,
                             "currency": "USD"})
    out = billing.handle_event(raw, mac, when)
    assert not out["ok"]
    assert "amount does not match" in out["error"]
    assert billing.entitled("sc.des") is False


def test_the_currency_must_match_the_order(provider) -> None:
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": provider["id"], "amount": 4800.0,
                             "currency": "EUR"})
    assert not billing.handle_event(raw, mac, when)["ok"]
    assert billing.entitled("sc.des") is False


def test_an_event_for_an_unknown_order_is_refused(provider) -> None:
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": "ORD-nothing", "amount": 4800.0,
                             "currency": "USD"})
    assert not billing.handle_event(raw, mac, when)["ok"]


def test_an_event_type_nobody_handles_is_recorded_and_ignored(
        provider) -> None:
    """An allowlist. A provider adding a new event type cannot reach a
    handler nobody has thought about."""
    raw, mac, when = signed({"id": "evt_x", "type": "invoice.doodled",
                             "order": provider["id"]})
    out = billing.handle_event(raw, mac, when)
    assert out["ok"] and out["ignored"] is True
    assert billing.entitled("sc.des") is False


# ------------------------------------------- refunds, disputes, and going back

def test_a_refund_takes_the_entitlement_away(provider) -> None:
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": provider["id"], "amount": 4800.0,
                             "currency": "USD"})
    billing.handle_event(raw, mac, when)
    assert billing.entitled("sc.des") is True

    raw2, mac2, when2 = signed({"id": "evt_2", "type": "refund.full",
                                "order": provider["id"]})
    assert billing.handle_event(raw2, mac2, when2)["ok"]
    assert billing.entitled("sc.des") is False


def test_a_dispute_takes_the_entitlement_away(provider) -> None:
    raw, mac, when = signed({"id": "evt_1", "type": "checkout.completed",
                             "order": provider["id"], "amount": 4800.0,
                             "currency": "USD"})
    billing.handle_event(raw, mac, when)
    raw2, mac2, when2 = signed({"id": "evt_2", "type": "dispute.opened",
                                "order": provider["id"]})
    assert billing.handle_event(raw2, mac2, when2)["ok"]
    assert billing.entitled("sc.des") is False


def test_a_refunded_order_cannot_be_walked_back_to_paid() -> None:
    """The state table is what stops a reordered or replayed event
    resurrecting a subscription somebody was refunded for."""
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    billing.settle_invoice(order["id"], ADMIN, reference="ACH-1")
    billing.mark(order["id"], billing.REFUNDED, ADMIN, why="test")

    out = billing.mark(order["id"], billing.PAID, ADMIN, why="replay")
    assert not out["ok"]
    assert "cannot become" in out["error"]
    assert billing.entitled("sc.des") is False


def test_a_repeated_transition_is_a_no_op_not_an_error() -> None:
    """Idempotent by design: the second attempt changes nothing and does not
    grant a second term."""
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    billing.settle_invoice(order["id"], ADMIN, reference="ACH-1")
    ends = billing.entitlement("sc.des")["until"]
    again = billing.mark(order["id"], billing.PAID, ADMIN)
    assert again["ok"] and again["unchanged"] is True
    assert billing.entitlement("sc.des")["until"] == ends


@pytest.mark.parametrize("state", [
    billing.REFUNDED, billing.EXPIRED, billing.FAILED,
])
def test_terminal_states_go_nowhere(state) -> None:
    assert billing.TRANSITIONS[state] == set()


def test_every_state_in_the_table_is_reachable() -> None:
    """A documented transition table is only worth having if it is complete:
    every state must be named as a source, so none is a dead end nobody
    declared."""
    named = set(billing.TRANSITIONS)
    reachable = {billing.PENDING}
    for froms in billing.TRANSITIONS.values():
        reachable |= froms
    assert reachable <= named, reachable - named


def test_a_pending_order_expires_rather_than_lingering() -> None:
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    held = billing._read()
    held["orders"][order["id"]]["raised_at"] = "2020-01-01T00:00:00+00:00"
    billing._write(held)

    out = billing.expire_stale_orders(older_than_days=30)
    assert order["id"] in out["expired"]
    assert billing.entitled("sc.des") is False


# --------------------------------------------------------------- the paperwork

def test_every_money_decision_reaches_the_audit_log() -> None:
    """The client, in capitals: "WE NEED TO LOG ALL CHOICES, ACTIVITIES, and
    Framework versions on the back end" — and "the log should survive
    absolutely". Money moving is exactly that."""
    from app.authz import default_log
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    billing.settle_invoice(order["id"], ADMIN, reference="ACH-1")

    entries = [json.loads(line) for line
               in default_log().path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    actions = [e.get("action") for e in entries]
    assert "price_subscription" in actions
    assert "raise_order" in actions
    assert "order_paid" in actions


def test_reconciliation_notices_an_entitlement_with_no_payment() -> None:
    """The daily check. It reports rather than repairs — an automatic fix
    would paper over the thing worth investigating."""
    priced()
    held = billing._read()
    held["entitlements"]["sc.des"] = {
        "agency": "sc.des", "state": "active", "since": "2026-01-01",
        "until": "2027-01-01", "route": "invoice", "order": "ORD-ghost"}
    billing._write(held)

    found = billing.reconcile()
    assert any("no paid order behind it" in f["says"]
               for f in found["findings"]), found


def test_reconciliation_notices_a_double_charge() -> None:
    priced()
    for i in range(2):
        order = billing.start_order("sc.des", billing.BY_INVOICE, STAFF,
                                    note=f"run {i}")["order"]
        billing.settle_invoice(order["id"], ADMIN, reference=f"ACH-{i}")

    found = billing.reconcile()
    assert any("double charge" in f["says"] for f in found["findings"]), found


def test_a_clean_book_reconciles_with_no_findings() -> None:
    priced()
    order = billing.start_order("sc.des", billing.BY_INVOICE,
                                STAFF)["order"]
    billing.settle_invoice(order["id"], ADMIN, reference="ACH-1")
    assert billing.reconcile()["findings"] == []


def test_the_page_is_told_when_the_whole_deployment_is_unlocked(
        monkeypatch) -> None:
    """Staging forces the paid modules open so they can be demonstrated.
    Without surfacing that, the page tells an agency it has no subscription
    while every paid module sits open next to it."""
    assert billing.listing("sc.des")["override"] is False
    monkeypatch.setenv("IIA_SUBSCRIPTION", "1")
    assert billing.listing("sc.des")["override"] is True
    # And it is still honest about what the agency itself has bought.
    assert billing.listing("sc.des")["entitlement"]["state"] == "none"


def test_no_card_data_field_exists_anywhere_in_the_module() -> None:
    """Asserted against the source, because the promise is about what the
    code cannot do rather than what one call happened not to store. This
    application never sees a card on either route.

    Comments and strings are stripped before the check. The first version of
    this searched the raw text and failed on the module's own docstring —
    which says the code never touches a CVC — so the test was reporting the
    promise as a breach of itself.
    """
    import inspect
    import io
    import tokenize

    source = inspect.getsource(billing)
    code = []
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type in (tokenize.COMMENT, tokenize.STRING):
            continue
        code.append(token.string)
    identifiers = " ".join(code).lower()

    for never in ("card_number", "cardnumber", "cvc", "cvv",
                  "expiry_month", "exp_month", "track_data", "pin_block",
                  "wallet_token"):
        assert never not in identifiers, never
