"""Theme invariants.

An agency's brand here is however many colours it actually has — two, three,
eight, twenty — and that list is never padded. These tests exist because the
padding bug was subtle and looked fine: derived filler followed the same recipe
for every agency, so the states quietly converged toward one house style while
each individual palette still looked plausible.

Four things must hold no matter what the scraped sites happen to serve:

  1. Nothing is invented. Every brand role resolves to a colour the agency
     actually has, so a four-colour agency is themed in exactly those four.

  2. Status colours are universal. Low / Moderate / High risk are identical in
     all fifty states — a governance record where High renders maroon in one
     state and olive in the next invites misreading.

  3. Provenance is not overstated. A scrape is evidence of use, not a ratified
     brand, and a placeholder says so.

  4. Text stays legible over whatever the brand turns out to be, without the
     brand colour being altered to achieve it.
"""

from __future__ import annotations

import pytest

from app.states import all_states, entry
from app.theme import (BRAND_ROLES, DARK_SURFACE, LIGHT_SURFACE, NEUTRAL,
                       STATUS, bands, contrast, darken_for_text,
                       lighten_for_text, readable_on, roles_from, sweep,
                       theme_for)

CODES = [s.code for s in all_states()]
PROVENANCE = {"brand", "scraped", "documented", "generated"}


# ------------------------------------------------------------------ no invention

@pytest.mark.parametrize("code", CODES)
def test_every_role_uses_a_colour_the_agency_actually_has(code: str) -> None:
    """The central guarantee. A role filled with a synthesised colour is a bug."""
    e = entry(code)
    owned = set(e.colors)
    for role, colour in e.roles.items():
        assert colour in owned, (
            f"{code}.{role} = {colour} is not one of {e.abbrev}'s "
            f"{len(owned)} colours: {sorted(owned)}")


@pytest.mark.parametrize("code", CODES)
def test_colour_list_is_never_padded(code: str) -> None:
    e = entry(code)
    assert e.brand_count == len(e.colors)
    assert len(set(e.colors)) == len(e.colors), f"{code} lists a colour twice"
    assert e.colors, f"{code} has no colours at all"


@pytest.mark.parametrize("code", CODES)
def test_all_roles_are_filled(code: str) -> None:
    e = entry(code)
    assert set(e.roles) == set(BRAND_ROLES), f"{code} is missing a brand role"


def test_a_short_palette_stays_short() -> None:
    """Two published colours must theme in two, by reuse rather than invention."""
    two = ["#14558f", "#f6c51b"]
    built = theme_for(two)
    assert set(built["roles"].values()) <= set(two)
    assert built["brand_count"] == 2
    assert built["reused"] == len(BRAND_ROLES) - 2

    one = ["#8a1538"]
    assert set(theme_for(one)["roles"].values()) == set(one)


def test_a_long_palette_uses_all_of_it() -> None:
    """Twenty colours must not be silently truncated to a fixed slot count."""
    many = [f"#{i:02x}3a{(200 - i * 7) % 256:02x}" for i in range(20)]
    built = theme_for(many)
    assert built["brand_count"] == 20
    assert built["colors"] == many
    # bands() is what makes the full set visible, so every colour must appear.
    css = bands(many)
    for colour in many:
        assert colour in css, f"{colour} missing from the brand bands"


def test_bands_and_sweep_introduce_no_new_colours() -> None:
    import re
    colors = ["#003e53", "#356584", "#23884c", "#babc33"]
    for css in (bands(colors), sweep(colors)):
        for found in re.findall(r"#[0-9a-fA-F]{6}", css):
            assert found in colors, f"{found} was invented by a gradient"


def test_roles_from_rejects_an_empty_brand() -> None:
    with pytest.raises(ValueError):
        roles_from([])


# ------------------------------------------------------------- universal status

@pytest.mark.parametrize("code", CODES)
def test_status_colours_are_identical_in_every_state(code: str) -> None:
    """Risk must mean the same thing whichever agency is loaded."""
    theme = entry(code).theme
    for key, expected in STATUS.items():
        var = f"--{key.replace('_', '-')}"
        assert theme[var] == expected, (
            f"{code} themed {var} to {theme[var]} — status colours are universal")


@pytest.mark.parametrize("code", CODES)
def test_no_brand_colour_leaks_into_a_status_slot(code: str) -> None:
    e = entry(code)
    for key in STATUS:
        assert e.theme[f"--{key.replace('_', '-')}"] not in set(e.colors) or \
            e.theme[f"--{key.replace('_', '-')}"] in STATUS.values()


def test_risk_colours_read_as_their_meaning() -> None:
    """Low green, Moderate amber, High red — checked once, since they are fixed."""
    import colorsys

    def hue(hex_colour: str) -> float:
        r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hls(r, g, b)[0]

    assert 0.20 <= hue(STATUS["risk_low"]) <= 0.47, "Low is not green"
    assert 0.05 <= hue(STATUS["risk_moderate"]) <= 0.19, "Moderate is not warm"
    h = hue(STATUS["risk_high"])
    assert h <= 0.05 or h >= 0.94, "High is not red"


# ----------------------------------------------------------------- legibility

@pytest.mark.parametrize("code", CODES)
def test_text_over_the_chrome_is_legible(code: str) -> None:
    """WCAG AA for the nav and header, without altering the brand colour."""
    e = entry(code)
    chrome = e.roles["chrome"]
    assert e.theme["--on-chrome"] == readable_on(chrome)
    assert contrast(e.theme["--on-chrome"], chrome) >= 4.5, (
        f"{code} chrome {chrome} cannot carry legible text")


@pytest.mark.parametrize("code", CODES)
def test_button_text_is_legible(code: str) -> None:
    """`action` exists precisely so a button fill can always carry text.

    A mid-tone accent often cannot clear AA against either black or white, so
    the role is chosen from the agency's own colours by legibility rather than a
    colour being adjusted to fit.
    """
    e = entry(code)
    action = e.roles["action"]
    assert action in set(e.colors), f"{code} action colour is not the agency's"
    assert contrast(e.theme["--on-action"], action) >= 4.5, (
        f"{code} button fill {action} cannot carry legible text")


#: Every background brand text can land on, per mode. The launcher's backdrop is
#: a gradient, so both its stops count; the panel and app surfaces are easier
#: cases but are asserted anyway, because "it passed on white" is exactly the
#: reasoning that let two contrast bugs through.
LIGHT_BACKGROUNDS = ("#ffffff", "#f5f8f9", "#eef2f3", "#e8eff1", LIGHT_SURFACE)
DARK_BACKGROUNDS = ("#05121a", "#0b1f29", "#0f2733", "#0b1d25", DARK_SURFACE)


@pytest.mark.parametrize("code", CODES)
def test_accent_text_meets_aa_on_every_light_surface(code: str) -> None:
    """The one place a brand colour is adjusted — and only in lightness."""
    colour = entry(code).theme["--accent-text-light"]
    for background in LIGHT_BACKGROUNDS:
        assert contrast(colour, background) >= 4.5, (
            f"{code} accent text {colour} fails AA on {background}")


@pytest.mark.parametrize("code", CODES)
def test_accent_text_meets_aa_on_every_dark_surface(code: str) -> None:
    """Dark mode needs its own value: darkened-for-white vanishes on dark."""
    colour = entry(code).theme["--accent-text-dark"]
    for background in DARK_BACKGROUNDS:
        assert contrast(colour, background) >= 4.5, (
            f"{code} dark accent text {colour} fails AA on {background}")


def test_the_reference_surfaces_really_are_the_worst_cases() -> None:
    """If a new surface out-ranges these, the anchors must move with it."""
    from app.theme import luminance
    assert luminance(LIGHT_SURFACE) == min(map(luminance, LIGHT_BACKGROUNDS))
    assert luminance(DARK_SURFACE) == max(map(luminance, DARK_BACKGROUNDS))


@pytest.mark.parametrize("code", CODES)
def test_the_two_accent_text_variants_are_supplied_separately(code: str) -> None:
    """--accent-text itself must NOT be emitted.

    applyTheme() writes these as inline styles on <html>, and an inline style
    outranks any stylesheet rule — so emitting --accent-text here would pin it
    and the dark-mode swap in tokens.css could never take effect.
    """
    theme = entry(code).theme
    assert "--accent-text" not in theme
    assert "--accent-text-light" in theme and "--accent-text-dark" in theme


def test_lightness_walks_preserve_the_hue() -> None:
    """Both directions keep the agency's hue — that is what makes it defensible."""
    import colorsys

    def hue(hex_colour: str) -> float:
        r, g, b = (int(hex_colour[i:i + 2], 16) / 255 for i in (1, 3, 5))
        return colorsys.rgb_to_hls(r, g, b)[0]

    bright = "#ffd76d"                        # fails AA on white
    darker = darken_for_text(bright)
    assert contrast(darker, "#ffffff") >= 4.5
    assert abs(hue(darker) - hue(bright)) < 0.02, "darkening shifted the hue"

    deep = "#071e32"                          # fails AA on a dark surface
    lighter = lighten_for_text(deep)
    assert contrast(lighter, DARK_SURFACE) >= 4.5
    assert abs(hue(lighter) - hue(deep)) < 0.02, "lightening shifted the hue"


def test_readable_on_picks_the_better_of_black_and_white() -> None:
    assert readable_on("#000000") == "#ffffff"
    assert readable_on("#ffffff") == NEUTRAL["ink"]
    assert readable_on("#f6c51b") == NEUTRAL["ink"]


# ------------------------------------------------------------------ provenance

@pytest.mark.parametrize("code", CODES)
def test_provenance_is_never_overstated(code: str) -> None:
    e = entry(code)
    assert e.provenance in PROVENANCE
    if e.is_brand:
        assert e.provenance == "brand"
    else:
        # Anything short of a ratified brand must say so in the interface.
        assert e.caveat, f"{code} is not a brand yet carries no caveat"


@pytest.mark.parametrize("code", CODES)
def test_scraped_palettes_name_the_site_they_came_from(code: str) -> None:
    e = entry(code)
    if e.provenance == "scraped":
        assert "http" in e.palette_source, (
            f"{code} claims a scrape without citing the URL")


@pytest.mark.parametrize("code", CODES)
def test_no_caveat_claims_colours_were_derived(code: str) -> None:
    """Guards the wording against regressing to the padded model."""
    e = entry(code)
    if e.provenance in {"scraped", "documented"}:
        lowered = e.caveat.lower()
        # Phrases that assert padding happened. "nothing here was invented" is
        # the opposite claim, so match the assertion, not the bare word.
        for phrase in ("were derived", "was derived", "to complete the palette",
                       "the rest were", "the remaining"):
            assert phrase not in lowered, (
                f"{code} caveat still describes padding: {e.caveat!r}")


def test_only_the_agency_with_a_brand_guide_is_brand_grade() -> None:
    brands = [e.code for e in map(entry, CODES) if e.provenance == "brand"]
    assert brands == ["SC"], f"unexpected brand-grade palettes: {brands}"


def test_placeholders_do_not_pretend_to_be_a_palette() -> None:
    """No evidence should look like no evidence, not like a confident brand."""
    placeholders = [e for e in map(entry, CODES) if e.provenance == "generated"]
    assert placeholders, "expected some states to have no colours available"
    for e in placeholders:
        assert e.brand_count <= 2, (
            f"{e.code} invents {e.brand_count} colours it has no source for")
        assert "not" in e.caveat.lower()


def test_scraping_actually_contributed_colours() -> None:
    """A silent scraper failure would leave every state on a placeholder."""
    scraped = [e for e in map(entry, CODES) if e.provenance == "scraped"]
    assert len(scraped) >= 25, f"only {len(scraped)} states have scraped colours"
    mean = sum(e.brand_count for e in scraped) / len(scraped)
    assert mean >= 3.0, f"scraped agencies average only {mean:.1f} colours"


# -------------------------------------------------------------- distinctiveness

def test_states_do_not_converge_on_a_shared_look() -> None:
    """The bug this suite exists for: filler making every state look alike.

    A colour on many agencies is a framework default, not a brand. The scraper
    drops those; this asserts the result, so a regression in that filter shows up
    here rather than as a vague sense that the states look samey.
    """
    from collections import Counter
    scraped = [e for e in map(entry, CODES) if e.provenance == "scraped"]
    shared = Counter()
    for e in scraped:
        shared.update(set(e.colors))
    worst = shared.most_common(1)[0] if shared else ("", 0)
    assert worst[1] <= 2, (
        f"{worst[0]} appears on {worst[1]} agencies — a framework default is "
        f"leaking through and making states look alike")


def test_chrome_and_accent_differ_where_the_agency_has_the_colours() -> None:
    """With three or more colours there is no excuse for a one-note interface."""
    for e in map(entry, CODES):
        if e.brand_count >= 3:
            distinct = len(set(e.roles.values()))
            assert distinct >= 3, (
                f"{e.code} has {e.brand_count} colours but uses only "
                f"{distinct} across six roles")
