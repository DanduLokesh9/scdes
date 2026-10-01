"""Does the verification email actually send?

`app/mailer.py` is well-formed and, as far as this project's history goes, has
never run. SMTP has never been configured on any deployment, so every code has
taken the fallback path and been shown on screen. That means the send path is
unexercised: if it is broken, the symptom appears the moment SES is finally
configured — codes stop arriving, and nothing distinguishes that from a DNS
problem.

So this drives the real `smtplib` code against a real SMTP conversation, using a
minimal server implemented here. Four cases:

  1. unconfigured — the fallback reports itself rather than pretending to send
  2. configured but unreachable — a named failure, not an exception
  3. configured and reachable — the message arrives, with the code in it
  4. `status()` tells the truth in both states

**One thing is stubbed, deliberately and narrowly: the TLS upgrade.**

The mailer calls `starttls()` on every non-465 port and builds a *verifying*
context, both of which are right — SES and SendGrid require TLS, and a mail
client that accepts any certificate is not securing anything. Exercising that
against a local server needs a certificate, and this machine has neither
`openssl` nor `cryptography`. Adding a dependency to a project with three, or
committing a throwaway private key, are both worse than the alternative:
`smtplib.SMTP.starttls` is replaced with a no-op for the duration, so the
conversation continues in plaintext to a local sink.

What that means for what this proves. The transport encryption is *not* tested
here — it is stdlib, and the same three lines every Python mailer uses. The
product's own logic is: the configuration gate, the envelope, the login, the
headers, both body parts, the DATA leg and the error handling. Those are what
break, and those are real here.

The TLS leg gets exercised the first time a code is sent through SES's sandbox,
which is the right place for it.

Usage:  python -m tools.check_mail
"""

from __future__ import annotations

import email
import os
import socket
import threading

from app import mailer

HOST = "127.0.0.1"


class Sink(threading.Thread):
    """The smallest SMTP server the mailer's conversation completes against.

    Speaks greeting, EHLO with STARTTLS advertised, AUTH, envelope, DATA and
    QUIT. It never has to perform the TLS upgrade because the harness stubs the
    client's `starttls()` — see the module note.
    """

    daemon = True

    def __init__(self) -> None:
        super().__init__()
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((HOST, 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]
        self.received: list[str] = []
        self.envelope: dict[str, str] = {}
        self.authed = False

    def run(self) -> None:            # noqa: C901 - a protocol, not a branch tree
        try:
            conn, _ = self.sock.accept()
        except OSError:
            return
        conn.settimeout(20)
        stream = conn.makefile("rwb")

        def say(line: str) -> None:
            stream.write((line + "\r\n").encode())
            stream.flush()

        say("220 localhost ESMTP probe")
        in_data = False
        body: list[str] = []
        while True:
            try:
                raw = stream.readline()
            except (OSError, ValueError):
                break
            if not raw:
                break
            line = raw.decode("utf-8", "replace").rstrip("\r\n")

            if in_data:
                if line == ".":
                    in_data = False
                    self.received.append("\n".join(body))
                    body = []
                    say("250 2.0.0 queued")
                else:
                    body.append(line[1:] if line.startswith("..") else line)
                continue

            upper = line.upper()
            if upper.startswith("EHLO") or upper.startswith("HELO"):
                say("250-localhost")
                say("250-STARTTLS")
                say("250-AUTH PLAIN LOGIN")
                say("250 8BITMIME")
            elif upper.startswith("AUTH"):
                self.authed = True
                say("235 2.7.0 accepted")
            elif upper.startswith("MAIL FROM"):
                self.envelope["from"] = line.partition(":")[2].strip()
                say("250 2.1.0 ok")
            elif upper.startswith("RCPT TO"):
                self.envelope["to"] = line.partition(":")[2].strip()
                say("250 2.1.5 ok")
            elif upper.startswith("DATA"):
                in_data = True
                say("354 end with .")
            elif upper.startswith("QUIT"):
                say("221 2.0.0 bye")
                break
            else:
                say("250 2.0.0 ok")
        try:
            conn.close()
        except OSError:
            pass


def configure(**over: str) -> None:
    for key in ("SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASSWORD",
                "SMTP_FROM", "SMTP_FROM_NAME"):
        os.environ.pop(key, None)
    for key, value in over.items():
        os.environ[key] = value


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<46} {detail}")
        if not ok:
            failures.append(label)

    print("1. with SMTP unconfigured")
    configure()
    check("configured() says no", not mailer.configured())
    out = mailer.send_code("jane@des.sc.gov", "482917", "SCDES")
    check("it does not claim to have sent", out["sent"] is False)
    check("it says why", "not configured" in out["reason"], out["reason"][:40])
    check("and names the fallback", bool(out.get("fallback")),
          out.get("fallback", ""))
    status = mailer.status()
    check("status() is honest", not status["configured"]
          and "shown on screen" in status["note"])

    print("\n2. configured, but the host is not there")
    # Port 1 is reserved and nothing listens on it.
    configure(SMTP_HOST=HOST, SMTP_PORT="1", SMTP_FROM="no-reply@governingai.us")
    check("configured() says yes", mailer.configured())
    out = mailer.send_code("jane@des.sc.gov", "482917", "SCDES")
    check("the failure is caught, not raised", out["sent"] is False)
    check("with the cause named", ":" in out["reason"], out["reason"][:56])

    print("\n3. configured and reachable")
    if True:
        sink = Sink()
        sink.start()
        configure(SMTP_HOST=HOST, SMTP_PORT=str(sink.port),
                  SMTP_USER="apikey", SMTP_PASSWORD="secret",
                  SMTP_FROM="no-reply@governingai.us",
                  SMTP_FROM_NAME="Governing AI")
        # The one stub — see the module note. TLS is stdlib; everything the
        # product does either side of it is not.
        import smtplib
        real_starttls = smtplib.SMTP.starttls
        smtplib.SMTP.starttls = lambda self, *a, **k: (220, b"stubbed")
        try:
            out = mailer.send_code("jane@des.sc.gov", "482917", "SCDES")
        finally:
            smtplib.SMTP.starttls = real_starttls
        sink.join(timeout=15)

        check("it reports success", out.get("sent") is True,
              out.get("reason", ""))
        check("the message arrived", bool(sink.received),
              f"{len(sink.received)} message(s)")
        check("it authenticated", sink.authed,
              "SMTP_USER was set, so login had to be attempted")
        check("the envelope is right",
              "no-reply@governingai.us" in sink.envelope.get("from", "")
              and "jane@des.sc.gov" in sink.envelope.get("to", ""),
              f'{sink.envelope.get("from")} -> {sink.envelope.get("to")}')

        if sink.received:
            message = email.message_from_string(sink.received[0])
            check("subject carries the code",
                  "482917" in (message["Subject"] or ""), message["Subject"])
            check("from-name is set",
                  "Governing AI" in (message["From"] or ""), message["From"])
            parts = {p.get_content_type(): p.get_payload(decode=True)
                     for p in message.walk() if p.get_payload(decode=True)}
            check("a plain-text part exists", "text/plain" in parts)
            check("an HTML part exists too", "text/html" in parts,
                  "a code-only mail that renders empty is a support ticket")
            for kind, blob in parts.items():
                if not blob:
                    continue
                check(f"the code is in the {kind.split('/')[1]} part",
                      b"482917" in blob)
            check("it names the agency",
                  any(b"SCDES" in b for b in parts.values() if b))
            check("and says who sent it",
                  any(b"iiac.ai" in b for b in parts.values() if b))

    configure()
    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — the send path works; only the credentials and DNS are missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
