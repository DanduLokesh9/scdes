"""Who has paid, what for, and until when.

Three decisions were taken before any of this was written, because each one
changes the shape of the code rather than its details:

**Agencies pay by purchase order *and* by card.** Public bodies overwhelmingly
buy software on a PO against an invoice, and many are barred outright from
putting a card-on-file subscription in place. A card-only checkout would be
unusable for exactly the customers this product is for. So the invoice route
is the one that works today and the card route is built beside it.

**No provider is wired.** The card route needs an account, a secret key, a
price identifier and a webhook secret, none of which exist yet. Rather than
guess at one provider's API, the parts that do not depend on the provider —
entitlement, the order state machine, idempotency, the webhook's
verification and de-duplication — are built and tested, and the card route
refuses to start until a provider is configured. Same rule as the mail
fallback: a feature that cannot work says so rather than failing oddly.

**The price is not invented here.** One annual subscription per agency, with
the amount read from configuration. Until somebody sets it, the page says
pricing is on request. A fabricated number on a client-facing page is worse
than no number, and what to charge is not a decision this module gets to
make.

Where this lives, and why it is not in the tenant's container
-------------------------------------------------------------

Entitlement is written to ``data/billing.json``, beside the tenancy register
and *outside* every agency's own directory. That is deliberate. An agency can
take a snapshot of its own container and restore it, and can erase the whole
thing from the Framework screen — so an entitlement stored in there could be
rolled back to a paid state after a refund, or destroyed by somebody clearing
their answers. Neither is acceptable for the record of who has paid.

What this module will not do
----------------------------

It never sees a card. No card number, expiry, CVC or wallet credential
reaches this application at any point, on either route: the card route hands
off to a provider's own hosted page, and the invoice route involves no
instrument at all. That keeps the card data environment out of scope, which
is a statement about *scope* and not a claim of PCI compliance — see
`docs/PAYMENTS.md`.

It never takes an amount, a currency, a plan or a payment status from a
client. Every one of those is loaded server-side from the plan or from a
verified provider event.
"""

from __future__ import annotations

from app import clock  # "today" where the person is

import hashlib
import hmac
import json
import os
import pathlib
import secrets
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.audit import atomic_write

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: Cross-tenant, and outside any agency's container on purpose — see the
#: module docstring. `data/` is also excluded from the deploy bundle, so a
#: push cannot overwrite who has paid with whatever was on a laptop.
BILLING_FILE = ROOT / "data" / "billing.json"

#: One lock for the file. Two agencies subscribing in the same second must not
#: interleave a read-modify-write and lose one of them — the same fault that
#: was found in the audit log.
_LOCK = threading.Lock()

# --------------------------------------------------------------- the states
#
# The order lifecycle. Every transition a payment can make is named here, and
# `_may_move` refuses anything absent from this table — so an unexpected or
# replayed provider event cannot walk an order backwards into `paid`.

PENDING = "pending"
PAID = "paid"
FULFILLED = "fulfilled"
EXPIRED = "expired"
FAILED = "failed"
REVIEW = "payment_review"
PART_REFUNDED = "partially_refunded"
REFUNDED = "refunded"
DISPUTED = "disputed"

#: from -> what it may become. Terminal states map to an empty set.
TRANSITIONS: dict[str, set[str]] = {
    PENDING: {PAID, REVIEW, EXPIRED, FAILED},
    # `paid` may still go to review: a provider can flag a payment after
    # accepting it, and that must be able to stop fulfilment.
    PAID: {FULFILLED, REVIEW, REFUNDED, PART_REFUNDED, DISPUTED},
    REVIEW: {PAID, FAILED, REFUNDED, DISPUTED},
    FULFILLED: {REFUNDED, PART_REFUNDED, DISPUTED},
    PART_REFUNDED: {REFUNDED, DISPUTED},
    DISPUTED: {REFUNDED, PART_REFUNDED, PAID},
    REFUNDED: set(),
    EXPIRED: set(),
    FAILED: set(),
}

#: An order in one of these states entitles the agency to the paid modules.
#: Deliberately short: `pending` is not on it, so an unpaid invoice grants
#: nothing, and neither does a refund or a dispute.
GRANTING = {PAID, FULFILLED, PART_REFUNDED}

#: How the order was raised. Validated against this rather than taken from
#: the request.
BY_INVOICE = "invoice"
BY_CARD = "card"
ROUTES = {
    BY_INVOICE: "Purchase order and invoice",
    BY_CARD: "Card, on the provider's own page",
}

#: Provider events this application will act on. Anything else is recorded
#: and ignored — an allowlist, so a provider adding a new event type cannot
#: reach a handler nobody has thought about.
HANDLED_EVENTS = {
    "checkout.completed": PAID,
    "payment.failed": FAILED,
    "payment.review": REVIEW,
    "checkout.expired": EXPIRED,
    "refund.full": REFUNDED,
    "refund.partial": PART_REFUNDED,
    "dispute.opened": DISPUTED,
}

#: A signed event older than this is refused, so a captured webhook cannot be
#: replayed tomorrow.
SIGNATURE_WINDOW_SECONDS = 300

#: Default term. One annual subscription per agency was the decision; the
#: amount is not set here and not set anywhere in code.
DEFAULT_TERM_MONTHS = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> dict[str, Any]:
    if not BILLING_FILE.is_file():
        return {"plan": {}, "entitlements": {}, "orders": {}, "events": {}}
    try:
        held = json.loads(BILLING_FILE.read_text(encoding="utf-8"))
    except ValueError:
        return {"plan": {}, "entitlements": {}, "orders": {}, "events": {}}
    if not isinstance(held, dict):
        return {"plan": {}, "entitlements": {}, "orders": {}, "events": {}}
    for key in ("plan", "entitlements", "orders", "events"):
        held.setdefault(key, {})
    return held


def _write(data: dict[str, Any]) -> None:
    atomic_write(BILLING_FILE, json.dumps(data, indent=2))


# ------------------------------------------------------------------ the plan

def plan() -> dict[str, Any]:
    """What is on sale, and whether anybody has priced it.

    `amount_set` is what the page keys off. False means the subscription is
    described and an enquiry is captured, with no figure shown — which is the
    honest state until somebody decides what to charge.
    """
    held = _read().get("plan") or {}
    amount = held.get("amount")
    try:
        amount = None if amount in (None, "") else round(float(amount), 2)
    except (TypeError, ValueError):
        amount = None
    return {
        "name": held.get("name") or "Governing AI — full subscription",
        "amount": amount,
        "amount_set": amount is not None and amount > 0,
        "currency": (held.get("currency") or "USD").upper()[:3],
        "term_months": int(held.get("term_months") or DEFAULT_TERM_MONTHS),
        "covers": held.get("covers") or [],
        "note": held.get("note") or "",
        "updated_at": held.get("updated_at") or "",
        "updated_by": held.get("updated_by") or "",
    }


def set_plan(raw: dict[str, Any], actor: Any) -> dict[str, Any]:
    """Price the subscription. Admins only, and recorded.

    Deliberately an endpoint rather than a constant, so the client can set
    what to charge without a code change — and so the change is audited with
    a name against it, which is what the rest of this application does with
    every other decision.
    """
    from app import admin
    if not admin.is_admin(getattr(actor, "email", "")):
        return {"ok": False, "error": "Only the GAIUS team can price the "
                                      "subscription."}

    amount = raw.get("amount")
    try:
        amount = None if amount in (None, "") else round(float(amount), 2)
    except (TypeError, ValueError):
        return {"ok": False, "error": "That amount is not a number."}
    if amount is not None and (amount < 0 or amount > 10_000_000):
        return {"ok": False, "error": "That amount is out of range."}

    # `or DEFAULT` swallowed a zero: a posted `term_months: 0` is falsy, so
    # it silently became twelve months instead of being refused. Absent and
    # zero are different answers and have to be told apart.
    term = raw.get("term_months")
    term = DEFAULT_TERM_MONTHS if term in (None, "") else term
    try:
        term = int(term)
    except (TypeError, ValueError):
        return {"ok": False, "error": "The term must be a whole number of "
                                      "months."}
    if not 1 <= term <= 60:
        return {"ok": False, "error": "The term must be between 1 and 60 "
                                      "months."}

    with _LOCK:
        held = _read()
        held["plan"] = {
            **(held.get("plan") or {}),
            "amount": amount,
            "currency": str(raw.get("currency") or "USD").upper()[:3],
            "term_months": term,
            "note": str(raw.get("note") or "")[:400],
            "updated_at": _now(),
            "updated_by": str(getattr(actor, "name", "") or "")[:120],
        }
        _write(held)

    _record("price_subscription", actor, {"amount": amount, "term": term})
    return {"ok": True, "plan": plan()}


# ----------------------------------------------------------- what an agency has

@dataclass
class Entitlement:
    """One agency's right to the paid modules, and where it came from."""

    agency: str = ""
    state: str = "none"                  # none · active · expired · cancelled
    #: ISO dates. `until` is what `entitled()` actually tests.
    since: str = ""
    until: str = ""
    route: str = ""
    order: str = ""
    note: str = ""
    updated_at: str = ""

    def as_dict(self) -> dict[str, Any]:
        out = asdict(self)
        out["route_label"] = ROUTES.get(self.route, "")
        out["days_left"] = _days_left(self.until)
        return out


def _days_left(until: str) -> int | None:
    if not until:
        return None
    try:
        return (date.fromisoformat(until[:10]) - clock.today()).days
    except ValueError:
        return None


def entitlement(agency: str) -> dict[str, Any]:
    """What this agency is entitled to, as a fact rather than a guess."""
    held = _read().get("entitlements") or {}
    row = held.get(agency or "")
    if not row:
        return Entitlement(agency=agency or "").as_dict()
    found = Entitlement(**{k: v for k, v in row.items()
                           if k in Entitlement.__dataclass_fields__})
    # Expiry is decided when the question is asked, not by a nightly job that
    # might not have run. A term that ended yesterday is not active today.
    left = _days_left(found.until)
    if found.state == "active" and left is not None and left < 0:
        found.state = "expired"
    return found.as_dict()


def entitled(agency: str) -> bool:
    """Whether this agency may open the paid modules."""
    return entitlement(agency).get("state") == "active"


def anyone_entitled() -> bool:
    """Whether anybody at all on this deployment is paying.

    For the things that run outside a request and so have no agency to ask
    about — the accessibility monitor's clock, which sweeps every tenant.
    """
    return any(entitlement(agency).get("state") == "active"
               for agency in (_read().get("entitlements") or {}))


def _grant(held: dict[str, Any], agency: str, order: dict[str, Any],
           term_months: int) -> None:
    """Start or extend a term. Called only from a verified payment."""
    start = clock.today()
    existing = (held.get("entitlements") or {}).get(agency) or {}
    # A renewal extends from the end of the current term rather than from
    # today, so paying early does not cost the agency the days it has left.
    try:
        current_end = date.fromisoformat(str(existing.get("until"))[:10])
        if current_end > start:
            start = current_end
    except (TypeError, ValueError):
        pass
    until = start + timedelta(days=int(round(term_months * 30.44)))

    held.setdefault("entitlements", {})[agency] = asdict(Entitlement(
        agency=agency,
        state="active",
        since=existing.get("since") or clock.today().isoformat(),
        until=until.isoformat(),
        route=order.get("route", ""),
        order=order.get("id", ""),
        note=order.get("note", ""),
        updated_at=_now(),
    ))


def _revoke(held: dict[str, Any], agency: str, why: str) -> None:
    """Take the entitlement away — a refund or a dispute."""
    row = (held.get("entitlements") or {}).get(agency)
    if not row:
        return
    row["state"] = "cancelled"
    row["note"] = why
    row["updated_at"] = _now()


# ---------------------------------------------------------------- the orders

def _order_id() -> str:
    """Unpredictable, so an order cannot be found by counting upwards."""
    return "ORD-" + secrets.token_urlsafe(9).replace("-", "").replace("_", "")


def _fingerprint(agency: str, route: str, snapshot: dict[str, Any]) -> str:
    """What makes two requests 'the same request'.

    The idempotency key. A double-clicked button, a retried fetch and a
    refreshed tab all produce the same fingerprint and therefore the same
    pending order, rather than three.
    """
    material = json.dumps({"agency": agency, "route": route,
                           "amount": snapshot.get("amount"),
                           "currency": snapshot.get("currency"),
                           "term": snapshot.get("term_months")},
                          sort_keys=True)
    return hashlib.sha256(material.encode()).hexdigest()[:32]


def start_order(agency: str, route: str, actor: Any, *,
                note: str = "") -> dict[str, Any]:
    """Raise a pending order for this agency, with the amount frozen into it.

    Nothing about the money comes from the caller. The amount, currency and
    term are read from the plan here and written into the order as a
    snapshot, so a later change of price cannot alter what somebody already
    agreed to — and a client that posts its own amount is simply ignored.
    """
    if route not in ROUTES:
        return {"ok": False, "error": "Unknown payment route."}
    if not agency:
        return {"ok": False, "error": "No agency on this request."}

    if route == BY_CARD and not card_route_ready():
        return {"ok": False, "error": card_route_note()}

    current = plan()
    snapshot = {"amount": current["amount"], "currency": current["currency"],
                "term_months": current["term_months"],
                "amount_set": current["amount_set"],
                "plan_name": current["name"]}
    key = _fingerprint(agency, route, snapshot)

    with _LOCK:
        held = _read()
        orders = held.setdefault("orders", {})

        # Idempotency: an identical request that is still pending returns the
        # order it already made.
        for existing in orders.values():
            if (existing.get("fingerprint") == key
                    and existing.get("state") == PENDING):
                return {"ok": True, "order": existing, "reused": True}

        order = {
            "id": _order_id(),
            "agency": agency,
            "route": route,
            "state": PENDING,
            "fingerprint": key,
            # The immutable snapshot. Read from the plan, never from a client.
            **snapshot,
            "note": str(note or "")[:400],
            "raised_by": str(getattr(actor, "name", "") or "")[:120],
            "raised_at": _now(),
            "history": [{"state": PENDING, "at": _now(), "why": "raised"}],
        }
        orders[order["id"]] = order
        _write(held)

    _record("raise_order", actor, {"order": order["id"], "route": route,
                                   "agency": agency,
                                   "amount": snapshot["amount"]})
    return {"ok": True, "order": order, "reused": False}


def _may_move(current: str, wanted: str) -> bool:
    return wanted in TRANSITIONS.get(current, set())


def mark(order_id: str, wanted: str, actor: Any, *, why: str = "",
         reference: str = "", amount: float | None = None) -> dict[str, Any]:
    """Move one order to a new state, if the state machine allows it.

    The single place an order changes state, so every route — an admin
    marking an invoice paid, a provider webhook, an expiry sweep — is subject
    to the same table and produces the same audit entry. A transition that is
    not in `TRANSITIONS` is refused rather than applied, which is what stops
    a replayed or out-of-order event resurrecting a refunded subscription.
    """
    with _LOCK:
        held = _read()
        order = (held.get("orders") or {}).get(order_id)
        if not order:
            return {"ok": False, "error": f"No order {order_id!r}."}
        was = order.get("state", PENDING)
        if was == wanted:
            # Idempotent by design: a duplicate event is a no-op, not an error
            # and not a second grant.
            return {"ok": True, "order": order, "unchanged": True}
        if not _may_move(was, wanted):
            return {"ok": False, "error": f"An order that is {was} cannot "
                                          f"become {wanted}.",
                    "order": order}

        order["state"] = wanted
        order.setdefault("history", []).append(
            {"state": wanted, "at": _now(), "why": why or "", "was": was})
        if reference:
            order["reference"] = str(reference)[:120]
        if amount is not None:
            order["amount_settled"] = round(float(amount), 2)

        # Entitlement follows the order, in the same write.
        agency = order.get("agency", "")
        if wanted in GRANTING and was not in GRANTING:
            _grant(held, agency, order, int(order.get("term_months")
                                            or DEFAULT_TERM_MONTHS))
        elif wanted in (REFUNDED, DISPUTED) and was in GRANTING:
            _revoke(held, agency, f"Order {order_id} became {wanted}.")

        _write(held)

    _record(f"order_{wanted}", actor,
            {"order": order_id, "was": was, "agency": order.get("agency"),
             "why": why, "reference": reference})
    return {"ok": True, "order": order}


def settle_invoice(order_id: str, actor: Any, *, reference: str = "",
                   amount: float | None = None) -> dict[str, Any]:
    """Record that an invoice was paid. Admins only.

    The invoice route has no provider to confirm anything, so a person
    confirms it — which makes this the most sensitive action in the module.
    It is restricted to the three GAIUS addresses, it demands a reference so
    the entry can be reconciled against a bank statement, and it is audited
    with a name against it.
    """
    from app import admin
    if not admin.is_admin(getattr(actor, "email", "")):
        return {"ok": False, "error": "Only the GAIUS team can settle an "
                                      "invoice."}
    if not str(reference or "").strip():
        return {"ok": False, "error": "A payment reference is required — a "
                                      "check number, an ACH trace, or the "
                                      "remittance advice."}
    return mark(order_id, PAID, actor, why="invoice settled",
                reference=reference, amount=amount)


def expire_stale_orders(older_than_days: int = 30) -> dict[str, Any]:
    """Close out pending orders nobody paid.

    A pending order is not a debt and not an entitlement; leaving them open
    for ever makes the reconciliation report meaningless.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=older_than_days)
    closed = []
    with _LOCK:
        held = _read()
        for order in (held.get("orders") or {}).values():
            if order.get("state") != PENDING:
                continue
            try:
                raised = datetime.fromisoformat(order.get("raised_at", ""))
            except ValueError:
                continue
            if raised < cutoff:
                order["state"] = EXPIRED
                order.setdefault("history", []).append(
                    {"state": EXPIRED, "at": _now(),
                     "why": f"unpaid for {older_than_days} days",
                     "was": PENDING})
                closed.append(order["id"])
        if closed:
            _write(held)
    return {"expired": closed}


# --------------------------------------------------------------- the webhook

def webhook_secret() -> str:
    return os.environ.get("BILLING_WEBHOOK_SECRET", "").strip()


# ------------------------------------------------------------------- Stripe
#
# The card route is Stripe's hosted Buy Button (Oct 2026, from IIA's CFO).
# The button and its publishable key are meant to sit in a public page — the
# publishable key cannot move money — so the test-mode pair is the default
# here and the live pair goes in the server's environment. The secret that
# matters is the webhook signing secret (STRIPE_WEBHOOK_SECRET), which never
# appears in code: with it set, a payment marks its order paid by itself;
# without it, the GAIUS team marks it paid on Admin → Subscriptions with the
# Stripe payment reference, exactly as an invoice is settled.

STRIPE_TEST_KEY = ("pk_test_51UKoO0KITswac9b9tccm0Tzc0vCOBspq3x6c0lPK27H1hWTx2S7bhRMiRV8IDFsk"
                   "iK75n9zs4IYjgSWpbPh7lcam003aMq1WJx")
STRIPE_TEST_BUTTON = "buy_btn_1UNEctKITswac9b9eDukGnjt"
STRIPE_TEST_LINK = "https://buy.stripe.com/test_fZubJ22AegB5doFaWRa3u00"


def stripe() -> dict[str, Any]:
    """What the Subscription page needs to show the Buy Button. No secrets."""
    if os.environ.get("STRIPE_OFF", "").strip() in ("1", "true", "yes"):
        return {"available": False}
    key = os.environ.get("STRIPE_PUBLISHABLE_KEY", "").strip() or STRIPE_TEST_KEY
    button = os.environ.get("STRIPE_BUY_BUTTON_ID", "").strip() or STRIPE_TEST_BUTTON
    link = os.environ.get("STRIPE_PAYMENT_LINK", "").strip() or STRIPE_TEST_LINK
    return {"available": bool(key and button), "publishable_key": key,
            "buy_button_id": button, "payment_link": link,
            "test_mode": key.startswith("pk_test_"),
            "confirms_itself": bool(stripe_webhook_secret())}


def stripe_webhook_secret() -> str:
    return os.environ.get("STRIPE_WEBHOOK_SECRET", "").strip()


def card_route_ready() -> bool:
    """Whether the card route can work at all.

    Both halves are needed: something to take the payment with, and a way to
    learn that it happened. Stripe's Buy Button is the first; the second is
    Stripe's signed webhook where its secret is set, and otherwise the GAIUS
    team, who settle a card order from the Stripe payment reference the way
    they settle an invoice. A key with neither would take money without the
    application ever knowing — which is worse than not offering the route.
    """
    if stripe()["available"]:
        return True
    return bool(os.environ.get("BILLING_PROVIDER_KEY", "").strip()
                and webhook_secret())


def stripe_verify(raw: bytes, header: str, *, now: float | None = None) -> tuple[bool, str]:
    """Stripe's own signature: `Stripe-Signature: t=<time>,v1=<hex>[,v1=…]`,
    an HMAC-SHA256 of "<time>.<raw body>" under the webhook signing secret.
    Over the raw bytes, within the replay window, in constant time."""
    secret = stripe_webhook_secret()
    if not secret:
        return False, "No Stripe webhook secret is configured on this server."
    parts: dict[str, list[str]] = {}
    for item in str(header or "").split(","):
        k, _, v = item.strip().partition("=")
        if k and v:
            parts.setdefault(k, []).append(v)
    stamp = (parts.get("t") or [""])[0]
    if not stamp or not parts.get("v1"):
        return False, "The request carried no Stripe signature."
    try:
        drift = abs((now if now is not None else time.time()) - int(stamp))
    except ValueError:
        return False, "The signature timestamp is not a number."
    if drift > SIGNATURE_WINDOW_SECONDS:
        return False, f"The signature is {int(drift)} seconds old."
    expected = hmac.new(secret.encode(), stamp.encode() + b"." + raw, hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, v) for v in parts["v1"]):
        return False, "The signature does not match."
    return True, ""


#: The Stripe events acted on — an allowlist, as for any provider.
STRIPE_EVENTS = {
    "checkout.session.completed": PAID,
    "checkout.session.async_payment_succeeded": PAID,
    "checkout.session.async_payment_failed": FAILED,
    "checkout.session.expired": EXPIRED,
}


def stripe_event(raw: bytes, header: str) -> dict[str, Any]:
    """One verified Stripe event, applied at most once. The order is the
    `client_reference_id` the Subscription page gave the Buy Button; the
    amount Stripe took has to match the order's where a price is set."""
    ok, why = stripe_verify(raw, header)
    if not ok:
        return {"ok": False, "error": why, "verified": False}
    try:
        event = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"ok": False, "error": "That is not a JSON body."}
    event_id = str(event.get("id") or "").strip()
    kind = str(event.get("type") or "").strip()
    if not event_id:
        return {"ok": False, "error": "The event carried no id."}
    with _LOCK:
        held = _read()
        if event_id in (held.get("events") or {}):
            return {"ok": True, "duplicate": True, "event": event_id}
        held.setdefault("events", {})[event_id] = {"type": kind, "at": _now(), "provider": "stripe"}
        _write(held)
    if kind not in STRIPE_EVENTS:
        return {"ok": True, "ignored": True, "type": kind}

    session = ((event.get("data") or {}).get("object") or {})
    order_id = str(session.get("client_reference_id") or "").strip()
    order = (_read().get("orders") or {}).get(order_id)
    if not order:
        _record("stripe_payment_unmatched", None,
                {"event": event_id, "client_reference_id": order_id,
                 "email": str((session.get("customer_details") or {}).get("email") or "")[:200]})
        return {"ok": False, "error": f"No order {order_id!r} for this payment.", "unmatched": True}

    wanted = STRIPE_EVENTS[kind]
    if wanted == PAID and kind == "checkout.session.completed" \
            and session.get("payment_status") not in ("paid", "no_payment_required"):
        return {"ok": True, "waiting": True, "status": session.get("payment_status")}
    paid = None
    if wanted == PAID:
        try:
            paid = round(int(session.get("amount_total") or 0) / 100, 2)
        except (TypeError, ValueError):
            paid = None
        if order.get("amount_set"):
            if paid != round(float(order.get("amount") or 0), 2):
                _record("webhook_amount_mismatch", None,
                        {"order": order_id, "claimed": paid, "expected": order.get("amount")})
                return {"ok": False, "error": "The amount does not match the order."}
            if str(session.get("currency") or "").upper() != str(order.get("currency") or "").upper():
                return {"ok": False, "error": "The currency does not match the order."}
    return mark(order_id, wanted, None, why=f"Stripe {kind}",
                reference=str(session.get("payment_intent") or session.get("id") or "")[:120],
                amount=paid)


def card_route_note() -> str:
    """Why the card route is unavailable, in words for a screen."""
    if card_route_ready():
        return ""
    # The purchase-order route is no longer offered on the page (Oct 2026),
    # so this does not send anyone to it.
    return ("Paying by card is not switched on here yet. "
            "Please contact the GAIUS team and we will help you subscribe.")


def verify(raw: bytes, signature: str, timestamp: str) -> tuple[bool, str]:
    """Is this really from the provider, and is it recent?

    Over the raw bytes, before any parsing. Re-serializing JSON and signing
    that is the classic way to make a signature check pass for a body that is
    not the body that was signed.
    """
    secret = webhook_secret()
    if not secret:
        # Fails closed. An unconfigured deployment accepts nothing rather
        # than accepting everything.
        return False, "No webhook secret is configured on this server."
    if not signature or not timestamp:
        return False, "The request carried no signature."
    try:
        sent_at = int(timestamp)
    except (TypeError, ValueError):
        return False, "The signature timestamp is not a number."
    drift = abs(int(time.time()) - sent_at)
    if drift > SIGNATURE_WINDOW_SECONDS:
        return False, (f"The signature is {drift} seconds old, outside the "
                       f"{SIGNATURE_WINDOW_SECONDS} second window.")

    expected = hmac.new(secret.encode(),
                        f"{sent_at}.".encode() + raw,
                        hashlib.sha256).hexdigest()
    # Constant time, so a wrong signature cannot be found a byte at a time.
    if not hmac.compare_digest(expected, signature.strip()):
        return False, "The signature does not match."
    return True, ""


def handle_event(raw: bytes, signature: str, timestamp: str) -> dict[str, Any]:
    """One verified provider event, applied at most once.

    Order of operations matters and is deliberate: verify the signature over
    the raw body, then parse, then check we have not seen this event before,
    then check the event is one we handle, then check the money matches what
    the order says, and only then move the order.
    """
    ok, why = verify(raw, signature, timestamp)
    if not ok:
        return {"ok": False, "error": why, "verified": False}

    try:
        event = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return {"ok": False, "error": "That is not a JSON body."}
    if not isinstance(event, dict):
        return {"ok": False, "error": "That is not an event."}

    event_id = str(event.get("id") or "").strip()
    kind = str(event.get("type") or "").strip()
    if not event_id:
        return {"ok": False, "error": "The event carried no id, so it cannot "
                                      "be de-duplicated."}

    with _LOCK:
        held = _read()
        if event_id in (held.get("events") or {}):
            # Providers retry. A retry must not grant a second term.
            return {"ok": True, "duplicate": True, "event": event_id}
        held.setdefault("events", {})[event_id] = {
            "type": kind, "at": _now()}
        _write(held)

    if kind not in HANDLED_EVENTS:
        # Recorded above, so it is de-duplicated, and then ignored.
        return {"ok": True, "ignored": True, "type": kind}

    order_id = str(event.get("order") or "").strip()
    order = (_read().get("orders") or {}).get(order_id)
    if not order:
        return {"ok": False, "error": f"No order {order_id!r} for this event."}

    wanted = HANDLED_EVENTS[kind]

    # The money has to match the order it claims to settle. A confirmation
    # for the right order at the wrong amount is not a confirmation.
    if wanted == PAID:
        claimed = event.get("amount")
        currency = str(event.get("currency") or "").upper()
        if order.get("amount_set"):
            try:
                claimed = round(float(claimed), 2)
            except (TypeError, ValueError):
                return {"ok": False, "error": "The event carried no amount."}
            if claimed != round(float(order.get("amount") or 0), 2):
                _record("webhook_amount_mismatch", None,
                        {"order": order_id, "claimed": claimed,
                         "expected": order.get("amount")})
                return {"ok": False, "error": "The amount does not match the "
                                              "order."}
            if currency != str(order.get("currency") or "").upper():
                return {"ok": False, "error": "The currency does not match "
                                              "the order."}

    return mark(order_id, wanted, None,
                why=f"provider event {kind}",
                reference=str(event.get("reference") or "")[:120],
                amount=event.get("amount") if wanted == PAID else None)


# ------------------------------------------------------------ what a screen needs

def deployment_override() -> bool:
    """Whether this whole deployment has the paid modules forced open.

    Staging sets `IIA_SUBSCRIPTION` so the paid modules can be demonstrated
    without raising an invoice against a fictional county. The page has to
    say so: without this it told an agency it had no subscription while every
    paid module sat open next to it, which is the same kind of lie as the
    mail panel telling an operator to configure variables that were already
    set.
    """
    return os.environ.get("IIA_SUBSCRIPTION", "").strip() in (
        "1", "true", "yes")


def listing(agency: str) -> dict[str, Any]:
    """Everything the subscription page draws itself from."""
    held = _read()
    mine = [o for o in (held.get("orders") or {}).values()
            if o.get("agency") == agency]
    mine.sort(key=lambda o: o.get("raised_at", ""), reverse=True)
    return {
        "plan": plan(),
        "entitlement": entitlement(agency),
        "routes": ROUTES,
        "card_ready": card_route_ready(),
        "card_note": card_route_note(),
        # The Buy Button's public settings — no secret is ever in here.
        "stripe": stripe(),
        "override": deployment_override(),
        # Only this agency's orders. The register is shared; the view is not.
        "orders": [_for_screen(o) for o in mine[:20]],
    }


def admin_listing() -> dict[str, Any]:
    """Every order and every entitlement on the deployment. GAIUS team only.

    The other half of the invoice route. An organization could ask for an
    invoice, and `settle_invoice` existed to record the payment, but nothing
    drew the list an admin would settle from — so no organization could ever
    become subscribed through the application, and "Request an invoice" led
    nowhere anybody at IIA could see.

    This deliberately crosses organizations, as the bug and usage screens do,
    and for the same reason: running the platform means seeing all of it.
    The caller checks the proven address before calling; nothing here trusts
    that it was checked.
    """
    held = _read()
    orders = sorted((held.get("orders") or {}).values(),
                    key=lambda o: o.get("raised_at", ""), reverse=True)
    entitlements = held.get("entitlements") or {}
    return {
        "orders": [{**_for_screen(o), "agency": o.get("agency", ""),
                    "agency_label": _agency_label(o.get("agency", "")),
                    "note": o.get("note", "")} for o in orders],
        "pending": sum(1 for o in orders if o.get("state") == PENDING),
        "entitlements": [{**entitlement(code),
                          "agency_label": _agency_label(code)}
                         for code in sorted(entitlements)],
        "findings": reconcile().get("findings", []),
        "override": deployment_override(),
        "plan": plan(),
    }


def _agency_label(code: str) -> str:
    """An organization's name for an admin reading a list of codes."""
    try:
        from app import tenancy, unlisted
        return str(tenancy.KNOWN.get(code, {}).get("label")
                   or unlisted.label(code) or code)
    except Exception:                                         # noqa: BLE001
        return code


def _for_screen(order: dict[str, Any]) -> dict[str, Any]:
    """An order as a screen may see it — no fingerprints, no internals."""
    return {
        "id": order.get("id"),
        "state": order.get("state"),
        "route": order.get("route"),
        "route_label": ROUTES.get(order.get("route", ""), ""),
        "amount": order.get("amount"),
        "amount_set": order.get("amount_set"),
        "currency": order.get("currency"),
        "term_months": order.get("term_months"),
        "raised_at": order.get("raised_at"),
        "raised_by": order.get("raised_by"),
        "reference": order.get("reference", ""),
    }


def reconcile() -> dict[str, Any]:
    """What does not add up. Run daily; every exception needs an owner.

    Deliberately reports rather than repairs. An automatic fix here would
    paper over the thing worth investigating.
    """
    held = _read()
    orders = list((held.get("orders") or {}).values())
    entitlements = held.get("entitlements") or {}
    findings: list[dict[str, str]] = []

    granting = [o for o in orders if o.get("state") in GRANTING]
    for order in granting:
        row = entitlements.get(order.get("agency", ""))
        if not row or row.get("state") not in ("active", "expired"):
            findings.append({
                "order": order.get("id", ""),
                "says": "is paid but the agency has no entitlement to match",
                "agency": order.get("agency", ""),
            })

    for agency, row in entitlements.items():
        if row.get("state") != "active":
            continue
        backing = [o for o in granting if o.get("agency") == agency]
        if not backing:
            findings.append({
                "order": row.get("order", ""),
                "says": "an active entitlement with no paid order behind it",
                "agency": agency,
            })

    # Two paid orders for one agency covering the same term is how a double
    # charge shows up.
    seen: dict[str, int] = {}
    for order in granting:
        seen[order.get("agency", "")] = seen.get(order.get("agency", ""), 0) + 1
    for agency, count in seen.items():
        if count > 1:
            findings.append({
                "order": "", "agency": agency,
                "says": f"{count} paid orders — check for a double charge",
            })

    return {
        "at": _now(),
        "orders": len(orders),
        "paid": len(granting),
        "entitled": sum(1 for r in entitlements.values()
                        if r.get("state") == "active"),
        "findings": findings,
    }


def _record(action: str, actor: Any, detail: dict[str, Any]) -> None:
    """Into the hash-chained log, like every other decision in this product.

    Money moving is exactly the kind of event the client meant by "log all
    choices, activities and framework versions on the back end" and "the log
    should survive absolutely".
    """
    from app.authz import default_log
    try:
        default_log().append(
            actor=getattr(actor, "user_id", "") or "provider",
            role=getattr(getattr(actor, "role", None), "value", "") or "system",
            action=action, target="billing", outcome="allowed",
            detail={**detail, "actor_name": str(getattr(actor, "name", "")
                                                or "")[:120]})
    except Exception:                                     # noqa: BLE001
        pass
