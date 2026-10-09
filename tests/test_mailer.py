"""Sending the verification code.

The property that matters here is not "does the mail look nice" — it is that
**the code is never returned to the caller when it was actually sent**. If it
were, anyone who could reach the registration endpoint could read the code for
an address they do not control, and the verification step would prove nothing at
all while appearing to work.
"""

from __future__ import annotations

import pytest

from app import mailer, tenancy


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    for name in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                 "SMTP_FROM", "SMTP_FROM_NAME"):
        monkeypatch.delenv(name, raising=False)


def _register():
    return tenancy.start_registration(
        agency="sc.des", name="Jane Smith", title="Deputy Director",
        email="jane.smith@des.sc.gov", phone="8035550100", attested=True)


# ------------------------------------------------------------ configuration

def test_unconfigured_by_default() -> None:
    assert not mailer.configured()
    assert "not configured" in mailer.status()["note"].lower()


def test_a_host_and_sender_are_enough_to_count_as_configured(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    assert mailer.configured()
    assert "emailed" in mailer.status()["note"].lower()


def test_a_host_without_a_sender_is_not_configured(monkeypatch) -> None:
    """Half-configured must count as unconfigured, or sending fails silently."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    assert not mailer.configured()


# ------------------------------------------------------- the important rule

def test_the_code_is_shown_only_when_it_could_not_be_sent() -> None:
    result = _register()
    assert result["ok"]
    assert result["emailed"] is False
    assert result["code"], "with no mail path the code must be shown"
    # The substance, not the sentence: it has to admit the code was not
    # emailed and say what would make it send.
    note = result["delivery_note"].lower()
    assert "shown here" in note
    assert "smtp_host" in note, "it must say what is missing"


def test_the_code_is_never_returned_once_it_has_been_emailed(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": True, "to": a[0]})

    result = _register()
    assert result["ok"]
    assert result["emailed"] is True
    assert "code" not in result, (
        "returning the code after emailing it would defeat verification")
    assert "delivery_note" not in result


def test_the_registration_survives_a_send_failure(monkeypatch) -> None:
    """A mail outage must not lose the registration — the code is already stored.

    This used to assert that the code came back as well ("fall back to
    showing it rather than stranding them"). It no longer does on a
    deployment that sends mail: see
    `test_a_deployment_that_sends_mail_withholds_the_code_when_it_fails`.
    What this guards is the half that has not changed — the registration
    stands, and the person is told what happened rather than getting a stack
    trace and a half-created account.
    """
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": False,
                                         "reason": "SMTPConnectError: refused"})

    result = _register()
    assert result["ok"], "the registration must still stand"
    assert result["emailed"] is False
    assert result["delivery_note"], "they have to be told what happened"


def test_a_failure_reason_is_reported_rather_than_swallowed(monkeypatch) -> None:
    monkeypatch.setenv("SMTP_HOST", "nope.invalid")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    outcome = mailer.send_code("someone@des.sc.gov", "123456")
    assert outcome["sent"] is False
    assert outcome["reason"], "a silent failure looks like a mistyped address"


# --------------------------------------------------- what the screen is told

def test_a_configured_server_is_not_told_to_configure_itself(
        monkeypatch) -> None:
    """The fault the client found.

    Staging had all six SMTP variables set and, when a send failed, told its
    operator: "Configure SMTP_HOST and SMTP_FROM on the server to send it for
    real." Both were already set. The note was a fixed string that ignored
    the reason computed on the line above it, so the screen misdiagnosed
    every real provider rejection as missing configuration — and cost an
    investigation to work out that the configuration was fine.
    """
    monkeypatch.setenv("SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    note = mailer.note_for({"sent": False, "reason":
                            "SMTPSenderRefused: 554 Message rejected: "
                            "Email address is not verified."})
    assert "SMTP_HOST" not in note, note
    assert "verified addresses" in note, note


def test_an_unconfigured_server_is_told_what_to_set(monkeypatch) -> None:
    for name in ("SMTP_HOST", "SMTP_FROM"):
        monkeypatch.delenv(name, raising=False)
    note = mailer.note_for({"sent": False, "reason": "not configured"})
    assert "SMTP_HOST" in note


def test_the_provider_is_never_quoted_to_the_browser(monkeypatch) -> None:
    """The note appears on the sign-in screen, before anybody has proved who
    they are. Whatever the provider chose to say back does not belong
    there — it goes to the log instead."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    raw = ("SMTPAuthenticationError: 535 Authentication Credentials Invalid "
           "for user AKIAEXAMPLE")
    note = mailer.note_for({"sent": False, "reason": raw})
    assert "AKIAEXAMPLE" not in note
    assert "535" not in note
    assert "credentials" in note.lower()


@pytest.mark.parametrize("reason,expected", [
    ("SMTPSenderRefused: 554 Email address is not verified", "verified"),
    ("SMTPAuthenticationError: 535 bad credentials", "credentials"),
    ("TimeoutError: timed out", "did not answer"),
    ("SMTPRecipientsRefused: 550 5.1.1 no such user", "does not exist"),
    ("ValueError: something nobody predicted", "refused the message"),
])
def test_each_kind_of_failure_says_something_different(reason, expected):
    assert expected in mailer.explain(reason)


def test_a_sent_message_produces_no_note() -> None:
    assert mailer.note_for({"sent": True, "to": "a@b.gov"}) == ""


# ------------------------------------------- who may be shown a code at all

def test_a_deployment_that_sends_mail_withholds_the_code_when_it_fails(
        monkeypatch) -> None:
    """The fallback was firing on any failed send.

    On a live deployment that meant a mail outage turned verification into a
    formality: type any address belonging to a registered agency and the
    screen hands you its code. The framework this product writes requires a
    code to prove control of a mailbox; the application must not contradict
    that because its provider had a bad afternoon.
    """
    monkeypatch.setenv("SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.delenv("IIA_SHOW_CODES", raising=False)
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": False, "reason":
                                         "SMTPDataError: 554 not verified"})

    result = _register()
    assert result["ok"], "the registration still stands"
    assert result["emailed"] is False
    assert "code" not in result, "a live deployment must not hand over a code"
    assert result["mail_failed"] is True
    assert "could not send your code" in result["delivery_note"].lower()


def test_a_deployment_with_no_mail_at_all_still_shows_the_code(
        monkeypatch) -> None:
    """A laptop, a test container, a demo box. There is no mail path to fall
    back *from*, so withholding the code would make the product unusable and
    would stop every browser harness signing in."""
    for name in ("SMTP_HOST", "SMTP_FROM", "IIA_SHOW_CODES"):
        monkeypatch.delenv(name, raising=False)
    result = _register()
    assert result["code"], "with no mail path the code has to be shown"
    assert "mail_failed" not in result


def test_an_operator_can_turn_the_fallback_back_on(monkeypatch) -> None:
    """Staging sends mail and is still inside the SES sandbox, so it needs
    codes on screen. That is a deliberate choice by whoever runs the
    deployment, not something a failed send decides."""
    monkeypatch.setenv("SMTP_HOST", "email-smtp.us-east-1.amazonaws.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.setenv("IIA_SHOW_CODES", "1")
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": False, "reason": "554"})

    result = _register()
    assert result["code"], "the operator asked for the fallback"
    assert "mail_failed" not in result


def test_the_harness_container_is_the_one_exception(monkeypatch) -> None:
    """SES leaving its sandbox broke the automated checks, because mail
    started sending and the code was — correctly — withheld.

    The fix is not to loosen the rule. `gaius.harness` exists solely for the
    scripts, is never offered in the agency picker, holds nothing anybody
    would miss, and can already be registered by anyone; returning a code
    for an address inside it grants a scratch space and nothing else.
    """
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.delenv("IIA_SHOW_CODES", raising=False)

    # A real agency's address stays strict.
    assert mailer.may_show_code_to("jane.smith@des.sc.gov") is False
    assert mailer.may_show_code_to("") is False
    # And so does an address nobody has registered.
    assert mailer.may_show_code_to("stranger@example.gov") is False


def test_the_harness_address_gets_its_code_once_registered(
        monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.delenv("IIA_SHOW_CODES", raising=False)
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": True, "to": a[0]})

    out = tenancy.start_registration(
        agency="gaius.harness", name="Automated Walk", title="Harness",
        email="walk@harness.gaius.test", phone="8035550100", attested=True)
    assert out["ok"], out
    # Emailed, so no code — the same rule as everyone else while it works.
    assert "code" not in out

    # And with the real sender in play, nothing is sent to it at all — the
    # domain does not exist, so a message would be accepted and then bounce,
    # spending sending reputation on mail nobody wanted.
    monkeypatch.undo()
    # undo() also drops the fixture's store, which sent this test writing to
    # the real one — so re-isolate it before anything else.
    monkeypatch.setattr(tenancy, "STORE", tmp_path / "tenancy.json")
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.delenv("IIA_SHOW_CODES", raising=False)

    sent_to = []
    monkeypatch.setattr(mailer, "send",
                        lambda to, *a, **k: sent_to.append(to) or
                        {"sent": True, "to": to})

    again = tenancy.start_signin("walk@harness.gaius.test")
    assert again["ok"], again
    assert again.get("code"), "the checks would have no way in"
    assert sent_to == [], "a bounce was posted to a domain that does not exist"


def test_a_real_address_is_still_sent_to(monkeypatch) -> None:
    """The skip above must be the harness and nothing else."""
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    sent_to = []
    monkeypatch.setattr(mailer, "send",
                        lambda to, *a, **k: sent_to.append(to) or
                        {"sent": True, "to": to})
    out = mailer.send_code("jane.smith@des.sc.gov", "123456")
    assert out["sent"] is True
    assert sent_to == ["jane.smith@des.sc.gov"]


def test_signing_in_withholds_the_code_on_the_same_rule(monkeypatch) -> None:
    """Both paths, because the registration one was fixed first and the
    sign-in one is the one a returning user meets."""
    # Register and verify first, with no mail configured — that is the
    # fixture's default and it is how a member comes to exist at all.
    issued = _register()
    tenancy.verify_code("jane.smith@des.sc.gov", issued["code"])

    # Now the deployment sends mail, and the send fails.
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_FROM", "no-reply@governingai.us")
    monkeypatch.delenv("IIA_SHOW_CODES", raising=False)
    monkeypatch.setattr(mailer, "send_code",
                        lambda *a, **k: {"sent": False, "reason": "554"})

    out = tenancy.start_signin("jane.smith@des.sc.gov")
    assert out["ok"], out
    assert "code" not in out, "the sign-in path leaked what registration did not"
    assert out["mail_failed"] is True


# ---------------------------------------------------------------- the mail

def test_the_message_carries_the_code_and_the_provenance() -> None:
    text, html = mailer._body("482913", "SC Department of Environmental Services", 30)
    for body in (text, html):
        assert "482913" in body
        assert "30" in body, "say how long it lasts"
        assert "Innovative Infrastructure Advising" in body
    assert "ignore this message" in text.lower(), (
        "an unrequested code must tell the reader nothing was created")


def test_the_code_verifies_after_being_issued() -> None:
    result = _register()
    verified = tenancy.verify_code("jane.smith@des.sc.gov", result["code"])
    assert verified["ok"]
