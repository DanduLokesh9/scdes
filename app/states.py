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

An agency's brand is however many colours it actually has — two, three, eight —
and that list is never padded. app/theme.py fills interface roles by reusing
them, so a two-colour agency is themed in exactly its two colours.

When a state's corpus is actually loaded, `profile.discover()` reads the real
name out of the adopted documents and overrides the seed. The seed exists so the
map is not blank on day one.
"""

from __future__ import annotations

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
#: A state opens when its agencies and their email conventions have actually been
#: confirmed. Guessing them would refuse real staff at the door.
LAUNCH_STATES: set[str] = {"SC"}

#: The governmental units inside a launched state. A state is not one agency:
#: environmental services, education and the rest each run their own governance,
#: each with their own email convention.
#:
#: Only what has been confirmed appears here. This list is what the "select your
#: agency" dropdown offers, so an omission is better than an invention.
STATE_AGENCIES: dict[str, list[dict[str, str]]] = {
    "SC": [
        {"id": "sc.des", "name": "South Carolina Department of Environmental Services",
         "abbrev": "SCDES", "domain": "des.sc.gov", "convention": "first.last"},
        {"id": "sc.ed", "name": "South Carolina Department of Education",
         "abbrev": "SCDE", "domain": "ed.sc.gov", "convention": "flast"},
        # For IIA's own testing. Named as such so it is never mistaken for a
        # real governmental unit in a screenshot or a demo.
        {"id": "iia.test", "name": "TEST agency — Innovative Infrastructure Advising",
         "abbrev": "TEST", "domain": "iiac.ai", "convention": "first.last",
         "test_only": "yes"},
    ],
}


def agencies_for(code: str) -> list[dict[str, str]]:
    return STATE_AGENCIES.get((code or "").upper(), [])


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
    "NM": ("New Mexico Environment Department", "NMED"),
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
    """A stable neutral pair for an agency whose colours we do not have.

    Deliberately *not* a full invented palette. When there is no evidence, the
    honest rendering is a plain slate interface that visibly isn't anybody's
    brand — a hash-generated eight-colour scheme merely looks confident about
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
    plural = "colour" if n == 1 else "colours"
    if source == "generated":
        provenance = "generated"
        caveat = (f"Placeholder slate — not {abbrev}'s brand, and not an attempt "
                  f"at it. {abbrev} publishes no colours we could find and its "
                  f"site could not be read, so the interface stays neutral "
                  f"rather than inventing an identity for it.")
    elif "scraped" in source:
        provenance = "scraped"
        caveat = (f"All {n} {plural} were taken from {abbrev}'s own website "
                  f"({source}) — nothing here was invented to pad them out. "
                  f"These are the colours {abbrev} uses in public, not a brand "
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


def grid() -> list[list[str]]:
    return [list(row) for row in TILE_GRID]


def registry(active_code: str | None = None,
             loaded_code: str | None = None) -> dict[str, Any]:
    entries = []
    for e in all_states():
        e.corpus_loaded = (loaded_code is not None
                           and e.code == loaded_code.upper())
        entries.append(e.as_dict())
    return {
        "grid": grid(),
        "states": entries,
        "active": (active_code or "").upper() or None,
        "loaded": (loaded_code or "").upper() or None,
        "sourced": sorted(set(SOURCED_PALETTES) |
                          {c for c in STATE_NAMES if _override_palette(c)}),
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
