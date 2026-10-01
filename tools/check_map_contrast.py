"""Is the parchment map still legible, in both modes?

The map was restyled from a flat slate to a printed-parchment look, which
changed the ground under every piece of text on the launcher: the heading, the
hint line, the ocean names and the Federal Login label. A warmer palette is
easy to get wrong in exactly one way — everything drifts toward the same middle
tone and the whole thing goes soft.

This repo holds text to WCAG AA (4.5:1, or 3:1 for large text and for the
boundary of a control), so this measures the pairs the restyle actually moved,
against the worst ground each one can land on.

Usage:  python -m tools.check_map_contrast
"""

from __future__ import annotations

import re
from pathlib import Path

CSS = Path(__file__).resolve().parent.parent / "app" / "web" / "assets" / "launcher.css"

AA_TEXT = 4.5
AA_LARGE = 3.0

#: How far apart two state fills must be. **Not a WCAG number** — there isn't
#: one for adjacent decorative areas, and the requirement that does apply
#: (1.4.11, the boundary of a control at 3:1) is carried by the per-tint stroke
#: above, which is asserted separately.
#:
#: This is a self-imposed floor for a different problem: two states with nearly
#: identical fills read as one shape however good the line between them is. An
#: earlier hand-picked palette had a pair at 1.03:1, which is the same colour.
#: 1.10 is deliberately modest because the range available in dark mode is
#: compressed — seven steps between a near-black ground and something still
#: recognisably dark cannot be spread as widely as seven on paper.
SEPARATION = 1.10


def lin(c: float) -> float:
    c = c / 255.0
    return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4


def luminance(rgb: tuple[float, float, float]) -> float:
    return 0.2126 * lin(rgb[0]) + 0.7152 * lin(rgb[1]) + 0.0722 * lin(rgb[2])


def ratio(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def rgb(value: str) -> tuple[float, float, float]:
    value = value.strip()
    if value.startswith("#"):
        h = value[1:]
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    m = re.match(r"rgba?\(([^)]+)\)", value)
    parts = [p.strip() for p in m.group(1).split(",")]
    return tuple(float(p) for p in parts[:3])


def over(fg: str, bg: tuple[float, float, float]) -> tuple[float, float, float]:
    """Flatten an rgba foreground onto its background."""
    m = re.match(r"rgba\(([^)]+)\)", fg.strip())
    if not m:
        return rgb(fg)
    parts = [float(p) for p in m.group(1).split(",")]
    a = parts[3] if len(parts) > 3 else 1.0
    return tuple(a * parts[i] + (1 - a) * bg[i] for i in range(3))


def token(block: str, name: str) -> str:
    """One custom property out of a CSS block."""
    src = CSS.read_text(encoding="utf-8")
    start = src.index(block)
    chunk = src[start:src.index("}", start)]
    m = re.search(rf"{re.escape(name)}:\s*([^;]+);", chunk)
    if not m:
        raise SystemExit(f"{name} is not in {block!r} any more")
    return m.group(1).strip()


def rule(selector: str, prop: str, night: bool = False) -> str:
    """One declaration. `night` also looks inside grouped dark-mode selectors,
    where the tint appears alongside its siblings rather than on its own."""
    src = CSS.read_text(encoding="utf-8")
    m = re.search(rf"{re.escape(selector)}\s*\{{[^}}]*?{re.escape(prop)}:\s*([^;]+);",
                  src, re.S)
    if m:
        return m.group(1).strip()
    if night:
        for block in re.finditer(r"([^{}]*)\{([^}]*)\}", src):
            sel, body = block.group(1), block.group(2)
            if selector in sel and f"{prop}:" in body:
                return re.search(rf"{re.escape(prop)}:\s*([^;]+);",
                                 body).group(1).strip()
    raise SystemExit(f"{selector} {{ {prop} }} is not there any more")


def stroke_for(tint: int, night: bool = False) -> str:
    """The stroke that actually applies to `tint`, in the mode asked for.

    Both palettes group tints that share a border color, so this finds the
    grouped selector the tint appears in rather than assuming one rule each —
    otherwise the check would fall back to a default that no longer exists and
    pass against nothing.
    """
    src = CSS.read_text(encoding="utf-8")
    for m in re.finditer(r"([^{}]*\.tint-\d[^{}]*)\{([^}]*)\}", src):
        selector, body = m.group(1), m.group(2)
        if f".tint-{tint} " not in selector + " " \
                and f".tint-{tint}," not in selector \
                and not selector.rstrip().endswith(f".tint-{tint}"):
            continue
        if "stroke:" not in body:
            continue
        if ("data-theme" in selector) != night:
            continue
        return re.search(r"stroke:\s*([^;]+);", body).group(1).strip()
    raise SystemExit(f"no {'night' if night else 'day'} stroke covers tint-{tint}")


def main() -> int:
    failures: list[str] = []

    def check(label: str, got: float, need: float) -> None:
        ok = got >= need
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<46} "
              f"{got:5.2f}:1  (needs {need})")
        if not ok:
            failures.append(f"{label} at {got:.2f}:1")

    print("light — text on parchment")
    # The darkest stop of the light gradient is the worst ground for text.
    paper = rgb("#e2d7c0")
    light = ':root[data-theme="light"] .launcher {'
    check("heading", ratio(rgb(token(light, "--lnch-ink-strong")), paper), AA_TEXT)
    check("body text", ratio(rgb(token(light, "--lnch-ink")), paper), AA_TEXT)
    check("the hint line under the heading",
          ratio(rgb(token(light, "--lnch-ink-muted")), paper), AA_TEXT)
    check("the faintest text", ratio(rgb(token(light, "--lnch-ink-faint")), paper),
          AA_TEXT)

    print("\nlight — the map's own ink")
    base = rgb(rule(".mapbase", "fill"))
    sea = rule(".sea", "fill")
    check("ocean names on parchment", ratio(over(sea, base), base), AA_LARGE)
    check("the country outline",
          ratio(over(rule(".usmap .outline path", "stroke"), base), base), AA_LARGE)

    # Every tint against its own stroke, not just the palest one.
    #
    # This checked a single stroke against a single fill, which was fine while
    # every state shared one border colour. The palette was then re-sampled from
    # the client's reference and turned out to span #ded2ba to #7e7e72 — far
    # wider — at which point one dark line cleared 3:1 on the sands and vanished
    # into the darkest fill. Each state is a button, so each boundary has to
    # hold on its own ground.
    for i in range(7):
        fill = rgb(rule(f".usmap .st.tint-{i}", "fill"))
        check(f"tint-{i} outline on its own fill",
              ratio(over(stroke_for(i), fill), fill), AA_LARGE)

    print("\nlight — neighboring states are told apart")
    fills = [rgb(rule(f".usmap .st.tint-{i}", "fill")) for i in range(7)]
    worst = min(ratio(a, b) for i, a in enumerate(fills)
                for b in fills[i + 1:])
    check("the two closest tints still differ", worst, SEPARATION)

    print("\ndark — text on the warmed ground")
    night = rgb("#201a12")
    dark = ".launcher {"
    check("heading", ratio(rgb(token(dark, "--lnch-ink-strong")), night), AA_TEXT)
    check("body text", ratio(rgb(token(dark, "--lnch-ink")), night), AA_TEXT)
    check("the hint line under the heading",
          ratio(rgb(token(dark, "--lnch-ink-muted")), night), AA_TEXT)
    check("the faintest text", ratio(rgb(token(dark, "--lnch-ink-faint")), night),
          AA_TEXT)

    print("\ndark — the map's own ink")
    dark_base = rgb(rule(':root[data-theme="dark"] .mapbase', "fill"))
    dark_sea = rule(':root[data-theme="dark"] .sea', "fill")
    check("ocean names", ratio(over(dark_sea, dark_base), dark_base), AA_LARGE)
    dark_fills = [rgb(rule(f':root[data-theme="dark"] .usmap .st.tint-{i}',
                           "fill")) for i in range(7)]
    for i, fill in enumerate(dark_fills):
        check(f"tint-{i} outline on its own fill",
              ratio(over(stroke_for(i, night=True), fill), fill), AA_LARGE)
    worst_dark = min(ratio(a, b) for i, a in enumerate(dark_fills)
                     for b in dark_fills[i + 1:])
    check("the two closest night tints differ", worst_dark, SEPARATION)

    print("\nthe selected agency must still be the loudest thing")
    # A saturated agency colour against the tints it will sit among. SCDES green
    # is the one in the corpus; the palest and darkest tints bracket the range.
    agency = rgb("#1c7a43")
    for name, tint in (("palest tint", ".usmap .st.tint-2"),
                       ("darkest tint", ".usmap .st.tint-6")):
        got = ratio(agency, rgb(rule(tint, "fill")))
        print(f"        against the {name:<14} {got:5.2f}:1")

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — the parchment map clears AA in both modes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
