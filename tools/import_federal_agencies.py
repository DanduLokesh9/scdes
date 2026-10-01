"""Turn the client's federal registry into the platform's federal agency list.

The client supplied one workbook covering both jurisdictions:
`SCDES_Agency_Registry_State_and_Federal.xlsx`. Its *Agencies* sheet is the
South Carolina list already imported by `tools/import_sc_agencies.py`. This
reads the two sheets that are new.

**Federal Agencies** — 472 entities, of which 339 are operating and 334 of
those publish an email domain. The rest are defunct, superseded or historical.
All 472 are written out, because a registry that quietly omits the abolished
ones cannot answer "is this agency real?" — but only the operating ones with a
domain are offered as somewhere to register. Each entry says which it is.

**Email Domain Allowlist** — 529 rows, 358 distinct domains across both
jurisdictions. This matters more than it looks. Onboarding accepts an address
on a suffix rule (`.gov`, `.mil`, `.edu`, `.us`, `.org`, `.int`), and 15 of the
domains in the client's own list do not end in any of them: `amtrak.com`,
`santeecooper.com`, `palmettorail.com`, `scalc.net`, `governors.school`,
`scdmvonline.com`. Those are real government bodies whose staff the suffix rule
would turn away — the Administrative Law Court and the DMV among them. An
exact-domain allowlist alongside the suffix rule lets them in without loosening
the rule for everyone.

Two things this deliberately does not do.

**No convention is derived.** The SC importer could infer that an agency runs
`first.last` because the client's *People* sheet gave it real staff addresses to
count. The federal sheet has no equivalent, so every entry here is
`convention: "any"` — the domain is checked, the local part is not, and the
entry says so. Guessing would lock real people out of their own agency with a
confidently-worded error.

**No names.** The federal sheet carries `Agency Head` and `Head Title` for many
entries and they are not read here, against the client's standing instruction:
"Do not pre-load any user names/info or gate any activities based on title."

Run:  python -m tools.import_federal_agencies            # report only
      python -m tools.import_federal_agencies --write    # write the data files
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

import openpyxl

SOURCE = Path(r"C:\Users\dandu\OneDrive\Desktop"
              r"\SCDES_Agency_Registry_State_and_Federal.xlsx")

DATA = Path(__file__).resolve().parent.parent / "app" / "data"
OUT_AGENCIES = DATA / "federal_agencies.json"
OUT_ALLOWLIST = DATA / "domain_allowlist.json"

#: Only these may be registered against. The others are kept for completeness
#: and marked, so the registry can say "abolished in 1993" rather than nothing.
OPERATING = "Active"


def _slug(text: str) -> str:
    """A stable id from a name. Same shape as the SC ids: `fed.<abbrev-or-name>`."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "", text.lower())
    return text[:28]


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _domains(row: dict[str, Any]) -> list[str]:
    """Primary first, then the accepted list, de-duplicated and lowercased.

    The `Accepted Email Domains` cell is pipe-separated in the source
    (`oa.eop.gov | eop.gov`), and an agency that uses its parent department's
    mail is the reason the second one exists.
    """
    out: list[str] = []
    primary = _clean(row.get("Email Domain (Primary)")).lower()
    if primary:
        out.append(primary)
    for part in _clean(row.get("Accepted Email Domains")).lower().split("|"):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def read_agencies() -> list[dict[str, Any]]:
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    rows = list(wb["Federal Agencies"].iter_rows(values_only=True))
    header = [_clean(h) for h in rows[0]]

    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for raw in rows[1:]:
        if not any(raw):
            continue
        row = dict(zip(header, raw))
        name = _clean(row.get("Agency"))
        if not name:
            continue

        abbrev = _clean(row.get("Abbreviation"))
        base = _slug(abbrev or name)
        ident = f"fed.{base}"
        # Abbreviations repeat across the federal estate. Suffix rather than
        # overwrite: two agencies collapsing into one id would silently hide
        # whichever was read second.
        n = 2
        while ident in seen:
            ident = f"fed.{base}{n}"
            n += 1
        seen.add(ident)

        status = _clean(row.get("Operating Status")) or "Unknown"
        domains = _domains(row)
        confidence = _clean(row.get("Domain Confidence")).lower() or "none"
        evidence = _clean(row.get("Domain Evidence"))

        out.append({
            "id": ident,
            "name": name,
            "abbrev": abbrev,
            "category": _clean(row.get("Category")),
            "parent": _clean(row.get("Parent Department")),
            "domain": domains[0] if domains else "",
            "domains": domains,
            # Never inferred — see the module note.
            "convention": "any",
            "confidence": confidence,
            "source": (
                f"domain {evidence or 'not evidenced'}; local part not checked "
                f"— the federal sheet carries no staff addresses to derive a "
                f"naming convention from"),
            "website": _clean(row.get("Website")),
            "status": status,
            "registrable": bool(domains) and status == OPERATING,
            "cfo_act": _clean(row.get("CFO Act Agency")).lower() in ("yes", "y",
                                                                     "true"),
            # Governance-relevant and worth carrying: an agency that has already
            # published an AI inventory has done some of this work.
            "ai_inventory_url": _clean(row.get("AI Use Case Inventory URL")),
            "ai_policy_url": _clean(row.get("AI Strategy / Policy URL")),
            "chief_ai_officer": bool(_clean(row.get("Chief AI Officer"))),
        })
    return out


def read_allowlist() -> dict[str, dict[str, str]]:
    """Every domain the client's list vouches for, and who it belongs to."""
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    rows = list(wb["Email Domain Allowlist"].iter_rows(values_only=True))
    header = [_clean(h) for h in rows[0]]

    out: dict[str, dict[str, str]] = {}
    for raw in rows[1:]:
        if not any(raw):
            continue
        row = dict(zip(header, raw))
        domain = _clean(row.get("Accepted Email Domain")).lower()
        if not domain:
            continue
        # First writer wins. A domain shared by a department and its bureaus
        # belongs to whichever the sheet lists first, and the agency named here
        # is context for a refusal message, not an authorisation.
        out.setdefault(domain, {
            "agency": _clean(row.get("Agency")),
            "jurisdiction": _clean(row.get("Jurisdiction")),
            "confidence": _clean(row.get("Confidence")).lower(),
            "evidence": _clean(row.get("Evidence")),
        })
    return out


def report(agencies: list[dict[str, Any]],
           allowlist: dict[str, dict[str, str]]) -> None:
    print(f"source: {SOURCE.name}\n")
    print(f"federal entities      : {len(agencies)}")
    by_status = Counter(a["status"] for a in agencies)
    for status, n in by_status.most_common():
        print(f"    {status:<22} {n}")
    registrable = [a for a in agencies if a["registrable"]]
    print(f"  registrable         : {len(registrable)}"
          f"  (operating, with a published domain)")

    conf = Counter(a["confidence"] for a in registrable)
    print(f"  domain confidence   : "
          + ", ".join(f"{k} {v}" for k, v in conf.most_common()))

    dupes = [k for k, n in Counter(a["id"] for a in agencies).items() if n > 1]
    print(f"  duplicate ids       : {dupes or 'none'}")

    print(f"\nallowlist domains     : {len(allowlist)}")
    juris = Counter(v["jurisdiction"] for v in allowlist.values())
    for k, n in juris.most_common():
        print(f"    {k:<22} {n}")

    from app import onboarding
    odd = sorted(d for d in allowlist
                 if not d.endswith(onboarding.ELIGIBLE_SUFFIXES))
    print(f"  would fail the suffix rule without this list: {len(odd)}")
    for d in odd[:10]:
        print(f"    {d:<24} {allowlist[d]['agency'][:44]}")
    if len(odd) > 10:
        print(f"    …and {len(odd) - 10} more")


def main(argv: list[str]) -> int:
    if not SOURCE.is_file():
        print(f"not found: {SOURCE}")
        return 1

    agencies = read_agencies()
    allowlist = read_allowlist()
    report(agencies, allowlist)

    if "--write" not in argv:
        print("\nreport only — pass --write to update the data files")
        return 0

    DATA.mkdir(parents=True, exist_ok=True)
    OUT_AGENCIES.write_text(json.dumps({
        "source": SOURCE.name,
        "jurisdiction": "FED",
        "count": len(agencies),
        "registrable": sum(1 for a in agencies if a["registrable"]),
        "note": "Agency head names in the source are deliberately not imported.",
        "agencies": agencies,
    }, indent=2), encoding="utf-8")

    OUT_ALLOWLIST.write_text(json.dumps({
        "source": SOURCE.name,
        "count": len(allowlist),
        "note": "Exact domains the client's registry vouches for. Checked in "
                "addition to the suffix rule, never instead of it.",
        "domains": allowlist,
    }, indent=2), encoding="utf-8")

    print(f"\nwritten {OUT_AGENCIES.relative_to(DATA.parent.parent)}"
          f" and {OUT_ALLOWLIST.relative_to(DATA.parent.parent)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
