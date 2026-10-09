"""Agency profile — everything that differs between agencies, discovered.

This application is not an SCDES application. It is a governance-operating
application that is *pointed at* an agency's adopted corpus. Nothing about a
particular agency belongs in code: not its name, not its bureaus, not how many
instruments it adopted, not what it calls them, not its gate structure, not its
statutory programs, not its adoption date.

All of that is **discovered** from the corpus on first run and written to
`corpus/config/agency.yaml`, which a human then confirms. Discovery is by
content and structure, never by filename, because filenames are the least
reliable thing an agency will hand you.

Deliberately not assumed:
  · that instruments are lettered A–N (they may be 1–12, or Schedules, or Forms)
  · that there are six gates numbered 0–5
  · that the agency is environmental, or has bureaus at all
  · that a charter exists, or carries a legible date
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, asdict, field as dc_field
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from app.audit import CORPUS, atomic_write

PROFILE_FILE = CORPUS / "config" / "agency.yaml"

# --------------------------------------------------------------- signals
#
# Documents are classified by what they say about themselves, not by filename.

DOC_SIGNALS: dict[str, list[str]] = {
    "framework": [
        r"\bgovernance framework\b", r"\bthis framework\b",
        r"\bframework establishes\b", r"\bpolicy framework\b",
    ],
    "manual": [
        r"\boperations manual\b", r"\bthis manual\b", r"\bprocedures manual\b",
        r"\bmanual (?:establishes|sets out|describes)\b",
    ],
    "charter": [
        r"\bcharter\b", r"\badoption memo\b", r"\bexecuted\b",
        r"\bhereby (?:adopt|establish)\b",
    ],
    "directive": [
        r"\bdirective\b", r"\beffective .{0,20}(?:are|is) binding\b",
        r"\bbinding across all\b",
    ],
    "procedures": [
        r"\boperating procedures\b", r"\bcouncil operating\b",
        r"\bquorum\b.{0,200}\bmeeting\b",
    ],
}

#: Nouns an agency might use for its operational instruments.
INSTRUMENT_NOUNS = ["Appendix", "Appendices", "Attachment", "Schedule",
                    "Annex", "Exhibit", "Form", "Tool"]

#: Nouns an agency might use for lifecycle checkpoints.
GATE_NOUNS = ["Gate", "Stage", "Phase", "Checkpoint", "Milestone", "Step"]

#: What an instrument is *for* — inferred from its own title, so the app can
#: find "the risk instrument" without knowing it is called Appendix B.
INSTRUMENT_ROLES: dict[str, list[str]] = {
    "taxonomy": [r"taxonomy", r"use case catalog"],
    "risk_model": [r"risk (classification|matrix|scoring)", r"risk assessment"],
    "registry": [r"registry", r"inventory of .*systems"],
    "data_readiness": [r"data readiness", r"data quality assessment"],
    "vendor_disclosure": [r"vendor .*disclosure", r"supplier disclosure"],
    "community_impact": [r"community impact", r"disparate impact",
                         r"equity (screening|assessment)"],
    "intake": [r"intake", r"project request", r"proposal form"],
    "gate_checklists": [r"gate review", r"stage[- ]gate", r"review checklist"],
    "capability_survey": [r"capability survey", r"technology .*survey",
                          r"contract .*survey"],
    "evaluation": [r"evaluation methodology", r"stopping rule",
                   r"performance evaluation"],
    "model_card": [r"model card", r"system documentation"],
    "incident": [r"incident report", r"incident form"],
    "authorities": [r"table of authorities", r"legal authorities"],
    "council_procedures": [r"operating procedures", r"council procedures"],
}

_TITLE_CASE_ROLE = re.compile(
    r"\b((?:Chief|Deputy|Assistant|Associate|Executive)?\s?"
    r"(?:[A-Z][a-z]{2,}\s){0,3}"
    r"(?:Officer|Director|Counsel|Chief|Strategist|Chair|Owner|Manager|"
    r"Coordinator|Administrator|Secretary|Analyst|Lead))\b")

_ROLE_STOPWORDS = {
    "The Owner", "Data Owner Has", "This Officer", "An Officer", "A Director",
}

_SIGNED_DATE = re.compile(
    r"(?:executed|signed|adopted|effective|dated)\D{0,30}"
    r"(?:on\s+)?(\d{1,2}[/-]\d{1,2}[/-](?:20)?\d{2}"
    r"|(?:January|February|March|April|May|June|July|August|September|"
    r"October|November|December)\s+\d{1,2},\s+\d{4})", re.I)

_MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october "
    "november december".split())}


# ----------------------------------------------------------------- dataclass

@dataclass
class Instrument:
    key: str                  # "B", "3", "II" — whatever the agency uses
    title: str
    filename: str
    role: str = ""            # taxonomy | risk_model | … | "" if unrecognised
    sheets: int = 0
    fields: int = 0


@dataclass
class Gate:
    key: str
    name: str
    source_sheet: str = ""
    requirements: int = 0


@dataclass
class AgencyProfile:
    name: str = ""
    short_name: str = ""
    jurisdiction: str = ""
    naming_rule: str = ""
    documents: dict[str, dict[str, Any]] = dc_field(default_factory=dict)
    instrument_noun: str = "Appendix"
    instrument_keys: list[str] = dc_field(default_factory=list)
    instruments: dict[str, dict[str, Any]] = dc_field(default_factory=dict)
    gate_noun: str = "Gate"
    gates: list[dict[str, Any]] = dc_field(default_factory=list)
    roles: list[str] = dc_field(default_factory=list)
    org_units: list[str] = dc_field(default_factory=list)
    statutory_programmes: list[str] = dc_field(default_factory=list)
    adoption_date: str | None = None
    adoption_source: str = ""
    confirmed: bool = False
    discovered_at: str = ""
    notes: list[str] = dc_field(default_factory=list)

    # -- convenience -----------------------------------------------------

    def instrument_for(self, role: str) -> str | None:
        for key, meta in self.instruments.items():
            if meta.get("role") == role:
                return key
        return None

    def instrument_label(self, key: str) -> str:
        title = self.instruments.get(key, {}).get("title", "")
        return f"{self.instrument_noun} {key}" + (f" — {title}" if title else "")

    def gate_keys(self) -> list[str]:
        return [g["key"] for g in self.gates]

    def gate_name(self, key: str | int) -> str:
        for g in self.gates:
            if str(g["key"]) == str(key):
                return g["name"]
        return ""

    def adoption(self) -> date | None:
        if not self.adoption_date:
            return None
        try:
            return date.fromisoformat(self.adoption_date)
        except ValueError:
            return None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


# ----------------------------------------------------------------- discovery

def _classify_document(text: str) -> str:
    head = text[:6000].lower()
    scores = {}
    for kind, patterns in DOC_SIGNALS.items():
        scores[kind] = sum(len(re.findall(p, head, re.I)) for p in patterns)
    best = max(scores, key=scores.get)
    return best if scores[best] else ""


#: No '.' in the word class: it would let the prefix run back across a sentence
#: boundary ("…Board Chair. Ohio Department of Health Services").
_AGENCY_NAME = re.compile(
    r"\b((?:[A-Z][A-Za-z'-]+\s){1,5}"
    r"(?:Department|Agency|Authority|Commission|Bureau|Board)"
    r"(?:\s+of\s+(?:[A-Z][A-Za-z'-]+\s?){1,4})?)")


def _agency_names(sources: list[str], primary: str = "") -> tuple[str, str, str]:
    """Full name, short name and jurisdiction, taken from the corpus itself.

    Sources are scanned separately, never concatenated, so a match cannot run
    from the end of one block into the start of the next.

    A corpus names other agencies — a procurement authority, a federal
    regulator — often enough to out-count its owner, so two signals break the
    tie: a name stated near the top of the governing document, and a name
    immediately followed by the abbreviation used everywhere else. The second
    matters most, because a framework often uses only its own initialism after
    the title page and spells the name out just once.
    """
    full = short = jurisdiction = ""
    opening = primary[:4000]
    text = "\n".join(sources)

    seen: Counter = Counter()
    introduces_itself: set[str] = set()
    for source in sources:
        for m in _AGENCY_NAME.finditer(source):
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .,")
            if len(name) < 12:
                continue
            seen[name] += 1
            if re.search(re.escape(name) + r"\s*\([A-Z]{2,8}\)", source):
                introduces_itself.add(name)

    # Each signal counts once. Scoring per occurrence would let a frequently
    # cited *other* agency — a procurement authority, say — outrank the owner
    # simply by being mentioned more often in operational text.
    candidates: Counter = Counter()
    for name, count in seen.items():
        candidates[name] = (
            min(count, 5)
            + (15 if name in opening else 0)
            + (40 if name in introduces_itself else 0)
        )
    if candidates:
        full = max(candidates,
                   key=lambda n: (candidates[n], 2 if " of " in n else 0, len(n)))
        # The match often runs on into the document's own title
        # ("… Health Services AI Governance Framework"). Cut it back.
        full = re.split(
            r"\s+(?:AI|Artificial Intelligence|Governance|Enterprise|Policy|"
            r"Framework|Manual|Operations)\b", full)[0].strip(" .,")
    # "… Services (SCDES)" — the agency states its own abbreviation.
    # An agency states its own abbreviation once, in brackets after its name.
    m2 = re.search(re.escape(full) + r"[^()]{0,60}\(([A-Z]{2,8})\)", text) \
        if full else None
    if m2:
        short = m2.group(1)
    else:
        skip = {"THE", "AND", "FOR", "NIST", "API", "PII", "FOIA", "DATE",
                *(n.upper() for n in INSTRUMENT_NOUNS),
                *(n.upper() for n in GATE_NOUNS)}
        # Prefer an acronym whose letters trace the agency's own name.
        initials = "".join(w[0] for w in full.split() if w[:1].isupper()) if full else ""
        acronyms = Counter(re.findall(r"\b([A-Z]{3,8})\b", text[:40000]))
        ranked = sorted(acronyms, key=lambda t: (t == initials, acronyms[t]),
                        reverse=True)
        short = next((t for t in ranked if t not in skip), "")
    states = ("Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|"
              "Delaware|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|"
              "Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|"
              "Minnesota|Mississippi|Missouri|Montana|Nebraska|Nevada|"
              "New Hampshire|New Jersey|New Mexico|New York|North Carolina|"
              "North Dakota|Ohio|Oklahoma|Oregon|Pennsylvania|Rhode Island|"
              "South Carolina|South Dakota|Tennessee|Texas|Utah|Vermont|"
              "Virginia|Washington|West Virginia|Wisconsin|Wyoming")
    m3 = re.search(rf"\b({states})\b", text)
    if m3:
        jurisdiction = m3.group(1)
    return full, short, jurisdiction


def _discover_instruments(appendices) -> tuple[str, dict[str, dict[str, Any]]]:
    nouns = Counter()
    instruments: dict[str, dict[str, Any]] = {}
    for schema in appendices:
        raw = (schema.title or "").strip()
        m = re.match(r"\s*(%s)\s+([A-Z0-9IVX]+)" % "|".join(INSTRUMENT_NOUNS),
                     raw, re.I)
        if m:
            nouns[m.group(1).title()] += 1
        # The leading "Appendix H" may be followed by a dash, or by prose
        # ("APPENDIX H to the … Manual — Authority: …"). Strip either shape.
        title = re.sub(r"^\s*(?:%s)\s+[A-Z0-9IVX]+\s*(?:[—–:-]\s*|to the\s+)"
                       % "|".join(INSTRUMENT_NOUNS), "", raw, flags=re.I)
        title = re.split(r"\s*[|;]|\s+Authority:|\s+Related:|\s+—\s+Authority",
                         title)[0]
        title = title.strip(" .:—–-")[:80]

        role = ""
        # Filenames separate words with underscores; normalise before matching
        # or "Gate_Review_Checklists" never matches "gate review".
        blob = f"{title} {schema.source_file}".lower().replace("_", " ")
        for candidate, patterns in INSTRUMENT_ROLES.items():
            if any(re.search(p, blob) for p in patterns):
                role = candidate
                break

        instruments[schema.letter] = {
            "title": title, "filename": schema.source_file, "role": role,
            "sheets": len(schema.sheets), "fields": schema.field_count,
        }
    noun = nouns.most_common(1)[0][0] if nouns else "Appendix"

    # An instrument need not be a workbook. Agencies routinely issue one or two
    # as prose — SCDES's Council Operating Procedures is a .docx — and leaving
    # it out makes every reference to it look like a dangling citation.
    pattern = re.compile(r"^\s*(?:%s)[ _]([A-Z0-9]{1,3})\b[ _]*(.*)"
                         % "|".join(INSTRUMENT_NOUNS), re.I)
    for path in sorted(CORPUS.rglob("*.docx")):
        if path.name.startswith("~$"):
            continue
        m = pattern.match(path.stem.replace("_", " "))
        if not m:
            continue
        key = m.group(1).upper()
        if key in instruments:
            continue
        title = re.sub(r"\s+", " ", m.group(2)).strip()
        role = ""
        blob = f"{title} {path.stem}".lower().replace("_", " ")
        for candidate, patterns in INSTRUMENT_ROLES.items():
            if any(re.search(p, blob) for p in patterns):
                role = candidate
                break
        instruments[key] = {"title": title, "filename": path.name,
                            "role": role, "sheets": 0, "fields": 0,
                            "format": "document"}
    return noun, instruments


def _discover_gates(appendices, instruments) -> tuple[str, list[dict[str, Any]]]:
    """Find the checklist instrument and read its lifecycle out of the sheets."""
    key = next((k for k, m in instruments.items()
                if m.get("role") == "gate_checklists"), None)
    if key is None:
        return "Gate", []
    schema = next((s for s in appendices if s.letter == key), None)
    if schema is None:
        return "Gate", []

    noun_counts = Counter()
    gates: list[dict[str, Any]] = []
    for sheet in schema.sheets:
        m = re.match(r"\s*(%s)\s*([0-9]+|[IVX]+)\s*[-–—:.]?\s*(.*)"
                     % "|".join(GATE_NOUNS), sheet.name, re.I)
        if not m:
            continue
        noun_counts[m.group(1).title()] += 1
        name = m.group(3).strip() or sheet.name
        # Prefer the fuller title printed inside the sheet.
        for block in sheet.blocks:
            if block.kind == "note" and "CHECKLIST" in block.title.upper():
                after = re.split(r"[—–-]", block.title)
                if len(after) > 1:
                    name = after[-1].strip().title()
                break
        gates.append({
            "key": m.group(2), "name": name, "source_sheet": sheet.name,
            "requirements": sum(len(b.sample_rows) for b in sheet.blocks
                                if b.kind == "checklist"),
        })
    noun = noun_counts.most_common(1)[0][0] if noun_counts else "Gate"
    return noun, gates


def _discover_roles(framework_text: str, manual_text: str) -> list[str]:
    counts = Counter()
    for blob, weight in ((framework_text, 2), (manual_text, 1)):
        # Match line by line: a heading followed by a sentence would otherwise
        # yield phrases like "Authority The Director".
        for line in blob.splitlines():
            for m in _TITLE_CASE_ROLE.finditer(line):
                role = re.sub(r"\s+", " ", m.group(1)).strip()
                role = re.sub(r"^(?:The|A|An|And|Or|Of|Authority|Purpose)\s+",
                              "", role).strip()
                if len(role) < 5 or role in _ROLE_STOPWORDS:
                    continue
                counts[role] += weight
    ranked = [r for r, n in counts.most_common(40) if n >= 2]
    # Drop a bare title that is only ever part of a fuller one: keep
    # "Agency Director", drop "Director" and "The Director".
    kept: list[str] = []
    for role in ranked:
        stripped = re.sub(r"^(The|An?)\s+", "", role)
        if any(stripped != other and stripped in other for other in ranked):
            continue
        if stripped not in kept:
            kept.append(stripped)
    return kept[:20]


_UNIT_FIELD = re.compile(
    r"\b(bureau|division|program|programme|office|unit|department|region)\b", re.I)


def _org_units_from_intake(appendices, instruments) -> list[str]:
    """Read the operating units out of the intake form's own picker."""
    key = next((k for k, m in instruments.items() if m.get("role") == "intake"),
               None)
    candidates = [s for s in appendices
                  if key is None or s.letter == key] or list(appendices)
    for schema in candidates:
        for sheet in schema.sheets:
            for block in sheet.blocks:
                for field in block.fields:
                    if (field.options and _UNIT_FIELD.search(field.label)
                            and 2 < len(field.options) <= 15):
                        return [o for o in field.options if 2 < len(o) < 48]
    return []


def _discover_org_units(text: str, roles: list[str]) -> list[str]:
    """Bureaus, divisions, offices — whatever this agency calls its units.

    An enumerated picker in an intake form is by far the most reliable source,
    because the agency wrote its own list. Prose matches are a fallback and are
    filtered against the discovered roles, or "Office of the General Counsel"
    is mistaken for an operating unit.
    """
    role_words = {w.lower() for r in roles for w in r.split()}

    for m in re.finditer(r"\[Select:\s*([^\]]+)\]", text):
        parts = [p.strip(" .") for p in m.group(1).split("/")]
        parts = [p for p in parts if 2 < len(p) < 40]
        if 3 <= len(parts) <= 12:
            return parts        # the agency's own enumeration wins outright

    units = Counter()
    for m in re.finditer(
            r"\b(?:Bureau|Division|Directorate)\s+of\s+"
            r"((?:[A-Z][A-Za-z]+\s?){1,4})", text):
        unit = re.sub(r"\s+", " ", m.group(1)).strip(" .,")
        if unit.lower() in role_words or any(w.lower() in role_words
                                             for w in unit.split()):
            continue
        units[unit] += 1
    return [u for u, n in units.most_common(12) if len(u) > 2]


#: Words that look like acronyms but carry no programme meaning. The agency's
#: own abbreviation is excluded dynamically — it is not a statutory programme.
_NOT_A_PROGRAMME = {
    "THE", "AND", "FOR", "ALL", "ANY", "NOT", "USE", "AI", "IT", "API", "PII",
    "NIST", "FOIA", "DATE", "NAME", "YES", "TBD", "CTO", "GIS", "PDF", "CSV",
}


def _discover_programmes(text: str, exclude: set[str] | None = None) -> list[str]:
    """Statutory or delegated programs this agency actually names.

    Case-sensitive on purpose: these are acronyms, and matching case-insensitively
    turns "and", "for" and "the" into statutory programs.
    """
    found = Counter()
    for m in re.finditer(r"\b([A-Z]{3,8})\b\s*(?:/|,|\s)\s*"
                         r"(?:permit|program|programme|delegation|delegated)", text):
        found[m.group(1)] += 1
    for m in re.finditer(r"delegated (?:federal )?programs?\s*\(([^)]{3,90})\)",
                         text, re.I):
        for token in re.split(r"[,/]| and ", m.group(1)):
            token = token.strip(" .")
            if 2 < len(token) < 24 and token.upper() == token:
                found[token] += 1
    # A comma-or-list of acronyms qualified by a programme word:
    # "subject to HIPAA, CMS or SNAP delegation".
    for m in re.finditer(
            r"((?:\b[A-Z]{2,8}\b[,/]?\s+(?:or|and)?\s*){2,})"
            r"(?:delegation|program|programme|requirements|rules)", text):
        for token in re.findall(r"\b([A-Z]{2,8})\b", m.group(1)):
            found[token] += 2
    # Programme acronyms paired with a statute reference are unambiguous.
    for m in re.finditer(r"\b([A-Z]{3,8})\b(?=[^.]{0,60}\b(?:Act|U\.S\.C\.|"
                         r"C\.F\.R\.|Title [IVX]+)\b)", text):
        found[m.group(1)] += 1
    skip = _NOT_A_PROGRAMME | {e.upper() for e in (exclude or set()) if e}
    return [p for p, n in found.most_common(20)
            if p not in skip and n >= 2][:12]


def _discover_adoption(texts: dict[str, str]) -> tuple[str | None, str]:
    for label, blob in texts.items():
        for m in _SIGNED_DATE.finditer(blob):
            raw = m.group(1)
            parsed = _parse_date(raw)
            if parsed:
                return parsed.isoformat(), f"{label}: “{m.group(0)[:70]}”"
    # Fall back to a date encoded in a filename (a signed PDF often carries it).
    for label in texts:
        m = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", label)
        if m:
            try:
                return date(int(m.group(1)), int(m.group(2)),
                            int(m.group(3))).isoformat(), f"filename: {label}"
            except ValueError:
                pass
    return None, ""


def _parse_date(raw: str) -> date | None:
    raw = raw.strip()
    m = re.match(r"(\d{1,2})[/-](\d{1,2})[/-]((?:20)?\d{2})", raw)
    if m:
        y = int(m.group(3))
        y = y + 2000 if y < 100 else y
        try:
            return date(y, int(m.group(1)), int(m.group(2)))
        except ValueError:
            return None
    m = re.match(r"([A-Za-z]+)\s+(\d{1,2}),\s+(\d{4})", raw)
    if m and m.group(1).lower() in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(1).lower()],
                        int(m.group(2)))
        except ValueError:
            return None
    return None


# -------------------------------------------------------------------- driver

def discover() -> AgencyProfile:
    """Read the corpus and work out whose it is and how it is structured."""
    from datetime import datetime, timezone
    from app.ingest_docx import parse_all as parse_docs
    from app.ingest_xlsx import parse_all as parse_appendices

    docs = parse_docs()
    appendices = parse_appendices()

    texts = {d.doc_id: "\n".join(f"{c.heading}\n{c.text}" for c in d.chunks)
             for d in docs}
    # The instruments carry the agency's own enumerations — the bureau picker
    # in an intake form is the most reliable statement of its operating units,
    # and it lives in a workbook rather than in prose.
    instrument_blob = "\n".join(
        " ".join(
            [b.title for sheet in s.sheets for b in sheet.blocks if b.title]
            + [f"{f.label} {' / '.join(f.options)} {f.help_text}"
               for sheet in s.sheets for b in sheet.blocks for f in b.fields]
        )
        for s in appendices
    )
    corpus_blob = "\n".join(texts.values()) + "\n" + instrument_blob

    # Also scan filenames of non-parsed artefacts (a signed PDF, for instance).
    for path in CORPUS.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".pdf",):
            texts.setdefault(path.stem, path.stem.replace("_", " "))

    profile = AgencyProfile(discovered_at=datetime.now(timezone.utc)
                            .isoformat(timespec="seconds"))

    # Identity comes from the narrative documents only. Instrument headers are
    # a run-on of titles and authority clauses, and a name regex will happily
    # span two of them ("…RISK CLASSIFICATION MATRIX Ohio Department of…").
    framework_doc = next(
        (d for d in docs if _classify_document(texts.get(d.doc_id, "")) == "framework"),
        None)
    primary = texts.get(framework_doc.doc_id, "") if framework_doc else ""
    # Documents first, then each instrument as its own block: the agency often
    # spells its full name out only once, in an instrument's header row.
    name_sources = list(texts.values()) + [
        " ".join([b.title for sheet in s.sheets for b in sheet.blocks if b.title]
                 + [" ".join(v for v in row.values() if v)
                    for sheet in s.sheets for b in sheet.blocks
                    for row in b.sample_rows[:10]])
        for s in appendices
    ]
    profile.name, profile.short_name, profile.jurisdiction = \
        _agency_names(name_sources, primary)
    if profile.short_name and profile.name:
        profile.naming_rule = (
            f'Refer to the agency as "{profile.name} ({profile.short_name})" '
            f'on first use and "{profile.short_name}" thereafter.')

    for doc in docs:
        kind = _classify_document(texts.get(doc.doc_id, ""))
        if kind and kind not in profile.documents:
            profile.documents[kind] = {
                "doc_id": doc.doc_id, "label": doc.doc_label,
                "path": doc.source_path, "sections": len([c for c in doc.chunks
                                                          if c.section]),
                "authoritative": True,
            }

    profile.instrument_noun, profile.instruments = _discover_instruments(appendices)
    profile.instrument_keys = sorted(profile.instruments)
    profile.gate_noun, profile.gates = _discover_gates(appendices, profile.instruments)

    fw = texts.get(profile.documents.get("framework", {}).get("doc_id", ""), "")
    mn = texts.get(profile.documents.get("manual", {}).get("doc_id", ""), "")
    profile.roles = _discover_roles(fw, mn)
    # The intake instrument names the agency's operating units in a dropdown —
    # the agency's own enumeration, and far more reliable than mining prose.
    profile.org_units = (_org_units_from_intake(appendices, profile.instruments)
                         or _discover_org_units(corpus_blob, profile.roles))
    profile.statutory_programmes = _discover_programmes(
        corpus_blob, exclude={profile.short_name})
    profile.adoption_date, profile.adoption_source = _discover_adoption(texts)

    if not profile.documents.get("framework"):
        profile.notes.append(
            "No document identified itself as the governing framework; "
            "authority checks will be limited until one is designated.")
    if not profile.gates:
        profile.notes.append(
            "No lifecycle checkpoints were discovered. Designate the "
            "checklist instrument so gates can be read from it.")
    if not profile.adoption_date:
        profile.notes.append(
            "No adoption date could be read from the corpus. Set it before the "
            "record is relied on.")
    return profile


# ------------------------------------------------------------------ storage

_cache: AgencyProfile | None = None


def load(refresh: bool = False) -> AgencyProfile:
    global _cache
    if _cache is not None and not refresh:
        return _cache
    if PROFILE_FILE.exists():
        data = yaml.safe_load(PROFILE_FILE.read_text(encoding="utf-8")) or {}
        _cache = AgencyProfile(**data)
    else:
        _cache = discover()
        save(_cache)
    return _cache


def save(profile: AgencyProfile) -> None:
    atomic_write(PROFILE_FILE, yaml.safe_dump(profile.as_dict(), sort_keys=False,
                                              allow_unicode=True))


def invalidate() -> None:
    global _cache
    _cache = None


def rediscover() -> AgencyProfile:
    profile = discover()
    existing = load() if PROFILE_FILE.exists() else None
    if existing and existing.confirmed:
        # Keep what a human confirmed; refresh only what is structural.
        profile.name = existing.name or profile.name
        profile.short_name = existing.short_name or profile.short_name
        profile.adoption_date = existing.adoption_date or profile.adoption_date
        profile.confirmed = True
    save(profile)
    invalidate()
    return load(refresh=True)


def summary() -> dict[str, Any]:
    p = load()
    return {
        "name": p.name, "short_name": p.short_name,
        "jurisdiction": p.jurisdiction, "naming_rule": p.naming_rule,
        "documents": p.documents,
        "instrument_noun": p.instrument_noun,
        "instruments": [{"key": k, **v} for k, v in
                        sorted(p.instruments.items())],
        "gate_noun": p.gate_noun, "gates": p.gates,
        "roles": p.roles, "org_units": p.org_units,
        "statutory_programmes": p.statutory_programmes,
        "adoption_date": p.adoption_date, "adoption_source": p.adoption_source,
        "confirmed": p.confirmed, "notes": p.notes,
        "discovered_at": p.discovered_at,
    }
