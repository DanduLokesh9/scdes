"""Read a local ``.env`` into the environment.

The server gets its secrets from ``/etc/governingai.env``, which systemd
loads before the process starts. A laptop has no systemd unit, so without
this every local run of the polish tools needs the key exported by hand, and
the first thing anybody does about that is paste the key into a script.

Deliberately small, and deliberately not a dependency. `python-dotenv` does
rather more than this needs — interpolation, nested files, a CLI — and every
dependency added to this project has to be justified to somebody who will
ask why an AI governance application needs it.

Three rules, all of them about not surprising anyone:

**The environment wins.** A variable already set is never overwritten, so a
value exported in a shell, or set by systemd, beats the file. Otherwise a
stale ``.env`` on a laptop would silently override the real configuration.

**It is called, not imported.** Loading at import time would mean the test
suite's behavior depended on whether a file existed on the machine running
it, and a live API key sitting in ``.env`` would quietly turn offline tests
into billable ones. So the server and the tools that need it ask for it.

**It is never logged.** Nothing here prints a value, and the file is
excluded from the deploy bundle — see ``deploy/push.ps1``.
"""

from __future__ import annotations

import os
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
ENV_FILE = ROOT / ".env"

#: Values that mean "nobody has filled this in". Skipped rather than set,
#: because the alternative is worse than an unset variable: a key reading
#: PASTE_KEY_HERE is a non-empty string, so everything downstream reports
#: itself as configured and then fails an authentication check on every
#: clause of the document. "Not configured" is a state this application
#: handles honestly and says out loud. "Configured with nonsense" is not.
PLACEHOLDERS = frozenset("""
paste_key_here your_key_here changeme change_me todo tbd xxx none null
sk-ant-xxx replace_me
""".split())


def load(path: pathlib.Path | None = None) -> list[str]:
    """Set any variable in the file that is not already set.

    Returns the names it set — names only, never values, so a caller can say
    what it picked up without putting a secret in a log.
    """
    where = path or ENV_FILE
    try:
        text = where.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    took: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip()
        # "export FOO=bar" is what people paste out of documentation.
        if name.startswith("export "):
            name = name[len("export "):].strip()
        if not name or not name.replace("_", "").isalnum():
            continue
        value = value.strip()
        # Quotes are for the shell's benefit, not ours.
        if len(value) > 1 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if not value or value.lower() in PLACEHOLDERS:
            continue
        if os.environ.get(name):
            continue
        os.environ[name] = value
        took.append(name)
    return took
