"""First use, remembered per person rather than per browser.

The guided tour is shown "on the first use" (Brett, Oct 2026). Whether it had
been seen lived only in the browser's storage, so it came back on every new
browser, every new machine and every cleared cache — "buggy and showing all the
time". This keeps it against the person's proven address instead, so it is
shown once, wherever they sign in from. Nothing else is stored.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "first_use.json"
_LOCK = threading.Lock()


def _load() -> dict[str, Any]:
    try:
        return json.loads(STORE.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def tour_seen(email: str) -> bool:
    address = (email or "").strip().lower()
    return bool(address) and bool((_load().get(address) or {}).get("tour_seen_at"))


def mark_tour_seen(email: str) -> dict[str, Any]:
    address = (email or "").strip().lower()
    if not address:
        return {"ok": False, "error": "Sign in first."}
    with _LOCK:
        data = _load()
        person = data.get(address) or {}
        if not person.get("tour_seen_at"):
            person["tour_seen_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            data[address] = person
            STORE.parent.mkdir(parents=True, exist_ok=True)
            tmp = STORE.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
            tmp.replace(STORE)
    return {"ok": True}
