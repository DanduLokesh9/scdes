"""Turn the client's SC agency spreadsheet into the platform's agency list.

The spreadsheet has two sheets that matter. *Agencies* gives the name, category,
website and a general mailbox. *People* gives named officials with their real
work addresses — and that second sheet is what makes this worth doing properly,
because an agency's email convention can be **derived from its own staff
directory** rather than guessed.

Why derive rather than assume. `app/tenancy.py` refuses a registration whose
address does not match the agency's convention, and every refusal quotes the
form it expected. A wrong convention therefore locks real people out of their
own agency with a confidently-worded error. SC does not use one convention: the
Arts Commission runs `flast`, DES runs `first.last`, and some agencies mix. So
each convention here carries the evidence it was derived from and a confidence,
and where the evidence is thin the importer says so instead of picking a winner.

Shared mailboxes (info@, frontdesk@, medboard@) are excluded from the sample —
they are not a person's address and match no naming convention. Including them
was the first version's bug: `info@arts.sc.gov` looks exactly like `first` for
someone called Info.

Run:  python -m tools.import_sc_agencies            # report only
      python -m tools.import_sc_agencies --write    # write the data file
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

SOURCE = Path(r"C:\Users\dandu\sc-state-agencies.xlsx")
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "sc_agencies.json"

#: Local parts that are a function, not a person. Never evidence of a convention.
ROLE_MAILBOXES = {
    "info", "contact", "help", "support", "admin", "office", "mail", "general",
    "frontdesk", "reception", "publicinfo", "press", "media", "webmaster",
    "postmaster", "noreply", "no-reply", "donotreply", "inquiries", "enquiries",
    "customerservice", "service", "hr", "jobs", "careers", "legal", "records",
    "foia", "complaints", "questions", "feedback", "clerk", "director",
}
#: Anything ending in one of these is a board or programme mailbox.
ROLE_SUFFIXES = ("board", "boardoffice", "help", "helpdesk", "info", "mail",
                 "office", "support", "team", "program", "unit", "desk")


def _fold(text: str) -> str:
    """Strip accents, punctuation and case — the form a mail system would use."""
    text = unicodedata.normalize("NFKD", str(text or ""))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z]", "", text.lower())


def _name_parts(raw: str) -> tuple[str, str]:
    """(first, last) with credentials and middle names dropped.

    "James H. Hollis, DVM, MS" -> ("james", "hollis")
    "Mike Neault, DVM"         -> ("mike", "neault")
    "Ce Scott-Fitts"           -> ("ce", "scottfitts")
    """
    name = str(raw or "").split(",")[0]                 # drop credentials
    name = re.sub(r"\b(jr|sr|ii|iii|iv|dvm|md|phd|esq|cpa|pe|ms|ma|mba)\b\.?",
                  "", name, flags=re.I)
    words = [w for w in re.split(r"\s+", name.strip()) if w]
    # Single-letter words are middle initials, not names.
    words = [w for w in words if len(_fold(w)) > 1] or words
    if len(words) < 2:
        return "", ""
    return _fold(words[0]), _fold(words[-1])


#: Each convention, as a function of (first, last) producing the local part it
#: would generate. Order matters only for reporting; matching tries all.
CONVENTIONS: dict[str, Any] = {
    "first.last":  lambda f, l: f"{f}.{l}",
    "first_last":  lambda f, l: f"{f}_{l}",
    "firstlast":   lambda f, l: f"{f}{l}",
    "flast":       lambda f, l: f"{f[:1]}{l}",
    "f.last":      lambda f, l: f"{f[:1]}.{l}",
    "firstl":      lambda f, l: f"{f}{l[:1]}",
    "first":       lambda f, l: f,
    "last":        lambda f, l: l,
    "lastf":       lambda f, l: f"{l}{f[:1]}",
    "last.first":  lambda f, l: f"{l}.{f}",
    "fl":          lambda f, l: f"{f[:1]}{l[:1]}",
}


def _is_role_mailbox(local: str) -> bool:
    low = local.lower()
    return low in ROLE_MAILBOXES or low.endswith(ROLE_SUFFIXES)


def _load() -> tuple[list[dict], list[dict]]:
    wb = openpyxl.load_workbook(SOURCE, data_only=True)

    def rows(sheet: str) -> list[dict]:
        ws = wb[sheet]
        it = ws.iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(it)]
        out = []
        for row in it:
            rec = {h: ("" if v is None else str(v).strip())
                   for h, v in zip(head, row)}
            if any(rec.values()):
                out.append(rec)
        return out

    return rows("Agencies"), rows("People")


STOP_WORDS = {"of", "the", "for", "and", "on", "in", "to", "a", "s"}


def _significant(name: str) -> list[str]:
    return [w for w in re.split(r"[^A-Za-z]+", name)
            if w and w.lower() not in STOP_WORDS]


def _abbrev(name: str) -> str:
    """The agency's own shorthand where it publishes one, else initials.

    "Commission for the Blind (SCCB)" -> SCCB. Where the spreadsheet publishes
    no shorthand this builds one from initials and prefixes SC, because that is
    how South Carolina agencies actually write themselves — the Department of
    Education is SCDE, not DE. The prefix is only added below four characters,
    so it never lengthens a shorthand that already reads as one.
    """
    bracket = re.search(r"\(([A-Z][A-Za-z0-9\-]{1,12})\)\s*$", name)
    if bracket:
        return bracket.group(1)
    initials = "".join(w[0] for w in _significant(name)[:5]).upper() or "AG"
    if len(initials) < 4 and not initials.startswith("SC"):
        initials = "SC" + initials
    return initials


def _disambiguate(entries: list[dict[str, Any]]) -> None:
    """Make every shorthand unique.

    Three SC bodies are a "Commission" whose other word starts with A — Arts,
    Athletic, Auctioneers' — so initials alone give all three SCAC. A shorthand
    that names three different agencies is worse than a long one: it is what the
    "Enter SCAC" button says, and the header chip, and the audit trail.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        groups.setdefault(e["abbrev"], []).append(e)

    for abbrev, clash in groups.items():
        if len(clash) < 2:
            continue
        for entry in clash:
            words = _significant(entry["name"])
            # Grow the *last* word, which is the one that differs. Growing the
            # first gives DEPA and SCDEA for Agriculture and Administration —
            # unique, but telling you nothing. Growing the last gives DAGRI and
            # DADMIN, which a reader can place at a glance.
            for size in range(2, 8):
                last = len(words[:5]) - 1
                grown = "".join(
                    w[:size] if i == last else w[0]
                    for i, w in enumerate(words[:5])
                ).upper()
                if len(grown) < 4 and not grown.startswith("SC"):
                    grown = "SC" + grown
                if all(o is entry or o["abbrev"] != grown for o in entries):
                    entry["abbrev"] = grown
                    break


def _clean_name(name: str) -> str:
    return re.sub(r"\s*\([A-Z][A-Za-z0-9\-]{1,12}\)\s*$", "", name).strip()


def _domain(email: str) -> str:
    return email.split("@")[-1].strip().lower() if "@" in email else ""


#: Conventions the client stated directly. Keyed by id or by domain, because a
#: derived id can move if an abbreviation changes but a mail domain does not.
CONFIRMED: dict[str, dict[str, Any]] = {
    # The ids are pinned, not derived. Containers, ownership records and audit
    # entries already reference them, and an id that moves when an abbreviation
    # changes would orphan a real agency's history.
    "des.sc.gov": {"id": "sc.des", "abbrev": "SCDES", "convention": "first.last",
                   "source": "confirmed by the client, August 2026"},
    "ed.sc.gov": {"id": "sc.ed", "abbrev": "SCDE", "convention": "flast",
                  "source": "confirmed by the client, August 2026"},
}


def derive() -> dict[str, Any]:
    agencies, people = _load()

    by_agency: dict[str, list[dict]] = {}
    for p in people:
        by_agency.setdefault(p.get("Agency", ""), []).append(p)

    out: list[dict[str, Any]] = []
    for row in agencies:
        raw_name = row.get("Agency", "")
        if not raw_name:
            continue

        staff = by_agency.get(raw_name, [])
        samples: list[tuple[str, str, str]] = []      # (first, last, local)
        domains: Counter = Counter()

        for person in staff:
            email = (person.get("Email") or "").strip().lower()
            if "@" not in email:
                continue
            local, dom = email.split("@", 1)
            domains[dom] += 1
            if _is_role_mailbox(local):
                continue
            first, last = _name_parts(person.get("Name", ""))
            if first and last:
                samples.append((first, last, local))

        # The general mailbox still evidences the domain even when it evidences
        # no convention.
        general = (row.get("Email") or "").strip().lower()
        if "@" in general:
            domains[_domain(general)] += 1

        hits: Counter = Counter()
        for first, last, local in samples:
            for key, build in CONVENTIONS.items():
                if build(first, last) == local:
                    hits[key] += 1

        matched = {local for f, l, local in samples
                   if any(b(f, l) == local for b in CONVENTIONS.values())}
        unmatched = [local for f, l, local in samples if local not in matched]

        convention, confidence, source = "any", "none", ""
        if hits:
            top, n = hits.most_common(1)[0]
            total = len(samples)
            # Two agreeing addresses is a pattern; one is a coincidence waiting
            # to lock somebody out.
            if n >= 2 and n >= total * 0.6:
                convention, confidence = top, "strong" if n >= 3 else "weak"
            elif n >= 1:
                convention, confidence = "any", "weak"
            source = (f"derived from {n} of {total} published staff address(es) "
                      f"in the client's SC agency spreadsheet")
            if unmatched:
                source += f"; {len(unmatched)} did not match any pattern"
        elif samples:
            source = (f"{len(samples)} staff address(es) published, none matching "
                      f"a standard pattern — domain checked, local part not")
        else:
            source = "no published staff addresses; domain checked, local part not"

        domain = domains.most_common(1)[0][0] if domains else ""
        website = (row.get("Website") or "").strip().lower()
        if not domain and website:
            domain = re.sub(r"^www\.", "", website.split("/")[0])
            source += "; domain taken from the published website, not from mail"

        name = _clean_name(raw_name)
        out.append({
            "id": "sc." + re.sub(r"[^a-z0-9]+", "", _abbrev(raw_name).lower()),
            "name": name,
            "abbrev": _abbrev(raw_name),
            "category": row.get("Category", ""),
            "domain": domain,
            "convention": convention,
            "confidence": confidence,
            "source": source,
            "website": website,
            "head": row.get("Agency Head", ""),
            "head_title": row.get("Head Title", ""),
            "staff_sampled": len(samples),
        })

    _disambiguate(out)

    # Ids come from abbreviations, and a collision would silently merge two
    # agencies' containers — so make them unique here rather than discovering it
    # in production.
    seen: Counter = Counter()
    for entry in out:
        entry["id"] = "sc." + re.sub(r"[^a-z0-9]+", "", entry["abbrev"].lower())
        seen[entry["id"]] += 1
        if seen[entry["id"]] > 1:
            entry["id"] = f"{entry['id']}{seen[entry['id']]}"

    # What the client told us outranks what the importer inferred. A convention
    # confirmed by the agency is stronger evidence than a pattern matched across
    # four published addresses, and quietly downgrading it to "any" would drop a
    # real check.
    for entry in out:
        override = CONFIRMED.get(entry["id"]) or CONFIRMED.get(entry["domain"])
        if override:
            entry.update(override)
            entry["confidence"] = "confirmed"

    return {
        "source": "sc-state-agencies.xlsx, supplied by the client 20 August 2026",
        "state": "SC",
        "count": len(out),
        "agencies": sorted(out, key=lambda a: a["name"]),
    }


def main() -> int:
    data = derive()
    rows = data["agencies"]
    conv = Counter(a["convention"] for a in rows)
    conf = Counter(a["confidence"] for a in rows)

    print(f"{data['count']} agencies from {SOURCE.name}\n")
    print("conventions derived:")
    for key, n in conv.most_common():
        print(f"  {key:12} {n:4}")
    print("\nconfidence:")
    for key, n in conf.most_common():
        print(f"  {key:12} {n:4}")
    print(f"\nwith a usable domain: {sum(1 for a in rows if a['domain'])}")
    print("\nsample of what was derived:")
    for a in [x for x in rows if x["confidence"] == "strong"][:8]:
        print(f"  {a['abbrev']:10} {a['domain']:24} {a['convention']:11} "
              f"({a['staff_sampled']} sampled)")

    if "--write" in sys.argv:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"\nwrote {OUT}")
    else:
        print("\n(report only — pass --write to save)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
