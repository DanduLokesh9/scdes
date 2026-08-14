"""Corpus integrity audit — is the governance trail tight enough to rely on?

The Framework fixes the naming and the authorities. That informs the Council
Operating Procedures, which informs the Operations Manual, which informs all
fourteen appendices. This module walks that chain and checks it holds:

  references   every "Appendix X" and "Section N" citation resolves to something
               that exists
  naming       an appendix is called the same thing everywhere it is named
  inventory    the appendix list is complete wherever it is enumerated
  dates        stated dates are mutually consistent and anchored to adoption
  authorities  every role given a duty downstream is established upstream
  terminology  one vocabulary is used, not several

Findings carry a severity and a suggested fix. Nothing is corrected silently:
this is the record that has to stand up later, so the audit reports and the
Council decides.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict, field as dc_field
from datetime import date
from typing import Any, Iterable

from app.ingest_docx import parse_all as parse_docs
from app.ingest_xlsx import parse_all as parse_appendices

CRITICAL, SERIOUS, MODERATE, NOTE = "critical", "serious", "moderate", "note"
SEVERITY_ORDER = {CRITICAL: 0, SERIOUS: 1, MODERATE: 2, NOTE: 3}

def _profile():
    from app import profile as profile_mod
    return profile_mod.load()


def instrument_keys() -> list[str]:
    """Whatever this agency's instruments are actually called — not A–N."""
    keys = _profile().instrument_keys
    return keys or list("ABCDEFGHIJKLMN")


def adoption_date() -> date | None:
    """Discovered from the corpus; the trail anchors to it when it exists."""
    return _profile().adoption()


@dataclass
class Finding:
    check: str
    severity: str
    title: str
    detail: str
    where: list[str] = dc_field(default_factory=list)
    fix: str = ""
    evidence: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Report:
    findings: list[Finding] = dc_field(default_factory=list)
    stats: dict[str, Any] = dc_field(default_factory=dict)

    def add(self, **kwargs: Any) -> None:
        self.findings.append(Finding(**kwargs))

    def sorted(self) -> list[Finding]:
        return sorted(self.findings,
                      key=lambda f: (SEVERITY_ORDER.get(f.severity, 9), f.check))

    def counts(self) -> dict[str, int]:
        return dict(Counter(f.severity for f in self.findings))

    def as_dict(self) -> dict[str, Any]:
        return {"findings": [f.as_dict() for f in self.sorted()],
                "counts": self.counts(), "stats": self.stats}


# ------------------------------------------------------------------- loading

def _corpus() -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
    docs = {d.doc_label: d for d in parse_docs()}
    text = {label: "\n".join(f"{c.heading}\n{c.text}" for c in d.chunks)
            for label, d in docs.items()}
    appendices = {s.letter: s for s in parse_appendices()}
    return docs, text, appendices


def _sentences(blob: str, pattern: re.Pattern[str], limit: int = 4) -> list[str]:
    out = []
    for m in pattern.finditer(blob):
        start = blob.rfind(".", 0, m.start()) + 1
        end = blob.find(".", m.end())
        end = end if end != -1 else m.end() + 120
        out.append(re.sub(r"\s+", " ", blob[start:end]).strip()[:220])
        if len(out) >= limit:
            break
    return out


# -------------------------------------------------------- 1. cross-references

_APPENDIX_REF = re.compile(r"\bAppendix\s+([A-Z])\b")
_FRAMEWORK_SEC = re.compile(
    r"[Ss]ection\s+(\d+[A-Z]?(?:\.\d+)*)\s+of\s+the\s+(?:Governance\s+)?Framework")
_MANUAL_SEC = re.compile(
    r"[Ss]ection\s+(\d+[A-Z]?(?:\.\d+)*)\s+of\s+this\s+Manual|"
    r"(?:Operations\s+Manual|Manual)[, ]+[§]?\s*(\d+[A-Z]?(?:\.\d+)*)")
_BARE_SEC = re.compile(r"§\s*(\d+[A-Z]?(?:\.\d+)*)")


def _doc_text(docs, text, kind: str) -> tuple[str, str]:
    """The label and body of a document by its discovered role, not its name."""
    meta = _profile().documents.get(kind, {})
    label = meta.get("label", "")
    return label, text.get(label, "")


def _sections_of(docs, kind: str) -> set[str]:
    label = _profile().documents.get(kind, {}).get("label", "")
    doc = docs.get(label)
    return {c.section for c in doc.chunks if c.section} if doc else set()


def check_references(report: Report, docs, text, appendices) -> None:
    keys = instrument_keys()
    framework_sections = _sections_of(docs, "framework")
    manual_sections = _sections_of(docs, "manual")

    # -- appendix references ------------------------------------------------
    dangling: dict[str, set[str]] = defaultdict(set)
    for label, blob in text.items():
        for letter in set(_APPENDIX_REF.findall(blob)):
            if letter not in keys:
                dangling[letter].add(label)
    for schema in appendices.values():
        for sheet in schema.sheets:
            for block in sheet.blocks:
                for row in block.sample_rows:
                    for letter in set(_APPENDIX_REF.findall(" ".join(
                            v for v in row.values() if v))):
                        if letter not in keys:
                            dangling[letter].add(f"Appendix {schema.letter}")

    if dangling:
        report.add(
            check="references", severity=CRITICAL,
            title=f"{len(dangling)} reference(s) point at an appendix that does not exist",
            detail="; ".join(f"'Appendix {k}' cited in {', '.join(sorted(v))}"
                             for k, v in sorted(dangling.items())),
            where=sorted({w for v in dangling.values() for w in v}),
            fix="Correct the letter, or add the appendix to the adopted set.",
        )

    # -- section references -------------------------------------------------
    for label, blob in text.items():
        if not framework_sections:
            break
        missing_fw = {s for s in _FRAMEWORK_SEC.findall(blob)
                      if s not in framework_sections}
        if missing_fw:
            report.add(
                check="references", severity=SERIOUS,
                title=f"{label} cites Framework section(s) that do not exist",
                detail=f"Cited: {', '.join(sorted(missing_fw))}. "
                       f"The Framework defines {len(framework_sections)} sections.",
                where=[label],
                evidence=_sentences(blob, _FRAMEWORK_SEC),
                fix="Re-point the citation at the correct Framework section.",
            )

        manual_refs = {a or b for a, b in _MANUAL_SEC.findall(blob) if (a or b)}
        missing_man = {s for s in manual_refs if s not in manual_sections}
        if missing_man:
            report.add(
                check="references", severity=SERIOUS,
                title=f"{label} cites Operations Manual section(s) that do not exist",
                detail=f"Cited: {', '.join(sorted(missing_man))}. "
                       f"The Manual defines {len(manual_sections)} sections.",
                where=[label],
                fix="Re-point the citation at the correct Manual section.",
            )

    report.stats["framework_sections"] = len(framework_sections)
    report.stats["manual_sections"] = len(manual_sections)


# ------------------------------------------------------------- 2. appendix naming

#: "Appendix J (Standardized Evaluation Methodology)" — stop at the closing
#: bracket or clause end so a run-on list is not swallowed as one title.
_NAMED = re.compile(
    r"Appendix\s+([A-N])\s*[\(:—-]\s*([A-Z][A-Za-z0-9&/,' -]{3,70}?)"
    r"(?=\s*[\).;\n]|\s+Appendix\s+[A-N]\b|$)")


def _canonical_titles(appendices) -> dict[str, str]:
    """The title an appendix gives itself, cut at the first authority clause.

    Workbook headers run on into authority and cross-reference text, so take
    only the leading title and never re-case it — SCDES and AI are acronyms.
    """
    titles = {}
    for letter, schema in appendices.items():
        raw = re.sub(r"\s+", " ", schema.title or "").strip()
        m = re.search(r"APPENDIX\s+[A-N]\s*[—–-]\s*(.+)", raw, re.I)
        title = (m.group(1) if m else raw)
        title = re.split(r"\s*[|;]|\s+—\s+Authority|\s+Authority:|\s+Related:",
                         title)[0]
        titles[letter] = title.strip(" .:—–-")[:70]
    return titles


def check_naming(report: Report, docs, text, appendices) -> None:
    canonical = _canonical_titles(appendices)
    stated: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))

    sources = dict(text)
    for schema in appendices.values():
        blob = " ".join(
            b.title for sheet in schema.sheets for b in sheet.blocks if b.title)
        sources[f"{_profile().instrument_noun} {schema.letter} (workbook)"] = blob

    for label, blob in sources.items():
        for letter, title in _NAMED.findall(blob):
            clean = re.sub(r"\s+", " ", title).strip(" .;,")
            if len(clean) > 3:
                stated[letter][clean].add(label)

    for letter in sorted(stated):
        variants = stated[letter]
        # Collapse trivial differences (case, punctuation, "the").
        norm = defaultdict(set)
        for title, where in variants.items():
            key = re.sub(r"[^a-z0-9]+", "", title.lower())
            norm[key] |= where
        if len(norm) > 1:
            listing = "; ".join(
                f'"{t}" ({", ".join(sorted(w))})' for t, w in variants.items())
            report.add(
                check="naming", severity=MODERATE,
                title=f"{_profile().instrument_noun} {letter} is named inconsistently across documents",
                detail=listing[:400],
                where=sorted({w for s in variants.values() for w in s}),
                fix=f"Standardise on the workbook title: "
                    f"\"{canonical.get(letter, '')}\".",
            )

    # Does each workbook's own title agree with how the Manual names it?
    manual_label, manual_blob = _doc_text(docs, text, "manual")
    reported: set[str] = set()
    for letter, title in _NAMED.findall(manual_blob):
        canon = canonical.get(letter, "")
        if not canon or letter in reported:
            continue
        a = re.sub(r"[^a-z0-9]+", "", title.lower())
        b = re.sub(r"[^a-z0-9]+", "", canon.lower())
        if a and b and a not in b and b not in a:
            reported.add(letter)
            report.add(
                check="naming", severity=MODERATE,
                title=f"{_profile().instrument_noun} {letter}: the manual and the workbook disagree on the title",
                detail=f'The manual says "{title.strip()}"; the workbook is titled '
                       f'"{canon}".',
                where=[manual_label, f"{_profile().instrument_noun} {letter}"],
                fix="Align the manual's instrument list with the workbook titles.",
            )


# ------------------------------------------------------------ 3. inventory

def check_inventory(report: Report, docs, text, appendices) -> None:
    # Instruments issued as prose have no workbook by design — not a gap.
    workbook_keys = {k for k, m in _profile().instruments.items()
                     if m.get("format") != "document"}
    missing_files = [k for k in instrument_keys()
                     if k in workbook_keys and k not in appendices]
    if missing_files:
        report.add(
            check="inventory", severity=CRITICAL,
            title="Adopted appendices are missing from the corpus",
            detail=f"No workbook found for: {', '.join(missing_files)}.",
            where=["corpus/appendices"],
            fix="Add the missing instruments or remove them from the adopted set.",
        )

    # Wherever the manual enumerates the instruments, the list should be complete.
    keys = instrument_keys()
    noun = _profile().instrument_noun or "Appendix"
    manual_label, manual = _doc_text(docs, text, "manual")
    first, last = (keys[0], keys[-1]) if keys else ("A", "N")
    span = re.compile(rf"{noun}(?:es|ices)?\s+{first}\s+(?:through|to|–|-)\s+{last}[^.]*\.",
                      re.I)
    for m in span.finditer(manual):
        segment = m.group()
        listed = set(_APPENDIX_REF.findall(segment))
        gap = [k for k in keys if k not in listed]
        if gap:
            report.add(
                check="inventory", severity=SERIOUS,
                title=f"An instrument enumeration in the {manual_label} is incomplete",
                detail=f"The list omits {', '.join(gap)} while claiming to cover "
                       f"{first} through {last}.",
                where=[manual_label],
                evidence=[re.sub(r"\s+", " ", segment)[:300]],
                fix="Add the omitted appendix/appendices to the enumeration.",
            )

    report.stats["appendices_present"] = len(appendices)


# ---------------------------------------------------------------- 4. dates

_MONTH = ("January|February|March|April|May|June|July|August|September|"
          "October|November|December")
_LONG_DATE = re.compile(rf"\b({_MONTH})\s+(\d{{1,2}}),\s+(\d{{4}})\b")
_SLASH_DATE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d{2})\b")
_MONTHS = {m: i + 1 for i, m in enumerate(
    "January February March April May June July August September October "
    "November December".split())}


def _dates_in(blob: str) -> list[tuple[date, str]]:
    found: list[tuple[date, str]] = []
    for m in _LONG_DATE.finditer(blob):
        try:
            found.append((date(int(m.group(3)), _MONTHS[m.group(1)],
                               int(m.group(2))), m.group()))
        except ValueError:
            pass
    for m in _SLASH_DATE.finditer(blob):
        try:
            found.append((date(int(m.group(3)), int(m.group(1)),
                               int(m.group(2))), m.group()))
        except ValueError:
            pass
    return found


def check_dates(report: Report, docs, text, appendices) -> None:
    anchor = adoption_date()
    all_dates: list[tuple[str, date, str]] = []
    for label, blob in text.items():
        if not docs[label].authoritative:
            continue
        for value, raw in _dates_in(blob):
            all_dates.append((label, value, raw))

    before_adoption = [(l, v, r) for l, v, r in all_dates
                       if anchor and v < anchor and v.year >= anchor.year]
    if before_adoption:
        report.add(
            check="dates", severity=MODERATE,
            title="Dates that precede the adoption date",
            detail="; ".join(f"{r} in {l}" for l, v, r in before_adoption[:6]) +
                   f". Adoption was {anchor.isoformat()}.",
            where=sorted({l for l, _, _ in before_adoption}),
            fix="Confirm each is a deliberate historical reference rather than a "
                "stale drafting date.",
        )

    # The adoption date is the anchor of the whole trail. It appears as a blank
    # in the header line every instrument inherits — one root cause, corpus-wide,
    # so report it once rather than thirty times.
    _ADOPTED_BLANK = re.compile(
        r"adopted\s+_{3,}\s*,?\s*(20\d{2})|Effective\s+\[\s*DATE\s*\]", re.I)
    _ANY_BLANK = re.compile(
        r"_{3,}\s*,?\s*20\d{2}|\[\s*date\s*\]|\bTBD\b|\bto be determined\b", re.I)

    adoption_blank: list[str] = []
    other_blank: dict[str, str] = {}

    sources = dict(text)
    for letter, schema in appendices.items():
        sources[f"{_profile().instrument_noun} {letter}"] = " ".join(
            b.title for sheet in schema.sheets for b in sheet.blocks if b.title)

    for label, blob in sources.items():
        if _ADOPTED_BLANK.search(blob):
            adoption_blank.append(label)
        elif (m := _ANY_BLANK.search(blob)):
            other_blank[label] = re.sub(r"\s+", " ", m.group())

    if adoption_blank:
        report.add(
            check="dates", severity=CRITICAL,
            title="The adoption date is blank across the entire corpus",
            detail=(
                f"{len(adoption_blank)} instruments carry the line "
                f'the adoption line with the date never filled in — while the '
                f"corpus itself puts adoption at "
                f"{anchor.strftime('%d %B %Y') if anchor else 'a date stated nowhere'}"
                f". Every instrument inherits this header, so the binding date "
                f"is asserted nowhere in the documents it binds."
            ),
            where=sorted(adoption_blank),
            evidence=['"…Governance Framework, adopted __________, 2026"',
                      '"Effective [DATE], the SCDES AI Governance Framework … '
                      'are binding across all programs"'],
            fix=(f"Set the adoption date to {anchor.isoformat()} everywhere it "
                 f"appears, or state explicitly why it differs."
                 if anchor else
                 "Establish the adoption date and set it everywhere it appears."),
        )

    for label, snippet in sorted(other_blank.items()):
        report.add(
            check="dates", severity=SERIOUS,
            title=f"Unfilled date placeholder in {label}",
            detail=f"Found: {snippet!r}",
            where=[label],
            fix="Fill the date before this is relied on as a binding record.",
        )

    report.stats["dates_found"] = len(all_dates)


# --------------------------------------------------------- 5. authorities

#: Roles the app understands generically, whatever the agency calls its own.
#: Ownership roles appear on instruments rather than in the Framework, so they
#: are added to whatever discovery found.
GENERIC_OWNER_ROLES = ["Operational Owner", "Technical Owner", "Data Owner"]

#: An office abbreviated is the same office. Built from the discovered roles.
def _role_aliases(roles: list[str]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for role in roles:
        words = [w for w in role.split() if w[:1].isupper()]
        if len(words) >= 3:
            aliases["".join(w[0] for w in words)] = role
    return aliases


def _roles() -> list[str]:
    found = list(_profile().roles)
    for extra in GENERIC_OWNER_ROLES:
        if extra not in found:
            found.append(extra)
    return found


def _role_counts(blob: str) -> Counter:
    roles = _roles()
    if not roles:
        return Counter()
    aliases = _role_aliases(roles)
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(r) for r in
                          sorted(roles + list(aliases), key=len, reverse=True))
        + r")\b")
    return Counter(aliases.get(r, r) for r in pattern.findall(blob))


def check_authorities(report: Report, docs, text, appendices) -> None:
    fw_label, fw_text = _doc_text(docs, text, "framework")
    mn_label, mn_text = _doc_text(docs, text, "manual")
    _, proc_text = _doc_text(docs, text, "procedures")
    if not fw_text:
        return
    framework = _role_counts(fw_text)
    manual = _role_counts(mn_text)
    procedures = _role_counts(proc_text)

    downstream = Counter()
    downstream.update(manual)
    downstream.update(procedures)
    for schema in appendices.values():
        blob = " ".join(
            f.label for sheet in schema.sheets for b in sheet.blocks
            for f in b.fields)
        downstream.update(_role_counts(blob))

    undefined = {role: n for role, n in downstream.items()
                 if role not in framework and n >= 2}
    if undefined:
        listing = ", ".join(f"{r} ({n} mentions)" for r, n in
                            sorted(undefined.items(), key=lambda kv: -kv[1]))
        report.add(
            check="authorities", severity=SERIOUS,
            title="Roles carry duties downstream but are not established in the Framework",
            detail=f"{listing}. The Framework is where authority is conferred; a "
                   f"duty assigned only in the Manual or an appendix has no "
                   f"upstream basis.",
            where=[mn_label, "procedures", "instruments"],
            fix="Establish each role in the Framework, or re-assign the duty to a "
                "role the Framework already establishes.",
        )

    # A role the Framework leans on heavily should also be operationalised.
    thin = {role: framework[role] for role in framework
            if framework[role] >= 3 and downstream.get(role, 0) == 0}
    if thin:
        report.add(
            check="authorities", severity=MODERATE,
            title="Roles established in the Framework never appear operationally",
            detail=", ".join(f"{r} ({n} mentions in the Framework, none downstream)"
                             for r, n in thin.items()),
            where=[fw_label],
            fix="Give the role a procedure in the Manual, or drop it from the "
                "Framework.",
        )

    # Imbalance is worth surfacing even when both ends mention the role.
    for role in sorted(set(framework) | set(downstream)):
        fw, dn = framework.get(role, 0), downstream.get(role, 0)
        if fw and dn and dn >= 8 * fw:
            report.add(
                check="authorities", severity=MODERATE,
                title=f"{role} is barely established upstream but heavily relied on downstream",
                detail=f"{fw} mention(s) in the Framework versus {dn} downstream. "
                       f"The operational load sits well ahead of the conferred "
                       f"authority.",
                where=[fw_label, mn_label],
                fix="Expand the Framework's statement of this role's authority to "
                    "match the duties the Manual assigns it.",
            )

    report.stats["roles_in_framework"] = len(framework)
    report.stats["roles_downstream"] = len(downstream)


# --------------------------------------------------------- 6. terminology

#: Competing vocabularies for the same concept. The Framework's choice governs.
#:
#: Each label is only counted when its concept anchor appears nearby: SCDES uses
#: "Tier" for Council decisions (A/B/C) *and* for vendor disclosure (1–4), so a
#: bare "Tier 2" says nothing about which concept is meant. Matching without an
#: anchor reports a vocabulary clash that is not there.
VOCABULARIES: dict[str, dict[str, Any]] = {
    "use case grouping": {
        "anchor": re.compile(r"use[- ]case|taxonomy|Category [123]", re.I),
        "options": {
            "category": re.compile(r"\bCategor(?:y|ies)\b"),
            "bucket": re.compile(r"\bBuckets?\b", re.I),
            "class": re.compile(r"\bClasses?\b(?!ification)", re.I),
        },
    },
    "council decision level": {
        "anchor": re.compile(r"Council|concurrence|consensus|unilateral|convened",
                             re.I),
        "options": {
            "tier": re.compile(r"\bTier\s*[ABC]\b"),
            "level": re.compile(r"\bLevel\s*[ABC]\b"),
            "class": re.compile(r"\bClass\s*[ABC]\b"),
        },
    },
    "incident severity": {
        "anchor": re.compile(r"incident|escalat|suspend|root[- ]cause|lookback",
                             re.I),
        "options": {
            "level": re.compile(r"\bLevel\s*[123]\b"),
            "tier": re.compile(r"\bTier\s*[123]\b"),
            "severity": re.compile(r"\bSeverity\s*[123]\b", re.I),
        },
    },
    "vendor disclosure depth": {
        "anchor": re.compile(r"disclosure|vendor", re.I),
        "options": {
            "tier": re.compile(r"\bTiers?\s*[1234]\b"),
            "level": re.compile(r"\bLevels?\s*[1234]\b"),
        },
    },
    "risk band labels": {
        "anchor": re.compile(r"risk", re.I),
        "options": {
            "low/moderate/high": re.compile(r"\bModerate\s+Risk\b"),
            "low/medium/high": re.compile(r"\bMedium\s+Risk\b"),
            "minimal/moderate/severe": re.compile(
                r"\bMinimal\s+Risk\b|\bSevere\s+Risk\b"),
        },
    },
}

_WINDOW = 140


def _anchored_count(blob: str, label: re.Pattern[str],
                    anchor: re.Pattern[str]) -> int:
    """Count label hits that sit within a window of their concept anchor."""
    hits = 0
    for m in label.finditer(blob):
        lo = max(0, m.start() - _WINDOW)
        hi = min(len(blob), m.end() + _WINDOW)
        if anchor.search(blob[lo:hi]):
            hits += 1
    return hits


def _vocabulary_sources(text, appendices) -> dict[str, str]:
    sources = dict(text)
    for schema in appendices.values():
        parts = []
        for sheet in schema.sheets:
            for block in sheet.blocks:
                if block.title:
                    parts.append(block.title)
                parts.extend(" ".join(v for v in row.values() if v)
                             for row in block.sample_rows[:20])
                parts.extend(f.label for f in block.fields[:40])
        sources[f"{_profile().instrument_noun} {schema.letter}"] = " ".join(parts)
    return sources


def observed_vocabulary(text, appendices) -> dict[str, dict[str, int]]:
    sources = _vocabulary_sources(text, appendices)
    observed: dict[str, dict[str, int]] = {}
    for concept, spec in VOCABULARIES.items():
        anchor = spec["anchor"]
        counts = {}
        for name, pattern in spec["options"].items():
            total = sum(_anchored_count(blob, pattern, anchor)
                        for blob in sources.values())
            if total:
                counts[name] = total
        observed[concept] = counts
    return observed


def check_terminology(report: Report, docs, text, appendices) -> None:
    observed = observed_vocabulary(text, appendices)
    report.stats["vocabulary"] = observed

    for concept, counts in observed.items():
        if len(counts) <= 1:
            continue
        ranked = sorted(counts.items(), key=lambda kv: -kv[1])
        winner, top = ranked[0]
        rivals = [(k, v) for k, v in ranked[1:] if v >= max(2, top * 0.02)]
        if not rivals:
            continue
        report.add(
            check="terminology", severity=MODERATE,
            title=f"Two vocabularies in use for {concept}",
            detail=f"'{winner}' dominates ({top} uses) but "
                   + ", ".join(f"'{k}' appears {v} time(s)" for k, v in rivals)
                   + ". The Framework's choice should be applied consistently "
                     "everywhere downstream.",
            where=["corpus"],
            fix=f"Adopt '{winner}' as the configured term and re-label the rest.",
        )


# ------------------------------------------------------------------ runner

CHECKS = (check_references, check_naming, check_inventory, check_dates,
          check_authorities, check_terminology)


def audit() -> Report:
    docs, text, appendices = _corpus()
    report = Report()
    report.stats["documents"] = len(docs)
    for check in CHECKS:
        check(report, docs, text, appendices)
    return report


def render(report: Report) -> str:
    lines = ["CORPUS INTEGRITY AUDIT", "=" * 78]
    counts = report.counts()
    lines.append("  " + " · ".join(
        f"{n} {sev}" for sev, n in sorted(counts.items(),
                                          key=lambda kv: SEVERITY_ORDER[kv[0]]))
        or "  no findings")
    lines.append(f"  {report.stats.get('documents', 0)} documents · "
                 f"{report.stats.get('appendices_present', 0)} appendix workbooks · "
                 f"{report.stats.get('framework_sections', 0)} Framework sections · "
                 f"{report.stats.get('manual_sections', 0)} Manual sections")
    lines.append("")

    for finding in report.sorted():
        lines.append(f"[{finding.severity.upper()}] {finding.title}")
        lines.append(f"    check : {finding.check}")
        lines.append(f"    detail: {finding.detail}")
        if finding.evidence:
            for ev in finding.evidence[:2]:
                lines.append(f"    quote : “{ev}”")
        if finding.where:
            lines.append(f"    where : {', '.join(finding.where)}")
        if finding.fix:
            lines.append(f"    fix   : {finding.fix}")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    print(render(audit()))
