#!/usr/bin/env bash
# Does SES accept a message to this address, and if not, what does it say?
#
# The SES API is closed to us — the instance role has no ses:* read
# permissions and the SMTP password cannot call the API at all. So the only
# way left to ask AWS about our own sending is to try to send, and read the
# answer.
#
# This runs the application's own mailer, so what it tests is exactly what a
# user's verification code goes through. It prints whether the message was
# accepted and, if not, what SES said. Nothing else.
#
#   bash /tmp/ses_probe.sh someone@example.gov
#
# Sends one real message on success. Point it at an address you own.

set -uo pipefail
TO="${1:?usage: ses_probe.sh <recipient>}"

cd /opt/governingai || exit 1

# The environment file is parsed by the interpreter, not by the shell.
#
# `sudo env $(grep ...)` looked tidier and broke immediately: the file holds
# `SMTP_FROM_NAME=Governing AI`, and word-splitting turned the space into a
# second argument — "env: 'AI': No such file or directory". systemd's own
# parser reads KEY=VALUE to the end of the line, so this does the same.
sudo /opt/governingai/.venv/bin/python - "$TO" <<'PY'
import os
import pathlib
import sys

for line in pathlib.Path("/etc/governingai.env").read_text().splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, _, value = line.partition("=")
    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))

from app import mailer

to = sys.argv[1]
print(f"  host configured : {mailer.configured()}")
s = mailer.settings()
print(f"  sending as      : {s['sender_name']} <{s['sender']}>")
print(f"  via             : {s['host']}:{s['port']}")
print()

out = mailer.send(
    to,
    "Governing AI — mail delivery probe",
    "This is a delivery probe sent to confirm that outbound mail works.\n"
    "No action is needed.\n",
)
print(f"  accepted        : {out.get('sent')}")
if not out.get("sent"):
    print(f"  provider said   : {out.get('reason')}")
    print(f"  in plain words  : {mailer.explain(str(out.get('reason') or ''))}")
PY
