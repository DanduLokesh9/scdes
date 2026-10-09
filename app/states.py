"""State registry — the launcher's list of agencies, and their themes.

This is a *starting point*, not an authority. It carries the commonly used name
and abbreviation of each state's environmental agency so the launcher has
something to show before any corpus is loaded, and a deterministic placeholder
palette so each state looks distinct.

Two honesty rules hold throughout:

  · every seeded agency name is marked `verified: False`. Agencies rename
    themselves — South Carolina's did in 2024 — so the seed is a label to be
    confirmed, never relied on.
  · placeholder palettes are marked as such. A palette becomes authoritative
    only when the state supplies its own brand tokens.

An agency's brand is however many colors it actually has — two, three, eight —
and that list is never padded. app/theme.py fills interface roles by reusing
them, so a two-color agency is themed in exactly its two colors.

When a state's corpus is actually loaded, `profile.discover()` reads the real
name out of the adopted documents and overrides the seed. The seed exists so the
map is not blank on day one.
"""

from __future__ import annotations

import functools
import json
import pathlib

import colorsys
import hashlib
import re
from dataclasses import dataclass, asdict, field as dc_field
from typing import Any

from app.theme import BRAND_ROLES, STATUS, theme_for

# --------------------------------------------------------------- tile layout
#
# A tile cartogram rather than a geographic outline: uniform hit targets, every
# state legible regardless of area, and no false precision about borders.
# Rows run north to south, columns west to east.

TILE_GRID: list[list[str]] = [
    ["AK", "",   "",   "",   "",   "",   "",   "",   "",   "",   "",   "ME"],
    ["",   "",   "",   "",   "",   "",   "",   "",   "",   "VT", "NH", ""],
    ["WA", "MT", "ND", "MN", "WI", "",   "MI", "",   "NY", "MA", "",   ""],
    ["OR", "ID", "SD", "IA", "IL", "IN", "OH", "PA", "NJ", "CT", "RI", ""],
    ["CA", "NV", "WY", "NE", "MO", "KY", "WV", "VA", "MD", "DE", "",   ""],
    ["",   "UT", "CO", "KS", "AR", "TN", "NC", "SC", "DC", "",   "",   ""],
    ["",   "AZ", "NM", "OK", "LA", "MS", "AL", "GA", "",   "",   "",   ""],
    ["HI", "",   "",   "TX", "",   "",   "",   "",   "FL", "",   "",   ""],
]

#: Commonly used name of each state's environmental agency. Seeded so the
#: launcher is not empty; every entry is unverified until a corpus confirms it.
#: States open for registration. Everything else is drawn on the map but cannot
#: be selected — visible so the reach is obvious, greyed so nobody starts a
#: registration the platform cannot yet honour.
#:
#: A state opens when its environmental agency and that agency's email domain
#: are on record. All fifty-one now are — see `_ENV_DOMAINS` — so all fifty-one
#: are open.
#:
#: What has *not* been confirmed for forty-nine of them is the local-part
#: convention, and for most of them the domain is the state's rather than the
#: agency's. Neither is a reason to keep a state shut, and the reason is the
#: shape of registration rather than optimism: an address is checked against
#: the domain, and then **a person approves the registration**. On a statewide
#: domain the check proves the applicant works for that state government and
#: no more, and the approver is told so in those words. Nobody is admitted to
#: a container by arithmetic alone.
#:
#: Closing this back to a handful is one line, and `tools/agency_domains.py`
#: prints what is still owed.
#:
#: Defined below, next to `STATE_NAMES`, which is the list it is built from.

#: The governmental units inside a launched state. A state is not one agency:
#: environmental services, education and the rest each run their own governance,
#: each with their own email convention.
#:
#: Only what has been confirmed appears here. This list is what the "select your
#: agency" dropdown offers, so an omission is better than an invention.
#: IIA's own container, for demonstrating the platform. Kept visible in the
#: dropdown at the client's direction — this is not a finished product and a
#: hidden demo helps nobody — but named so it can never be mistaken for a real
#: governmental unit in a screenshot.
DEMO_AGENCY: dict[str, str] = {
    # Still `iia.test` on the record. The client asked for the *label* to read
    # DEMO; changing the id would orphan the registrations already sitting in
    # this container, which is a real cost for a cosmetic gain.
    "id": "iia.test",
    "name": "DEMO agency — Innovative Infrastructure Advising",
    "abbrev": "DEMO",
    "domain": "iiac.ai",
    # Domain checked, local part not: a demo container exists to be used, so it
    # must not impose a naming rule on the people using it.
    "convention": "any",
    "test_only": "yes",
}

#: The container the automated checks own. Deliberately *not* in
#: `agencies_for`, so it never appears in the "select your agency" dropdown —
#: nobody should be able to pick it — but present in `agency_ids` so the checks
#: can register into it through the ordinary flow.
#:
#: It exists because the checks and the client were sharing `iia.test`. The
#: browser walks blank answers to make themselves deterministic, and on staging
#: they did that to his real work.
HARNESS_AGENCY: dict[str, str] = {
    "id": "gaius.harness",
    "name": "TEST — automated checks only, not for people",
    "abbrev": "HARNESS",
    "domain": "harness.gaius.test",
    "convention": "any",
    "test_only": "yes",
}

#: Where the imported list lives. Built by tools/import_sc_agencies.py from the
#: client's spreadsheet; see that file for how each convention was derived.
_SC_DATA = pathlib.Path(__file__).resolve().parent / "data" / "sc_agencies.json"

#: The federal estate, from the same workbook. See tools/import_federal_agencies.py.
_FED_DATA = (pathlib.Path(__file__).resolve().parent / "data"
             / "federal_agencies.json")

#: The federal government is not a state, but it is a jurisdiction someone can
#: register under, so it needs a code the rest of the application can carry
#: without special-casing. Chosen not to collide with any USPS state code.
FEDERAL_CODE = "FED"


@functools.lru_cache(maxsize=1)
def federal_agencies() -> list[dict[str, str]]:
    """Federal entities somebody could actually register under.

    The client's list holds 472, of which 339 operate and 334 of those publish
    a domain. Only those 334 are returned: an agency abolished in 1993 is
    correct to keep in the registry and absurd to offer as a place to sign in.

    Every one is `convention: "any"`. The SC list could derive that an agency
    runs `first.last` because the client's People sheet gave real staff
    addresses to count; the federal sheet has no equivalent, so the domain is
    checked and the local part is not.
    """
    try:
        raw = json.loads(_FED_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for a in raw.get("agencies", []):
        if not a.get("registrable"):
            continue
        out.append({
            "id": a["id"],
            "name": a["name"],
            "abbrev": a.get("abbrev", ""),
            "domain": a.get("domain", ""),
            "domains": a.get("domains", []),
            "convention": a.get("convention", "any"),
            "confidence": a.get("confidence", "none"),
            "category": a.get("category", ""),
            "parent": a.get("parent", ""),
        })
    return sorted(out, key=lambda a: a["name"].lower())


@functools.lru_cache(maxsize=1)
def _sc_agencies() -> list[dict[str, str]]:
    """South Carolina's 148 state agencies, from the client's own list.

    Each entry carries the convention that was derived for it and how confident
    that derivation is. Most agencies publish no staff addresses, so most are
    `any` — domain checked, local part not. That is the honest position: a
    guessed convention refuses real people at the door with a confidently
    worded error, which is worse than no rule at all.
    """
    try:
        raw = json.loads(_SC_DATA.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        # The launcher must still open. Fall back to the two the client
        # confirmed directly rather than to nothing.
        return [
            {"id": "sc.scdes", "abbrev": "SCDES", "domain": "des.sc.gov",
             "name": "South Carolina Department of Environmental Services",
             "convention": "first.last", "confidence": "confirmed"},
            {"id": "sc.scde", "abbrev": "SCDE", "domain": "ed.sc.gov",
             "name": "South Carolina Department of Education",
             "convention": "flast", "confidence": "confirmed"},
        ]
    out = []
    for a in raw.get("agencies", []):
        if not a.get("domain"):
            continue                     # nowhere to check an address against
        out.append({
            "id": a["id"],
            # The spreadsheet names them as the state does — "Department of
            # Environmental Services". Prefixed here so the dropdown reads the
            # way someone would say it out loud.
            "name": f"South Carolina {a['name']}"
                    if not a["name"].lower().startswith("south carolina")
                    else a["name"],
            "abbrev": a["abbrev"],
            "domain": a["domain"],
            "convention": a.get("convention", "any"),
            "confidence": a.get("confidence", "none"),
            "category": a.get("category", ""),
        })
    return out


#: The governmental units inside a launched state, as the dropdown offers them.
#:
#: New Mexico is the first state opened after South Carolina, and the first
#: time two real agencies have existed side by side — which is the case the
#: isolation rule exists for, so `tests/test_isolation.py` covers it by name.
#:
#: Named as the client named it. The agency itself trades as the New Mexico
#: Environment Department, which is what `AGENCIES` below still carries for
#: the map; the label here is the one he asked for and it is the one that
#: reaches the front of an adopted document, so it is worth him confirming.
#:
#: No convention: he gave the domain and not the local part, so the address is
#: checked for `@env.nm.gov` and the name part is not. That is the honest
#: setting rather than a guessed rule that turns away a real deputy director,
#: and `confidence` records that nobody has confirmed one.
#: The email domain each state's environmental agency uses, and — the part
#: that matters — whether that domain belongs to the agency or to the whole
#: state government.
#:
#: `agency` means the domain is the agency's own, so an address ending in it
#: is somebody at that agency. `statewide` means it is shared with every
#: other department in the state: a `@pa.gov` address is a Pennsylvania state
#: employee and says nothing about which department. Most states turn out to
#: be the second kind, which was not the assumption this table was started on.
#:
#: That distinction is recorded rather than smoothed over, because it decides
#: how much the domain check is worth. On a statewide domain the check proves
#: the person works for the state and nothing more, and the human approval
#: step is doing all the remaining work. A reviewer is told so.
#:
#: `checked` marks the twelve verified against addresses the agency itself
#: publishes, on 23 September 2026. Everything else is this application's own
#: best reading and carries `unconfirmed` — a real answer, and the one the
#: confirmation report at `tools/agency_domains.py` exists to close out.
AGENCY_DOMAIN = "agency"
STATEWIDE_DOMAIN = "statewide"

#: Where a domain came from. Its own field, and deliberately not folded into
#: `confidence`.
#:
#: `confidence` has meant one thing since the South Carolina list was
#: imported: how much is known about the **local-part** rule — `strong` from
#: many published addresses, `weak` from a few, `none` where none were
#: published and the local part is therefore not checked at all. Reusing it
#: for the domain looked tidy and was wrong: it made New Mexico read as
#: confirmed when what the client confirmed was the domain and not the naming
#: rule, and a test written precisely to stop that drift caught it.
#:
#: So the two axes stay apart. Every state outside South Carolina has
#: `confidence = "none"`, because nobody has confirmed a local-part rule for
#: any of them, and `domain_source` says separately who vouched for the
#: domain.
DOMAIN_STATED = "stated"          # the client said so outright
DOMAIN_CHECKED = "checked"        # verified against the agency's own pages
DOMAIN_UNCONFIRMED = "unconfirmed"   # this application's reading, unchecked

_ENV_DOMAINS: dict[str, tuple[str, str, bool]] = {
    # code: (domain, whose domain it is, verified against published addresses)
    "AL": ("adem.alabama.gov", AGENCY_DOMAIN, False),
    "AK": ("alaska.gov", STATEWIDE_DOMAIN, False),
    "AZ": ("azdeq.gov", AGENCY_DOMAIN, False),
    "AR": ("adeq.state.ar.us", AGENCY_DOMAIN, False),
    "CA": ("calepa.ca.gov", AGENCY_DOMAIN, False),
    "CO": ("state.co.us", STATEWIDE_DOMAIN, True),
    "CT": ("ct.gov", STATEWIDE_DOMAIN, False),
    "DE": ("delaware.gov", STATEWIDE_DOMAIN, False),
    "DC": ("dc.gov", STATEWIDE_DOMAIN, False),
    "FL": ("floridadep.gov", AGENCY_DOMAIN, False),
    "GA": ("dnr.ga.gov", AGENCY_DOMAIN, False),
    "HI": ("doh.hawaii.gov", AGENCY_DOMAIN, False),
    "ID": ("deq.idaho.gov", AGENCY_DOMAIN, False),
    "IL": ("illinois.gov", STATEWIDE_DOMAIN, False),
    "IN": ("idem.in.gov", AGENCY_DOMAIN, False),
    "IA": ("dnr.iowa.gov", AGENCY_DOMAIN, False),
    "KS": ("ks.gov", STATEWIDE_DOMAIN, True),
    "KY": ("ky.gov", STATEWIDE_DOMAIN, False),
    "LA": ("la.gov", STATEWIDE_DOMAIN, True),
    "ME": ("maine.gov", STATEWIDE_DOMAIN, False),
    "MD": ("maryland.gov", STATEWIDE_DOMAIN, False),
    "MA": ("mass.gov", STATEWIDE_DOMAIN, False),
    "MI": ("michigan.gov", STATEWIDE_DOMAIN, True),
    "MN": ("state.mn.us", STATEWIDE_DOMAIN, False),
    "MS": ("mdeq.ms.gov", AGENCY_DOMAIN, False),
    "MO": ("dnr.mo.gov", AGENCY_DOMAIN, False),
    "MT": ("mt.gov", STATEWIDE_DOMAIN, False),
    "NE": ("nebraska.gov", STATEWIDE_DOMAIN, False),
    "NV": ("ndep.nv.gov", AGENCY_DOMAIN, False),
    "NH": ("des.nh.gov", AGENCY_DOMAIN, False),
    "NJ": ("dep.nj.gov", AGENCY_DOMAIN, False),
    # The one the client stated outright. Kept here so the table is complete,
    # and overridden below by the entry he gave.
    "NM": ("env.nm.gov", AGENCY_DOMAIN, True),
    "NY": ("dec.ny.gov", AGENCY_DOMAIN, False),
    "NC": ("deq.nc.gov", AGENCY_DOMAIN, False),
    "ND": ("nd.gov", STATEWIDE_DOMAIN, True),
    "OH": ("epa.ohio.gov", AGENCY_DOMAIN, False),
    "OK": ("deq.ok.gov", AGENCY_DOMAIN, False),
    "OR": ("deq.oregon.gov", AGENCY_DOMAIN, False),
    "PA": ("pa.gov", STATEWIDE_DOMAIN, True),
    "RI": ("dem.ri.gov", AGENCY_DOMAIN, False),
    # SC is absent on purpose. Its 148 governmental units come from the
    # client's own spreadsheet through `_sc_agencies()`, with the
    # environmental department among them, and generating a 149th here would
    # give that department two entries with two ids.
    "SD": ("state.sd.us", STATEWIDE_DOMAIN, False),
    "TN": ("tn.gov", STATEWIDE_DOMAIN, False),
    "TX": ("tceq.texas.gov", AGENCY_DOMAIN, True),
    "UT": ("utah.gov", STATEWIDE_DOMAIN, True),
    "VT": ("vermont.gov", STATEWIDE_DOMAIN, True),
    "VA": ("deq.virginia.gov", AGENCY_DOMAIN, False),
    "WA": ("ecy.wa.gov", AGENCY_DOMAIN, True),
    "WV": ("wv.gov", STATEWIDE_DOMAIN, True),
    "WI": ("wisconsin.gov", STATEWIDE_DOMAIN, False),
    "WY": ("wyo.gov", STATEWIDE_DOMAIN, True),
}

#: The client's own entry for New Mexico, which outranks the generated one.
#:
#: He gave the domain — "email of this state must end with this @env.nm.gov"
#: — and not the naming rule, so the address is checked for the domain and
#: the local part is not. That is the honest setting rather than a guessed
#: rule that turns away a real deputy director.
#:
#: He also named the agency the New Mexico Department of the Environment. It
#: trades as the New Mexico Environment Department; his name is the one that
#: reaches the front of an adopted document, so it is the one used, and it is
#: still worth him confirming.
_STATED: dict[str, dict[str, str]] = {
    "NM": {
        "id": "nm.env",
        "name": "New Mexico Department of the Environment",
        "abbrev": "NMED",
        "domain": "env.nm.gov",
        "scope": AGENCY_DOMAIN,
        "convention": "any",
        # The domain is his; the naming rule is nobody's yet. Two fields
        # because they are two facts.
        "domain_source": DOMAIN_STATED,
        "confidence": "none",
    },
}


def _state_agencies() -> dict[str, list[dict[str, str]]]:
    """One environmental agency per state, built from the names already on
    the map rather than typed out a second time.

    `AGENCIES` is where a state's environmental department gets its name and
    its abbreviation, for the map. Repeating those fifty-one names here would
    be fifty-one chances for the map and the registration dropdown to
    disagree about what an agency is called — which happened once already,
    with New Mexico, and put two different names for one agency in front of
    one user.

    No convention is set for any of them. Nobody has confirmed a local-part
    rule for a single state outside South Carolina, and a guessed rule that
    refuses a real deputy director is worse than no rule.
    """
    built: dict[str, list[dict[str, str]]] = {}
    for code, (domain, scope, checked) in _ENV_DOMAINS.items():
        if code in _STATED:
            built[code] = [dict(_STATED[code])]
            continue
        name, abbrev = AGENCIES[code]
        built[code] = [{
            "id": f"{code.lower()}.env",
            "name": name,
            "abbrev": abbrev,
            "domain": domain,
            "scope": scope,
            "convention": "any",
            "domain_source": DOMAIN_CHECKED if checked
            else DOMAIN_UNCONFIRMED,
            # Nobody has confirmed a local-part rule for any state outside
            # South Carolina, so the local part is not checked anywhere else.
            "confidence": "none",
        }]
    return built


#: `STATE_AGENCIES` itself is built further down, immediately after
#: `AGENCIES`, because it reads the names out of it and a module-level call
#: cannot run before the thing it reads exists.


def agencies_for(code: str) -> list[dict[str, str]]:
    code = (code or "").upper()
    if code == FEDERAL_CODE:
        return federal_agencies()
    if code in STATE_AGENCIES:
        return STATE_AGENCIES[code]
    if code == "SC":
        # Demo last, so a real agency is what a user reaches for first.
        return _sc_agencies() + [DEMO_AGENCY]
    return []


@functools.lru_cache(maxsize=1)
def agency_ids() -> frozenset[str]:
    """Every agency id the platform knows, across all jurisdictions.

    Registration checks against this. Without it `start_registration` accepted
    any string as an agency: a walkthrough that asked for `sc.scde` — a typo for
    `sc.ed` — created a real container for an agency that does not exist, which
    then resolved to no name, so the framework it exported had no agency on the
    title page and no way to get one.
    """
    ids: set[str] = set()
    for code in list(STATE_NAMES) + [FEDERAL_CODE]:
        ids.update(a["id"] for a in agencies_for(code) if a.get("id"))
    # Registerable, but never offered: the checks need somewhere to write that
    # is not a container a person is using.
    ids.add(HARNESS_AGENCY["id"])
    return frozenset(ids)


def is_open(code: str) -> bool:
    return (code or "").upper() in LAUNCH_STATES


AGENCIES: dict[str, tuple[str, str]] = {
    "AL": ("Alabama Department of Environmental Management", "ADEM"),
    "AK": ("Alaska Department of Environmental Conservation", "ADEC"),
    "AZ": ("Arizona Department of Environmental Quality", "ADEQ"),
    "AR": ("Arkansas Division of Environmental Quality", "DEQ"),
    "CA": ("California Environmental Protection Agency", "CalEPA"),
    "CO": ("Colorado Department of Public Health and Environment", "CDPHE"),
    "CT": ("Connecticut Department of Energy and Environmental Protection", "DEEP"),
    "DE": ("Delaware Department of Natural Resources and Environmental Control",
           "DNREC"),
    "DC": ("District Department of Energy and Environment", "DOEE"),
    "FL": ("Florida Department of Environmental Protection", "FDEP"),
    "GA": ("Georgia Environmental Protection Division", "EPD"),
    "HI": ("Hawaii Department of Health, Environmental Health", "DOH"),
    "ID": ("Idaho Department of Environmental Quality", "DEQ"),
    "IL": ("Illinois Environmental Protection Agency", "Illinois EPA"),
    "IN": ("Indiana Department of Environmental Management", "IDEM"),
    "IA": ("Iowa Department of Natural Resources", "Iowa DNR"),
    "KS": ("Kansas Department of Health and Environment", "KDHE"),
    "KY": ("Kentucky Energy and Environment Cabinet", "EEC"),
    "LA": ("Louisiana Department of Environmental Quality", "LDEQ"),
    "ME": ("Maine Department of Environmental Protection", "Maine DEP"),
    "MD": ("Maryland Department of the Environment", "MDE"),
    "MA": ("Massachusetts Department of Environmental Protection", "MassDEP"),
    "MI": ("Michigan Department of Environment, Great Lakes, and Energy", "EGLE"),
    "MN": ("Minnesota Pollution Control Agency", "MPCA"),
    "MS": ("Mississippi Department of Environmental Quality", "MDEQ"),
    "MO": ("Missouri Department of Natural Resources", "MoDNR"),
    "MT": ("Montana Department of Environmental Quality", "Montana DEQ"),
    "NE": ("Nebraska Department of Environment and Energy", "NDEE"),
    "NV": ("Nevada Division of Environmental Protection", "NDEP"),
    "NH": ("New Hampshire Department of Environmental Services", "NHDES"),
    "NJ": ("New Jersey Department of Environmental Protection", "NJDEP"),
    # Named as the client named it, and matched to the dropdown entry in
    # STATE_AGENCIES above. The two disagreeing gave the same agency two names
    # in one product — the map called it the Environment Department and the
    # registration form called it the Department of the Environment.
    "NM": ("New Mexico Department of the Environment", "NMED"),
    "NY": ("New York State Department of Environmental Conservation", "DEC"),
    "NC": ("North Carolina Department of Environmental Quality", "NCDEQ"),
    "ND": ("North Dakota Department of Environmental Quality", "NDDEQ"),
    "OH": ("Ohio Environmental Protection Agency", "Ohio EPA"),
    "OK": ("Oklahoma Department of Environmental Quality", "ODEQ"),
    "OR": ("Oregon Department of Environmental Quality", "Oregon DEQ"),
    "PA": ("Pennsylvania Department of Environmental Protection", "PADEP"),
    "RI": ("Rhode Island Department of Environmental Management", "RIDEM"),
    "SC": ("South Carolina Department of Environmental Services", "SCDES"),
    "SD": ("South Dakota Department of Agriculture and Natural Resources", "DANR"),
    "TN": ("Tennessee Department of Environment and Conservation", "TDEC"),
    "TX": ("Texas Commission on Environmental Quality", "TCEQ"),
    "UT": ("Utah Department of Environmental Quality", "Utah DEQ"),
    "VT": ("Vermont Department of Environmental Conservation", "Vermont DEC"),
    "VA": ("Virginia Department of Environmental Quality", "Virginia DEQ"),
    "WA": ("Washington State Department of Ecology", "Ecology"),
    "WV": ("West Virginia Department of Environmental Protection", "WVDEP"),
    "WI": ("Wisconsin Department of Natural Resources", "Wisconsin DNR"),
    "WY": ("Wyoming Department of Environmental Quality", "Wyoming DEQ"),
}


#: The governmental units inside a state, as the dropdown offers them.
#:
#: Built from `AGENCIES` above rather than written out a second time. South
#: Carolina is absent — its units come from the client's own list — and New
#: Mexico's entry is the one he stated.
STATE_AGENCIES: dict[str, list[dict[str, str]]] = _state_agencies()


def needs_confirming() -> list[dict[str, str]]:
    """Every agency whose email domain nobody has confirmed.

    The list somebody has to close out before these are more than a good
    guess. Ordered worst first: a statewide domain nobody has checked is the
    weakest thing in the table, because it admits the whole state government
    and no person has looked at it.
    """
    rows = []
    for code in sorted(STATE_AGENCIES):
        for a in STATE_AGENCIES[code]:
            if a.get("domain_source") == DOMAIN_STATED:
                continue
            rows.append({**a, "state": code})
    rows.sort(key=lambda a: (a["domain_source"] != DOMAIN_UNCONFIRMED,
                             a["scope"] != STATEWIDE_DOMAIN, a["state"]))
    return rows


STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida",
    "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky",
    "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont",
    "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}

#: Every state and the District, open for registration. The reasoning is at
#: the top of this module, where this used to be a set of two.
LAUNCH_STATES: set[str] = set(STATE_NAMES)


# ------------------------------------------------------------------- theming

#: Palettes with a real source behind them. Each records where it came from,
#: because "we have a brand guide" and "we converted two Pantone chips" are very
#: different levels of confidence and the UI should say which.
#:
#: There is no public registry of 50 state environmental-agency palettes. Most
#: agencies publish no hex values at all; some publish Pantone only; several
#: inherit a statewide standard rather than holding their own. So this table
#: stays small and honest, and everything else is a placeholder until the agency
#: supplies `corpus/config/brand.yaml`.
#:
#: Each entry is a *list*, holding exactly the colours that source documents.
#: There is no fixed palette length to fill: SCDES publishes eight, TCEQ
#: publishes two Pantone chips, the Commonwealth publishes three. Padding the
#: short ones out to eight is what made every state look alike, so they stay the
#: length they actually are and app/theme.py fills interface roles by reuse.
SOURCED_PALETTES: dict[str, tuple[str, list[str]]] = {
    "SC": ("brand guide", [
        # SCDES Brand Style Guide, supplied with the corpus. All eight.
        "#003e53", "#356584", "#0d757f", "#23884c",
        "#babc33", "#86c8bc", "#c4ced4", "#071e32",
    ]),
    "TX": ("Pantone-derived", [
        # TCEQ Logo Public Use Style Guide specifies PMS 313 C and PMS 377 C and
        # gives no hex values. Two chips, two colours — standard conversions, so
        # close rather than exact.
        "#0092bc", "#7a9a01",
    ]),
    "MA": ("statewide standard", [
        # Commonwealth of Massachusetts digital brand — MassDEP inherits it.
        # Bay Blue, Berkshires Green, Duckling Yellow. Three, not eight.
        "#14558f", "#388557", "#f6c51b",
    ]),
}

#: An agency may drop its real palette in alongside its corpus. This overrides
#: everything above, and is how a state gets its actual brand into the app.
BRAND_OVERRIDE = "config/brand.yaml"


_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def _override_palette(code: str) -> tuple[str, list[str]] | None:
    """Read `corpus/config/brand.yaml` if the agency has supplied one.

    Accepts either a `colors:` list — the current form, and however long the
    agency's brand actually is — or the older mapping of named slots, whose
    values are taken in order so an existing hand-written file keeps working.
    """
    from app.audit import CORPUS
    path = CORPUS / BRAND_OVERRIDE
    if not path.exists():
        return None
    try:
        import yaml
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    entry = (data.get("palettes") or {}).get(code.upper())
    if not isinstance(entry, dict):
        return None

    source = entry.get("source", "supplied brand file")
    raw = entry.get("colors")
    if raw is None:
        # Legacy slot-per-key form. Order is unreliable, so sort dark to light
        # to at least give the chrome role something dark to work with.
        raw = [v for k, v in entry.items() if k != "source"]
    if isinstance(raw, str):
        raw = [raw]
    colors: list[str] = []
    for value in raw or []:
        if isinstance(value, str) and _HEX.match(value.strip()):
            colour = value.strip().lower()
            if colour not in colors:
                colors.append(colour)
    return (source, colors) if colors else None


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def _shift(hue: float, delta: float, sat: float, light: float) -> str:
    h = (hue + delta) % 1.0
    return _hex(*colorsys.hls_to_rgb(h, light, sat))


def placeholder_colors(code: str) -> list[str]:
    """A stable neutral pair for an agency whose colors we do not have.

    Deliberately *not* a full invented palette. When there is no evidence, the
    honest rendering is a plain slate interface that visibly isn't anybody's
    brand — a hash-generated eight-color scheme merely looks confident about
    something it made up. Hue varies a little by state so the states remain
    distinguishable at a glance, and stays desaturated so none of them reads as
    a claim.
    """
    digest = hashlib.sha256(code.encode()).digest()
    hue = digest[0] / 255.0
    return [_shift(hue, 0.00, 0.16, 0.19),     # slate chrome
            _shift(hue, 0.02, 0.20, 0.42)]     # slate accent


@dataclass
class StateEntry:
    code: str
    state: str
    agency: str
    abbrev: str
    #: Exactly the colours this agency has — 2, 4, 8, however many. Interface
    #: roles are filled from these by reuse; see app/theme.py.
    colors: list[str] = dc_field(default_factory=list)
    roles: dict[str, str] = dc_field(default_factory=dict)
    theme: dict[str, str] = dc_field(default_factory=dict)
    palette_source: str = "derived"
    name_verified: bool = False
    corpus_loaded: bool = False
    brand_count: int = 0
    is_brand: bool = False          # true only when a brand document backs it
    provenance: str = "generated"   # brand | scraped | documented | generated
    caveat: str = ""
    #: Whether this state can be registered yet, and which units it contains.
    open_for_registration: bool = False
    agencies: list[dict[str, str]] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def entry(code: str) -> StateEntry:
    code = code.upper()
    agency, abbrev = AGENCIES.get(
        code, (f"{STATE_NAMES.get(code, code)} environmental agency", code))

    override = _override_palette(code)
    if override:
        source, colors = override
    elif code in SOURCED_PALETTES:
        source, colors = SOURCED_PALETTES[code]
    else:
        source, colors = "generated", placeholder_colors(code)

    # Where the colours came from decides how much they can be claimed to be —
    # never how many of them there are. A published guide is authoritative.
    # Colours harvested from the live site are what the agency demonstrably uses,
    # but nobody has ratified them. A partial published source (Pantone chips, an
    # inherited statewide standard) is documented but not the whole identity. A
    # hash is nothing at all, and says so.
    n = len(colors)
    plural = "color" if n == 1 else "colors"
    if source == "generated":
        provenance = "generated"
        caveat = (f"Placeholder slate — not {abbrev}'s brand, and not an attempt "
                  f"at it. {abbrev} publishes no colors we could find and its "
                  f"site could not be read, so the interface stays neutral "
                  f"rather than inventing an identity for it.")
    elif "scraped" in source:
        provenance = "scraped"
        caveat = (f"All {n} {plural} were taken from {abbrev}'s own website "
                  f"({source}) — nothing here was invented to pad them out. "
                  f"These are the colors {abbrev} uses in public, not a brand "
                  f"guide it has ratified; confirm before treating as official.")
    elif "brand guide" in source:
        provenance = "brand"
        caveat = ""
    else:
        provenance = "documented"
        caveat = (f"{n} {plural} from a published source ({source}). That is "
                  f"{abbrev}'s documented palette in full — it is a short one, "
                  f"and the interface uses those {n} rather than padding them "
                  f"out. Treat it as close to {abbrev}'s identity.")

    built = theme_for(colors)
    return StateEntry(
        code=code,
        state=STATE_NAMES.get(code, code),
        agency=agency,
        abbrev=abbrev,
        colors=list(colors),
        roles=built["roles"],                  # type: ignore[arg-type]
        theme=built["vars"],                   # type: ignore[arg-type]
        palette_source=source,
        name_verified=False,
        brand_count=n,
        is_brand=provenance == "brand",
        provenance=provenance,
        caveat=caveat,
        open_for_registration=is_open(code),
        agencies=agencies_for(code),
    )


def all_states() -> list[StateEntry]:
    codes = sorted({c for row in TILE_GRID for c in row if c})
    return [entry(c) for c in codes]


#: The flag's own specification, which is where the launcher's map already gets
#: these three. A documented palette rather than a scraped or invented one.
FEDERAL_COLORS = ["#0a3161", "#b31942", "#ffffff"]


@functools.lru_cache(maxsize=1)
def federal_entry() -> StateEntry:
    """The federal government, shaped like a state so nothing has to special-case it.

    The client asked for the map to carry "a line to a USA flag to the side
    which says Federal Login". Behind that link the picker, the theme, the
    sign-in card and the agency search all have to work exactly as they do for
    a state — so rather than a parallel path, federal is an entry with a code
    the rest of the application carries unchanged.

    It is not on the tile grid: there is no square for it, because it is not a
    state. The map draws it as a flag off the coast with a line back to the
    District, which is where it actually is.
    """
    built = theme_for(FEDERAL_COLORS)
    agencies = agencies_for(FEDERAL_CODE)
    return StateEntry(
        code=FEDERAL_CODE,
        state="Federal",
        agency="Federal agencies",
        abbrev="USA",
        colors=list(FEDERAL_COLORS),
        roles=built["roles"],                  # type: ignore[arg-type]
        theme=built["vars"],                   # type: ignore[arg-type]
        palette_source="the flag specification",
        name_verified=False,
        brand_count=len(FEDERAL_COLORS),
        is_brand=False,
        provenance="documented",
        caveat=("The flag's own three colors. Federal bodies each have their "
                "own identity; this is the jurisdiction, not any one agency's "
                "brand."),
        # 334 of the client's 472 entities operate and publish a domain. The
        # rest are defunct, superseded or historical and are not offered.
        open_for_registration=bool(agencies),
        agencies=agencies,
    )


@functools.lru_cache(maxsize=1)
def _entry_dicts() -> tuple[dict[str, Any], ...]:
    """Every state, themed, computed once.

    Building 51 themes means 51 rounds of contrast-walking to find foreground
    colors that clear AA on both surfaces. That took a second on a laptop and
    three on the instance — on *every* request — and the launcher cannot draw
    until it returns, so the browser sat on a bare shell for five seconds and
    looked broken.

    Nothing in the result varies at runtime: the palettes come from static brand
    data and the agency list from a committed file. The one field that does vary
    per request, `corpus_loaded`, is applied by the caller to a copy.
    """
    return tuple(e.as_dict() for e in all_states())


@functools.lru_cache(maxsize=1)
def _sourced() -> list[str]:
    """States whose palette came from the agency's own site, not a placeholder.

    Cached for the same reason as the themes: `_override_palette` reads and
    parses a brand file per state, 51 times, and the answer is the same on every
    request. Half a second of the three the launcher was waiting on was this
    list being rebuilt to produce an identical result.
    """
    return sorted(set(SOURCED_PALETTES) |
                  {c for c in STATE_NAMES if _override_palette(c)})


def invalidate_registry() -> None:
    """Drop the cached themes. For tests, and for a reset."""
    _entry_dicts.cache_clear()
    _sourced.cache_clear()
    _sc_agencies.cache_clear()


def grid() -> list[list[str]]:
    return [list(row) for row in TILE_GRID]


def registry(active_code: str | None = None,
             loaded_code: str | None = None) -> dict[str, Any]:
    loaded = (loaded_code or "").upper()
    # A copy per request, so the cached dicts are never mutated — a shared
    # object carrying one caller's `corpus_loaded` into the next response would
    # tell the next visitor that a corpus is loaded for a state that has none.
    entries = [{**e, "corpus_loaded": bool(loaded) and e["code"] == loaded}
               for e in _entry_dicts()]
    # Appended to the same list rather than carried in a field of its own, so
    # every lookup the launcher already does — selectState, enterAgency, the
    # agency search — finds it without knowing it is different.
    entries.append({**federal_entry().as_dict(),
                    "corpus_loaded": loaded == FEDERAL_CODE})
    return {
        "grid": grid(),
        "states": entries,
        "active": (active_code or "").upper() or None,
        "loaded": (loaded_code or "").upper() or None,
        "sourced": _sourced(),
        # Deliberately says nothing about where the colours came from or how many
        # there are. That belongs in the README and the API fields, not on screen
        # every time someone picks a state.
        "note": (
            "Agency names are seeded from public knowledge and are NOT "
            "verified — agencies rename themselves. Loading a state's corpus "
            "replaces the name with the one its own adopted documents state, "
            "along with its instruments, lifecycle and vocabulary."
        ),
    }
