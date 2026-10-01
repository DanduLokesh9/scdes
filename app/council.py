"""The decision record — the gated room where the governance itself changes.

Append-only. Framework and appendix amendments run propose → diff → approve →
commit; gate decisions and award decisions are logged against their tier; the
minutes and recordings live here too.

**Who the decider is comes from `app/decider.py`, not from this module.** The
name is historical: this file was written for SCDES, which has a council, and it
used to state as fact that decisions are graded A/B/C with a 72-hour concurrence
and a convened session. That is SCDES's answer to a framework question, and an
agency whose framework named one person instead has no body to concur and no
session to convene. So the tiers, the quorum and the wording are all read from
the answer that agency actually gave; only the storage and the append-only
discipline live here.

The canonical keys stay A/B/C whichever shape is chosen, so a decision recorded
under one arrangement is still readable under another.
"""

from __future__ import annotations

import difflib
import json
import uuid
from dataclasses import dataclass, asdict, field as dc_field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.audit import CORPUS, atomic_write
from app.authz import Actor, Decision, Role, Target, guard

COUNCIL_DIR = CORPUS.parent / "council"
DECISION_LOG = COUNCIL_DIR / "decision_log.jsonl"
PROPOSALS = COUNCIL_DIR / "proposals.jsonl"
MINUTES_DIR = COUNCIL_DIR / "minutes"
RECORDINGS_DIR = COUNCIL_DIR / "recordings"
MEMBERS_FILE = COUNCIL_DIR / "members.yaml"

TIER_A, TIER_B, TIER_C = "A", "B", "C"


def tier_rules() -> dict[str, str]:
    """What each decision level requires, in this agency's arrangement.

    A single decider has one level, because the other two describe things that
    only a group can do. Offering all three to someone who chose one person
    would be offering them procedures they cannot carry out.
    """
    from app import decider
    return {k.upper(): v for k, v in decider.levels().items()}



def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().isoformat(timespec="seconds")


def _append(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _read(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in
            path.read_text(encoding="utf-8").splitlines() if line.strip()]


# -------------------------------------------------------------------- members

DEFAULT_MEMBERS = {
    "quorum": 3,
    "members": [
        {"id": "council.cto", "name": "Chief Technology Officer", "chair": True},
        {"id": "council.gc", "name": "General Counsel"},
        {"id": "council.water", "name": "Bureau Chief — Water"},
        {"id": "council.air", "name": "Bureau Chief — Air"},
        {"id": "council.strategist", "name": "AI Strategist", "secretary": True},
    ],
}


def members() -> dict[str, Any]:
    if not MEMBERS_FILE.exists():
        import yaml
        MEMBERS_FILE.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(MEMBERS_FILE, yaml.safe_dump(DEFAULT_MEMBERS, sort_keys=False))
        return DEFAULT_MEMBERS
    import yaml
    return yaml.safe_load(MEMBERS_FILE.read_text(encoding="utf-8"))


def quorum() -> int:
    """Members needed for a convened session.

    A single decider is always their own quorum — asking one person to muster
    three is how a framework becomes unusable.
    """
    from app import decider
    if not decider.is_group():
        return 1
    return int(members().get("quorum", decider.quorum()))


def is_member(actor: Actor) -> bool:
    """Whether this actor holds the deciding authority.

    Role.COUNCIL is the canonical name for that capacity whichever shape the
    agency chose; what the interface *calls* it comes from decider.py.
    """
    from app import decider
    if not decider.is_group():
        return actor.role is Role.COUNCIL
    ids = {m["id"] for m in members().get("members", [])}
    return actor.role is Role.COUNCIL and (actor.user_id in ids or not ids)


# ------------------------------------------------------------------ decisions

def log_decision(*, tier: str, summary: str, actor: Actor,
                 refs: list[str] | None = None,
                 kind: str = "decision",
                 detail: dict[str, Any] | None = None) -> dict[str, Any]:
    """Record an A/B/C decision. Council-gated and audited."""
    decision = guard(actor, Target.COUNCIL_LOG, f"log_decision_tier_{tier}",
                     detail={"tier": tier, "summary": summary[:120]})
    if not decision.allowed:
        return {"logged": False, "reason": decision.reason}

    entry = {
        "decision_id": f"D-{uuid.uuid4().hex[:8].upper()}",
        "at": _stamp(), "tier": tier, "kind": kind, "summary": summary,
        "by": actor.user_id, "by_name": actor.name,
        "refs": refs or [], "detail": detail or {},
        "tier_rule": tier_rules().get(tier, ""),
        "status": "recorded",
    }
    _append(DECISION_LOG, entry)
    return {"logged": True, **entry}


def decisions(limit: int | None = None) -> list[dict[str, Any]]:
    rows = list(reversed(_read(DECISION_LOG)))
    return rows[:limit] if limit else rows


def tier_for_band(band: str) -> str:
    """Which decision tier a gate decision needs, given the project's risk.

    Under a single decider every band lands on A: risk cannot summon a body the
    agency did not create, so a high-risk system is still that person's call —
    logged, and reported out.
    """
    from app import decider
    return decider.level_for_band(band).upper()


def request_gate_decision(*, project, gate: int, actor: Actor,
                          summary: str = "") -> dict[str, Any]:
    """Route a gate decision to the Council. The operator does not self-approve."""
    risk = project.risk()
    tier = tier_for_band(risk.band)
    entry = {
        "decision_id": f"D-{uuid.uuid4().hex[:8].upper()}",
        "at": _stamp(), "tier": tier, "kind": "gate_decision",
        "summary": summary or f"Gate {gate} decision for {project.name}",
        "requested_by": actor.user_id,
        "registry_id": project.registry_id, "gate": gate,
        "risk_band": risk.band, "composite": risk.total,
        "tier_rule": tier_rules().get(tier, ""),
        "status": "awaiting_decision",
        "due_by": (_now() + timedelta(hours=72)).isoformat(timespec="seconds")
        if tier == TIER_B else None,
        "refs": ["Appendix H — Gate Review Checklists",
                 "Appendix B — AI Risk Classification Matrix"],
    }
    _append(DECISION_LOG, entry)
    return entry


def decide_gate(decision_id: str, *, outcome: str, actor: Actor,
                members_present: list[str] | None = None,
                rationale: str = "") -> dict[str, Any]:
    """Council records the outcome of a routed gate decision."""
    guard_result = guard(actor, Target.COUNCIL_LOG, "decide_gate",
                         detail={"decision_id": decision_id, "outcome": outcome})
    if not guard_result.allowed:
        return {"decided": False, "reason": guard_result.reason}

    original = next((d for d in _read(DECISION_LOG)
                     if d.get("decision_id") == decision_id), None)
    if original is None:
        return {"decided": False, "reason": f"unknown decision {decision_id}"}

    tier = original.get("tier", TIER_B)
    present = members_present or [actor.user_id]
    if tier == TIER_C and len(set(present)) < quorum():
        return {"decided": False,
                "reason": (f"Tier C requires a convened session: {len(set(present))} "
                           f"member(s) present, quorum is {quorum()}.")}

    entry = {
        "decision_id": f"D-{uuid.uuid4().hex[:8].upper()}",
        "at": _stamp(), "tier": tier, "kind": "gate_outcome",
        "resolves": decision_id, "outcome": outcome,
        "summary": f"{outcome.title()} — {original.get('summary', '')}",
        "by": actor.user_id, "members_present": sorted(set(present)),
        "rationale": rationale, "registry_id": original.get("registry_id"),
        "gate": original.get("gate"), "status": "recorded",
    }
    _append(DECISION_LOG, entry)

    if outcome == "approved" and original.get("registry_id"):
        from app import registry as registry_mod
        gate = int(original.get("gate", 0))
        stage = {0: "concept", 1: "concept", 2: "pilot", 3: "production",
                 4: "production", 5: "production"}.get(gate, "concept")
        registry_mod.advance_stage(
            original["registry_id"], actor, stage=stage, gate=gate,
            note=f"Advanced on Council decision {entry['decision_id']}")
        entry["advanced"] = True
    return {"decided": True, **entry}


# ------------------------------------------------------- amendments (gated)

def propose_amend(*, target: str, path: str, new_content: str, actor: Actor,
                  rationale: str = "") -> dict[str, Any]:
    """Propose a change to a governed text. Produces a diff for review."""
    guard_result = guard(actor, Target.FRAMEWORK, "propose_amendment",
                         detail={"target": target, "path": path})
    if not guard_result.allowed:
        return {"proposed": False, "reason": guard_result.reason,
                "requires_council": guard_result.requires_council}

    source = Path(path)
    current = source.read_text(encoding="utf-8") if source.exists() else ""
    diff = "\n".join(difflib.unified_diff(
        current.splitlines(), new_content.splitlines(),
        fromfile=f"{target} (current)", tofile=f"{target} (proposed)", lineterm=""))

    proposal = {
        "proposal_id": f"P-{uuid.uuid4().hex[:8].upper()}",
        "at": _stamp(), "target": target, "path": str(path),
        "proposed_by": actor.user_id, "rationale": rationale,
        "diff": diff, "new_content": new_content,
        "status": "open", "approvals": [],
    }
    _append(PROPOSALS, proposal)
    return {"proposed": True, **proposal}


def proposals(open_only: bool = True) -> list[dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _read(PROPOSALS):
        latest[row["proposal_id"]] = {**latest.get(row["proposal_id"], {}), **row}
    rows = list(latest.values())
    return [r for r in rows if r.get("status") == "open"] if open_only else rows


def approve(proposal_id: str, actor: Actor, *,
            commit: bool = True) -> dict[str, Any]:
    """Approve and commit an amendment. Council members only."""
    guard_result = guard(actor, Target.FRAMEWORK, "approve_amendment",
                         detail={"proposal_id": proposal_id})
    if not guard_result.allowed:
        return {"approved": False, "reason": guard_result.reason}

    proposal = next((p for p in proposals(open_only=False)
                     if p["proposal_id"] == proposal_id), None)
    if proposal is None:
        return {"approved": False, "reason": f"unknown proposal {proposal_id}"}

    approvals = sorted(set(proposal.get("approvals", []) + [actor.user_id]))
    needed = quorum()
    record = {**proposal, "approvals": approvals, "at": _stamp()}

    if len(approvals) < needed:
        record["status"] = "open"
        _append(PROPOSALS, record)
        return {"approved": False, "pending": True, "approvals": approvals,
                "needed": needed,
                "reason": f"{len(approvals)} of {needed} approvals recorded."}

    if commit:
        Path(proposal["path"]).parent.mkdir(parents=True, exist_ok=True)
        atomic_write(Path(proposal["path"]), proposal["new_content"])
    record["status"] = "committed"
    _append(PROPOSALS, record)

    logged = log_decision(
        tier=TIER_C, summary=f"Amendment committed: {proposal['target']}",
        actor=actor, kind="amendment",
        refs=[proposal["proposal_id"], proposal["target"]],
        detail={"approvals": approvals, "rationale": proposal.get("rationale", "")},
    )
    return {"approved": True, "committed": commit, "approvals": approvals,
            "decision": logged}


# --------------------------------------------------------- minutes & recordings

def add_minutes(*, title: str, body: str, actor: Actor,
                members_present: list[str] | None = None) -> dict[str, Any]:
    guard_result = guard(actor, Target.MINUTES, "add_minutes",
                         detail={"title": title})
    if not guard_result.allowed:
        return {"added": False, "reason": guard_result.reason}
    MINUTES_DIR.mkdir(parents=True, exist_ok=True)
    slug = _now().strftime("%Y-%m-%d") + "-" + \
        "".join(c if c.isalnum() else "-" for c in title.lower())[:40].strip("-")
    path = MINUTES_DIR / f"{slug}.md"
    present = ", ".join(members_present or [actor.user_id])
    atomic_write(path, f"# {title}\n\n**Date:** {_stamp()}  \n"
                       f"**Present:** {present}\n\n{body}\n")
    return {"added": True, "path": str(path.relative_to(COUNCIL_DIR.parent))}


def add_recording(*, title: str, source: Path | str, actor: Actor,
                  duration: str = "") -> dict[str, Any]:
    guard_result = guard(actor, Target.RECORDINGS, "add_recording",
                         detail={"title": title})
    if not guard_result.allowed:
        return {"added": False, "reason": guard_result.reason}
    RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
    manifest = RECORDINGS_DIR / "recordings.jsonl"
    entry = {"at": _stamp(), "title": title, "source": str(source),
             "duration": duration, "by": actor.user_id}
    _append(manifest, entry)
    return {"added": True, **entry}


def minutes() -> list[dict[str, str]]:
    if not MINUTES_DIR.exists():
        return []
    return [{"name": p.stem, "path": str(p.relative_to(COUNCIL_DIR.parent)),
             "preview": p.read_text(encoding="utf-8")[:200]}
            for p in sorted(MINUTES_DIR.glob("*.md"), reverse=True)]


def recordings() -> list[dict[str, Any]]:
    return list(reversed(_read(RECORDINGS_DIR / "recordings.jsonl")))


# --------------------------------------------------- the mode-transition act

def adopt_parameter_set(*, actor: Actor, members_present: list[str],
                        summary: str = "") -> dict[str, Any]:
    """The second adoption: the Council adopts OT's tuned values, guardrails on."""
    from app import config as config_mod
    from app import mode as mode_mod

    guard_result = guard(actor, Target.MODE, "adopt_parameter_set",
                         detail={"members": members_present})
    if not guard_result.allowed:
        return {"adopted": False, "reason": guard_result.reason}

    param_hash = config_mod.parameter_set_hash()
    try:
        record = mode_mod.adopt_operating(
            members=members_present, parameter_set_hash=param_hash,
            summary=summary, quorum=quorum(), actor=actor.user_id,
        )
    except mode_mod.ModeError as exc:
        return {"adopted": False, "reason": str(exc)}

    logged = log_decision(
        tier=TIER_C,
        summary=(summary or "Tuned parameter set adopted; change guardrails "
                            "activated (Operating Mode)."),
        actor=actor, kind="parameter_set_adoption",
        refs=["Appendix B", "Appendix N — Council Operating Procedures"],
        detail={"parameter_set_hash": param_hash,
                "members_present": sorted(set(members_present))},
    )
    return {"adopted": True, "mode": record.mode,
            "parameter_set_hash": param_hash, "decision": logged}
