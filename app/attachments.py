"""Attachments on a check or an incident — Integrity 8.15 and 11.14.

"A spreadsheet, a memo, a screenshot of the run. Nothing here is read by the
app; it is stored so the next person can see what you saw."

Stored and never read. The application does not parse an uploaded
spreadsheet, does not extract a number from it, and does not use it to compute
anything. Each file lives in the organization's own container, under a random
name, and is handed back only to somebody signed in to that organization —
always as a download, never rendered, so a file somebody uploaded cannot run
as a page on this host.
"""

from __future__ import annotations

import base64
import json
import re
import secrets
from datetime import datetime, timezone
from typing import Any

from app.audit import CORPUS, atomic_write

#: Per file, and per record. Enough for a spreadsheet, a memo or a
#: screenshot; not a place to keep a system export.
MAX_BYTES = 5 * 1024 * 1024
MAX_PER_RECORD = 5

FOLDER = CORPUS / "config" / "attachments"
INDEX = "index.json"

TOO_LARGE = ("That file is larger than 5 MB. Attach a smaller copy, or say "
             "where the full one lives.")
TOO_MANY = "Five files is the most one record holds."
SECURITY_NOTE = ("The kind, never the credential. Nothing on this screen "
                 "should be a secret.")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _folder():
    from app import tenant
    return tenant.scoped(FOLDER)


def _index() -> dict[str, Any]:
    path = _folder() / INDEX
    if not path.is_file():
        return {}
    try:
        held = json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return held if isinstance(held, dict) else {}


def _clean_name(name: str) -> str:
    """Kept only to show a person what they attached. Never used as a path."""
    name = re.sub(r"[\x00-\x1f\\/:*?\"<>|]+", "_", str(name or "")).strip()
    return name[:120] or "attachment"


def store(data: bytes, name: str, *, by: str = "", content_type: str = ""
          ) -> dict[str, Any]:
    """Keep one file, unread. Returns its id, or the refusal in words."""
    if not data:
        return {"ok": False, "error": "That file is empty."}
    if len(data) > MAX_BYTES:
        return {"ok": False, "error": TOO_LARGE}
    folder = _folder()
    folder.mkdir(parents=True, exist_ok=True)
    fid = "AT-" + secrets.token_hex(8).upper()
    (folder / fid).write_bytes(data)
    index = _index()
    index[fid] = {"name": _clean_name(name), "bytes": len(data),
                  # Recorded as given, and never trusted: the file always goes
                  # back as a download.
                  "type": str(content_type or "")[:100],
                  "by": str(by or "")[:120], "at": _now()}
    atomic_write(folder / INDEX, json.dumps(index, indent=2))
    return {"ok": True, "id": fid, **index[fid]}


def store_base64(encoded: str, name: str, *, by: str = "",
                 content_type: str = "") -> dict[str, Any]:
    # A base64 string is a third larger than the file it carries.
    if len(encoded or "") > MAX_BYTES * 4 // 3 + 16:
        return {"ok": False, "error": TOO_LARGE}
    try:
        data = base64.b64decode(encoded or "", validate=True)
    except (ValueError, TypeError):
        return {"ok": False, "error": "That file could not be read."}
    return store(data, name, by=by, content_type=content_type)


def describe(ids: list[str]) -> list[dict[str, Any]]:
    """What a person sees beside a record: the name, the size, who and when."""
    index = _index()
    return [{"id": i, **index[i]} for i in ids or [] if i in index]


def known(ids: list[str]) -> list[str]:
    """Only ids this organization actually holds — a record cannot point at
    somebody else's file by guessing a name."""
    index = _index()
    return [i for i in (ids or []) if isinstance(i, str) and i in index]


def fetch(fid: str) -> dict[str, Any]:
    """Hand one file back, base64, to somebody signed in to this
    organization. The browser saves it; nothing renders it."""
    if not re.fullmatch(r"AT-[0-9A-F]{16}", str(fid or "")):
        return {"ok": False, "error": "No such attachment."}
    index = _index()
    path = _folder() / fid
    if fid not in index or not path.is_file():
        return {"ok": False, "error": "No such attachment."}
    return {"ok": True, "id": fid, "name": index[fid]["name"],
            "data": base64.b64encode(path.read_bytes()).decode("ascii")}
