"""OT's operational configuration — the tunable model behind every surface.

The Council adopted the appendices as templates. The *values* in them are OT's
to set, and this module is where they live. Every key is:

  editable      through guard(), so mode and role are checked and it is audited
  explainable   it states what it governs and cites the instrument it implements
  consequential consequence_preview() shows what a change does to the live
                pipeline *before* it is saved

Bootstrapped from the adopted workbooks: the six risk weights and the three
classification bands are read out of Appendix B, not written here.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Iterable

import yaml

from app.audit import CORPUS, atomic_write, snapshot
from app.authz import Actor, Decision, Target, guard
from app.ingest_xlsx import APPENDIX_DIR, parse_appendix

CONFIG_DIR = CORPUS / "config"
RISK_MODEL = CONFIG_DIR / "risk_model.yaml"
BUDGET = CONFIG_DIR / "budget.yaml"
PROCUREMENT = CONFIG_DIR / "procurement.yaml"
CATEGORIES = CONFIG_DIR / "categories.yaml"
VISION = CONFIG_DIR / "vision.yaml"
CAPABILITIES = CONFIG_DIR / "capabilities.yaml"

FILES = {
    "risk_model": RISK_MODEL,
    "budget": BUDGET,
    "procurement": PROCUREMENT,
    "categories": CATEGORIES,
    "vision": VISION,
    "capabilities": CAPABILITIES,
}

APPENDIX_B_CITATION = (
    "Appendix B — AI Risk Classification Matrix; "
    "SCDES AI Operations Manual §6 (Risk Classification Procedure)"
)


# --------------------------------------------------------------- bootstrapping

def _slug(label: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in label.lower()).strip("_")


def derive_risk_model_from_appendix_b() -> dict[str, Any]:
    """Read the adopted matrix out of the workbook — no hardcoded weights."""
    schema = parse_appendix(APPENDIX_B_CITATION and
                            APPENDIX_DIR / "Appendix_B_Risk_Classification_Matrix.xlsx")
    block = next(b for sheet in schema.sheets for b in sheet.blocks
                 if b.kind == "param_table")

    factors: list[dict[str, Any]] = []
    bands: dict[str, str] = {}
    for row in block.sample_rows:
        name = (row.get("Risk Factor") or "").strip()
        weight = row.get("Weight")
        if name and weight:
            factors.append({
                "key": _slug(name),
                "label": name,
                "weight": float(weight),
                "levels": {
                    1: row.get("Low (1)", ""),
                    2: row.get("Moderate (2)", ""),
                    3: row.get("High (3)", ""),
                },
            })
        marker = (row.get("#") or "").strip().upper()
        if marker.endswith("RISK"):
            bands[marker] = " ".join(
                v for k, v in row.items() if v and k not in ("#", "_group")
            )

    thresholds = {
        "low_max": 12,
        "moderate_min": 13,
        "moderate_max": 17,
        "high_min": 18,
        "high_factor_count": 2,
        "single_high_forces_moderate": True,
    }
    # Prefer the ranges printed in the workbook over the defaults above.
    import re
    for marker, text in bands.items():
        found = re.search(r"(\d+)\s*[–-]\s*(\d+)", text)
        if not found:
            continue
        lo, hi = int(found.group(1)), int(found.group(2))
        if marker.startswith("LOW"):
            thresholds["low_max"] = hi
        elif marker.startswith("MODERATE"):
            thresholds["moderate_min"], thresholds["moderate_max"] = lo, hi
        elif marker.startswith("HIGH"):
            thresholds["high_min"] = lo

    return {
        "version": 1,
        "source": "Appendix B — AI Risk Classification Matrix",
        "citation": APPENDIX_B_CITATION,
        "max_possible": round(sum(f["weight"] * 3 for f in factors), 2),
        "factors": factors,
        "thresholds": thresholds,
        "band_text": bands,
    }


DEFAULT_BUDGET = {
    "citation": "SCDES AI Operations Manual §9–10; Appendix E, Appendix I",
    "pools": {
        "recurring_per_year": 1_500_000,
        "one_time": 0,
    },
    "currency": "USD",
    "goal_weights": {
        "permit_backlog_reduction": 5,
        "inspection_targeting": 4,
        "public_response_time": 4,
        "internal_efficiency": 3,
        "innovation": 2,
    },
}

DEFAULT_PROCUREMENT = {
    "citation": "SCDES AI Governance Framework §8A; SCDES AI Operations Manual §9",
    "mandatory_provisions": [
        "AI disclosure and inventory obligation",
        "Data use and model-training restriction",
        "Performance and accuracy standards",
        "Audit and inspection rights",
        "Incident notification obligation",
        "Termination and transition assistance",
    ],
    "disclosure_tiers": {
        1: "Internal use, low decision criticality — streamlined disclosure",
        2: "Internal use, high decision criticality — algorithmic disclosure",
        3: "Public-facing, low decision criticality — accessibility and transparency",
        4: "Public-facing, high decision criticality — comprehensive supplement",
    },
    "change_management": {
        1: "Notify OT; registry update within 10 business days",
        2: "OT review and CTO acknowledgment before substitution",
        3: "Council concurrence (Tier B) before substitution",
        4: "Convened Council decision (Tier C) before substitution",
    },
}

DEFAULT_CATEGORIES = {
    "citation": "SCDES AI Governance Framework §5 (Authorized Use Case Structure)",
    "categories": {
        1: {"label": "Internal Service Optimization and Efficiency",
            "sequence": 1,
            "description": "Internal tools that make existing work faster or more "
                           "consistent, with no direct public-facing decision."},
        2: {"label": "Public and Economic Benefit",
            "sequence": 2,
            "description": "Systems that affect public services, public information, "
                           "or regulated parties."},
        3: {"label": "Innovation and Emerging Capability",
            "sequence": 3,
            "description": "Exploratory capability building beyond current operations."},
    },
}

DEFAULTS = {
    "budget": DEFAULT_BUDGET,
    "procurement": DEFAULT_PROCUREMENT,
    "categories": DEFAULT_CATEGORIES,
}


def bootstrap(force: bool = False) -> dict[str, Any]:
    """Create the config files from the adopted instruments if absent."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    written = {}
    if force or not RISK_MODEL.exists():
        model = derive_risk_model_from_appendix_b()
        atomic_write(RISK_MODEL, yaml.safe_dump(model, sort_keys=False))
        written["risk_model"] = model
    for name, payload in DEFAULTS.items():
        path = FILES[name]
        if force or not path.exists():
            atomic_write(path, yaml.safe_dump(payload, sort_keys=False))
            written[name] = payload
    return written


# --------------------------------------------------------------------- access

_cache: dict[str, Any] = {}


def load(name: str, refresh: bool = False) -> dict[str, Any]:
    if refresh or name not in _cache:
        path = FILES[name]
        if not path.exists():
            bootstrap()
        _cache[name] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return _cache[name]


def invalidate() -> None:
    _cache.clear()


def risk_model(refresh: bool = False) -> dict[str, Any]:
    return load("risk_model", refresh)


def _split(key: str) -> tuple[str, list[str]]:
    head, _, rest = key.partition(".")
    return head, [p for p in rest.split(".") if p]


def _resolve(doc: Any, path: list[str]) -> Any:
    node = doc
    for part in path:
        if isinstance(node, list):
            # factors.data_sensitivity.weight — address list items by their key
            match = next((i for i in node
                          if isinstance(i, dict) and i.get("key") == part), None)
            if match is None:
                try:
                    match = node[int(part)]
                except (ValueError, IndexError):
                    raise KeyError(part)
            node = match
        else:
            if part not in node:
                raise KeyError(part)
            node = node[part]
    return node


def _assign(doc: Any, path: list[str], value: Any) -> Any:
    parent = _resolve(doc, path[:-1]) if len(path) > 1 else doc
    leaf = path[-1]
    if isinstance(parent, list):
        match = next((i for i in parent
                      if isinstance(i, dict) and i.get("key") == leaf), None)
        if match is None:
            raise KeyError(leaf)
        return match
    old = parent.get(leaf)
    parent[leaf] = value
    return old


def get(key: str, default: Any = None) -> Any:
    name, path = _split(key)
    try:
        return _resolve(load(name), path)
    except (KeyError, TypeError):
        return default


def as_dict() -> dict[str, Any]:
    return {name: load(name) for name in FILES if FILES[name].exists()}


# ---------------------------------------------------------------- explanation

#: What each tunable key governs, in plain language, with the instrument it
#: implements. Configure renders these next to every control.
EXPLANATIONS: dict[str, tuple[str, str]] = {
    "risk_model.factors.*.weight": (
        "How heavily this factor counts toward the composite risk score. The "
        "composite decides a project's risk band, and the band decides who "
        "approves it and how often it is reviewed.",
        APPENDIX_B_CITATION,
    ),
    "risk_model.thresholds.low_max": (
        "The highest composite score that still classifies a project Low risk. "
        "Low-risk projects need only bureau-level approval.",
        APPENDIX_B_CITATION + "; §6.2 (Classification Thresholds)",
    ),
    "risk_model.thresholds.moderate_min": (
        "The composite score at which a project becomes Moderate risk and "
        "Council review enters the gate.",
        APPENDIX_B_CITATION + "; §6.2 (Classification Thresholds)",
    ),
    "risk_model.thresholds.moderate_max": (
        "The highest composite score that remains Moderate rather than High.",
        APPENDIX_B_CITATION + "; §6.2 (Classification Thresholds)",
    ),
    "risk_model.thresholds.high_min": (
        "The composite score at or above which a project is High risk, "
        "requiring Council review plus independent review.",
        APPENDIX_B_CITATION + "; §6.2 (Classification Thresholds)",
    ),
    "risk_model.thresholds.high_factor_count": (
        "How many individual High (3) factor ratings force a High "
        "classification regardless of the composite total.",
        APPENDIX_B_CITATION,
    ),
    "budget.pools.recurring_per_year": (
        "The annual recurring funding pool. License and subscription costs are "
        "scored against this pool; a quote that exceeds it is flagged over "
        "budget but is still fully scored.",
        "SCDES AI Operations Manual §9–10 (Procurement and Budget)",
    ),
    "budget.pools.one_time": (
        "The one-time (build and implementation) funding pool. Implementation "
        "costs are scored against this pool rather than the recurring one.",
        "SCDES AI Operations Manual §9–10 (Procurement and Budget)",
    ),
}


def _explanation_for(key: str) -> tuple[str, str]:
    if key in EXPLANATIONS:
        return EXPLANATIONS[key]
    parts = key.split(".")
    for pattern, value in EXPLANATIONS.items():
        pat = pattern.split(".")
        if len(pat) != len(parts):
            continue
        if all(p == "*" or p == a for p, a in zip(pat, parts)):
            return value
    name = _split(key)[0]
    doc = load(name)
    return (f"An operational parameter of {name.replace('_', ' ')}.",
            doc.get("citation", "SCDES AI Governance Framework"))


@dataclass
class Explanation:
    key: str
    label: str
    value: Any
    governs: str
    citation: str
    control: str = "text"
    options: list[Any] = dc_field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    step: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "label": self.label, "value": self.value,
            "governs": self.governs, "citation": self.citation,
            "control": self.control, "options": self.options,
            "min": self.minimum, "max": self.maximum, "step": self.step,
        }


def explain(key: str) -> Explanation:
    """What this control governs, what it implements, and how to render it."""
    governs, citation = _explanation_for(key)
    value = get(key)
    label = key.rsplit(".", 1)[-1].replace("_", " ").title()

    if key.startswith("risk_model.factors."):
        factor_key = key.split(".")[2]
        factor = next((f for f in risk_model()["factors"]
                       if f["key"] == factor_key), {})
        label = f"{factor.get('label', factor_key)} — weight"
        return Explanation(key, label, value, governs, citation,
                           control="slider", minimum=0.5, maximum=3.0, step=0.1)

    if key.startswith("risk_model.thresholds."):
        return Explanation(key, label, value, governs, citation,
                           control="slider", minimum=1, maximum=24, step=1)

    if key.startswith("budget.pools."):
        return Explanation(key, label, value, governs, citation,
                           control="number", minimum=0, step=50_000)

    return Explanation(key, label, value, governs, citation)


def tunable_keys() -> list[str]:
    keys = [f"risk_model.factors.{f['key']}.weight" for f in risk_model()["factors"]]
    keys += [f"risk_model.thresholds.{k}" for k in
             ("low_max", "moderate_min", "moderate_max", "high_min",
              "high_factor_count")]
    keys += ["budget.pools.recurring_per_year", "budget.pools.one_time"]
    return keys


# ------------------------------------------------------------------- previewing

def candidate(key: str, value: Any) -> dict[str, Any]:
    """A deep copy of the config with one key changed — never persisted."""
    name, path = _split(key)
    doc = copy.deepcopy(load(name))
    _assign(doc, path, value)
    return doc


@dataclass
class Consequence:
    key: str
    old_value: Any
    new_value: Any
    reclassified: list[dict[str, Any]] = dc_field(default_factory=list)
    newly_gated: list[str] = dc_field(default_factory=list)
    newly_required_appendices: list[str] = dc_field(default_factory=list)
    summary: str = ""
    affected: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key, "old_value": self.old_value,
            "new_value": self.new_value, "reclassified": self.reclassified,
            "newly_gated": self.newly_gated,
            "newly_required_appendices": self.newly_required_appendices,
            "summary": self.summary, "affected": self.affected,
        }


def consequence_preview(key: str, value: Any,
                        projects: Iterable[Any] | None = None) -> Consequence:
    """What this change would do to the live pipeline, before it is saved."""
    from app import registry as registry_mod
    from app import scoring

    projects = list(projects) if projects is not None else registry_mod.load_all()
    old_value = get(key)
    before_model = risk_model()
    after_doc = candidate(key, value)
    after_model = after_doc if key.startswith("risk_model") else before_model

    reclassified: list[dict[str, Any]] = []
    gated: list[str] = []
    appendices: set[str] = set()

    for project in projects:
        before = scoring.classify(project.factor_scores, before_model)
        after = scoring.classify(project.factor_scores, after_model)
        if before.band != after.band:
            reclassified.append({
                "registry_id": project.registry_id,
                "name": project.name,
                "from": before.band,
                "to": after.band,
                "score_before": before.total,
                "score_after": after.total,
            })
            if scoring.council_required(after.band) and not scoring.council_required(before.band):
                gated.append(project.name)
            appendices.update(scoring.required_appendices(after.band)
                              - scoring.required_appendices(before.band))

    consequence = Consequence(
        key=key, old_value=old_value, new_value=value,
        reclassified=reclassified, newly_gated=gated,
        newly_required_appendices=sorted(appendices),
        affected=len(reclassified),
    )
    consequence.summary = _summarise(consequence)
    return consequence


def _summarise(c: Consequence) -> str:
    if not c.reclassified:
        return "No project in the current pipeline changes risk band."
    moves: dict[str, int] = {}
    for row in c.reclassified:
        moves[f"{row['from']} → {row['to']}"] = moves.get(f"{row['from']} → {row['to']}", 0) + 1
    parts = [f"{n} project{'s' if n != 1 else ''} move {move}"
             for move, n in sorted(moves.items())]
    text = "; ".join(parts) + "."
    if c.newly_gated:
        text += (f" Council review newly triggers for "
                 f"{', '.join(c.newly_gated[:3])}"
                 f"{'…' if len(c.newly_gated) > 3 else ''}.")
    if c.newly_required_appendices:
        text += f" Newly required: {', '.join(c.newly_required_appendices)}."
    return text


# ---------------------------------------------------------------------- editing

@dataclass
class EditResult:
    decision: Decision
    key: str
    old_value: Any = None
    new_value: Any = None
    consequence: Consequence | None = None
    committed: bool = False


def edit(key: str, value: Any, actor: Actor, *,
         preview: Consequence | None = None) -> EditResult:
    """Set a governed parameter. Passes the guard; audited either way."""
    name, path = _split(key)
    target = Target.MANUAL if name == "manual" else Target.CONFIG
    old_value = get(key)
    consequence = preview or consequence_preview(key, value)

    decision = guard(
        actor, target, f"edit:{key}",
        detail={"key": key, "from": old_value, "to": value,
                "affected_projects": consequence.affected,
                "consequence": consequence.summary,
                "file_before": snapshot(FILES[name])},
    )
    if not decision.allowed:
        return EditResult(decision, key, old_value, value, consequence, False)

    doc = load(name)
    _assign(doc, path, value)
    atomic_write(FILES[name], yaml.safe_dump(doc, sort_keys=False))
    invalidate()
    return EditResult(decision, key, old_value, value, consequence, True)


def parameter_set_hash() -> str:
    """Identifies the exact tuned set the Council adopts at the mode transition."""
    import hashlib
    blob = yaml.safe_dump({n: load(n) for n in sorted(FILES) if FILES[n].exists()},
                          sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
