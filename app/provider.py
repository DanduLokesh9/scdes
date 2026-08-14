"""Language providers — phrasing only, and only over retrieved snippets.

Retrieval, citation, scoring and the audit trail are always local. A provider is
asked to do one narrow job: turn passages the app already found into readable
prose, and read a plain-language problem statement into intake fields.

**The corpus never leaves the machine.** Only the question and the top-k
retrieved snippets are ever sent anywhere.

Two implementations behind one interface:

  AnthropicProvider  claude-opus-5; better phrasing and intake extraction
  LocalProvider      deterministic templates + Appendix A taxonomy matching;
                     no network, no API key — this is the offline path
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field as dc_field
from typing import Any, Iterable, Protocol

from app.retrieval import Hit

MODEL = "claude-opus-5"

SYSTEM_PROMPT = """\
You explain the South Carolina Department of Environmental Services (SCDES) AI \
Governance Framework to agency staff.

You are given a question and numbered excerpts retrieved from SCDES's adopted \
governance documents. Answer only from those excerpts.

Rules:
- Ground every claim in the excerpts. If they do not answer the question, say \
so plainly rather than filling the gap.
- Cite the excerpt number inline as [1], [2] where a claim comes from it. The \
application renders the full citation, so do not restate document titles.
- Be direct and brief — two or three sentences unless the question genuinely \
needs more. Lead with the answer.
- Never invent a section number, a threshold, a weight, a tier, or a deadline. \
If a specific figure is not in the excerpts, say it is not stated there.
- Refer to the agency as "South Carolina Department of Environmental Services \
(SCDES)" on first use and "SCDES" after. Never "DES" or "SC DES".
"""

INTAKE_SCHEMA = {
    "type": "object",
    "properties": {
        "project_name": {"type": "string",
                         "description": "Short descriptive name, title case"},
        "problem_statement": {"type": "string",
                              "description": "The problem in one or two sentences"},
        "bureau": {"type": "string", "enum": [
            "Water", "Land and Waste", "Air", "Coastal Zone Management",
            "Operations and Services", "Other (specify)"]},
        "suggested_category": {"type": "integer", "enum": [1, 2, 3]},
        "category_reason": {"type": "string"},
        "public_facing": {"type": "boolean"},
        "touches_protected_data": {"type": "boolean"},
        "federal_program": {"type": "string",
                            "description": "Named delegated programme, or empty"},
        "expected_outcome": {"type": "string"},
    },
    "required": ["project_name", "problem_statement", "bureau",
                 "suggested_category", "category_reason", "public_facing",
                 "touches_protected_data", "federal_program",
                 "expected_outcome"],
    "additionalProperties": False,
}


@dataclass
class Phrasing:
    text: str
    provider: str
    grounded: bool = True
    refused: bool = False
    note: str = ""


class Provider(Protocol):
    name: str
    offline: bool

    def phrase(self, question: str, hits: list[Hit]) -> Phrasing: ...
    def extract_intake(self, description: str) -> dict[str, Any]: ...


def _numbered_excerpts(hits: Iterable[Hit], limit: int = 5) -> str:
    lines = []
    for n, hit in enumerate(list(hits)[:limit], start=1):
        lines.append(f"[{n}] {hit.passage.citation}\n{hit.snippet(600)}")
    return "\n\n".join(lines)


# ------------------------------------------------------------------- offline

class LocalProvider:
    """Deterministic phrasing. Ships the fully-offline path."""

    name = "local"
    offline = True

    def phrase(self, question: str, hits: list[Hit]) -> Phrasing:
        if not hits:
            return Phrasing(
                "The governance corpus does not appear to address that.",
                self.name, grounded=False)

        best = hits[0]
        body = best.snippet(520)
        extra = ""
        if len(hits) > 1:
            extra = (f" See also {hits[1].passage.citation}"
                     f"{' and ' + hits[2].passage.citation if len(hits) > 2 else ''}.")
        return Phrasing(
            f"{best.passage.citation} states: “{body}”[1]{extra}",
            self.name,
        )

    def extract_intake(self, description: str) -> dict[str, Any]:
        """Match the description against Appendix A's 24 classified use cases."""
        from app import registry as registry_mod
        from app.retrieval import tokenize

        import math
        from collections import Counter

        rows = registry_mod.taxonomy_rows()
        # Field weights: what a use case *is* identifies it; the data it happens
        # to read is weaker evidence. Without this, "permit applications" in a
        # data-source list outranks "stormwater" in the use case's own name.
        FIELD_WEIGHTS = {
            "Use Case Category": 1.3,
            "Environmental Domain": 1.2,
            "Specific Application": 1.0,
            "Data Sources": 0.35,
        }
        weighted: list[dict[str, float]] = []
        for row in rows:
            terms: dict[str, float] = {}
            for field, weight in FIELD_WEIGHTS.items():
                for token in set(tokenize(row.get(field, ""))):
                    terms[token] = max(terms.get(token, 0.0), weight)
            weighted.append(terms)

        # Inverse document frequency: "stormwater" identifies a use case,
        # "permit" appears almost everywhere and identifies nothing.
        df: Counter = Counter()
        for terms in weighted:
            df.update(terms.keys())
        n = len(weighted) or 1

        words = set(tokenize(description))
        ranked: list[tuple[float, dict[str, str]]] = []
        for row, terms in zip(rows, weighted):
            score = sum(
                terms[t] * math.log(1 + n / (1 + df[t]))
                for t in words & terms.keys()
            )
            if score > 0:
                ranked.append((score, row))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        best_row = ranked[0][1] if ranked else None
        # Matching a description to a use case is genuinely ambiguous — a
        # stormwater permit backlog matches "Permit Review" on function and
        # "Erosion & Stormwater" on domain. Offer the alternatives rather than
        # pretending the top hit is the answer; the operator confirms at Gate 0.
        candidates = [
            {"id": row.get("ID", ""),
             "domain": row.get("Environmental Domain", ""),
             "use_case": row.get("Use Case Category", ""),
             "category": str(row.get("Category (1/2/3)", "")).strip(),
             "score": round(score, 2)}
            for score, row in ranked[:3]
        ]

        text = description.strip()
        name = re.split(r"[.\n]", text)[0][:70].strip() or "Untitled project"
        name = name[0].upper() + name[1:] if name else name

        domain = (best_row or {}).get("Environmental Domain", "")
        bureau = registry_mod._BUREAU_BY_DOMAIN.get(domain, "Operations and Services")
        try:
            category = int(str((best_row or {}).get("Category (1/2/3)", "1")).strip() or 1)
        except ValueError:
            category = 1

        public = bool(re.search(r"public|resident|citizen|applicant|community",
                                text, re.I))
        protected = bool(re.search(r"pii|personal|medical|demographic|enforcement",
                                   text, re.I))
        return {
            "project_name": name,
            "problem_statement": text[:400],
            "bureau": bureau,
            "suggested_category": category,
            "category_reason": (
                f"Closest match in Appendix A is "
                f"{(best_row or {}).get('ID', 'no close match')} "
                f"({(best_row or {}).get('Use Case Category', 'n/a')}), "
                f"Category {category}."
                if best_row else "No close match in Appendix A; defaulted to Category 1."
            ),
            "public_facing": public,
            "touches_protected_data": protected,
            "federal_program": (best_row or {}).get("Federal Program Nexus", ""),
            "expected_outcome": "",
            "_matched_taxonomy_id": (best_row or {}).get("ID", ""),
            "_candidates": candidates,
            "_provider": self.name,
        }


# ------------------------------------------------------------------ Anthropic

class AnthropicProvider:
    """claude-opus-5. Sends the question and retrieved snippets, nothing else."""

    name = "anthropic"
    offline = False

    def __init__(self, model: str = MODEL, effort: str = "medium") -> None:
        self.model = model
        self.effort = effort
        self._client: Any = None

    @property
    def client(self) -> Any:
        if self._client is None:
            import anthropic          # imported lazily so offline installs work
            self._client = anthropic.Anthropic()
        return self._client

    @staticmethod
    def available() -> bool:
        try:
            import anthropic  # noqa: F401
        except ImportError:
            return False
        return bool(os.environ.get("ANTHROPIC_API_KEY")
                    or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def _system(self) -> list[dict[str, Any]]:
        # One stable prefix, cached. Opus 5 caches from 512 tokens, so repeated
        # questions read the prefix at a fraction of the input cost.
        return [{
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        }]

    def phrase(self, question: str, hits: list[Hit]) -> Phrasing:
        if not hits:
            return Phrasing("The governance corpus does not address that.",
                            self.name, grounded=False)
        user = (f"Question: {question}\n\n"
                f"Excerpts from the SCDES governance corpus:\n\n"
                f"{_numbered_excerpts(hits)}")
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1200,
                system=self._system(),
                output_config={"effort": self.effort},
                messages=[{"role": "user", "content": user}],
            )
        except Exception as exc:                       # network, auth, rate limit
            fallback = LocalProvider().phrase(question, hits)
            fallback.note = f"{type(exc).__name__}: falling back to local phrasing"
            fallback.provider = f"{self.name}→local"
            return fallback

        if getattr(response, "stop_reason", None) == "refusal":
            return Phrasing(
                "The language provider declined to phrase this response. The "
                "retrieved sections are shown below unchanged.",
                self.name, grounded=True, refused=True)

        text = "".join(b.text for b in response.content
                       if getattr(b, "type", "") == "text").strip()
        return Phrasing(text or "No phrasing returned.", self.name)

    def extract_intake(self, description: str) -> dict[str, Any]:
        prompt = (
            "Read this plain-language description of a problem at SCDES and fill "
            "the intake fields. Suggest Category 1 for internal efficiency work, "
            "2 for anything touching public services or regulated parties, 3 for "
            "exploratory capability building. Do not invent a federal programme "
            "that is not implied.\n\n"
            f"Description:\n{description}"
        )
        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                output_config={
                    "effort": "medium",
                    "format": {"type": "json_schema", "schema": INTAKE_SCHEMA},
                },
                messages=[{"role": "user", "content": prompt}],
            )
            if getattr(response, "stop_reason", None) == "refusal":
                raise RuntimeError("provider refused")
            text = next(b.text for b in response.content
                        if getattr(b, "type", "") == "text")
            data = json.loads(text)
            data["_provider"] = self.name
            return data
        except Exception:
            data = LocalProvider().extract_intake(description)
            data["_provider"] = f"{self.name}→local"
            return data


# ------------------------------------------------------------------- selection

def get_provider(prefer: str | None = None) -> Provider:
    """Anthropic when configured and requested; otherwise the offline path."""
    choice = (prefer or os.environ.get("SCDES_PROVIDER") or "auto").lower()
    if choice in ("local", "offline"):
        return LocalProvider()
    if choice in ("anthropic", "auto") and AnthropicProvider.available():
        return AnthropicProvider()
    return LocalProvider()


def describe_provider(provider: Provider) -> str:
    if provider.offline:
        return ("Local provider — deterministic phrasing, no network. "
                "Retrieval and citation are local in every mode.")
    return (f"Anthropic {MODEL} — phrasing only. The question and the retrieved "
            f"snippets are sent; the corpus never leaves this machine.")
