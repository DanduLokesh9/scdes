"""The quiet console must not crash on the server's own error lines.

http.server's send_error logs "code %d, message %s" with an HTTPStatus as the
first argument, not the request line. The filter that hides /api/ lines did
`"/api/" in args[0]` and raised TypeError on staging (Oct 5 2026), turning a
malformed request into a traceback in the service log.
"""

from __future__ import annotations

from http import HTTPStatus

from app import server


class _Quiet(server.Handler):
    def __init__(self):                       # no socket: only log_message is used
        self.lines = []

    def address_string(self):
        return "127.0.0.1"

    def log_date_time_string(self):
        return "now"


def test_an_error_line_with_a_status_does_not_crash(capsys):
    h = _Quiet()
    h.log_message("code %d, message %s", HTTPStatus.BAD_REQUEST, "Bad request syntax")
    assert "Bad request syntax" in capsys.readouterr().err


def test_api_request_lines_are_still_hidden(capsys):
    h = _Quiet()
    h.log_message('"%s" %s %s', "GET /api/state HTTP/1.1", "200", "-")
    assert capsys.readouterr().err == ""
