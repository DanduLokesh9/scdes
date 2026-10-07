"""The daily technical report, emailed to the development team.

Every day at 5:00 PM Eastern (EST in winter, EDT in summer), if anybody
reported a bug since the previous day's report, the development team gets one
email saying where the bugs are and what is stopping organizations from
getting their work done. A day with no new bug reports sends nothing.

What the email carries, all from records the application already keeps:

1. **Each new bug report** — who reported it and from which organization,
   the screen, what they expected and what happened, and the evidence the
   report captured on its own: the errors the browser raised and the server
   calls that failed in the minute before it was filed. That is usually where
   the bug is.
2. **Which screens are drawing the reports.**
3. **Server errors** since the last report. The server's own failures were
   printed to the console and nowhere else, so they are kept here now —
   where, the kind of error, the file and line, never a request body.
4. **What is stopping people** — sign-ups sent a code and never finished,
   organizations whose framework has not moved for a week, the actions real
   people keep being refused, and the open bug backlog.

Everything is cleaned of addresses, long numbers and anything shaped like a
key before it is kept, except the reporter's own address on their own ticket,
which the team needs in order to reply. Test and automated accounts are left
out of the counts of what people hit.

Settings, all optional, read from the server's environment:

    GAIUS_REPORT_TO      comma-separated recipients (default: lokesh@iiac.ai,
                         dev@iiac.ai)
    GAIUS_REPORT_HOUR    hour of the day, Eastern, 0–23 (default: 17)
    GAIUS_REPORT_OFF     set to 1 to stop sending

From a shell on the server:

    python -m app.techreport --preview     print today's report, send nothing
    python -m app.techreport --send-now    send it now, whatever the time
"""

from __future__ import annotations

import html
import json
import os
import threading
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "techreport_state.json"
SERVER_ERRORS = ROOT / "data" / "server_errors.jsonl"

DEFAULT_TO = ("lokesh@iiac.ai", "dev@iiac.ai")
DEFAULT_HOUR = 17
KEEP_DAYS = 30
MAX_ERROR_FILE = 5 * 1024 * 1024
STUCK_SIGNUP_HOURS = 24
STALLED_DAYS = 7

_LOCK = threading.Lock()
_RUNNING = threading.Event()


# ---------------------------------------------------------------- settings

def recipients() -> list[str]:
    raw = os.getenv("GAIUS_REPORT_TO", "").strip()
    source = raw.split(",") if raw else DEFAULT_TO
    return [a.strip().lower() for a in source if "@" in a]


def send_hour() -> int:
    try:
        hour = int(os.getenv("GAIUS_REPORT_HOUR", "").strip() or DEFAULT_HOUR)
    except ValueError:
        return DEFAULT_HOUR
    return hour if 0 <= hour <= 23 else DEFAULT_HOUR


def switched_off() -> bool:
    return os.getenv("GAIUS_REPORT_OFF", "").strip().lower() in ("1", "true", "yes")


# ---------------------------------------------------------------- time

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def eastern(now_utc: datetime | None = None) -> datetime:
    """Eastern time, with daylight saving, on any machine — the same rule
    the rest of the application uses for a South Carolina organization."""
    from app import clock
    now_utc = now_utc or _utcnow()
    minutes = clock.offset_for_agency("sc", now_utc)
    return now_utc.astimezone(timezone(timedelta(minutes=minutes if minutes is not None else -300)))


def _parse(iso: str) -> datetime | None:
    try:
        when = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def _et(iso: str) -> str:
    """A stored UTC time, as the team reads it: Eastern."""
    when = _parse(iso)
    if when is None:
        return str(iso or "")
    local = eastern(when)
    hour = local.hour % 12 or 12
    return (f"{local:%b} {local.day}, {hour}:{local.minute:02d} "
            f"{'AM' if local.hour < 12 else 'PM'} {'EDT' if local.utcoffset() == timedelta(hours=-4) else 'EST'}")


# ---------------------------------------------------------------- scrubbing

def _scrub(text: Any, limit: int = 600) -> str:
    try:
        from app.bugs import scrub
        return scrub(str(text or ""))[:limit]
    except Exception:                                         # noqa: BLE001
        return str(text or "")[:limit]


# ---------------------------------------------------------------- server errors

def note_server_error(where: str, exc: BaseException, agency: str = "") -> None:
    """Keep one server failure for the report. Never raises — failing to
    record a failure must not become a second failure for the person who hit
    the first. Never the request body."""
    try:
        frame = traceback.extract_tb(exc.__traceback__)[-1] if exc.__traceback__ else None
        row = {"at": _utcnow().isoformat(timespec="seconds"),
               "where": _scrub(where, 200),
               "what": _scrub(f"{type(exc).__name__}: {exc}", 400),
               "at_line": f"{Path(frame.filename).name}:{frame.lineno}" if frame else "",
               "agency": str(agency or "")[:60]}
        with _LOCK:
            SERVER_ERRORS.parent.mkdir(parents=True, exist_ok=True)
            with SERVER_ERRORS.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
            if SERVER_ERRORS.stat().st_size > MAX_ERROR_FILE:
                lines = SERVER_ERRORS.read_text(encoding="utf-8").splitlines()
                SERVER_ERRORS.write_text("\n".join(lines[len(lines) // 2:]) + "\n",
                                         encoding="utf-8")
    except Exception:                                         # noqa: BLE001
        pass


def server_errors_since(since: datetime) -> list[dict[str, Any]]:
    """Grouped by fault, most frequent first."""
    if not SERVER_ERRORS.is_file():
        return []
    import re
    groups: dict[str, dict[str, Any]] = {}
    for line in SERVER_ERRORS.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        when = _parse(row.get("at", ""))
        if when is None or when < since:
            continue
        key = f"{row.get('where')}|{re.sub(r'[0-9]+', '#', row.get('what', ''))}"
        g = groups.setdefault(key, {"where": row.get("where", ""), "what": row.get("what", ""),
                                    "at_line": row.get("at_line", ""), "count": 0,
                                    "last": row["at"], "orgs": set()})
        g["count"] += 1
        g["last"] = max(g["last"], row["at"])
        if row.get("agency"):
            g["orgs"].add(row["agency"])
    out = []
    for g in groups.values():
        g["organizations"] = len(g.pop("orgs"))
        out.append(g)
    out.sort(key=lambda g: -g["count"])
    return out


# ---------------------------------------------------------------- the bugs

def _is_test(code: str) -> bool:
    return str(code or "").endswith((".test", ".harness"))


def _org_name(code: str) -> str:
    if not code:
        return "no organization"
    try:
        from app import tenancy, usage
        return tenancy._agency_names(code).get("agency_label") or usage._state_of(code)[1] or code
    except Exception:                                         # noqa: BLE001
        return code


def new_bugs(since: datetime) -> list[dict[str, Any]]:
    """Every bug reported since `since`, with the evidence it captured."""
    from app import bugs
    out = []
    for r in bugs._read():
        when = _parse(r.get("at", ""))
        if when is None or when < since:
            continue
        events = r.get("events") or []
        errors = [e.get("text", "") for e in events if e.get("kind") == "error"]
        failed = [f"{e.get('method', 'GET')} {e.get('text', '')} → {e.get('status')}"
                  for e in events if e.get("kind") == "network"
                  and str(e.get("status", "")).isdigit() and int(e["status"]) >= 400]
        out.append({
            "id": r.get("id", ""), "at": r.get("at", ""), "status": r.get("status", ""),
            "reporter": r.get("reporter", ""), "name": r.get("name", ""),
            "organization": _org_name(r.get("agency", "")), "test": _is_test(r.get("agency", "")),
            "view": r.get("view", "") or "—", "url": r.get("url", ""),
            "browser": r.get("browser", ""), "screen": r.get("screen", ""),
            "expected": r.get("expected", ""), "happened": r.get("happened", ""),
            "errors": errors[:5], "error_count": len(errors),
            "failed_calls": failed[:5], "failed_count": len(failed),
            "seen_before": r.get("seen_before", 0)})
    out.sort(key=lambda b: b["at"])
    return out


def backlog(now: datetime) -> dict[str, Any]:
    from app import bugs
    open_ = [r for r in bugs._read() if r.get("status") in (bugs.NEW, bugs.OPEN)]
    ages = [(now - w).total_seconds() / 86400 for w in
            (_parse(r.get("at", "")) for r in open_) if w]
    return {"open": len(open_), "oldest_days": round(max(ages), 1) if ages else 0}


# ---------------------------------------------------------------- what stops people

def stuck_signups(now: datetime) -> list[dict[str, Any]]:
    from app import tenancy
    out = []
    for email, p in (tenancy._load().get("pending") or {}).items():
        if p.get("status") != "pending_code" or _is_test(p.get("state", "")):
            continue
        when = _parse(p.get("created_at", ""))
        if when is None and p.get("code_expires"):
            # A returning member's sign-in carries no created time; the code
            # was issued its lifetime before it expires.
            expires = _parse(p["code_expires"])
            when = expires - timedelta(minutes=tenancy.CODE_TTL_MINUTES) if expires else None
        if when is None or (now - when).total_seconds() < STUCK_SIGNUP_HOURS * 3600:
            continue
        out.append({"name": p.get("name", ""), "email": email,
                    "organization": _org_name(p.get("state", "")),
                    "days": round((now - when).total_seconds() / 86400, 1)})
    out.sort(key=lambda s: -s["days"])
    return out


def stalled(now: datetime) -> list[dict[str, Any]]:
    from app import tenancy, usage
    last = {}
    try:
        for row in usage.report().get("agencies", []):
            last[row["agency"]] = row.get("last") or ""
    except Exception:                                         # noqa: BLE001
        pass
    out = []
    for code, container in (tenancy._load().get("agencies") or {}).items():
        if container.get("status") != "active" or _is_test(code):
            continue
        progress = usage.progress_of(code)
        if progress.get("adopted") or progress.get("percent", 0) >= 100:
            continue
        seen = _parse(last.get(code, ""))
        idle = (now - seen).total_seconds() / 86400 if seen else None
        if idle is None or idle >= STALLED_DAYS:
            out.append({"organization": _org_name(code), "percent": progress.get("percent", 0),
                        "idle_days": round(idle, 1) if idle is not None else None})
    return out


def refusals(since: datetime) -> list[dict[str, Any]]:
    from app import usage
    try:
        rows = usage._read(usage._log_path())
    except Exception:                                         # noqa: BLE001
        rows = []
    counts: Counter = Counter()
    reasons: dict[str, str] = {}
    for r in rows:
        when = _parse(r.get("at", ""))
        if str(r.get("outcome")) != "denied" or when is None or when < since:
            continue
        d = r.get("detail") or {}
        agency = str(d.get("agency") or "")
        if _is_test(agency) or usage._is_robot(str(d.get("actor_name") or ""), agency):
            continue
        action = str(r.get("action") or "unknown")
        counts[action] += 1
        reasons[action] = _scrub(r.get("reason") or d.get("reason") or "", 160)
    # System wording, so it follows the product's word rules ("tool", never
    # the banned word). A reporter's own words are quoted as written instead.
    import re
    tool = lambda s: re.sub(r"(?i)model", "tool", s)          # noqa: E731
    return [{"action": tool(a), "count": n, "reason": tool(reasons.get(a, ""))}
            for a, n in counts.most_common(8)]


# ------------------------------------------------- saves that did not happen
#
# Sep 29: 111 of a client's framework answers were saved under no
# organization while her screen looked normal, and nobody knew for three
# days. The server now refuses such a change (server._proven_session_gate,
# _no_organization_gate) and the screen says so; these make sure the team
# hears about it the same day too.

REFUSED = ROOT / "data" / "refused_saves.jsonl"
HOLDING = ROOT / "data" / "agencies" / "~unresolved"


def note_refused_save(claimed_email: str, organization: str, path: str, why: str) -> None:
    """One refused change. The address is the one the browser claimed — the
    team needs it to reach the person — and nothing of what they typed."""
    try:
        row = {"at": _utcnow().isoformat(timespec="seconds"),
               "email": str(claimed_email or "")[:200], "agency": str(organization or "")[:80],
               "where": _scrub(path, 120), "why": str(why or "")[:80]}
        with _LOCK:
            REFUSED.parent.mkdir(parents=True, exist_ok=True)
            with REFUSED.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row) + "\n")
    except Exception:                                         # noqa: BLE001
        pass


def refused_since(since: datetime) -> list[dict[str, Any]]:
    """Refused changes, one line per person and organization."""
    if not REFUSED.is_file():
        return []
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for line in REFUSED.read_text(encoding="utf-8").splitlines():
        try:
            row = json.loads(line)
        except ValueError:
            continue
        when = _parse(row.get("at", ""))
        if when is None or when < since:
            continue
        key = (row.get("email", ""), row.get("agency", ""))
        g = groups.setdefault(key, {"email": key[0] or "no address", "organization":
                                    _org_name(key[1]) if key[1] else "no organization",
                                    "count": 0, "first": row["at"], "last": row["at"],
                                    "why": row.get("why", ""), "where": set()})
        g["count"] += 1
        g["last"] = max(g["last"], row["at"])
        g["where"].add(row.get("where", ""))
    out = []
    for g in groups.values():
        g["where"] = sorted(g["where"])[:4]
        out.append(g)
    return sorted(out, key=lambda g: -g["count"])


def integrity_alarms(since: datetime) -> list[str]:
    """Anything that means work may have gone somewhere it should not.

    * The holding area for "no organization" has anything in it.
    * The log shows a change filed under no organization since the last
      report (sign-ins and sign-outs excepted — they are recorded before the
      person's organization is known).
    * An organization was active in the framework since the last report but
      none of its saved answers is that recent.
    """
    alarms: list[str] = []
    try:
        left = [f.name for f in HOLDING.iterdir() if f.is_file()
                and ".bak-" not in f.name and ".recovered-" not in f.name] if HOLDING.is_dir() else []
        if left:
            alarms.append(f"The no-organization holding area has {len(left)} file(s) in it "
                          f"({', '.join(left[:3])}) — somebody's work may have been saved there.")
    except OSError:
        pass
    try:
        from app import tenant, usage
        rows = usage._read(usage._log_path())
    except Exception:                                         # noqa: BLE001
        return alarms
    recent = [r for r in rows if (_parse(r.get("at", "")) or since) >= since]
    stray = [r for r in recent
             if ((r.get("detail") or {}).get("organisation") or (r.get("detail") or {}).get("agency")) == tenant.ANONYMOUS
             and r.get("action") not in ("sign_in", "sign_out")]
    if stray:
        names = sorted({(r.get("detail") or {}).get("actor_name", "") or "unnamed" for r in stray})
        alarms.append(f"{len(stray)} change(s) were filed under no organization, by "
                      f"{', '.join(names[:5])}.")
    active: Counter = Counter()
    for r in recent:
        if r.get("action") == "answer_framework_question":
            org = (r.get("detail") or {}).get("organisation") or (r.get("detail") or {}).get("agency") or ""
            if org and org != tenant.ANONYMOUS and not _is_test(org):
                active[org] += 1
    for org, n in active.items():
        if not _answers_saved_since(org, since):
            alarms.append(f"{_org_name(org)} answered {n} framework question(s) since the last "
                          f"report, but none of its saved answers is that recent.")
    return alarms


def _answers_saved_since(org: str, since: datetime) -> bool:
    try:
        from app import tenant, versions
        held = tenant.set_current(org)
        try:
            working = versions.state().get("working") or {}
        finally:
            tenant.reset(held)
    except Exception:                                         # noqa: BLE001
        return True                     # cannot tell: say nothing rather than alarm
    for value in working.values():
        when = _parse(value.get("at", "")) if isinstance(value, dict) else None
        if when and when >= since:
            return True
    return False


# ------------------------------------------------- a framework passing 70%
#
# Asked for (Oct 2026): "whoever completed 70% of their framework in their
# agency, send a report to the mailbox, same as the bug report." So it rides
# in the same 5 PM email, to the same people, and that email goes out on a
# day an organization first passes the mark even if no bug was reported.
# Each organization is reported once; the state file remembers which.

def public_url() -> str:
    return os.getenv("GAIUS_PUBLIC_URL", "").strip().rstrip("/") or "https://app.staging.governingai.us"


def milestone() -> int:
    try:
        value = int(os.getenv("GAIUS_MILESTONE_PERCENT", "").strip() or 70)
    except ValueError:
        return 70
    return value if 1 <= value <= 100 else 70


def _steps_left(org: str) -> list[str]:
    """The framework steps that still have questions open, e.g.
    "Step 06 · Your non-negotiables: 3 open"."""
    try:
        from app import module_one, tenant, versions
        held = tenant.set_current(org)
        try:
            answers = versions.state().get("working") or {}
        finally:
            tenant.reset(held)
        out = []
        for step in module_one.STEPS:
            left = [q for q in step.questions
                    if module_one.visible(q, answers) and not module_one.answered(q, answers)]
            if left:
                out.append(f"Step {step.number} · {step.title}: {len(left)} open")
        return out
    except Exception:                                         # noqa: BLE001
        return []


def frameworks_reached(already: set[str] | None = None) -> list[dict[str, Any]]:
    """Organizations at or past the mark that have not been reported yet."""
    from app import tenancy, tenant, usage
    mark = milestone()
    done = already or set()
    out = []
    for code, container in (tenancy._load().get("agencies") or {}).items():
        if code in done or code == tenant.ANONYMOUS or _is_test(code) \
                or container.get("status") != "active" or container.get("tester"):
            continue
        progress = usage.progress_of(code)
        if progress.get("percent", 0) < mark:
            continue
        people = [m.get("name") or m.get("email", "") for m in container.get("members", [])]
        out.append({"agency": code, "organization": _org_name(code),
                    "state": code.split(".", 1)[0].upper(),
                    "percent": progress.get("percent", 0),
                    "answered": progress.get("answered", 0), "asked": progress.get("asked", 0),
                    "adopted": bool(progress.get("adopted")),
                    "people": people[:8], "left": _steps_left(code)})
    return sorted(out, key=lambda r: -r["percent"])


# ---------------------------------------------------------------- the report

def build(since: datetime, now: datetime | None = None) -> dict[str, Any]:
    now = now or _utcnow()
    bugs_ = new_bugs(since)
    screens = Counter(b["view"] for b in bugs_ if not b["test"])
    return {
        "since": since.isoformat(timespec="seconds"),
        "until": now.isoformat(timespec="seconds"),
        "bugs": bugs_,
        "real_bugs": sum(1 for b in bugs_ if not b["test"]),
        "screens": screens.most_common(8),
        "server_errors": server_errors_since(since)[:15],
        "stuck": stuck_signups(now),
        "stalled": stalled(now),
        "refusals": refusals(since),
        "backlog": backlog(now),
        "refused_saves": refused_since(since),
        "alarms": integrity_alarms(since),
        "reached": frameworks_reached(set((_state().get("milestones") or {}).keys())),
        "milestone": milestone(),
    }


def worth_sending(report: dict[str, Any]) -> bool:
    """A new bug report, a refused save, or an alarm — any one is a reason to
    write; a quiet day sends nothing."""
    return bool(report["bugs"] or report.get("refused_saves") or report.get("alarms")
                or report.get("reached"))


def subject(report: dict[str, Any]) -> str:
    n = len(report["bugs"])
    day = eastern(_parse(report["until"]))
    extra = ""
    if report.get("alarms"):
        extra += f" · {len(report['alarms'])} alarm{'' if len(report['alarms']) == 1 else 's'}"
    saves = sum(g["count"] for g in report.get("refused_saves") or [])
    if saves:
        extra += f" · {saves} refused save{'' if saves == 1 else 's'}"
    reached = report.get("reached") or []
    if reached:
        extra += (f" · {len(reached)} framework{'' if len(reached) == 1 else 's'} "
                  f"past {report.get('milestone', 70)}%")
    return (f"GAIUS technical report — {n} new bug report{'' if n == 1 else 's'}{extra} · "
            f"{day:%a %b} {day.day}")


def text(report: dict[str, Any]) -> str:
    L = [subject(report), f"Covers {_et(report['since'])} to {_et(report['until'])}.", ""]
    if report.get("alarms"):
        L += ["ALARMS — WORK MAY HAVE GONE SOMEWHERE IT SHOULD NOT"]
        L += [f"  ! {a}" for a in report["alarms"]] + [""]
    if report.get("reached"):
        L += [f"REACHED {report.get('milestone', 70)}% OF THE FRAMEWORK"]
        for r in report["reached"]:
            L += [f"  {r['organization']} ({r['state']}) — {r['percent']}%, "
                  f"{r['answered']} of {r['asked']} answered{' · adopted' if r['adopted'] else ''}",
                  f"    Working on it: {', '.join(r['people']) or 'nobody named'}"]
            L += [f"    Still open: {line}" for line in r["left"][:6]] or ["    Every question asked so far is answered."]
        L += ["  Their answers, question by question, are attached as a PDF for each.",
              f"  To read them inside GAIUS instead: sign in at {public_url()} from DEMO agency, "
              "open Admin → Organizations, and choose View as next to one of their people.", ""]
    if report.get("refused_saves"):
        L += ["SAVES REFUSED (the person was told their session ended)"]
        L += [f"  {g['count']}× {g['email']} · {g['organization']} · {g['why']} · "
              f"last {_et(g['last'])} · {', '.join(g['where'])}" for g in report["refused_saves"]] + [""]
    L.append(f"NEW BUG REPORTS ({len(report['bugs'])})")
    for b in report["bugs"]:
        L += ["", f"{b['id']} · {_et(b['at'])}{' · TEST ACCOUNT' if b['test'] else ''}",
              f"  From: {b['name'] or 'no name'} <{b['reporter'] or 'no address'}> · {b['organization']}",
              f"  Screen: {b['view']}  ({b['url']})",
              f"  Expected: {b['expected'] or '—'}",
              f"  Happened: {b['happened']}"]
        if b["errors"]:
            L.append(f"  Browser errors ({b['error_count']}): " + " | ".join(b["errors"]))
        if b["failed_calls"]:
            L.append(f"  Failed server calls ({b['failed_count']}): " + " | ".join(b["failed_calls"]))
        if b["seen_before"]:
            L.append(f"  Looks like {b['seen_before']} earlier report(s).")
        L.append(f"  Browser: {b['browser']} · {b['screen']}")
    if report["screens"]:
        L += ["", "SCREENS DRAWING THE REPORTS"] + [f"  {v}: {n}" for v, n in report["screens"]]
    L += ["", f"SERVER ERRORS ({sum(g['count'] for g in report['server_errors'])})"]
    L += [f"  {g['count']}× {g['where']} — {g['what']} ({g['at_line']}) · "
          f"{g['organizations']} org(s) · last {_et(g['last'])}" for g in report["server_errors"]] \
        or ["  None."]
    L += ["", "WHAT IS STOPPING PEOPLE"]
    L += [f"  Stuck on a sign-in code: {s['name']} <{s['email']}> · {s['organization']} · "
          f"{s['days']} days" for s in report["stuck"]] or ["  Nobody is stuck on a sign-in code."]
    L += [f"  Framework stalled: {s['organization']} · {s['percent']}% · "
          f"{'never active' if s['idle_days'] is None else str(s['idle_days']) + ' days idle'}"
          for s in report["stalled"]]
    L += [f"  Refused {r['count']}×: {r['action']} — {r['reason']}" for r in report["refusals"]]
    bl = report["backlog"]
    L += ["", f"OPEN BUG BACKLOG: {bl['open']} open, oldest {bl['oldest_days']} days.",
          "", "Reply to people from Admin → Reported bugs. This email is sent at "
          f"{send_hour()}:00 Eastern on days with new bug reports, refused saves or alarms."]
    return "\n".join(L)


def html_body(report: dict[str, Any]) -> str:
    e = lambda s: html.escape(str(s or ""))                # noqa: E731
    parts = [f"<h1 style='font-size:18px'>{e(subject(report))}</h1>",
             f"<p>Covers {e(_et(report['since']))} to {e(_et(report['until']))}.</p>"]
    if report.get("alarms"):
        parts.append("<div style='border:2px solid #a40000;border-radius:6px;padding:10px;margin:8px 0'>"
                     "<h2 style='font-size:16px;margin:0 0 6px;color:#a40000'>Alarms — work may have gone "
                     "somewhere it should not</h2><ul>"
                     + "".join(f"<li>{e(a)}</li>" for a in report["alarms"]) + "</ul></div>")
    if report.get("reached"):
        parts.append(f"<h2 style='font-size:16px'>Reached {report.get('milestone', 70)}% of the framework</h2>")
        for r in report["reached"]:
            parts.append("<div style='border:1px solid #1f7a45;border-radius:6px;padding:10px;margin:8px 0'>"
                         f"<p style='margin:0'><b>{e(r['organization'])}</b> ({e(r['state'])}) — "
                         f"<b>{r['percent']}%</b>, {r['answered']} of {r['asked']} answered"
                         f"{' · adopted' if r['adopted'] else ''}</p>"
                         f"<p style='margin:4px 0'>Working on it: {e(', '.join(r['people']) or 'nobody named')}</p>"
                         + ("<ul style='margin:4px 0'>" + "".join(f"<li>{e(x)}</li>" for x in r["left"][:6]) + "</ul>"
                            if r["left"] else "<p style='margin:4px 0'>Every question asked so far is answered.</p>")
                         + "</div>")
        parts.append("<p>Their answers, question by question, are attached as a PDF for each. "
                     f"To read them inside GAIUS instead: <a href='{e(public_url())}'>sign in</a> from "
                     "DEMO agency, open <b>Admin → Organizations</b>, and choose <b>View as</b> next to "
                     "one of their people.</p>")
    if report.get("refused_saves"):
        parts.append("<h2 style='font-size:16px'>Saves refused</h2><p style='color:#555'>Each person "
                     "was told their session ended and asked to sign in again.</p>"
                     "<table style='border-collapse:collapse' cellpadding='4' border='1'><tr>"
                     "<th scope='col'>Times</th><th scope='col'>Who</th><th scope='col'>Organization</th>"
                     "<th scope='col'>Why</th><th scope='col'>Last</th></tr>"
                     + "".join(f"<tr><td>{g['count']}</td><td>{e(g['email'])}</td><td>{e(g['organization'])}</td>"
                               f"<td>{e(g['why'])}</td><td>{e(_et(g['last']))}</td></tr>"
                               for g in report["refused_saves"]) + "</table>")
    parts.append(f"<h2 style='font-size:16px'>New bug reports ({len(report['bugs'])})</h2>")
    for b in report["bugs"]:
        parts.append("<div style='border:1px solid #ccc;border-radius:6px;padding:10px;margin:8px 0'>"
                     f"<p style='margin:0'><b>{e(b['id'])}</b> · {e(_et(b['at']))}"
                     f"{' · <b>test account</b>' if b['test'] else ''}</p>"
                     f"<p style='margin:4px 0'>From {e(b['name'] or 'no name')} &lt;{e(b['reporter'])}&gt; · {e(b['organization'])}</p>"
                     f"<p style='margin:4px 0'>Screen: <b>{e(b['view'])}</b> <span style='color:#555'>({e(b['url'])})</span></p>"
                     f"<p style='margin:4px 0'><b>Expected:</b> {e(b['expected'] or '—')}</p>"
                     f"<p style='margin:4px 0'><b>Happened:</b> {e(b['happened'])}</p>"
                     + (f"<p style='margin:4px 0'><b>Browser errors ({b['error_count']}):</b> {e(' | '.join(b['errors']))}</p>" if b["errors"] else "")
                     + (f"<p style='margin:4px 0'><b>Failed server calls ({b['failed_count']}):</b> {e(' | '.join(b['failed_calls']))}</p>" if b["failed_calls"] else "")
                     + (f"<p style='margin:4px 0'>Looks like {b['seen_before']} earlier report(s).</p>" if b["seen_before"] else "")
                     + f"<p style='margin:4px 0;color:#555'>{e(b['browser'])} · {e(b['screen'])}</p></div>")

    def table(title: str, head: list[str], rows: list[list[Any]], empty: str) -> None:
        parts.append(f"<h2 style='font-size:16px'>{e(title)}</h2>")
        if not rows:
            parts.append(f"<p>{e(empty)}</p>")
            return
        parts.append("<table style='border-collapse:collapse' cellpadding='4' border='1'><tr>"
                     + "".join(f"<th scope='col' style='text-align:left'>{e(h)}</th>" for h in head) + "</tr>"
                     + "".join("<tr>" + "".join(f"<td>{e(c)}</td>" for c in r) + "</tr>" for r in rows)
                     + "</table>")
    table("Screens drawing the reports", ["Screen", "Reports"], [list(s) for s in report["screens"]], "None.")
    table("Server errors", ["Times", "Where", "Error", "File:line", "Orgs", "Last"],
          [[g["count"], g["where"], g["what"], g["at_line"], g["organizations"], _et(g["last"])]
           for g in report["server_errors"]], "None.")
    table("Stuck on a sign-in code", ["Name", "Email", "Organization", "Days"],
          [[s["name"], s["email"], s["organization"], s["days"]] for s in report["stuck"]], "Nobody.")
    table("Frameworks stalled a week or more", ["Organization", "Done", "Idle"],
          [[s["organization"], f"{s['percent']}%", "never active" if s["idle_days"] is None
            else f"{s['idle_days']} days"] for s in report["stalled"]], "None.")
    table("What real people were refused", ["Action", "Times", "Reason"],
          [[r["action"], r["count"], r["reason"]] for r in report["refusals"]], "Nothing.")
    bl = report["backlog"]
    parts.append(f"<p><b>Open bug backlog:</b> {bl['open']} open, oldest {bl['oldest_days']} days.</p>"
                 f"<p style='color:#555'>Reply to people from Admin → Reported bugs. Sent at "
                 f"{send_hour()}:00 Eastern on days with new bug reports, refused saves or alarms.</p>")
    return "<html><body style='font-family:Segoe UI,Arial,sans-serif;font-size:14px;color:#111'>" \
           + "".join(parts) + "</body></html>"


# ---------------------------------------------------------------- the schedule

def _state() -> dict[str, Any]:
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(state: dict[str, Any]) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
    tmp.replace(STATE)


def _answer_pdfs(report: dict[str, Any]) -> list[tuple[str, bytes, str]]:
    """The framework answers, as a PDF, for each organization past the mark
    (app/framework_report.py)."""
    from app import framework_report
    day = eastern(_parse(report["until"]))
    stamp = f"{day:%Y-%m-%d}"
    out = []
    for r in report.get("reached") or []:
        try:
            pdf = framework_report.build_pdf(
                r["agency"], r["organization"], percent=r["percent"],
                answered=r["answered"], asked=r["asked"], stamp=f"{day:%B} {day.day}, {day.year}")
            out.append((framework_report.filename(r["organization"], stamp), pdf, "application/pdf"))
        except Exception:                                     # noqa: BLE001
            traceback.print_exc()          # the email still goes, without that one
    return out


def _log_pdfs_sent(report: dict[str, Any], to: list[str]) -> None:
    """Each organization's answers that left GAIUS by email, and to whom — on
    the team's side of the log, which no organization's History reads."""
    try:
        from app import audit
        for r in report.get("reached") or []:
            audit.JsonlAuditLog(audit.DEFAULT_LOG).append(
                actor="gaius.team", role="ot", action="framework_answers_emailed",
                target="GAIUS team", outcome="allowed", mode="report",
                detail={"agency": "", "about": r["agency"], "percent": r["percent"],
                        "to": to, "actor_name": "Technical report"})
    except Exception:                                         # noqa: BLE001
        pass


def send(report: dict[str, Any]) -> list[dict[str, Any]]:
    from app import mailer
    subj, body, rich = subject(report), text(report), html_body(report)
    files = _answer_pdfs(report)
    extra = {"attachments": files} if files else {}
    sent = [{"to": to, **mailer.send(to, subj, body, rich, **extra)} for to in recipients()]
    delivered = [s["to"] for s in sent if s.get("sent")]
    if files and delivered:
        _log_pdfs_sent(report, delivered)
    return sent


def run_once(now_utc: datetime | None = None) -> dict[str, Any]:
    """The daily check. At or after the hour, once per Eastern day: build the
    report for everything since the last check, send it if any bug was
    reported, and move the window on either way."""
    now_utc = now_utc or _utcnow()
    local = eastern(now_utc)
    day = local.date().isoformat()
    with _LOCK:
        state = _state()
        if switched_off() or local.hour < send_hour() or state.get("last_day") == day:
            return {"ran": False}
        since = _parse(state.get("window_start", "")) or (now_utc - timedelta(days=1))
        report = build(since, now_utc)
        outcome: dict[str, Any] = {"ran": True, "day": day, "bugs": len(report["bugs"])}
        if worth_sending(report):
            outcome["sent"] = send(report)
            # Each organization past the mark is reported once — but only
            # once it has actually been sent to somebody; a failed send tries
            # again tomorrow.
            if report.get("reached") and any(s.get("sent") for s in outcome["sent"]):
                marks = dict(state.get("milestones") or {})
                for r in report["reached"]:
                    marks[r["agency"]] = {"day": day, "percent": r["percent"]}
                state["milestones"] = marks
                outcome["reached"] = [r["agency"] for r in report["reached"]]
        state.update({"last_day": day, "window_start": now_utc.isoformat(timespec="seconds")})
        history = list(state.get("history") or [])[-60:]
        history.append({"day": day, "bugs": outcome["bugs"],
                        "sent_to": [s["to"] for s in outcome.get("sent", []) if s.get("sent")],
                        "failed": [f"{s['to']}: {s.get('reason')}" for s in outcome.get("sent", [])
                                   if not s.get("sent")]})
        state["history"] = history
        _save(state)
    return outcome


def start(interval: int = 60) -> None:
    """Check once a minute, in the background, for the life of the server."""
    if _RUNNING.is_set():
        return
    _RUNNING.set()

    def loop() -> None:
        while _RUNNING.is_set():
            try:
                run_once()
            except Exception:                                 # noqa: BLE001
                traceback.print_exc()
            time.sleep(interval)

    threading.Thread(target=loop, name="technical-report", daemon=True).start()


def stop() -> None:
    _RUNNING.clear()


if __name__ == "__main__":                                    # pragma: no cover
    import sys
    since = _parse(_state().get("window_start", "")) or (_utcnow() - timedelta(days=1))
    report = build(since)
    if "--send-now" in sys.argv:
        for s in send(report):
            print(s)
    else:
        print(text(report))
