from __future__ import annotations

import csv
import html
import json
import math
import re
from urllib.request import urlopen
import zipfile
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parent
VECTORS = ROOT / "Vetores"
OUTPUT = ROOT / "Mapa_Campo_LT_PGR_CAN.html"
TRACKS_DIR = VECTORS / "Caminhamentos Terrestres"
CONTROL_POINTS_CSV = VECTORS / "Pontos_Controle_Google.csv"
CONTROL_POINTS_CSV_URL = "https://docs.google.com/spreadsheets/d/1O5p5TUAw_R8thT9GVXGzjGlRMIXDIdEknbXSaHUAjH4/export?format=csv&gid=0"
TRACK_EXTENSIONS = {".kml", ".kmz", ".gpx"}


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child_text(node: ET.Element, name: str) -> str:
    for child in node:
        if local_name(child.tag) == name and child.text:
            return child.text.strip()
    return ""


def parse_coords(text: str) -> list[list[float]]:
    coords: list[list[float]] = []
    for token in re.split(r"\s+", (text or "").strip()):
        if not token:
            continue
        parts = token.split(",")
        if len(parts) >= 2:
            coords.append([float(parts[0]), float(parts[1])])
    return coords


def read_kml_text(path: Path) -> str:
    if path.suffix.lower() == ".kmz":
        with zipfile.ZipFile(path) as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError(f"KMZ sem KML interno: {path}")
            return archive.read(kml_names[0]).decode("utf-8", errors="ignore")
    return path.read_text(encoding="utf-8", errors="ignore")


def update_control_points_csv(csv_url: str = CONTROL_POINTS_CSV_URL) -> None:
    try:
        with urlopen(csv_url, timeout=30) as response:
            content = response.read()
        CONTROL_POINTS_CSV.write_bytes(content)
    except Exception as exc:
        if not CONTROL_POINTS_CSV.exists():
            raise RuntimeError("Não foi possível baixar a planilha de pontos de controle.") from exc
        print(f"Aviso: usando CSV local porque a planilha online não pôde ser baixada: {exc}")


def activity_from_kml_text(text: str) -> str:
    match = re.search(r"<b>Atividade</b>.*?<td[^>]*>(.*?)</td>", text, re.IGNORECASE | re.DOTALL)
    return re.sub(r"\s+", " ", match.group(1)).strip() if match else ""


def iter_placemarks(root: ET.Element):
    parents: dict[int, ET.Element] = {}
    for parent in root.iter():
        for child in parent:
            parents[id(child)] = parent
    for placemark in root.iter():
        if local_name(placemark.tag) != "Placemark":
            continue
        folder_name = ""
        parent = parents.get(id(placemark))
        while parent is not None:
            if local_name(parent.tag) == "Folder":
                folder_name = child_text(parent, "name")
                break
            parent = parents.get(id(parent))
        yield placemark, folder_name


def placemark_name(placemark: ET.Element, folder_name: str, fallback: str) -> str:
    name = child_text(placemark, "name") or folder_name or fallback
    return re.sub(r"\s+", " ", name).strip()


def parse_kml(path: Path, layer_name: str, layer_type: str) -> list[dict]:
    kml_text = read_kml_text(path)
    activity = activity_from_kml_text(kml_text)
    root = ET.fromstring(kml_text.encode("utf-8"))
    features: list[dict] = []
    for placemark, folder_name in iter_placemarks(root):
        name = placemark_name(placemark, folder_name, path.stem)
        description = child_text(placemark, "description")
        for node in placemark.iter():
            tag = local_name(node.tag)
            if tag not in {"Point", "LineString", "Polygon"}:
                continue
            coords_text = ""
            for child in node.iter():
                if local_name(child.tag) == "coordinates" and child.text:
                    coords_text = child.text
                    break
            coords = parse_coords(coords_text)
            if not coords:
                continue
            if tag == "Point":
                geometry = {"type": "Point", "coordinates": coords[0]}
            elif tag == "LineString":
                geometry = {"type": "LineString", "coordinates": coords}
            else:
                geometry = {"type": "Polygon", "coordinates": [coords]}
            features.append(
                {
                    "type": "Feature",
                    "geometry": geometry,
                    "properties": {
                        "name": name,
                        "description": description,
                        "layer": layer_name,
                        "kind": layer_type,
                        "source": path.name,
                        "activity": activity,
                    },
                }
            )
    return features


def parse_gpx(path: Path, layer_name: str, layer_type: str) -> list[dict]:
    root = ET.fromstring(path.read_text(encoding="utf-8", errors="ignore").encode("utf-8"))
    features: list[dict] = []

    for track_index, track in enumerate((node for node in root.iter() if local_name(node.tag) == "trk"), start=1):
        name = child_text(track, "name") or f"{path.stem} - track {track_index}"
        description = child_text(track, "desc")
        for segment_index, segment in enumerate((node for node in track if local_name(node.tag) == "trkseg"), start=1):
            coords = []
            times = []
            for point in segment:
                if local_name(point.tag) != "trkpt":
                    continue
                lat = point.attrib.get("lat")
                lon = point.attrib.get("lon")
                if lat is None or lon is None:
                    continue
                coord = [float(lon), float(lat)]
                elevation = child_text(point, "ele")
                if elevation:
                    coord.append(float(elevation))
                coords.append(coord)
                point_time = child_text(point, "time")
                if point_time:
                    times.append(point_time)
            if len(coords) < 2:
                continue
            feature_name = name if segment_index == 1 else f"{name} - trecho {segment_index}"
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "name": feature_name,
                        "description": description,
                        "layer": layer_name,
                        "kind": layer_type,
                        "source": path.name,
                        "activity": "",
                        "start_time": times[0] if times else "",
                        "end_time": times[-1] if times else "",
                    },
                }
            )

    for route_index, route in enumerate((node for node in root.iter() if local_name(node.tag) == "rte"), start=1):
        name = child_text(route, "name") or f"{path.stem} - rota {route_index}"
        description = child_text(route, "desc")
        coords = []
        for point in route:
            if local_name(point.tag) != "rtept":
                continue
            lat = point.attrib.get("lat")
            lon = point.attrib.get("lon")
            if lat is not None and lon is not None:
                coords.append([float(lon), float(lat)])
        if len(coords) >= 2:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {
                        "name": name,
                        "description": description,
                        "layer": layer_name,
                        "kind": layer_type,
                        "source": path.name,
                        "activity": "",
                    },
                }
            )

    return features


def parse_vector_file(path: Path, layer_name: str, layer_type: str) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix in {".kml", ".kmz"}:
        return parse_kml(path, layer_name, layer_type)
    if suffix == ".gpx":
        return parse_gpx(path, layer_name, layer_type)
    return []


def parse_control_points_csv(path: Path) -> list[dict]:
    features: list[dict] = []
    with path.open(encoding="utf-8-sig", newline="") as csv_file:
        for index, row in enumerate(csv.DictReader(csv_file), start=1):
            lat, lon = coordinates_from_row(row)
            if lat is None or lon is None:
                continue
            point_name = row.get("Ponto", "").strip() or f"Ponto {index:03d}"
            observations = row.get("Observações", "").strip()
            features.append(
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [lon, lat]},
                    "properties": {
                        "name": point_name,
                        "description": observations,
                        "layer": "Pontos de controle",
                        "kind": "point",
                        "source": path.name,
                        "id": row.get("ID", "").strip(),
                        "data": row.get("Data", "").strip(),
                        "unidade": row.get("Unidade", "").strip(),
                        "relevo": row.get("Relevo - Tipo de Terreno", "").strip(),
                        "declividade": row.get("Declividade", "").strip(),
                        "litologia": row.get("Litologia", "").strip(),
                        "solo": row.get("Solo", "").strip(),
                        "feicoes": row.get("Feições Cársticas", "").strip(),
                        "potencial": row.get("Potencial Espeleológico", "").strip(),
                    },
                }
            )
    return features


def coordinates_from_row(row: dict[str, str]) -> tuple[float | None, float | None]:
    lat_text = row.get("lat", "").strip().replace(",", ".")
    lon_text = row.get("lon", "").strip().replace(",", ".")
    if lat_text and lon_text:
        return float(lat_text), float(lon_text)
    coords = row.get("Coordenadas", "")
    match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*,\s*(-?\d+(?:[.,]\d+)?)", coords)
    if not match:
        return None, None
    return float(match.group(1).replace(",", ".")), float(match.group(2).replace(",", "."))


def parse_track_folder(path: Path, layer_name: str) -> list[dict]:
    features: list[dict] = []
    for track_file in sorted(path.rglob("*")):
        if not track_file.is_file() or track_file.suffix.lower() not in TRACK_EXTENSIONS:
            continue
        track_features = parse_vector_file(track_file, layer_name, "track")
        features.extend(track_features)
    return filter_duplicate_tracks(features)


def parse_track_folder_for_display(path: Path, layer_name: str) -> list[dict]:
    features: list[dict] = []
    raw_features: list[dict] = []
    for track_file in sorted(path.rglob("*")):
        if not track_file.is_file() or track_file.suffix.lower() not in TRACK_EXTENSIONS:
            continue
        raw_features.extend(parse_vector_file(track_file, layer_name, "track"))

    line_features = [feature for feature in raw_features if feature["geometry"]["type"] == "LineString"]
    all_lats = [coord[1] for feature in line_features for coord in feature["geometry"]["coordinates"]]
    ref_lat = sum(all_lats) / len(all_lats) if all_lats else -25.6
    for feature in line_features:
        properties = dict(feature["properties"])
        properties["filtered"] = "traçado completo apresentado no mapa"
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": simplify_line(feature["geometry"]["coordinates"], ref_lat, tolerance_m=2.0),
                },
                "properties": properties,
            }
        )
    return features


def parse_reference_folder(path: Path, layer_name: str) -> list[dict]:
    features: list[dict] = []
    if not path.exists():
        return features
    for vector_file in sorted(path.rglob("*")):
        if not vector_file.is_file() or vector_file.suffix.lower() not in TRACK_EXTENSIONS:
            continue
        features.extend(parse_vector_file(vector_file, layer_name, "extra"))
    return features


def feature_collection(features: list[dict]) -> dict:
    return {"type": "FeatureCollection", "features": features}


def bounds_for(features: list[dict]) -> list[list[float]]:
    west = south = float("inf")
    east = north = float("-inf")

    def visit(coord):
        nonlocal west, south, east, north
        if isinstance(coord[0], (int, float)):
            lon, lat = coord[:2]
            west = min(west, lon)
            east = max(east, lon)
            south = min(south, lat)
            north = max(north, lat)
        else:
            for part in coord:
                visit(part)

    for feature in features:
        visit(feature["geometry"]["coordinates"])
    return [[south, west], [north, east]]


def line_length_km(coords: list[list[float]]) -> float:
    total = 0.0
    earth_radius_km = 6371.0088
    for start, end in zip(coords, coords[1:]):
        lon1, lat1 = map(math.radians, start[:2])
        lon2, lat2 = map(math.radians, end[:2])
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
        total += 2 * earth_radius_km * math.asin(math.sqrt(a))
    return total


def lonlat_to_meters(coord: list[float], ref_lat: float) -> tuple[float, float]:
    lon, lat = coord[:2]
    x = lon * 111_320.0 * math.cos(math.radians(ref_lat))
    y = lat * 110_574.0
    return x, y


def segment_key(start: list[float], end: list[float], ref_lat: float, grid_m: float) -> tuple[int, int, int]:
    x1, y1 = lonlat_to_meters(start, ref_lat)
    x2, y2 = lonlat_to_meters(end, ref_lat)
    mid_x = (x1 + x2) / 2
    mid_y = (y1 + y2) / 2
    angle = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
    angle_bin = round(angle / 15)
    return round(mid_x / grid_m), round(mid_y / grid_m), angle_bin


def filter_duplicate_tracks(features: list[dict], grid_m: float = 35.0, overlap_threshold: float = 0.82) -> list[dict]:
    line_features = [feature for feature in features if feature["geometry"]["type"] == "LineString"]
    all_lats = [coord[1] for feature in line_features for coord in feature["geometry"]["coordinates"]]
    ref_lat = sum(all_lats) / len(all_lats) if all_lats else -25.6
    candidates = []

    for index, feature in enumerate(line_features):
        coords = feature["geometry"]["coordinates"]
        keys = track_keys(coords, ref_lat, grid_m)
        candidates.append(
            {
                "index": index,
                "feature": feature,
                "keys": keys,
                "date": track_date(feature),
                "length": line_length_km(coords),
            }
        )

    kept: list[dict] = []
    for candidate in sorted(candidates, key=lambda item: (item["date"], -item["length"], item["index"])):
        keys = candidate["keys"]
        if not keys:
            continue
        duplicate = False
        for existing in kept:
            if existing["date"] != candidate["date"]:
                continue
            overlap = len(keys & existing["keys"]) / len(keys)
            if overlap >= overlap_threshold:
                duplicate = True
                break
        if not duplicate:
            kept.append(candidate)

    return [complete_track_feature(item["feature"], ref_lat) for item in sorted(kept, key=lambda item: item["index"])]


def track_keys(coords: list[list[float]], ref_lat: float, grid_m: float) -> set[tuple[int, int, int]]:
    keys: set[tuple[int, int, int]] = set()
    for start, end in zip(coords, coords[1:]):
        if line_length_km([start, end]) >= 0.005:
            keys.add(segment_key(start, end, ref_lat, grid_m))
    return keys


def track_date(feature: dict) -> str:
    source = feature["properties"].get("source", "")
    name = feature["properties"].get("name", "")
    match = re.search(r"(20\d{2})[-_](\d{2})[-_](\d{2})", source) or re.search(r"(20\d{2})-(\d{2})-(\d{2})", name)
    return "-".join(match.groups()) if match else source[:10]


def simplify_line(coords: list[list[float]], ref_lat: float, tolerance_m: float) -> list[list[float]]:
    if len(coords) <= 2:
        return coords
    projected = [lonlat_to_meters(coord, ref_lat) for coord in coords]

    def point_line_distance(point, start, end) -> float:
        px, py = point
        x1, y1 = start
        x2, y2 = end
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            return math.hypot(px - x1, py - y1)
        t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
        return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

    keep = {0, len(coords) - 1}
    stack = [(0, len(coords) - 1)]
    while stack:
        start_idx, end_idx = stack.pop()
        if end_idx <= start_idx + 1:
            continue
        start = projected[start_idx]
        end = projected[end_idx]
        max_distance = -1.0
        max_idx = start_idx
        for idx in range(start_idx + 1, end_idx):
            distance = point_line_distance(projected[idx], start, end)
            if distance > max_distance:
                max_distance = distance
                max_idx = idx
        if max_distance > tolerance_m:
            keep.add(max_idx)
            stack.append((start_idx, max_idx))
            stack.append((max_idx, end_idx))
    return [coords[idx] for idx in sorted(keep)]


def complete_track_feature(source_feature: dict, ref_lat: float) -> dict:
    properties = dict(source_feature["properties"])
    properties["filtered"] = "caminhamentos duplicados no mesmo dia removidos, sem cortar ida e volta"
    return {
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": simplify_line(source_feature["geometry"]["coordinates"], ref_lat, tolerance_m=8.0),
        },
        "properties": properties,
    }


def total_line_length_km(features: list[dict]) -> float:
    total = 0.0
    for feature in features:
        if feature["geometry"]["type"] == "LineString":
            total += line_length_km(feature["geometry"]["coordinates"])
        elif feature["geometry"]["type"] == "MultiLineString":
            total += sum(line_length_km(part) for part in feature["geometry"]["coordinates"])
    return total


def collect_features(
    control_points_csv_url: str = CONTROL_POINTS_CSV_URL,
    tracks_dir: Path | str = TRACKS_DIR,
    lt_label: str = "LT 500kV Ponta Grossa - Canoinhas",
    tracks_label: str = "Caminhamentos terrestres",
    points_label: str = "Pontos de controle",
    extra_vectors_dir: Path | str | None = None,
    extra_vectors_label: str = "Áreas e referências",
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    update_control_points_csv(control_points_csv_url)
    lt = parse_kml(VECTORS / "LT230kV PGR-CAN.kml", lt_label, "lt")
    points = parse_control_points_csv(CONTROL_POINTS_CSV) if CONTROL_POINTS_CSV.exists() else parse_kml(VECTORS / "Pontos Vistoriados.kml", points_label, "point")
    for point in points:
        point["properties"]["layer"] = points_label
    tracks_path = Path(tracks_dir)
    tracks = parse_track_folder_for_display(tracks_path, tracks_label)
    tracks_for_distance = parse_track_folder(tracks_path, tracks_label)
    extras = parse_reference_folder(Path(extra_vectors_dir), extra_vectors_label) if extra_vectors_dir else []
    return lt, points, tracks, tracks_for_distance, extras


def main(
    map_title: str = "Mapa de Pontos e Caminhamentos LT Ponta Grossa - Canoinhas",
    control_points_csv_url: str = CONTROL_POINTS_CSV_URL,
    tracks_dir: Path | str = TRACKS_DIR,
    lt_label: str = "LT 500kV Ponta Grossa - Canoinhas",
    lt_color: str = "#d71920",
    tracks_label: str = "Caminhamentos terrestres",
    tracks_color: str = "#2f80ed",
    points_label: str = "Pontos de controle",
    extra_vectors_dir: Path | str | None = None,
    extra_vectors_label: str = "Áreas e referências",
    extra_vectors_color: str = "#7c3aed",
) -> dict:
    lt, points, tracks, tracks_for_distance, extras = collect_features(
        control_points_csv_url=control_points_csv_url,
        tracks_dir=tracks_dir,
        lt_label=lt_label,
        tracks_label=tracks_label,
        points_label=points_label,
        extra_vectors_dir=extra_vectors_dir,
        extra_vectors_label=extra_vectors_label,
    )
    all_features = lt + points + tracks + extras
    data = feature_collection(all_features)
    map_bounds = bounds_for(all_features)
    point_bounds = bounds_for(points)
    generated_date = datetime.now().strftime("%d/%m/%Y")
    extra_legend_row = (
        f'<div class="row"><span class="swatch area" style="border-color:{html.escape(extra_vectors_color)}; background:{html.escape(extra_vectors_color)}22"></span><span>{html.escape(extra_vectors_label)}</span></div>'
        if extras
        else ""
    )

    summary = {
        "lt": len(lt),
        "points": len(points),
        "tracks": len(tracks),
        "extras": len(extras),
        "tracks_km": total_line_length_km(tracks_for_distance),
        "features": len(all_features),
    }

    html_doc = f"""<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(map_title)}</title>
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    :root {{
      color-scheme: light;
      --ink: #17212b;
      --muted: #52606d;
      --panel: #ffffff;
      --line: #d6dde5;
      --lt: {html.escape(lt_color)};
      --track: {html.escape(tracks_color)};
      --extra: {html.escape(extra_vectors_color)};
      --point: #ffd23f;
    }}
    html, body {{
      height: 100%;
      margin: 0;
      font-family: Arial, Helvetica, sans-serif;
      color: var(--ink);
      background: #eef2f5;
    }}
    .page {{
      display: grid;
      grid-template-rows: auto 1fr;
      height: 100%;
    }}
    header {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 18px;
      align-items: center;
      padding: 14px 18px;
      background: var(--panel);
      border-bottom: 1px solid var(--line);
      box-shadow: 0 1px 8px rgba(20, 35, 50, 0.08);
      z-index: 500;
    }}
    h1 {{
      margin: 0;
      font-size: 20px;
      line-height: 1.2;
      letter-spacing: 0;
    }}
    .subtitle {{
      margin-top: 3px;
      color: var(--muted);
      font-size: 12px;
    }}
    .stats {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
      font-size: 12px;
      color: var(--muted);
    }}
    .stat {{
      border: 1px solid var(--line);
      border-radius: 6px;
      padding: 5px 8px;
      background: #f8fafc;
      white-space: nowrap;
    }}
    #map {{
      width: 100%;
      height: 100%;
    }}
    .legend, .reference {{
      background: rgba(255, 255, 255, 0.96);
      border: 1px solid var(--line);
      border-radius: 8px;
      box-shadow: 0 2px 12px rgba(20, 35, 50, 0.15);
    }}
    .legend {{
      padding: 10px 12px;
      min-width: 190px;
      font-size: 12px;
      margin-bottom: 24px !important;
    }}
    .legend-title {{
      font-weight: 700;
      margin-bottom: 7px;
    }}
    .row {{
      display: flex;
      align-items: center;
      gap: 7px;
      margin: 5px 0;
    }}
    .swatch {{
      width: 22px;
      height: 0;
      border-top: 4px solid;
      border-radius: 4px;
      flex: 0 0 auto;
    }}
    .swatch.area {{
      height: 10px;
      border-top-width: 3px;
    }}
    .dot {{
      width: 11px;
      height: 11px;
      border-radius: 50%;
      background: var(--point);
      border: 2px solid #333;
      box-sizing: border-box;
      flex: 0 0 auto;
    }}
    .reference {{
      width: 260px;
      padding: 8px;
    }}
    .reference-title {{
      font-size: 12px;
      font-weight: 700;
      margin: 0 0 6px;
    }}
    #overview {{
      width: 260px;
      height: 180px;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid var(--line);
    }}
    .leaflet-popup-content {{
      margin: 10px 12px;
      font-size: 12px;
    }}
    .leaflet-control-layers-expanded {{
      max-width: min(245px, calc(100vw - 52px));
      font-size: 12px;
      line-height: 1.25;
    }}
    .leaflet-control-layers label {{
      margin-bottom: 3px;
    }}
    .popup-title {{
      font-weight: 700;
      margin-bottom: 4px;
    }}
    @media print {{
      header {{ box-shadow: none; }}
      .leaflet-control-layers, .leaflet-control-zoom {{ display: none !important; }}
    }}
    @media (max-width: 760px) {{
      header {{
        grid-template-columns: 1fr;
      }}
      .stats {{
        justify-content: flex-start;
      }}
      .reference {{
        width: 190px;
      }}
      #overview {{
        width: 190px;
        height: 128px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <header>
      <div>
        <h1>{html.escape(map_title)}</h1>
        <div class="subtitle">Dados coletados até {html.escape(generated_date)}.</div>
      </div>
      <div class="stats">
        <div class="stat">{summary["points"]} pontos de controle</div>
        <div class="stat">{summary["tracks_km"]:.1f} km percorridos</div>
      </div>
    </header>
    <main id="map"></main>
  </div>
  <script>
    const dataset = {json.dumps(data, ensure_ascii=False)};
    const bounds = {json.dumps(map_bounds)};
    const pointBounds = {json.dumps(point_bounds)};

    const map = L.map('map', {{ zoomControl: true }});
    const imagery = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 19,
      attribution: 'Imagem: Esri, Maxar, Earthstar Geographics e colaboradores'
    }});
    const localities = L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{
      maxZoom: 19,
      attribution: 'Localidades: OpenStreetMap'
    }});
    const labels = L.tileLayer('https://services.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{{z}}/{{y}}/{{x}}', {{
      maxZoom: 19,
      attribution: 'Rótulos: Esri'
    }});
    imagery.addTo(map);
    labels.addTo(map);

    function escapeHtml(value) {{
      return String(value || '').replace(/[&<>"']/g, char => ({{
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
      }}[char]));
    }}

    function popupContent(feature) {{
      const p = feature.properties || {{}};
      const rows = p.kind === 'point'
        ? [
          ['Unidade', p.unidade],
          ['Potencial Espeleológico', p.potencial]
        ].filter(([, value]) => value)
        : [
          ['Camada', p.layer],
          ['Fonte', p.source]
        ].filter(([, value]) => value);
      const details = rows.map(([label, value]) => `<div><strong>${{escapeHtml(label)}}:</strong> ${{escapeHtml(value)}}</div>`).join('');
      return `<div class="popup-title">${{escapeHtml(p.name || p.layer)}}</div>${{details}}`;
    }}

    function styleFeature(feature) {{
      const kind = feature.properties.kind;
      if (kind === 'lt') return {{ color: {json.dumps(lt_color)}, weight: 4, opacity: 0.95 }};
      if (kind === 'track') return {{ color: {json.dumps(tracks_color)}, weight: 2, opacity: 0.8 }};
      if (kind === 'extra') return {{ color: {json.dumps(extra_vectors_color)}, weight: 2, opacity: 0.85, fillColor: {json.dumps(extra_vectors_color)}, fillOpacity: 0.18 }};
      return {{ color: '#333333', weight: 1 }};
    }}

    function pointMarker(feature, latlng) {{
      return L.circleMarker(latlng, {{
        radius: 5,
        fillColor: '#ffd23f',
        color: '#24292f',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.95
      }});
    }}

    const ltLayer = L.geoJSON(dataset, {{
      filter: f => f.properties.kind === 'lt',
      style: styleFeature,
      onEachFeature: (f, l) => l.bindPopup(popupContent(f))
    }}).addTo(map);
    const trackLayer = L.geoJSON(dataset, {{
      filter: f => f.properties.kind === 'track',
      style: styleFeature,
      onEachFeature: (f, l) => l.bindPopup(popupContent(f))
    }}).addTo(map);
    const extraLayer = L.geoJSON(dataset, {{
      filter: f => f.properties.kind === 'extra',
      style: styleFeature,
      onEachFeature: (f, l) => l.bindPopup(popupContent(f))
    }});
    if (extraLayer.getLayers().length) extraLayer.addTo(map);
    const pointLayer = L.geoJSON(dataset, {{
      filter: f => f.properties.kind === 'point',
      pointToLayer: pointMarker,
      onEachFeature: (f, l) => l.bindPopup(popupContent(f))
    }}).addTo(map);

    map.fitBounds(pointBounds, {{ padding: [18, 18] }});

    const overlays = {{
      'Nomes e localidades sobre imagem': labels,
      {json.dumps(lt_label)}: ltLayer,
      {json.dumps(tracks_label)}: trackLayer,
      {json.dumps(points_label)}: pointLayer
    }};
    if (extraLayer.getLayers().length) overlays[{json.dumps(extra_vectors_label)}] = extraLayer;

    L.control.layers(
      {{
        'Imagem de satélite': imagery,
        'Localidades / ruas': localities
      }},
      overlays,
      {{ collapsed: true }}
    ).addTo(map);

    const Legend = L.Control.extend({{
      options: {{ position: 'bottomleft' }},
      onAdd: function () {{
        const div = L.DomUtil.create('div', 'legend');
        div.innerHTML = `
          <div class="legend-title">Legenda</div>
          <div class="row"><span class="swatch" style="border-color:{html.escape(lt_color)}"></span><span>{html.escape(lt_label)}</span></div>
          <div class="row"><span class="swatch" style="border-color:{html.escape(tracks_color)}"></span><span>{html.escape(tracks_label)}</span></div>
          {extra_legend_row}
          <div class="row"><span class="dot"></span><span>{html.escape(points_label)}</span></div>
        `;
        return div;
      }}
    }});
    map.addControl(new Legend());

    const Reference = L.Control.extend({{
      options: {{ position: 'bottomright' }},
      onAdd: function () {{
        const div = L.DomUtil.create('div', 'reference');
        div.innerHTML = '<div class="reference-title">Mapa de referência</div><div id="overview"></div>';
        L.DomEvent.disableClickPropagation(div);
        setTimeout(initOverview, 0);
        return div;
      }}
    }});
    map.addControl(new Reference());

    function initOverview() {{
      const overview = L.map('overview', {{
        zoomControl: false,
        dragging: false,
        scrollWheelZoom: false,
        doubleClickZoom: false,
        boxZoom: false,
        keyboard: false,
        attributionControl: false
      }});
      L.tileLayer('https://{{s}}.tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png', {{ maxZoom: 12 }}).addTo(overview);
      const overviewLtHalo = L.geoJSON(dataset, {{
        filter: f => f.properties.kind === 'lt',
        style: {{ color: '#ffffff', weight: 7, opacity: 0.9 }}
      }}).addTo(overview);
      const overviewLt = L.geoJSON(dataset, {{
        filter: f => f.properties.kind === 'lt',
        style: {{ color: {json.dumps(lt_color)}, weight: 4, opacity: 1 }}
      }}).addTo(overview);
      L.rectangle(bounds, {{ color: '#17212b', weight: 1, fill: false }}).addTo(overview);
      overview.fitBounds(overviewLt.getBounds().isValid() ? overviewLt.getBounds() : bounds, {{ padding: [8, 8] }});
      overviewLtHalo.bringToFront();
      overviewLt.bringToFront();
    }}
  </script>
</body>
</html>
"""
    OUTPUT.write_text(html_doc, encoding="utf-8")
    result = {"output": str(OUTPUT), "summary": summary, "bounds": map_bounds}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def kml_coords(coords: list[list[float]]) -> str:
    return " ".join(",".join(str(value) for value in coord[:3]) for coord in coords)


def kml_geometry(geometry: dict) -> str:
    geom_type = geometry["type"]
    coords = geometry["coordinates"]
    if geom_type == "Point":
        return f"<Point><coordinates>{kml_coords([coords])}</coordinates></Point>"
    if geom_type == "LineString":
        return f"<LineString><tessellate>1</tessellate><coordinates>{kml_coords(coords)}</coordinates></LineString>"
    if geom_type == "Polygon":
        ring = coords[0]
        if ring and ring[0][:2] != ring[-1][:2]:
            ring = ring + [ring[0]]
        return (
            "<Polygon><outerBoundaryIs><LinearRing><coordinates>"
            f"{kml_coords(ring)}"
            "</coordinates></LinearRing></outerBoundaryIs></Polygon>"
        )
    return ""


def create_kmz(
    map_title: str,
    control_points_csv_url: str,
    tracks_dir: Path | str,
    output_path: Path,
    lt_label: str,
    lt_color: str,
    tracks_label: str,
    tracks_color: str,
    points_label: str,
    extra_vectors_dir: Path | str | None,
    extra_vectors_label: str,
    extra_vectors_color: str,
) -> Path:
    lt, points, tracks, _tracks_for_distance, extras = collect_features(
        control_points_csv_url=control_points_csv_url,
        tracks_dir=tracks_dir,
        lt_label=lt_label,
        tracks_label=tracks_label,
        points_label=points_label,
        extra_vectors_dir=extra_vectors_dir,
        extra_vectors_label=extra_vectors_label,
    )
    features = lt + points + tracks + extras
    style_by_kind = {
        "lt": ("ltStyle", lt_color),
        "track": ("trackStyle", tracks_color),
        "extra": ("extraStyle", extra_vectors_color),
        "point": ("pointStyle", "ffd23f"),
    }
    styles = f"""
      <Style id="ltStyle"><LineStyle><color>{kml_color(lt_color)}</color><width>4</width></LineStyle></Style>
      <Style id="trackStyle"><LineStyle><color>{kml_color(tracks_color)}</color><width>2</width></LineStyle></Style>
      <Style id="extraStyle"><LineStyle><color>{kml_color(extra_vectors_color)}</color><width>2</width></LineStyle><PolyStyle><color>33{kml_color(extra_vectors_color)[2:]}</color></PolyStyle></Style>
      <Style id="pointStyle"><IconStyle><scale>0.8</scale><Icon><href>http://maps.google.com/mapfiles/kml/shapes/placemark_circle.png</href></Icon></IconStyle></Style>
    """
    placemarks = []
    for feature in features:
        properties = feature.get("properties", {})
        style_id = style_by_kind.get(properties.get("kind"), ("extraStyle", extra_vectors_color))[0]
        placemarks.append(
            f"""
      <Placemark>
        <name>{html.escape(str(properties.get("name") or properties.get("layer") or ""))}</name>
        <description>{html.escape(str(properties.get("source") or properties.get("layer") or ""))}</description>
        <styleUrl>#{style_id}</styleUrl>
        {kml_geometry(feature["geometry"])}
      </Placemark>"""
        )
    kml_doc = f"""<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>{html.escape(map_title)}</name>
    {styles}
    {''.join(placemarks)}
  </Document>
</kml>
"""
    output_path.write_bytes(b"")
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("doc.kml", kml_doc.encode("utf-8"))
    return output_path


def kml_color(hex_color: str) -> str:
    clean = hex_color.strip().lstrip("#")
    if len(clean) != 6:
        clean = "333333"
    rr, gg, bb = clean[0:2], clean[2:4], clean[4:6]
    return f"ff{bb}{gg}{rr}"


if __name__ == "__main__":
    main()
