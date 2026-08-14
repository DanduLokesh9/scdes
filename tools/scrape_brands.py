"""Scrape each state environmental agency's live site for its real brand colours.

Most state environmental agencies publish no brand guide and no hex values. But
every one of them runs a website, and that site's stylesheet *is* the agency's
operative visual identity — in practice more current than a PDF filed in 2014.

Method
    fetch the homepage → follow its stylesheets → collect every colour →
    weight by how the colour is used (header, nav, primary button, link) →
    drop greys, near-whites and near-blacks → map the survivors onto the eight
    palette slots the application themes with.

Provenance is recorded per state: the URL, the date, and how many slots were
actually filled from the site rather than generated. A colour taken from a live
site is evidence, not a brand guide, and the app says so.

Run:  python tools/scrape_brands.py            # all states
      python tools/scrape_brands.py SC TX OH   # just these
"""

from __future__ import annotations

import colorsys
import gzip
import io
import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

OUT = Path(__file__).resolve().parent.parent / "corpus" / "config" / "brand.yaml"
RAW = Path(__file__).resolve().parent / "brand_scrape.json"

TIMEOUT = 20
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

#: Homepages of the primary state environmental agency in each state.
SITES: dict[str, str] = {
    "AL": "https://adem.alabama.gov/",
    "AK": "https://dec.alaska.gov/",
    "AZ": "https://azdeq.gov/",
    "AR": "https://www.adeq.state.ar.us/",
    "CA": "https://calepa.ca.gov/",
    "CO": "https://cdphe.colorado.gov/",
    "CT": "https://portal.ct.gov/deep",
    "DE": "https://dnrec.delaware.gov/",
    "DC": "https://doee.dc.gov/",
    "FL": "https://floridadep.gov/",
    "GA": "https://epd.georgia.gov/",
    "HI": "https://health.hawaii.gov/epo/",
    "ID": "https://www.deq.idaho.gov/",
    "IL": "https://epa.illinois.gov/",
    "IN": "https://www.in.gov/idem/",
    "IA": "https://www.iowadnr.gov/",
    "KS": "https://www.kdhe.ks.gov/",
    "KY": "https://eec.ky.gov/",
    "LA": "https://deq.louisiana.gov/",
    "ME": "https://www.maine.gov/dep/",
    "MD": "https://mde.maryland.gov/",
    "MA": "https://www.mass.gov/orgs/massachusetts-department-of-environmental-protection",
    "MI": "https://www.michigan.gov/egle",
    "MN": "https://www.pca.state.mn.us/",
    "MS": "https://www.mdeq.ms.gov/",
    "MO": "https://dnr.mo.gov/",
    "MT": "https://deq.mt.gov/",
    "NE": "https://dee.nebraska.gov/",
    "NV": "https://ndep.nv.gov/",
    "NH": "https://www.des.nh.gov/",
    "NJ": "https://dep.nj.gov/",
    "NM": "https://www.env.nm.gov/",
    "NY": "https://dec.ny.gov/",
    "NC": "https://www.deq.nc.gov/",
    "ND": "https://deq.nd.gov/",
    "OH": "https://epa.ohio.gov/",
    "OK": "https://www.deq.ok.gov/",
    "OR": "https://www.oregon.gov/deq/",
    "PA": "https://www.pa.gov/agencies/dep.html",
    "RI": "https://dem.ri.gov/",
    "SC": "https://des.sc.gov/",
    "SD": "https://danr.sd.gov/",
    "TN": "https://www.tn.gov/environment.html",
    "TX": "https://www.tceq.texas.gov/",
    "UT": "https://deq.utah.gov/",
    "VT": "https://dec.vermont.gov/",
    "VA": "https://www.deq.virginia.gov/",
    "WA": "https://ecology.wa.gov/",
    "WV": "https://dep.wv.gov/",
    "WI": "https://dnr.wisconsin.gov/",
    "WY": "https://deq.wyoming.gov/",
}

# --------------------------------------------------------------- fetching

#: A bare urllib request is refused by several state portals (Akamai and
#: Cloudflare both fingerprint header sets). Sending what a browser sends gets
#: through; nothing here defeats a rate limit or an authentication wall.
BROWSER_HEADERS = {
    "User-Agent": UA,
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "text/css,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

#: Some state sites serve an incomplete certificate chain. We are reading
#: public stylesheets for colour values, so falling back to an unverified
#: context is acceptable — but it is recorded per state rather than hidden.
_UNVERIFIED = ssl.create_default_context()
_UNVERIFIED.check_hostname = False
_UNVERIFIED.verify_mode = ssl.CERT_NONE


def fetch(url: str, limit: int = 900_000) -> tuple[str, bool]:
    """Return (text, tls_verified). Retries unverified only on a TLS failure."""
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)

    def read(context=None) -> str:
        with urllib.request.urlopen(req, timeout=TIMEOUT, context=context) as resp:
            raw = resp.read(limit)
            if resp.headers.get("Content-Encoding") == "gzip":
                try:
                    raw = gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
                except OSError:
                    pass
        return raw.decode("utf-8", errors="replace")

    try:
        return read(), True
    except urllib.error.URLError as exc:
        if isinstance(getattr(exc, "reason", None), ssl.SSLError) or \
                "CERTIFICATE" in str(exc).upper():
            return read(_UNVERIFIED), False
        raise


_LINK = re.compile(r"""<link[^>]+rel=["']?stylesheet["']?[^>]*>""", re.I)
_HREF = re.compile(r"""href=["']([^"']+)["']""", re.I)


def stylesheets(html: str, base: str, cap: int = 4) -> list[str]:
    urls = []
    for tag in _LINK.findall(html):
        m = _HREF.search(tag)
        if not m:
            continue
        href = m.group(1)
        if href.startswith("data:"):
            continue
        urls.append(urljoin(base, href))
    # Prefer stylesheets whose name suggests the site's own theme over vendor
    # bundles, which are usually framework defaults rather than brand.
    def rank(u: str) -> int:
        name = urlparse(u).path.lower()
        if any(k in name for k in ("theme", "brand", "main", "site", "custom")):
            return 0
        if any(k in name for k in ("bootstrap", "vendor", "font", "icon", "normalize")):
            return 2
        return 1
    urls.sort(key=rank)
    return urls[:cap]


# --------------------------------------------------------------- colours

_HEX = re.compile(r"#([0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
_RGB = re.compile(r"rgba?\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})")

#: Selectors and properties whose colours are almost always brand.
_STRONG = re.compile(
    r"(header|banner|masthead|navbar|nav\b|primary|brand|hero|footer|"
    r"btn-primary|button|--.*primary|topbar|site-title)", re.I)


def _norm(h: str) -> str:
    h = h.lower()
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return "#" + h


def _hsl(hex_colour: str) -> tuple[float, float, float]:
    r = int(hex_colour[1:3], 16) / 255
    g = int(hex_colour[3:5], 16) / 255
    b = int(hex_colour[5:7], 16) / 255
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, l


#: CSS framework default palettes. A site built on Bootstrap ships these
#: whether or not anyone chose them, so harvesting them yields Bootstrap's
#: brand rather than the agency's — and the result looks sourced, which makes
#: it more misleading than an obvious placeholder.
FRAMEWORK_DEFAULTS = {
    # Bootstrap 3
    "#337ab7", "#2e6da4", "#5cb85c", "#4cae4c", "#d9534f", "#d43f3a",
    "#f0ad4e", "#eea236", "#5bc0de", "#46b8da", "#286090", "#449d44",
    "#c9302c", "#ec971f", "#31b0d5", "#204d74", "#398439", "#ac2925",
    # Bootstrap 4
    "#007bff", "#6c757d", "#28a745", "#dc3545", "#ffc107", "#17a2b8",
    "#343a40", "#0069d9", "#218838", "#c82333", "#e0a800", "#138496",
    # Bootstrap 5
    "#0d6efd", "#198754", "#0dcaf0", "#6610f2", "#6f42c1", "#d63384",
    "#fd7e14", "#20c997", "#0b5ed7", "#157347", "#bb2d3b",
    # Materialize
    "#26a69a", "#ee6e73", "#f44336", "#2196f3", "#4caf50", "#ffeb3b",
    # Tailwind common
    "#2563eb", "#4f46e5", "#3b82f6", "#1d4ed8", "#ef4444", "#10b981",
    # Bootstrap 3 alert / panel tints — these show up as "brand" constantly
    "#a94442", "#d6e9c6", "#d0e9c6", "#ebccd1", "#ebcccc", "#c4e3f3",
    "#f8efc0", "#3c763d", "#31708f", "#8a6d3b", "#f2dede", "#dff0d8",
    "#d9edf7", "#fcf8e3", "#faebcc", "#bce8f1", "#c9e2b3",
    # Bootstrap 5 subtle/emphasis tints
    "#6ea8fe", "#9ec5fe", "#cfe2ff", "#d1e7dd", "#75b798", "#a3cfbb",
    "#ea868f", "#f1aeb5", "#664d03", "#997404", "#b02a37", "#856404",
    "#e2e3e5", "#f8d7da", "#fff3cd", "#cff4fc", "#adb5bd", "#495057",
    # WordPress / Gutenberg core palette — the single biggest source of false
    # "brand" colours on state agency sites, and identical on all of them.
    "#cf2e2e", "#ff6900", "#fcb900", "#7bdcb5", "#00d084", "#8ed1fc",
    "#0693e3", "#abb8c3", "#9b51e0", "#f78da7", "#7a00df", "#4721fb",
    "#cf2aba", "#ee2c82", "#dad0ec", "#fdd79a", "#faaca8", "#d3e6e4",
    "#313131", "#eeeeee",
    # Foundation / misc
    "#2199e8", "#00449e", "#008cba",
}


def interesting(hex_colour: str) -> bool:
    """Brand colours are saturated, mid-toned, and not a framework default."""
    if hex_colour in FRAMEWORK_DEFAULTS:
        return False
    _, s, l = _hsl(hex_colour)
    return 0.12 <= l <= 0.88 and s >= 0.16


def harvest(css: str) -> dict[str, float]:
    """Score every colour in a stylesheet by how brand-ish its context is."""
    scores: dict[str, float] = {}
    for block in re.split(r"[}\n]", css):
        weight = 3.0 if _STRONG.search(block) else 1.0
        found = [_norm(m) for m in _HEX.findall(block)]
        for r, g, b in _RGB.findall(block):
            try:
                found.append("#%02x%02x%02x" % (int(r), int(g), int(b)))
            except ValueError:
                pass
        for colour in found:
            if interesting(colour):
                scores[colour] = scores.get(colour, 0.0) + weight
    return scores


def distinct(ranked: list[str], minimum_gap: float = 0.055) -> list[str]:
    """Collapse near-duplicate shades so a palette is not five blues."""
    out: list[str] = []
    for colour in ranked:
        h, s, l = _hsl(colour)
        clash = False
        for other in out:
            oh, os_, ol = _hsl(other)
            dh = min(abs(h - oh), 1 - abs(h - oh))
            if dh < minimum_gap and abs(l - ol) < 0.14:
                clash = True
                break
        if not clash:
            out.append(colour)
    return out


#: A brand is however many colours the agency actually uses. Padding a set of
#: four up to a fixed eight with rotated and shaded variants was a mistake: the
#: derived filler follows the same recipe for every agency, so it dominates the
#: impression and every state drifts toward looking like every other one. The
#: agency's real four are what make it recognisable. Emit exactly those.
#:
#: Roles are assigned downstream by *reusing* these colours (app/theme.py), and
#: status colours — Low / Moderate / High risk — are universal rather than
#: per-agency, so nothing here ever has to invent a green.


def to_brand(ranked: list[str]) -> list[str]:
    """The agency's colours, most prominent first. No padding, no synthesis."""
    return distinct(ranked)



# ------------------------------------------------------------------ driver

def scrape(code: str, url: str) -> dict:
    result = {"code": code, "url": url, "ok": False, "error": "",
              "colours": [], "tls_verified": True,
              "stylesheets": 0, "scraped": date.today().isoformat()}
    try:
        html, verified = fetch(url)
        result["tls_verified"] = verified
    except Exception as exc:                                   # noqa: BLE001
        result["error"] = f"{type(exc).__name__}: {exc}"[:120]
        return result

    scores = harvest(html)
    for sheet in stylesheets(html, url):
        try:
            css, _ = fetch(sheet)
        except Exception:                                      # noqa: BLE001
            continue
        result["stylesheets"] += 1
        for colour, weight in harvest(css).items():
            scores[colour] = scores.get(colour, 0.0) + weight

    ranked = [c for c, _ in sorted(scores.items(), key=lambda kv: -kv[1])][:40]
    brand = to_brand(ranked)

    # Too few distinct survivors means the site's colour is carried by imagery
    # or a framework we filtered out. Better to report nothing than to dress a
    # thin result up as a brand.
    if len(brand) < 2:
        result["error"] = (f"only {len(brand)} distinct non-framework "
                           f"colour(s) found — not enough to theme with")
        return result

    result.update(ok=True, colours=brand)
    return result


#: An agency's brand colour is its own. If the same hex turns up on this many
#: *different* state agencies' sites, it is not anyone's brand — it is a CMS or
#: framework default that nobody chose. Enumerating those by hand does not scale
#: (Bootstrap tints, the WordPress Gutenberg palette, USWDS tokens, whatever
#: ships next), so the corpus of scraped sites is used as its own evidence.
#:
#: This matters for exactly the reason the whole exercise does: shared defaults
#: are what make every state look like every other state.
#:
#: Three is where the observed distribution breaks: across 32 scraped sites, 335
#: colours belonged to exactly one agency and only a dozen appeared on three or
#: more, all of them traceable to Bootstrap, Gutenberg or USWDS. Two is left
#: alone — genuine government navies and forest greens do coincide.
SHARED_COLOUR_LIMIT = 3


def drop_shared(results: list[dict]) -> dict[str, int]:
    """Remove colours common to several agencies. Returns what was dropped.

    Mutates each result's `colours` in place, and marks an agency failed if too
    little of its own is left — better to show a neutral placeholder and say so
    than to theme a state in someone else's framework defaults.
    """
    scraped = [r for r in results if r["ok"]]
    everywhere: dict[str, int] = {}
    for r in scraped:
        for colour in set(r["colours"]):
            everywhere[colour] = everywhere.get(colour, 0) + 1

    shared = {c: n for c, n in everywhere.items() if n >= SHARED_COLOUR_LIMIT}
    for r in scraped:
        r["shared_dropped"] = [c for c in r["colours"] if c in shared]
        r["colours"] = [c for c in r["colours"] if c not in shared]
        if len(r["colours"]) < 2:
            r["ok"] = False
            r["error"] = ("nothing left after removing colours shared with other "
                          "agencies — the site is framework defaults throughout")
    return shared


def main(argv: list[str]) -> int:
    codes = [a.upper() for a in argv if a.upper() in SITES] or list(SITES)
    print(f"scraping {len(codes)} agency sites…\n")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda c: scrape(c, SITES[c]), codes))

    # Only meaningful across a full run; a handful of codes gives no evidence.
    shared: dict[str, int] = {}
    if len(codes) >= 12:
        shared = drop_shared(results)

    ok = [r for r in results if r["ok"]]
    for r in sorted(results, key=lambda r: r["code"]):
        if r["ok"]:
            shown = " ".join(r["colours"][:6])
            more = f" +{len(r['colours']) - 6}" if len(r["colours"]) > 6 else ""
            print(f"  {r['code']}  {len(r['colours']):>2} colours  "
                  f"{r['stylesheets']} css  {shown}{more}")
        else:
            print(f"  {r['code']}  FAILED  {r['error'][:70]}")

    RAW.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n{len(ok)}/{len(results)} scraped · raw saved to {RAW.name}")
    if ok:
        counts = [len(r["colours"]) for r in ok]
        print(f"colours per agency: min {min(counts)}, max {max(counts)}, "
              f"mean {sum(counts) / len(counts):.1f}")
    if shared:
        top = sorted(shared.items(), key=lambda kv: -kv[1])
        print(f"\ndropped {len(shared)} colours shared by "
              f"{SHARED_COLOUR_LIMIT}+ agencies — framework/CMS defaults, "
              f"not anybody's brand:")
        for colour, n in top[:14]:
            print(f"  {colour}  on {n} sites")
        if len(top) > 14:
            print(f"  … and {len(top) - 14} more")

    lines = [
        "# Brand colours scraped from each agency's live website.",
        "# Generated by tools/scrape_brands.py — re-run to refresh.",
        "#",
        "# Each entry lists exactly the colours that agency uses, most prominent",
        "# first. Nothing is padded to a fixed length and nothing is synthesised:",
        "# an agency with four colours gets four. Interface roles are filled by",
        "# reusing these (see app/theme.py), and status colours are universal, so",
        "# no colour here was invented to fill a gap.",
        "#",
        "# This is evidence of visual identity, not a ratified brand guide. An",
        "# agency can replace any entry with its own official values.",
        "palettes:",
    ]
    for r in sorted(ok, key=lambda r: r["code"]):
        lines.append(f"  {r['code']}:")
        lines.append(f"    source: scraped from {r['url']} on {r['scraped']}")
        lines.append(f"    colors: [{', '.join(f'\"{c}\"' for c in r['colours'])}]")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
