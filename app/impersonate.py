"""View as — the GAIUS team sees an organization's screens as one of its people.

Asked for by the team: "an impersonating option so that we can see what they
are doing on their account and try helping them … only access by brett, dev
and lokesh accounts. Clients' work shouldn't get distracted by impersonation,
and there should be an option to exit impersonation."

What it is, exactly:

* **Only the three admins** (`admin.admins()`), and only from a proven session
  — the token issued when a code was read out of their own mailbox.
* **View only.** While it is on, every request from that admin's browser is
  answered as the chosen person, inside that person's organization — and
  anything that would save, change, upload or delete is refused. Nothing the
  organization has can be altered from here, by design rather than by care.
* **Nothing reaches the organization.** Their sessions, their screens and
  their own History are untouched: the record of it is written to the GAIUS
  team's side of the log (the admin's own organization), never theirs. This
  is the team's decision, made deliberately.
* **Ends** when the admin presses End impersonation, signs out, or the server
  restarts. It is held in memory, keyed on the admin's session, so it cannot
  outlive either.

Every start and end is on the audit log, with who looked at whom and how many
screens were opened — "log all choices and activities" applies here more than
anywhere.

This is the one place the client's rule — "THE ENTIRE MODULAR PROCESS IS NOT TO
EVER REFERENCE OR HAVE ACCESS TO OTHER AGENCIES" — is deliberately crossed,
for support, by the team, read-only.
"""

from __future__ import annotations

import contextvars
import hashlib
import threading
from datetime import datetime, timezone
from typing import Any

_LOCK = threading.Lock()
#: Session hash → the impersonation it carries.
_ACTIVE: dict[str, dict[str, Any]] = {}

#: The impersonation on the request being served, if any. Set by the server's
#: dispatcher for the life of one request.
_CURRENT: contextvars.ContextVar[dict[str, Any] | None] = contextvars.ContextVar(
    "gaius_impersonation", default=None)

#: The session token on the request being served, so the start and stop
#: endpoints can key on it without every handler being handed headers.
_TOKEN: contextvars.ContextVar[str] = contextvars.ContextVar(
    "gaius_session_token", default="")

#: The only writes allowed while viewing as somebody: ending it, and signing
#: out (which ends it too).
ALLOWED_WHILE_VIEWING = {("POST", "/api/admin/impersonate/stop"),
                         ("POST", "/api/session/end")}

VIEW_ONLY = ("You are viewing as {name} — view only. Nothing can be saved or "
             "changed. End impersonation to work as yourself again.")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _key(token: str) -> str:
    return hashlib.sha256((token or "").encode("utf-8")).hexdigest()


def _log(action: str, admin_email: str, detail: dict[str, Any]) -> None:
    """On the GAIUS team's side of the log: the admin's own organization, so
    the organization being viewed never sees it in its History."""
    try:
        from app import tenancy
        from app.authz import default_log
        own = tenancy.access_for(admin_email).get("state") or ""
        default_log().append(actor="gaius.team", role="ot", action=action,
                             target="GAIUS team", outcome="allowed",
                             detail={"agency": own, "by": admin_email,
                                     "actor_name": admin_email, **detail})
    except Exception:                                         # noqa: BLE001
        pass


def start(token: str, admin_email: str, target_email: str) -> dict[str, Any]:
    from app import admin, tenancy
    admin_email = (admin_email or "").strip().lower()
    target = (target_email or "").strip().lower()
    if not token or not admin.is_admin(admin_email):
        return {"ok": False, "error": "This is for the GAIUS team."}
    if target == admin_email:
        return {"ok": False, "error": "That is you."}
    access = tenancy.access_for(target)
    if not access.get("state") or access.get("status") in ("", "unregistered"):
        return {"ok": False, "error": "That address is not on any organization."}
    data = tenancy._load()
    container = data["agencies"].get(access["state"]) or {}
    member = next((m for m in container.get("members", [])
                   if m.get("email") == target), {})
    record = {
        "admin": admin_email,
        "email": target,
        "name": member.get("name") or target,
        "title": member.get("title", ""),
        "agency": access["state"],
        "organization": tenancy._label(access["state"]),
        "started": _now().isoformat(timespec="seconds"),
        "views": 0,
    }
    with _LOCK:
        _ACTIVE[_key(token)] = record
    _log("impersonation_started", admin_email,
         {"viewed_person": target, "viewed_agency": record["agency"]})
    return {"ok": True, "impersonating": public(record)}


def stop(token: str) -> dict[str, Any]:
    with _LOCK:
        record = _ACTIVE.pop(_key(token), None)
    if not record:
        return {"ok": True, "ended": False}
    seconds = int((_now() - datetime.fromisoformat(record["started"])).total_seconds())
    _log("impersonation_ended", record["admin"],
         {"viewed_person": record["email"], "viewed_agency": record["agency"],
          "seconds": seconds, "screens_opened": record["views"]})
    return {"ok": True, "ended": True, "name": record["name"]}


def for_session(token: str, proven_email: str) -> dict[str, Any] | None:
    """The impersonation this request carries — only while the session still
    belongs to the admin who started it, and that admin is still an admin."""
    if not token:
        return None
    from app import admin
    with _LOCK:
        record = _ACTIVE.get(_key(token))
        if not record:
            return None
        if record["admin"] != (proven_email or "").strip().lower() \
                or not admin.is_admin(proven_email):
            _ACTIVE.pop(_key(token), None)
            return None
        record["views"] += 1
        return dict(record)


def set_current(record: dict[str, Any] | None, session: str = ""
                ) -> tuple[contextvars.Token, contextvars.Token]:
    return _CURRENT.set(record), _TOKEN.set(session or "")


def reset(tokens: tuple[contextvars.Token, contextvars.Token]) -> None:
    _CURRENT.reset(tokens[0])
    _TOKEN.reset(tokens[1])


def session() -> str:
    return _TOKEN.get()


def current() -> dict[str, Any] | None:
    return _CURRENT.get()


def public(record: dict[str, Any] | None) -> dict[str, Any] | None:
    """What the screen is told: who is being viewed, and since when."""
    if not record:
        return None
    return {"name": record["name"], "title": record["title"],
            "email": record["email"], "organization": record["organization"],
            "since": record["started"],
            "says": VIEW_ONLY.format(name=record["name"])}


def refused(method: str, path: str) -> dict[str, Any] | None:
    """The refusal for a write while viewing, or None if it may go ahead."""
    record = current()
    if not record or method != "POST" or (method, path) in ALLOWED_WHILE_VIEWING:
        return None
    return {"ok": False, "view_only": True,
            "error": VIEW_ONLY.format(name=record["name"])}
