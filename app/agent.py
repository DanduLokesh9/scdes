"""The chat bar — three modes, none of which change anything.

  query     a cited answer from the governed corpus, or an honest refusal
  scenario  a live what-if, computed against a candidate config that is
            never persisted; the budget- and risk-of-record do not move
  intake    a plain-language problem becomes a *draft* intake with a suggested
            Category and an initial risk score

The draft is deliberately returned rather than saved. Turning it into a Registry
entry is a separate, deliberate act by a named operator through the guard — so
describing a problem cannot itself write to the record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any

from app import config as config_mod
from app import registry as registry_mod
from app import retrieval, scoring
from app.authz import CHAT_ACTOR
from app.provider import Provider, get_provider

QUERY, SCENARIO, INTAKE = "query", "scenario", "intake"

_SCENARIO_CUE = re.compile(
    r"\bwhat if\b|\bwhat happens if\b|\bsuppose\b|\bif we (set|move|change|raise|"
    r"lower|had|add)\b|\bhow would\b.*\bchange\b", re.I)

_INTAKE_CUE = re.compile(
    r"\bstart a project\b|\bwe (need|want|have|are drowning)\b|\bour \w+ (is|are)\b|"
    r"\bcould ai\b|\bcan ai\b|\bhelp (us|me)\b|\bi want to\b|\bwe'?re (drowning|"
    r"struggling|behind)\b|\bbacklog\b.*\b(out of control|growing|huge)\b", re.I)

_MONEY = re.compile(r"\$?\s*([\d,]+(?:\.\d+)?)\s*(m|million|k|thousand)?\b", re.I)
_TO_VALUE = re.compile(r"\bto\s+(?:x|×)?\s*([\d.]+)", re.I)


@dataclass
class ChatResult:
    mode: str
    answer: str
    provider: str
    citations: list[dict[str, Any]] = dc_field(default_factory=list)
    scenario: dict[str, Any] | None = None
    draft_project: dict[str, Any] | None = None
    in_scope: bool = True
    changed_nothing: bool = True
    note: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode, "answer": self.answer, "provider": self.provider,
            "citations": self.citations, "scenario": self.scenario,
            "draft_project": self.draft_project, "in_scope": self.in_scope,
            "changed_nothing": self.changed_nothing, "note": self.note,
        }


def detect_mode(message: str) -> str:
    if _SCENARIO_CUE.search(message):
        return SCENARIO
    if _INTAKE_CUE.search(message):
        return INTAKE
    return QUERY


# ---------------------------------------------------------------------- query

def _citations(hits: list[retrieval.Hit]) -> list[dict[str, Any]]:
    return [
        {"n": n, "citation": h.passage.citation, "source": h.passage.source,
         "section": h.passage.section, "snippet": h.snippet(360),
         "authoritative": h.passage.authoritative, "score": h.score}
        for n, h in enumerate(hits, start=1)
    ]


def answer_query(message: str, provider: Provider) -> ChatResult:
    hits = retrieval.search(message, top_k=5)
    if not retrieval.in_scope(hits):
        nearest = ", ".join(h.passage.citation for h in hits[:2]) or "nothing close"
        return ChatResult(
            mode=QUERY,
            answer=(
                "That is outside the governed corpus, so there is nothing here I "
                "can cite. This assistant answers only from the SCDES AI "
                f"Governance Framework, the Operations Manual and Appendices A–N. "
                f"The closest sections I found were: {nearest}. If you meant "
                "something in scope, try naming the gate, tier, appendix or "
                "procedure you have in mind."
            ),
            provider=provider.name, citations=_citations(hits[:2]),
            in_scope=False,
        )

    phrasing = provider.phrase(message, hits)
    return ChatResult(
        mode=QUERY, answer=phrasing.text, provider=phrasing.provider,
        citations=_citations(hits), note=phrasing.note,
    )


# ------------------------------------------------------------------- scenario

def _parse_money(text: str) -> float | None:
    m = _MONEY.search(text)
    if not m:
        return None
    value = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    if unit in ("m", "million"):
        value *= 1_000_000
    elif unit in ("k", "thousand"):
        value *= 1_000
    return value


def _find_factor(text: str) -> dict[str, Any] | None:
    model = config_mod.risk_model()
    lowered = text.lower()
    for factor in model["factors"]:
        label = factor["label"].lower()
        if label in lowered:
            return factor
        # "data sensitivity" also written "sensitivity"
        tail = label.split()[-1]
        if len(tail) > 5 and tail in lowered:
            return factor
    return None


def run_scenario(message: str, provider: Provider) -> ChatResult:
    """Compute a what-if. Nothing is written — the config is copied, not saved."""
    projects = registry_mod.load_all()

    factor = _find_factor(message)
    target_value = _TO_VALUE.search(message)

    # --- a risk-model what-if -------------------------------------------
    if factor and target_value:
        key = f"risk_model.factors.{factor['key']}.weight"
        try:
            value = float(target_value.group(1))
        except ValueError:
            value = None
        if value is not None:
            consequence = config_mod.consequence_preview(key, value, projects)
            lines = [
                f"Scenario only — the risk model of record is unchanged.",
                f"Moving {factor['label']} from ×{factor['weight']:g} to ×{value:g}: "
                f"{consequence.summary}",
            ]
            for row in consequence.reclassified[:6]:
                lines.append(
                    f"  · {row['name'][:52]} {row['from']} → {row['to']} "
                    f"(composite {row['score_before']:g} → {row['score_after']:g})")
            if consequence.reclassified:
                lines.append("Only OT editing Configure makes this real.")
            return ChatResult(
                mode=SCENARIO, answer="\n".join(lines), provider=provider.name,
                scenario=consequence.as_dict(),
                citations=_citations(retrieval.search(
                    f"risk classification {factor['label']}", top_k=2)),
            )

    # --- a budget what-if ------------------------------------------------
    amount = _parse_money(message)
    if amount is not None and re.search(r"budget|pool|recurring|one[- ]time|fund",
                                        message, re.I):
        one_time = bool(re.search(r"one[- ]time|build|implementation|capital",
                                  message, re.I))
        key = ("budget.pools.one_time" if one_time
               else "budget.pools.recurring_per_year")
        from app import budget as budget_mod
        result = budget_mod.scenario(**{("one_time" if one_time
                                        else "recurring_per_year"): amount})
        return ChatResult(
            mode=SCENARIO, answer=result["narrative"], provider=provider.name,
            scenario=result,
            citations=_citations(retrieval.search("budget procurement pool", top_k=2)),
        )

    # --- couldn't pin the change ----------------------------------------
    return ChatResult(
        mode=SCENARIO,
        answer=(
            "I can run that as a what-if if you name the parameter and the value "
            "— for example “what if Data Sensitivity moved to 2.0?” or “what if we "
            "had $4.5M one-time?”. Scenarios are computed live and never touch the "
            "record."
        ),
        provider=provider.name, in_scope=False,
    )


# --------------------------------------------------------------------- intake

def start_project(message: str, provider: Provider) -> ChatResult:
    """A plain-language problem becomes a draft intake — not a Registry entry."""
    extracted = provider.extract_intake(message)

    public = bool(extracted.get("public_facing"))
    protected = bool(extracted.get("touches_protected_data"))
    federal = str(extracted.get("federal_program") or "")
    category = int(extracted.get("suggested_category") or 1)

    scores = {
        "regulatory_impact": 2 if re.search(
            r"permit|complian|enforce|inspect|regulat", message, re.I) else 1,
        "public_facing_exposure": 3 if public else (2 if category >= 2 else 1),
        "data_sensitivity": 3 if protected else 2,
        "reversibility": 2,
        "community_impact": 2 if public else 1,
        "federal_program_nexus": 3 if registry_mod._DELEGATED.search(federal) else (
            2 if federal.strip() else 1),
    }
    risk = scoring.classify(scores, config_mod.risk_model())

    draft = {
        "registry_id": registry_mod.next_registry_id(),
        "name": extracted.get("project_name", "Untitled project"),
        "description": extracted.get("problem_statement", message[:400]),
        "bureau": extracted.get("bureau", "Operations and Services"),
        "category": category,
        "category_reason": extracted.get("category_reason", ""),
        "factor_scores": scores,
        "scores_are_derived": True,
        "risk": risk.as_dict(),
        "federal_nexus": federal,
        "expected_outcome": extracted.get("expected_outcome", ""),
        "matched_taxonomy_id": extracted.get("_matched_taxonomy_id", ""),
        "candidates": extracted.get("_candidates", []),
        "next_gate": 0,
        "required_appendices": sorted(risk.required_appendices),
        "persisted": False,
    }

    gate_note = ("This is a draft only — nothing has been written to the Registry. "
                 "An owner confirms it to create the entry.")
    alternates = ""
    if len(draft["candidates"]) > 1:
        others = ", ".join(
            f"{c['id']} ({c['use_case']}, Category {c['category']})"
            for c in draft["candidates"][1:]
        )
        alternates = (f"Other close matches in Appendix A: {others}. "
                      f"Confirm the right one at Gate 0.\n")
    answer = (
        f"Drafted “{draft['name']}” as {draft['registry_id']} for the "
        f"{draft['bureau']} bureau.\n"
        f"Suggested Category {category} — {draft['category_reason']}\n"
        f"{alternates}"
        f"Initial risk: {risk.band} (composite {risk.total:g} of "
        f"{risk.max_possible:g}). {risk.explanation}\n"
        f"At Gate 0 this needs: {', '.join(draft['required_appendices'])}.\n"
        f"{gate_note}"
    )
    return ChatResult(
        mode=INTAKE, answer=answer, provider=extracted.get("_provider", provider.name),
        draft_project=draft,
        citations=_citations(retrieval.search(
            "project intake gate 0 concept approval category", top_k=3)),
    )


# ----------------------------------------------------------------------- entry

def chat(message: str, *, provider: Provider | None = None,
         prefer: str | None = None) -> ChatResult:
    """Single entry point. Runs as CHAT_ACTOR, which cannot write anything."""
    assert CHAT_ACTOR.readonly, "the chat actor must never be write-capable"
    provider = provider or get_provider(prefer)
    message = (message or "").strip()
    if not message:
        return ChatResult(QUERY, "Ask a question, run a what-if, or describe a "
                                 "problem to start a project.", provider.name)

    mode = detect_mode(message)
    if mode == SCENARIO:
        return run_scenario(message, provider)
    if mode == INTAKE:
        return start_project(message, provider)
    return answer_query(message, provider)
