"""Vision → funded roadmap, and the line-of-sight view over it.

The interesting question is not "can we afford this project" but "what has to
exist first". Foundations are modeled as a **capability dependency graph**:
projects declare the capabilities they need, foundations declare the ones they
provide, and the app computes the unmet set, orders it, and costs it against the
budget pools.

The app derives the *sequence and the cost*; the dependencies themselves are
OT's to author, because the documents do not state them. Pretending to mine them
out of the corpus would be fabrication.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable

import yaml

from app import config as config_mod
from app import registry as registry_mod
from app import scoring
from app.audit import atomic_write

DEFAULT_VISION = {
    "citation": ("SCDES AI Governance Framework §4 (Measurable Value); "
                 "SCDES AI Operations Manual §20 (Portfolio Management)"),
    "statement": (
        "Every program uses AI it can trust — to cut permit backlog, target "
        "inspections by risk, and answer the public faster — without a person "
        "ever losing the final call."
    ),
    "pillars": {
        "Protect": "Protect public health and the environment through faster, "
                   "better-targeted regulatory work.",
        "Promote": "Promote economic activity by making permitting predictable "
                   "and timely.",
        "Pursue": "Pursue capability the agency does not yet have, sequenced "
                  "behind the foundations that make it safe.",
    },
    "category_progression": (
        "Category 1 builds internal competence, Category 2 extends it to public "
        "and economic benefit, Category 3 pursues new capability. The portfolio "
        "climbs in that order."
    ),
}

DEFAULT_CAPABILITIES = {
    "citation": "SCDES AI Operations Manual §8 (Data Governance), §20 (Portfolio Management)",
    "foundations": [
        {
            "key": "data_governance",
            "label": "Data governance stood up",
            "provides": ["data_governance"],
            "requires": [],
            "one_time": 180_000, "recurring": 40_000,
            "status": "in_progress",
            "why": "Prerequisite for every Category 2 or 3 project: named data "
                   "owners, classification, retention and lineage.",
            "appendix": "Appendix D — Data Readiness Assessment",
        },
        {
            "key": "mcp_api_access",
            "label": "Siloed files made API-accessible and meta-tagged",
            "provides": ["mcp_api_access", "retrieval"],
            "requires": ["data_governance"],
            "one_time": 420_000, "recurring": 60_000,
            "status": "not_started",
            "why": "Unlocks retrieval for the permit assistant and inspection "
                   "targeting; without it every project rebuilds its own access.",
            "appendix": "Appendix D — Data Readiness Assessment",
        },
        {
            "key": "identity_access",
            "label": "Identity and access baseline",
            "provides": ["identity_access"],
            "requires": [],
            "one_time": 90_000, "recurring": 25_000,
            "status": "not_started",
            "why": "SSO and role assignment for the governance app itself and "
                   "for any system that writes to the Registry.",
            "appendix": "Appendix C — AI System Registry",
        },
        {
            "key": "evaluation_harness",
            "label": "Evaluation harness and stopping rules",
            "provides": ["evaluation_harness"],
            "requires": ["data_governance"],
            "one_time": 140_000, "recurring": 30_000,
            "status": "not_started",
            "why": "Gate 2 cannot be evidenced without a repeatable evaluation "
                   "and an agreed stopping rule.",
            "appendix": "Appendix J — Evaluation Methodology",
        },
        {
            "key": "data_readiness_baseline",
            "label": "Data readiness baseline across bureaux",
            "provides": ["data_readiness_baseline"],
            "requires": ["data_governance"],
            "one_time": 75_000, "recurring": 0,
            "status": "not_started",
            "why": "Establishes which programs can support AI at all, so the "
                   "roadmap is sequenced on evidence rather than appetite.",
            "appendix": "Appendix D — Data Readiness Assessment",
        },
    ],
    "desired_projects": [
        {"name": "PermitPro — Stormwater", "registry_id": "AI-001",
         "requires": ["data_governance"], "one_time": 0, "recurring": 1_500_000},
        {"name": "Risk-based inspection targeting", "registry_id": "",
         "requires": ["data_governance", "mcp_api_access"],
         "one_time": 610_000, "recurring": 120_000},
        {"name": "Public permit assistant", "registry_id": "",
         "requires": ["mcp_api_access", "identity_access"],
         "one_time": 300_000, "recurring": 120_000},
    ],
}


def ensure_defaults() -> None:
    if not config_mod.VISION.exists():
        atomic_write(config_mod.VISION, yaml.safe_dump(DEFAULT_VISION, sort_keys=False))
    if not config_mod.CAPABILITIES.exists():
        atomic_write(config_mod.CAPABILITIES,
                     yaml.safe_dump(DEFAULT_CAPABILITIES, sort_keys=False))
    config_mod.invalidate()


def vision() -> dict[str, Any]:
    ensure_defaults()
    return config_mod.load("vision", refresh=True)


def capabilities() -> dict[str, Any]:
    ensure_defaults()
    return config_mod.load("capabilities", refresh=True)


# --------------------------------------------------------------- gap analysis

@dataclass
class Step:
    key: str
    label: str
    kind: str                      # "foundation" | "project"
    status: str = "not_started"
    one_time: float = 0.0
    recurring: float = 0.0
    requires: list[str] = dc_field(default_factory=list)
    unlocks: list[str] = dc_field(default_factory=list)
    why: str = ""
    appendix: str = ""
    wave: int = 0

    @property
    def total_first_year(self) -> float:
        return self.one_time + self.recurring

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "kind": self.kind,
            "status": self.status, "one_time": self.one_time,
            "recurring": self.recurring, "requires": self.requires,
            "unlocks": self.unlocks, "why": self.why, "appendix": self.appendix,
            "wave": self.wave, "total_first_year": self.total_first_year,
        }


def _sequence(foundations: list[dict[str, Any]]) -> list[Step]:
    """Order foundations so nothing is scheduled before what it depends on."""
    provided_by = {}
    for f in foundations:
        for capability in f.get("provides", [f["key"]]):
            provided_by[capability] = f["key"]

    steps = {
        f["key"]: Step(
            key=f["key"], label=f["label"], kind="foundation",
            status=f.get("status", "not_started"),
            one_time=float(f.get("one_time", 0)),
            recurring=float(f.get("recurring", 0)),
            requires=list(f.get("requires", [])),
            why=f.get("why", ""), appendix=f.get("appendix", ""),
        )
        for f in foundations
    }

    resolved: list[Step] = []
    remaining = dict(steps)
    wave = 1
    while remaining:
        ready = [
            s for s in remaining.values()
            if all(provided_by.get(dep, dep) not in remaining for dep in s.requires)
        ]
        if not ready:                      # a cycle — surface it rather than hang
            for s in remaining.values():
                s.wave = wave
                s.why += " (dependency cycle — OT must break this in Configure)"
                resolved.append(s)
            break
        for s in sorted(ready, key=lambda s: s.key):
            s.wave = wave
            resolved.append(s)
            del remaining[s.key]
        wave += 1
    return resolved


def gap_analysis() -> dict[str, Any]:
    """Everything that has to happen, in order, costed against the pools."""
    cfg = capabilities()
    budget_cfg = config_mod.load("budget")
    pools = budget_cfg.get("pools", {})

    foundations = _sequence(cfg.get("foundations", []))
    provided_by = {}
    for f in cfg.get("foundations", []):
        for capability in f.get("provides", [f["key"]]):
            provided_by[capability] = f["key"]

    # What each foundation unlocks, for the "why does this come first" line.
    wanted = cfg.get("desired_projects", [])
    for step in foundations:
        provides = set(next((f.get("provides", [f["key"]])
                             for f in cfg["foundations"] if f["key"] == step.key), []))
        step.unlocks = sorted({
            p["name"] for p in wanted
            if provides & set(p.get("requires", []))
        })

    done = {f.key for f in foundations if f.status == "complete"}
    project_steps: list[Step] = []
    max_wave = max((f.wave for f in foundations), default=0)
    for p in wanted:
        blockers = [
            provided_by.get(dep, dep) for dep in p.get("requires", [])
            if provided_by.get(dep, dep) not in done
        ]
        wave = max(
            [next((f.wave for f in foundations if f.key == b), 0) for b in blockers] + [0]
        ) + 1
        project_steps.append(Step(
            key=p.get("registry_id") or p["name"], label=p["name"], kind="project",
            status="blocked" if blockers else "ready",
            one_time=float(p.get("one_time", 0)),
            recurring=float(p.get("recurring", 0)),
            requires=list(p.get("requires", [])),
            why=("Needs: " + ", ".join(
                next((f.label for f in foundations if f.key == b), b)
                for b in blockers)) if blockers else "No unmet prerequisites.",
            wave=max(wave, 2),
        ))

    all_steps = foundations + project_steps
    foundation_one_time = sum(s.one_time for s in foundations)
    foundation_recurring = sum(s.recurring for s in foundations)
    project_one_time = sum(s.one_time for s in project_steps)
    project_recurring = sum(s.recurring for s in project_steps)

    return {
        "citation": cfg.get("citation", ""),
        "foundations": [s.as_dict() for s in foundations],
        "projects": [s.as_dict() for s in project_steps],
        "waves": sorted({s.wave for s in all_steps}),
        "totals": {
            "foundations_one_time": foundation_one_time,
            "foundations_recurring": foundation_recurring,
            "projects_one_time": project_one_time,
            "projects_recurring": project_recurring,
            "one_time": foundation_one_time + project_one_time,
            "recurring": foundation_recurring + project_recurring,
        },
        "pools": pools,
        "fits": {
            "one_time": (foundation_one_time + project_one_time)
            <= float(pools.get("one_time", 0)),
            "recurring": (foundation_recurring + project_recurring)
            <= float(pools.get("recurring_per_year", 0)),
        },
        "narrative": _roadmap_narrative(
            foundations, project_steps, pools,
            foundation_one_time + project_one_time,
            foundation_recurring + project_recurring),
    }


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _roadmap_narrative(foundations, projects, pools, one_time, recurring) -> str:
    blocked = [p for p in projects if p.status == "blocked"]
    first = [f for f in foundations if f.wave == 1 and f.status != "complete"]
    parts = [
        f"{len(foundations)} enabling foundations and {len(projects)} projects, "
        f"{_money(one_time)} one-time and {_money(recurring)}/yr recurring."
    ]
    if first:
        parts.append("Nothing else starts until " +
                     ", ".join(f.label for f in first[:2]) + " land.")
    if blocked:
        parts.append(f"{len(blocked)} of the {len(projects)} projects are blocked "
                     f"on a foundation that does not exist yet.")
    rec_pool = float(pools.get("recurring_per_year", 0))
    ot_pool = float(pools.get("one_time", 0))
    if recurring > rec_pool:
        parts.append(f"Recurring need exceeds the pool by "
                     f"{_money(recurring - rec_pool)}/yr.")
    if one_time > ot_pool:
        parts.append(f"One-time need exceeds the pool by {_money(one_time - ot_pool)}.")
    return " ".join(parts)


# --------------------------------------------------------------- the home view

def overview() -> dict[str, Any]:
    """Vision, whole-of-process, and each project's contribution to it."""
    v = vision()
    roadmap = gap_analysis()
    projects = registry_mod.load_all()
    summary = registry_mod.portfolio_summary(projects)

    by_category: dict[int, dict[str, Any]] = {}
    for n in (1, 2, 3):
        members = [p for p in projects if p.category == n]
        delivered = [p for p in members if p.stage == "production"]
        in_flight = [p for p in members if p.stage in ("pilot",)]
        by_category[n] = {
            "count": len(members), "delivered": len(delivered),
            "in_flight": len(in_flight),
            "concept": len([p for p in members if p.stage == "concept"]),
            "maturity": round(100 * len(delivered) / len(members), 1) if members else 0.0,
        }

    per_project = []
    for p in sorted(projects, key=lambda p: (-p.gate, p.registry_id)):
        risk = p.risk()
        completed = [h for h in p.gate_history if h.get("to_gate") is not None]
        per_project.append({
            "registry_id": p.registry_id, "name": p.name,
            "category": p.category, "stage": p.stage, "gate": p.gate,
            "gate_name": registry_mod.GATE_NAMES.get(p.gate, ""),
            "risk": risk.band, "composite": risk.total,
            "gates_completed": len(completed),
            "contribution": _contribution(p, risk),
            "pillar": _pillar_for(p),
        })

    gaps = []
    if by_category[1]["delivered"] == 0:
        gaps.append("No Category 1 system has reached production, so the "
                    "capacity ladder has not started climbing.")
    blocked = [s for s in roadmap["projects"] if s["status"] == "blocked"]
    if blocked:
        gaps.append(f"{len(blocked)} roadmap projects are blocked on foundations "
                    f"that are not funded or not started.")
    if summary["bands"].get("High", 0) > summary["count"] / 3:
        from app import decider
        gaps.append(f"{summary['bands']['High']} of {summary['count']} pipeline "
                    f"projects classify High risk, which concentrates the load "
                    f"on {decider.body()}.")

    return {
        "vision": v.get("statement", ""),
        "pillars": v.get("pillars", {}),
        "category_progression": v.get("category_progression", ""),
        "citation": v.get("citation", ""),
        "portfolio": summary,
        "category_maturity": by_category,
        "roadmap": roadmap,
        "per_project": per_project,
        "gaps": gaps,
    }


def _pillar_for(project: registry_mod.Project) -> str:
    if project.category == 3:
        return "Pursue"
    if project.category == 2:
        return "Promote"
    return "Protect"


def _oversight_by(risk: scoring.RiskResult) -> str:
    """Who watches this one — the agency's own decider, or its bureau."""
    if not risk.council_required:
        return "bureau oversight"
    from app import decider
    return f"oversight by {decider.body()}"


def _contribution(project: registry_mod.Project, risk: scoring.RiskResult) -> str:
    stage_text = {
        "concept": "not yet contributing — at concept",
        "pilot": "proving the capability in a bounded pilot",
        "production": "delivering against the vision now",
        "suspended": "suspended pending incident resolution",
        "retired": "retired; capability absorbed or discontinued",
    }.get(project.stage, project.stage)
    return (f"Category {project.category} · {stage_text}. "
            f"Each cleared gate moves it from intent to evidenced capability; "
            f"at {risk.band} risk it carries "
            f"{_oversight_by(risk)}.")
