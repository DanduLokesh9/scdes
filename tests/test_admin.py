"""Who may read other people's bug reports.

This exists because of a specific hole. The queue keyed off `actor.is_ot`, and
every signed-in user is offered "Office of Technology" in the header dropdown —
so one click showed anybody every report filed from every agency. That is the
client's hardest standing rule broken in one line:

    "THE ENTIRE MODULAR PROCESS IS NOT TO EVER REFERENCE OR HAVE ACCESS TO
     OTHER AGENCIES."

The fix separates two things the code had merged. Capacity says what you may do
to *your own* agency's record and is self-selected on purpose. Admin says you
run GAIUS, is three named addresses, and is proved by a session token rather
than asserted in a query string.

Most of what is asserted below is therefore refusal — that picking a grander
capacity, or typing somebody else's address, gets you nothing.
"""

from __future__ import annotations

import pytest

from app import admin, tenancy
from app.authz import Actor, Role

BRETT = "brett@iiac.ai"
STRANGER = "jane.smith@des.sc.gov"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.delenv(admin.ENV_KEY, raising=False)
    yield


# --------------------------------------------------------------- the list

def test_the_three_named_accounts_are_admins() -> None:
    for address in ("brett@iiac.ai", "lokesh@iiac.ai", "dev@iiac.ai"):
        assert admin.is_admin(address)


def test_nobody_else_is() -> None:
    assert not admin.is_admin(STRANGER)
    assert not admin.is_admin("")
    assert not admin.is_admin(None)


def test_the_address_is_matched_regardless_of_case_or_spacing() -> None:
    assert admin.is_admin("  Brett@IIAC.ai  ")


def test_a_lookalike_address_is_not_an_admin() -> None:
    """Substring matching here would make brett@iiac.ai.attacker.com an admin."""
    assert not admin.is_admin("brett@iiac.ai.example.com")
    assert not admin.is_admin("notbrett@iiac.ai")
    assert not admin.is_admin("brett@iiac.a")


def test_the_list_can_be_changed_without_a_code_change(monkeypatch) -> None:
    monkeypatch.setenv(admin.ENV_KEY, "someone@iiac.ai, other@iiac.ai")
    assert admin.is_admin("someone@iiac.ai")
    assert not admin.is_admin(BRETT), "the override replaces, it does not extend"


# ------------------------------------------------------------- the session

def test_a_token_proves_the_address_it_was_issued_for() -> None:
    token = tenancy.issue_session(BRETT)
    assert token
    assert tenancy.session_email(token) == BRETT


def test_an_invented_token_proves_nothing() -> None:
    tenancy.issue_session(BRETT)
    assert tenancy.session_email("not-a-real-token") == ""
    assert tenancy.session_email("") == ""


def test_the_token_itself_is_not_stored() -> None:
    """The file holds hashes, so reading it does not hand over working keys."""
    token = tenancy.issue_session(BRETT)
    assert token not in tenancy.STORE.read_text(encoding="utf-8")


def test_an_expired_token_proves_nothing(monkeypatch) -> None:
    from datetime import timedelta
    token = tenancy.issue_session(BRETT)
    real_now = tenancy._now
    monkeypatch.setattr(
        tenancy, "_now",
        lambda: real_now() + timedelta(days=tenancy.SESSION_DAYS + 1))
    assert tenancy.session_email(token) == ""


def test_signing_out_retires_the_token() -> None:
    token = tenancy.issue_session(BRETT)
    tenancy.end_session(token)
    assert tenancy.session_email(token) == ""


def test_ending_a_token_that_does_not_exist_is_harmless() -> None:
    tenancy.end_session("nonsense")
    tenancy.end_session("")


# ------------------------------------------------- capacity is not identity

def test_choosing_the_ot_capacity_does_not_make_you_an_admin() -> None:
    """The hole this module was written to close.

    An operator who picks "Office of Technology" from the header dropdown is
    genuinely acting as OT over their own agency. It buys them nothing here.
    """
    ot_but_unproven = Actor("sean.ot", "Office of Technology", Role.OT)
    assert not admin.is_admin(ot_but_unproven.email)

    ot_and_a_stranger = Actor("sean.ot", "Office of Technology", Role.OT,
                              email=STRANGER)
    assert not admin.is_admin(ot_and_a_stranger.email)


def test_an_admin_is_an_admin_in_the_humblest_capacity() -> None:
    """Admin is not seniority. The client's rule is not to gate on title."""
    operator = Actor("liz.operator", "Operator", Role.OPERATOR, email=BRETT)
    assert admin.is_admin(operator.email)


def test_a_typed_address_is_not_a_proved_one() -> None:
    """`?email=` is whatever the browser sent. Only the token resolves."""
    assert tenancy.session_email(BRETT) == "", \
        "an address is not a token, and must not be accepted as one"
