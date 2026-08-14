"""Appendix C — the AI System Registry, as a living portfolio.

Every AI system is a tracked project: stage, gate, owners, risk factors, review
schedule. Writes are operational and owner-scoped; they pass the guard and land
in the audit chain.

The pipeline is seeded from the agency's own instruments — the 24 classified use
cases in Appendix A, plus the PermitPro permitting analysis as the flagship.
Per-factor scores are **derived** from Appendix A's own columns using the stated
heuristics below, because Appendix A records a *typical* risk classification
rather than the six factor ratings. Derived scores are marked as such and are a
starting point for the operator to confirm at Gate 0 — exactly what Appendix A
says its risk column is for.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict, field as dc_field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.audit import CORPUS, atomic_write
from app.authz import Actor, Decision, Target, guard
from app.ingest_xlsx import APPENDIX_DIR, parse_appendix

REGISTRY_DIR = CORPUS / "registry"

STAGES = ("concept", "pilot", "production", "suspended", "retired")
GATE_NAMES = {
    0: "Concept Approval", 1: "Readiness Confirmation", 2: "Pilot Authorization",
    3: "Operational Deployment", 4: "Scaling Approval",
    5: "Annual Continuous Operations Review",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Project:
    registry_id: str
    name: str
    description: str = ""
    category: int = 1
    bureau: str = ""
    domain: str = ""
    stage: str = "concept"
    gate: int = 0
    operational_owner: str = ""
    technical_owner: str = ""
    data_owner: str = ""
    owners: list[str] = dc_field(default_factory=list)
    factor_scores: dict[str, int] = dc_field(default_factory=dict)
    scores_are_derived: bool = False
    typical_classification: str = ""
    data_sources: str = ""
    federal_nexus: str = ""
    regulatory_constraints: str = ""
    vendor: str = ""
    annual_cost: float = 0.0
    capabilities_required: list[str] = dc_field(default_factory=list)
    seeded_from: str = ""
    created_at: str = dc_field(default_factory=_now)
    updated_at: str = dc_field(default_factory=_now)
    gate_history: list[dict[str, Any]] = dc_field(default_factory=list)
    appendix_instances: dict[str, str] = dc_field(default_factory=dict)
    notes: str = ""

    @property
    def gate_label(self) -> str:
        return f"Gate {self.gate} — {GATE_NAMES.get(self.gate, '')}"

    @property
    def path(self) -> Path:
        return REGISTRY_DIR / self.registry_id

    def risk(self, model: dict[str, Any] | None = None):
        from app import config as config_mod
        from app import scoring
        return scoring.classify(self.factor_scores, model or config_mod.risk_model())

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ------------------------------------------------------------------ persistence

def save(project: Project) -> Path:
    project.updated_at = _now()
    project.path.mkdir(parents=True, exist_ok=True)
    target = project.path / "project.json"
    atomic_write(target, json.dumps(project.as_dict(), indent=2) + "\n")
    return target


def load(registry_id: str) -> Project | None:
    path = REGISTRY_DIR / registry_id / "project.json"
    if not path.exists():
        return None
    return Project(**json.loads(path.read_text(encoding="utf-8")))


def load_all() -> list[Project]:
    if not REGISTRY_DIR.exists():
        return []
    projects = []
    for child in sorted(REGISTRY_DIR.iterdir()):
        candidate = child / "project.json"
        if candidate.exists():
            projects.append(Project(**json.loads(candidate.read_text(encoding="utf-8"))))
    return projects


def next_registry_id() -> str:
    existing = [p.registry_id for p in load_all()]
    numbers = [int(m.group(1)) for p in existing
               if (m := re.match(r"AI-(\d+)$", p))]
    return f"AI-{max(numbers, default=0) + 1:03d}"


# ------------------------------------------------------------- governed writes

def create(project: Project, actor: Actor) -> tuple[Decision, Project | None]:
    decision = guard(actor, Target.REGISTRY, "create_project",
                     owners=project.owners,
                     detail={"registry_id": project.registry_id,
                             "name": project.name})
    if not decision.allowed:
        return decision, None
    save(project)
    return decision, project


def advance_stage(registry_id: str, actor: Actor, *, stage: str | None = None,
                  gate: int | None = None,
                  note: str = "") -> tuple[Decision, Project | None]:
    project = load(registry_id)
    if project is None:
        raise KeyError(registry_id)

    decision = guard(
        actor, Target.REGISTRY, "advance_stage", owners=project.owners,
        detail={"registry_id": registry_id, "from_gate": project.gate,
                "to_gate": gate, "from_stage": project.stage,
                "to_stage": stage, "note": note},
    )
    if not decision.allowed:
        return decision, project

    entry = {"at": _now(), "by": actor.user_id,
             "from_gate": project.gate, "from_stage": project.stage}
    if gate is not None:
        project.gate = gate
    if stage is not None:
        if stage not in STAGES:
            raise ValueError(f"unknown stage {stage!r}")
        project.stage = stage
    entry.update({"to_gate": project.gate, "to_stage": project.stage,
                  "note": note})
    project.gate_history.append(entry)
    save(project)
    return decision, project


def set_factor_scores(registry_id: str, scores: dict[str, int],
                      actor: Actor) -> tuple[Decision, Project | None]:
    project = load(registry_id)
    if project is None:
        raise KeyError(registry_id)
    before = project.risk()
    decision = guard(
        actor, Target.REGISTRY, "set_factor_scores", owners=project.owners,
        detail={"registry_id": registry_id, "scores": scores,
                "band_before": before.band},
    )
    if not decision.allowed:
        return decision, project
    project.factor_scores.update({k: int(v) for k, v in scores.items()})
    project.scores_are_derived = False
    save(project)
    return decision, project


# ---------------------------------------------------------------- portfolio view

def portfolio_summary(projects: Iterable[Project] | None = None) -> dict[str, Any]:
    from app import scoring
    projects = list(projects) if projects is not None else load_all()
    bands: dict[str, int] = {b: 0 for b in scoring.BANDS}
    stages: dict[str, int] = {s: 0 for s in STAGES}
    categories: dict[int, int] = {1: 0, 2: 0, 3: 0}
    for p in projects:
        bands[p.risk().band] = bands.get(p.risk().band, 0) + 1
        stages[p.stage] = stages.get(p.stage, 0) + 1
        categories[p.category] = categories.get(p.category, 0) + 1
    return {
        "count": len(projects), "bands": bands, "stages": stages,
        "categories": categories,
        "council_gated": sum(1 for p in projects if p.risk().council_required),
    }


# --------------------------------------------------------------------- seeding
#
# Heuristics that turn Appendix A's descriptive columns into the six Appendix B
# factor ratings. Each rule is stated so an operator can see why a starting score
# was proposed and correct it at Gate 0.

_DELEGATED = re.compile(
    r"NPDES|RCRA|CAA|Title V|CERCLA|ESA|CWA|EPCRA|Beaches Act|303\(d\)|404", re.I)
# Appendix B level 3 is "PII, enforcement data, or legally protected data" —
# permit and monitoring records are level 2 "internal operational data".
_SENSITIVE = re.compile(r"PII|personal|demographic|personnel|protected", re.I)
_PUBLIC_FACING = re.compile(
    r"public (notification|advisory|water quality|health|service)|"
    r"fence-line|public-facing|for public", re.I)
_IRREVERSIBLE = re.compile(
    r"real-time|emergency|spill trajectory|command authority|public safety|"
    r"time-critical", re.I)
# Text that explicitly keeps a human in the loop caps Regulatory Impact — these
# are constraints *forbidding* a determination, not evidence of one.
_HUMAN_IN_LOOP = re.compile(
    r"cannot (replace|constitute|be)|not (a )?substitute|advisory only|"
    r"human final determination|human review|pre-?screening only|"
    r"prioriti[sz]ation tool only|supports (targeting|inspection)|"
    r"must be verified", re.I)
_DETERMINATIVE = re.compile(
    r"permit decision|final determination|enforcement action|automatic(ally)? (deny|approve|issue)",
    re.I)


def derive_factor_scores(row: dict[str, str]) -> tuple[dict[str, int], list[str]]:
    """Propose the six factor ratings from an Appendix A taxonomy row."""
    application = row.get("Specific Application", "")
    use_case = row.get("Use Case Category", "")
    constraints = row.get("Regulatory Constraints", "")
    sources = row.get("Data Sources", "")
    nexus = row.get("Federal Program Nexus", "")
    category = str(row.get("Category (1/2/3)", "1")).strip()
    blob = f"{application} {use_case} {constraints}"

    why: list[str] = []
    human_in_loop = bool(_HUMAN_IN_LOOP.search(constraints))

    # Regulatory Impact — 3 only where the output *is* a regulatory outcome.
    if _DETERMINATIVE.search(blob) and not human_in_loop:
        regulatory = 3
    elif re.search(r"permit|compliance|enforcement|regulat|inspection", blob, re.I):
        regulatory = 2
    else:
        regulatory = 1
    why.append(
        f"Regulatory Impact {regulatory} — '{use_case}'"
        + ("; constraints keep a human in the loop, so this influences "
           "operations rather than deciding outcomes." if human_in_loop else ".")
    )

    # Public-Facing Exposure
    if _PUBLIC_FACING.search(blob):
        public_facing = 3
    elif category == "2":
        public_facing = 2
    elif category == "3":
        public_facing = 2
    else:
        public_facing = 1
    why.append(f"Public-Facing Exposure {public_facing} — Category {category}.")

    # Data Sensitivity — permit/monitoring records are operational, not protected.
    if _SENSITIVE.search(f"{sources} {blob}"):
        sensitivity = 3
    elif sources.strip():
        sensitivity = 2
    else:
        sensitivity = 1
    why.append(f"Data Sensitivity {sensitivity} — sources: {sources[:60] or 'unstated'}.")

    # Reversibility — 3 means hard to reverse.
    if _IRREVERSIBLE.search(blob):
        reversibility = 3
    elif human_in_loop:
        reversibility = 1
    else:
        reversibility = 2
    why.append(
        f"Reversibility {reversibility} — "
        + ("time-critical or safety-critical." if reversibility == 3
           else "a human decision sits between output and effect."
           if reversibility == 1 else "reversible with moderate effort.")
    )

    # Community Impact
    if re.search(r"demographic|Title VI|fence-line|disproportionate|"
                 r"overburdened|environmental justice", f"{sources} {blob}", re.I):
        community = 3
    elif _PUBLIC_FACING.search(blob):
        community = 2
    else:
        community = 1
    why.append(f"Community Impact {community}.")

    # Federal Program Nexus
    if _DELEGATED.search(nexus):
        federal = 3
    elif nexus.strip() and nexus.strip().lower() not in ("none", "multiple"):
        federal = 2
    elif nexus.strip().lower() == "multiple":
        federal = 2
    else:
        federal = 1
    why.append(f"Federal Program Nexus {federal} — '{nexus or 'none'}'.")

    return ({
        "regulatory_impact": regulatory,
        "public_facing_exposure": public_facing,
        "data_sensitivity": sensitivity,
        "reversibility": reversibility,
        "community_impact": community,
        "federal_program_nexus": federal,
    }, why)


_BUREAU_BY_DOMAIN = {
    "Water Quality": "Water",
    "Air Quality": "Air",
    "Waste Management": "Land and Waste",
    "Land & Natural Resources": "Land and Waste",
    "Emergency Response": "Operations and Services",
    "Agency Operations": "Operations and Services",
    "Innovation": "Operations and Services",
}


def taxonomy_rows() -> list[dict[str, str]]:
    schema = parse_appendix(APPENDIX_DIR / "Appendix_A_Use_Case_Taxonomy.xlsx")
    for sheet in schema.sheets:
        if sheet.name.lower().startswith("use case"):
            for block in sheet.blocks:
                if block.kind == "record_table" and "ID" in block.columns:
                    return [r for r in block.sample_rows if r.get("ID")]
    return []


PERMITPRO = Project(
    registry_id="AI-001",
    name="PermitPro — Permitting Analysis & Triage",
    description=(
        "Risk-based triage of the permitting backlog. Ranks permit actions by "
        "volume, statutory-clock exposure and processing latency so reviewers "
        "work the highest-consequence queue first. Seeded from the SCDES "
        "permitting unified model (235,009 completed submission records, "
        "4/2022–4/2026)."
    ),
    category=2, bureau="Water", domain="Water Quality",
    stage="pilot", gate=2,
    operational_owner="Bureau of Water — Permitting",
    technical_owner="Office of Technology",
    data_owner="Bureau of Water",
    owners=["liz.operator", "sean.ot"],
    factor_scores={
        "regulatory_impact": 3,        # ranks actions against statutory clocks
        "public_facing_exposure": 2,   # affects regulated parties, not the public directly
        "data_sensitivity": 2,         # permit + submission records, no PII
        "reversibility": 2,            # triage order is revisable
        "community_impact": 2,         # uneven queueing could fall unevenly
        "federal_program_nexus": 3,    # CWA / NPDES delegated program
    },
    typical_classification="Moderate",
    data_sources="Submission records, backlog snapshots, permit-type catalogue, statutory-deadline flags",
    federal_nexus="CWA / NPDES",
    regulatory_constraints=(
        "Advisory triage only; must not constitute a permit decision. "
        "Processing-time data is right-censored (completed-only) — the backlog "
        "is invisible to the speed data, so ranking on it under-prioritises "
        "stuck cases."
    ),
    capabilities_required=["data_governance", "mcp_api_access"],
    seeded_from="05_WORKED_EXAMPLE_SCDES_PermitPro / SCDES_Permitting_Unified_Model.xlsx",
    notes=(
        "Data Quality Log records 3 CRITICAL findings: right-censored processing "
        "time, backlog invisible to the speed data, and 8.5% exact duplicate rows. "
        "Gate 1 data readiness must clear these before pilot results are trusted."
    ),
)


def seed(actor: Actor, *, limit: int | None = None,
         include_taxonomy: bool = True) -> dict[str, Any]:
    """Populate the registry from Appendix A and the PermitPro worked example."""
    created: list[Project] = []
    skipped: list[str] = []

    if load(PERMITPRO.registry_id) is None:
        decision, project = create(PERMITPRO, actor)
        if project:
            created.append(project)
    else:
        skipped.append(PERMITPRO.registry_id)

    if include_taxonomy:
        rows = taxonomy_rows()
        if limit:
            rows = rows[:limit]
        for n, row in enumerate(rows, start=2):
            registry_id = f"AI-{n:03d}"
            if load(registry_id) is not None:
                skipped.append(registry_id)
                continue
            scores, why = derive_factor_scores(row)
            try:
                category = int(str(row.get("Category (1/2/3)", "1")).strip() or 1)
            except ValueError:
                category = 1
            domain = row.get("Environmental Domain", "")
            project = Project(
                registry_id=registry_id,
                name=f"{row.get('ID', '')} · {row.get('Use Case Category', '')}".strip(" ·"),
                description=row.get("Specific Application", ""),
                category=category, domain=domain,
                bureau=_BUREAU_BY_DOMAIN.get(domain, "Operations and Services"),
                stage="concept", gate=0,
                owners=["liz.operator"],
                factor_scores=scores, scores_are_derived=True,
                typical_classification=row.get("Typical Risk Classification", ""),
                data_sources=row.get("Data Sources", ""),
                federal_nexus=row.get("Federal Program Nexus", ""),
                regulatory_constraints=row.get("Regulatory Constraints", ""),
                seeded_from="Appendix A — Use Case Taxonomy",
                notes="Derived starting scores: " + " ".join(why),
            )
            decision, made = create(project, actor)
            if made:
                created.append(made)

    return {"created": [p.registry_id for p in created], "skipped": skipped,
            "count": len(created)}


def calibration_report(projects: Iterable[Project] | None = None) -> dict[str, Any]:
    """How often derived factor scores reproduce Appendix A's typical band.

    Appendix A calls its risk column "starting guidance only", so disagreement
    is expected and informative — it marks the projects most worth confirming.
    """
    projects = [p for p in (projects if projects is not None else load_all())
                if p.typical_classification]
    agree, rows = 0, []
    for p in projects:
        derived = p.risk().band
        expected = p.typical_classification.strip().title()
        match = derived == expected
        agree += match
        rows.append({"registry_id": p.registry_id, "name": p.name,
                     "expected": expected, "derived": derived, "match": match})
    return {
        "compared": len(projects), "agreed": agree,
        "rate": round(100 * agree / len(projects), 1) if projects else 0.0,
        "rows": rows,
    }
