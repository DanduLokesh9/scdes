"""Append-only, tamper-evident audit log.

Each entry hashes the previous one, so removing or editing a past entry breaks
the chain and `verify()` reports exactly where. This sits behind an `AuditLog`
interface: the spec's preferred backing store is git, and `GitAuditLog` drops in
unchanged once git is available on the host.

Both grants *and* refusals are recorded — an attempt to change a governed field
without authority is itself part of the record.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, asdict, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
DEFAULT_LOG = CORPUS / "audit" / "log.jsonl"

GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str)


def entry_hash(entry: dict[str, Any]) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return hashlib.sha256(_canonical(body).encode("utf-8")).hexdigest()


@dataclass
class Entry:
    seq: int
    at: str
    actor: str
    role: str
    action: str
    target: str
    outcome: str                     # "allowed" | "denied"
    mode: str = ""
    detail: dict[str, Any] = dc_field(default_factory=dict)
    prev_hash: str = GENESIS
    hash: str = ""

    def finalise(self) -> "Entry":
        self.hash = entry_hash(asdict(self))
        return self


class AuditLog(Protocol):
    def append(self, **kwargs: Any) -> Entry: ...
    def entries(self) -> list[Entry]: ...
    def verify(self) -> tuple[bool, str]: ...


class JsonlAuditLog:
    """Hash-chained JSONL. Writes are append-only and fsync'd."""

    def __init__(self, path: Path | str = DEFAULT_LOG) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()

    # -- reading -----------------------------------------------------------

    def _raw(self) -> Iterator[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    def entries(self) -> list[Entry]:
        return [Entry(**row) for row in self._raw()]

    def head(self) -> tuple[int, str]:
        seq, prev = 0, GENESIS
        for row in self._raw():
            seq, prev = row["seq"], row["hash"]
        return seq, prev

    # -- writing -----------------------------------------------------------

    def append(self, *, actor: str, role: str, action: str, target: str,
               outcome: str, mode: str = "",
               detail: dict[str, Any] | None = None) -> Entry:
        seq, prev = self.head()
        entry = Entry(
            seq=seq + 1, at=_now(), actor=actor, role=role, action=action,
            target=target, outcome=outcome, mode=mode, detail=detail or {},
            prev_hash=prev,
        ).finalise()
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(asdict(entry)) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return entry

    # -- integrity ---------------------------------------------------------

    def verify(self) -> tuple[bool, str]:
        prev, expected_seq = GENESIS, 1
        for row in self._raw():
            if row.get("seq") != expected_seq:
                return False, f"sequence break at entry {row.get('seq')!r} (expected {expected_seq})"
            if row.get("prev_hash") != prev:
                return False, f"broken chain at entry {expected_seq}: prev_hash mismatch"
            recomputed = entry_hash(row)
            if recomputed != row.get("hash"):
                return False, f"entry {expected_seq} was modified after it was written"
            prev = row["hash"]
            expected_seq += 1
        return True, f"chain intact ({expected_seq - 1} entries)"


class GitAuditLog(JsonlAuditLog):
    """Mirrors the JSONL chain into git commits when git is available.

    Scaffolded, not active: git is not installed on the reference machine, so
    the JSONL chain is the record of authority. Activating this changes the
    storage, not the interface.
    """

    available = False

    def append(self, **kwargs: Any) -> Entry:      # pragma: no cover - scaffold
        entry = super().append(**kwargs)
        if self.available:
            raise NotImplementedError("git mirroring not enabled in v1")
        return entry


def snapshot(path: Path) -> str:
    """Content hash of a governed file, for recording what a change acted on."""
    if not path.exists():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def atomic_write(path: Path, data: str) -> None:
    """Write governed files without leaving a half-written record behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
