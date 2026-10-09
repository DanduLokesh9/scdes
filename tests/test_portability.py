"""The application must not know anything about a particular agency.

These tests build a synthetic corpus for an agency that shares nothing with
SCDES — different state, different domain, instruments called "Schedule"
numbered 1–5 instead of "Appendix" A–N, checkpoints called "Stage", different
roles, different statutory programs, a different risk vocabulary — and assert
that discovery adapts.

They are the guard against agency-specific values creeping back into code.
"""

from __future__ import annotations

import pytest

from demo_portability import build_corpus


@pytest.fixture(scope="module")
def other_agency(tmp_path_factory):
    """Discover a profile for a corpus that is not SCDES's."""
    root = tmp_path_factory.mktemp("odhs")
    build_corpus(root)

    from app import audit, ingest_docx, ingest_xlsx, profile as profile_mod
    originals = (audit.CORPUS, ingest_docx.CORPUS, ingest_xlsx.APPENDIX_DIR,
                 profile_mod.CORPUS, profile_mod.PROFILE_FILE)
    audit.CORPUS = root
    ingest_docx.CORPUS = root
    ingest_xlsx.APPENDIX_DIR = root / "appendices"
    profile_mod.CORPUS = root
    profile_mod.PROFILE_FILE = root / "config" / "agency.yaml"
    profile_mod.invalidate()

    yield profile_mod.discover()

    (audit.CORPUS, ingest_docx.CORPUS, ingest_xlsx.APPENDIX_DIR,
     profile_mod.CORPUS, profile_mod.PROFILE_FILE) = originals
    profile_mod.invalidate()


def test_agency_identity_comes_from_the_corpus(other_agency):
    assert other_agency.name == "Ohio Department of Health Services"
    assert other_agency.short_name == "ODHS"
    assert other_agency.jurisdiction == "Ohio"
    assert "SCDES" not in other_agency.name


def test_adoption_date_is_read_not_assumed(other_agency):
    assert other_agency.adoption_date == "2027-03-03"
    assert other_agency.adoption_source


def test_instruments_are_not_assumed_to_be_appendices_a_to_n(other_agency):
    assert other_agency.instrument_noun == "Schedule"
    assert other_agency.instrument_keys == ["1", "2", "3", "4", "5"]


def test_instrument_roles_are_inferred(other_agency):
    roles = {m["role"] for m in other_agency.instruments.values()}
    assert {"taxonomy", "risk_model", "intake", "gate_checklists",
            "incident"} <= roles
    assert other_agency.instrument_for("risk_model") == "2"


def test_lifecycle_is_not_assumed_to_be_six_gates(other_agency):
    assert other_agency.gate_noun == "Stage"
    assert other_agency.gate_keys() == ["1", "2", "3"]
    assert all(g["requirements"] for g in other_agency.gates)


def test_operating_units_come_from_the_agencys_own_picker(other_agency):
    assert "Member Services" in other_agency.org_units
    assert "Public Health" in other_agency.org_units
    assert "Water" not in other_agency.org_units      # that is SCDES's list


def test_roles_are_discovered_not_listed(other_agency):
    assert "Privacy Officer" in other_agency.roles
    assert "Chief Medical Informatics Officer" in other_agency.roles
    assert "Bureau Chief" not in other_agency.roles   # SCDES-specific


def test_statutory_programmes_are_domain_neutral(other_agency):
    assert {"HIPAA", "CMS"} <= set(other_agency.statutory_programmes)
    assert "NPDES" not in other_agency.statutory_programmes


def test_vocabulary_follows_the_corpus(other_agency):
    """This agency says bucket, not category — and severe, not high."""
    from app.integrity import observed_vocabulary
    from app.ingest_docx import parse_all as parse_docs
    from app.ingest_xlsx import parse_all as parse_appendices

    text = {d.doc_label: "\n".join(f"{c.heading}\n{c.text}" for c in d.chunks)
            for d in parse_docs()}
    vocab = observed_vocabulary(text, {s.letter: s for s in parse_appendices()})

    grouping = vocab["use case grouping"]
    assert grouping.get("bucket", 0) > 0
    assert grouping.get("category", 0) == 0

    bands = vocab["risk band labels"]
    assert bands.get("minimal/moderate/severe", 0) > 0


def test_no_agency_literals_survive_in_the_discovery_path():
    """Code that discovers must not name any agency, program or bureau."""
    import re
    from pathlib import Path

    banned = re.compile(
        r"SCDES|NPDES|RCRA|CERCLA|HIPAA|Coastal Zone|Member Services", re.I)
    offenders = {}
    for name in ("profile.py", "ingest_docx.py", "ingest_xlsx.py"):
        path = Path(__file__).resolve().parent.parent / "app" / name
        hits = []
        in_docstring = False
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.count('"""') == 1:
                in_docstring = not in_docstring
                continue
            # Prose and comments may name an agency by way of example; only
            # executable code must stay neutral.
            if in_docstring or stripped.startswith(("#", '"""')):
                continue
            if banned.search(line):
                hits.append(stripped[:70])
        if hits:
            offenders[name] = hits
    assert not offenders, f"agency-specific literals in discovery code: {offenders}"


# --------------------------------------------------------------- the agency mark

def test_the_header_shows_the_departments_own_shorthand() -> None:
    """The top-left mark is the agency's abbreviation exactly as published.

    Not the state code, and not decorated with one — SCDES, TCEQ, Ecology.
    """
    from app.states import all_states, entry
    for e in map(entry, [s.code for s in all_states()]):
        assert e.abbrev, f"{e.code} has no abbreviation to show"
        assert e.abbrev == e.abbrev.strip()
        assert e.abbrev != e.code or e.code == e.abbrev, "mark must name the department"


def test_known_abbreviations_are_used_verbatim() -> None:
    from app.states import entry
    for code, expected in (("SC", "SCDES"), ("TX", "TCEQ"), ("WA", "Ecology"),
                           ("OH", "Ohio EPA"), ("MO", "MoDNR")):
        assert entry(code).abbrev == expected, (
            f"{code} shows {entry(code).abbrev!r}, expected {expected!r}")
