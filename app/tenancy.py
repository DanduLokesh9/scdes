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
   leave the judgment to a human:

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

import functools
from collections.abc import Mapping

import json
import re
import secrets
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "tenancy.json"


def review_required() -> bool:
    """Whether a human must release a registration before the agency opens.

    **Off by default, at the client's direction:** "if they register and verify,
    that's enough for today." The queue was the right design and the wrong
    trade — it put every new agency behind one person's inbox, and nobody had
    committed to a turnaround time that could be stated honestly on the waiting
    screen.

    What that costs is real and is not hidden. A verified mailbox proves the
    address belongs to the person holding it. It proves nothing about whether
    they may act for the agency, so the container records that no human checked,
    and every screen that matters says so rather than implying an approval
    happened.

    Set ``IIA_REVIEW_REQUIRED=1`` to put the queue back without a code change —
    which is the point of it being a switch rather than a deletion.
    """
    import os
    return os.getenv("IIA_REVIEW_REQUIRED", "").strip() in ("1", "true", "yes")

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
#: Agencies stated directly by the client. These outrank anything derived: a
#: convention the agency confirmed is stronger evidence than a pattern matched
#: across four published addresses.
CONFIRMED: dict[str, dict[str, Any]] = {
    # `scope` says whether the domain is the agency's or the whole state
    # government's. All three real entries below are the agency's own, which
    # is why their domain check is worth something on its own. Most states
    # are not like this — see `states._ENV_DOMAINS` — and a reviewer needs
    # the same field there, so it is carried here too rather than left to be
    # inferred from the absence of a warning.
    "sc.des": {
        "state": "SC",
        "label": "South Carolina Department of Environmental Services",
        "domains": ["des.sc.gov"],
        "scope": "agency",
        "convention": "first.last",
        "source": "confirmed by the client, August 2026",
    },
    "sc.ed": {
        "state": "SC",
        "label": "South Carolina Department of Education",
        "domains": ["ed.sc.gov"],
        "scope": "agency",
        "convention": "flast",
        "source": "confirmed by the client, August 2026",
    },
    "nm.env": {
        "state": "NM",
        "label": "New Mexico Department of the Environment",
        "domains": ["env.nm.gov"],
        "scope": "agency",
        # Domain checked, local part not. He gave the domain — "email of this
        # state must end with this @env.nm.gov" — and not the naming rule, and
        # the note above this table is the reason that matters: a guessed
        # convention that refuses a real deputy director is worse than no
        # rule. This is the loose path, recorded as loose.
        "convention": "any",
        "source": "domain stated by the client, September 2026; local-part "
                  "convention not yet confirmed",
    },
    "iia.test": {
        "state": "SC",
        # The same name the agency list shows (app/states.py). They differed,
        # so one organization read as two.
        "label": "DEMO agency — Innovative Infrastructure Advising",
        "domains": ["iiac.ai"],
        # "any" means the domain is checked and the local part is not. A test
        # container exists to exercise the platform, so it must not also impose
        # a naming rule on the people testing it — `lokesh@iiac.ai` is a real
        # working address and would fail a first.last rule.
        "convention": "any",
        "source": "IIA's own test container, August 2026",
        "test_only": True,
    },
    # A container for the automated checks, and nothing else.
    #
    # The browser harnesses answer real questions through the real endpoints —
    # that is the point of them — and they begin by blanking a list of keys so
    # the walk is deterministic. Run against `iia.test` they did exactly that
    # to the client's own answers: five blanked, nine overwritten, and the
    # audit log could not say what had been there because it records the key
    # and the actor but not the value.
    #
    # A shared test container cannot be both the place people try the product
    # and the place a destructive script runs unattended. So the scripts get
    # their own, and `tools/harness_identity.py` refuses to run anywhere else.
    "gaius.harness": {
        "state": "SC",
        "label": "TEST — automated checks only, not for people",
        "domains": ["harness.gaius.test"],
        "convention": "any",
        "source": "created for the check scripts, September 2026",
        "test_only": True,
        "harness_only": True,
    },
}


def _imported() -> dict[str, dict[str, Any]]:
    """Every agency the platform knows, from the registries that hold them.

    Two sources, walked the same way. South Carolina's 148 governmental units
    come from the client's own spreadsheet, each carrying the evidence its
    convention was derived from — see tools/import_sc_agencies.py. Every other
    state contributes its environmental agency from `states._ENV_DOMAINS`.

    Registration checks an address against the agency's convention, so an
    agency missing from this table gets the loose path — domain recognized,
    local part not checked, and the looseness reported rather than hidden.

    It used to walk South Carolina alone, which was right while South Carolina
    was the only state with a list. New Mexico got in because somebody added
    it to `CONFIRMED` by hand; fifty more would not have, and each one would
    have shown up in the dropdown and then failed at the door with no rule to
    check against.
    """
    from app import states
    out: dict[str, dict[str, Any]] = {}
    for code in states.STATE_NAMES:
        for a in states.agencies_for(code):
            entry = _from_registry(code, a)
            if entry:
                out[a["id"]] = entry
    return out


def _from_registry(code: str, a: dict[str, Any]) -> dict[str, Any] | None:
    """One registry row, as this module's table wants it.

    Returns `None` for a row with no domain, and for one the client has
    stated directly — `CONFIRMED` outranks anything derived, and merging the
    two the other way round would quietly replace his answer with ours.
    """
    if not a.get("domain") or a["id"] in CONFIRMED:
        return None
    return {
        "state": code,
        "label": a["name"],
        "domains": [a["domain"]],
        "convention": a.get("convention", "any"),
        # Whose domain it is, where the registry says. A statewide domain
        # admits every department in that state, so the approver needs to
        # know which kind they are looking at. Absent on the South Carolina
        # rows, which predate the field.
        "scope": a.get("scope", ""),
        # Every entry states where its rule came from — asserted by
        # test_known_conventions_are_evidenced_not_guessed, which is the
        # test that stops a guess from ever entering this table.
        "source": _why(a),
        "test_only": bool(a.get("test_only")),
    }


#: Where a row's rule came from, in the words a reviewer reads.
#:
#: Two axes, not one. `confidence` is about the local-part rule and
#: `domain_source` is about the domain, and a sentence that covered only one
#: of them would tell a reviewer the wrong thing about the other. The
#: South Carolina rows carry no `domain_source` — they predate the field, and
#: their domains came off the client's own spreadsheet — so they fall through
#: to the convention wording they have always had.
_LOCAL_PART = {
    "strong": "derived from the agency's own published staff addresses in "
              "the client's SC agency list, August 2026",
    "weak": "derived from a small sample of published staff addresses; the "
            "domain is checked, the local part loosely",
    "none": "listed in the client's SC agency list, August 2026; no staff "
            "addresses published, so the domain is checked and the local "
            "part is not",
}

_DOMAIN = {
    "stated": "the domain was stated by the client; no local-part "
              "convention has been confirmed, so the domain is checked and "
              "the local part is not",
    "checked": "the domain was verified against addresses the agency itself "
               "publishes, September 2026; no local-part convention has "
               "been confirmed, so the domain is checked and the local part "
               "is not",
    "unconfirmed": "the domain is this application's own reading and nobody "
                   "has confirmed it; the local part is not checked at all. "
                   "Approve on the person, not on the address",
}


def _why(a: dict[str, Any]) -> str:
    """The provenance sentence for one registry row."""
    whose = a.get("domain_source")
    if whose in _DOMAIN:
        said = _DOMAIN[whose]
        # A statewide domain is the weaker of the two shapes, and a reviewer
        # looking at one is doing all of the work themselves.
        if a.get("scope") == "statewide":
            said += (". This domain belongs to the whole state government "
                     "rather than to this agency, so it does not show which "
                     "department the person works in")
        return said
    return _LOCAL_PART.get(a.get("confidence", "none"),
                           "listed in the client's SC agency list, "
                           "August 2026")


@functools.lru_cache(maxsize=1)
def _known() -> dict[str, dict[str, Any]]:
    return {**_imported(), **CONFIRMED}


class _Known(Mapping):
    """The agency table, built once and read like a dict.

    A plain module-level dict would have to be built at import time, and
    building it imports `states`, which imports this module back. Deferring it
    behind a mapping keeps `KNOWN[...]` reading exactly as it did at all 12 call
    sites while breaking the cycle.
    """

    def __getitem__(self, key): return _known()[key]
    def __iter__(self): return iter(_known())
    def __len__(self): return len(_known())


KNOWN = _Known()

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


def testers() -> set[str] | None:
    """The allowlist, or ``None`` meaning "the whole test domain".

    Default is the whole of ``iiac.ai`` — everyone at IIA can test without
    anyone maintaining a list of colleagues. ``IIA_TESTERS`` narrows or closes
    it:

        (unset)                     anyone @iiac.ai
        IIA_TESTERS=none            nobody — what production sets
        IIA_TESTERS=a@iiac.ai,b@…   only those addresses
    """
    import os
    raw = os.environ.get("IIA_TESTERS")
    if raw is None:
        return None                                  # whole domain
    if raw.strip().lower() in ("", "none", "off", "0"):
        return set()                                 # closed
    listed = (a.strip().lower() for a in raw.split(",") if a.strip())
    return {a for a in listed if a.endswith("@" + TESTER_DOMAIN)}


def is_tester(email: str) -> bool:
    """Whether this address skips the approval queue.

    The domain check is outside the allowlist on purpose: an address off
    ``iiac.ai`` can never be a tester, however ``IIA_TESTERS`` is set. That way
    a typo or a careless edit widens nothing.
    """
    address = (email or "").strip().lower()
    if not address.endswith("@" + TESTER_DOMAIN):
        return False
    allowed = testers()
    return True if allowed is None else address in allowed


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

    # A unit that is not on the list has no domain to check. The address is
    # proven by the code that follows, which is the check that still means
    # something here; see `app/unlisted.py`. Recorded as its own confidence,
    # so nobody later reads "domain-only" and assumes a domain was checked.
    if not known:
        from app import unlisted
        if unlisted.exists(agency):
            return IdentityCheck(True, matched="any", domain=domain,
                                 confidence="unlisted")

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
        "recognize. Check both, or ask for your agency to be added.",
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
    data.setdefault("sessions", {})
    return data


def _save(data: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    STORE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ------------------------------------------------------------ sending codes

#: How many verification codes one address may be sent in an hour, across
#: registering, registering an unlisted unit, and signing in.
#:
#: Every one of those sends an email, and the unlisted door accepts any
#: address at all. Without a ceiling, somebody could put a stranger's address
#: into the form and press Register over and over, and this application's
#: mail account would do the flooding — at a cost to that person's inbox and
#: to whether anybody's mail provider trusts ours afterwards.
#:
#: Counted per recipient because the application cannot see the caller: the
#: proxy in front of it passes no client address, so every request arrives
#: from the same place. Four is room for a mistyped address, a code that went
#: to spam, and a second try; it is not room for a campaign.
CODES_PER_HOUR = 4

TOO_MANY_CODES = ("Several codes have already been sent to this address in the "
                  "last hour. Use the most recent one, or wait an hour and try "
                  "again — the limit is there so this form cannot be used to "
                  "flood somebody's inbox.")


def _recent_codes(data: dict[str, Any], address: str) -> list[str]:
    cutoff = _now() - timedelta(hours=1)
    kept = []
    for stamp in (data.get("sent") or {}).get(address, []):
        try:
            if datetime.fromisoformat(stamp) > cutoff:
                kept.append(stamp)
        except (TypeError, ValueError):
            continue
    return kept


def _may_send_code(data: dict[str, Any], address: str) -> bool:
    # The limit protects an inbox. The harness container's domain does not
    # exist and nothing is ever mailed to it, so there is no inbox to protect
    # — and the browser walks sign in once each, which spent its four codes an
    # hour and locked the leak scan out of its own container.
    if _is_harness_address(address):
        return True
    return len(_recent_codes(data, address)) < CODES_PER_HOUR


def _is_harness_address(address: str) -> bool:
    domain = str(address or "").rsplit("@", 1)[-1].strip().lower()
    return any(entry.get("harness_only") and domain in (entry.get("domains")
                                                       or [])
               for entry in KNOWN.values())


def _note_code_sent(data: dict[str, Any], address: str) -> None:
    """Record one send, and forget sends older than the window as it goes,
    so the store does not grow with every address anybody ever typed."""
    sent = data.setdefault("sent", {})
    sent[address] = _recent_codes(data, address) + [
        _now().isoformat(timespec="seconds")]
    for other in [a for a in sent if a != address]:
        if not _recent_codes(data, other):
            del sent[other]


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


def is_shared_test_container(agency: str) -> bool:
    """Whether this container is IIA's own test space rather than an agency's.

    Only containers explicitly marked ``test_only`` in KNOWN qualify. A real
    governmental unit can never become shared by configuration drift.
    """
    return bool(KNOWN.get((agency or "").strip().lower(), {}).get("test_only"))


def is_harness_container(agency: str) -> bool:
    """Whether this container exists solely for the automated checks.

    The checks call this before they write anything. A shared test container
    holds people's real attempts at the product; this one holds nothing anybody
    would miss, which is the only safe place for a script that starts by
    blanking answers.
    """
    return bool(KNOWN.get((agency or "").strip().lower(),
                          {}).get("harness_only"))


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
            "needs_admin": not any(m.get("role") in ("admin", "owner")
                                   for m in container.get("members", [])),
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

    # The agency has to be one the platform actually knows.
    #
    # `check_identity` below treats an unrecognised id as an agency with no
    # recorded convention and lets it through on the domain alone — right for a
    # real agency missing from the convention table, and wrong for a string that
    # names no agency at all. Without this, a typo (`sc.scde` for `sc.ed`)
    # created a container nothing could ever resolve: no name on the framework
    # it exported, no route to fix it, and it occupied an id a real registration
    # would then collide with.
    from app import states, unlisted
    # An unlisted unit is one the platform knows too — the person registering
    # it described it a moment ago, in `unlisted.create`, and it has an id.
    if code_state and code_state not in states.agency_ids() \
            and not unlisted.exists(code_state):
        return {"ok": False,
                "error": f"No agency is recorded as {code_state!r}. Choose one "
                         f"from the list rather than typing an identifier — the "
                         f"platform has to know the agency before it can hold a "
                         f"framework for it."}

    identity = check_identity(code_state, name, email)
    if not identity.ok:
        return {"ok": False, "error": identity.reason,
                "identity": identity.as_dict()}

    address = email.strip().lower()

    # An agency already claimed cannot be registered again — that is the whole
    # point of the container. Joining is by invitation from the owner.
    #
    # The one exception is a shared test container. Everyone at IIA is a tester,
    # so refusing the second colleague would mean only one person could ever try
    # the platform. They join as members instead of being turned away. This
    # applies ONLY where the container is marked test_only and the address is a
    # tester — a real agency is never shared this way, because two people each
    # authoring half a framework is exactly what the container rule prevents.
    existing = agency_state(code_state)
    shared = is_shared_test_container(code_state) and is_tester(address)
    if existing["exists"] and existing["status"] in ("active", "pending_approval") \
            and not shared:
        if existing.get("owner") == address:
            # It is them. Telling someone to ask themselves for access is the
            # kind of message that makes a product feel broken.
            return {"ok": False, "is_you": True,
                    "error": "You registered this agency already. Sign in "
                             "instead — a code goes to this address.",
                    "agency": existing}
        admins = admins_of(code_state)
        return {"ok": False, "taken": True,
                "error": (f"This agency has already been registered. Ask its "
                          f"admin, {admins[0].get('name') or 'named on its people page'}, "
                          f"to add you." if admins else
                          "This agency has already been registered, and the "
                          "GAIUS team is appointing its admin. Ask to be added "
                          "once they have."),
                "agency": existing}

    data = _load()
    if not _may_send_code(data, address):
        return {"ok": False, "throttled": True, "error": TOO_MANY_CODES}
    reg = Registration(
        state=code_state, name=name.strip(), title=title.strip(),
        email=address, phone=digits, created_at=_now().isoformat(timespec="seconds"),
        identity=identity.as_dict(), seniority=seniority_flag(title),
        attested=True,
    )
    code = issue_code()
    _note_code_sent(data, address)
    data["pending"][address] = {
        **reg.as_dict(),
        "code_hash": _hash_code(code),
        "code_expires": (_now() + timedelta(minutes=CODE_TTL_MINUTES))
                        .isoformat(timespec="seconds"),
        "attempts": 0,
    }
    _save(data)

    # Send it for real where the deployment can. The code is only ever returned
    # to the caller when it could NOT be sent — otherwise anyone who can reach
    # the endpoint could read the code for an address they do not control, and
    # the verification step would prove nothing.
    from app import mailer
    label = ((KNOWN.get(code_state, {}) or {}).get("label", "")
             or unlisted.label(code_state))
    delivery = mailer.send_code(address, code, agency=label,
                                minutes=CODE_TTL_MINUTES)

    result = {"ok": True, "registration": reg.as_dict(),
              "identity": identity.as_dict(),
              "expires_in_minutes": CODE_TTL_MINUTES,
              "emailed": bool(delivery.get("sent")),
              "delivery": ("Sent to " + address) if delivery.get("sent")
                          else delivery.get("reason", "could not send")}
    if not delivery.get("sent"):
        # From the delivery result, not a fixed sentence — see
        # `mailer.note_for`. This told an operator with all six SMTP
        # variables set to go and configure two of them.
        result["delivery_note"] = mailer.note_for(delivery)
        # And the code only where this deployment is allowed to show one. See
        # `mailer.may_show_code`: on a deployment that sends mail, a failed
        # send is an incident, and handing the code over would make
        # verification a formality for anybody who typed an address.
        if mailer.may_show_code_to(address):
            result["code"] = code
        else:
            result["mail_failed"] = True
    return result


def _hash_code(code: str) -> str:
    import hashlib
    return hashlib.sha256(code.encode()).hexdigest()


# ------------------------------------------------------------------ sessions

#: How long a proven address stays proven. Long enough not to be a nuisance
#: during a demo, short enough that a token copied off a shared machine is not
#: a permanent key.
SESSION_DAYS = 30


def issue_session(email: str) -> str:
    """Prove, from here on, that this browser belongs to this address.

    Issued only where a code has just been checked against the mailbox. Every
    other identity signal in this application is whatever the browser chose to
    send — `?email=`, `X-SCDES-User`, the capacity dropdown — which is fine for
    deciding what to *show* someone and useless for deciding what to *let* them
    read. Anything that crosses an agency boundary keys off this instead.

    The token is returned once and stored only as a hash, so the file this
    writes is not a set of working keys if it is ever read by the wrong person.
    """
    address = (email or "").strip().lower()
    if not address:
        return ""
    token = secrets.token_urlsafe(32)
    data = _load()
    data.setdefault("sessions", {})[_hash_code(token)] = {
        "email": address,
        "issued_at": _now().isoformat(timespec="seconds"),
        "expires": (_now() + timedelta(days=SESSION_DAYS))
                   .isoformat(timespec="seconds"),
    }
    _save(data)
    _note_session("sign_in", address, data)
    return token


def _note_session(action: str, email: str, data: dict[str, Any]) -> None:
    """Record a sign-in or sign-out in the hash-chained log.

    Added because nothing did. The client asked for a usage page reporting
    "how many hours he logged in", and five weeks of audit log held no event
    of that shape at all — every entry was somebody changing something, so
    the only thing derivable was time *between changes*. `app/usage.py` still
    infers that for the history it cannot go back and measure; from here on
    it has the real thing to count instead.

    Records the agency and the name already on file rather than anything the
    browser sent, and swallows its own failures: a log that cannot be written
    is a reason to look at the disk, not a reason to refuse somebody a
    session they have already proved they are entitled to.
    """
    try:
        from app.authz import default_log

        who = ""
        agency = ""
        for code, row in (data.get("agencies") or {}).items():
            for member in row.get("members") or []:
                if str(member.get("email", "")).lower() == email:
                    who = str(member.get("name") or "")
                    agency = code
                    break
            if agency:
                break
        if not agency:
            held = (data.get("pending") or {}).get(email) or {}
            who = str(held.get("name") or "")
            agency = str(held.get("state") or "")

        default_log().append(
            actor=email.split("@")[0][:60] or "unknown",
            role="member", action=action, target="session",
            outcome="allowed",
            # No address in the detail. The log is read by admins and exported
            # in reports, and an email is the one thing here that identifies a
            # person outside this application.
            detail={"actor_name": who[:120], "agency": agency})
    except Exception:                                         # noqa: BLE001
        pass


def session_email(token: str) -> str:
    """The address this token proves, or "" — expired, unknown, or absent."""
    raw = (token or "").strip()
    if not raw:
        return ""
    row = _load().get("sessions", {}).get(_hash_code(raw))
    if not row:
        return ""
    if _now().isoformat(timespec="seconds") > row.get("expires", ""):
        return ""
    return str(row.get("email", ""))


def end_session(token: str) -> None:
    """Signing out on a shared machine should not leave the key in the lock."""
    raw = (token or "").strip()
    if not raw:
        return
    data = _load()
    held = data.get("sessions", {}).pop(_hash_code(raw), None)
    if held is not None:
        _save(data)
        # The other half of the pair, so a sitting has an end as well as a
        # beginning and the time between them is measured rather than guessed.
        _note_session("sign_out", str(held.get("email", "")), data)


def end_sessions_for(email: str) -> int:
    """Retire every session for one address. Returns how many.

    Only the hash of a token is stored, so a token that has been lost cannot be
    retired by presenting it — and testing leaves exactly that behind: working
    admin credentials nobody holds any more and nobody can revoke. This is the
    way out, and it is the same operation a person wants when they think they
    have signed in somewhere they should not have.
    """
    address = (email or "").strip().lower()
    if not address:
        return 0
    data = _load()
    sessions = data.get("sessions", {})
    doomed = [h for h, row in sessions.items()
              if str(row.get("email", "")).lower() == address]
    for h in doomed:
        sessions.pop(h, None)
    if doomed:
        _save(data)
    return len(doomed)


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

    # A returning member. Their container already exists and they are already on
    # it; the code proved the mailbox, which is all this step is for.
    if pending.get("signin"):
        pending["status"] = "active"
        pending["verified_at"] = _now().isoformat(timespec="seconds")
        _save(data)
        return {"ok": True, "status": "active", "signin": True,
                "session": issue_session(address),
                "agency": agency_state(state),
                "next": "Signed in."}

    existing = data["agencies"].get(state)
    if existing and existing.get("status") in ("active", "pending_approval"):
        # Shared test container: join it rather than collide with it.
        if is_shared_test_container(state) and is_tester(address):
            if not any(m["email"] == address for m in existing["members"]):
                existing["members"].append({
                    "email": address, "name": pending["name"],
                    "title": pending["title"], "role": "member",
                    "added_at": _now().isoformat(timespec="seconds"),
                    "added_by": "tester bypass — shared test container",
                })
            pending["status"] = "active"
            pending["verified_at"] = _now().isoformat(timespec="seconds")
            _save(data)
            return {"ok": True, "status": "active", "tester": True,
                    "session": issue_session(address),
                    "agency": agency_state(state),
                    "next": "Joined the shared test container. Real agencies "
                            "are not shared this way — only the registrant can "
                            "add people."}
        return {"ok": False,
                "error": "That agency was registered by someone else while you "
                         "were verifying."}

    tester = is_tester(address)
    # Verification is the gate. Everything before it was still enforced — the
    # naming convention, the code, the container rules — and what was *not*
    # enforced is written onto the record rather than left to be assumed.
    queued = review_required() and not tester
    status = "pending_approval" if queued else "active"
    pending["status"] = status
    pending["verified_at"] = _now().isoformat(timespec="seconds")
    pending["tester"] = tester

    data["agencies"][state] = {
        "code": state,
        "status": status,
        "tester": tester,
        "approved_by": (
            "" if queued else
            "tester bypass — not reviewed" if tester else
            # Not blank, and not a name. A blank here reads as "approval
            # pending"; a name would be a lie. This states what happened.
            "not reviewed — opened on mailbox verification alone"),
        "authority_verified": False,
        # Who registered it. Since the admin change this grants nothing: the
        # registrant joins as a member, and the organization has no admin
        # until the GAIUS team appoints one (see "people" below). IIA's own
        # testers are made admin so the team can try the whole thing.
        "owner_email": address,
        "owner_name": pending["name"],
        "owner_title": pending["title"],
        "registered_by": address,
        "created_at": _now().isoformat(timespec="seconds"),
        "members": [{"email": address, "name": pending["name"],
                     "title": pending["title"],
                     "role": ADMIN if tester else MEMBER}],
        "seniority": pending.get("seniority", {}),
        "identity": pending.get("identity", {}),
    }
    _save(data)
    # Issued on every path that got here, including the queued one. The token
    # says which mailbox this is, not what its owner is allowed to do — someone
    # awaiting review has still proved who they are.
    session = issue_session(address)
    if tester:
        return {"ok": True, "status": "active", "tester": True,
                "session": session,
                "agency": agency_state(state),
                "next": "Tester account — everything is open. This is not how "
                        "a real registration behaves."}
    if queued:
        return {"ok": True, "status": "pending_approval",
                "session": session,
                "agency": agency_state(state),
                "next": "A reviewer confirms you hold delegated authority "
                        "before the agency opens. Verifying your mailbox "
                        "proves the address is yours, not that you may act for "
                        "the agency."}
    return {"ok": True, "status": "active", "authority_verified": False,
            "review_required": False,
            "session": session,
            "agency": agency_state(state),
            "needs_admin": True,
            "next": "Your agency is open. Note what this did and did not "
                    "prove: the code confirmed the mailbox is yours. Nobody "
                    "has checked whether you hold authority to set governance "
                    "for the agency — the framework you build is marked DRAFT "
                    "until someone who does adopts it. The GAIUS team appoints "
                    "its admin, who can then add your colleagues."}


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


# ------------------------------------------------------------------ people
#
# Two levels of say over who is in an organization, and neither reaches its
# work.
#
# **An organization's admins** add people, make people admins, and take people
# off — in their own organization and no other. There can be several. The
# last admin cannot be removed or made a member by another admin, so an
# organization is never left with nobody who can add anyone.
#
# **The GAIUS team's permanent owners** (`admin.admins()`: brett@, lokesh@ and
# dev@iiac.ai) appoint an organization's admins, in any organization of any
# state. They manage people only. Nothing here, or on the screens that call it,
# opens an organization's framework, answers or documents — the client's rule
# "THE ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE OR HAVE ACCESS TO OTHER
# AGENCIES" is about the work, and it holds for them as for everyone.
#
# Registering an organization no longer makes you its admin. The registrant
# joins as a member and can build the framework; the organization has no admin
# until a permanent owner appoints one. (IIA's own testers are the exception,
# so the team can still stand up an organization and try it end to end.)
#
# "owner" is what the one-admin model called the role, and containers written
# then still carry it. It reads as admin everywhere.

ADMIN = "admin"
MEMBER = "member"
_ADMIN_ROLES = ("admin", "owner")


def _is_admin_role(member: dict[str, Any]) -> bool:
    return member.get("role") in _ADMIN_ROLES


def _platform_owner(email: str) -> bool:
    from app import admin
    return admin.is_admin(email)


def admins_of(agency: str) -> list[dict[str, Any]]:
    container = _load()["agencies"].get((agency or "").strip().lower()) or {}
    return [m for m in container.get("members", []) if _is_admin_role(m)]


def is_agency_admin(agency: str, email: str) -> bool:
    address = (email or "").strip().lower()
    return bool(address) and any(m["email"] == address for m in admins_of(agency))


def organization_of(email: str, data: dict[str, Any] | None = None) -> str:
    """The one organization this address belongs to, or ''."""
    address = (email or "").strip().lower()
    data = data or _load()
    for code, container in data["agencies"].items():
        if any(m.get("email") == address for m in container.get("members", [])):
            return code
    return ""


def _may_manage(container: dict[str, Any], by_email: str,
                by_platform: bool) -> bool:
    if by_platform:
        return True
    address = (by_email or "").strip().lower()
    return any(m["email"] == address and _is_admin_role(m)
               for m in container.get("members", []))


def _refuse_manage() -> dict[str, Any]:
    return {"ok": False, "error": "Only an admin of this organization can change "
                                  "who is in it."}


def add_member(agency: str, by_email: str, name: str, title: str,
               email: str, role: str = MEMBER,
               by_platform: bool = False) -> dict[str, Any]:
    """An admin — or a permanent owner — adds somebody, as a member or an
    admin. Their address has to fit the organization's email rule, and it
    must not already belong to a different organization: sign-in finds one
    organization per address, so a second would be one they could never reach."""
    code = (agency or "").strip().lower()
    data = _load()
    container = data["agencies"].get(code)
    if not container or container.get("status") != "active":
        return {"ok": False, "error": "That agency is not active."}
    if not _may_manage(container, by_email, by_platform):
        return _refuse_manage()
    role = ADMIN if role == ADMIN else MEMBER

    identity = check_identity(code, name, email)
    if not identity.ok:
        return {"ok": False, "error": identity.reason}

    address = email.strip().lower()
    if any(m["email"] == address for m in container["members"]):
        return {"ok": False, "error": "That person is already on the agency."}
    elsewhere = organization_of(address, data)
    if elsewhere:
        # Not named: which organization somebody else belongs to is theirs.
        return {"ok": False, "error": "That address already belongs to another "
                                      "organization. One address can be in one "
                                      "organization."}

    container["members"].append({
        "email": address, "name": name.strip(), "title": title.strip(),
        "role": role,
        "added_at": _now().isoformat(timespec="seconds"),
        "added_by": (by_email or "").strip().lower(),
        **({"added_as": "GAIUS team"} if by_platform else {}),
    })
    _save(data)
    return {"ok": True, "agency": agency_state(code)}


def remove_member(agency: str, by_email: str, email: str,
                  by_platform: bool = False) -> dict[str, Any]:
    """Take somebody off the organization, and end their open sign-ins so
    they are out now rather than when their session happens to expire.

    An admin may remove anybody, themselves included, except the last admin.
    A permanent owner may remove anybody — the organization then waits for
    them to appoint another admin, as a new one does."""
    code = (agency or "").strip().lower()
    address = (email or "").strip().lower()
    data = _load()
    container = data["agencies"].get(code)
    if not container or container.get("status") != "active":
        return {"ok": False, "error": "That agency is not active."}
    if not _may_manage(container, by_email, by_platform):
        return _refuse_manage()
    gone = next((m for m in container["members"] if m["email"] == address), None)
    if gone is None:
        return {"ok": False, "error": "That person is not on this organization."}
    admins = [m for m in container["members"] if _is_admin_role(m)]
    if not by_platform and _is_admin_role(gone) and len(admins) == 1:
        return {"ok": False, "error": "They are the only admin. Make somebody "
                                      "else an admin first, so the organization "
                                      "is never left without one."}
    container["members"] = [m for m in container["members"]
                            if m["email"] != address]
    container.setdefault("removed", []).append({
        "email": address, "name": gone.get("name", ""),
        "title": gone.get("title", ""), "role": gone.get("role", ""),
        "removed_at": _now().isoformat(timespec="seconds"),
        "removed_by": (by_email or "").strip().lower(),
        **({"removed_as": "GAIUS team"} if by_platform else {})})
    data["sessions"] = {k: v for k, v in (data.get("sessions") or {}).items()
                        if v.get("email") != address}
    _save(data)
    return {"ok": True, "agency": agency_state(code),
            "removed": gone.get("name") or address}


def set_role(agency: str, by_email: str, email: str, role: str,
             by_platform: bool = False) -> dict[str, Any]:
    """Make somebody already on the organization an admin, or a member.
    Every change is kept on the record under `role_history`."""
    code = (agency or "").strip().lower()
    address = (email or "").strip().lower()
    role = ADMIN if role == ADMIN else MEMBER
    data = _load()
    container = data["agencies"].get(code)
    if not container or container.get("status") != "active":
        return {"ok": False, "error": "That agency is not active."}
    if not _may_manage(container, by_email, by_platform):
        return _refuse_manage()
    person = next((m for m in container["members"] if m["email"] == address), None)
    if person is None:
        return {"ok": False, "error": "Add them to the organization first."}
    was = ADMIN if _is_admin_role(person) else MEMBER
    if was == role:
        return {"ok": False, "error": f"They are already {'an admin' if role == ADMIN else 'a member'}."}
    admins = [m for m in container["members"] if _is_admin_role(m)]
    if role == MEMBER and not by_platform and len(admins) == 1:
        return {"ok": False, "error": "They are the only admin. Make somebody "
                                      "else an admin first."}
    person["role"] = role
    container.setdefault("role_history", []).append({
        "at": _now().isoformat(timespec="seconds"), "email": address,
        "name": person.get("name", ""), "from": was, "to": role,
        "by": (by_email or "").strip().lower(),
        **({"by_as": "GAIUS team"} if by_platform else {})})
    _save(data)
    return {"ok": True, "agency": agency_state(code),
            "name": person.get("name") or address, "role": role}


def appoint(agency: str, by_email: str, name: str, title: str,
            email: str) -> dict[str, Any]:
    """A permanent owner makes somebody an organization's admin.

    Somebody already on it is promoted. Somebody new is added as an admin —
    and if nobody has registered the agency yet, it is opened for them, so
    the team can bring an agency on rather than wait for it to find the
    door. The address still has to fit the agency's email rule, and the
    person still proves it with a code the first time they sign in."""
    if not _platform_owner(by_email):
        return {"ok": False, "error": "Only the GAIUS team can appoint an "
                                      "organization's admins."}
    code = (agency or "").strip().lower()
    address = (email or "").strip().lower()
    data = _load()
    container = data["agencies"].get(code)
    if container and any(m["email"] == address for m in container["members"]):
        return set_role(code, by_email, address, ADMIN, by_platform=True)
    if container is None:
        from app import states, unlisted
        listed = any(a.get("id") == code for s in list(states.STATE_NAMES)
                     + [states.FEDERAL_CODE] for a in states.agencies_for(s))
        if not listed and not unlisted.exists(code):
            return {"ok": False, "error": "There is no agency with that id."}
        if not _NAME_OK.match((name or "").strip()):
            return {"ok": False, "error": "Enter their full name."}
        identity = check_identity(code, name, address)
        if not identity.ok:
            return {"ok": False, "error": identity.reason}
        if organization_of(address, data):
            return {"ok": False, "error": "That address already belongs to "
                                          "another organization. One address "
                                          "can be in one organization."}
        data["agencies"][code] = {
            "code": code, "status": "active", "tester": False,
            "approved_by": f"opened by the GAIUS team ({by_email.strip().lower()})",
            "authority_verified": False,
            "owner_email": "", "owner_name": "", "owner_title": "",
            "registered_by": "", "opened_by": by_email.strip().lower(),
            "created_at": _now().isoformat(timespec="seconds"),
            "members": [], "seniority": {}, "identity": identity.as_dict(),
        }
        _save(data)
    return add_member(code, by_email, name, title, address, role=ADMIN,
                      by_platform=True)


def _label(code: str) -> str:
    """An organization's name for the GAIUS team's screens: its own name, or
    the name on the state or federal list, or its code as a last resort."""
    name = _agency_names(code).get("agency_label")
    if not name:
        try:
            from app import usage
            name = usage._state_of(code)[1]
        except Exception:                                     # noqa: BLE001
            name = ""
    return name or code


def pending_signups() -> list[dict[str, Any]]:
    """Sign-ups sent a code and not finished, and registrations waiting on a
    reviewer. For the GAIUS team's screen — names and addresses, no work."""
    data = _load()
    out = []
    for address, p in (data.get("pending") or {}).items():
        if p.get("status") not in ("pending_code", "pending_approval"):
            continue
        started = p.get("created_at") or ""
        if not started and p.get("code_expires"):
            try:
                started = (datetime.fromisoformat(p["code_expires"])
                           - timedelta(minutes=CODE_TTL_MINUTES)
                           ).isoformat(timespec="seconds")
            except ValueError:
                started = ""
        out.append({"email": address, "name": p.get("name", ""),
                    "title": p.get("title", ""), "agency": p.get("state", ""),
                    "organization": _label(p.get("state", "")),
                    "status": p["status"], "signin": bool(p.get("signin")),
                    "started": started, "attempts": p.get("attempts", 0),
                    "code_expired": (p.get("code_expires", "") or "")
                    < _now().isoformat(timespec="seconds")})
    out.sort(key=lambda r: r["started"])
    return out


def remove_pending(email: str, by_email: str) -> dict[str, Any]:
    """A permanent owner clears a sign-up that never finished. Kept, not
    forgotten: what was removed, when and by whom goes onto the store's own
    `removed_pending` list as well as the audit log."""
    if not _platform_owner(by_email):
        return {"ok": False, "error": "Only the GAIUS team can remove sign-ups."}
    address = (email or "").strip().lower()
    data = _load()
    p = (data.get("pending") or {}).get(address)
    if not p or p.get("status") not in ("pending_code", "pending_approval"):
        return {"ok": False, "error": "There is no unfinished sign-up for that "
                                      "address."}
    if p.get("status") == "pending_approval" and p.get("state") in data["agencies"]:
        return {"ok": False, "error": "That one is waiting on a reviewer, and its "
                                      "organization already exists. Review it "
                                      "instead."}
    data["pending"].pop(address)
    data.setdefault("removed_pending", []).append({
        "email": address, "name": p.get("name", ""), "agency": p.get("state", ""),
        "status": p.get("status", ""), "created_at": p.get("created_at", ""),
        "removed_at": _now().isoformat(timespec="seconds"),
        "removed_by": (by_email or "").strip().lower()})
    _save(data)
    return {"ok": True, "removed": p.get("name") or address,
            "agency": p.get("state", "")}


def organizations() -> list[dict[str, Any]]:
    """Every organization and who is in it — for the GAIUS team's screen.

    People only: names, titles, addresses and roles. Not a byte of any
    organization's framework, which lives in its own container and is never
    opened from here."""
    data = _load()
    out = []
    for code, c in data["agencies"].items():
        members = c.get("members", [])
        out.append({
            "agency": code,
            "organization": _label(code),
            "state": code.split(".", 1)[0].upper(),
            "status": c.get("status", ""),
            "created_at": c.get("created_at", ""),
            "test": bool(c.get("tester")) or code.endswith((".test", ".harness")),
            "needs_admin": not any(_is_admin_role(m) for m in members),
            "people": [{"email": m.get("email", ""), "name": m.get("name", ""),
                        "title": m.get("title", ""),
                        "role": ADMIN if _is_admin_role(m) else MEMBER,
                        "added_at": m.get("added_at", "")} for m in members],
        })
    out.sort(key=lambda o: (not o["needs_admin"], o["test"],
                            o["organization"].lower()))
    return out


def start_signin(email: str) -> dict[str, Any]:
    """Send a fresh code to someone who is already a member.

    Registering was the only door. Register claims an agency and refuses if it
    is taken, so the person who registered it and then signed out was told
    "this agency has already been registered by lokesh dandu — ask them to add
    you", about themselves, with nothing else to click. A one-way door into a
    product is a product nobody gets back into.

    This proves the same thing registration proves — control of the mailbox —
    and nothing more. It creates no container and claims no agency; it only
    issues a code to an address that is already on one.
    """
    address = (email or "").strip().lower()
    if "@" not in address:
        return {"ok": False, "error": "Enter the work email you registered "
                                      "with."}

    access = access_for(address)
    if access["status"] == "unregistered":
        # Deliberately not "no such account". Confirming which addresses exist
        # would let anyone map an agency's staff from the sign-in box.
        return {"ok": False, "unregistered": True,
                "error": "No registration was found for that address on this "
                         "agency. Check the spelling, or register instead."}

    data = _load()
    # The same ceiling as registering. Signing in only ever mails somebody
    # already on an organization, but that is still somebody whose inbox a
    # repeated press would fill.
    if not _may_send_code(data, address):
        return {"ok": False, "throttled": True, "error": TOO_MANY_CODES}
    code = issue_code()
    _note_code_sent(data, address)
    data["pending"][address] = {
        **data["pending"].get(address, {}),
        "state": access["state"],
        "name": access.get("name", ""),
        "title": access.get("title", ""),
        "email": address,
        "status": "pending_code",
        # The flag verify_code branches on: this is a returning member, so there
        # is no container to create and no agency to claim.
        "signin": True,
        "code_hash": _hash_code(code),
        "code_expires": (_now() + timedelta(minutes=CODE_TTL_MINUTES))
                        .isoformat(timespec="seconds"),
        "attempts": 0,
    }
    _save(data)

    from app import mailer
    label = ((KNOWN.get(access["state"], {}) or {}).get("label", "")
             or _agency_names(access["state"]).get("agency_label", ""))
    delivery = mailer.send_code(address, code, agency=label,
                                minutes=CODE_TTL_MINUTES)
    result = {"ok": True, "signin": True, "state": access["state"],
              "expires_in_minutes": CODE_TTL_MINUTES,
              "emailed": bool(delivery.get("sent")),
              # Carried here too. The registration path reported why a send
              # failed and this one did not, so signing in gave an operator
              # nothing at all to go on.
              "delivery": ("Sent to " + address) if delivery.get("sent")
                          else delivery.get("reason", "could not send")}
    if not delivery.get("sent"):
        result["delivery_note"] = mailer.note_for(delivery)
        if mailer.may_show_code_to(address):
            result["code"] = code
        else:
            result["mail_failed"] = True
    return result


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
                    **_agency_names(code),
                }
    pending = data["pending"].get(address)
    if pending:
        return {"allowed": False, "state": pending["state"],
                "status": pending["status"], "role": "",
                "name": pending.get("name", ""),
                "title": pending.get("title", "")}
    return {"allowed": False, "state": "", "status": "unregistered", "role": ""}


def _agency_names(code: str) -> dict[str, Any]:
    """The organization's own name for a signed-in screen to show.

    A listed agency's name is also on the dropdown, so the browser could find
    it there. An unlisted unit's is not — it is never offered to anybody else
    — and without this a person signing back in on a new browser landed on a
    header naming nothing, or worse, their state's environmental agency.
    """
    from app import unlisted
    unit = unlisted.get(code)
    if unit:
        return {"agency_label": unit["name"], "agency_abbrev": unit["abbrev"],
                "unlisted": True}
    known = KNOWN.get(code, {}) or {}
    return {"agency_label": known.get("label", ""), "agency_abbrev": "",
            "unlisted": False}


def _mail_configured() -> bool:
    try:
        from app import mailer
        return mailer.configured()
    except Exception:                                          # noqa: BLE001
        return False


def _delivery_note() -> str:
    return ("Codes are emailed to the address given." if _mail_configured()
            else "No mail is configured on this server, so the code is shown "
                 "on screen rather than emailed. That verifies nothing — set "
                 "SMTP_HOST and SMTP_FROM before real agencies register.")


def summary() -> dict[str, Any]:
    """What the registration screens need to draw themselves."""
    return {
        "conventions": {k: {"example": v["example"], "describe": v["describe"]}
                        for k, v in CONVENTIONS.items()},
        "known": {k: {"domains": v["domains"], "convention": v["convention"],
                      "source": v["source"]} for k, v in KNOWN.items()},
        "sibling_examples": SIBLING_EXAMPLES,
        "code_ttl_minutes": CODE_TTL_MINUTES,
        # Asked of the mailer rather than asserted. This line was previously a
        # fixed string claiming no mail path, which stayed wrong after SMTP was
        # configured — an interface confidently reporting the opposite of what
        # the server does is worse than one that says nothing.
        "notes": {
            "mailbox": "A verification code proves control of the mailbox.",
            # Derived, like the delivery note above and for the same reason.
            # This claimed a reviewer approves every first registrant, and kept
            # claiming it after the client switched the queue off — so the
            # verification screen promised a step that never came.
            "authority": _authority_note(),
            "delivery": _delivery_note(),
        },
        "email_configured": _mail_configured(),
        # The screens word themselves from this rather than restating the rule.
        "review_required": review_required(),
    }


def _authority_note() -> str:
    if review_required():
        return ("It proves nothing about seniority. A named reviewer approves "
                "the first registrant for each agency.")
    return ("It proves nothing about seniority, and nobody checks. The agency "
            "opens on mailbox verification alone, and the record says so — "
            "what you build stays a draft until whoever holds the authority "
            "adopts it.")
