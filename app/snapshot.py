"""Keep a copy of your work, and put it back.

The client wanted a way to wipe his tenant so he could demo from zero and test
from a clean start. A one-way wipe does that once. What he actually needs is to
do it repeatedly without losing the content he spent a fortnight entering, so:
take a snapshot, wipe, demo, restore.

    "Great idea. Didn't know it was even possible."

What a snapshot is, and is not
------------------------------

It is a copy of **the same things a reset clears**, and deliberately not a list
of its own. `reset._targets()` is the one definition of "this agency's work",
and both features read it. Two lists would drift, and the failure would be
silent and terrible: a snapshot that misses a file restores an agency to a
state it was never in.

It is **per agency**, like everything else here. A snapshot is taken from and
restored into the caller's own container, and nothing in this module can name
another one — the paths come from `reset._targets()`, which is already scoped.

It does **not** include the audit log, and restoring does not rewind it. The
client's rule is that the log survives absolutely, and a snapshot that could
roll it back would make it a draft rather than a record. Taking, restoring and
deleting a snapshot are each themselves audited, so the log ends up with *more*
in it, never less. What the log will show is the truth: that on this date this
agency's answers were replaced with a copy taken earlier.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app import reset as reset_mod
from app.authz import Actor

#: How many snapshots one agency may keep. Enough for a demo cycle and a
#: couple of experiments; bounded because these are full copies and nobody
#: prunes something the interface never mentions filling up.
LIMIT = 12

#: Bounded so a label cannot become a way to write an essay into a filename.
LABEL_LIMIT = 80


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _record(action: str, actor: Actor, detail: dict[str, Any]) -> None:
    """Audit the act, without gating it on a capacity.

    These were guarded on `Target.CONFIG`, which is the Office of Technology's
    to set — so a person clicking "Take a snapshot" was told "operator cannot
    take_snapshot". Their own content, in their own container, refused because
    of a dropdown in the header.

    That is the same circularity already removed from `versions.answer`: a
    public official writing their first framework has no Office of Technology,
    and whether they should have one is question 4.1. What makes these acts
    safe is not a capacity, it is that every path they touch comes from
    `reset._targets()`, which is scoped to the caller's own container and
    cannot name anybody else's.

    So the record stays and the gate goes. The governed acts — cutting a
    version, recording an adoption — are still guarded, which is the whole
    point of the draft/adopted split.
    """
    from app import tenant
    from app.authz import default_log
    try:
        default_log().append(
            actor=actor.user_id, role=actor.role.value, action=action,
            target="config", outcome="allowed",
            detail={**detail,
                    "agency": tenant.current(),
                    "actor_name": (actor.name or "").strip()[:120],
                    "actor_title": (actor.title or "").strip()[:120],
                    "reason": "The agency's own draft content, in its own "
                              "container. Recorded, not gated."})
    except Exception:
        # A copy is not refused because the log could not be written. The log
        # records what happened; it is not a lock on it.
        pass


def _home() -> Path:
    """Where this agency's snapshots live."""
    from app import tenant
    return tenant.data_dir() / "snapshots"


def _folder(snapshot_id: str) -> Path | None:
    """The directory for this id, or None if it is not one of ours.

    Resolved and checked for containment rather than string-matched. The first
    version rejected anything with a slash in it, which let `".."` through —
    and `forget("..")` would then have deleted the agency's entire data
    directory rather than one snapshot. Caught by its own test, before it
    reached anybody.

    Requiring `about.json` is the second half: a directory that is not a
    snapshot cannot be restored from or deleted through here, whatever it is
    called.
    """
    home = _home()
    try:
        folder = (home / str(snapshot_id)).resolve()
    except (OSError, ValueError):
        return None
    if folder.parent != home.resolve() or not folder.is_dir():
        return None
    if not (folder / "about.json").is_file():
        return None
    return folder


def _safe(label: str) -> str:
    """A label reduced to something that can be part of a directory name."""
    kept = "".join(c if c.isalnum() or c in " -_" else "" for c in label)
    return kept.strip()[:40].replace(" ", "-") or "snapshot"


def listing() -> dict[str, Any]:
    """Every snapshot this agency holds, newest first."""
    home = _home()
    out = []
    if home.is_dir():
        for folder in home.iterdir():
            record = folder / "about.json"
            if not record.is_file():
                continue
            try:
                about = json.loads(record.read_text(encoding="utf-8"))
            except ValueError:
                continue
            out.append({**about, "id": folder.name})
    out.sort(key=lambda s: str(s.get("taken_at", "")), reverse=True)
    return {"snapshots": out, "limit": LIMIT, "room": max(0, LIMIT - len(out))}


def take(actor: Actor, *, label: str = "") -> dict[str, Any]:
    """Copy this agency's work aside, under a name they can recognize."""
    _record("take_snapshot", actor, {"label": label[:LABEL_LIMIT]})

    held = listing()
    if len(held["snapshots"]) >= LIMIT:
        return {"ok": False,
                "error": f"You are holding {LIMIT} snapshots, which is the "
                         f"limit. Delete one you no longer need first."}

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    folder = _home() / f"{stamp}-{_safe(label)}"
    folder.mkdir(parents=True, exist_ok=True)

    copied = []
    for target in reset_mod._targets():
        if not target.path.exists():
            continue
        into = folder / target.path.name
        if target.path.is_dir():
            shutil.copytree(target.path, into, dirs_exist_ok=True)
        else:
            shutil.copy2(target.path, into)
        copied.append(target.label)

    about = {
        "label": (label or "").strip()[:LABEL_LIMIT] or "Unnamed",
        "taken_at": _now(),
        "taken_by": (actor.name or "").strip()[:120],
        "taken_title": (actor.title or "").strip()[:120],
        "holds": copied,
    }
    (folder / "about.json").write_text(
        json.dumps(about, indent=2), encoding="utf-8")

    return {"ok": True, "id": folder.name, **about, "state": listing()}


def restore(snapshot_id: str, actor: Actor) -> dict[str, Any]:
    """Put a snapshot back, replacing whatever is there now.

    Replacing, not merging. A half-restored agency — this snapshot's answers
    beside today's adoption record — is a state nobody chose and nobody could
    reason about. So every target a reset would clear is cleared first, and
    then the snapshot is laid down.
    """
    folder = _folder(snapshot_id)
    if folder is None:
        return {"ok": False, "error": f"No snapshot {snapshot_id!r}."}

    _record("restore_snapshot", actor,
            {"snapshot": snapshot_id,
             "note": "the agency's own work is replaced; the audit log is "
                     "untouched and this entry records the replacement"})

    restored = []
    for target in reset_mod._targets():
        saved = folder / target.path.name
        # Clear first, so anything created since the snapshot goes too.
        if target.path.is_dir():
            if target.path.exists():
                shutil.rmtree(target.path, ignore_errors=True)
        elif target.path.exists():
            target.path.unlink()

        if not saved.exists():
            continue
        target.path.parent.mkdir(parents=True, exist_ok=True)
        if saved.is_dir():
            shutil.copytree(saved, target.path, dirs_exist_ok=True)
        else:
            shutil.copy2(saved, target.path)
        restored.append(target.label)

    return {"ok": True, "id": snapshot_id, "restored": restored,
            "state": listing()}


def forget(snapshot_id: str, actor: Actor) -> dict[str, Any]:
    """Delete a snapshot. The work it held is gone with it."""
    folder = _folder(snapshot_id)
    if folder is None:
        return {"ok": False, "error": f"No snapshot {snapshot_id!r}."}

    _record("forget_snapshot", actor, {"snapshot": snapshot_id})

    shutil.rmtree(folder, ignore_errors=True)
    return {"ok": True, "id": snapshot_id, "state": listing()}


