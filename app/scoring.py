"""Risk classification and the weighted purchase recommendation.

Everything here is a **pure function of (inputs, config)**. Nothing reads global
state, nothing writes. That is what makes the same code serve four surfaces
without any of them being able to move the record:

  Configure   re-runs it over the pipeline with a *candidate* config to preview
  Chat        re-runs it with a hypothetical config for a what-if
  Workflow    runs it with the live config to score a gate
  Oversight   re-runs it after an incident or a material change

"Exploring changes nothing" is therefore structural, not a rule to remember.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable

LOW, MODERATE, HIGH = "Low", "Moderate", "High"
BANDS = (LOW, MODERATE, HIGH)

#: Which appendices a band pulls into the lifecycle, per the Operations Manual.
BAND_APPENDICES = {
    LOW: {"Appendix B", "Appendix C", "Appendix G"},
    MODERATE: {"Appendix B", "Appendix C", "Appendix G", "Appendix F",
               "Appendix J"},
    HIGH: {"Appendix B", "Appendix C", "Appendix G", "Appendix F",
           "Appendix J", "Appendix K"},
}

def band_approval() -> dict[str, str]:
    """Who approves at each risk band.

    Derived rather than stated, because the approver is a framework answer. An
    agency that named one decision-maker has no council to route a Moderate
    system to, and telling them otherwise sends the approval nowhere.
    """
    from app import decider
    who = decider.body()
    return {
        LOW: "Bureau-level approval is sufficient at Gate 0.",
        MODERATE: f"Review by {who} is required at the gate.",
        HIGH: f"Review by {who} plus an independent review is required.",
    }


#: Convenience for callers that only want one band.
def approval_for(band: str) -> str:
    return band_approval().get(band, "")


def _decider_possessive() -> str:
    from app import decider
    return decider.possessive()

BAND_REVIEW_CADENCE = {LOW: "Annual", MODERATE: "Semi-annual", HIGH: "Quarterly"}


# ------------------------------------------------------------------ risk model

@dataclass
class Contribution:
    key: str
    label: str
    score: int
    weight: float
    weighted: float
    level_text: str = ""

    @property
    def is_high(self) -> bool:
        return self.score >= 3


@dataclass
class RiskResult:
    total: float
    band: str
    contributions: list[Contribution] = dc_field(default_factory=list)
    high_factors: list[str] = dc_field(default_factory=list)
    triggers: list[str] = dc_field(default_factory=list)
    explanation: str = ""
    max_possible: float = 0.0

    @property
    def council_required(self) -> bool:
        return council_required(self.band)

    @property
    def required_appendices(self) -> set[str]:
        return required_appendices(self.band)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total, "band": self.band,
            "max_possible": self.max_possible,
            "high_factors": self.high_factors, "triggers": self.triggers,
            "explanation": self.explanation,
            "contributions": [
                {"key": c.key, "label": c.label, "score": c.score,
                 "weight": c.weight, "weighted": c.weighted}
                for c in self.contributions
            ],
        }


def classify(factor_scores: dict[str, int],
             model: dict[str, Any]) -> RiskResult:
    """Score a project against the configured Appendix B model.

    `factor_scores` maps factor key → 1 (Low), 2 (Moderate) or 3 (High).
    Missing factors score 1 so a partially-filled intake still classifies.
    """
    factors = model.get("factors", [])
    thresholds = model.get("thresholds", {})

    contributions: list[Contribution] = []
    for factor in factors:
        raw = factor_scores.get(factor["key"], 1)
        try:
            score = max(1, min(3, int(raw)))
        except (TypeError, ValueError):
            score = 1
        weight = float(factor.get("weight", 1.0))
        levels = factor.get("levels") or {}
        contributions.append(Contribution(
            key=factor["key"], label=factor.get("label", factor["key"]),
            score=score, weight=weight, weighted=round(score * weight, 2),
            level_text=str(levels.get(score, levels.get(str(score), ""))),
        ))

    total = round(sum(c.weighted for c in contributions), 2)
    highs = [c.label for c in contributions if c.is_high]

    low_max = float(thresholds.get("low_max", 12))
    moderate_max = float(thresholds.get("moderate_max", 17))
    high_min = float(thresholds.get("high_min", 18))
    high_count = int(thresholds.get("high_factor_count", 2))
    single_high_moderate = bool(thresholds.get("single_high_forces_moderate", True))

    triggers: list[str] = []
    if len(highs) >= high_count:
        band = HIGH
        triggers.append(
            f"{len(highs)} factors rated High ({high_count} or more forces High)")
    elif total >= high_min:
        band = HIGH
        triggers.append(f"composite {total} is at or above the High threshold {high_min:g}")
    elif highs and single_high_moderate:
        band = MODERATE
        triggers.append(f"a single High factor ({highs[0]}) sets a Moderate floor")
    elif total > low_max:
        band = MODERATE
        triggers.append(f"composite {total} is above the Low ceiling {low_max:g}")
    else:
        band = LOW
        triggers.append(f"composite {total} is within the Low band (≤{low_max:g}), "
                        f"with no High factors")

    result = RiskResult(
        total=total, band=band, contributions=contributions,
        high_factors=highs, triggers=triggers,
        max_possible=float(model.get("max_possible",
                                     round(sum(float(f.get("weight", 1)) * 3
                                               for f in factors), 2))),
    )
    result.explanation = _explain(result, moderate_max)
    return result


def _explain(result: RiskResult, moderate_max: float) -> str:
    top = sorted(result.contributions, key=lambda c: c.weighted, reverse=True)[:2]
    drivers = ", ".join(f"{c.label} ({c.score}×{c.weight:g}={c.weighted:g})"
                        for c in top)
    text = (f"Composite {result.total:g} of {result.max_possible:g} → "
            f"{result.band} risk. Driven by {drivers}. "
            f"{result.triggers[0].capitalize()}.")
    return text + f" {approval_for(result.band)}"


def council_required(band: str) -> bool:
    return band in (MODERATE, HIGH)


def required_appendices(band: str) -> set[str]:
    return set(BAND_APPENDICES.get(band, set()))


def review_cadence(band: str) -> str:
    return BAND_REVIEW_CADENCE.get(band, "Annual")


def band_index(band: str) -> int:
    return BANDS.index(band) if band in BANDS else 0


# ------------------------------------------------------------- budget & quotes

ONE_TIME, RECURRING, SPLIT = "one_time", "recurring", "split"


@dataclass
class Quote:
    quote_id: str
    vendor: str
    product: str
    project_id: str = ""
    cost_type: str = RECURRING
    one_time_cost: float = 0.0
    recurring_cost_per_year: float = 0.0
    disclosure_tier: int = 1
    goals: dict[str, int] = dc_field(default_factory=dict)  # goal key → fit 0-5
    notes: str = ""

    @property
    def total_first_year(self) -> float:
        return self.one_time_cost + self.recurring_cost_per_year

    def retyped(self, cost_type: str, *, one_time: float | None = None,
                recurring: float | None = None) -> "Quote":
        """A copy with the cost re-typed — used by scenarios, never persisted."""
        from dataclasses import replace
        return replace(
            self, cost_type=cost_type,
            one_time_cost=self.one_time_cost if one_time is None else one_time,
            recurring_cost_per_year=(self.recurring_cost_per_year
                                     if recurring is None else recurring),
        )


@dataclass
class BudgetFit:
    pool: str
    pool_size: float
    committed: float
    requested: float
    headroom_before: float
    headroom_after: float
    over_budget: bool
    note: str = ""


@dataclass
class Recommendation:
    quote: Quote
    verdict: str                  # buy | hold | pass
    score: float
    goal_score: float
    risk_score: float
    budget_score: float
    risk: RiskResult | None = None
    fit: BudgetFit | None = None
    rationale: list[str] = dc_field(default_factory=list)
    citations: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "quote_id": self.quote.quote_id, "vendor": self.quote.vendor,
            "product": self.quote.product, "verdict": self.verdict,
            "score": self.score, "components": {
                "fit_to_goals": self.goal_score,
                "weighted_risk": self.risk_score,
                "budget_fit": self.budget_score,
            },
            "over_budget": self.fit.over_budget if self.fit else False,
            "rationale": self.rationale, "citations": self.citations,
        }


def budget_fit(quote: Quote, budget_cfg: dict[str, Any],
               committed: dict[str, float] | None = None) -> BudgetFit:
    """Score a cost-typed quote against the *matching* pool."""
    pools = budget_cfg.get("pools", {})
    committed = committed or {}

    if quote.cost_type == ONE_TIME:
        pool, size, requested = ("one_time", float(pools.get("one_time", 0)),
                                 quote.one_time_cost)
    elif quote.cost_type == SPLIT:
        # A split quote must clear both pools; report the tighter one.
        one = budget_fit(quote.retyped(ONE_TIME), budget_cfg, committed)
        rec = budget_fit(quote.retyped(RECURRING), budget_cfg, committed)
        tighter = one if one.headroom_after < rec.headroom_after else rec
        tighter.note = ("split quote — scored against both pools; "
                        f"tighter pool is {tighter.pool}")
        return tighter
    else:
        pool, size, requested = ("recurring_per_year",
                                 float(pools.get("recurring_per_year", 0)),
                                 quote.recurring_cost_per_year)

    already = float(committed.get(pool, 0.0))
    headroom_before = size - already
    headroom_after = headroom_before - requested
    return BudgetFit(
        pool=pool, pool_size=size, committed=already, requested=requested,
        headroom_before=headroom_before, headroom_after=headroom_after,
        over_budget=headroom_after < 0,
    )


def score_quote(quote: Quote, *, risk: RiskResult, budget_cfg: dict[str, Any],
                committed: dict[str, float] | None = None) -> Recommendation:
    """Three axes: fit to goals, weighted risk, budget fit. Explainable."""
    goal_weights = budget_cfg.get("goal_weights", {})
    max_goal = sum(goal_weights.values()) * 5 or 1
    earned = sum(goal_weights.get(g, 0) * min(5, max(0, fit))
                 for g, fit in quote.goals.items())
    goal_score = round(100 * earned / max_goal, 1)

    # Risk is scaled across the *achievable* composite range, not 0–max: the
    # floor is every factor rated Low, which is a clean bill of health and
    # should score 100. Scaling from zero would cap even the safest project in
    # the sixties and drag every verdict down with it.
    floor = risk.max_possible / 3 if risk.max_possible else 0     # all factors = 1
    span = (risk.max_possible - floor) or 1
    risk_score = round(100 * max(0.0, (risk.max_possible - risk.total)) / span, 1)

    fit = budget_fit(quote, budget_cfg, committed)
    if fit.over_budget:
        overage = -fit.headroom_after
        budget_score = round(max(0.0, 100 * (1 - overage / max(fit.pool_size, 1))), 1)
    else:
        used = fit.requested / fit.pool_size if fit.pool_size else 1
        budget_score = round(100 * (1 - 0.5 * used), 1)

    score = round(0.45 * goal_score + 0.20 * risk_score + 0.35 * budget_score, 1)

    rationale = [
        f"Fit to goals {goal_score:g}/100 — weighted by OT's configured goal priorities.",
        f"Weighted risk {risk_score:g}/100 — composite {risk.total:g} "
        f"({risk.band}) under the configured Appendix B model.",
    ]
    if fit.over_budget:
        rationale.append(
            f"Budget fit {budget_score:g}/100 — OVER the {_pool_label(fit.pool)} "
            f"pool by {_money(-fit.headroom_after)}; requested "
            f"{_money(fit.requested)} against {_money(fit.headroom_before)} headroom."
        )
    else:
        rationale.append(
            f"Budget fit {budget_score:g}/100 — fits the {_pool_label(fit.pool)} "
            f"pool, leaving {_money(fit.headroom_after)} headroom."
        )
    if fit.note:
        rationale.append(fit.note)
    if risk.council_required:
        rationale.append(
            f"{risk.band} risk does not block the purchase — it sets the approval "
            f"path. {approval_for(risk.band)} The award decision is "
            f"{_decider_possessive()} to log."
        )

    # Over budget is a hard flag, never a silent downgrade: the quote is still
    # fully scored so the decider can see what it would be buying.
    if fit.over_budget:
        verdict = "hold"
    elif score >= 60 and not (risk.band == HIGH and goal_score < 50):
        verdict = "buy"
    elif score >= 45:
        verdict = "hold"
    else:
        verdict = "pass"

    return Recommendation(
        quote=quote, verdict=verdict, score=score, goal_score=goal_score,
        risk_score=risk_score, budget_score=budget_score, risk=risk, fit=fit,
        rationale=rationale,
        citations=[
            budget_cfg.get("citation", "SCDES AI Operations Manual §9–10"),
            "Appendix B — AI Risk Classification Matrix",
            "Appendix E — Vendor AI Disclosure",
        ],
    )


def rank(recommendations: Iterable[Recommendation]) -> list[Recommendation]:
    order = {"buy": 0, "hold": 1, "pass": 2}
    return sorted(recommendations,
                  key=lambda r: (order.get(r.verdict, 3), -r.score))


def _pool_label(pool: str) -> str:
    return "recurring" if pool.startswith("recurring") else "one-time"


def _money(value: float) -> str:
    return f"${value:,.0f}"
