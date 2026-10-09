"""Portal selection and email registration, before anyone reaches the map.

Two portals. The government / non-profit one is open and requires an email on a
public-sector or non-profit domain. The business one is announced but not built.

Three things worth being explicit about, because each is a limit rather than a
feature:

  · **This is eligibility, not verification.** A `.gov` address in a form field
    proves nothing — nobody has sent a confirmation link, and no link is sent
    here because there is no mail path in an offline build. What this does is
    record what someone claimed, and refuse the claims that are obviously out of
    scope. Real onboarding verifies the mailbox and, for an agency, federates
    with its identity provider.

  · **`.org` and `.us` are open registries.** `.gov` and `.mil` are restricted
    to US government bodies, and `.edu` to accredited institutions, so those
    carry real weight. Anyone can buy a `.org`. They are accepted because the
    brief asks for non-profits, who overwhelmingly use `.org`, but the gate they
    provide is a soft one and should not be mistaken for proof.

  · **The check lives here, not only in the browser.** A client-side rule is a
    suggestion — anyone can edit it in the console. The server applies the same
    rule to every registration so the recorded set stays meaningful.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "registrations.jsonl"

#: Portals offered on the first screen.
PORTALS: dict[str, dict[str, Any]] = {
    "government": {
        "key": "government",
        "label": "Government or non-profit",
        "blurb": "State, local, tribal or federal agencies, and non-profit "
                 "organizations operating a governance framework.",
        "open": True,
    },
    # A public body whose mail is not on .gov, .us or .org — a city on
    # cityofmonticello.net, a utility district, a court on scalc.net. The
    # suffix rule turned these away before they reached the map; they register
    # themselves as an organization not on the list, and the code sent to
    # their mailbox is what proves the address is theirs.
    "other": {
        "key": "other",
        "label": "Other public body",
        "blurb": "A city, town, district, court or other public organization "
                 "whose email is not on a .gov, .us or .org address. You add "
                 "your organization yourself, and a code sent to your work "
                 "email confirms it is yours.",
        "open": True,
    },
    "business": {
        "key": "business",
        "label": "Business",
        "blurb": "Vendors, consultancies and private operators. Not open yet — "
                 "the disclosure and procurement obligations differ enough to "
                 "need their own path rather than a relabelled one.",
        "open": False,
    },
}

#: Domain endings accepted for the government / non-profit portal. Suffix match,
#: so `deq.state.mt.us` and `epa.ohio.gov` both pass.
ELIGIBLE_SUFFIXES = (".gov", ".mil", ".edu", ".us", ".org", ".int")

#: Restricted registries — these genuinely evidence the sector.
STRONG_SUFFIXES = (".gov", ".mil", ".edu")

#: Exact domains the client's own registry vouches for, checked *in addition*
#: to the suffix rule and never instead of it.
#:
#: The suffix rule turns away fifteen bodies in the client's own list, because
#: not every government organisation sits on a restricted registry: the SC
#: Administrative Law Court is `scalc.net`, the DMV is `scdmvonline.com`,
#: Amtrak is `amtrak.com`, Santee Cooper is `santeecooper.com`. Refusing a
#: judge or a DMV administrator with "you need a .gov address" is wrong, and
#: loosening the suffix rule to admit `.com` would be worse. A named list is
#: the narrow fix: it admits exactly the organisations the client identified
#: and nobody else.
_ALLOWLIST_FILE = (Path(__file__).resolve().parent / "data"
                   / "domain_allowlist.json")


@functools.lru_cache(maxsize=1)
def _allowlist() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(_ALLOWLIST_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}                     # the suffix rule alone still works
    return raw.get("domains", {})


def allowlisted(domain: str) -> dict[str, str] | None:
    """What the registry says about this domain, or None.

    Exact match only. A suffix match here would make `notreally-amtrak.com`
    eligible, which is the whole reason this is a list of names rather than a
    pattern.
    """
    return _allowlist().get((domain or "").strip().lower())

#: Deliberately named so the refusal can explain itself. A consumer mailbox is
#: the most common wrong answer, and "use your work address" is more use than
#: "invalid domain".
CONSUMER_DOMAINS = {
    "gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "hotmail.com",
    "outlook.com", "live.com", "msn.com", "aol.com", "icloud.com", "me.com",
    "proton.me", "protonmail.com", "gmx.com", "mail.com", "zoho.com",
    "yandex.com", "qq.com",
}

#: Shape check only. Deliberately not the full RFC 5322 grammar: an over-clever
#: pattern rejects addresses that work, which is worse than letting one through
#: to a step that would have failed anyway.
_EMAIL = re.compile(r"^[^@\s]+@[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?"
                    r"(\.[A-Za-z0-9]([A-Za-z0-9-]*[A-Za-z0-9])?)+$")


@dataclass
class Eligibility:
    ok: bool
    reason: str = ""
    domain: str = ""
    #: "restricted" for .gov/.mil/.edu, "open" for .org/.us — see the module note.
    evidence: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_email(email: str, portal: str = "government") -> Eligibility:
    """Whether this address may proceed through `portal`."""
    address = (email or "").strip().lower()

    if portal not in PORTALS:
        return Eligibility(False, f"Unknown portal {portal!r}.")
    if not PORTALS[portal]["open"]:
        return Eligibility(False, f"The {PORTALS[portal]['label']} portal is "
                                  f"not open yet.")
    if not address:
        return Eligibility(False, "Enter your work email address.")
    if not _EMAIL.match(address):
        return Eligibility(False, "That does not look like an email address.")

    domain = address.rsplit("@", 1)[1]

    # Any address at all — the same rule as the unlisted registration it leads
    # to, where a twelve-person district may run on a personal mailbox. There
    # is no suffix to check; the code sent to the mailbox is the proof. A
    # personal mailbox is recorded as such, so nobody later mistakes it for
    # an organization's own domain.
    if portal == "other":
        return Eligibility(True, domain=domain,
                           evidence="other-personal" if domain in CONSUMER_DOMAINS
                           else "other")
    if domain in CONSUMER_DOMAINS:
        return Eligibility(False, "That is a personal mailbox. Use your "
                                  "organization's address, or go Back and "
                                  "choose Other public body.", domain=domain)
    vouched = allowlisted(domain)
    if not domain.endswith(ELIGIBLE_SUFFIXES) and not vouched:
        allowed = ", ".join(ELIGIBLE_SUFFIXES)
        return Eligibility(
            False,
            f"This option needs an address ending in {allowed}. If you work "
            f"for a public body whose email is on another address, go Back "
            f"and choose Other public body.",
            domain=domain)

    if domain.endswith(STRONG_SUFFIXES):
        evidence = "restricted"
    elif vouched:
        # Named in the client's own registry. Stronger evidence than a suffix,
        # which anyone can buy — this one says which body it belongs to.
        evidence = "listed"
    else:
        evidence = "open"
    return Eligibility(True, domain=domain, evidence=evidence)


def register(email: str, portal: str = "government",
             organisation: str = "") -> dict[str, Any]:
    """Record a registration if it is eligible. Returns the outcome either way.

    Appended to its own file, not to the governance audit log. That log is the
    record of decisions taken under an agency's adopted framework; sign-ups are
    not such decisions, and mixing them would dilute the one artefact whose
    value depends on containing nothing else.
    """
    verdict = check_email(email, portal)
    if not verdict.ok:
        return {"ok": False, **verdict.as_dict()}

    entry = {
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "email": email.strip().lower(),
        "domain": verdict.domain,
        "portal": portal,
        "organisation": organisation.strip()[:120],
        "evidence": verdict.evidence,
        # Recorded on the entry itself so a later reader cannot mistake these
        # for confirmed addresses.
        "verified": False,
        "note": "eligibility checked; mailbox not verified",
    }
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")

    return {"ok": True, **verdict.as_dict(), "registered": entry}


def portals() -> list[dict[str, Any]]:
    return list(PORTALS.values())


def summary() -> dict[str, Any]:
    """What the onboarding screens need in order to render themselves."""
    return {
        "portals": portals(),
        "eligible_suffixes": list(ELIGIBLE_SUFFIXES),
        "strong_suffixes": list(STRONG_SUFFIXES),
        "notice": ("Eligibility is checked, not verified. No confirmation email "
                   "is sent — this build has no mail path — so an address here "
                   "records what was claimed rather than proving it. In "
                   "production this step federates with the organization's own "
                   "identity provider."),
    }
