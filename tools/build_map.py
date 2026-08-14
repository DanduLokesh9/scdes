"""Build a real, offline US map asset from Census boundary data.

Input   app/web/assets/us-states-10m.json  — us-atlas TopoJSON (public domain,
        derived from US Census Bureau cartographic boundary files)
Output  app/web/assets/us-map.json         — {viewBox, states: {XX: {name, d}}}

This runs once. The application then renders real state outlines with no
network access, which matters because the whole thing is meant to work offline.

Projection is Albers equal-area conic — the standard choice for the contiguous
US — with Alaska and Hawaii projected separately and placed as insets, which is
how essentially every US thematic map is drawn.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

ASSETS = Path(__file__).resolve().parent.parent / "app" / "web" / "assets"
SOURCE = ASSETS / "us-states-10m.json"
TARGET = ASSETS / "us-map.json"

WIDTH, HEIGHT = 960.0, 600.0

FIPS_TO_CODE = {
    "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO",
    "09": "CT", "10": "DE", "11": "DC", "12": "FL", "13": "GA", "15": "HI",
    "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
    "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN",
    "28": "MS", "29": "MO", "30": "MT", "31": "NE", "32": "NV", "33": "NH",
    "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
    "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD",
    "47": "TN", "48": "TX", "49": "UT", "50": "VT", "51": "VA", "53": "WA",
    "54": "WV", "55": "WI", "56": "WY",
}


# ------------------------------------------------------------- TopoJSON

def decode_arcs(topology: dict) -> list[list[tuple[float, float]]]:
    """Undo quantisation and delta-encoding to get lon/lat rings."""
    scale = topology["transform"]["scale"]
    translate = topology["transform"]["translate"]
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * scale[0] + translate[0],
                           y * scale[1] + translate[1]))
        arcs.append(points)
    return arcs


def ring_for(indices: list[int], arcs: list) -> list[tuple[float, float]]:
    ring: list[tuple[float, float]] = []
    for index in indices:
        if index >= 0:
            piece = arcs[index]
        else:
            piece = arcs[~index][::-1]     # negative index means reversed
        ring.extend(piece[1:] if ring else piece)
    return ring


def polygons_of(geometry: dict, arcs: list) -> list[list[tuple[float, float]]]:
    out = []
    if geometry["type"] == "Polygon":
        for part in geometry["arcs"]:
            out.append(ring_for(part, arcs))
    elif geometry["type"] == "MultiPolygon":
        for polygon in geometry["arcs"]:
            for part in polygon:
                out.append(ring_for(part, arcs))
    return out


# ------------------------------------------------------------ projection

def albers(lon: float, lat: float, *, lon0: float, lat0: float,
           p1: float, p2: float) -> tuple[float, float]:
    """Spherical Albers equal-area conic."""
    lam = math.radians(lon - lon0)
    phi = math.radians(lat)
    sp1, sp2 = math.sin(math.radians(p1)), math.sin(math.radians(p2))
    n = 0.5 * (sp1 + sp2)
    if abs(n) < 1e-10:
        n = 1e-10
    c = math.cos(math.radians(p1)) ** 2 + 2 * n * sp1
    rho0 = math.sqrt(max(c - 2 * n * math.sin(math.radians(lat0)), 0)) / n
    rho = math.sqrt(max(c - 2 * n * math.sin(phi), 0)) / n
    theta = n * lam
    # Negate y: Albers increases northward, SVG's y axis increases downward.
    return rho * math.sin(theta), -(rho0 - rho * math.cos(theta))


#: Each inset gets its own conic, tuned to its latitude band.
PROJECTIONS = {
    "lower48": dict(lon0=-96.0, lat0=37.5, p1=29.5, p2=45.5),
    "AK": dict(lon0=-152.0, lat0=60.0, p1=55.0, p2=65.0),
    "HI": dict(lon0=-157.0, lat0=20.0, p1=8.0, p2=18.0),
}

#: Where each group sits in the viewBox: (x, y, width, height) of its slot.
LAYOUT = {
    "lower48": (26.0, 8.0, 908.0, 470.0),
    "AK": (26.0, 400.0, 210.0, 172.0),
    "HI": (256.0, 500.0, 108.0, 66.0),
}


def group_for(code: str) -> str:
    return code if code in ("AK", "HI") else "lower48"


def fit(points_by_state: dict, group: str) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for code, polys in points_by_state.items():
        if group_for(code) != group:
            continue
        for ring in polys:
            for x, y in ring:
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def simplify(ring: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Drop points that move less than `tol`; keeps files small, shape intact."""
    out = [ring[0]]
    for point in ring[1:]:
        px, py = out[-1]
        if abs(point[0] - px) >= tol or abs(point[1] - py) >= tol:
            out.append(point)
    if len(out) < 3:
        return ring[:3]
    return out


def main() -> None:
    topology = json.loads(SOURCE.read_text(encoding="utf-8"))
    arcs = decode_arcs(topology)
    geometries = topology["objects"]["states"]["geometries"]

    names: dict[str, str] = {}
    projected: dict[str, list[list[tuple[float, float]]]] = {}

    for geometry in geometries:
        code = FIPS_TO_CODE.get(str(geometry.get("id", "")).zfill(2))
        if not code:
            continue                       # territories are out of scope
        names[code] = geometry.get("properties", {}).get("name", code)
        params = PROJECTIONS[group_for(code)]
        rings = []
        for ring in polygons_of(geometry, arcs):
            if len(ring) < 4:
                continue
            rings.append([albers(lon, lat, **params) for lon, lat in ring])
        projected[code] = rings

    # Scale each group into its slot, preserving aspect ratio.
    placed: dict[str, list[list[tuple[float, float]]]] = {}
    for group, (ox, oy, ow, oh) in LAYOUT.items():
        minx, miny, maxx, maxy = fit(projected, group)
        span_x, span_y = (maxx - minx) or 1, (maxy - miny) or 1
        k = min(ow / span_x, oh / span_y)
        dx = ox + (ow - span_x * k) / 2
        dy = oy + (oh - span_y * k) / 2
        for code, rings in projected.items():
            if group_for(code) != group:
                continue
            placed[code] = [[((x - minx) * k + dx, (y - miny) * k + dy)
                             for x, y in ring] for ring in rings]

    states: dict[str, dict[str, str]] = {}
    for code, rings in sorted(placed.items()):
        parts = []
        for ring in rings:
            ring = simplify(ring, 0.35)
            if len(ring) < 3:
                continue
            head = f"M{ring[0][0]:.1f},{ring[0][1]:.1f}"
            body = "".join(f"L{x:.1f},{y:.1f}" for x, y in ring[1:])
            parts.append(head + body + "Z")
        if parts:
            states[code] = {"name": names[code], "d": "".join(parts)}

    payload = {
        "viewBox": f"0 0 {WIDTH:.0f} {HEIGHT:.0f}",
        "projection": "Albers equal-area conic; Alaska and Hawaii as insets",
        "source": ("us-atlas states-10m (public domain), derived from US "
                   "Census Bureau cartographic boundary files"),
        "states": states,
    }
    TARGET.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    size = TARGET.stat().st_size / 1024
    print(f"wrote {TARGET.name}: {len(states)} states, {size:.0f} KB")
    missing = sorted(set(FIPS_TO_CODE.values()) - set(states))
    print("missing:", missing or "none")


if __name__ == "__main__":
    main()
