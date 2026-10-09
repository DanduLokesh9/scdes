"""The one-way NDA that stands between verification and the product.

The client's rule, in their words: after email verification the NDA appears as a
PDF with Accept or Decline. Accept and you go to the home screen. Decline and
IIA is notified immediately and you are asked "Are you sure?". Decline a second
time and the account is locked until IIA unlocks it after speaking to you.

Four states, and the order they run in matters:

  ``pending``        Verified, NDA not yet answered. Nothing else is reachable.
  ``accepted``       Recorded, with what was accepted and when. In.
  ``declined_once``  Declined and asked to confirm. IIA already notified. Still
                     recoverable — accepting from here is a normal acceptance.
  ``locked``         Declined twice. Only IIA can lift it, and lifting it is
                     itself recorded with who did it and why.

Two decisions worth stating, because both could reasonably have gone the other
way.

**A first decline is not a lock.** People misclick, and people read a legal
document, hesitate, and want a moment. Locking on the first press would make an
unrecoverable state one accidental click away. The confirm step is what makes
the lock defensible — by the time it fires, the person has said no twice with
the consequence spelled out in between.

**The acceptance records the document, not just the act.** Every acceptance
stores the SHA-256 of the exact PDF that was on screen. "Did they agree to this
version?" is then a question with an answer, years later, without anyone having
to remember whether the NDA changed in between. The document itself says the
acceptance is evidence of the agreement — so the evidence has to identify what
was agreed to.

This module runs before anyone has a role, exactly like `app/tenancy.py`, so it
cannot pass through `guard()`. It is kept safe the same way: it validates its
input, writes one record, touches nothing else, and appends every transition to
the same hash-chained audit log as everything else.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "nda.json"
DOCUMENT = ROOT / "app" / "web" / "assets" / "legal" / "IIA_GAIUS_OneWay_NDA.pdf"

#: Where the browser fetches it. Served as a static asset, not generated.
DOCUMENT_URL = "/assets/legal/IIA_GAIUS_OneWay_NDA.pdf"

PENDING = "pending"
ACCEPTED = "accepted"
DECLINED_ONCE = "declined_once"
LOCKED = "locked"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def notify_address() -> str:
    """Where a decline is reported. IIA's own address, overridable per deploy."""
    return (os.getenv("IIA_NOTIFY", "").strip() or "brett@iiac.ai")


# ------------------------------------------------------------------ document

def document() -> dict[str, Any]:
    """What is being agreed to, and a fingerprint of it.

    The hash is computed from the file rather than stored as a constant, so
    replacing the PDF cannot leave the record claiming a version that is no
    longer what people see.
    """
    if not DOCUMENT.is_file():
        return {"available": False, "url": DOCUMENT_URL, "sha256": "",
                "bytes": 0,
                "error": "The NDA PDF is missing. Run "
                         "`python -m tools.build_nda_pdf`."}
    blob = DOCUMENT.read_bytes()
    return {
        "available": True,
        "url": DOCUMENT_URL,
        "title": "One-Way Non-Disclosure Agreement",
        "subtitle": "GoverningAI.US — Confidential Product Materials",
        "sha256": hashlib.sha256(blob).hexdigest(),
        "bytes": len(blob),
    }


# -------------------------------------------------------------------- storage

def _load() -> dict[str, Any]:
    if not STORE.is_file():
        return {"people": {}, "notifications": []}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {"people": {}, "notifications": []}
    data.setdefault("people", {})
    data.setdefault("notifications", [])
    return data


def _save(data: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(STORE)


def _audit(action: str, email: str, detail: dict[str, Any],
           outcome: str = "allowed") -> None:
    """Every transition, on the same hash-chained log as everything else.

    Direct rather than through `guard()`: there is no actor yet — the person has
    proved a mailbox and nothing more. `guard()` needs a role to decide against,
    and inventing one to satisfy the signature would put a fictitious capacity
    into the trail.
    """
    try:
        from app.audit import JsonlAuditLog
        JsonlAuditLog().append(
            actor=email, role="registrant", action=action, target="nda",
            outcome=outcome, mode="onboarding", detail=detail)
    except Exception:                    # the record must not block the person
        pass


# ------------------------------------------------------------------- reading

def status(email: str) -> dict[str, Any]:
    """Where this person stands, and what the interface should therefore do."""
    address = (email or "").strip().lower()
    person = _load()["people"].get(address, {})
    state = person.get("status", PENDING)
    doc = document()

    if state == ACCEPTED:
        # An acceptance is against a version. When the document changes, the
        # earlier agreement stops covering it — so the NDA is presented again
        # rather than treated as already answered.
        #
        # Re-asking on any change, including a corrected product name, is
        # deliberate. Nothing here can tell a typo from a new clause, and the
        # only two options are "re-ask sometimes unnecessarily" and "sometimes
        # let someone in under terms they never saw". For a confidentiality
        # agreement that is not a close call.
        stale = bool(doc["sha256"]) and person.get("sha256") != doc["sha256"]
        if stale:
            return {
                "email": address, "status": PENDING, "may_enter": False,
                "superseded": True,
                "previously_accepted_at": person.get("accepted_at", ""),
                "document": doc,
                "headline": "The agreement has been updated",
                "note": ("You accepted an earlier version on "
                         f"{(person.get('accepted_at') or '')[:10]}. This one "
                         "differs, so it needs reading and accepting again — "
                         "your previous acceptance still stands as a record of "
                         "what you agreed to then."),
            }
        return {
            "email": address, "status": ACCEPTED, "may_enter": True,
            "accepted_at": person.get("accepted_at", ""),
            "accepted_name": person.get("name", ""),
            "sha256": person.get("sha256", ""),
            "superseded": False,
            "note": "Accepted, and recorded with the version you agreed to.",
            "document": doc,
        }

    if state == LOCKED:
        return {
            "email": address, "status": LOCKED, "may_enter": False,
            "locked_at": person.get("locked_at", ""),
            "document": doc,
            "headline": "This account is locked.",
            "note": ("Access to the platform requires agreeing to the "
                     "non-disclosure agreement, and this account declined it "
                     f"twice. IIA has been notified. Contact "
                     f"{notify_address()} to discuss it — the lock is lifted by "
                     f"a person, not by trying again."),
        }

    if state == DECLINED_ONCE:
        return {
            "email": address, "status": DECLINED_ONCE, "may_enter": False,
            "declined_at": person.get("declined_at", ""),
            "document": doc,
            "headline": "Are you sure?",
            "note": ("Declining again locks this account, and only IIA can "
                     "unlock it after speaking with you. You can still accept "
                     "— nothing has been held against you."),
        }

    return {
        "email": address, "status": PENDING, "may_enter": False,
        "document": doc,
        "headline": "Before you go any further",
        "note": ("Everything inside is IIA's confidential product material. "
                 "Read the agreement below and accept it to continue."),
    }


def may_enter(email: str) -> bool:
    return status(email)["status"] == ACCEPTED


# ------------------------------------------------------------------- writing

def accept(email: str, *, name: str = "", title: str = "",
           agency: str = "") -> dict[str, Any]:
    """Record acceptance. Works from pending and from a first decline."""
    address = (email or "").strip().lower()
    if "@" not in address:
        return {"ok": False, "error": "A valid email address is required."}

    doc = document()
    if not doc["available"]:
        # Never record agreement to a document nobody could read.
        return {"ok": False, "error": doc["error"]}

    data = _load()
    person = data["people"].get(address, {})
    if person.get("status") == LOCKED:
        return {"ok": False, "status": LOCKED,
                "error": f"This account is locked. Contact "
                         f"{notify_address()}."}

    # Keep every acceptance, not just the latest. The document says the record
    # is evidence of the agreement; overwriting it when the NDA is reissued
    # would destroy the evidence of what was agreed to before.
    history = person.get("history", [])
    if person.get("status") == ACCEPTED and person.get("sha256"):
        history = history + [{"at": person.get("accepted_at", ""),
                              "sha256": person.get("sha256", ""),
                              "name": person.get("name", "")}]

    data["people"][address] = {
        **person,
        "history": history,
        "status": ACCEPTED,
        "name": (name or "").strip()[:120],
        "title": (title or "").strip()[:120],
        "agency": (agency or "").strip()[:80],
        "accepted_at": _now(),
        # The document as it stood, not merely the fact of agreement.
        "sha256": doc["sha256"],
        "document_bytes": doc["bytes"],
    }
    _save(data)
    _audit("nda_accepted", address,
           {"actor_name": name, "actor_title": title, "agency": agency,
            "sha256": doc["sha256"],
            "reason": "One-way NDA accepted; access granted."})
    return {"ok": True, "status": ACCEPTED, "may_enter": True,
            "state": status(address)}


def decline(email: str, *, name: str = "", title: str = "",
            agency: str = "", reason: str = "") -> dict[str, Any]:
    """Decline. First time asks for confirmation; second time locks.

    IIA is notified on the *first* decline, per the client: "If decline, it
    should notify us immediately and ask 'Are you sure?'". Notifying only on the
    lock would mean the one case worth a conversation — someone hesitating — is
    the case nobody hears about.
    """
    address = (email or "").strip().lower()
    if "@" not in address:
        return {"ok": False, "error": "A valid email address is required."}

    data = _load()
    person = data["people"].get(address, {})
    state = person.get("status", PENDING)

    if state == LOCKED:
        return {"ok": True, "status": LOCKED, "state": status(address)}

    who = {"name": (name or "").strip()[:120],
           "title": (title or "").strip()[:120],
           "agency": (agency or "").strip()[:80],
           "reason": (reason or "").strip()[:400]}

    if state != DECLINED_ONCE:
        data["people"][address] = {**person, **who,
                                   "status": DECLINED_ONCE,
                                   "declined_at": _now(),
                                   "declines": person.get("declines", 0) + 1}
        note = _notify(data, address, who, first=True)
        _save(data)
        _audit("nda_declined", address,
               {**who, "reason": "NDA declined; confirmation requested.",
                "notified": note["sent"]}, outcome="denied")
        return {"ok": True, "status": DECLINED_ONCE, "confirm_required": True,
                "notified": note, "state": status(address)}

    data["people"][address] = {**person, **who,
                               "status": LOCKED,
                               "locked_at": _now(),
                               "declines": person.get("declines", 0) + 1}
    note = _notify(data, address, who, first=False)
    _save(data)
    _audit("nda_locked", address,
           {**who, "reason": "NDA declined twice; account locked.",
            "notified": note["sent"]}, outcome="denied")
    return {"ok": True, "status": LOCKED, "notified": note,
            "state": status(address)}


def _notify(data: dict[str, Any], email: str, who: dict[str, str],
            *, first: bool) -> dict[str, Any]:
    """Tell IIA. Queued first, emailed second.

    The queue is the part that is guaranteed. Email can be unconfigured or
    rejected by the provider, and a notification that exists only as a failed
    send is not a notification — so it is written to the record either way and
    the interface reports honestly whether it also went out.
    """
    entry = {
        "at": _now(), "email": email, "kind": "locked" if not first else "declined",
        "name": who.get("name", ""), "title": who.get("title", ""),
        "agency": who.get("agency", ""), "reason": who.get("reason", ""),
        "emailed": False, "delivery": "",
    }

    subject = (f"GAIUS — NDA declined twice, account locked: {email}"
               if not first else
               f"GAIUS — NDA declined: {email}")
    body = (
        f"{'An account has been locked.' if not first else 'Someone declined the NDA.'}\n\n"
        f"  Address : {email}\n"
        f"  Name    : {who.get('name') or '(not given)'}\n"
        f"  Title   : {who.get('title') or '(not given)'}\n"
        f"  Agency  : {who.get('agency') or '(not given)'}\n"
        f"  When    : {entry['at']}\n"
        + (f"  Reason  : {who['reason']}\n" if who.get("reason") else "")
        + ("\nThey were asked to confirm. If they decline again the account "
           "locks automatically.\n" if first else
           "\nThe account is locked and cannot be used until you unlock it:\n"
           f"  python -m app.nda --unlock {email} --by \"your name\"\n")
    )
    try:
        from app import mailer
        result = mailer.send(notify_address(), subject, body)
        entry["emailed"] = bool(result.get("sent"))
        entry["delivery"] = result.get("reason", "") or "sent"
    except Exception as exc:                                # noqa: BLE001
        entry["delivery"] = f"{type(exc).__name__}: {exc}"

    data["notifications"].append(entry)
    return {"sent": entry["emailed"], "queued": True,
            "to": notify_address(), "detail": entry["delivery"]}


# --------------------------------------------------------------- IIA controls

def unlock(email: str, *, by: str, note: str = "") -> dict[str, Any]:
    """Lift a lock. A person does this, and the record says which person."""
    address = (email or "").strip().lower()
    by = (by or "").strip()
    if not by:
        return {"ok": False,
                "error": "Say who is unlocking it. An unlock with no name is "
                         "not a record of anything."}

    data = _load()
    person = data["people"].get(address)
    if not person:
        return {"ok": False, "error": f"No NDA record for {address}."}
    if person.get("status") != LOCKED:
        return {"ok": False,
                "error": f"{address} is not locked (status: "
                         f"{person.get('status', PENDING)})."}

    history = person.get("unlocks", [])
    history.append({"at": _now(), "by": by[:120], "note": (note or "")[:400]})
    # Back to pending, not to accepted. Unlocking restores the chance to answer;
    # it does not answer on their behalf.
    data["people"][address] = {**person, "status": PENDING,
                               "unlocks": history, "locked_at": ""}
    _save(data)
    _audit("nda_unlocked", address,
           {"actor_name": by, "note": note,
            "reason": "Lock lifted; the NDA is presented again."})
    return {"ok": True, "status": PENDING, "state": status(address)}


def pending_notifications(limit: int = 50) -> list[dict[str, Any]]:
    return list(reversed(_load()["notifications"]))[:limit]


def locked_accounts() -> list[dict[str, Any]]:
    return [{"email": e, **p} for e, p in _load()["people"].items()
            if p.get("status") == LOCKED]


def summary() -> dict[str, Any]:
    people = _load()["people"]
    counts: dict[str, int] = {}
    for p in people.values():
        counts[p.get("status", PENDING)] = counts.get(p.get("status", PENDING), 0) + 1
    return {"document": document(), "counts": counts,
            "locked": locked_accounts(),
            "notifications": pending_notifications(20),
            "notify_address": notify_address()}


def _cli() -> int:
    """`python -m app.nda --unlock someone@agency.gov --by "Brett Butz"`"""
    import argparse
    ap = argparse.ArgumentParser(description="NDA acceptance records")
    ap.add_argument("--unlock", metavar="EMAIL")
    ap.add_argument("--by", default="")
    ap.add_argument("--note", default="")
    ap.add_argument("--list", action="store_true",
                    help="show locked accounts and recent declines")
    args = ap.parse_args()

    if args.unlock:
        result = unlock(args.unlock, by=args.by, note=args.note)
        print(json.dumps(result, indent=2))
        return 0 if result.get("ok") else 1

    info = summary()
    print(f"document : {info['document']['sha256'][:16]}…  "
          f"({info['document']['bytes']} bytes)")
    print(f"counts   : {info['counts'] or 'none yet'}")
    print(f"notify   : {info['notify_address']}")
    if info["locked"]:
        print("\nlocked:")
        for p in info["locked"]:
            print(f"  {p['email']}  {p.get('name', '')}  since {p.get('locked_at', '')}")
    if info["notifications"]:
        print("\nrecent:")
        for n in info["notifications"][:10]:
            print(f"  {n['at']}  {n['kind']:9} {n['email']}  "
                  f"emailed={n['emailed']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
