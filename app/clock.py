"""What "today" means, for the person on this request.

Every stored timestamp stays in UTC — that is what an audit record needs, and
it is never rewritten. What changes is the *date* the application stamps on
things and offers as a default: an incident's write-down date, today's check,
a feed confirmed today. Those used the UTC date, so for anybody in the United
States after about eight in the evening Eastern, "today" was already
tomorrow.

The browser says where it is on every request — its current offset from UTC
in minutes, which already carries daylight saving — and `today()` answers in
that. No time-zone database is needed for it.

Where there is no browser to ask — the public report page works without
JavaScript — the organization's own state stands in: the main time zone of
the state in its agency code. That uses the system's zone database where
there is one, and a plain United States daylight-saving rule where there is
not, so the answer is the same on every machine.
"""

from __future__ import annotations

import contextvars
from datetime import date, datetime, timedelta, timezone

#: Minutes east of UTC for this request (New York in summer is -240), or
#: None where nothing said.
_OFFSET: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "gaius_utc_offset", default=None)

#: The widest real offsets are -12:00 and +14:00.
_LOWEST, _HIGHEST = -12 * 60, 14 * 60

#: Each state's main time zone: (zone name, standard offset in minutes,
#: observes daylight saving). Where a state spans two zones, the one most of
#: its people live in. Federal bodies are read as Eastern, where they sit.
_STATES: dict[str, tuple[str, int, bool]] = {
    **{s: ("America/New_York", -300, True) for s in (
        "ct", "de", "dc", "fl", "ga", "in", "me", "md", "ma", "mi", "nh",
        "nj", "ny", "nc", "oh", "pa", "ri", "sc", "vt", "va", "wv", "ky",
        "fed")},
    **{s: ("America/Chicago", -360, True) for s in (
        "al", "ar", "il", "ia", "ks", "la", "mn", "ms", "mo", "ne", "nd",
        "ok", "sd", "tn", "tx", "wi")},
    **{s: ("America/Denver", -420, True) for s in (
        "co", "id", "mt", "nm", "ut", "wy")},
    "az": ("America/Phoenix", -420, False),
    **{s: ("America/Los_Angeles", -480, True) for s in ("ca", "nv", "or", "wa")},
    "ak": ("America/Anchorage", -540, True),
    "hi": ("Pacific/Honolulu", -600, False),
}


def set_offset(raw: str | None) -> contextvars.Token:
    """Bind the browser's stated offset for this request. Anything that is
    not a real offset is ignored rather than trusted."""
    value: int | None = None
    try:
        minutes = int(str(raw or "").strip())
        if _LOWEST <= minutes <= _HIGHEST:
            value = minutes
    except ValueError:
        value = None
    return _OFFSET.set(value)


def reset(token: contextvars.Token) -> None:
    _OFFSET.reset(token)


def _us_dst(now_utc: datetime, standard: int) -> bool:
    """The United States rule since 2007: from 2 a.m. local on the second
    Sunday of March to 2 a.m. local on the first Sunday of November."""
    year = now_utc.year

    def nth_sunday(month: int, n: int) -> date:
        first = date(year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))

    local = now_utc + timedelta(minutes=standard)
    start = datetime.combine(nth_sunday(3, 2), datetime.min.time()) + \
        timedelta(hours=2)
    end = datetime.combine(nth_sunday(11, 1), datetime.min.time()) + \
        timedelta(hours=1)          # 2 a.m. daylight time is 1 a.m. standard
    naive = local.replace(tzinfo=None)
    return start <= naive < end


def offset_for_agency(agency: str, now_utc: datetime | None = None) -> int | None:
    """The organization's own state's offset right now, from its agency code
    ("sc.des" is South Carolina). None where the code names no state."""
    now_utc = now_utc or datetime.now(timezone.utc)
    prefix = str(agency or "").split(".", 1)[0].lower()
    known = _STATES.get(prefix)
    if not known:
        return None
    name, standard, observes = known
    try:
        from zoneinfo import ZoneInfo
        off = now_utc.astimezone(ZoneInfo(name)).utcoffset()
        if off is not None:
            return int(off.total_seconds() // 60)
    except Exception:                                         # noqa: BLE001
        pass
    return standard + (60 if observes and _us_dst(now_utc, standard) else 0)


def offset() -> int:
    """Minutes east of UTC for this request: the browser's word, else the
    organization's state, else UTC."""
    said = _OFFSET.get()
    if said is not None:
        return said
    try:
        from app import tenant
        fallback = offset_for_agency(tenant.current())
    except Exception:                                         # noqa: BLE001
        fallback = None
    return fallback if fallback is not None else 0


def now_local(now_utc: datetime | None = None) -> datetime:
    now_utc = now_utc or datetime.now(timezone.utc)
    return now_utc.astimezone(timezone(timedelta(minutes=offset())))


def today(now_utc: datetime | None = None) -> date:
    """Today's date where the person is."""
    return now_local(now_utc).date()


def today_str(now_utc: datetime | None = None) -> str:
    return today(now_utc).isoformat()


def _stored(iso: str) -> datetime | None:
    """A stored timestamp as the UTC moment it is. Stored without a zone it
    is still UTC — every timestamp this application writes is."""
    text = str(iso or "").strip()
    if len(text) < 16 or text[10:11] not in ("T", " "):
        return None
    try:
        when = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when if when.tzinfo else when.replace(tzinfo=timezone.utc)


def local_date(iso: str) -> str:
    """The date a stored timestamp falls on where the person is. A bare date
    is a calendar date and comes back as written."""
    when = _stored(iso)
    if when is None:
        return str(iso or "")[:10]
    return now_local(when).date().isoformat()


def local_stamp(iso: str) -> str:
    """When something was recorded, in the person's own time:
    "2026-09-24 9:38 PM", never "2026-09-25 01:38 UTC"."""
    when = _stored(iso)
    if when is None:
        return str(iso or "")[:10]
    local = now_local(when)
    hour = local.hour % 12 or 12
    return (f"{local.date().isoformat()} {hour}:{local.minute:02d} "
            f"{'AM' if local.hour < 12 else 'PM'}")
