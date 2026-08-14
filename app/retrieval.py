"""Local cited search over the governed corpus.

BM25 over heading-scoped chunks. Lexical rather than semantic on purpose: this
corpus is dense regulatory prose searched with its own vocabulary ("Gate 3",
"Tier B", "Federal Program Nexus"), the chunk boundary *is* the citation, and it
runs with no model download and no network.

The index lives on disk under corpus/index/ and is rebuilt from the documents.
"""

from __future__ import annotations

import json
import math
import pickle
import re
from collections import Counter
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from typing import Any, Iterable

from app.audit import CORPUS
from app.ingest_docx import Chunk, parse_all as parse_docs
from app.ingest_xlsx import parse_all as parse_appendices

INDEX_DIR = CORPUS / "index"
INDEX_FILE = INDEX_DIR / "bm25.pkl"

K1, B = 1.5, 0.75

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "is", "are", "for", "on",
    "that", "this", "it", "as", "be", "by", "with", "at", "from", "shall",
    "any", "all", "which", "may", "not", "if", "each", "its", "these", "such",
    "was", "were", "has", "have", "will", "than", "then", "when", "where",
}

_TOKEN = re.compile(r"[a-z0-9]+(?:\.[0-9]+)*", re.I)


def tokenize(text: str) -> list[str]:
    tokens = [t.lower() for t in _TOKEN.findall(text or "")]
    return [t for t in tokens if t not in _STOP and len(t) > 1]


@dataclass
class Passage:
    """One retrievable unit — a document section or an appendix block."""
    passage_id: str
    source: str            # "document" | "appendix"
    label: str             # doc label or "Appendix G — Project Intake Form"
    citation: str
    heading: str
    section: str
    text: str
    authoritative: bool = True
    sheet: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "passage_id": self.passage_id, "source": self.source,
            "label": self.label, "citation": self.citation,
            "heading": self.heading, "section": self.section,
            "text": self.text, "authoritative": self.authoritative,
            "sheet": self.sheet,
        }


@dataclass
class Hit:
    passage: Passage
    score: float
    matched: list[str] = dc_field(default_factory=list)
    coverage: float = 0.0      # fraction of the question's content terms found
    phrases: list[str] = dc_field(default_factory=list)

    def snippet(self, limit: int = 420) -> str:
        """The part of the passage that actually answers, not just the head."""
        text = self.passage.text
        if len(text) <= limit:
            return text
        sentences = re.split(r"(?<=[.;])\s+", text)
        best, best_score = 0, -1
        for i in range(len(sentences)):
            window, n = [], i
            while n < len(sentences) and len(" ".join(window)) < limit:
                window.append(sentences[n])
                n += 1
            blob = " ".join(window).lower()
            score = sum(blob.count(m) for m in self.matched)
            if score > best_score:
                best, best_score = i, score
        window, n = [], best
        while n < len(sentences) and len(" ".join(window)) < limit:
            window.append(sentences[n])
            n += 1
        out = " ".join(window)
        return ("…" if best else "") + out + ("…" if n < len(sentences) else "")


@dataclass
class Index:
    passages: list[Passage] = dc_field(default_factory=list)
    doc_tokens: list[Counter] = dc_field(default_factory=list)
    doc_len: list[int] = dc_field(default_factory=list)
    df: Counter = dc_field(default_factory=Counter)
    avg_len: float = 0.0

    @property
    def size(self) -> int:
        return len(self.passages)


# ------------------------------------------------------------------- building

def _appendix_passages() -> list[Passage]:
    passages: list[Passage] = []
    for schema in parse_appendices():
        for sheet in schema.sheets:
            for block in sheet.blocks:
                parts: list[str] = []
                if block.title:
                    parts.append(block.title)
                if block.columns:
                    parts.append(" | ".join(block.columns))
                for row in block.sample_rows[:12]:
                    parts.append(" | ".join(v for v in row.values() if v))
                for field in block.fields[:30]:
                    bits = [field.label]
                    if field.options:
                        bits.append("options: " + " / ".join(field.options))
                    if field.help_text:
                        bits.append(field.help_text)
                    parts.append(" — ".join(bits))
                text = "\n".join(p for p in parts if p).strip()
                if len(text) < 20:
                    continue
                where = f"{schema.title}"
                if sheet.name and sheet.name.lower() not in where.lower():
                    where += f" · {sheet.name}"
                citation = where + (f" · {block.title}" if block.title else "")
                passages.append(Passage(
                    passage_id=f"app:{schema.letter}:{sheet.name}:{block.first_row}",
                    source="appendix", label=schema.title, citation=citation,
                    heading=block.title or sheet.name, section="",
                    text=text, sheet=sheet.name,
                ))
    return passages


def _document_passages() -> list[Passage]:
    passages: list[Passage] = []
    for doc in parse_docs():
        for chunk in doc.chunks:
            if len(chunk.text) < 20 and not chunk.heading:
                continue
            body = f"{chunk.heading}\n{chunk.text}".strip()
            passages.append(Passage(
                passage_id=f"doc:{chunk.doc_id}:{chunk.order}",
                source="document", label=chunk.doc_label,
                citation=chunk.citation, heading=chunk.heading,
                section=chunk.section, text=body,
                authoritative=chunk.authoritative,
            ))
    return passages


def build(save_to_disk: bool = True) -> Index:
    passages = _document_passages() + _appendix_passages()
    index = Index(passages=passages)
    for passage in passages:
        tokens = tokenize(f"{passage.label} {passage.heading} {passage.text}")
        counts = Counter(tokens)
        index.doc_tokens.append(counts)
        index.doc_len.append(len(tokens))
        for term in counts:
            index.df[term] += 1
    index.avg_len = (sum(index.doc_len) / len(index.doc_len)) if index.doc_len else 0.0

    if save_to_disk:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        with INDEX_FILE.open("wb") as fh:
            pickle.dump(index, fh)
        (INDEX_DIR / "passages.json").write_text(
            json.dumps([p.as_dict() for p in passages][:5], indent=2),
            encoding="utf-8")
    return index


_index: Index | None = None


def get_index(rebuild: bool = False) -> Index:
    global _index
    if _index is not None and not rebuild:
        return _index
    if INDEX_FILE.exists() and not rebuild:
        try:
            with INDEX_FILE.open("rb") as fh:
                _index = pickle.load(fh)
                return _index
        except Exception:
            pass
    _index = build()
    return _index


# ------------------------------------------------------------------ searching

def _bigrams(terms: list[str]) -> list[str]:
    return [f"{a} {b}" for a, b in zip(terms, terms[1:])]


def search(query: str, *, top_k: int = 5, authoritative_only: bool = False,
           index: Index | None = None) -> list[Hit]:
    index = index or get_index()
    terms = tokenize(query)
    if not terms or index.size == 0:
        return []

    unique = set(terms)
    query_bigrams = _bigrams(terms)
    n = index.size
    idf = {
        t: math.log(1 + (n - index.df.get(t, 0) + 0.5) / (index.df.get(t, 0) + 0.5))
        for t in unique
    }

    scored: list[Hit] = []
    for i, passage in enumerate(index.passages):
        if authoritative_only and not passage.authoritative:
            continue
        counts = index.doc_tokens[i]
        length = index.doc_len[i] or 1
        score, matched = 0.0, []
        for term in unique:
            freq = counts.get(term, 0)
            if not freq:
                continue
            matched.append(term)
            denom = freq + K1 * (1 - B + B * length / (index.avg_len or 1))
            score += idf[term] * (freq * (K1 + 1)) / denom
        if score <= 0:
            continue

        # "Gate 2" and "Level 2" only mean something as phrases — a passage that
        # contains the literal phrase is answering the question that was asked,
        # and one whose *heading* is that phrase is the rule itself rather than
        # a cross-reference to it.
        heading_l = passage.heading.lower()
        haystack = f"{heading_l} {passage.text}".lower()
        phrases = [bg for bg in query_bigrams if bg in haystack]
        heading_phrases = [bg for bg in query_bigrams if bg in heading_l]
        if phrases:
            score *= 1.0 + 0.45 * len(phrases)
        if heading_phrases:
            score *= 1.0 + 1.1 * len(heading_phrases)

        # A section whose heading carries the query terms is the rule itself.
        heading_terms = set(tokenize(passage.heading))
        if heading_terms:
            overlap = len(heading_terms & unique) / len(unique)
            score *= 1.0 + 0.9 * overlap

        # The Framework and Manual are the authorities; appendices are the
        # instruments; supporting documents only inform.
        if not passage.authoritative:
            score *= 0.5
        elif passage.source == "appendix":
            score *= 0.8
        elif passage.section:
            score *= 1.15

        # Coverage weighted by IDF: failing to match a rare, load-bearing term
        # ("gate", "incident") matters; failing to match "require" does not.
        total_idf = sum(idf[t] for t in unique) or 1.0
        covered_idf = sum(idf[t] for t in matched)
        scored.append(Hit(
            passage=passage, score=round(score, 4), matched=matched,
            coverage=round(covered_idf / total_idf, 3), phrases=phrases,
        ))

    scored.sort(key=lambda h: h.score, reverse=True)
    return scored[:top_k]


#: A single rare-term match is not an answer. "What is the best pizza topping?"
#: hits "best" in "best practices" and would otherwise score well, so scope is
#: judged on how much of the question the corpus actually covers.
#: Calibrated against the corpus: off-topic questions ("pizza", "driver
#: licence", "capital of France") cover 0.17-0.21 of the query's IDF mass,
#: while real governance questions cover 0.37-0.83. The gap is wide and the
#: threshold sits in it.
IN_SCOPE_SCORE = 6.0
IN_SCOPE_COVERAGE = 0.30


def in_scope(hits: Iterable[Hit]) -> bool:
    hits = list(hits)
    if not hits:
        return False
    best = hits[0]
    return best.score >= IN_SCOPE_SCORE and best.coverage >= IN_SCOPE_COVERAGE
