"""Today, where the person is — app/clock.py.

Stored timestamps stay in UTC. What changed is the date the application
stamps and offers: it used the UTC date, so in the United States after about
eight in the evening Eastern, "today" was already tomorrow.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app import clock, tenant

EVENING_EASTERN = datetime(2026, 9, 25, 1, 30, tzinfo=timezone.utc)  # 9:30 PM EDT on the 24th


@pytest.fixture(autouse=True)
def fresh():
    token = clock.set_offset(None)
    held = tenant.set_current("")
    yield
    tenant.reset(held)
    clock.reset(token)


def test_the_browsers_offset_decides_today() -> None:
    clock.set_offset("-240")                       # New York, in summer
    assert clock.today_str(EVENING_EASTERN) == "2026-09-24"
    clock.set_offset("0")
    assert clock.today_str(EVENING_EASTERN) == "2026-09-25"


@pytest.mark.parametrize("bad", ["", "abc", "9999", "-99999", None])
def test_a_nonsense_offset_is_ignored(bad) -> None:
    clock.set_offset(bad)
    assert clock.offset() == 0                     # no organization either: UTC


def test_with_no_browser_the_organizations_state_stands_in() -> None:
    """The public report page works without JavaScript."""
    tenant.set_current("sc.des")
    assert clock.today_str(EVENING_EASTERN) == "2026-09-24"


@pytest.mark.parametrize("agency, summer, winter", [
    ("sc.des", -240, -300), ("tx.tceq", -300, -360), ("co.cdphe", -360, -420),
    ("az.adeq", -420, -420), ("ca.calepa", -420, -480), ("hi.doh", -600, -600),
    ("fed.epa", -240, -300),
])
def test_each_state_has_its_own_time(agency, summer, winter) -> None:
    july = datetime(2026, 7, 1, 12, tzinfo=timezone.utc)
    january = datetime(2026, 1, 15, 12, tzinfo=timezone.utc)
    assert clock.offset_for_agency(agency, july) == summer
    assert clock.offset_for_agency(agency, january) == winter


def test_an_unknown_code_gets_no_guess() -> None:
    assert clock.offset_for_agency("gaius.harness") is None


def test_the_daylight_saving_rule_without_a_zone_database() -> None:
    """Second Sunday of March at 2 a.m. to first Sunday of November at 2 a.m.,
    local — the same answer on a machine with no zone data."""
    est = -300
    assert not clock._us_dst(datetime(2026, 3, 8, 6, 59, tzinfo=timezone.utc), est)
    assert clock._us_dst(datetime(2026, 3, 8, 7, 0, tzinfo=timezone.utc), est)
    assert clock._us_dst(datetime(2026, 11, 1, 5, 59, tzinfo=timezone.utc), est)
    assert not clock._us_dst(datetime(2026, 11, 1, 6, 0, tzinfo=timezone.utc), est)


def test_a_stored_time_is_shown_in_the_persons_own_time() -> None:
    clock.set_offset("-240")
    assert clock.local_stamp("2026-09-25T01:38:00+00:00") == "2026-09-24 9:38 PM"
    assert clock.local_stamp("2026-09-25T13:05:09") == "2026-09-25 9:05 AM"
    assert clock.local_date("2026-09-25T01:38:00+00:00") == "2026-09-24"


def test_a_bare_date_is_a_calendar_date_and_never_moves() -> None:
    clock.set_offset("-600")
    assert clock.local_date("2026-09-25") == "2026-09-25"
    assert clock.local_stamp("2026-09-25") == "2026-09-25"


def test_the_modules_that_stamp_today_ask_the_clock(monkeypatch) -> None:
    from app import checks, goals, procedures
    monkeypatch.setattr(clock, "today_str", lambda now_utc=None: "2026-09-24")
    assert checks._today() == procedures._today() == goals._today() == "2026-09-24"
