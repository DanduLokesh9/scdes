"""Sending the verification code.

Standard library only — ``smtplib`` talks to any SMTP provider, so this works
with SendGrid, Mailgun, Amazon SES, Google Workspace or an agency's own relay
without adding a dependency or tying the build to one vendor.

Configuration is entirely environmental, because credentials must never sit in
the repository:

    SMTP_HOST      smtp.sendgrid.net
    SMTP_PORT      587            (587 = STARTTLS, 465 = implicit TLS)
    SMTP_USER      apikey
    SMTP_PASSWORD  ...
    SMTP_FROM      no-reply@governingai.us
    SMTP_FROM_NAME Governing AI            (optional)

**When SMTP is not configured, no mail is sent and the code is returned to the
caller instead**, so the platform can still be demonstrated end to end. That
path is clearly labeled everywhere it surfaces, because a verification step
that shows you the answer verifies nothing. ``configured()`` is what the rest of
the application asks before deciding which of the two it is doing — the
distinction is never inferred or assumed.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Any


def settings() -> dict[str, str]:
    return {
        "host": os.environ.get("SMTP_HOST", "").strip(),
        "port": os.environ.get("SMTP_PORT", "587").strip(),
        "user": os.environ.get("SMTP_USER", "").strip(),
        "password": os.environ.get("SMTP_PASSWORD", ""),
        "sender": os.environ.get("SMTP_FROM", "").strip(),
        "sender_name": os.environ.get("SMTP_FROM_NAME", "Governing AI").strip(),
    }


def configured() -> bool:
    """Whether real mail can be sent. A host and a from-address is the minimum."""
    s = settings()
    return bool(s["host"] and s["sender"])


def may_show_code() -> bool:
    """Whether this deployment may put a verification code on the screen.

    The fallback exists so a deployment with no mail path can still be walked
    end to end. It was firing on *any* failed send, which meant a mail outage
    on a live deployment turned verification into a formality: type any
    address belonging to a registered agency and the screen hands you its
    code. The framework this product writes requires that a code proves
    control of a mailbox, and the application should not contradict that the
    moment its mail provider has a bad afternoon.

    So the rule is about what kind of deployment this is, not about whether
    one send worked:

    * **No mail configured at all** — a laptop, a test container, a demo box.
      There is no mail path to fall back *from*, so showing the code is the
      only way the product can be used, and it is labeled as such
      everywhere it appears.
    * **Mail configured** — this deployment intends to send. A failure is an
      incident, not a mode. The code is withheld and the person is told we
      could not send it, unless the operator has deliberately set
      ``IIA_SHOW_CODES`` — which staging does, so codes stay visible while
      SES is still in its sandbox.
    """
    import os
    if not configured():
        return True
    return os.environ.get("IIA_SHOW_CODES", "").strip().lower() in (
        "1", "true", "yes")


def no_real_mailbox(email: str) -> bool:
    """Whether this address has no mailbox anybody can read.

    True only for the automated checks' own container. `harness.gaius.test`
    is not a real domain, so a code sent there reaches nothing — and once
    SES left its sandbox it started *accepting* those messages and bouncing
    them afterward, which spends sending reputation on mail nobody wanted.

    So the harness's codes are not sent at all. Better than sending them
    into a hole: no bounce, and the scripts can still read the code out of
    the response, which is how they have always signed in.
    """
    address = (email or "").strip().lower()
    if not address:
        return False
    try:
        from app import tenancy
        access = tenancy.access_for(address)
        return tenancy.is_harness_container(access.get("state") or "")
    except Exception:                                     # noqa: BLE001
        return False


def may_show_code_to(email: str) -> bool:
    """As `may_show_code`, plus the one narrow exception.

    The automated checks sign in the way a person does — ask for a code, read
    it from the response, verify — because a locally minted token is one the
    server never issued, and testing with one produced five false passes
    before anybody noticed the harness was testing itself.

    That worked while mail could not be delivered. It stopped the moment SES
    left its sandbox: mail now sends, so the code is correctly withheld, and
    the checks lost their way in. The fix is not to loosen the rule — it is
    to name the one container the rule does not need to protect.

    `gaius.harness` exists solely for the scripts. It is never offered in the
    agency picker, it holds nothing anybody would miss, and anybody who wants
    it can register it already. Returning a code for an address inside it
    grants access to a scratch space and nothing else. Every real tenant
    stays strict.
    """
    return may_show_code() or no_real_mailbox(email)


def _body(code: str, agency: str, minutes: int) -> tuple[str, str]:
    """Plain text and HTML. Both, because a code-only mail that renders as an
    empty message in a text client is a support ticket."""
    text = (
        f"Your verification code is {code}\n\n"
        f"Enter this to confirm your email address and continue registering "
        f"{agency or 'your agency'} on Governing AI.\n\n"
        f"The code expires in {minutes} minutes. If you did not request it, "
        f"you can ignore this message — nothing has been created.\n\n"
        f"Delivered by IIA. Innovative Infrastructure Advising, LLC · iiac.ai · "
        f"Charleston, SC\n"
    )
    html = f"""\
<html><body style="font:15px/1.6 -apple-system,Segoe UI,system-ui,sans-serif;
 color:#16242c;margin:0;padding:24px">
  <p style="margin:0 0 18px">Your verification code is</p>
  <p style="font:700 34px/1 Consolas,monospace;letter-spacing:8px;
     margin:0 0 20px;color:#0d3b2e">{code}</p>
  <p style="margin:0 0 14px">Enter this to confirm your email address and
     continue registering <b>{agency or "your agency"}</b> on Governing AI.</p>
  <p style="margin:0 0 14px;color:#5b6e74">The code expires in {minutes}
     minutes. If you did not request it you can ignore this message — nothing
     has been created.</p>
  <hr style="border:0;border-top:1px solid #cfd9dc;margin:22px 0 12px">
  <p style="margin:0;font-size:12px;color:#5b6e74">
    Delivered by IIA. Innovative Infrastructure Advising, LLC ·
    <a href="https://iiac.ai" style="color:#1c7a43">iiac.ai</a> · Charleston, SC
  </p>
</body></html>"""
    return text, html


def send(to: str, subject: str, text: str,
         html: str | None = None,
         attachments: list[tuple[str, bytes, str]] | None = None) -> dict[str, Any]:
    """Send one message. Returns what happened, and never raises at the caller.

    The generic path. `send_code` was the only sender for a while and grew the
    SMTP handling inside it; the NDA decline notice needs the same transport
    with different words, and two copies of a TLS-and-login block is one copy
    too many.
    """
    if not configured():
        return {"sent": False,
                "reason": "SMTP is not configured on this server"}

    s = settings()
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = f'{s["sender_name"]} <{s["sender"]}>'
    message["To"] = to
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    # (filename, content, "type/subtype") — e.g. the framework answers PDF the
    # technical report carries for an organization past 70%.
    for name, content, mime in attachments or []:
        main, _, sub = (mime or "application/octet-stream").partition("/")
        message.add_attachment(content, maintype=main, subtype=sub or "octet-stream",
                               filename=name)

    port = int(s["port"] or 587)
    context = ssl.create_default_context()
    try:
        if port == 465:
            with smtplib.SMTP_SSL(s["host"], port, context=context,
                                  timeout=20) as server:
                if s["user"]:
                    server.login(s["user"], s["password"])
                server.send_message(message)
        else:
            with smtplib.SMTP(s["host"], port, timeout=20) as server:
                server.ehlo()
                server.starttls(context=context)
                server.ehlo()
                if s["user"]:
                    server.login(s["user"], s["password"])
                server.send_message(message)
    except Exception as exc:                                  # noqa: BLE001
        # Named, not swallowed: "could not send" with a reason is actionable,
        # a silent failure looks like the user mistyped their address.
        reason = f"{type(exc).__name__}: {exc}"[:180]
        # And said out loud where the team can find it. The reason was being
        # returned to the caller and then dropped by both callers, so a real
        # provider rejection left no trace anywhere — not in the log, not on
        # the screen, which is why "why was the code shown here" took a
        # server-side investigation to answer.
        print(f"  mail: could not send to {to} — {reason}", flush=True)
        return {"sent": False, "reason": reason}

    return {"sent": True, "to": to}


def send_code(to: str, code: str, agency: str = "",
              minutes: int = 30) -> dict[str, Any]:
    """Email a verification code.

    A failure here must not lose the registration — the code is already stored,
    so the honest response is "we could not send it", not a stack trace and a
    half-created account.
    """
    if not configured():
        return {"sent": False, "reason": "SMTP is not configured on this server",
                "fallback": "code returned to the caller instead"}
    if no_real_mailbox(to):
        # Not a refusal and not a failure — a deliberate skip. See
        # `no_real_mailbox`: sending here bounces and buys nothing.
        return {"sent": False,
                "reason": "the automated checks' container has no mailbox, "
                          "so nothing was sent",
                "fallback": "code returned to the caller instead"}
    text, html = _body(code, agency, minutes)
    return send(to, f"{code} is your Governing AI verification code",
                text, html)


#: A failed send, translated into something a person can act on.
#:
#: The raw SMTP response is the useful thing and it does not belong in a
#: browser: it is shown on the sign-in screen, before anybody has proved who
#: they are, and it quotes whatever the provider chose to say back. So the
#: provider's own words go to the log, and the caller gets the class of
#: problem and what to do about it.
#: Order matters, and the needles have to be specific. A bare "refused"
#: matched `SMTPRecipientsRefused` and reported a rejected recipient as a
#: network problem, because "connection refused" and "recipients refused"
#: share a word. So the addressing cases are tested first and the connection
#: case looks for the whole phrase.
_FAILURES = (
    (("not verified", "sandbox", "554"),
     "the mail provider will not send to that address yet — the account is "
     "still restricted to verified addresses"),
    (("authentication", "535", "credentials", "login"),
     "the mail provider rejected this server's credentials"),
    (("recipient", "550", "5.1.1", "no such user"),
     "the mail provider says that address does not exist"),
    (("timed out", "timeout", "connection refused", "connectionrefused",
      "connecterror", "resolve", "getaddrinfo", "unreachable"),
     "the mail provider did not answer"),
)


def explain(reason: str) -> str:
    """What went wrong, in words that point at a fix and quote no server."""
    text = (reason or "").lower()
    for needles, plain in _FAILURES:
        if any(needle in text for needle in needles):
            return plain
    return "the mail provider refused the message"


def note_for(delivery: dict[str, Any]) -> str:
    """The sentence shown beside a code that had to be displayed.

    Split out because two call sites in `tenancy` wrote their own, and both
    wrote the same one: "Configure SMTP_HOST and SMTP_FROM on the server to
    send it for real." That is correct advice on a server with no mail
    configured and actively misleading on one that has it — the staging
    deployment has all six SMTP variables set and was still telling its
    operator to go and set two of them, which sent two people looking in the
    wrong place.
    """
    if delivery.get("sent"):
        return ""
    if not configured():
        return ("No mail is configured on this server, so the code is shown "
                "here instead. Set SMTP_HOST and SMTP_FROM to send it for "
                "real.")
    why = explain(str(delivery.get("reason") or ""))
    if may_show_code():
        return (f"Mail is configured, but the message could not be sent: "
                f"{why}. The code is shown here so you can carry on; the "
                f"reason is in the server log.")
    # Withheld. Saying why is still right — the person needs to know whether
    # to wait, retry, or ring somebody — but the code is not theirs to see
    # until they have proved the mailbox is.
    return (f"We could not send your code: {why}. Nothing is wrong with your "
            f"address. Try again in a few minutes; if it keeps failing, tell "
            f"whoever runs this service — the reason is in the server "
            f"log.")


def status() -> dict[str, Any]:
    """What the deployment can actually do, for the interface to be honest about."""
    s = settings()
    return {
        "configured": configured(),
        "host": s["host"] or "(not set)",
        "sender": s["sender"] or "(not set)",
        "note": ("Codes are emailed." if configured() else
                 "SMTP is not configured, so codes are shown on screen instead "
                 "of being emailed. Set SMTP_HOST and SMTP_FROM to send for "
                 "real."),
    }
