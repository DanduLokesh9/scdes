"""The beta notice shown after signing in.

The client asked for one and left the wording open. These tests hold it to
the same rules as the rest of the product's language, and pin the two
behaviors that matter: an acknowledgment is recorded, and it is recorded
against the words that were actually shown.
"""

from __future__ import annotations

from app import beta, server, spine
from app.authz import Actor, Role

BRETT = Actor("sean.ot", "Brett Butz", Role.OT, title="Principal",
              email="brett@iiac.ai")


class _Recorder:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    def append(self, **entry) -> None:
        self.entries.append(entry)


def _all_words() -> str:
    n = beta.notice()
    return " ".join([n["title"], n["lead"], n["data"], n["button"],
                     n["recorded"]] + [p["head"] + " " + p["body"]
                                       for p in n["points"]])


def test_it_says_it_is_a_beta_and_may_be_wrong() -> None:
    words = _all_words().lower()
    assert "beta" in words
    assert "errors" in words


def test_it_warns_about_the_polished_version() -> None:
    """The same caution the download gives, where it is read first."""
    assert "Polished" in _all_words()
    assert "AI writing tool" in _all_words()


def test_it_says_it_is_not_legal_advice() -> None:
    assert "not legal advice" in _all_words()


def test_it_says_how_to_report_a_problem_with_the_real_control() -> None:
    """A first draft named "Report a bug", which is not on the screen any
    more. The control is "Report an issue", behind the ? button."""
    words = _all_words()
    assert "Report an issue" in words
    assert "Report a bug" not in words


def test_no_banned_word_reaches_the_notice() -> None:
    words = _all_words().lower()
    for banned in spine.BANNED_IN_COPY:
        assert banned not in spine.banned_in(words), banned


def test_it_names_no_other_organization() -> None:
    words = _all_words()
    for name in ("SCDES", "South Carolina", "New Mexico", "Texas"):
        assert name not in words


def test_an_acknowledgement_is_recorded_with_who_and_which_version(
        monkeypatch) -> None:
    log = _Recorder()
    from app import authz
    monkeypatch.setattr(authz, "default_log", lambda: log)
    got = beta.acknowledge(BRETT, beta.VERSION)
    assert got == {"ok": True, "recorded": True}
    entry = log.entries[-1]
    assert entry["action"] == "acknowledge_beta_notice"
    assert entry["detail"]["version"] == beta.VERSION
    assert entry["detail"]["actor_name"] == "Brett Butz"
    assert entry["detail"]["actor_email"] == "brett@iiac.ai"


def test_an_old_version_is_not_recorded_as_read(monkeypatch) -> None:
    """An acknowledgment on the record always refers to words that were
    shown."""
    log = _Recorder()
    from app import authz
    monkeypatch.setattr(authz, "default_log", lambda: log)
    got = beta.acknowledge(BRETT, "2020-01-01")
    assert got["ok"] is False
    assert log.entries == []


def test_a_failed_log_write_does_not_stop_anybody(monkeypatch) -> None:
    from app import authz

    class _Broken:
        def append(self, **_):
            raise OSError("disk full")

    monkeypatch.setattr(authz, "default_log", lambda: _Broken())
    got = beta.acknowledge(BRETT, beta.VERSION)
    assert got["ok"] is True and got["recorded"] is False


def test_the_routes_are_registered() -> None:
    assert server.ROUTES[("GET", "/api/beta")] is server.api_beta
    assert server.ROUTES[("POST", "/api/beta/acknowledge")] is \
        server.api_beta_acknowledge
