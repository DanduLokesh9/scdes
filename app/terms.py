"""The GoverningAI.US Terms of Use and License Agreement, accepted at registration.

Brett's flow (Oct 2026): the registration form carries the agreement. It
cannot be dismissed; Accept stays disabled until the terms have been scrolled
to the end, the authority box is ticked, and the acceptor has given their
name, title, work email and governmental unit. Only then is a verification
code sent. A Governmental Unit whose counsel will not accept a click-through
asks for the signed form instead, and its registration waits until IIA has
the executed copy back.

The agreement is shown exactly as written — `assets/legal/terms_v1.0.html` is
rendered word for word from the click-through DOCX, and the acceptance stores
the SHA-256 of that text, so "which version did they accept?" has an answer
years later. It replaces the earlier one-way NDA as the thing a person agrees
to: see `nda.status`, which treats a current acceptance of these terms as
satisfying it.

Two kinds of record, both kept for good:

* **acceptance** — click-wrap: who, for which unit, the version and its hash,
  that the authority box was ticked and the text scrolled, when, and the
  browser. Recorded before the code is sent (the agreement is what the code
  is for); marked ``confirmed`` once that address proves itself.
* **signed request** — the counsel route: the form is emailed to the person
  and to IIA, and the registration pauses at ``awaiting_signed`` until the
  GAIUS team marks the executed copy received.

Like `nda` and `tenancy`, this runs before anyone has a role, so it writes its
own records and appends every step to the hash-chained audit log directly.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
LEGAL = ROOT / "app" / "web" / "assets" / "legal"
TEXT = LEGAL / "terms_v1.0.html"
STORE = ROOT / "data" / "terms.json"

VERSION = "v1.0"
TITLE = "GoverningAI.US Terms of Use and License Agreement"
TIER = "Free Governmental Tier"
CLICK_DOCX_URL = "/assets/legal/GoverningAI_Terms_of_Use_and_License_v1.0.docx"
SIGNED_DOCX_URL = "/assets/legal/GoverningAI_Terms_of_Use_and_License_SIGNED_FORM_v1.0.docx"

CONFIRMED = "confirmed"          # accepted, and the address since proved
ACCEPTED = "accepted"            # accepted; code sent, not yet proved
AWAITING_SIGNED = "awaiting_signed"
SIGNED_RECEIVED = "signed_received"

_LOCK = threading.Lock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def notify_address() -> str:
    return os.getenv("IIA_NOTIFY", "").strip() or "brett@iiac.ai"


def document() -> dict[str, Any]:
    """The agreement as shown, and a fingerprint of exactly that text."""
    if not TEXT.is_file():
        return {"available": False, "error": "The Terms of Use text is missing."}
    html = TEXT.read_text(encoding="utf-8")
    return {"available": True, "title": TITLE, "version": VERSION, "tier": TIER,
            "html": html, "sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
            "download_url": CLICK_DOCX_URL, "signed_form_url": SIGNED_DOCX_URL}


# -------------------------------------------------------------------- storage

def _load() -> dict[str, Any]:
    try:
        data = json.loads(STORE.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        data = {}
    data.setdefault("people", {})
    return data


def _save(data: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STORE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(STORE)


def _audit(action: str, email: str, detail: dict[str, Any]) -> None:
    try:
        from app.audit import JsonlAuditLog
        JsonlAuditLog().append(actor=email, role="registrant", action=action,
                               target="terms", outcome="allowed",
                               mode="onboarding", detail=detail)
    except Exception:                    # the record must not block the person
        pass


# -------------------------------------------------------------------- reading

def status(email: str) -> dict[str, Any]:
    """Where this person stands against the current version."""
    address = (email or "").strip().lower()
    person = _load()["people"].get(address) or {}
    doc = document()
    current = bool(doc.get("sha256")) and person.get("sha256") == doc["sha256"]
    state = person.get("status", "")
    if state in (ACCEPTED, CONFIRMED) and not current:
        state = ""                       # an earlier version: ask again
    return {"email": address, "status": state or "none",
            "accepted": state in (ACCEPTED, CONFIRMED, SIGNED_RECEIVED),
            "awaiting_signed": state == AWAITING_SIGNED,
            "accepted_at": person.get("accepted_at", ""),
            "version": person.get("version", "")}


def may_register(email: str) -> bool:
    """Whether a verification code may be sent: the current terms accepted,
    or the executed signed form received."""
    return status(email)["accepted"]


# -------------------------------------------------------------------- writing

def accept(*, email: str, name: str, title: str, unit: str, agency: str = "",
           authority: bool = False, scrolled: bool = False,
           user_agent: str = "", sha256: str = "") -> dict[str, Any]:
    """Click-wrap acceptance. Every condition the form enforces is checked
    again here, because a rule that depends on the browser is not a rule."""
    address = (email or "").strip().lower()
    doc = document()
    if not doc.get("available"):
        return {"ok": False, "error": doc.get("error", "The agreement is unavailable.")}
    missing = [label for label, value in (("your name", name), ("your title", title),
                                          ("your work email", address),
                                          ("the governmental unit", unit))
               if len(str(value or "").strip()) < 2]
    if missing or "@" not in address:
        return {"ok": False, "error": "Enter " + ", ".join(missing or ["a valid work email"]) + "."}
    if not authority:
        return {"ok": False, "error": "Confirm that you are authorized to accept "
                                      "for the governmental unit, and are at least 18."}
    if not scrolled:
        return {"ok": False, "error": "Read the agreement to the end first."}
    if sha256 and sha256 != doc["sha256"]:
        return {"ok": False, "stale": True,
                "error": "The agreement has been updated since this page opened. "
                         "Reload, and read the current version."}
    record = {
        "status": ACCEPTED,
        "agreement": TITLE, "version": VERSION, "tier": TIER,
        "method": "click-wrap", "sha256": doc["sha256"],
        "accepted_by": {"name": name.strip()[:120], "title": title.strip()[:120],
                        "email": address},
        "governmental_unit": unit.strip()[:160], "agency": (agency or "")[:120],
        "authority_affirmed": True, "scrolled_to_end": True,
        "accepted_at": _now(), "user_agent": (user_agent or "")[:200],
    }
    with _LOCK:
        data = _load()
        person = data["people"].get(address) or {}
        history = list(person.get("history") or [])
        if person.get("accepted_at"):
            history.append({k: person.get(k) for k in
                            ("status", "version", "sha256", "accepted_at", "governmental_unit")})
        data["people"][address] = {**record, "history": history}
        _save(data)
    _audit("terms_accepted", address,
           {"actor_name": record["accepted_by"]["name"],
            "actor_title": record["accepted_by"]["title"],
            "unit": record["governmental_unit"], "agency": record["agency"],
            "version": VERSION, "sha256": doc["sha256"], "method": "click-wrap"})
    return {"ok": True, "record": {k: v for k, v in record.items() if k != "status"}}


def confirm(email: str) -> None:
    """The address that accepted has now proved itself with a code."""
    address = (email or "").strip().lower()
    with _LOCK:
        data = _load()
        person = data["people"].get(address)
        if not person or person.get("status") != ACCEPTED:
            return
        person["status"] = CONFIRMED
        person["confirmed_at"] = _now()
        _save(data)
    _audit("terms_confirmed", address, {"version": person.get("version", "")})


def request_signed(*, email: str, name: str, title: str, unit: str,
                   agency: str = "") -> dict[str, Any]:
    """The counsel route. The signed form goes to them and to IIA, and the
    registration waits for the executed copy."""
    address = (email or "").strip().lower()
    if "@" not in address or len((name or "").strip()) < 2 or len((unit or "").strip()) < 2:
        return {"ok": False, "error": "Enter your name, work email and governmental "
                                      "unit, so the signed form can be sent to you."}
    with _LOCK:
        data = _load()
        person = data["people"].get(address) or {}
        data["people"][address] = {
            **person, "status": AWAITING_SIGNED, "version": VERSION,
            "accepted_by": {"name": name.strip()[:120], "title": (title or "").strip()[:120],
                            "email": address},
            "governmental_unit": unit.strip()[:160], "agency": (agency or "")[:120],
            "signed_requested_at": _now()}
        _save(data)
    _audit("terms_signed_form_requested", address,
           {"actor_name": name, "unit": unit, "agency": agency, "version": VERSION})
    _mail_signed_form(address, name.strip(), unit.strip())
    return {"ok": True, "awaiting_signed": True,
            "says": ("The signed form has been emailed to you and to IIA. Your "
                     "registration will continue once IIA has the executed copy back — "
                     "you will be able to get your code then.")}


def mark_signed_received(email: str, by: str) -> dict[str, Any]:
    """The GAIUS team has the executed copy. Registration may continue."""
    from app import admin
    if not admin.is_admin(by):
        return {"ok": False, "error": "This is for the GAIUS team."}
    address = (email or "").strip().lower()
    with _LOCK:
        data = _load()
        person = data["people"].get(address)
        if not person or person.get("status") != AWAITING_SIGNED:
            return {"ok": False, "error": "Nobody is waiting on a signed form at that address."}
        doc = document()
        person.update({"status": SIGNED_RECEIVED, "method": "signed",
                       "sha256": doc.get("sha256", ""),
                       "signed_received_at": _now(), "signed_received_by": by})
        _save(data)
    _audit("terms_signed_form_received", address, {"by": by, "version": VERSION})
    return {"ok": True}


def awaiting_signed() -> list[dict[str, Any]]:
    """For the GAIUS team's Organizations screen."""
    out = []
    for address, p in _load()["people"].items():
        if p.get("status") == AWAITING_SIGNED:
            who = p.get("accepted_by") or {}
            out.append({"email": address, "name": who.get("name", ""),
                        "title": who.get("title", ""),
                        "unit": p.get("governmental_unit", ""),
                        "requested_at": p.get("signed_requested_at", "")})
    return sorted(out, key=lambda r: r["requested_at"])


def _mail_signed_form(address: str, name: str, unit: str) -> None:
    """In the background, so the form answers at once; never raises."""
    def send() -> None:
        try:
            from app import mailer
            base = os.getenv("GAIUS_PUBLIC_URL", "https://app.staging.governingai.us").rstrip("/")
            link = base + SIGNED_DOCX_URL
            mailer.send(address, "GoverningAI.US — the signed Terms of Use form",
                        f"Hello {name},\n\nAs requested, here is the countersignable form of "
                        f"the GoverningAI.US Terms of Use and License Agreement, for {unit}:\n\n"
                        f"{link}\n\nPlease have it signed by someone authorized to bind "
                        f"{unit}, and return it to {notify_address()}. Your registration "
                        f"continues once IIA has the executed copy.\n\nInnovative "
                        f"Infrastructure Advising, LLC")
            mailer.send(notify_address(), f"GoverningAI.US — signed Terms requested: {unit}",
                        f"{name} <{address}> asked for the signed form of the Terms of Use "
                        f"for {unit}. It has been emailed to them ({link}).\n\nWhen the "
                        f"executed copy comes back, mark it received on Admin → "
                        f"Organizations so they can get their code.")
        except Exception:                                     # noqa: BLE001
            pass
    threading.Thread(target=send, name="signed-terms-mail", daemon=True).start()
