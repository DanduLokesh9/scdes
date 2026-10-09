"""Reading a local .env, and the ways that could go wrong.

The server gets its secrets from systemd. A laptop does not, and the first
thing anybody does about that is paste a key into a script — so this reads a
file instead. Everything here is about the file not being able to surprise
somebody: it cannot override real configuration, it cannot set a placeholder
over the top of nothing, and it cannot put a value in a log.
"""

from __future__ import annotations

import os

from app import env


def test_it_sets_what_the_file_holds(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("SOME_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("SOME_KEY=abc123\n", encoding="utf-8")

    assert env.load(path) == ["SOME_KEY"]
    assert os.environ["SOME_KEY"] == "abc123"
    monkeypatch.delenv("SOME_KEY", raising=False)


def test_the_environment_wins(tmp_path, monkeypatch) -> None:
    """A stale file on a laptop must not override what systemd set, or what
    somebody exported deliberately in the shell they are working in."""
    monkeypatch.setenv("SOME_KEY", "from-the-shell")
    path = tmp_path / ".env"
    path.write_text("SOME_KEY=from-the-file\n", encoding="utf-8")

    assert env.load(path) == []
    assert os.environ["SOME_KEY"] == "from-the-shell"


def test_a_placeholder_is_not_a_key(tmp_path, monkeypatch) -> None:
    """The failure this prevents is worse than the one it causes.

    "PASTE_KEY_HERE" is a non-empty string, so every check downstream would
    report the writing tool as configured and then fail authentication on
    each clause of the document — which reads, to whoever is looking at it,
    as polishing being broken. Not configured is a state this application
    says out loud and handles properly.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("ANTHROPIC_API_KEY=PASTE_KEY_HERE\n", encoding="utf-8")

    assert env.load(path) == []
    assert "ANTHROPIC_API_KEY" not in os.environ

    from app import polish
    ok, why = polish.available()
    assert not ok
    assert "writing tool" in why


def test_comments_blanks_and_shell_habits(tmp_path, monkeypatch) -> None:
    """What people actually paste: a comment, an export, quotes around the
    value, a blank line, and a stray line with no equals sign."""
    for name in ("A_KEY", "B_KEY", "C_KEY"):
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / ".env"
    path.write_text(
        "# a comment\n"
        "\n"
        "A_KEY=plain\n"
        "export B_KEY=\"quoted\"\n"
        "  C_KEY = spaced \n"
        "not a variable at all\n",
        encoding="utf-8")

    took = env.load(path)
    assert sorted(took) == ["A_KEY", "B_KEY", "C_KEY"]
    assert os.environ["A_KEY"] == "plain"
    assert os.environ["B_KEY"] == "quoted"
    assert os.environ["C_KEY"] == "spaced"
    for name in ("A_KEY", "B_KEY", "C_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_a_missing_file_is_not_an_error(tmp_path) -> None:
    """The ordinary case on the server, where systemd has already done it."""
    assert env.load(tmp_path / "nothing-here") == []


def test_it_returns_names_and_never_values(tmp_path, monkeypatch) -> None:
    """The server prints what it picked up. That line goes to journalctl."""
    monkeypatch.delenv("SECRET_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text("SECRET_KEY=sk-ant-the-actual-secret\n", encoding="utf-8")

    took = env.load(path)
    assert took == ["SECRET_KEY"]
    assert "the-actual-secret" not in " ".join(took)
    monkeypatch.delenv("SECRET_KEY", raising=False)


def test_the_real_env_file_is_kept_out_of_the_deploy_bundle() -> None:
    """A secret has no business in a zip that lands in /tmp on a shared box.

    The bundle already excluded *.pem and the per-agency state files. This
    checks the exclusion list itself rather than trusting the comment above
    it, because the cost of being wrong is a key on a server in a world
    readable archive.
    """
    from pathlib import Path
    push = (Path(__file__).resolve().parent.parent
            / "deploy" / "push.ps1").read_text(encoding="utf-8")
    assert '".env"' in push
    # rsplit, not split: a comment above the command explains what the /XF
    # list is for, and matching that one checks the prose rather than the
    # argument that does the work.
    excludes = push.rsplit("/XF", 1)[1].split("| Out-Null", 1)[0]
    assert '".env"' in excludes
