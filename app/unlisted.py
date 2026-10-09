"""Governmental units that are not on the list.

The client: "Add a side button on the registration page which says something
like 'Don't see your governmental unit? Click here to create your framework'
and then walk them through the onboarding anyway. There just won't be an @
domain requirement."

The list covers one environmental agency per state, the federal agencies, and
South Carolina's 148 units. Tens of thousands of governmental units are not on
it — counties, towns, special districts, school boards — and every one of them
is entitled to the free framework. This is the door for them.

What changes, and what does not:

- **The unit is described by the person registering it.** They type its name;
  nothing checks it. It gets an id of its own, scoped to the state they chose,
  and a container of its own like any other.
- **No email domain is required.** A water district of twelve people may well
  run on a consumer mailbox. The address is still proven — a code goes to it
  and has to be read back — because that is what stops somebody registering in
  a stranger's name.
- **It is private to its registrant.** An unlisted unit is never added to the
  dropdown anybody else sees. Its name is self-described and unchecked, and
  putting it in front of everybody in the state would publish whatever somebody
  typed. The registrant signs back in with their address, as anyone does.
- **It cannot be used to get round the list.** A unit whose name matches an
  agency that *is* listed in that state is refused and pointed at the listed
  entry. Otherwise "Texas Commission on Environmental Quality" typed into this
  form, with a consumer address, would walk past the domain check the listed
  entry exists to apply.

Everything after registration is the ordinary path: the code, the NDA, the
framework builder, and a document marked DRAFT until whoever holds the
authority adopts it.
"""

from __future__ import annotations

import json
import re
import secrets
import threading
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()

#: The marker in an unlisted unit's id: `tx.u-harris-county-mud-12-k4f9`.
#: A listed agency's id never contains it, so the kind can be told from the id.
MARK = ".u-"

#: Shortest and longest name accepted. Long enough for "Harris County
#: Municipal Utility District No. 12", short enough to stay a name.
MIN_NAME, MAX_NAME = 3, 120

#: How many different units one address may describe. A person runs one
#: governmental unit, occasionally two; five is room for somebody who clerks
#: for several small districts, and not room for filling the store.
PER_PERSON = 5

#: New units across the whole deployment in any hour. The ceiling on a bulk
#: run from many addresses, which the per-address limits cannot see. Far
#: above anything real sign-ups would reach, and a hard stop on a script.
PER_HOUR = 40

#: A unit nobody ever verified is removed after this long. The code that
#: would have verified it expired within the hour; a week is generous, and
#: without a limit the store would keep every name ever typed into the form.
UNVERIFIED_DAYS = 7

BUSY = ("We are receiving an unusual number of new registrations right now, so "
        "this one has not been taken. Please try again in an hour.")

#: Said on the record wherever the unit's provenance is shown.
PROVENANCE = ("Not on the platform's list. The organization's name was typed "
              "by the person who registered it and has not been checked; no "
              "email domain applies, and their address was proven with a "
              "code.")


def _store() -> Path:
    from app import tenancy
    return Path(tenancy.STORE).parent / "unlisted_units.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read() -> dict[str, Any]:
    path = _store()
    if not path.is_file():
        return {"units": {}}
    try:
        held = json.loads(path.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {"units": {}}
    held.setdefault("units", {})
    return held


def _write(data: dict[str, Any]) -> None:
    path = _store()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)


def _fold(text: str) -> str:
    """A name reduced to what two spellings of it have in common."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = re.sub(r"&", " and ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(re.sub(r"\b(the|of|and|on)\b", " ", text).split())


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-") or "unit"


def _initials(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name or "")
             if w and w.lower() not in ("of", "the", "and", "for")]
    return "".join(w[0].upper() for w in words)[:8] or "UNIT"


def is_unlisted(agency_id: str) -> bool:
    return MARK in (agency_id or "")


def get(agency_id: str) -> dict[str, Any] | None:
    return _read()["units"].get((agency_id or "").strip().lower())


def exists(agency_id: str) -> bool:
    return get(agency_id) is not None


def label(agency_id: str) -> str:
    unit = get(agency_id)
    return unit["name"] if unit else ""


def listed_match(state: str, name: str) -> dict[str, str] | None:
    """The listed agency this name is, if it is one.

    Matched on the full name and on the abbreviation, after folding case,
    punctuation and the small words — so "Texas Commission on Environmental
    Quality", "TEXAS COMMISSION ENVIRONMENTAL QUALITY" and "TCEQ" all find
    the listed Texas entry.
    """
    from app import states
    wanted = _fold(name)
    short = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    for agency in states.agencies_for(state):
        if agency.get("test_only"):
            continue
        if _fold(agency.get("name", "")) == wanted:
            return agency
        abbrev = re.sub(r"[^a-z0-9]", "", str(agency.get("abbrev", "")).lower())
        if abbrev and len(abbrev) >= 3 and abbrev == short:
            return agency
    return None


def create(state: str, name: str, created_by: str) -> dict[str, Any]:
    """Record a unit somebody described, and give it an id of its own.

    Idempotent for the same person: registering the same name twice from one
    address — a double click, a back button, a second attempt after a code
    that never arrived — returns the unit already made rather than a second
    one with a second container.
    """
    from app import states
    code = (state or "").strip().upper()
    if code not in states.STATE_NAMES:
        return {"ok": False, "error": "Choose the state your organization is in."}
    cleaned = re.sub(r"\s+", " ", (name or "").strip())
    if not (MIN_NAME <= len(cleaned) <= MAX_NAME):
        return {"ok": False,
                "error": "Enter your organization's name as it appears on its "
                         "letterhead."}
    if not re.search(r"[A-Za-z]", cleaned):
        return {"ok": False, "error": "Enter your organization's name."}

    listed = listed_match(code, cleaned)
    if listed:
        return {"ok": False, "listed": listed.get("id", ""),
                "error": f"{listed.get('name')} is on our list. Choose it from "
                         f"the list instead — its email rule is what keeps "
                         f"somebody else from registering it."}

    address = (created_by or "").strip().lower()
    with _LOCK:
        held = _read()
        _purge_unverified(held)
        for unit in held["units"].values():
            if (unit["state"] == code and unit["created_by"] == address
                    and _fold(unit["name"]) == _fold(cleaned)):
                return {"ok": True, "unit": unit, "reused": True}

        mine = [u for u in held["units"].values()
                if u.get("created_by") == address]
        if len(mine) >= PER_PERSON:
            return {"ok": False, "limited": True,
                    "error": f"This address has already registered {len(mine)} "
                             f"organizations that are not on our list. Sign in "
                             f"to one of them, or contact the GAIUS team if you "
                             f"genuinely run more."}
        hour_ago = datetime.now(timezone.utc).timestamp() - 3600
        recent = sum(1 for u in held["units"].values()
                     if _stamp(u.get("created_at")) > hour_ago)
        if recent >= PER_HOUR:
            return {"ok": False, "limited": True, "error": BUSY}

        while True:
            unit_id = (f"{code.lower()}{MARK}{_slug(cleaned)}-"
                       f"{secrets.token_hex(2)}")
            if unit_id not in held["units"]:
                break
        unit = {"id": unit_id, "state": code, "name": cleaned,
                "abbrev": _initials(cleaned), "created_by": address,
                "created_at": _now(), "provenance": PROVENANCE}
        held["units"][unit_id] = unit
        _write(held)
    return {"ok": True, "unit": unit, "reused": False}


def _stamp(value: Any) -> float:
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _purge_unverified(held: dict[str, Any]) -> list[str]:
    """Drop units older than `UNVERIFIED_DAYS` that nobody ever verified.

    Verified means an organization exists for the unit — `verify_code`
    creates one the moment the code is read back. A unit with an
    organization is never touched, however old, because somebody's work is
    in it. Changes `held` in place; the caller writes it.
    """
    from app import tenancy
    live = set(tenancy._load().get("agencies", {}))
    cutoff = datetime.now(timezone.utc).timestamp() - UNVERIFIED_DAYS * 86400
    gone = [uid for uid, unit in held["units"].items()
            if uid not in live and _stamp(unit.get("created_at")) < cutoff]
    for uid in gone:
        del held["units"][uid]
    if gone:
        _write(held)
    return gone


def forget(agency_id: str) -> None:
    """Remove a unit whose registration never started.

    Called only when the registration that created it was refused on the spot
    — so a refused form does not leave an empty unit behind with nobody in it.
    """
    with _LOCK:
        held = _read()
        if held["units"].pop((agency_id or "").strip().lower(), None):
            _write(held)
