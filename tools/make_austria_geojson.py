"""Download, simplify, and package the nine Austrian federal-state shapes."""
import json
import math
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/"
    "ne_10m_admin_1_states_provinces.geojson"
)
STATE_NAMES = {
    "AT-1": "Burgenland",
    "AT-2": "Kärnten",
    "AT-3": "Niederösterreich",
    "AT-4": "Oberösterreich",
    "AT-5": "Salzburg",
    "AT-6": "Steiermark",
    "AT-7": "Tirol",
    "AT-8": "Vorarlberg",
    "AT-9": "Wien",
}
TOLERANCE = 0.01


def _distance(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0 and dy == 0:
        return math.hypot(point[0] - start[0], point[1] - start[1])
    amount = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)))
    closest = (start[0] + amount * dx, start[1] + amount * dy)
    return math.hypot(point[0] - closest[0], point[1] - closest[1])


def _simplify_open(points, tolerance):
    if len(points) <= 2:
        return points
    maximum, index = 0.0, 0
    for position in range(1, len(points) - 1):
        distance = _distance(points[position], points[0], points[-1])
        if distance > maximum:
            maximum, index = distance, position
    if maximum <= tolerance:
        return [points[0], points[-1]]
    left = _simplify_open(points[:index + 1], tolerance)
    right = _simplify_open(points[index:], tolerance)
    return left[:-1] + right


def _simplify_ring(ring, tolerance):
    if len(ring) < 5 or ring[0] != ring[-1]:
        simplified = _simplify_open(ring, tolerance)
        return simplified if len(simplified) >= 4 else ring
    open_ring = ring[:-1]
    anchor = open_ring[0]
    split = max(range(1, len(open_ring)), key=lambda index: _distance(open_ring[index], anchor, anchor))
    first = _simplify_open(open_ring[:split + 1], tolerance)
    second = _simplify_open(open_ring[split:] + [anchor], tolerance)
    simplified = first[:-1] + second
    if simplified[-1] != simplified[0]:
        simplified.append(simplified[0])
    return simplified if len(simplified) >= 4 else ring


def _simplify_geometry(geometry, tolerance):
    kind = geometry["type"]
    coordinates = geometry["coordinates"]
    if kind == "Polygon":
        geometry["coordinates"] = [_simplify_ring(ring, tolerance) for ring in coordinates]
    elif kind == "MultiPolygon":
        geometry["coordinates"] = [
            [_simplify_ring(ring, tolerance) for ring in polygon]
            for polygon in coordinates
        ]
    else:
        raise ValueError(f"Unsupported geometry type: {kind}")
    return geometry


def _source_file():
    cache_dir = Path(tempfile.gettempdir()) / "accessdesk2-cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached = cache_dir / "ne_10m_admin_1_states_provinces.geojson"
    if not cached.exists():
        request = Request(SOURCE_URL, headers={"User-Agent": "AccessDesk2-local-asset-builder"})
        with urlopen(request, timeout=60) as response, cached.open("wb") as stream:
            stream.write(response.read())
    return cached


def build(output_path=None):
    output_path = Path(output_path) if output_path else (
        Path(__file__).resolve().parents[1] / "web" / "src" / "assets" / "austria-states.json"
    )
    with _source_file().open(encoding="utf-8") as stream:
        source = json.load(stream)
    features = []
    found = set()
    for feature in source["features"]:
        properties = feature["properties"]
        iso_code = properties.get("iso_3166_2")
        if properties.get("adm0_a3") != "AUT" or iso_code not in STATE_NAMES:
            continue
        region = STATE_NAMES[iso_code]
        found.add(iso_code)
        geometry = _simplify_geometry(feature["geometry"], TOLERANCE)

        def rounded(value):
            if isinstance(value, list):
                return [rounded(item) for item in value]
            return round(value, 4)

        features.append({
            "type": "Feature",
            "properties": {"region": region, "iso_3166_2": iso_code},
            "geometry": {"type": geometry["type"], "coordinates": rounded(geometry["coordinates"])},
        })
    missing = set(STATE_NAMES) - found
    if missing:
        raise ValueError(f"Natural Earth data did not contain Austrian regions: {sorted(missing)}")
    features.sort(key=lambda feature: feature["properties"]["iso_3166_2"])
    collection = {"type": "FeatureCollection", "features": features}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return output_path


if __name__ == "__main__":
    path = build()
    print(f"Wrote {path} ({path.stat().st_size:,} bytes)")
