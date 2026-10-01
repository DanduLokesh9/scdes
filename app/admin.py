"""Who runs GAIUS, as opposed to who is governed by it.

Two different questions live in this application and they were being answered by
the same mechanism, which is why the bug queue leaked.

**Capacity** — operator, Office of Technology, the deciding body — is a
*governance* idea. It says what someone may do to their agency's own record.
The header lets a person choose their own capacity, deliberately: this is a
reference build with no SSO, the README says so, and for a demonstration it is
right that one person can walk the whole approval path. Nothing about that is
secret, and every choice is audited.

**Admin** is not a capacity. It is the handful of people at IIA who operate the
product itself — who read the reports users file, across every agency. That
crosses the one line the client drew hardest: *"THE ENTIRE MODULAR PROCESS IS
NOT TO EVER REFERENCE OR HAVE ACCESS TO OTHER AGENCIES."* An admin does see
across agencies, which is exactly why it cannot be something a user can select
from a dropdown.

So admin is keyed on a verified email address and nothing else. Not on capacity,
not on job title — the client's rule is "do not gate any activities based on
title", and this does not: a Secretary of State with the wrong address is not an
admin, and a junior developer on the list is. It is product ownership, not
seniority.

The address has to be *proven*, not asserted. `?email=` is whatever the browser
sends, so the check runs against the session token issued by tenancy.verify_code
when someone actually reads a code out of their inbox. See `server.session_email`.
"""

from __future__ import annotations

import os

#: The three accounts named by the client. Anyone else is not an admin, and
#: there is no path in the application to add to this — it is a deployment fact,
#: changed by whoever controls the deployment.
DEFAULT_ADMINS = (
    "brett@iiac.ai",
    "lokesh@iiac.ai",
    "dev@iiac.ai",
)

#: Overridable so the list can change without a code change. Comma-separated.
ENV_KEY = "GAIUS_ADMINS"


def admins() -> set[str]:
    """The current admin addresses, lowercased."""
    raw = os.getenv(ENV_KEY, "").strip()
    source = raw.split(",") if raw else DEFAULT_ADMINS
    return {a.strip().lower() for a in source if a.strip()}


def is_admin(email: str | None) -> bool:
    """Whether this address administers GAIUS.

    Takes an address the caller has already proven — passing an unverified one
    is the whole failure mode this module exists to prevent.
    """
    address = (email or "").strip().lower()
    return bool(address) and address in admins()


#: What to say when someone is refused. Deliberately does not name the admins:
#: the reports are other people's, and a refusal is not a place to publish a
#: staff list.
REFUSAL = ("Reported issues are read by the GAIUS team. Your own reports, and "
           "any replies to them, are on the bell.")
