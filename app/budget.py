"""Budget pools, cost-typed quotes, and the weighted purchase recommendation.

Budget is **pools, not a number**: a recurring annual pool and a one-time pool.
Every quote is cost-typed and scored against the *matching* pool, which is why
re-typing a quote from recurring to one-time can change the ranking without a
penny of the budget-of-record moving.

Scenarios run against a candidate copy of the budget config. Only OT editing
Configure makes a change real.
"""

from __future__ import annotations

import copy
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from app import config as config_mod
from app import registry as registry_mod
from app import scoring
from app.audit import CORPUS, atomic_write
from app.authz import Actor, Decision, Target, guard
from app.scoring import ONE_TIME, RECURRING, SPLIT, Quote

QUOTES_DIR = CORPUS / "vendor_quotes"
LEDGER = CORPUS / "ledger.md"


# ------------------------------------------------------------------ persistence

def save_quote(quote: Quote) -> Path:
    QUOTES_DIR.mkdir(parents=True, exist_ok=True)
    path = QUOTES_DIR / f"{quote.quote_id}.json"
    atomic_write(path, json.dumps(asdict(quote), indent=2) + "\n")
    return path


def load_quotes() -> list[Quote]:
    if not QUOTES_DIR.exists():
        return []
    quotes = []
    for path in sorted(QUOTES_DIR.glob("*.json")):
        quotes.append(Quote(**json.loads(path.read_text(encoding="utf-8"))))
    return quotes


def record_quote(quote: Quote, actor: Actor) -> tuple[Decision, Quote | None]:
    decision = guard(actor, Target.VENDOR_QUOTE, "record_quote",
                     detail={"quote_id": quote.quote_id, "vendor": quote.vendor,
                             "cost_type": quote.cost_type})
    if not decision.allowed:
        return decision, None
    save_quote(quote)
    return decision, quote


# ------------------------------------------------------------------- the seeds

DELTA_BRAVO = Quote(
    quote_id="Q-DELTA-BRAVO",
    vendor="Delta Bravo",
    product="PermitPro expansion — three divisions",
    project_id="AI-001",
    cost_type=RECURRING,          # as quoted: an annual licence
    recurring_cost_per_year=1_880_000,
    one_time_cost=0,
    disclosure_tier=2,
    goals={"permit_backlog_reduction": 5, "inspection_targeting": 3,
           "internal_efficiency": 4, "public_response_time": 3},
    notes=("Quoted as an annual license across three divisions. The vendor will "
           "re-type the build portion as one-time on request — which is the "
           "scenario worth running."),
)

OTHER_QUOTES = [
    Quote(
        quote_id="Q-RIVERWATCH",
        vendor="RiverWatch Analytics",
        product="Effluent anomaly detection",
        project_id="AI-003",
        cost_type=RECURRING, recurring_cost_per_year=240_000,
        disclosure_tier=1,
        goals={"internal_efficiency": 4, "inspection_targeting": 4,
               "permit_backlog_reduction": 1},
    ),
    Quote(
        quote_id="Q-ATLAS",
        vendor="Atlas Civic",
        product="Public permit assistant",
        project_id="AI-006",
        cost_type=SPLIT, one_time_cost=300_000, recurring_cost_per_year=120_000,
        disclosure_tier=3,
        goals={"public_response_time": 5, "permit_backlog_reduction": 2,
               "internal_efficiency": 2},
    ),
]


def seed(actor: Actor) -> dict[str, Any]:
    created = []
    for quote in [DELTA_BRAVO, *OTHER_QUOTES]:
        if (QUOTES_DIR / f"{quote.quote_id}.json").exists():
            continue
        decision, made = record_quote(quote, actor)
        if made:
            created.append(made.quote_id)
    return {"created": created}


# -------------------------------------------------------------- recommendations

def _risk_for(quote: Quote, model: dict[str, Any]) -> scoring.RiskResult:
    project = registry_mod.load(quote.project_id) if quote.project_id else None
    if project is not None:
        return scoring.classify(project.factor_scores, model)
    # No linked project yet — score the purchase on the disclosure tier alone.
    tier = max(1, min(4, quote.disclosure_tier))
    return scoring.classify({
        "regulatory_impact": 2,
        "public_facing_exposure": 3 if tier >= 3 else 1,
        "data_sensitivity": 2,
        "reversibility": 2,
        "community_impact": 2 if tier >= 3 else 1,
        "federal_program_nexus": 2,
    }, model)


def committed_totals(exclude: str | None = None) -> dict[str, float]:
    """What the ledger has already spoken for, by pool."""
    totals = {"recurring_per_year": 0.0, "one_time": 0.0}
    for project in registry_mod.load_all():
        if project.stage in ("production", "pilot") and project.annual_cost:
            totals["recurring_per_year"] += float(project.annual_cost)
    return totals


def recommendations(*, budget_cfg: dict[str, Any] | None = None,
                    model: dict[str, Any] | None = None,
                    quotes: list[Quote] | None = None
                    ) -> list[scoring.Recommendation]:
    budget_cfg = budget_cfg or config_mod.load("budget")
    model = model or config_mod.risk_model()
    quotes = quotes if quotes is not None else load_quotes()
    committed = committed_totals()

    results = [
        scoring.score_quote(q, risk=_risk_for(q, model),
                            budget_cfg=budget_cfg, committed=committed)
        for q in quotes
    ]
    return scoring.rank(results)


# ------------------------------------------------------------------- scenarios

def scenario(*, recurring_per_year: float | None = None,
             one_time: float | None = None,
             retype: dict[str, str] | None = None) -> dict[str, Any]:
    """A live what-if over the budget. The budget-of-record does not move."""
    live_cfg = config_mod.load("budget")
    candidate = copy.deepcopy(live_cfg)
    if recurring_per_year is not None:
        candidate["pools"]["recurring_per_year"] = recurring_per_year
    if one_time is not None:
        candidate["pools"]["one_time"] = one_time

    quotes = load_quotes()
    if retype:
        adjusted = []
        for q in quotes:
            if q.quote_id in retype:
                new_type = retype[q.quote_id]
                if new_type == ONE_TIME:
                    adjusted.append(q.retyped(
                        ONE_TIME, one_time=q.recurring_cost_per_year or q.one_time_cost,
                        recurring=0.0))
                elif new_type == RECURRING:
                    adjusted.append(q.retyped(
                        RECURRING, one_time=0.0,
                        recurring=q.one_time_cost or q.recurring_cost_per_year))
                else:
                    adjusted.append(q.retyped(new_type))
            else:
                adjusted.append(q)
        quotes = adjusted

    before = recommendations(budget_cfg=live_cfg)
    after = recommendations(budget_cfg=candidate, quotes=quotes)

    moved = []
    before_rank = {r.quote.quote_id: i for i, r in enumerate(before)}
    for i, rec in enumerate(after):
        was = before_rank.get(rec.quote.quote_id)
        if was is not None and was != i:
            moved.append({"quote_id": rec.quote.quote_id,
                          "vendor": rec.quote.vendor,
                          "from_rank": was + 1, "to_rank": i + 1})

    flips = []
    before_verdict = {r.quote.quote_id: r for r in before}
    for rec in after:
        prev = before_verdict.get(rec.quote.quote_id)
        if prev and (prev.verdict != rec.verdict
                     or prev.fit.over_budget != rec.fit.over_budget):
            flips.append({
                "quote_id": rec.quote.quote_id, "vendor": rec.quote.vendor,
                "verdict_before": prev.verdict, "verdict_after": rec.verdict,
                "over_before": prev.fit.over_budget,
                "over_after": rec.fit.over_budget,
            })

    return {
        "pools_of_record": live_cfg["pools"],
        "pools_in_scenario": candidate["pools"],
        "retype": retype or {},
        "before": [r.as_dict() for r in before],
        "after": [r.as_dict() for r in after],
        "rank_changes": moved,
        "verdict_changes": flips,
        "budget_of_record_unchanged": True,
        "narrative": _narrate(live_cfg, candidate, before, after, flips, moved),
    }


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _narrate(live: dict, candidate: dict, before, after, flips, moved) -> str:
    lines = ["Scenario only — the budget of record has not moved."]
    lp, cp = live["pools"], candidate["pools"]
    if lp != cp:
        lines.append(
            f"Pools: recurring {_money(lp['recurring_per_year'])} → "
            f"{_money(cp['recurring_per_year'])}/yr; one-time "
            f"{_money(lp['one_time'])} → {_money(cp['one_time'])}.")
    for flip in flips:
        if flip["over_before"] and not flip["over_after"]:
            lines.append(f"{flip['vendor']} was over budget and now fits "
                         f"({flip['verdict_before']} → {flip['verdict_after']}).")
        elif not flip["over_before"] and flip["over_after"]:
            lines.append(f"{flip['vendor']} no longer fits "
                         f"({flip['verdict_before']} → {flip['verdict_after']}).")
        else:
            lines.append(f"{flip['vendor']}: {flip['verdict_before']} → "
                         f"{flip['verdict_after']}.")
    if moved:
        lines.append("Ranking changes: " + "; ".join(
            f"{m['vendor']} #{m['from_rank']}→#{m['to_rank']}" for m in moved) + ".")
    if not flips and not moved:
        lines.append("No verdict or ranking changes.")
    lines.append("Only OT editing Configure makes this real.")
    return " ".join(lines)


def delta_bravo_scenario() -> dict[str, Any]:
    """The must-pass test: over budget as quoted, fits when re-typed one-time."""
    return scenario(one_time=4_500_000, recurring_per_year=1_500_000,
                    retype={"Q-DELTA-BRAVO": ONE_TIME})
