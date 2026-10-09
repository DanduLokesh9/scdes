"""Does the agency search box stay legible for every agency, in both modes?

The abbreviation in each row is drawn in `--accent-text`, which is a different
color for every state. That color was chosen against the worst-case page
surfaces (#d3dfe3 light, #14303c dark). The combobox uses its own opaque
surfaces — #ffffff and #10222b — because a dropdown floating over the flag has
to be solid.

Both new surfaces sit *further* from mid-gray than the anchors, so the contrast
should improve rather than degrade. That is an argument, not a measurement, and
the first version of this component shipped white-on-white because I reasoned
about color instead of computing it.

    python -m tools.check_combo_contrast
"""

from __future__ import annotations

from app import states, theme

LIGHT_SOLID = "#ffffff"
DARK_SOLID = "#10222b"


def _lum(hex_colour: str) -> float:
    h = hex_colour.lstrip("#")
    parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
             for c in parts]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def ratio(fg: str, bg: str) -> float:
    a, b = _lum(fg), _lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def main() -> int:
    worst_light = ("", 99.0)
    worst_dark = ("", 99.0)
    checked = 0

    registry = states.registry()
    for entry in registry.get("states", []):
        code = entry.get("code", "")
        tokens = entry.get("theme") or {}
        light = tokens.get("--accent-text-light")
        dark = tokens.get("--accent-text-dark")
        if not light or not dark:
            continue
        checked += 1
        rl = ratio(light, LIGHT_SOLID)
        rd = ratio(dark, DARK_SOLID)
        if rl < worst_light[1]:
            worst_light = (code, rl)
        if rd < worst_dark[1]:
            worst_dark = (code, rd)

    print(f"checked {checked} agencies\n")
    print(f"  worst accent on {LIGHT_SOLID} : {worst_light[0]} "
          f"{worst_light[1]:.2f}:1")
    print(f"  worst accent on {DARK_SOLID} : {worst_dark[0]} "
          f"{worst_dark[1]:.2f}:1")

    floor = min(worst_light[1], worst_dark[1])
    # The abbreviation is small bold text, so AA is 4.5:1.
    print(f"\n{'PASS' if floor >= 4.5 else 'FAIL'} — AA needs 4.5:1")
    return 0 if floor >= 4.5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
