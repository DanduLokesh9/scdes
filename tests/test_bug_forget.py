"""Removing a ticket that should never have been one.

The queue had no delete. That sounds like discipline and was not: the
notification check files a genuine report every run, and a dozen of them
accumulated twice next to reports from real people, clearable only with a shell
on the server — which is no use against a deployment nobody has a shell on.

`wont_fix` is the answer for a report the team disagrees with. This is the
answer for a duplicate, an empty message, or a harness's own row.
"""

from __future__ import annotations

import json

import pytest

from app import bugs
from app.authz import Actor, Role

OT = Actor("sean.ot", "Office of Technology", Role.OT, title="CTO")

CONTEXT = {"view": "Registry", "url": "/", "browser": "Chrome/140",
           "screen": "1920x1080", "version": "test"}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(bugs, "STORE", tmp_path / "bugs.jsonl")
    yield


def _file(**over):
    args = dict(expected="It to work", happened="It did not.", context=CONTEXT,
                events=[], reporter="jane.smith@des.sc.gov", name="Jane Smith",
                agency="SCDES")
    args.update(over)
    return bugs.report(**args)


def test_a_ticket_can_be_removed() -> None:
    junk = _file(happened="hi")["id"]
    keep = _file(happened="The gate review would not save.")["id"]

    out = bugs.forget(junk)
    assert out["ok"]
    assert out["id"] == junk

    left = [t["id"] for t in bugs.listing(status="", query="")["tickets"]]
    assert junk not in left
    assert keep in left, "it took the wrong one"


def test_every_row_for_that_ticket_goes() -> None:
    """The store is append-only, so one ticket is several lines — a report, a
    reply, a reopen. Leaving any of them would resurrect it on the next read."""
    bug = _file()["id"]
    # Fixed, not open — reopening something already being worked on is refused,
    # so an OPEN status here writes two rows rather than three and the count
    # says nothing.
    bugs.respond(bug, message="Fixed.", status=bugs.FIXED, actor=OT)
    assert bugs.reopen(bug, message="Still broken.",
                       email="jane.smith@des.sc.gov")["ok"]

    out = bugs.forget(bug)
    assert out["rows_removed"] >= 3, out
    assert bugs.ticket(bug) is None


def test_the_previous_contents_are_kept() -> None:
    """Reversible for as long as anybody notices."""
    bug = _file()["id"]
    bugs.forget(bug)
    backup = bugs.STORE.with_suffix(".jsonl.bak")
    assert backup.is_file()
    assert bug in backup.read_text(encoding="utf-8")


def test_removing_something_that_is_not_there_says_so() -> None:
    _file()
    out = bugs.forget("BUG-NOTREAL")
    assert not out["ok"]
    assert "not there" in out["error"]


def test_it_needs_an_id() -> None:
    assert not bugs.forget("")["ok"]
    assert not bugs.forget("   ")["ok"]


def test_an_unreadable_line_is_not_collateral() -> None:
    """A corrupt row is not an unwanted row. Dropping it because it could not be
    parsed would quietly lose whatever else it held."""
    keep = _file()["id"]
    with bugs.STORE.open("a", encoding="utf-8") as fh:
        fh.write("{not json at all\n")
    junk = _file(happened="hi")["id"]

    assert bugs.forget(junk)["ok"]
    assert "{not json at all" in bugs.STORE.read_text(encoding="utf-8")
    assert keep in [t["id"] for t in bugs.listing(status="", query="")["tickets"]]


def test_the_id_is_matched_regardless_of_case() -> None:
    bug = _file()["id"]
    assert bugs.forget(bug.lower())["ok"]


def test_the_rest_of_the_queue_still_reads_back() -> None:
    """The rewrite is the risky part — a malformed file would take everything."""
    ids = [_file(happened=f"fault {i}")["id"] for i in range(4)]
    bugs.forget(ids[1])
    left = [t["id"] for t in bugs.listing(status="", query="")["tickets"]]
    assert sorted(left) == sorted([ids[0], ids[2], ids[3]])
    for line in bugs.STORE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            json.loads(line)          # raises if the rewrite corrupted a row
