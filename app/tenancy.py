"""Who may register an agency, and who owns it once they have.

Three jobs, and they are not equally solvable. Being clear about which is which
is the point of this module's existence rather than a note bolted onto it.

1. **Does the email match the person and the agency?**  Solvable, and done here.
   State agencies use a fixed local-part convention — South Carolina's
   Department of Environmental Services is ``first.last@des.sc.gov``, its
   Department of Education is ``flast@ed.sc.gov``. Given a name, an address and a
   known convention, the three either agree or they do not. That is arithmetic.

2. **Does the person control that mailbox?**  Solvable, by sending a code to it
   and requiring it back. Standard, and implemented — with one caveat recorded
   in ``issue_code``: this build has no mail path, so the code is returned to the
   caller instead of emailed. That is a stand-in for a demo, not a design.

3. **Is the person an executive?**  *Not* solvable from an email address, and
   nothing here pretends otherwise. An address proves control of a mailbox. It
   says nothing about rank: a summer intern at ``des.sc.gov`` passes every check
   above, and a deputy director using a personal address fails them.

   What this module does instead is make the claim explicit and evidenced, and
   leave the judgement to a human:

   * the registrant states their title, and it goes on the record;
   * they attest, in the first person, that they hold delegated authority — a
     recorded assertion is worth more than an inferred one, because it is
     something they can be held to;
   * the registration enters ``pending_approval`` rather than ``active``, and a
     named reviewer approves it.

   ``SENIORITY_HINTS`` exists only to *flag* titles that do not look like
   delegated authority, so a reviewer looks harder. It is a prompt for a human,
   never a decision — and it is deliberately not used to reject anyone.

Once an agency is approved, its container is closed: only the registrant can add
people, and nobody else can register that agency. This is what stops four people
from one department each building a different half of the same framework.
"""

from __future__ import annotations

import json
import re
import secrets
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "tenancy.json"

#: How long a verification code is good for. Short enough to matter, long enough
#: to survive someone walking to another machine to read their mail.
CODE_TTL_MINUTES = 30


# --------------------------------------------------------------- conventions

def _first_last(first: str, last: str) -> str:
    return f"{first}.{last}"


def _f_last(first: str, last: str) -> str:
    return f"{first[:1]}{last}"


def _first_l(first: str, last: str) -> str:
    return f"{first}{last[:1]}"


def _firstlast(first: str, last: str) -> str:
    return f"{first}{last}"


def _first_underscore_last(first: str, last: str) -> str:
    return f"{first}_{last}"


def _lastf(first: str, last: str) -> str:
    return f"{last}{first[:1]}"


#: Local-part conventions, each with a plain-language description so a refusal
#: can say what was expected rather than "invalid".
CONVENTIONS: dict[str, dict[str, Any]] = {
    "first.last": {"build": _first_last, "example": "jane.smith",
                   "describe": "first name, a dot, then last name"},
    "flast": {"build": _f_last, "example": "jsmith",
              "describe": "first initial then last name"},
    "firstl": {"build": _first_l, "example": "janes",
               "describe": "first name then last initial"},
    "firstlast": {"build": _firstlast, "example": "janesmith",
                  "describe": "first name then last name, run together"},
    "first_last": {"build": _first_underscore_last, "example": "jane_smith",
                   "describe": "first name, an underscore, then last name"},
    "lastf": {"build": _lastf, "example": "smithj",
              "describe": "last name then first initial"},
}

#: What we actually know, keyed by *agency*, not by state.
#:
#: A state is not one governmental unit. South Carolina's environmental services
#: department uses ``first.last@des.sc.gov`` and its education department uses
#: ``flast@ed.sc.gov`` — same state, different rule. Keying on the state would
#: apply one department's convention to another and refuse real staff.
#:
#: Deliberately short. A guessed convention that rejects a real deputy director
#: is worse than no rule, so an agency absent from this table is checked against
#: *any* recognised convention and the looseness is reported rather than hidden.
KNOWN: dict[str, dict[str, Any]] = {
    "sc.des": {
        "state": "SC",
        "label": "South Carolina Department of Environmental Services",
        "domains": ["des.sc.gov"],
        "convention": "first.last",
        "source": "confirmed by the client, August 2026",
    },
    "sc.ed": {
        "state": "SC",
        "label": "South Carolina Department of Education",
        "domains": ["ed.sc.gov"],
        "convention": "flast",
        "source": "confirmed by the client, August 2026",
    },
    "iia.test": {
        "state": "SC",
        "label": "TEST agency — Innovative Infrastructure Advising",
        "domains": ["iiac.ai"],
        # "any" means the domain is checked and the local part is not. A test
        # container exists to exercise the platform, so it must not also impose
        # a naming rule on the people testing it — `lokesh@iiac.ai` is a real
        # working address and would fail a first.last rule.
        "convention": "any",
        "source": "IIA's own test container, August 2026",
        "test_only": True,
    },
}

#: Other South Carolina departments, recorded because the client cited them as
#: the pattern to follow. Not used for the environmental agency check; kept so
#: the shape of a state's conventions is visible rather than folklore.
SIBLING_EXAMPLES = [
    {"agency": "SC Department of Environmental Services",
     "domain": "des.sc.gov", "convention": "first.last"},
    {"agency": "SC Department of Education",
     "domain": "ed.sc.gov", "convention": "flast"},
]

#: Titles that do not, on their face, indicate delegated authority. Used ONLY to
#: raise a flag for the human reviewer. Never used to refuse a registration:
#: titles vary wildly between agencies, and a rule strict enough to catch
#: pretenders would also catch the "Administrator" who genuinely runs the place.
SENIORITY_HINTS = {
    "looks_delegated": [
        "director", "deputy", "chief", "commissioner", "secretary",
        "administrator", "superintendent", "officer", "counsel", "head",
        "manager", "lead", "principal", "president", "vice",
    ],
    "looks_junior": [
        "intern", "student", "trainee", "assistant to", "apprentice",
        "volunteer", "contractor", "temp",
    ],
}

#: Addresses that skip the human approval queue so the platform can be tested
#: end to end without waiting on a reviewer.
#:
#: Three deliberate constraints, because a bypass in a governance tool is exactly
#: the kind of thing that reaches production by accident:
#:
#:   1. **Only on the test domain.** An address outside ``iiac.ai`` is refused
#:      even if someone adds it to this list — enforced in ``is_tester``, not
#:      left to whoever edits the list.
#:   2. **Visible.** A tester session is flagged all the way to the interface,
#:      which shows a TESTER badge. A bypassed session must never be mistaken
#:      for a real one in a screenshot or a demo.
#:   3. **Switchable off.** Setting ``IIA_TESTERS=none`` in the environment
#:      empties this entirely, which is what a production deployment does.
#:
#: What it skips is the *approval* step only. The email convention check, the
#: verification code and the container rules all still apply — those are the
#: things worth testing, so bypassing them would defeat the purpose.
TESTER_DOMAIN = "iiac.ai"
_DEFAULT_TESTERS = ("lokesh@iiac.ai",)


def testers() -> set[str]:
    import os
    raw = os.environ.get("IIA_TESTERS")
    if raw is not None:
        if raw.strip().lower() in ("", "none", "off", "0"):
            return set()
        listed = tuple(a.strip().lower() for a in raw.split(",") if a.strip())
    else:
        listed = _DEFAULT_TESTERS
    return {a for a in listed if a.endswith("@" + TESTER_DOMAIN)}


def is_tester(email: str) -> bool:
    """Whether this address skips the approval queue. Domain-locked."""
    address = (email or "").strip().lower()
    return address.endswith("@" + TESTER_DOMAIN) and address in testers()


_LOCAL_OK = re.compile(r"^[a-z0-9][a-z0-9._\-]*$")
_NAME_OK = re.compile(r"^[\w'\-. ]{2,80}$", re.UNICODE)
_PHONE_DIGITS = re.compile(r"\D+")


# ------------------------------------------------------------------ matching

def _tidy(part: str) -> str:
    """Reduce a name part to what an email convention would use."""
    return re.sub(r"[^a-z]", "", (part or "").lower())


def split_name(name: str) -> tuple[str, str]:
    """First and last from a free-text name. Middle names are ignored.

    Hyphenated and apostrophed surnames are kept as one part, because that is
    how they appear in an address: O'Brien becomes ``obrien``.
    """
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return _tidy(parts[0]), ""
    return _tidy(parts[0]), _tidy(parts[-1])


@dataclass
class IdentityCheck:
    ok: bool
    reason: str = ""
    #: Which convention the address matched, if any.
    matched: str = ""
    domain: str = ""
    #: strict  — the agency's convention is on record and the address fits it
    #: loose   — no convention on record; the address fits a recognised pattern
    #: failed  — neither
    confidence: str = "failed"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_identity(agency: str, name: str, email: str) -> IdentityCheck:
    """Does the name, the address and the agency agree with each other?

    `agency` is an agency id such as ``sc.des`` — not a state code. Two
    departments in one state have different conventions, so checking against the
    state would refuse whichever of them was not encoded.
    """
    address = (email or "").strip().lower()
    if "@" not in address:
        return IdentityCheck(False, "That does not look like an email address.")
    local, _, domain = address.rpartition("@")
    if not _LOCAL_OK.match(local):
        return IdentityCheck(False, "That email address is not readable.",
                             domain=domain)

    known = KNOWN.get((agency or "").strip().lower())

    # A container whose convention is "any" checks the domain and stops there.
    if known and known["convention"] == "any":
        allowed = known["domains"]
        if not any(domain == d or domain.endswith("." + d) for d in allowed):
            return IdentityCheck(
                False, f"That address is not on {' or '.join(allowed)}.",
                domain=domain)
        return IdentityCheck(True, matched="any", domain=domain,
                             confidence="domain-only")

    first, last = split_name(name)
    if not first or not last:
        return IdentityCheck(
            False, "Enter your full name — first and last — so it can be "
                   "checked against your email address.", domain=domain)

    # The agency's domain, where we know it. Subdomains count: a regional office
    # on mail.des.sc.gov is still the department.
    if known:
        allowed = known["domains"]
        if not any(domain == d or domain.endswith("." + d) for d in allowed):
            return IdentityCheck(
                False, f"That address is not on {' or '.join(allowed)}. "
                       f"Register with your agency address.", domain=domain)

    # Compare the local part against the conventions.
    candidates = ([known["convention"]] if known else list(CONVENTIONS))
    stripped = re.sub(r"[^a-z0-9]", "", local)
    for key in candidates:
        spec = CONVENTIONS[key]
        expected = spec["build"](first, last)
        if local == expected or stripped == re.sub(r"[^a-z0-9]", "", expected):
            return IdentityCheck(True, matched=key, domain=domain,
                                 confidence="strict" if known else "loose")

    if known:
        spec = CONVENTIONS[known["convention"]]
        return IdentityCheck(
            False,
            f"That address does not match your name. This agency uses "
            f"{spec['describe']} — for {name.strip()} that would be "
            f"{spec['build'](first, last)}@{known['domains'][0]}.",
            domain=domain)

    return IdentityCheck(
        False,
        "The address does not match the name entered under any convention we "
        "recognise. Check both, or ask for your agency to be added.",
        domain=domain)


def seniority_flag(title: str) -> dict[str, Any]:
    """A prompt for the reviewer. Never a decision.

    Returns what the title looks like and, explicitly, that it is not proof.
    """
    text = (title or "").lower()
    junior = [w for w in SENIORITY_HINTS["looks_junior"] if w in text]
    senior = [w for w in SENIORITY_HINTS["looks_delegated"] if w in text]
    if junior:
        looks = "junior"
    elif senior:
        looks = "delegated"
    else:
        looks = "unclear"
    return {"looks": looks, "matched": junior or senior,
            "note": "A title is a claim, not evidence. A reviewer decides."}


# ------------------------------------------------------------------- storage

def _load() -> dict[str, Any]:
    if not STORE.is_file():
        return {"agencies": {}, "pending": {}}
    try:
        data = json.loads(STORE.read_text(encoding="utf-8")) or {}
    except (ValueError, OSError):
        return {"agencies": {}, "pending": {}}
    data.setdefault("agencies", {})
    data.setdefault("pending", {})
    return data


def _save(data: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# -------------------------------------------------------------- registration

@dataclass
class Registration:
    state: str
    name: str
    title: str
    email: str
    phone: str
    #: pending_code → pending_approval → active | rejected
    status: str = "pending_code"
    created_at: str = ""
    verified_at: str = ""
    approved_at: str = ""
    approved_by: str = ""
    identity: dict[str, Any] = field(default_factory=dict)
    seniority: dict[str, Any] = field(default_factory=dict)
    attested: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def agency_state(agency: str) -> dict[str, Any]:
    """Whether this agency is taken, and by whom."""
    code = (agency or "").strip().lower()
    data = _load()
    container = data["agencies"].get(code)
    if not container:
        return {"code": code, "exists": False, "active": False,
                "owner": "", "members": []}
    return {"code": code, "exists": True,
            "active": container.get("status") == "active",
            "status": container.get("status", ""),
            "owner": container.get("owner_email", ""),
            "owner_name": container.get("owner_name", ""),
            "members": container.get("members", []),
            "created_at": container.get("created_at", "")}


def start_registration(agency: str, name: str, title: str, email: str,
                       phone: str, attested: bool = False) -> dict[str, Any]:
    """Check everything checkable, then issue a code to the address given."""
    code_state = (agency or "").strip().lower()
    if not _NAME_OK.match((name or "").strip()):
        return {"ok": False, "error": "Enter your full name."}
    if not (title or "").strip():
        return {"ok": False,
                "error": "Enter your job title. It goes on the record, and a "
                         "reviewer sees it."}
    digits = _PHONE_DIGITS.sub("", phone or "")
    if len(digits) < 10:
        return {"ok": False,
                "error": "Enter a contact phone number with at least 10 digits."}
    if not attested:
        return {"ok": False,
                "error": "You need to confirm you hold delegated authority to "
                         "register on behalf of this agency."}

    identity = check_identity(code_state, name, email)
    if not identity.ok:
        return {"ok": False, "error": identity.reason,
                "identity": identity.as_dict()}

    # An agency already claimed cannot be registered again — that is the whole
    # point of the container. Joining is by invitation from the owner.
    existing = agency_state(code_state)
    if existing["exists"] and existing["status"] in ("active", "pending_approval"):
        return {"ok": False,
                "error": f"This agency has already been registered by "
                         f"{existing['owner_name'] or existing['owner']}. Ask "
                         f"them to add you.",
                "agency": existing}

    data = _load()
    address = email.strip().lower()
    reg = Registration(
        state=code_state, name=name.strip(), title=title.strip(),
        email=address, phone=digits, created_at=_now().isoformat(timespec="seconds"),
        identity=identity.as_dict(), seniority=seniority_flag(title),
        attested=True,
    )
    code = issue_code()
    data["pending"][address] = {
        **reg.as_dict(),
        "code_hash": _hash_code(code),
        "code_expires": (_now() + timedelta(minutes=CODE_TTL_MINUTES))
                        .isoformat(timespec="seconds"),
        "attempts": 0,
    }
    _save(data)
    return {"ok": True, "registration": reg.as_dict(),
            "identity": identity.as_dict(),
            "expires_in_minutes": CODE_TTL_MINUTES,
            # See issue_code: there is no mail path in this build.
            "code": code,
            "delivery": "not emailed — this build has no mail path"}


def _hash_code(code: str) -> str:
    import hashlib
    return hashlib.sha256(code.encode()).hexdigest()


def issue_code() -> str:
    """A six-digit code.

    In a real deployment this is emailed and never returned to the browser.
    Here there is no SMTP path — the application is offline by design — so the
    caller receives it and the response says plainly that it was not sent. Do
    not ship that: it turns verification into a formality.
    """
    return f"{secrets.randbelow(900000) + 100000}"


def verify_code(email: str, code: str) -> dict[str, Any]:
    """Confirm control of the mailbox, then create the agency container."""
    address = (email or "").strip().lower()
    data = _load()
    pending = data["pending"].get(address)
    if not pending:
        return {"ok": False, "error": "No registration is waiting for that "
                                      "address."}
    if pending.get("attempts", 0) >= 6:
        return {"ok": False, "error": "Too many attempts. Start again."}
    if _now().isoformat(timespec="seconds") > pending.get("code_expires", ""):
        return {"ok": False, "error": "That code has expired. Request another."}

    if _hash_code((code or "").strip()) != pending.get("code_hash"):
        pending["attempts"] = pending.get("attempts", 0) + 1
        _save(data)
        left = 6 - pending["attempts"]
        return {"ok": False,
                "error": f"That code is not right. {left} attempt(s) left."}

    state = pending["state"]
    if data["agencies"].get(state, {}).get("status") in ("active",
                                                        "pending_approval"):
        return {"ok": False,
                "error": "That agency was registered by someone else while you "
                         "were verifying."}

    # A tester's container opens immediately. Everything up to this point —
    # convention, code, container rules — was still enforced; only the wait for
    # a human reviewer is skipped, and the record says so.
    tester = is_tester(address)
    pending["status"] = "active" if tester else "pending_approval"
    pending["verified_at"] = _now().isoformat(timespec="seconds")
    pending["tester"] = tester

    # The container exists from here, but is not usable until a human approves
    # the registrant. Mailbox control is proven; authority is not.
    data["agencies"][state] = {
        "code": state,
        "status": "active" if tester else "pending_approval",
        "tester": tester,
        "approved_by": "tester bypass — not reviewed" if tester else "",
        "owner_email": address,
        "owner_name": pending["name"],
        "owner_title": pending["title"],
        "created_at": _now().isoformat(timespec="seconds"),
        "members": [{"email": address, "name": pending["name"],
                     "title": pending["title"], "role": "owner"}],
        "seniority": pending.get("seniority", {}),
        "identity": pending.get("identity", {}),
    }
    _save(data)
    if tester:
        return {"ok": True, "status": "active", "tester": True,
                "agency": agency_state(state),
                "next": "Tester account — the approval queue was skipped and "
                        "everything is open. This is not how a real "
                        "registration behaves."}
    return {"ok": True, "status": "pending_approval",
            "agency": agency_state(state),
            "next": "A reviewer confirms you hold delegated authority before "
                    "the agency opens. Verifying your mailbox proves the "
                    "address is yours, not that you may act for the agency."}


def approve(agency: str, reviewer: str, note: str = "") -> dict[str, Any]:
    """A named human confirms the registrant may act for the agency."""
    code = (agency or "").strip().lower()
    data = _load()
    container = data["agencies"].get(code)
    if not container:
        return {"ok": False, "error": "No registration for that agency."}
    if container.get("status") == "active":
        return {"ok": True, "agency": agency_state(code)}

    container["status"] = "active"
    container["approved_at"] = _now().isoformat(timespec="seconds")
    container["approved_by"] = (reviewer or "").strip()[:120]
    container["approval_note"] = (note or "").strip()[:300]
    owner = container.get("owner_email", "")
    if owner in data["pending"]:
        data["pending"][owner]["status"] = "active"
        data["pending"][owner]["approved_at"] = container["approved_at"]
        data["pending"][owner]["approved_by"] = container["approved_by"]
    _save(data)
    return {"ok": True, "agency": agency_state(code)}


def add_member(agency: str, by_email: str, name: str, title: str,
               email: str) -> dict[str, Any]:
    """The owner adds a colleague. Only the owner, for now, and by design."""
    code = (agency or "").strip().lower()
    data = _load()
    container = data["agencies"].get(code)
    if not container or container.get("status") != "active":
        return {"ok": False, "error": "That agency is not active."}
    if (by_email or "").strip().lower() != container.get("owner_email"):
        return {"ok": False,
                "error": "Only the person who registered this agency can add "
                         "people to it."}

    identity = check_identity(code, name, email)
    if not identity.ok:
        return {"ok": False, "error": identity.reason}

    address = email.strip().lower()
    if any(m["email"] == address for m in container["members"]):
        return {"ok": False, "error": "That person is already on the agency."}

    container["members"].append({
        "email": address, "name": name.strip(), "title": title.strip(),
        "role": "member",
        "added_at": _now().isoformat(timespec="seconds"),
        "added_by": container["owner_email"],
    })
    _save(data)
    return {"ok": True, "agency": agency_state(code)}


def access_for(email: str) -> dict[str, Any]:
    """What this address may see. The answer is one agency, or none."""
    address = (email or "").strip().lower()
    data = _load()
    for code, container in data["agencies"].items():
        for member in container.get("members", []):
            if member["email"] == address:
                return {
                    "allowed": container.get("status") == "active",
                    "state": code,
                    "role": member.get("role", "member"),
                    "status": container.get("status", ""),
                    "name": member.get("name", ""),
                    "title": member.get("title", ""),
                    "tester": is_tester(address),
                }
    pending = data["pending"].get(address)
    if pending:
        return {"allowed": False, "state": pending["state"],
                "status": pending["status"], "role": "",
                "name": pending.get("name", ""),
                "title": pending.get("title", "")}
    return {"allowed": False, "state": "", "status": "unregistered", "role": ""}


def summary() -> dict[str, Any]:
    """What the registration screens need to draw themselves."""
    return {
        "conventions": {k: {"example": v["example"], "describe": v["describe"]}
                        for k, v in CONVENTIONS.items()},
        "known": {k: {"domains": v["domains"], "convention": v["convention"],
                      "source": v["source"]} for k, v in KNOWN.items()},
        "sibling_examples": SIBLING_EXAMPLES,
        "code_ttl_minutes": CODE_TTL_MINUTES,
        "notes": {
            "mailbox": "A verification code proves control of the mailbox.",
            "authority": "It proves nothing about seniority. A named reviewer "
                         "approves the first registrant for each agency.",
            "delivery": "This build has no mail path, so the code is shown "
                        "rather than emailed. Production must send it.",
        },
    }
