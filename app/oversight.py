"""Oversight — risk re-scoring, monitoring, and AI incident response.

On standby until something fails. Incidents run Levels 1–3 per the Operations
Manual: suspend, root-cause, lookback, resume. Level 2 and above route to the
Council; Level 3 additionally reaches the executive and General Counsel.

Drift and bias monitoring is deliberately a **register of obligations**, not a
metrics dashboard: no production model telemetry exists yet, and inventing
numbers would be worse than showing what is owed and when.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, asdict, field as dc_field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app import config as config_mod
from app import registry as registry_mod
from app import scoring
from app.audit import CORPUS
from app.authz import Actor, Decision, Target, guard

INCIDENTS = CORPUS / "incidents.jsonl"

LEVEL_RULES = {
    1: {
        "label": "Level 1 — contained",
        "route": "Operational owner resolves; logged to the record.",
        "council": False, "executive": False,
        "citation": "SCDES AI Operations Manual §22.3 (Level 1 Procedure)",
    },
    2: {
        "label": "Level 2 — material",
        "route": ("Operational owner suspends the system immediately. The AI "
                  "Strategist notifies the Council Chair within 24 hours. "
                  "Root-cause analysis and a lookback are required before resume."),
        "council": True, "executive": False,
        "citation": "SCDES AI Operations Manual §22.4 (Level 2 Procedure)",
    },
    3: {
        "label": "Level 3 — severe",
        "route": ("Immediate suspension, executive notification and General "
                  "Counsel involvement, in addition to the Level 2 obligations. "
                  "Delegated federal programme notification may apply."),
        "council": True, "executive": True,
        "citation": ("SCDES AI Operations Manual §22.5 (Level 3 Procedure); "
                     "§22.8 (Delegated Federal Program Notification)"),
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _stamp() -> str:
    return _now().isoformat(timespec="seconds")


@dataclass
class Incident:
    incident_id: str
    registry_id: str
    level: int
    summary: str
    detected_at: str
    reported_by: str
    status: str = "open"                # open | suspended | root_cause | resolved
    system_name: str = ""
    risk_band_at_incident: str = ""
    obligations: list[dict[str, Any]] = dc_field(default_factory=list)
    council_decision_id: str = ""
    lookback_required: bool = False
    resolved_at: str = ""
    notes: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _append(payload: dict[str, Any]) -> None:
    INCIDENTS.parent.mkdir(parents=True, exist_ok=True)
    with INCIDENTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(payload, sort_keys=True, default=str) + "\n")


def _read() -> list[dict[str, Any]]:
    if not INCIDENTS.exists():
        return []
    return [json.loads(line) for line in
            INCIDENTS.read_text(encoding="utf-8").splitlines() if line.strip()]


def incidents(open_only: bool = False) -> list[Incident]:
    latest: dict[str, dict[str, Any]] = {}
    for row in _read():
        latest[row["incident_id"]] = {**latest.get(row["incident_id"], {}), **row}
    rows = [Incident(**r) for r in latest.values()]
    rows.sort(key=lambda i: i.detected_at, reverse=True)
    return [i for i in rows if i.status != "resolved"] if open_only else rows


def _obligations(level: int, project) -> list[dict[str, Any]]:
    rule = LEVEL_RULES[level]
    now = _now()
    items = [{"what": "Log the incident on Appendix L",
              "due": _stamp(), "done": True,
              "citation": "Appendix L — AI Incident Report"}]
    if level >= 2:
        items += [
            {"what": "Suspend the system", "due": _stamp(), "done": False,
             "citation": rule["citation"]},
            {"what": "Notify the Council Chair",
             "due": (now + timedelta(hours=24)).isoformat(timespec="seconds"),
             "done": False, "citation": rule["citation"]},
            {"what": "Root-cause analysis",
             "due": (now + timedelta(days=10)).isoformat(timespec="seconds"),
             "done": False, "citation": "SCDES AI Operations Manual §22.6 (Lookback Protocol)"},
            {"what": "Lookback over decisions made while impaired",
             "due": (now + timedelta(days=10)).isoformat(timespec="seconds"),
             "done": False, "citation": "SCDES AI Operations Manual §22.6 (Lookback Protocol)"},
            {"what": "Reassess risk classification (Appendix B)",
             "due": (now + timedelta(days=10)).isoformat(timespec="seconds"),
             "done": False, "citation": "Appendix B — AI Risk Classification Matrix"},
        ]
    if level >= 3:
        items += [
            {"what": "Notify the executive and General Counsel",
             "due": (now + timedelta(hours=24)).isoformat(timespec="seconds"),
             "done": False, "citation": rule["citation"]},
            {"what": "Assess delegated federal programme notification",
             "due": (now + timedelta(hours=72)).isoformat(timespec="seconds"),
             "done": False,
             "citation": "SCDES AI Operations Manual §22.8"},
        ]
    return items


def report_incident(*, registry_id: str, level: int, summary: str,
                    actor: Actor, notes: str = "") -> dict[str, Any]:
    """Record an incident and run the routing the Manual requires."""
    if level not in LEVEL_RULES:
        raise ValueError(f"incident level must be 1, 2 or 3 — got {level!r}")

    project = registry_mod.load(registry_id)
    decision = guard(
        actor, Target.REGISTRY, f"report_incident_level_{level}",
        owners=project.owners if project else None,
        detail={"registry_id": registry_id, "level": level,
                "summary": summary[:120]},
    )
    if not decision.allowed:
        return {"recorded": False, "reason": decision.reason}

    rule = LEVEL_RULES[level]
    risk = project.risk() if project else None
    incident = Incident(
        incident_id=f"INC-{uuid.uuid4().hex[:6].upper()}",
        registry_id=registry_id, level=level, summary=summary,
        detected_at=_stamp(), reported_by=actor.user_id,
        status="suspended" if level >= 2 else "open",
        system_name=project.name if project else registry_id,
        risk_band_at_incident=risk.band if risk else "",
        obligations=_obligations(level, project),
        lookback_required=level >= 2, notes=notes,
    )

    result: dict[str, Any] = {"recorded": True, "incident": incident.as_dict(),
                              "route": rule["route"], "citation": rule["citation"]}

    if level >= 2 and project is not None:
        from app import council as council_mod
        logged = council_mod.log_decision(
            tier=council_mod.TIER_C if level == 3 else council_mod.TIER_B,
            summary=f"{rule['label']}: {summary}",
            actor=Actor(actor.user_id, actor.name, actor.role)
            if actor.role.value == "council-member" else _strategist(actor),
            kind="incident", refs=[incident.incident_id, registry_id],
            detail={"level": level, "obligations": len(incident.obligations)},
        )
        if logged.get("logged"):
            incident.council_decision_id = logged["decision_id"]
            result["council_decision"] = logged["decision_id"]
        else:
            result["council_note"] = logged.get("reason", "")

        # The Manual requires suspension at Level 2+, which is an operational
        # stage change on the Registry — recorded like any other.
        registry_mod.advance_stage(
            registry_id, actor, stage="suspended",
            note=f"Suspended on {incident.incident_id} ({rule['label']})")
        result["suspended"] = True

    _append(incident.as_dict())
    return result


def _strategist(actor: Actor) -> Actor:
    """Incident escalation is filed by the AI Strategist on the Council's behalf."""
    from app.authz import Role
    return Actor("council.strategist", "AI Strategist (on behalf of the Council)",
                 Role.COUNCIL)


def resolve_incident(incident_id: str, actor: Actor, *,
                     resume: bool = False, note: str = "") -> dict[str, Any]:
    incident = next((i for i in incidents() if i.incident_id == incident_id), None)
    if incident is None:
        return {"resolved": False, "reason": f"unknown incident {incident_id}"}

    decision = guard(actor, Target.REGISTRY, "resolve_incident",
                     detail={"incident_id": incident_id, "resume": resume})
    if not decision.allowed:
        return {"resolved": False, "reason": decision.reason}

    incident.status = "resolved"
    incident.resolved_at = _stamp()
    incident.notes = (incident.notes + " " + note).strip()
    _append(incident.as_dict())

    if resume:
        registry_mod.advance_stage(
            incident.registry_id, actor, stage="pilot",
            note=f"Resumed after {incident_id}")
    return {"resolved": True, "incident": incident.as_dict(), "resumed": resume}


# ------------------------------------------------------------- monitoring view

def monitoring_register() -> list[dict[str, Any]]:
    """What each production/pilot system owes, and when — not invented metrics."""
    rows = []
    for project in registry_mod.load_all():
        if project.stage not in ("pilot", "production"):
            continue
        risk = project.risk()
        cadence = scoring.review_cadence(risk.band)
        rows.append({
            "registry_id": project.registry_id, "name": project.name,
            "stage": project.stage, "risk": risk.band, "cadence": cadence,
            "bias_testing_required": project.category >= 2,
            "drift_monitoring_required": True,
            "next_gate": 5 if project.stage == "production" else project.gate + 1,
            "obligations": [
                {"what": f"{cadence} risk reassessment",
                 "citation": "SCDES AI Operations Manual §6.3 (Reassessment Cadence)"},
                {"what": "Model drift monitoring",
                 "citation": "SCDES AI Operations Manual §6.5 (Model Drift Monitoring)"},
                *([{"what": "Ongoing bias monitoring",
                    "citation": "SCDES AI Operations Manual §11.6 (Ongoing Monitoring)"}]
                  if project.category >= 2 else []),
            ],
            "evidence": "No production telemetry connected yet — this is the "
                        "register of what is owed, not a measurement.",
        })
    return rows


def rescore(registry_id: str) -> dict[str, Any]:
    """Re-run the risk model against the live config — pure, changes nothing."""
    project = registry_mod.load(registry_id)
    if project is None:
        raise KeyError(registry_id)
    risk = project.risk()
    return {
        "registry_id": registry_id, "band": risk.band, "composite": risk.total,
        "explanation": risk.explanation,
        "council_required": risk.council_required,
        "cadence": scoring.review_cadence(risk.band),
        "required_appendices": sorted(risk.required_appendices),
    }


def status() -> dict[str, Any]:
    open_incidents = incidents(open_only=True)
    return {
        "active_incidents": len(open_incidents),
        "highest_level": max((i.level for i in open_incidents), default=0),
        "standby": not open_incidents,
        "monitored_systems": len(monitoring_register()),
        "incidents": [i.as_dict() for i in open_incidents],
    }
