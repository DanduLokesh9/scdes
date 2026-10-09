"""A change with no organization behind it is refused, not saved to nowhere.

Reported: on Sep 29 Rebecca Valencia answered 111 framework questions from a
browser that had lost its session. The server resolved those requests to no
organization (`tenant.ANONYMOUS`, "~unresolved") and saved every answer
there, while her own framework showed 7. Now such a change is refused with
"Your session ended — sign in again", and the screen says so.
"""

from __future__ import annotations

import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from app import server, tenant, tenancy


def test_a_write_with_no_organization_is_refused():
    held = tenant.set_current(tenant.ANONYMOUS)
    try:
        out = server._no_organization_gate("POST", "/api/versions/answer")
        assert out and out["session_ended"] and "sign in again" in out["error"]
        # Reading stays harmless, and getting in stays open.
        assert server._no_organization_gate("GET", "/api/framework") is None
        for door in ("/api/agency/register", "/api/agency/verify", "/api/terms/accept",
                     "/api/bugs/report", "/api/session/end", "/api/chat"):
            assert server._no_organization_gate("POST", door) is None, door
    finally:
        tenant.reset(held)


def test_a_write_with_an_organization_goes_ahead():
    held = tenant.set_current("sc.ed")
    try:
        assert server._no_organization_gate("POST", "/api/versions/answer") is None
    finally:
        tenant.reset(held)


@pytest.fixture
def served(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.setattr(tenant, "AGENCIES", tmp_path / "agencies")
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}", tmp_path
    httpd.shutdown()


def test_over_http_an_answer_from_a_lost_session_is_not_saved(served):
    base, tmp = served
    req = urllib.request.Request(
        base + "/api/versions/answer?email=nobody%40nowhere.gov", method="POST",
        data=json.dumps({"key": "org.size", "value": "u25"}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
        status, out = 200, {}
    except urllib.error.HTTPError as e:
        status, out = e.code, json.loads(e.read())
    assert status == 401 and out["session_ended"]
    assert not (tmp / "agencies" / tenant.ANONYMOUS).exists(), "nothing written to nowhere"
