"""What the agency already has — uploaded, read, and offered as evidence.

The client's instruction: *"if the user has documents/policies/governance in
effect of any kind (acceptable use policies, data governance, etc.), they should
upload those first. Those uploads should be analyzed and FULLY incorporated into
the GAIUS framework."*

An agency with an acceptable-use policy and a data-governance standard should not
be typing answers that are already written down somewhere. So uploads come first,
and every framework question is checked against them.

How "incorporated" is interpreted here, and why
-----------------------------------------------

Two readings were possible. **Absorbed**: merge the uploaded text into the
generated framework directly. **Evidence**: find the passage that answers a
question, quote it, name the file and page, and let a person confirm it.

This is the second, deliberately.

An absorbed answer is unattributable. Six months on, nobody can say whether a
clause came from the agency's own policy or from the reference regime, and the
DRAFT-to-adopted model rests on being able to say exactly that. Worse, a wrong
extraction disappears into the document instead of sitting on screen where
someone would notice it. The matching below is lexical and will sometimes be
wrong; the design has to survive that, and quoting the source does while
silently rewriting a framework does not.

So: nothing here answers anything. It finds the passage, shows it with its
filename, and the person decides. Confirming is one click, and the answer is
then theirs — recorded with what it came from.

The matching
------------

Term overlap against the question and the phrase from the reference framework
that produced it, weighted toward the rarer words. Not semantic, and not
pretending to be: this is a small corpus of the agency's own prose searched with
its own vocabulary, where an exact word match is a strong signal and a clever
one is unnecessary. Where nothing scores above the floor, nothing is offered —
a bad suggestion costs more than a missing one, because a plausible wrong quote
gets confirmed.
"""

from __future__ import annotations

import base64
import binascii
import json
import math
import re
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.authz import Actor, Target, guard

ROOT = Path(__file__).resolve().parent.parent
STORE = ROOT / "data" / "intake"
INDEX = STORE / "index.json"


def _store() -> Path:
    """Where this agency's uploaded documents live.

    One shared directory until now, which meant an agency's own policies — the
    documents it uploads precisely because they are not public — were readable
    by every other agency on the deployment, and their passages were offered as
    evidence when anyone answered a framework question. The same fault the
    client reported against the reference documents, one directory along.

    `STORE` stays as the single-tenant default so tests and the CLI are
    unaffected; see app/tenant.py.
    """
    from app import tenant
    return tenant.scoped(STORE)


def _index() -> Path:
    return _store() / INDEX.name

#: What can be read. Anything else is refused with its own name in the message,
#: rather than being accepted and silently contributing nothing.
READABLE = {".docx": "Word document", ".txt": "text file", ".md": "Markdown",
            ".pdf": "PDF"}

#: 12 MB. Comfortably above a long policy, far below anything that would stall
#: a single-threaded server reading it.
MAX_BYTES = 12 * 1024 * 1024

#: A passage must beat this to be offered.
#:
#: Set against a real county acceptable-use policy. At 0.18 every question got a
#: suggestion, including the ones the policy plainly does not answer — "why is
#: your agency doing this?" was matched to a Purpose paragraph on the strength
#: of the words "technology" and "use". At 0.45 the clauses that genuinely
#: answer something still clear it comfortably (the conflict rule at 0.82, the
#: scope arbiter at 0.61, human review at 0.68) and the noise drops out.
#:
#: Erring high is the right direction. A missing suggestion costs a person a
#: minute of typing; a plausible wrong one gets confirmed and ends up in an
#: adopted framework.
FLOOR = 0.45

_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "by", "with",
    "is", "are", "be", "as", "at", "that", "this", "it", "its", "any", "all",
    "may", "shall", "will", "must", "not", "no", "from", "which", "who", "what",
    "your", "our", "their", "you", "we", "they", "has", "have", "been", "than",
    "such", "each", "other", "into", "under", "upon", "if", "when", "where",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _terms(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", str(text or "")).lower()
    return [w for w in re.findall(r"[a-z][a-z0-9\-]{2,}", text)
            if w not in _STOP]


# ------------------------------------------------------------------ reading

def _read_docx(path: Path) -> list[str]:
    import docx
    return [p.text.strip() for p in docx.Document(str(path)).paragraphs
            if p.text.strip()]


def _read_text(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    return [p.strip() for p in re.split(r"\n\s*\n", raw) if p.strip()]


def _read_pdf(path: Path) -> list[str]:
    """Best effort, and honest when it is not enough.

    There is no PDF library in `requirements.txt` and adding one to a production
    deployment for this would be the wrong trade. Text drawn with the standard
    operators comes out; a scanned page does not, and the caller is told the
    difference rather than left with an empty document that looks read.
    """
    import zlib
    raw = path.read_bytes()
    chunks: list[str] = []
    for match in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            chunks.append(zlib.decompress(match.group(1)).decode("latin-1"))
        except Exception:                                   # noqa: BLE001
            continue
    runs: list[str] = []
    for blob in chunks:
        for m in re.finditer(r"\(((?:[^()\\]|\\.)*)\)\s*Tj", blob):
            runs.append(m.group(1))
        for m in re.finditer(r"\[(.*?)\]\s*TJ", blob, re.S):
            runs.extend(re.findall(r"\(((?:[^()\\]|\\.)*)\)", m.group(1)))
    text = " ".join(runs).replace("\\(", "(").replace("\\)", ")")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) < 200:
        return []
    return [p.strip() for p in re.split(r"(?<=[.;:])\s{2,}|\n\s*\n", text)
            if len(p.strip()) > 40]


def _extract(path: Path) -> list[str]:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return _read_docx(path)
    if suffix == ".pdf":
        return _read_pdf(path)
    return _read_text(path)


# -------------------------------------------------------------------- storage

def _load() -> dict[str, Any]:
    index = _index()
    if not index.is_file():
        return {"documents": []}
    try:
        data = json.loads(index.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {"documents": []}
    data.setdefault("documents", [])
    return data


def _save(data: dict[str, Any]) -> None:
    index = _index()
    index.parent.mkdir(parents=True, exist_ok=True)
    tmp = index.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(index)


def _safe_name(name: str) -> str:
    """No paths, no traversal — a filename and nothing else."""
    base = Path(str(name or "")).name
    base = re.sub(r"[^A-Za-z0-9._ \-]", "_", base).strip() or "upload"
    return base[:120]


# -------------------------------------------------------------------- uploading

def upload(filename: str, content_b64: str, actor: Actor, *,
           kind: str = "") -> dict[str, Any]:
    """Store one of the agency's own documents and read it.

    Guarded and audited like any other governed write. What is uploaded here
    becomes evidence attached to framework answers, so who put it there is part
    of the record.
    """
    name = _safe_name(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in READABLE:
        return {"ok": False,
                "error": f"{suffix or 'That file type'} cannot be read. "
                         f"Upload a Word document, PDF, text or Markdown file."}

    try:
        blob = base64.b64decode(content_b64 or "", validate=True)
    except (binascii.Error, ValueError):
        return {"ok": False, "error": "That upload did not arrive intact."}
    if not blob:
        return {"ok": False, "error": "That file is empty."}
    if len(blob) > MAX_BYTES:
        return {"ok": False,
                "error": f"{len(blob) // (1024 * 1024)} MB is too large. "
                         f"The limit is {MAX_BYTES // (1024 * 1024)} MB."}

    decision = guard(actor, Target.CONFIG, "upload_existing_policy",
                     detail={"file": name, "bytes": len(blob), "kind": kind})
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}

    store = _store()
    store.mkdir(parents=True, exist_ok=True)
    path = store / name
    path.write_bytes(blob)

    try:
        paragraphs = _extract(path)
    except Exception as exc:                                # noqa: BLE001
        path.unlink(missing_ok=True)
        return {"ok": False,
                "error": f"Could not read that file ({type(exc).__name__}). "
                         f"If it is a scan, the text has to be recognized "
                         f"first."}

    if not paragraphs:
        # Kept, not discarded — but the response says plainly that nothing was
        # read, rather than listing a document that contributes nothing.
        return {"ok": True, "readable": False, "file": name,
                "paragraphs": 0,
                "note": ("The file was stored but no text could be read from "
                         "it. Scanned pages need recognizing before anything "
                         "in them can be matched to a question."),
                "state": summary()}

    data = _load()
    data["documents"] = [d for d in data["documents"] if d["file"] != name]
    data["documents"].append({
        "file": name,
        "kind": (kind or "").strip()[:80],
        "type": READABLE[suffix],
        "bytes": len(blob),
        "paragraphs": paragraphs,
        "words": sum(len(p.split()) for p in paragraphs),
        "uploaded_at": _now(),
        "uploaded_by": (actor.name or actor.user_id or "")[:120],
    })
    _save(data)
    return {"ok": True, "readable": True, "file": name,
            "paragraphs": len(paragraphs), "state": summary()}


def remove(filename: str, actor: Actor) -> dict[str, Any]:
    name = _safe_name(filename)
    decision = guard(actor, Target.CONFIG, "remove_existing_policy",
                     detail={"file": name})
    if not decision.allowed:
        return {"ok": False, "error": decision.reason}
    data = _load()
    before = len(data["documents"])
    data["documents"] = [d for d in data["documents"] if d["file"] != name]
    _save(data)
    (_store() / name).unlink(missing_ok=True)
    return {"ok": before != len(data["documents"]), "state": summary()}


# -------------------------------------------------------------------- matching

def _idf(documents: list[dict[str, Any]]) -> dict[str, float]:
    """Rarer words count for more. Otherwise every paragraph containing "agency"
    scores, and the top hit is whichever one is longest."""
    seen: Counter = Counter()
    total = 0
    for doc in documents:
        for para in doc["paragraphs"]:
            total += 1
            for term in set(_terms(para)):
                seen[term] += 1
    return {t: math.log(1 + total / (1 + n)) for t, n in seen.items()}


def evidence_for(query: str, *, limit: int = 2,
                 documents: list[dict[str, Any]] | None = None,
                 idf: dict[str, float] | None = None) -> list[dict[str, Any]]:
    """Passages from the agency's own documents that may answer this.

    Returns nothing rather than a weak guess. A plausible wrong quote is worse
    than none, because a plausible wrong quote gets confirmed.

    `documents` and `idf` may be passed in so a whole step's questions are
    matched against one reading of the documents rather than one per question.
    """
    if documents is None:
        documents = _load()["documents"]
    if not documents:
        return []

    wanted = set(_terms(query))
    if not wanted:
        return []
    idf = idf if idf is not None else _idf(documents)
    ceiling = sum(idf.get(t, 0.0) for t in wanted) or 1.0

    hits: list[dict[str, Any]] = []
    for doc in documents:
        for i, para in enumerate(doc["paragraphs"]):
            terms = set(_terms(para))
            if not terms:
                continue
            overlap = wanted & terms
            if len(overlap) < 2:
                continue
            score = sum(idf.get(t, 0.0) for t in overlap) / ceiling
            # Long paragraphs match more words by accident; damp them lightly
            # rather than excluding them, since real policy clauses are long.
            score /= 1 + math.log(1 + len(terms) / 40)
            if score >= FLOOR:
                hits.append({
                    "file": doc["file"], "kind": doc.get("kind", ""),
                    "paragraph": i,
                    "quote": para if len(para) <= 700 else para[:700] + "…",
                    "score": round(score, 3),
                    "matched": sorted(overlap)[:8],
                })
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def evidence_for_row(row: dict[str, Any], *, limit: int = 2) -> list[dict[str, Any]]:
    """Evidence for one register row, queried on its own words.

    Both the question and the source phrase are used. The source phrase carries
    the reference framework's vocabulary, which is often the vocabulary the
    agency's own policy uses too.
    """
    query = " ".join([row.get("question", ""), row.get("source_phrase", ""),
                      row.get("default", "")])
    return evidence_for(query, limit=limit)


# ------------------------------------------------------- Module One questions

#: How strongly a passage has to point at one option before that option is
#: offered. Below it, the passage is still shown — the person reads it and
#: chooses — but nothing is offered as "this reads like". The same reasoning
#: as FLOOR: a plausible wrong choice gets confirmed.
OPTION_FLOOR = 0.34
#: The winning option has to beat the next one by this much, so a passage
#: that fits two answers equally never picks one of them.
OPTION_MARGIN = 1.5

#: Question kinds a passage can answer. A grid of levels, a list of rows or a
#: set of tiers is never filled from prose; the passage is shown to help, and
#: the person fills the grid.
_SUGGESTS = {"single", "multi", "short", "long"}

#: What a text answer taken from a passage may hold.
_SHORT_MAX, _LONG_MAX = 400, 2000


#: Words nearly every governance sentence contains. They say a passage is
#: about governance, never which question it answers — with a short policy
#: they carried "Chief Information Officer" to a question about information
#: that must never go into a tool. They never count toward a match here.
_GENERIC = {
    "tool", "tools", "information", "organization", "organizations",
    "agency", "agencies", "use", "used", "using", "uses", "county", "city",
    "policy", "policies", "decision", "decisions", "whether", "system",
    "systems", "artificial", "intelligence", "staff", "employee",
    "employees", "given", "determine", "determines", "determined", "new",
    "existing", "particular", "set", "something", "anything", "one", "ones",
    "there", "would", "should", "could", "can", "does", "did", "done", "get",
    "make", "made", "also", "only", "more", "most", "about", "over", "then",
    "these", "those", "them", "his", "her", "own", "yes", "kind", "kinds",
    "way", "ways", "time", "times", "part", "within", "without", "subject",
    # Found by running every question against a real adopted framework:
    # these matched everywhere and decided nothing.
    "framework", "frameworks", "governance", "how", "every", "before",
    "after", "matter", "matters", "person", "people", "later", "level",
    "levels", "out", "currently", "need", "needs", "carried", "apply",
    "applies", "applied", "two", "three", "right", "rights", "work",
    "documented", "document", "documents", "documentation", "approved",
    "approve", "rule", "rules", "follow", "follows", "structure", "case",
    "cases", "include", "includes", "including", "require", "required",
    "requires", "requirement", "process", "processes", "role", "roles",
    "responsible", "general", "specific", "provide", "provides", "ensure",
}

#: The same idea in different words, where a policy's wording routinely
#: differs from a choice's. Kept short and literal on purpose — this is a
#: word match, not an interpretation.
_SAME = {"stringent": "strict", "stricter": "strict", "strictest": "strict",
         "prohibited": "prohibit", "prohibits": "prohibit",
         "forbidden": "prohibit", "forbids": "prohibit"}


def _norm(term: str) -> str:
    term = _SAME.get(term, term)
    if len(term) > 4 and term.endswith("s") and not term.endswith("ss"):
        term = term[:-1]
    return _SAME.get(term, term)


def _qterms(text: str) -> set[str]:
    out = set()
    for t in _terms(text):
        if t in _GENERIC:
            continue
        n = _norm(t)
        if n not in _GENERIC:
            out.add(n)
    return out


def _weight(term: str, idf: dict[str, float], top: float) -> float:
    # A word the documents never use is rare by definition, not worthless.
    return idf.get(term, top)


def _option_scores(passage_terms: set[str], options: list[dict[str, Any]],
                   asked: set[str], idf: dict[str, float]
                   ) -> list[tuple[float, int, dict[str, Any]]]:
    """How strongly the passage names each option, on the option's own
    words — never the question's. "The state or federal rule" matched a
    passage only because the question itself says "state or federal"."""
    top = max(idf.values(), default=1.0)
    scored = []
    for option in options:
        if option.get("value") in ("unknown", "", None):
            continue
        words = _qterms(option.get("label", "")) - asked
        if not words:
            continue
        ceiling = sum(_weight(t, idf, top) for t in words) or 1.0
        hit = words & passage_terms
        scored.append((sum(_weight(t, idf, top) for t in hit) / ceiling,
                       len(hit), option))
    scored.sort(key=lambda s: -s[0])
    return scored


def _suggest(question: dict[str, Any], passage: str,
             idf: dict[str, float]) -> dict[str, Any] | None:
    """What this passage would fill in for this question, or None.

    Single choice: one option, only where the passage clearly names it in
    that option's own words. Multiple choice: every option it names on at
    least two of that option's own words. Text: the passage itself.
    """
    kind = question.get("kind")
    if kind not in _SUGGESTS:
        return None
    if kind in ("short", "long"):
        limit = _SHORT_MAX if kind == "short" else _LONG_MAX
        text = passage.strip()
        return {"value": text[:limit], "labels": [],
                "trimmed": len(text) > limit}
    asked = _qterms(" ".join(str(question.get(k) or "")
                             for k in ("prompt", "help", "above")))
    terms = _qterms(passage)
    scored = _option_scores(terms, question.get("options") or [], asked, idf)
    if not scored:
        return None
    if kind == "single":
        best, hits, option = scored[0]
        runner = scored[1][0] if len(scored) > 1 else 0.0
        # Two of the option's own words, or one that is rare in these
        # documents. "Case by case" matched every "use case" on one word.
        top = max(idf.values(), default=1.0)
        own = (_qterms(option.get("label", "")) - asked) & terms
        rare_one = hits == 1 and all(_weight(t, idf, top) >= 0.75 * top
                                     for t in own)
        if (hits >= 2 or rare_one) and best >= OPTION_FLOOR and \
                best > runner and best >= runner * OPTION_MARGIN:
            return {"value": option["value"], "labels": [option["label"]],
                    "own_words": hits}
        return None
    picked = [o for s, hits, o in scored if hits >= 2 and s >= OPTION_FLOOR]
    if picked:
        return {"value": [o["value"] for o in picked],
                "labels": [o["label"] for o in picked], "own_words": 2}
    return None


#: How many of the question's own specific words a passage has to share.
#: Three from anywhere in the question, or two that are both in the question
#: itself rather than its help text. Counted on specific words only — the
#: generic governance vocabulary above never counts.
MIN_SHARED, MIN_SHARED_IN_PROMPT = 3, 2


def _question_hits(query: str, documents: list[dict[str, Any]],
                   idf: dict[str, float], limit: int, *,
                   prompt: str = "") -> list[dict[str, Any]]:
    """Passages that share enough of the question's own specific words,
    ranked toward the rarer ones."""
    wanted = _qterms(query)
    asked = _qterms(prompt) if prompt else wanted
    if len(wanted) < 2:
        return []
    top = max(idf.values(), default=1.0)
    hits = []
    for doc in documents:
        for i, para in enumerate(doc["paragraphs"]):
            terms = _qterms(para)
            overlap = wanted & terms
            enough = len(overlap) >= MIN_SHARED or (
                len(overlap) >= MIN_SHARED_IN_PROMPT and overlap <= asked)
            if not enough:
                continue
            score = sum(_weight(t, idf, top) for t in overlap) / (top * 5)
            score /= 1 + math.log(1 + len(terms) / 40)
            if enough:
                hits.append({
                    "file": doc["file"], "kind": doc.get("kind", ""),
                    "paragraph": i,
                    "quote": para if len(para) <= 700 else para[:700] + "…",
                    "score": round(score, 3), "matched": sorted(overlap)[:8]})
    hits.sort(key=lambda h: -h["score"])
    return hits[:limit]


def matcher() -> tuple[list[dict[str, Any]], dict[str, float]] | None:
    """One reading of this organization's documents, for a whole step."""
    documents = _load()["documents"]
    if not documents:
        return None
    return documents, _idf(documents)


def evidence_for_question(question: dict[str, Any], *, limit: int = 2,
                          context: tuple | None = None
                          ) -> list[dict[str, Any]]:
    """Passages that may answer one Module One question, each with what it
    would fill in where that is clear.

    Queried on the question's own words — the prompt, the help and the line
    above it — never on its option labels, which would match every passage
    that happens to mention one of the choices.
    """
    context = context or matcher()
    if not context:
        return []
    documents, idf = context
    query = " ".join(str(question.get(k) or "")
                     for k in ("prompt", "help", "above"))
    hits = _question_hits(query, documents, idf, limit,
                          prompt=str(question.get("prompt") or ""))
    by_file = {d["file"]: d for d in documents}
    for hit in hits:
        full = by_file[hit["file"]]["paragraphs"][hit["paragraph"]]
        # Something is offered to fill in only where it is clear: the passage
        # is firmly about this question (three of its specific words), or it
        # names a choice in two of that choice's own words. A looser match is
        # still shown, to read, with nothing offered.
        s = _suggest(question, full, idf)
        firm = len(hit["matched"]) >= MIN_SHARED
        if s and not (firm or s.get("own_words", 0) >= 2):
            s = None
        if s:
            s.pop("own_words", None)
        hit["suggest"] = s
    return hits


def passage(file: str, paragraph: int) -> str:
    """The passage a recorded answer names as its source, or empty."""
    for doc in _load()["documents"]:
        if doc["file"] == file:
            paras = doc.get("paragraphs") or []
            if isinstance(paragraph, int) and 0 <= paragraph < len(paras):
                return paras[paragraph]
    return ""


# ------------------------------------------------------------------ reporting

def documents() -> list[dict[str, Any]]:
    return [{k: v for k, v in d.items() if k != "paragraphs"}
            for d in _load()["documents"]]


def summary() -> dict[str, Any]:
    docs = documents()
    return {
        "documents": docs,
        "count": len(docs),
        "words": sum(d.get("words", 0) for d in docs),
        "accepts": sorted(READABLE),
        "max_mb": MAX_BYTES // (1024 * 1024),
        "why": ("If your agency already has an acceptable use policy, a data "
                "governance standard, a records policy or anything similar in "
                "effect, upload it first. Every question in the builder is "
                "checked against what you upload, and where a passage in your "
                "own documents appears to answer one, it is shown beside that "
                "question with the file it came from."),
        "how": ("Nothing is answered on your behalf. Choose to use a passage "
                "and it becomes your answer, recorded with the document it "
                "came from; change the answer later and it is simply yours. "
                "The matching looks for your own words, not their meaning, so "
                "read the passage before you use it."),
    }
