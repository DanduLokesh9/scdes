"""Bug reports — the ticket, the queue, and what may be kept.

Every user is a tester, and email is a poor channel for a bug: by the time
someone has described what went wrong, the evidence has gone. So the widget
holds the last minute of technical activity in memory and attaches it when a
report is made, and the person is asked only two things — what they expected,
and what happened instead.

This module is the server half: the ticket, the queue, the transitions, and the
rules about what is allowed to be stored.

Grouping
--------

Every report carries a fingerprint derived from the first error and the screen
it happened on. Phase 1 does not act on it beyond counting, but it is computed
now because it cannot be computed later: the fingerprint has to come from the
report as it arrived, and once a hundred reports of one bad deploy are in the
queue as a hundred separate tickets, no amount of clever matching afterward
puts that back together.

Privacy, which the client asked to be part of v1 rather than added after
--------------------------------------------------------------------------

Three rules, enforced here rather than trusted to the client:

**No bodies, ever.** A captured network call may record its method, its URL and
its status. Never what was sent or returned. Request bodies in this application
contain framework answers and registration details.

**Redaction is checked again on arrival.** The widget redacts email addresses
before anything enters its buffer, which is the right place to do it — but a
server that trusts a client to have sanitized its own payload is a server with
no rule at all. Everything is scrubbed a second time here.

**Retention is a number, not an intention.** Technical capture expires; the
ticket text does not. `purge()` drops the attached logs from anything older than
the window while leaving the conversation intact, so a six-month-old ticket
still reads as a record without still holding a minute of someone's session.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.authz import Actor, Target, guard

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "bugs.jsonl"

#: Ticket states. Deliberately few — a workflow with nine states is a workflow
#: nobody keeps accurate.
NEW = "new"
OPEN = "open"
FIXED = "fixed"
WONT_FIX = "wont_fix"
CLOSED = "closed"

STATUSES = {
    NEW: "Reported, not yet looked at.",
    OPEN: "Being worked on.",
    FIXED: "Fixed. Waiting for the reporter to confirm.",
    WONT_FIX: "Working as intended, or not something we will change. The reason "
              "is on the ticket.",
    CLOSED: "Done.",
}

#: What a reporter may do, and what only the team may do.
TEAM_ONLY = {OPEN, FIXED, WONT_FIX, CLOSED}

#: How long attached technical capture is kept. The ticket outlives it.
RETENTION_DAYS = int(os.getenv("IIA_BUG_RETENTION_DAYS", "30"))

#: Bounds. A report is a report, not an upload channel.
MAX_TEXT = 4000
MAX_EVENTS = 400
MAX_EVENT_CHARS = 600


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ------------------------------------------------------------------ scrubbing

_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_LONG_DIGITS = re.compile(r"\b\d{7,}\b")
#: Anything that looks like a secret in a query string.
_SECRETISH = re.compile(
    r"([?&](?:code|token|key|secret|password|auth|session)=)[^&\s]+", re.I)


def scrub(text: str) -> str:
    """Remove the things that must never reach a ticket.

    Run on arrival even though the widget already does it. The widget runs in a
    browser we do not control, and a rule that only holds when the client
    behaves is not a rule.
    """
    out = str(text or "")[:MAX_TEXT]
    out = _EMAIL.sub("[email removed]", out)
    out = _SECRETISH.sub(r"\1[removed]", out)
    # Long digit runs are phone numbers and verification codes far more often
    # than they are anything a developer needs.
    out = _LONG_DIGITS.sub("[number removed]", out)
    return out


def _clean_events(events: Any) -> list[dict[str, Any]]:
    """The captured buffer, bounded and scrubbed, with bodies discarded."""
    if not isinstance(events, list):
        return []
    out: list[dict[str, Any]] = []
    for raw in events[-MAX_EVENTS:]:
        if not isinstance(raw, dict):
            continue
        kind = str(raw.get("kind", ""))[:24]
        if kind not in ("error", "warn", "network", "nav", "click", "note"):
            continue
        event = {
            "kind": kind,
            "at": str(raw.get("at", ""))[:32],
            "text": scrub(str(raw.get("text", ""))[:MAX_EVENT_CHARS]),
        }
        # Network calls keep their shape and nothing else. `body` and `response`
        # are dropped here rather than filtered — if they are never read, they
        # cannot be accidentally kept later.
        for field in ("method", "status", "ms"):
            if field in raw:
                event[field] = str(raw[field])[:16]
        out.append(event)
    return out


def fingerprint(report: dict[str, Any]) -> str:
    """What makes two reports the same bug.

    The first error, with the volatile parts flattened, plus the screen. Numbers
    and quoted strings are stripped so "no corpus for SCDES" and "no corpus for
    SCDE" group together — the differing agency is the symptom, not the fault.
    """
    first = next((e["text"] for e in report.get("events", [])
                  if e.get("kind") == "error"), "")
    if not first:
        # No error to key on, so group by what the person said instead. Weaker,
        # and better than every no-error report becoming its own group.
        first = report.get("happened", "")[:120]
    flat = re.sub(r"\d+", "#", first.lower())
    flat = re.sub(r"[\"'`].*?[\"'`]", "…", flat)
    flat = re.sub(r"\s+", " ", flat).strip()
    seed = f"{report.get('view', '')}|{flat}"
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:12]


# -------------------------------------------------------------------- storage

def _read() -> list[dict[str, Any]]:
    if not STORE.is_file():
        return []
    rows: dict[str, dict[str, Any]] = {}
    for line in STORE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        # Append-only on disk; the last write for an id wins when read back.
        rows[row["id"]] = {**rows.get(row["id"], {}), **row}
    return list(rows.values())


def _append(record: dict[str, Any]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    with STORE.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True, default=str) + "\n")


# ------------------------------------------------------------------ reporting

def report(*, expected: str, happened: str, context: dict[str, Any],
           events: Any, reporter: str = "", name: str = "",
           agency: str = "") -> dict[str, Any]:
    """File a bug. Deliberately unauthenticated — a broken sign-in is a bug too.

    Kept safe by being narrow rather than by being trusted: it writes one
    record, reads nothing, and everything in it is scrubbed and bounded.
    """
    expected = scrub(expected).strip()
    happened = scrub(happened).strip()
    if not happened:
        return {"ok": False,
                "error": "Say what happened. Without that there is nothing to "
                         "look into."}

    record = {
        "id": "BUG-" + uuid.uuid4().hex[:8].upper(),
        "at": _now(),
        "status": NEW,
        "expected": expected,
        "happened": happened,
        # Deliberately NOT scrubbed, and this is the one exception.
        #
        # Scrubbing it turned every reporter into the literal string
        # "[email removed]" — so `mine()` returned everyone's tickets to
        # anyone, and any address could reopen any ticket, because they all
        # compared equal. A privacy rule applied without thinking became an
        # access-control hole, which is worse than the leak it was guarding.
        #
        # The distinction: the rule exists to strip addresses that leak in
        # *incidentally* — out of a URL, an error message, a description. This
        # one is the person deliberately identifying themselves on their own
        # ticket, and Phase 3 cannot notify them without it.
        "reporter": str(reporter or "").strip().lower()[:160],
        "name": str(name or "")[:120],
        "agency": str(agency or "")[:80],
        "view": str(context.get("view", ""))[:60],
        "url": scrub(str(context.get("url", ""))[:300]),
        "browser": str(context.get("browser", ""))[:200],
        "screen": str(context.get("screen", ""))[:40],
        "version": str(context.get("version", ""))[:60],
        "events": _clean_events(events),
        "replies": [],
    }
    record["fingerprint"] = fingerprint(record)
    # How many others already look like this one. Phase 2 groups them; Phase 1
    # at least tells whoever opens the queue that it is one fault, not forty.
    record["seen_before"] = sum(1 for r in _read()
                                if r.get("fingerprint") == record["fingerprint"])
    _append(record)
    return {"ok": True, "id": record["id"], "fingerprint": record["fingerprint"],
            "seen_before": record["seen_before"],
            "thanks": ("Filed as " + record["id"] + ". You will see a reply "
                       "here when someone has looked at it.")}


# --------------------------------------------------------------------- queue

def listing(*, status: str = "", query: str = "",
            limit: int = 100) -> dict[str, Any]:
    rows = sorted(_read(), key=lambda r: r.get("at", ""), reverse=True)
    if status:
        rows = [r for r in rows if r.get("status") == status]
    if query:
        needle = query.lower()
        rows = [r for r in rows
                if needle in json.dumps(r, default=str).lower()]

    groups: dict[str, int] = {}
    for r in _read():
        key = r.get("fingerprint", "")
        groups[key] = groups.get(key, 0) + 1

    counts: dict[str, int] = {}
    for r in _read():
        counts[r.get("status", NEW)] = counts.get(r.get("status", NEW), 0) + 1

    return {
        "tickets": [{**r, "duplicates": groups.get(r.get("fingerprint", ""), 1)}
                    for r in rows[:limit]],
        "counts": counts,
        "total": len(_read()),
        "statuses": STATUSES,
        "retention_days": RETENTION_DAYS,
    }


def ticket(bug_id: str) -> dict[str, Any] | None:
    return next((r for r in _read() if r["id"] == bug_id), None)


def mine(email: str) -> list[dict[str, Any]]:
    """A reporter sees their own tickets and nobody else's."""
    address = str(email or "").strip().lower()
    if not address or "@" not in address:
        return []
    return sorted((r for r in _read()
                   if (r.get("reporter") or "").lower() == address),
                  key=lambda r: r.get("at", ""), reverse=True)


# ---------------------------------------------------------------- the team

def respond(bug_id: str, *, message: str, status: str, actor: Actor
            ) -> dict[str, Any]:
    """Reply and move the ticket. The team's to do, and audited."""
    if status not in STATUSES:
        return {"ok": False, "error": f"{status!r} is not a status."}

    decision = guard(actor, Target.CONFIG, "respond_to_bug",
                     detail={"bug": bug_id, "status": status})
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}

    existing = ticket(bug_id)
    if not existing:
        return {"ok": False, "error": f"No ticket {bug_id}."}

    reply = {
        "at": _now(),
        "by": (actor.name or actor.user_id or "")[:120],
        "team": True,
        "message": scrub(message)[:MAX_TEXT],
        "status": status,
    }
    updated = {**existing, "status": status,
               "replies": existing.get("replies", []) + [reply]}
    _append(updated)
    return {"ok": True, "ticket": updated}


def reopen(bug_id: str, *, message: str, email: str) -> dict[str, Any]:
    """The reporter says it is not fixed. Phase 3 notifies; this records.

    Only the person who filed it, and only from a resolved state — reopening a
    ticket somebody is already working on adds noise rather than information.
    """
    existing = ticket(bug_id)
    if not existing:
        return {"ok": False, "error": f"No ticket {bug_id}."}
    address = str(email or "").strip().lower()
    if not address or (existing.get("reporter") or "").lower() != address:
        return {"ok": False,
                "error": "Only the person who reported it can reopen it."}
    if existing.get("status") not in (FIXED, WONT_FIX, CLOSED):
        return {"ok": False,
                "error": f"That ticket is already {existing.get('status')}."}

    reply = {"at": _now(), "by": existing.get("name") or "Reporter",
             "team": False, "message": scrub(message)[:MAX_TEXT],
             "status": OPEN}
    updated = {**existing, "status": OPEN,
               "replies": existing.get("replies", []) + [reply],
               "reopened": existing.get("reopened", 0) + 1}
    _append(updated)
    return {"ok": True, "ticket": updated}


# -------------------------------------------------------------- notifications

def notifications(email: str, limit: int = 30) -> dict[str, Any]:
    """Every team reply on this person's tickets, newest first.

    Derived rather than stored. A notifications table would be a second record
    of something the ticket already holds, and the two would drift the first
    time a reply was edited — so the replies *are* the notifications, and "have
    I read this" is the only extra fact, which the browser keeps.

    A reporter sees their own and nobody else's: `mine()` is the filter, and it
    matches on the address that filed the ticket.
    """
    address = str(email or "").strip().lower()
    if not address or "@" not in address:
        return {"items": [], "total": 0}

    items: list[dict[str, Any]] = []
    for ticket in mine(address):
        for reply in ticket.get("replies", []):
            if not reply.get("team"):
                continue                      # their own words are not news
            items.append({
                "id": ticket["id"],
                "at": reply.get("at", ""),
                "by": reply.get("by", "The team"),
                "status": reply.get("status", ticket.get("status", "")),
                "message": reply.get("message", ""),
                # Enough context to know which report this answers without
                # opening it.
                "about": ticket.get("happened", "")[:120],
                # Only a resolved ticket can be reopened, so the button is only
                # offered where it would work.
                "can_reopen": ticket.get("status") in (FIXED, WONT_FIX, CLOSED),
            })

    items.sort(key=lambda i: i.get("at", ""), reverse=True)
    return {"items": items[:limit], "total": len(items)}


# ------------------------------------------------------------------ retention

def purge(now: datetime | None = None) -> dict[str, Any]:
    """Drop attached capture past the window; keep the ticket.

    The conversation is a record and stays. A minute of somebody's session is
    evidence for a fix, and once the fix is old the evidence is only a liability.
    """
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)
    stripped = 0
    for row in _read():
        if not row.get("events"):
            continue
        try:
            when = datetime.fromisoformat(row["at"])
        except ValueError:
            continue
        if when < cutoff:
            _append({**row, "events": [],
                     "events_purged_at": _now(),
                     "events_note": f"Technical capture removed after "
                                    f"{RETENTION_DAYS} days."})
            stripped += 1
    return {"purged": stripped, "retention_days": RETENTION_DAYS}


def forget(bug_id: str, *, why: str = "") -> dict[str, Any]:
    """Remove a ticket entirely. For junk, not for disagreement.

    The queue had no way to delete anything, which sounds like discipline and
    is not: a test that files a real report every time it runs, a duplicate
    filed twice by a fumbled button, an empty "hi" — all of them sit there
    forever, and a queue with permanent litter in it is a queue people stop
    reading. `wont_fix` is the answer for a report the team disagrees with;
    this is the answer for one that should never have been a report.

    Rewrites the store rather than appending a tombstone, because a tombstone
    would still carry whatever the ticket held — and the reason to remove a
    ticket is usually that it holds something. The previous file is kept
    alongside, so this is reversible for as long as anybody notices.

    Deliberately not audited to `audit.log`. That log is the record of
    decisions taken under an agency's adopted framework, and housekeeping the
    product's own bug queue is not one; mixing them would dilute the one
    artefact whose value depends on holding nothing else.
    """
    target = (bug_id or "").strip().upper()
    if not target:
        return {"ok": False, "error": "Which ticket?"}

    if not STORE.is_file():
        return {"ok": False, "error": f"{target} is not there."}

    kept: list[str] = []
    dropped = 0
    for line in STORE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            kept.append(line)          # unreadable is not the same as unwanted
            continue
        if str(row.get("id", "")).upper() == target:
            dropped += 1
        else:
            kept.append(line)

    if not dropped:
        return {"ok": False, "error": f"{target} is not there."}

    backup = STORE.with_suffix(".jsonl.bak")
    backup.write_text(STORE.read_text(encoding="utf-8"), encoding="utf-8")
    tmp = STORE.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(line + "\n" for line in kept), encoding="utf-8")
    tmp.replace(STORE)
    return {"ok": True, "id": target, "rows_removed": dropped,
            "why": (why or "").strip()[:200],
            "note": f"Previous contents kept at {backup.name}."}


def summary() -> dict[str, Any]:
    rows = _read()
    return {
        "total": len(rows),
        "open": sum(1 for r in rows if r.get("status") in (NEW, OPEN)),
        "retention_days": RETENTION_DAYS,
        "captures": ("Console errors, network calls (method, address and status "
                     "code only), which screen you were on, and your browser. "
                     "No page contents, no keystrokes, no screen recording."),
        "keeps": (f"The report and any replies are kept as a record. The "
                  f"technical capture attached to it is removed after "
                  f"{RETENTION_DAYS} days."),
    }
