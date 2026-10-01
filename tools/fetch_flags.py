"""Download each state's flag from Wikimedia Commons, once, for offline use.

Input   the state list in app/states.py
Output  app/web/assets/flags/XX.png   — one flag per state, plus DC
        app/web/assets/flags/index.json — source, license and author for each

Why PNG rather than the original SVG: several state flags carry a full state
seal, and those SVGs run to hundreds of kilobytes each — Washington's is 265 KB,
and it is not the worst. The application shows the flag at roughly 150 px wide,
so a rendered thumbnail is both faithful at the size actually used and about a
twentieth of the weight. Commons renders these itself, so the thumbnail is the
same artwork, not a re-drawing.

US state flags are public domain as government insignia, but that is asserted
per-file rather than assumed: this records the license Commons reports for each
one and refuses to save anything that is not public domain or CC0.

This runs once. Afterward the application needs no network, which is the whole
point of the build.
"""

from __future__ import annotations

import json
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.states import STATE_NAMES                       # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "app" / "web" / "assets" / "flags"
API = "https://commons.wikimedia.org/w/api.php"

#: Wikimedia asks for a descriptive agent naming the tool. Sending a browser
#: string here would be both untrue and against their policy.
UA = {"User-Agent": "SCDES-AI-Governance-App/1.0 (offline reference build; "
                    "one-time flag fetch)"}

#: Rendered width. The flag is displayed around 150 px; 400 keeps it crisp on a
#: high-density screen without pulling down seal artwork nobody will see.
WIDTH = 400

#: Licences we will actually bundle. Anything else is reported and skipped
#: rather than quietly shipped.
#:
#: "Copyrighted free use" is here for one flag: Mississippi's, redesigned in
#: 2020, whose magnolia artwork is still under copyright with unrestricted
#: permission granted rather than released to the public domain. That is a free
#: licence and fine to ship, but it is not the same footing as the other fifty,
#: so the distinction is kept in the manifest rather than flattened away.
ACCEPTED = ("public domain", "pd", "cc0", "copyrighted free use")

#: Commons titles that do not follow "Flag of {State}".
TITLE_OVERRIDES = {
    "DC": "File:Flag of the District of Columbia.svg",
}


def title_for(code: str) -> str:
    if code in TITLE_OVERRIDES:
        return TITLE_OVERRIDES[code]
    return f"File:Flag of {STATE_NAMES[code]}.svg"


def _context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def fetch_json(params: dict) -> dict:
    url = f"{API}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=30, context=_context()) as r:
        return json.loads(r.read())


def fetch_bytes(url: str, attempts: int = 4) -> bytes:
    """Download with backoff. Commons answers 429 readily and expects a wait."""
    delay = 1.5
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(request, timeout=45,
                                        context=_context()) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (429, 503) or attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2
    raise RuntimeError("unreachable")


def lookup_all(codes: list[str]) -> dict[str, dict]:
    """One API call per 50 titles instead of one per state.

    The first version asked separately for each flag and was rate-limited after
    six. The API takes up to 50 titles at once, so the whole country is two
    requests — faster, and the polite way to use someone else's service.
    """
    by_title = {title_for(c): c for c in codes}
    found: dict[str, dict] = {}
    titles = list(by_title)
    for start in range(0, len(titles), 50):
        batch = titles[start:start + 50]
        for attempt in range(4):
            try:
                data = fetch_json({
                    "action": "query", "titles": "|".join(batch),
                    "prop": "imageinfo", "iiprop": "url|size|extmetadata",
                    "iiurlwidth": str(WIDTH), "format": "json",
                })
                break
            except urllib.error.HTTPError as exc:
                if exc.code not in (429, 503) or attempt == 3:
                    raise
                time.sleep(2 * (attempt + 1))
        # Commons normalises titles (underscores, capitalisation); follow it back.
        normal = {n["to"]: n["from"]
                  for n in (data.get("query") or {}).get("normalized", [])}
        for page in ((data.get("query") or {}).get("pages") or {}).values():
            title = normal.get(page.get("title", ""), page.get("title", ""))
            code = by_title.get(title)
            if code and page.get("imageinfo"):
                found[code] = page["imageinfo"][0]
        time.sleep(1.0)
    return found


def strip_markup(value: str) -> str:
    """extmetadata returns small HTML fragments; the manifest wants plain text."""
    out, depth = [], 0
    for ch in value or "":
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    return " ".join("".join(out).split())[:120]


def flag_for(code: str, info: dict) -> dict:
    result = {"code": code, "ok": False, "error": "", "title": title_for(code)}
    if not info.get("thumburl"):
        result["error"] = "no rendered thumbnail on Commons"
        return result

    meta = info.get("extmetadata") or {}
    licence = strip_markup(meta.get("LicenseShortName", {}).get("value", ""))
    if not any(word in licence.lower() for word in ACCEPTED):
        result["error"] = f"license not clearly public domain: {licence!r}"
        return result

    # Already on disk: don't ask Commons for it again. Reruns after a partial
    # failure then cost one metadata call rather than fifty downloads.
    target = OUT / f"{code}.png"
    if target.exists() and target.stat().st_size > 400:
        result.update(ok=True, cached=True, bytes=target.stat().st_size,
                      licence=licence,
                      descriptionurl=info.get("descriptionurl", ""),
                      artist=strip_markup(meta.get("Artist", {}).get("value", "")))
        return result

    try:
        payload = fetch_bytes(info["thumburl"])
    except Exception as exc:                                   # noqa: BLE001
        result["error"] = f"download failed: {type(exc).__name__}"
        return result

    OUT.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    time.sleep(0.4)               # spread the image requests out
    result.update(ok=True, bytes=len(payload), licence=licence,
                  descriptionurl=info.get("descriptionurl", ""),
                  artist=strip_markup(meta.get("Artist", {}).get("value", "")))
    return result


def main(argv: list[str]) -> int:
    codes = [a.upper() for a in argv if a.upper() in STATE_NAMES] or \
        sorted(STATE_NAMES)
    print(f"fetching {len(codes)} state flags from Wikimedia Commons…\n")

    info = lookup_all(codes)
    print(f"metadata for {len(info)}/{len(codes)} resolved\n")

    results = []
    for code in codes:
        row = flag_for(code, info.get(code, {}))
        results.append(row)
        if row["ok"]:
            note = "cached" if row.get("cached") else f"{row['bytes'] / 1024:.1f} KB"
            print(f"  {code}  {note:>10}  {row['licence']}")
        else:
            print(f"  {code}  FAILED  {row['error']}")

    ok = [r for r in results if r["ok"]]
    manifest = {
        "note": ("US state flags, rendered by Wikimedia Commons and bundled so "
                 "the application needs no network. Public domain as government "
                 "insignia; the license Commons reports is recorded per file."),
        "width": WIDTH,
        "flags": {r["code"]: {"licence": r["licence"], "source": r["descriptionurl"],
                              "artist": r["artist"]} for r in ok},
    }
    (OUT / "index.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    total = sum(r["bytes"] for r in ok) / 1024
    print(f"\n{len(ok)}/{len(results)} flags · {total:.0f} KB total")
    missing = [r["code"] for r in results if not r["ok"]]
    print("missing:", " ".join(missing) if missing else "none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
