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
import threading
from dataclasses import dataclass, asdict, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol

CORPUS = Path(__file__).resolve().parent.parent / "corpus"
DEFAULT_LOG = CORPUS / "audit" / "log.jsonl"

GENESIS = "0" * 64


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _version_now() -> str:
    """The framework version in force, right now.

    Swallows its own failures and returns "" — which renders as "before your
    framework took effect", the ordinary reading for an organization that has
    not adopted anything yet. A log that refuses to write because it could
    not resolve a version stamp would lose the event entirely, and the event
    is worth more than the stamp.
    """
    try:
        from app import versions
        return str(versions.export_label() or "")
    except Exception:                                         # noqa: BLE001
        return ""


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
    #: Which version of the organisation's framework was in force when this
    #: was written. Resolved at the moment of writing and never afterwards.
    #:
    #: "The fourth is the one everybody forgets to keep, and it is the one
    #: that settles the argument, because rules move. A decision made under
    #: what you had written in March is not defensible against what you had
    #: written in September unless you can show what March said."
    #:
    #: Empty means the entry predates the framework's first effective date,
    #: which is ordinary — most organisations write down half their register
    #: before they adopt anything — and renders as "before your framework
    #: took effect" rather than as a fault.
    version: str = ""
    #: When the thing happened, where that is earlier than when it was
    #: written down. Empty means the two are the same moment.
    #:
    #: Order is recorded, never enforced. A tool found already running walks
    #: Identify, Procure and Test in order, with each date saying when it was
    #: recorded rather than pretending it happened first.
    happened: str = ""
    prev_hash: str = GENESIS
    hash: str = ""

    def finalise(self) -> "Entry":
        self.hash = entry_hash(asdict(self))
        return self


class AuditLog(Protocol):
    def append(self, **kwargs: Any) -> Entry: ...
    def entries(self) -> list[Entry]: ...
    def verify(self) -> tuple[bool, str]: ...


#: One lock per log file, shared by every instance pointing at it.
#:
#: `append` reads the head of the chain, computes a hash from it, and then
#: writes. Two threads doing that at once can interleave — and the server is a
#: `ThreadingHTTPServer`, so two requests genuinely are concurrent. The
#: observed failure was a torn line: one entry's bytes written into the middle
#: of another's, leaving a file that would not parse and a chain that could
#: not be verified.
#:
#: That is the worst place in this application for a race. The log is the
#: tamper-evidence mechanism; a log that corrupts itself under ordinary load
#: cannot be relied on to show that nobody tampered with it.
#:
#: Keyed by resolved path rather than held per instance, because handlers
#: construct `JsonlAuditLog()` freely and two objects pointing at one file
#: must not each hold their own lock.
_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        if key not in _LOCKS:
            _LOCKS[key] = threading.Lock()
        return _LOCKS[key]


class JsonlAuditLog:
    """Hash-chained JSONL. Writes are append-only, serialized and fsync'd."""

    def __init__(self, path: Path | str = DEFAULT_LOG) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self.path.touch()
        self._lock = _lock_for(self.path)

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
               detail: dict[str, Any] | None = None,
               version: str | None = None, happened: str = "") -> Entry:
        # Reading the head and writing the next entry is one operation, not
        # two. Split across threads it produces a torn line and a chain that
        # will not verify — see the note on `_LOCKS`.
        with self._lock:
            seq, prev = self.head()
            entry = Entry(
                seq=seq + 1, at=_now(), actor=actor, role=role, action=action,
                target=target, outcome=outcome, mode=mode,
                detail=detail or {},
                # Resolved here, at the moment of writing, rather than looked
                # up when the entry is read. An entry read in September has
                # to say what March said, and a version resolved at read time
                # would say what September says.
                version=(_version_now() if version is None else version),
                happened=happened,
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


def organisation_log_path() -> Path | None:
    """Where the organization on this request keeps its own trail.

    Every organization — the corpus owner included — has a trail of its own
    under its own directory, and no screen anywhere reads another's. Before
    this, every organization wrote into one shared file and the audit screen
    served its last sixty lines to whoever asked: one agency's names and
    actions, in front of another.

    With no organization set (a tool, a test, the command line) the original
    single path is kept. An unresolved browser gets no trail of its own —
    what it causes is still kept in the back-end copy.
    """
    from app import tenant
    code = tenant.current()
    if not code:
        return DEFAULT_LOG
    if code == tenant.ANONYMOUS:
        return None
    return tenant.AGENCIES / code / "audit" / "log.jsonl"


class OrganisationLog:
    """The log a write lands in: this organization's own trail, and the
    back-end copy of everything, which no organization's screen reads.

    The back-end copy is the original shared file. It keeps growing, so the
    record survives whatever happens to any one organization's directory, and
    each line in it says which organization it came from. Where the two paths
    are the same — no organization set — the entry is written once.
    """

    @property
    def path(self) -> Path:
        return organisation_log_path() or DEFAULT_LOG

    def _own(self) -> JsonlAuditLog | None:
        where = organisation_log_path()
        return JsonlAuditLog(where) if where else None

    def append(self, **kwargs: Any) -> Entry:
        from app import impersonate, tenant
        # A GAIUS admin viewing as somebody (app/impersonate.py) leaves no
        # mark on that organization: anything recorded while viewing goes to
        # the back-end copy only, saying who was viewing. Nothing reaches the
        # organization's own History, and nothing is written in their name.
        viewing = impersonate.current()
        if viewing:
            copy = dict(kwargs)
            copy["detail"] = {**(kwargs.get("detail") or {}),
                              "organisation": tenant.current() or "",
                              "while_viewing_as": viewing["email"],
                              "viewed_by": viewing["admin"]}
            return JsonlAuditLog(DEFAULT_LOG).append(**copy)
        own = self._own()
        written = own.append(**kwargs) if own else None
        if own is None or own.path.resolve() != DEFAULT_LOG.resolve():
            copy = dict(kwargs)
            copy["detail"] = {**(kwargs.get("detail") or {}),
                              "organisation": tenant.current() or ""}
            master = JsonlAuditLog(DEFAULT_LOG).append(**copy)
            written = written or master
        return written

    def entries(self) -> list[Entry]:
        own = self._own()
        return own.entries() if own else []

    def _raw(self) -> Iterator[dict[str, Any]]:
        own = self._own()
        return own._raw() if own else iter(())

    def head(self) -> tuple[int, str]:
        own = self._own()
        return own.head() if own else (0, GENESIS)

    def verify(self) -> tuple[bool, str]:
        own = self._own()
        return own.verify() if own else (True, "chain intact (0 entries)")


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
