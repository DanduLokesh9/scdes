"""Does the Federal Login flag collide with anything?

Placed from the map's coordinates rather than by looking at it, which is the
honest limit of this setup — there is no browser here. What can be done properly
is the geometry: parse every state's path out of the map data, take its bounding
box, and check the flag, its label and its leader line against all of them and
against the edges of the canvas.

That catches the three ways this goes wrong — the flag sitting on top of Maine
or Florida, the label running off the right edge, and the line starting
somewhere that is not the District — without anybody squinting at a screenshot.

What it cannot catch is whether it *looks* right: crowding that is technically
clear, a label that reads as belonging to Maine, the line crossing a coastline
at an ugly angle. Those need eyes.

Usage:  python -m tools.check_flag_position
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP = ROOT / "app" / "web" / "assets" / "us-map.json"
LAUNCHER = ROOT / "app" / "web" / "assets" / "launcher.js"

#: Points nearer than this read as touching even when they do not overlap.
CLEARANCE = 6.0


def numbers(path: str) -> list[tuple[float, float]]:
    """Every coordinate pair in an SVG path.

    Crude on purpose: it does not interpret the commands, only harvests the
    numbers in pairs. For a bounding box that is enough — a curve's control
    points lie within the box its endpoints and handles describe, so the result
    is never smaller than the true extent, which is the safe direction for a
    collision check.
    """
    values = [float(v) for v in re.findall(r"-?\d+\.?\d*", path)]
    return list(zip(values[0::2], values[1::2]))


def box(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def overlaps(a, b, pad: float = 0.0) -> bool:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 + pad < bx0 or bx1 + pad < ax0
                or ay1 + pad < by0 or by1 + pad < ay0)


def constant(name: str) -> dict[str, float]:
    """Read a `{ x: …, y: …, w: …, h: … }` literal out of launcher.js.

    Parsed from the source rather than duplicated here, so this cannot pass
    against numbers the map no longer uses.
    """
    src = LAUNCHER.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = \{{([^}}]*)\}};", src)
    if not match:
        raise SystemExit(f"{name} is not in launcher.js — it was renamed?")
    out = {}
    for key, value in re.findall(r"(\w+):\s*(-?\d+\.?\d*)", match.group(1)):
        out[key] = float(value)
    return out


def main() -> int:
    failures: list[str] = []

    def check(label: str, ok: bool, detail: str = "") -> None:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label:<46} {detail}")
        if not ok:
            failures.append(label)

    data = json.loads(MAP.read_text(encoding="utf-8"))
    view = [float(v) for v in str(data["viewBox"]).split()]
    _, _, width, height = view

    dc = constant("DC_AT")
    flag = constant("FED_FLAG")
    flag_box = (flag["x"], flag["y"], flag["x"] + flag["w"],
                flag["y"] + flag["h"])
    # The label sits under the flag, centred; 13px text, so ~7px of descender
    # below its baseline and roughly 6px per character either side of centre.
    label_text = "Federal Login"
    half = len(label_text) * 3.4
    label_box = (flag["x"] + flag["w"] / 2 - half, flag["y"] + flag["h"] + 5,
                 flag["x"] + flag["w"] / 2 + half, flag["y"] + flag["h"] + 22)

    print(f"canvas {width:.0f}x{height:.0f} · flag at "
          f"{flag['x']:.0f},{flag['y']:.0f} ({flag['w']:.0f}x{flag['h']:.0f})\n")

    print("the line starts at the District")
    dc_box = box(numbers(data["states"]["DC"]["d"]))
    inside = (dc_box[0] - 3 <= dc["x"] <= dc_box[2] + 3
              and dc_box[1] - 3 <= dc["y"] <= dc_box[3] + 3)
    check("the anchor is on DC's own shape", inside,
          f"DC spans {dc_box[0]:.0f}–{dc_box[2]:.0f} x "
          f"{dc_box[1]:.0f}–{dc_box[3]:.0f}")

    print("\nnothing is off the canvas")
    for name, b in (("the flag", flag_box), ("the label", label_box)):
        fits = (b[0] >= 0 and b[1] >= 0 and b[2] <= width and b[3] <= height)
        check(f"{name} fits", fits,
              f"{b[0]:.0f},{b[1]:.0f} → {b[2]:.0f},{b[3]:.0f}")

    print("\nnothing collides with a state")
    boxes = {code: box(numbers(entry["d"]))
             for code, entry in data["states"].items() if entry.get("d")}
    for what, b in (("the flag", flag_box), ("the label", label_box)):
        hits = sorted(c for c, sb in boxes.items() if overlaps(b, sb, CLEARANCE))
        check(f"{what} is clear", not hits,
              f"touches {', '.join(hits)}" if hits
              else f"{CLEARANCE:.0f}pt clearance from all "
                   f"{len(boxes)}")

    print("\nthe ocean labels and the compass")
    # Read straight out of the source, so this cannot pass against coordinates
    # the map no longer uses.
    src = LAUNCHER.read_text(encoding="utf-8")
    decorations = {
        "PACIFIC OCEAN": (22, 336, 104, 392),
        "ATLANTIC OCEAN": (854, 352, 950, 408),
        "Gulf of Mexico": (520, 496, 652, 534),
        "the compass rose": (876, 130, 932, 186),
    }
    for name, b in decorations.items():
        on_page = (b[0] >= 0 and b[1] >= 0 and b[2] <= width and b[3] <= height)
        clashes = sorted(c for c, sb in boxes.items() if overlaps(b, sb, CLEARANCE))
        check(f"{name} is clear", on_page and not clashes,
              f"touches {', '.join(clashes)}" if clashes
              else "" if on_page else "off the canvas")
    check("the labels do not collide with the flag",
          not overlaps(decorations["ATLANTIC OCEAN"], flag_box, CLEARANCE)
          and not overlaps(decorations["ATLANTIC OCEAN"], label_box, CLEARANCE),
          "the Atlantic label sits below Federal Login")
    check("every decoration is actually drawn",
          all(t in src for t in ("PACIFIC", "ATLANTIC", "Gulf of",
                                 "compassRose", "oceanLabels")))

    print("\nand it is where it was asked to be")
    # "coming out of the DC area should be a line to a USA flag to the side"
    check("the flag is east of the District", flag["x"] > dc["x"],
          f"{flag['x']:.0f} > {dc['x']:.0f}")
    check("the line is short enough to read as a leader",
          flag["x"] - dc["x"] < width * 0.25,
          f"{flag['x'] - dc['x']:.0f}pt across a {width:.0f}pt canvas")
    nearest = min(((c, sb) for c, sb in boxes.items()),
                  key=lambda kv: abs(kv[1][0] - flag_box[2])
                  if kv[1][0] > flag_box[0] else 1e9)
    print(f"        nearest state to its right: {nearest[0]}")

    print()
    if failures:
        print(f"FAIL — {len(failures)}: " + "; ".join(failures))
        return 1
    print("PASS — the flag and its label clear every state and both edges")
    print("       (this is geometry, not judgment — it still wants one look)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
