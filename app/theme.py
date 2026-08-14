"""Build an interface theme from however many colours an agency actually has.

The earlier design mapped every agency onto a fixed eight-slot palette and
synthesised whatever was missing. That was wrong in a way worth recording,
because it is a tempting mistake: the synthesised colours were produced by the
same recipe for every agency, so a state with four real colours ended up
four-parts itself and four-parts house style. The filler dominated the
impression and the states converged toward looking alike — the opposite of the
point of theming per agency.

So: no padding and no synthesis. Whatever the agency uses, N colours, is the
brand. Interface roles are filled by *reusing* those N. When N is small a colour
serves several roles, which is what small brands do in practice and reads as
deliberate rather than diluted.

Two things are deliberately *not* taken from the brand:

  Status colours are universal. Low / Moderate / High risk are the same in all
  fifty states. This is better than theming them — a governance record where
  "High risk" is maroon in one state and olive in another invites misreading —
  and it removes the only reason the old code had to invent a green.

  Foreground colours are chosen, not invented. Text over a brand colour is
  black or white, whichever is readable. The brand colour is never altered to
  make text fit; the text adapts to the brand.

The single exception is `accent_text`: a brand colour used as small text on
white must clear WCAG AA 4.5:1, so it is darkened along its own hue until it
does. That is the agency's colour at a readable lightness, not a new colour, and
`theme_for()` reports whether the adjustment was needed.
"""

from __future__ import annotations

import colorsys

#: Universal status colours — identical for every agency, by design.
#: Low and High are the WCAG-AA-on-white pair used throughout; Moderate is
#: darkened from amber for the same reason.
STATUS: dict[str, str] = {
    "ok": "#1c7a43",
    "warn": "#8a6510",
    "alert": "#b3261e",
    "risk_low": "#1c7a43",
    "risk_moderate": "#8a6510",
    "risk_high": "#b3261e",
}

#: Neutral ink and canvas. Not brand, not invented brand — the paper.
NEUTRAL: dict[str, str] = {
    "ink": "#12222a",
    "muted": "#4d5f67",
    "line": "#d3dee0",
    "canvas": "#eef2f3",
    "surface": "#ffffff",
    "surface_2": "#f5f8f9",
}

#: Reference backgrounds for brand text, one per mode. Each is the *worst case*
#: — the lightest dark surface and the darkest light surface that brand text can
#: land on, both being the far stops of the launcher's backdrop gradient.
#:
#: Measuring against the easy cases (near-black, pure white) is what went wrong
#: twice here: a colour clearing AA on #ffffff still failed at 3.31:1 on the
#: launcher's #d3dfe3, and one clearing AA on #0b1f29 failed at 3.89:1 on
#: #14303c. Anchoring on the worst case satisfies every easier surface for free.
DARK_SURFACE = "#14303c"
LIGHT_SURFACE = "#d3dfe3"

#: The roles the stylesheet fills from brand colours. Every one of these is
#: decoration or chrome — none of them carries meaning a user must decode, which
#: is why reuse is safe here and would not be safe for a risk band.
BRAND_ROLES = ("chrome", "chrome_2", "chrome_line", "accent", "accent_2",
               "highlight", "action")


# ----------------------------------------------------------------- colour maths

def _rgb(hex_colour: str) -> tuple[float, float, float]:
    h = hex_colour.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore


def _hex(r: float, g: float, b: float) -> str:
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def luminance(hex_colour: str) -> float:
    """WCAG relative luminance."""
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in _rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    lo, hi = sorted((la, lb))
    return (hi + 0.05) / (lo + 0.05)


def readable_on(background: str) -> str:
    """Black or white — whichever is legible. The background is never changed."""
    return "#ffffff" if contrast("#ffffff", background) >= \
        contrast(NEUTRAL["ink"], background) else NEUTRAL["ink"]


def _walk_lightness(hex_colour: str, on: str, ratio: float, step: float,
                    fallback: str) -> str:
    """Move a colour along its own lightness axis until it reads against `on`.

    Hue and saturation are preserved, so the result is still recognisably the
    agency's colour — this is the one adjustment made to a brand value, and only
    because small text has to be legible.
    """
    if contrast(hex_colour, on) >= ratio:
        return hex_colour
    h, l, s = colorsys.rgb_to_hls(*_rgb(hex_colour))
    while 0.0 < l + step < 1.0:
        l += step
        candidate = _hex(*colorsys.hls_to_rgb(h, l, s))
        if contrast(candidate, on) >= ratio:
            return candidate
    return fallback


def darken_for_text(hex_colour: str, on: str = LIGHT_SURFACE,
                    ratio: float = 4.5) -> str:
    """A brand colour dark enough to read as text on a light surface."""
    return _walk_lightness(hex_colour, on, ratio, -0.02, NEUTRAL["ink"])


def lighten_for_text(hex_colour: str, on: str = DARK_SURFACE,
                     ratio: float = 4.5) -> str:
    """A brand colour light enough to read as text on a dark surface.

    Dark mode needs its own value: an accent darkened for white would vanish
    against the dark canvas, so both are computed and the stylesheet swaps them.
    """
    return _walk_lightness(hex_colour, on, ratio, 0.02, "#e7eff1")


# --------------------------------------------------------------- role assignment

def roles_from(colors: list[str]) -> dict[str, str]:
    """Fill the brand roles by reusing `colors`. Never returns a new colour.

    Every value in the result is an element of `colors`, so a four-colour agency
    is themed in exactly its four colours.
    """
    if not colors:
        raise ValueError("an agency needs at least one colour to theme with")

    by_light = sorted(colors, key=luminance)
    darkest, lightest = by_light[0], by_light[-1]

    def next_unused(*taken: str) -> str:
        """Most prominent colour not already spoken for, else reuse."""
        for colour in colors:                    # colors is prominence-ordered
            if colour not in taken:
                return colour
        return colors[0]

    chrome = darkest                             # carries the nav and header
    chrome_2 = by_light[1] if len(by_light) > 1 else chrome
    accent = next_unused(chrome)                 # links, focus, borders, strokes
    accent_2 = next_unused(chrome, accent)
    highlight = lightest if lightest != chrome else accent
    chrome_line = by_light[len(by_light) // 2]   # rules inside the dark chrome

    # Buttons put text directly on a fill, so `action` must be a colour that can
    # carry text at AA. A mid-tone often cannot in either black or white — the
    # agency's olive slate reaches only 4.3:1 against white — and the answer is
    # to pick a different colour the agency already has, never to adjust one.
    # The darkest colour is the guaranteed fallback: it always takes white.
    action = next((c for c in colors if can_carry_text(c)), chrome)

    return {"chrome": chrome, "chrome_2": chrome_2, "chrome_line": chrome_line,
            "accent": accent, "accent_2": accent_2, "highlight": highlight,
            "action": action}


def can_carry_text(background: str, ratio: float = 4.5) -> bool:
    """Whether black or white clears `ratio` over this colour."""
    return max(contrast("#ffffff", background),
               contrast(NEUTRAL["ink"], background)) >= ratio


def bands(colors: list[str]) -> str:
    """A hard-edged stripe for each colour, in prominence order.

    Every colour the agency has appears exactly once and at equal width, so a
    twenty-colour agency looks like a twenty-colour agency. No interpolation:
    blending would invent intermediate colours, which is the thing to avoid.
    """
    step = 100 / len(colors)
    stops = ", ".join(
        f"{c} {i * step:.2f}% {(i + 1) * step:.2f}%"
        for i, c in enumerate(colors))
    return f"linear-gradient(180deg, {stops})"


def sweep(colors: list[str], limit: int = 4) -> str:
    """A soft diagonal wash for large fills, using the most prominent colours.

    Capped because a twenty-stop gradient across a whole state silhouette reads
    as mud. The full set is always shown by `bands()`; this is for area fills
    where legibility of the shape matters more than completeness.
    """
    picks = colors[:limit] if len(colors) > 1 else colors * 2
    step = 100 / max(len(picks) - 1, 1)
    stops = ", ".join(f"{c} {i * step:.1f}%" for i, c in enumerate(picks))
    return f"linear-gradient(135deg, {stops})"


def theme_for(colors: list[str]) -> dict[str, object]:
    """The complete set of values the stylesheet needs, plus what it drew on.

    `brand_count` is how many colours the agency actually has; `reused` is how
    many roles had to share one. Both are reported rather than hidden, because
    "themed in four colours" is the honest description of a four-colour agency.
    """
    roles = roles_from(colors)
    accent = roles["accent"]
    accent_text = darken_for_text(accent)
    accent_text_dark = lighten_for_text(accent)

    vars_: dict[str, str] = {}
    for role, colour in roles.items():
        vars_[f"--{role.replace('_', '-')}"] = colour
    vars_["--on-chrome"] = readable_on(roles["chrome"])
    vars_["--on-action"] = readable_on(roles["action"])
    # Emitted as the two *inputs*, not as --accent-text itself. applyTheme() sets
    # these as inline styles on <html>, and an inline style outranks any
    # stylesheet rule — so if --accent-text were set here, the dark-mode swap in
    # tokens.css could never take effect. tokens.css picks between them.
    vars_["--accent-text-light"] = accent_text
    vars_["--accent-text-dark"] = accent_text_dark
    vars_["--brand-bands"] = bands(colors)
    vars_["--brand-sweep"] = sweep(colors)
    for key, colour in STATUS.items():
        vars_[f"--{key.replace('_', '-')}"] = colour
    for key, colour in NEUTRAL.items():
        vars_[f"--{key.replace('_', '-')}"] = colour

    return {
        "vars": vars_,
        "roles": roles,
        "colors": list(colors),
        "brand_count": len(colors),
        "reused": len(BRAND_ROLES) - len(set(roles.values())),
        "accent_text_adjusted": accent_text != accent,
    }
