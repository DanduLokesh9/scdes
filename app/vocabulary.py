"""Terminology — the vocabulary layer every other surface reads from.

Agencies name the same concepts differently: bucket or category, tier or level,
A/B/C or 1/2/3, low/moderate/high or minimal/moderate/severe. SCDES settled its
naming in the Governance Framework; that fixed the Council Operating Procedures,
which fixed the Operations Manual, which fixed all fourteen appendices.

So this is **one choice made once at the top**, not fourteen to reconcile. It is
the first thing configured and it cascades to everything after.

Design note: the engine keeps **stable canonical keys** internally — a risk band
is always `low`/`moderate`/`high`, a Council decision is always `a`/`b`/`c`. Only
the *rendering* is configurable. That keeps scoring, the audit trail and the
gate map from breaking when an agency renames a concept, and it means a record
written under one vocabulary is still readable under another.

The defaults are not invented: `derive_from_corpus()` reads the adopted
documents and reports what they actually say.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field as dc_field
from typing import Any

import yaml

from app.audit import CORPUS, atomic_write
from app.authz import Actor, Decision, Target, guard

VOCABULARY_FILE = CORPUS / "config" / "vocabulary.yaml"

#: Canonical keys. These never change — only their labels do.
CONCEPTS = {
    "use_case_grouping": {
        "keys": ["1", "2", "3"],
        "governs": "How authorised use cases are grouped and sequenced. The "
                   "grouping drives the capacity ladder and which screening "
                   "applies.",
        "citation": "SCDES AI Governance Framework §5 (Authorized Use Case Structure)",
    },
    "council_decision": {
        "keys": ["a", "b", "c"],
        "governs": "How a Council decision is classified, which sets who may "
                   "decide and how quickly.",
        "citation": "SCDES AI Governance Framework §6; Appendix N",
    },
    "incident_severity": {
        "keys": ["1", "2", "3"],
        "governs": "How an AI incident is graded, which sets suspension, "
                   "notification and lookback obligations.",
        "citation": "SCDES AI Operations Manual §22 (Incident Response Procedure)",
    },
    "vendor_disclosure": {
        "keys": ["1", "2", "3", "4"],
        "governs": "How much disclosure a vendor owes, set by public exposure "
                   "and decision criticality.",
        "citation": "SCDES AI Operations Manual §9 (Vendor AI Disclosure Tier Procedure)",
    },
    "risk_band": {
        "keys": ["low", "moderate", "high"],
        "governs": "How a project's composite risk score is named. The band "
                   "sets the approval path and the review cadence.",
        "citation": "Appendix B; SCDES AI Operations Manual §6.2",
    },
}

#: The alternatives a new agency can choose between, per concept.
NOUN_OPTIONS = {
    "use_case_grouping": ["Category", "Bucket", "Class", "Group"],
    "council_decision": ["Tier", "Level", "Class"],
    "incident_severity": ["Level", "Tier", "Severity"],
    "vendor_disclosure": ["Tier", "Level", "Band"],
    "risk_band": ["Risk"],
}

SCHEME_OPTIONS = {
    "numeric": ["1", "2", "3", "4"],
    "alpha": ["A", "B", "C", "D"],
    "descriptive_risk": ["Low", "Moderate", "High"],
    "descriptive_risk_alt": ["Minimal", "Moderate", "Severe"],
    "descriptive_medium": ["Low", "Medium", "High"],
}


# ------------------------------------------------------------------ derivation

def derive_from_corpus() -> dict[str, Any]:
    """What the adopted documents actually say — the defaults come from here."""
    from app.integrity import observed_vocabulary
    from app.ingest_docx import parse_all as parse_docs
    from app.ingest_xlsx import parse_all as parse_appendices

    text = {d.doc_label: "\n".join(f"{c.heading}\n{c.text}" for c in d.chunks)
            for d in parse_docs()}
    appendices = {s.letter: s for s in parse_appendices()}
    observed = observed_vocabulary(text, appendices)

    def winner(concept: str, fallback: str) -> tuple[str, int, dict[str, int]]:
        counts = observed.get(concept, {})
        if not counts:
            return fallback, 0, {}
        top = max(counts.items(), key=lambda kv: kv[1])
        return top[0], top[1], counts

    grouping, g_n, g_all = winner("use case grouping", "category")
    council, c_n, c_all = winner("council decision level", "tier")
    incident, i_n, i_all = winner("incident severity", "level")
    vendor, v_n, v_all = winner("vendor disclosure depth", "tier")
    band, b_n, b_all = winner("risk band labels", "low/moderate/high")

    band_labels = {
        "low/moderate/high": ["Low", "Moderate", "High"],
        "low/medium/high": ["Low", "Medium", "High"],
        "minimal/moderate/severe": ["Minimal", "Moderate", "Severe"],
    }.get(band, ["Low", "Moderate", "High"])

    return {
        "source": "derived from the adopted SCDES corpus",
        "concepts": {
            "use_case_grouping": {
                "noun": grouping.title(), "scheme": "numeric",
                "labels": {k: f"{grouping.title()} {k}" for k in ("1", "2", "3")},
                "evidence": f"{g_n} uses in the corpus", "alternatives": g_all,
            },
            "council_decision": {
                "noun": council.title(), "scheme": "alpha",
                "labels": {k: f"{council.title()} {k.upper()}"
                           for k in ("a", "b", "c")},
                "evidence": f"{c_n} uses in the corpus", "alternatives": c_all,
            },
            "incident_severity": {
                "noun": incident.title(), "scheme": "numeric",
                "labels": {k: f"{incident.title()} {k}" for k in ("1", "2", "3")},
                "evidence": f"{i_n} uses in the corpus", "alternatives": i_all,
            },
            "vendor_disclosure": {
                "noun": vendor.title(), "scheme": "numeric",
                "labels": {k: f"{vendor.title()} {k}"
                           for k in ("1", "2", "3", "4")},
                "evidence": f"{v_n} uses in the corpus", "alternatives": v_all,
            },
            "risk_band": {
                "noun": "Risk", "scheme": "descriptive_risk",
                "labels": dict(zip(("low", "moderate", "high"), band_labels)),
                "evidence": f"{b_n} uses in the corpus", "alternatives": b_all,
            },
        },
    }


# ------------------------------------------------------------------- storage

_cache: dict[str, Any] | None = None


def load(refresh: bool = False) -> dict[str, Any]:
    global _cache
    if _cache is not None and not refresh:
        return _cache
    if not VOCABULARY_FILE.exists():
        bootstrap()
    _cache = yaml.safe_load(VOCABULARY_FILE.read_text(encoding="utf-8")) or {}
    return _cache


def bootstrap(force: bool = False) -> dict[str, Any]:
    if force or not VOCABULARY_FILE.exists():
        derived = derive_from_corpus()
        atomic_write(VOCABULARY_FILE, yaml.safe_dump(derived, sort_keys=False))
        invalidate()
    return load(refresh=True)


def invalidate() -> None:
    global _cache
    _cache = None


# -------------------------------------------------------------------- lookup

def noun(concept: str) -> str:
    return load().get("concepts", {}).get(concept, {}).get("noun", concept.title())


def label(concept: str, key: str | int) -> str:
    """Render a canonical key in the configured vocabulary."""
    spec = load().get("concepts", {}).get(concept, {})
    labels = spec.get("labels", {})
    return labels.get(str(key).lower(), str(key))


def labels(concept: str) -> dict[str, str]:
    return dict(load().get("concepts", {}).get(concept, {}).get("labels", {}))


def band(key: str) -> str:
    """Risk band label — the most-used lookup, so give it a short name."""
    return label("risk_band", key)


def synonyms(concept: str) -> list[str]:
    """Every noun this concept might be called, for search-query expansion."""
    configured = noun(concept)
    return sorted({configured, *NOUN_OPTIONS.get(concept, [])})


def as_display_map() -> dict[str, dict[str, str]]:
    return {c: labels(c) for c in CONCEPTS}


# -------------------------------------------------------------------- editing

@dataclass
class RenameImpact:
    concept: str
    old_noun: str
    new_noun: str
    old_labels: dict[str, str] = dc_field(default_factory=dict)
    new_labels: dict[str, str] = dc_field(default_factory=dict)
    surfaces: list[str] = dc_field(default_factory=list)
    corpus_mentions: int = 0
    summary: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept, "old_noun": self.old_noun,
            "new_noun": self.new_noun, "old_labels": self.old_labels,
            "new_labels": self.new_labels, "surfaces": self.surfaces,
            "corpus_mentions": self.corpus_mentions, "summary": self.summary,
        }


#: Where each concept shows up, so a rename can state its own blast radius.
SURFACES = {
    "use_case_grouping": ["Registry", "Vision — category maturity", "Intake form",
                          "Appendix A", "Appendix G", "Gate 0 checklist"],
    "council_decision": ["Council decision log", "Process — decision tiers",
                         "Gate routing", "Appendix N"],
    "incident_severity": ["Oversight", "Incident report", "Appendix L"],
    "vendor_disclosure": ["Budget — vendor quotes", "Procurement", "Appendix E"],
    "risk_band": ["Registry", "Configure — consequence preview", "Workflow gates",
                  "Budget recommendation", "Oversight", "Appendix B"],
}


def preview_rename(concept: str, new_noun: str,
                   scheme: str | None = None) -> RenameImpact:
    """What a rename would change — computed, never saved."""
    spec = load().get("concepts", {}).get(concept, {})
    old_noun = spec.get("noun", "")
    old_labels = dict(spec.get("labels", {}))
    keys = list(old_labels) or CONCEPTS[concept]["keys"]

    scheme = scheme or spec.get("scheme", "numeric")
    if scheme.startswith("descriptive"):
        values = SCHEME_OPTIONS.get(scheme, ["Low", "Moderate", "High"])
        new_labels = {k: v for k, v in zip(keys, values)}
    elif scheme == "alpha":
        new_labels = {k: f"{new_noun} {k.upper()}" for k in keys}
    else:
        new_labels = {k: f"{new_noun} {k}" for k in keys}

    mentions = 0
    try:
        from app.integrity import observed_vocabulary
        from app.ingest_docx import parse_all as parse_docs
        from app.ingest_xlsx import parse_all as parse_appendices
        text = {d.doc_label: "\n".join(c.text for c in d.chunks)
                for d in parse_docs()}
        appendices = {s.letter: s for s in parse_appendices()}
        observed = observed_vocabulary(text, appendices)
        for counts in observed.values():
            mentions += counts.get(old_noun.lower(), 0)
    except Exception:
        mentions = 0

    impact = RenameImpact(
        concept=concept, old_noun=old_noun, new_noun=new_noun,
        old_labels=old_labels, new_labels=new_labels,
        surfaces=SURFACES.get(concept, []), corpus_mentions=mentions,
    )
    changed = [k for k in keys if old_labels.get(k) != new_labels.get(k)]
    impact.summary = (
        f"“{old_noun}” becomes “{new_noun}” across {len(impact.surfaces)} "
        f"surfaces and {len(changed)} label(s): "
        + ", ".join(f"{old_labels.get(k, k)} → {new_labels[k]}" for k in changed[:4])
        + (f". The adopted documents use “{old_noun}” {mentions} times; the app "
           f"re-labels its own surfaces, it does not rewrite the corpus."
           if mentions else ".")
    )
    return impact


def set_term(concept: str, new_noun: str, actor: Actor, *,
             scheme: str | None = None) -> dict[str, Any]:
    """Change a concept's vocabulary. OT-owned, guarded, audited."""
    if concept not in CONCEPTS:
        raise KeyError(concept)
    impact = preview_rename(concept, new_noun, scheme)

    decision = guard(
        actor, Target.CONFIG, f"set_terminology:{concept}",
        detail={"concept": concept, "from": impact.old_noun, "to": new_noun,
                "surfaces": len(impact.surfaces), "summary": impact.summary},
    )
    if not decision.allowed:
        return {"committed": False, "reason": decision.reason,
                "requires_council": decision.requires_council,
                "impact": impact.as_dict()}

    doc = load()
    spec = doc.setdefault("concepts", {}).setdefault(concept, {})
    spec["noun"] = new_noun
    if scheme:
        spec["scheme"] = scheme
    spec["labels"] = impact.new_labels
    atomic_write(VOCABULARY_FILE, yaml.safe_dump(doc, sort_keys=False))
    invalidate()
    return {"committed": True, "impact": impact.as_dict(),
            "reason": decision.reason}


# ------------------------------------------------------------------ reporting

def state() -> dict[str, Any]:
    """Everything the Configure room needs to render the terminology step."""
    doc = load()
    derived = doc.get("source", "")
    out = []
    for concept, meta in CONCEPTS.items():
        spec = doc.get("concepts", {}).get(concept, {})
        out.append({
            "concept": concept,
            "title": concept.replace("_", " ").title(),
            "noun": spec.get("noun", ""),
            "scheme": spec.get("scheme", ""),
            "labels": spec.get("labels", {}),
            "options": NOUN_OPTIONS.get(concept, []),
            "schemes": (["descriptive_risk", "descriptive_risk_alt",
                         "descriptive_medium"] if concept == "risk_band"
                        else ["numeric", "alpha"]),
            "governs": meta["governs"],
            "citation": meta["citation"],
            "evidence": spec.get("evidence", ""),
            "alternatives_in_corpus": spec.get("alternatives", {}),
            "surfaces": SURFACES.get(concept, []),
        })
    return {"source": derived, "concepts": out}
