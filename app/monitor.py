"""Is the interface still answering?

The client: "Would love if it also had an 'accessibility monitor', something
which scans/tests API connections at a fixed interval to detect outages."

An AI tool that reads from a system nobody is watching fails silently. The
answers keep coming, they are simply stale, or wrong, or the tool has quietly
fallen back to something else — and the first anybody hears of it is a
complaint. Checking on a clock is how an outage becomes a fact with a
timestamp instead of an argument about when it started.

What a probe is
---------------

One request, to see whether something answers. `HEAD`, falling back to `GET`
where a server refuses `HEAD`, with a short timeout, no redirects followed,
no body read beyond what proves a response arrived, and no credentials sent
ever. It records that the door opened and how long it took. It does not go in.

That restraint is the design. The moment this holds a credential it becomes
the most valuable thing on the box, and "we watch your systems" is a far
smaller promise to keep than "we hold keys to your systems".

Why it will not probe a private address
---------------------------------------

A monitor that fetches whatever URL a tenant types is a port scanner with a
web interface, pointed at whatever network this server sits in. On a cloud
host the first thing it would reach is the instance metadata service, which
hands out credentials to anybody who asks.

So a probe resolves the name first and refuses anything that lands on a
loopback, private, link-local or reserved address, and refuses any scheme but
http and https.

The cost of that is real and worth stating plainly rather than hiding: **an
on-premises system on a private network cannot be watched from here.** Doing
it properly needs a small agent inside their own network reporting outwards,
which is a different piece of work. Until then the register records the
endpoint and this says, on the entry, that it cannot be reached from outside
— which is true, and better than a green tick that means nothing.
"""

from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from app.audit import CORPUS, atomic_write

#: Where the results live, per tenant.
MONITOR_FILE = CORPUS / "config" / "endpoint_checks.json"

#: How often the sweep runs, and how many results are kept per endpoint.
#: Fifteen minutes is frequent enough to catch an outage inside one working
#: hour and infrequent enough that nobody's operations team notices us.
INTERVAL_SECONDS = 15 * 60
KEEP = 96                      # a day of history at that interval

#: A probe that has not answered in this long is treated as down. Short,
#: because a slow answer is its own kind of outage.
TIMEOUT_SECONDS = 8

#: What the application calls itself when it knocks. Somebody reading their
#: own access log should be able to tell immediately who this is and why.
#:
#: ASCII only, and not as a style preference: HTTP headers are latin-1, and
#: the em-dash that was here made every single probe fail with "'latin-1'
#: codec can't encode character" — reported as the endpoint being down. A
#: monitor whose own request cannot be built is worse than no monitor, because
#: it reports outages that are its own.
AGENT = ("GoverningAI-AccessibilityMonitor/1.0 "
         "(+https://governingai.us/monitor; reachability only, no content)")

UP, DOWN, REFUSED, UNCHECKED = "up", "down", "refused", "unchecked"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _file():
    from app import tenant
    return tenant.scoped(MONITOR_FILE)


def _read() -> dict[str, Any]:
    path = _file()
    if not path.is_file():
        return {"checks": {}}
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"checks": {}}
    return held if isinstance(held, dict) else {"checks": {}}


def _write(data: dict[str, Any]) -> None:
    atomic_write(_file(), json.dumps(data, indent=2))


# ------------------------------------------------------------- is it allowed

def _addresses(host: str) -> list[str]:
    try:
        found = socket.getaddrinfo(host, None)
    except (OSError, UnicodeError):
        return []
    return [entry[4][0] for entry in found]


def permitted(url: str) -> tuple[bool, str]:
    """Whether this application may knock on that door, and why not if not.

    Resolved before the request is made, because a name that looks external
    can point anywhere — `metadata.example.com` resolving to 169.254.169.254
    is the whole trick. Every address the name resolves to has to be public;
    one private answer is enough to refuse.
    """
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https"):
        return False, ("Only http and https can be checked. Anything else "
                       "would be this application opening a connection of a "
                       "kind nobody asked it to.")
    if not parsed.hostname:
        return False, "That does not look like a web address."

    found = _addresses(parsed.hostname)
    if not found:
        return False, (f"{parsed.hostname} does not resolve from here. If it "
                       f"is an internal name, it will not be reachable from "
                       f"outside your network — see the note on private "
                       f"addresses.")

    for raw in found:
        try:
            address = ipaddress.ip_address(raw.split("%")[0])
        except ValueError:
            return False, f"Could not make sense of the address {raw!r}."
        if (address.is_private or address.is_loopback or address.is_reserved
                or address.is_link_local or address.is_multicast
                or address.is_unspecified):
            return False, (
                f"{parsed.hostname} resolves to {address}, which is inside a "
                f"private network. This monitor will not probe private "
                f"addresses — from a shared host that would be a port "
                f"scanner. Watching an internal system needs an agent inside "
                f"your own network.")
    return True, ""


# ------------------------------------------------------------------ the probe

def probe(url: str) -> dict[str, Any]:
    """Knock once. Never sends a credential, never reads the body."""
    allowed, why = permitted(url)
    if not allowed:
        return {"state": REFUSED, "at": _now(), "ms": 0, "status": 0,
                "why": why}

    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, method=method)
        request.add_header("User-Agent", AGENT)
        # Nothing is followed to a new host: a redirect is a fine way to be
        # sent somewhere the check above already refused.
        opener = urllib.request.build_opener(_NoRedirects)
        started = time.monotonic()
        try:
            with opener.open(request, timeout=TIMEOUT_SECONDS) as response:
                took = int((time.monotonic() - started) * 1000)
                return {"state": UP, "at": _now(), "ms": took,
                        "status": response.status, "why": ""}
        except urllib.error.HTTPError as exc:
            took = int((time.monotonic() - started) * 1000)
            # An answer is an answer. A 401 from an endpoint that needs a key
            # means the door is there and shut, which is exactly what a
            # reachability check should report as up.
            if exc.code in (401, 403, 405) and method == "HEAD":
                if exc.code == 405:
                    continue                      # HEAD not allowed; try GET
                return {"state": UP, "at": _now(), "ms": took,
                        "status": exc.code,
                        "why": "answered, and asked who we were"}
            return {"state": UP if exc.code < 500 else DOWN, "at": _now(),
                    "ms": took, "status": exc.code,
                    "why": f"HTTP {exc.code}"}
        except Exception as exc:                          # noqa: BLE001
            took = int((time.monotonic() - started) * 1000)
            if method == "GET":
                return {"state": DOWN, "at": _now(), "ms": took, "status": 0,
                        "why": str(exc)[:160]}
    return {"state": DOWN, "at": _now(), "ms": 0, "status": 0,
            "why": "no answer"}


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):        # noqa: D102
        return None


# ------------------------------------------------------------ keeping results

def record(holding_id: str, result: dict[str, Any]) -> dict[str, Any]:
    """Keep one result, and notice if it is a change."""
    held = _read()
    checks = held.setdefault("checks", {})
    entry = checks.setdefault(holding_id, {"history": []})
    was = entry.get("state")
    entry["state"] = result["state"]
    entry["last"] = result
    entry["history"] = ([result] + entry.get("history", []))[:KEEP]

    # A transition is the thing worth telling somebody about. A hundred
    # consecutive "down" results are one outage, not a hundred.
    if was and was != result["state"]:
        entry["changed_at"] = result["at"]
        entry["was"] = was
    _write(held)
    return entry


def state_of(holding_id: str) -> dict[str, Any]:
    entry = _read().get("checks", {}).get(holding_id)
    if not entry:
        return {"state": UNCHECKED, "history": []}
    return entry


def sweep() -> dict[str, Any]:
    """Check every holding that has somewhere to check, once."""
    from app import holdings

    # The stored rows, not `listing()` — that shapes them for the browser and
    # adds labels this has no use for.
    raw = holdings._read().get("holdings", [])
    results = []
    for row in raw:
        endpoint = str(row.get("endpoint") or "").strip()
        if not endpoint:
            continue
        result = probe(endpoint)
        record(str(row.get("id")), result)
        results.append({"id": row.get("id"), "name": row.get("name"),
                        **result})
    return {"checked": len(results), "at": _now(), "results": results}


def forget(holding_id: str) -> None:
    """Drop the results for a holding that is no longer on the register."""
    held = _read()
    if held.get("checks", {}).pop(holding_id, None) is not None:
        _write(held)


def summary() -> dict[str, Any]:
    """What the monitor knows, for the screen.

    Counted against the register as it stands now, not against everything the
    file has ever held. A holding removed from the register left its results
    behind, so the panel said "10 watched · 8 answering" on an organization
    with one endpoint recorded — a number nobody could trace to anything on
    the screen below it, which is worse than no number.
    """
    from app import holdings

    checks = _read().get("checks", {})
    live = {h.get("id") for h in holdings._read().get("holdings", [])
            if str(h.get("endpoint") or "").strip()}
    checks = {k: v for k, v in checks.items() if k in live}
    states = [c.get("state", UNCHECKED) for c in checks.values()]
    return {
        "watched": len(checks),
        "up": states.count(UP),
        "down": states.count(DOWN),
        "refused": states.count(REFUSED),
        "interval_minutes": INTERVAL_SECONDS // 60,
        "checks": checks,
    }


# ------------------------------------------------------------- on a clock

_RUNNING = threading.Event()


def _every_agency() -> list[str]:
    """Each tenant with a register of its own, plus the corpus owner.

    The sweep runs outside any request, so nothing has bound a tenant for it.
    Reading one agency's endpoints while another's context is set would write
    results into the wrong container — the same class of mistake as the reset
    that cleared the wrong tenant.
    """
    from app import tenant
    found = []
    if tenant.AGENCIES.is_dir():
        found = [p.name for p in tenant.AGENCIES.iterdir() if p.is_dir()]
    return found + [""]                # "" is the corpus owner


def run_once() -> dict[str, Any]:
    """One pass over every agency. Returns what it found, for logging."""
    from app import tenant
    done = {}
    for agency in _every_agency():
        token = tenant.set_current(agency or tenant.corpus_owner())
        try:
            outcome = sweep()
            if outcome["checked"]:
                done[agency or "corpus"] = outcome["checked"]
        except Exception:                                 # noqa: BLE001
            # One agency's bad entry must not stop the sweep for everybody.
            continue
        finally:
            tenant.reset(token)
    return {"agencies": done, "at": _now()}


def start(interval: int = INTERVAL_SECONDS) -> None:
    """Begin sweeping on a clock, in the background.

    A daemon thread rather than cron, so the monitor lives and dies with the
    application and there is no second thing to deploy. First sweep is delayed
    by one interval: a restart should not fire a burst of requests at
    somebody's production API.
    """
    if _RUNNING.is_set():
        return
    _RUNNING.set()

    def loop() -> None:
        while _RUNNING.is_set():
            time.sleep(interval)
            if not _RUNNING.is_set():
                return
            try:
                run_once()
            except Exception:                             # noqa: BLE001
                continue

    threading.Thread(target=loop, name="accessibility-monitor",
                     daemon=True).start()


def stop() -> None:
    _RUNNING.clear()
