"""Configuration Mode → Operating Mode, and the Council act that closes the gate.

The Council adopted the appendices as *templates*, sight unseen. Configuration
Mode is the one-time window in which OT tunes their real parameters freely. When
OT is finished it proposes the tuned set, the Council adopts it, and the change
guardrails come on: from then on every governed field routes through the Council.

Neither transition is available to OT or to operators. Re-opening bulk tuning is
itself a Council act, recorded as such — it is not an undo.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field as dc_field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from app.audit import CORPUS, atomic_write

MODE_FILE = CORPUS / "config" / "mode.json"
DEFAULT_QUORUM = 3


class Mode(str, Enum):
    CONFIGURATION = "configuration"
    OPERATING = "operating"

    @property
    def label(self) -> str:
        return ("Configuration Mode · tuning open" if self is Mode.CONFIGURATION
                else "Operating Mode · guardrails live")


class ModeError(RuntimeError):
    """Raised when a mode transition is attempted without Council authority."""


@dataclass
class ModeRecord:
    mode: str = Mode.CONFIGURATION.value
    adopted_at: str | None = None
    adopted_by: list[str] = dc_field(default_factory=list)
    parameter_set_hash: str | None = None
    history: list[dict[str, Any]] = dc_field(default_factory=list)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load() -> ModeRecord:
    if not MODE_FILE.exists():
        record = ModeRecord()
        save(record)
        return record
    data = json.loads(MODE_FILE.read_text(encoding="utf-8"))
    return ModeRecord(**data)


def save(record: ModeRecord) -> None:
    atomic_write(MODE_FILE, json.dumps(asdict(record), indent=2) + "\n")


def current() -> Mode:
    return Mode(load().mode)


def is_configuring() -> bool:
    return current() is Mode.CONFIGURATION


def _check_quorum(members: list[str], quorum: int) -> None:
    distinct = sorted(set(m for m in members if m))
    if len(distinct) < quorum:
        raise ModeError(
            f"Council quorum not met: {len(distinct)} member(s) recorded, "
            f"{quorum} required. A mode change is a convened Council decision."
        )


def adopt_operating(*, members: list[str], parameter_set_hash: str,
                    summary: str = "", quorum: int = DEFAULT_QUORUM,
                    audit=None, actor: str = "") -> ModeRecord:
    """Council adopts OT's tuned parameter set; guardrails activate."""
    record = load()
    if record.mode == Mode.OPERATING.value:
        raise ModeError("Already in Operating Mode.")
    _check_quorum(members, quorum)

    record.mode = Mode.OPERATING.value
    record.adopted_at = _now()
    record.adopted_by = sorted(set(members))
    record.parameter_set_hash = parameter_set_hash
    record.history.append({
        "at": record.adopted_at, "to": Mode.OPERATING.value,
        "members": record.adopted_by, "parameter_set_hash": parameter_set_hash,
        "summary": summary or "Tuned parameter set adopted; change guardrails activated.",
    })
    save(record)
    if audit is not None:
        audit.append(
            actor=actor or "council", role="council-member",
            action="adopt_operating_mode", target="mode", outcome="allowed",
            mode=Mode.OPERATING.value,
            detail={"members": record.adopted_by,
                    "parameter_set_hash": parameter_set_hash,
                    "summary": summary},
        )
    return record


def reopen_configuration(*, members: list[str], reason: str,
                         quorum: int = DEFAULT_QUORUM,
                         audit=None, actor: str = "") -> ModeRecord:
    """A second, distinct Council act — not an undo of adoption."""
    record = load()
    if record.mode == Mode.CONFIGURATION.value:
        raise ModeError("Already in Configuration Mode.")
    if not reason.strip():
        raise ModeError("Re-opening bulk tuning requires a recorded reason.")
    _check_quorum(members, quorum)

    record.mode = Mode.CONFIGURATION.value
    record.history.append({
        "at": _now(), "to": Mode.CONFIGURATION.value,
        "members": sorted(set(members)), "reason": reason,
    })
    save(record)
    if audit is not None:
        audit.append(
            actor=actor or "council", role="council-member",
            action="reopen_configuration_mode", target="mode",
            outcome="allowed", mode=Mode.CONFIGURATION.value,
            detail={"members": sorted(set(members)), "reason": reason},
        )
    return record
