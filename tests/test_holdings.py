"""The data warehouse module, and the monitor that watches it.

The client: "Data warehouse module is the foundation on which all deployments
rest, so that must be robust, reliable and helpful." Foundations get tested
for what they refuse as much as for what they do — most of this file is about
the monitor declining to knock on doors it has no business knocking on.
"""

from __future__ import annotations

import pytest

from app import holdings, monitor, tenant, versions
from app.authz import Actor, Role

WHO = Actor("sean.ot", "Dana Reed", Role.OT, title="Chief of Staff")


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    monkeypatch.setattr(holdings, "HOLDINGS_FILE",
                        tmp_path / "corpus" / "config" / "holdings.json")
    monkeypatch.setattr(monitor, "MONITOR_FILE",
                        tmp_path / "corpus" / "config" / "checks.json")
    monkeypatch.setattr(versions, "VERSIONS_FILE",
                        tmp_path / "corpus" / "config" / "versions.json")
    yield


def as_agency(code: str):
    class Bound:
        def __enter__(self):
            self.token = tenant.set_current(code)
            return self
        def __exit__(self, *_):
            tenant.reset(self.token)
    return Bound()


PERMITS = {
    "name": "Permit system",
    "contains": "Every permit application, decision and inspection since 2009",
    "purpose": "Issuing and tracking environmental permits",
    "format": "structured", "location": "gov_cloud",
    "system": "PermitPro", "owner": "The Permitting Manager",
    "reachable": "api", "endpoint": "https://example.com/permits/v1",
    "auth": "An API key issued by IT", "freshness": "live",
    "sensitive": ["regulated"],
}


# ------------------------------------------------------------- the register

def test_a_holding_can_be_written_down_and_read_back() -> None:
    with as_agency("iia.test"):
        out = holdings.save(PERMITS, WHO)
        assert out["ok"], out
        rows = holdings.listing()["holdings"]
        assert len(rows) == 1
        assert rows[0]["name"] == "Permit system"
        assert rows[0]["format_label"].startswith("Structured records")
        assert rows[0]["id"].startswith("DH-")


def test_a_holding_needs_a_name_and_nothing_else() -> None:
    """A register that refuses a row until every field is filled is a register
    nobody finishes. The name is the one thing that has to be there, because
    without it there is nothing to come back to."""
    with as_agency("iia.test"):
        assert not holdings.save({"contains": "things"}, WHO)["ok"]
        assert holdings.save({"name": "The K drive"}, WHO)["ok"]
        only = holdings.listing()["holdings"][0]
        # Unanswered stays unanswered — "We are not sure" is an answer, and
        # the one that makes a gap record. The unknown-location counter
        # counts both.
        assert only["location"] == ""
        assert only["reachable"] == ""
        assert holdings.summary()["unknown_location"] == 1


def test_editing_keeps_the_same_entry() -> None:
    with as_agency("iia.test"):
        first = holdings.save(PERMITS, WHO)["holding"]
        again = holdings.save({**PERMITS, "id": first["id"],
                               "owner": "The Deputy Director"}, WHO)
        assert again["ok"]
        rows = holdings.listing()["holdings"]
        assert len(rows) == 1, "a second entry was created"
        assert rows[0]["owner"] == "The Deputy Director"
        assert rows[0]["added_at"] == first["added_at"], "added_at moved"


def test_one_agencys_register_is_invisible_to_another() -> None:
    with as_agency("iia.test"):
        holdings.save(PERMITS, WHO)
    with as_agency("sc.ed"):
        assert holdings.listing()["holdings"] == []
        holdings.save({"name": "Student information system"}, WHO)
    with as_agency("iia.test"):
        names = [h["name"] for h in holdings.listing()["holdings"]]
        assert names == ["Permit system"]


def test_the_summary_counts_what_matters() -> None:
    with as_agency("iia.test"):
        holdings.save(PERMITS, WHO)
        holdings.save({"name": "Paper inspection files", "location": "paper",
                       "reachable": "no", "freshness": "static"}, WHO)
        holdings.save({"name": "Somebody's spreadsheet"}, WHO)
        found = holdings.listing()["summary"]
        assert found["total"] == 3
        assert found["with_an_interface"] == 1
        assert found["unreachable"] == 1
        assert found["unowned"] == 2
        assert found["unknown_location"] == 1
        assert found["holding_sensitive"] == 1


# ------------------------------------ where the register meets the framework

def test_it_flags_a_sensitive_holding_left_open() -> None:
    """The reason the register is worth keeping. Their own answer at 7.1 said
    this must never reach a general-purpose tool; the register says it is on
    an interface with no way of proving who is calling."""
    answers = {"data.never": ["regulated", "personal"]}
    with as_agency("iia.test"):
        holdings.save({**PERMITS, "auth": ""}, WHO)
        found = holdings.concerns(answers)
        assert any("no way of proving who is calling" in c["says"]
                   for c in found), found
        assert any("7.1" in c["against"] for c in found)


def test_an_authenticated_holding_is_flagged_more_gently() -> None:
    answers = {"data.never": ["regulated"]}
    with as_agency("iia.test"):
        holdings.save(PERMITS, WHO)              # has an API key recorded
        found = [c for c in holdings.concerns(answers) if "7.1" in c["against"]]
        assert found
        assert not any("no way of proving" in c["says"] for c in found)


def test_nothing_is_flagged_that_they_did_not_decide() -> None:
    """The categories come from their own answer. A tool that decided which
    holdings were sensitive would be making a legal judgment it is not
    qualified to make."""
    with as_agency("iia.test"):
        holdings.save({**PERMITS, "auth": ""}, WHO)
        found = holdings.concerns({})            # 7.1 unanswered
        assert not any("7.1" in c["against"] for c in found)


def test_the_categories_come_from_their_own_question() -> None:
    """The form's tick boxes are 7.1's options, not a second list. A separate
    vocabulary for the same idea is a thing that drifts, and the direction it
    drifts in is a holding marked sensitive against a category the framework
    has never heard of."""
    with as_agency("iia.test"):
        offered = holdings.categories({"data.never": ["personal"]})
        values = [c["value"] for c in offered]
        assert "personal" in values and "student" in values
        assert "unknown" not in values, "the not-sure option is not a category"
        chosen = [c for c in offered if c["banned"]]
        assert [c["value"] for c in chosen] == ["personal"]


def test_every_category_is_offered_not_only_the_banned_ones() -> None:
    """Marking that a holding contains personnel files is a fact about the
    holding. Whether that is a problem is the framework's judgment, made
    afterward — so the form cannot only offer the ones they banned."""
    with as_agency("iia.test"):
        offered = holdings.categories({"data.never": []})
        assert len(offered) > 5
        assert not any(c["banned"] for c in offered)


def test_a_category_they_wrote_themselves_survives() -> None:
    """7.1 lets them add their own. If the form only offered the eleven we
    thought of, editing a holding would silently drop theirs on the next
    save."""
    with as_agency("iia.test"):
        answers = {"data.never": ["custom:Well log data"]}
        offered = holdings.categories(answers)
        theirs = [c for c in offered if c["value"] == "custom:Well log data"]
        assert theirs, [c["value"] for c in offered]
        assert theirs[0]["label"] == "Well log data"
        assert theirs[0]["banned"]

        holdings.save({**PERMITS, "auth": "",
                       "sensitive": ["custom:Well log data"]}, WHO)
        found = holdings.concerns(answers)
        assert any("well log data" in c["says"] for c in found), found


def test_a_category_recorded_before_7_1_changed_stays_visible() -> None:
    """They un-tick something at 7.1 after a holding was marked with it. The
    mark is still on the record and has to stay editable — a form that quietly
    drops it loses the entry without telling anybody."""
    with as_agency("iia.test"):
        holdings.save({**PERMITS, "sensitive": ["custom:Well log data"]}, WHO)
        offered = holdings.categories({"data.never": ["personal"]})
        stale = [c for c in offered if c["value"] == "custom:Well log data"]
        assert stale, "a recorded category vanished from the form"
        assert not stale[0]["banned"], "it is no longer one they named"


def test_unticking_the_last_category_clears_it() -> None:
    """An empty list means "none of them", not "leave what was there". The
    register has to be able to say a holding turned out to be fine."""
    with as_agency("iia.test"):
        first = holdings.save(PERMITS, WHO)["holding"]
        assert first["sensitive"] == ["regulated"]
        again = holdings.save({**PERMITS, "id": first["id"],
                               "sensitive": []}, WHO)
        assert again["holding"]["sensitive"] == []


def test_an_unowned_holding_is_a_finding() -> None:
    """Floor 7 — somebody's name is on it."""
    with as_agency("iia.test"):
        holdings.save({"name": "The K drive"}, WHO)
        found = holdings.concerns({})
        assert any("nobody named against it" in c["says"] for c in found)


# ------------------------------------------------------------- the monitor

@pytest.mark.parametrize("url", [
    "http://169.254.169.254/latest/meta-data/",   # cloud credentials
    "http://127.0.0.1:8765/api/state",            # this very application
    "http://10.0.0.5/permits",
    "http://192.168.1.1/",
    "http://[::1]/",
    "file:///etc/passwd",
    "gopher://example.com/",
    "ftp://example.com/",
])
def test_the_monitor_refuses_to_knock_where_it_should_not(url) -> None:
    """A monitor that fetches whatever URL a tenant types is a port scanner
    with a web interface, pointed at whatever network this server sits in. On
    a cloud host the first thing it reaches hands out credentials."""
    allowed, why = monitor.permitted(url)
    assert not allowed, url
    assert why, "refused without saying why"


def test_a_public_address_is_allowed() -> None:
    allowed, why = monitor.permitted("https://example.com/api")
    assert allowed, why


def test_a_refusal_is_recorded_rather_than_hidden() -> None:
    """An entry that cannot be watched should say so on its face, not show a
    green tick that means nothing."""
    result = monitor.probe("http://127.0.0.1:9/nothing")
    assert result["state"] == monitor.REFUSED
    assert "private" in result["why"]


def test_a_probe_never_carries_a_credential() -> None:
    """The moment this holds a key it becomes the most valuable thing on the
    box. Asserted against the source, because the promise is about what the
    code cannot do rather than what one call happened not to send."""
    import inspect
    source = inspect.getsource(monitor)
    for leak in ("Authorization", "api_key", "password", "secret",
                 "Bearer "):
        assert leak not in source, leak


def test_results_are_kept_and_bounded() -> None:
    with as_agency("iia.test"):
        for i in range(monitor.KEEP + 12):
            monitor.record("DH-TEST", {"state": monitor.UP, "at": f"t{i}",
                                       "ms": 10, "status": 200, "why": ""})
        entry = monitor.state_of("DH-TEST")
        assert len(entry["history"]) == monitor.KEEP
        assert entry["state"] == monitor.UP


def test_a_change_of_state_is_noticed() -> None:
    """A hundred consecutive "down" results are one outage, not a hundred."""
    with as_agency("iia.test"):
        monitor.record("DH-TEST", {"state": monitor.UP, "at": "t1", "ms": 5,
                                   "status": 200, "why": ""})
        entry = monitor.record("DH-TEST", {"state": monitor.DOWN, "at": "t2",
                                           "ms": 0, "status": 0,
                                           "why": "timeout"})
        assert entry["changed_at"] == "t2"
        assert entry["was"] == monitor.UP

        same = monitor.record("DH-TEST", {"state": monitor.DOWN, "at": "t3",
                                          "ms": 0, "status": 0,
                                          "why": "timeout"})
        assert same["changed_at"] == "t2", "an unchanged state moved the mark"


def test_a_sweep_only_touches_holdings_with_somewhere_to_check() -> None:
    with as_agency("iia.test"):
        holdings.save({"name": "Paper files", "reachable": "no"}, WHO)
        holdings.save({"name": "A system with no address recorded",
                       "reachable": "api"}, WHO)
        assert monitor.sweep()["checked"] == 0


def test_the_monitor_counts_only_what_is_still_on_the_register() -> None:
    """A removed holding left its results behind, so the panel reported ten
    endpoints watched on an organization with one recorded — a number that
    traced to nothing visible on the screen under it."""
    with as_agency("iia.test"):
        kept = holdings.save(PERMITS, WHO)["holding"]
        monitor.record(kept["id"], {"state": monitor.UP, "at": "t", "ms": 1,
                                    "status": 200, "why": ""})
        gone = holdings.save({**PERMITS, "name": "An old system",
                              "endpoint": "https://example.com/old"},
                             WHO)["holding"]
        monitor.record(gone["id"], {"state": monitor.DOWN, "at": "t", "ms": 0,
                                    "status": 0, "why": "timeout"})
        assert monitor.summary()["watched"] == 2

        holdings.forget(gone["id"], WHO)
        found = monitor.summary()
        assert found["watched"] == 1, found
        assert found["down"] == 0
        assert gone["id"] not in found["checks"]


def test_a_holding_with_no_endpoint_is_not_counted_as_watched() -> None:
    with as_agency("iia.test"):
        holdings.save({"name": "Paper files", "reachable": "no"}, WHO)
        assert monitor.summary()["watched"] == 0


def test_one_agencys_results_stay_in_its_own_container() -> None:
    # Recorded against a holding that exists, because the summary counts
    # against the register rather than against whatever the results file has
    # accumulated.
    with as_agency("iia.test"):
        mine = holdings.save(PERMITS, WHO)["holding"]
        monitor.record(mine["id"], {"state": monitor.UP, "at": "t", "ms": 1,
                                    "status": 200, "why": ""})
    with as_agency("sc.ed"):
        assert monitor.summary()["watched"] == 0
    with as_agency("iia.test"):
        assert monitor.summary()["watched"] == 1


def test_the_probes_own_request_can_actually_be_built() -> None:
    """HTTP headers are latin-1. The user-agent string here contained an
    em-dash, so every probe failed with "'latin-1' codec can't encode
    character" — and reported it as the endpoint being down.

    A monitor whose own request cannot be built is worse than none, because
    the outages it reports are its own. Found by running it, not by reading
    it.
    """
    monitor.AGENT.encode("latin-1")


def test_a_real_probe_reaches_a_real_server(tmp_path) -> None:
    """End to end against a socket this test owns, because every layer below
    HTTP is where the surprises live."""
    import http.server
    import threading

    class Quiet(http.server.BaseHTTPRequestHandler):
        def do_HEAD(self):                                # noqa: N802
            self.send_response(200)
            self.end_headers()
        def log_message(self, *args):                     # noqa: D102
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Quiet)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    try:
        # Loopback is refused by design, which is itself the assertion.
        result = monitor.probe(f"http://127.0.0.1:{port}/health")
        assert result["state"] == monitor.REFUSED
        assert "private" in result["why"]
    finally:
        server.shutdown()
