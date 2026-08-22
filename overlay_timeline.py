"""Zeitgesteuerte Bild-Overlays fuer Vlogs.

Die Timeline ist absichtlich generisch: Heute erzeugt sie eine GPX-Minikarte,
spaeter kann dieselbe Liste Fotos oder andere PNG/JPEG-Einblendungen tragen.
Projektwerte stehen in der Schnittliste; die Quelldateien bleiben unangetastet.
"""

from __future__ import annotations

import bisect
import math
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


DEFAULT_DURATION_S = 4.0
DEFAULT_FADE_IN_S = 0.18
DEFAULT_FADE_OUT_S = 0.22
CARD_WIDTH = 560
CARD_HEIGHT = 260
MARGIN = 48


def entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    value = config.get("overlays", [])
    return value if isinstance(value, list) else []


def _time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Zeitzone fehlt")
    return parsed.astimezone(timezone.utc)


def _haversine(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1 = map(math.radians, a)
    lat2, lon2 = map(math.radians, b)
    dlat, dlon = lat2 - lat1, lon2 - lon1
    h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(h))


def read_gpx(path: Path) -> list[tuple[datetime, float, float, float]]:
    """Liest Zeit, Position und kumulierte Distanz aus einem GPX-Track."""
    root = ET.parse(path).getroot()
    raw: list[tuple[datetime, float, float]] = []
    for point in root.iter():
        if not point.tag.endswith("trkpt"):
            continue
        time_node = next((child for child in point if child.tag.endswith("time")), None)
        if time_node is None or not time_node.text:
            continue
        raw.append((_time(time_node.text), float(point.attrib["lat"]), float(point.attrib["lon"])))
    if len(raw) < 2:
        raise ValueError("GPX enthaelt weniger als zwei zeitgestempelte Trackpunkte")
    raw.sort(key=lambda item: item[0])
    result: list[tuple[datetime, float, float, float]] = []
    distance = 0.0
    for index, (stamp, lat, lon) in enumerate(raw):
        if index:
            distance += _haversine((raw[index - 1][1], raw[index - 1][2]), (lat, lon))
        result.append((stamp, lat, lon, distance))
    return result


def progress_at(
    points: list[tuple[datetime, float, float, float]], stamp: datetime
) -> tuple[float, float, float, list[tuple[float, float]]]:
    """Interpoliert Distanz/Position und liefert die bis dahin gelaufene Linie."""
    times = [point[0] for point in points]
    index = bisect.bisect_left(times, stamp)
    if index == 0 and stamp < times[0] or index == len(points):
        raise ValueError("Zeit liegt ausserhalb des GPX-Tracks")
    if index == 0:
        lat, lon, distance = points[0][1:]
        return lat, lon, distance, [(lat, lon)]
    before, after = points[index - 1], points[index]
    span = (after[0] - before[0]).total_seconds()
    fraction = 0.0 if span <= 0 else (stamp - before[0]).total_seconds() / span
    lat = before[1] + (after[1] - before[1]) * fraction
    lon = before[2] + (after[2] - before[2]) * fraction
    distance = before[3] + (after[3] - before[3]) * fraction
    travelled = [(point[1], point[2]) for point in points[:index]]
    travelled.append((lat, lon))
    return lat, lon, distance, travelled


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def _project(points: list[tuple[float, float]], box: tuple[int, int, int, int]) -> list[tuple[int, int]]:
    left, top, right, bottom = box
    latitudes = [point[0] for point in points]
    mean_lat = math.radians(sum(latitudes) / len(latitudes))
    xy = [(lon * math.cos(mean_lat), lat) for lat, lon in points]
    xs, ys = zip(*xy)
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    scale = min((right - left) / span_x, (bottom - top) / span_y)
    offset_x = left + ((right - left) - span_x * scale) / 2
    offset_y = top + ((bottom - top) - span_y * scale) / 2
    return [
        (round(offset_x + (x - min_x) * scale), round(offset_y + (max_y - y) * scale))
        for x, y in xy
    ]


def route_card(gpx: Path, stamp: datetime, output: Path) -> tuple[float, float]:
    """Erzeugt transparente Minikarte; Rueckgabe: Stunden und Kilometer."""
    points = read_gpx(gpx)
    lat, lon, distance, travelled = progress_at(points, stamp)
    elapsed = (stamp - points[0][0]).total_seconds() / 3600

    image = Image.new("RGBA", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((0, 0, CARD_WIDTH - 1, CARD_HEIGHT - 1), radius=24,
                           fill=(12, 18, 22, 218), outline=(255, 255, 255, 55), width=2)
    map_box = (28, 24, 295, CARD_HEIGHT - 24)
    route = [(point[1], point[2]) for point in points]
    route_xy = _project(route, map_box)
    travelled_xy = _project(route, map_box)[:0]
    # Fuer beide Linien muss dieselbe Projektion gelten; Positionen der
    # Teilstrecke deshalb ueber die Extents der Gesamtroute abbilden.
    combined = _project(route + travelled, map_box)
    route_xy = combined[:len(route)]
    travelled_xy = combined[len(route):]
    draw.line(route_xy, fill=(150, 160, 166, 190), width=5, joint="curve")
    if len(travelled_xy) > 1:
        draw.line(travelled_xy, fill=(42, 190, 176, 255), width=7, joint="curve")
    if travelled_xy:
        x, y = travelled_xy[-1]
        draw.ellipse((x - 9, y - 9, x + 9, y + 9), fill=(255, 205, 64, 255),
                     outline=(255, 255, 255, 255), width=3)

    small = _font(24)
    large = _font(43, bold=True)
    text_x = 330
    draw.text((text_x, 45), "SEIT START", font=small, fill=(190, 202, 208, 255))
    hours = int(elapsed)
    minutes = int(round((elapsed - hours) * 60))
    if minutes == 60:
        hours, minutes = hours + 1, 0
    draw.text((text_x, 76), f"{hours:02d}:{minutes:02d} h", font=large, fill="white")
    draw.text((text_x, 152), "STRECKE", font=small, fill=(190, 202, 208, 255))
    draw.text((text_x, 181), f"{distance / 1000:.1f} km", font=large, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)
    return elapsed, distance / 1000


def prepare(
    config: dict[str, Any], root: Path, asset_dir: Path, first_input: int,
    width: int, height: int,
) -> tuple[list[str], str]:
    """Erzeugt Assets, ffmpeg-Eingaenge und Videofilter bis Ergebnis ``[v]``."""
    overlays = entries(config)
    if not overlays:
        return [], ""
    if asset_dir.exists():
        shutil.rmtree(asset_dir)
    asset_dir.mkdir(parents=True)
    args: list[str] = []
    filters: list[str] = []
    previous = "video_basis"
    for index, item in enumerate(overlays):
        kind = item["type"]
        duration = float(item.get("dauer", DEFAULT_DURATION_S))
        start = float(item["schnitt_bei"])
        fade_in = float(item.get("fade_in_s", DEFAULT_FADE_IN_S))
        fade_out = float(item.get("fade_out_s", DEFAULT_FADE_OUT_S))
        if kind == "route_progress":
            source = asset_dir / f"route_{int(item['n']):03d}.png"
            route_card(root / config["gpx"], _time(item["zeit"]), source)
        else:
            source = root / item["datei"]
        args.extend(["-loop", "1", "-t", f"{duration:.6f}", "-i", str(source)])
        input_index = first_input + index
        label = f"overlay_asset_{index}"
        chain = ["format=rgba"]
        if kind == "image" and "breite" in item:
            chain.append(f"scale={int(item['breite'])}:-2:flags=lanczos")
        if fade_in:
            chain.append(f"fade=t=in:st=0:d={fade_in:.6f}:alpha=1")
        if fade_out:
            chain.append(f"fade=t=out:st={duration - fade_out:.6f}:d={fade_out:.6f}:alpha=1")
        chain.append(f"setpts=PTS-STARTPTS+{start:.6f}/TB")
        filters.append(f"[{input_index}:v]" + ",".join(chain) + f"[{label}]")

        position = item.get("position", "bottom_right")
        if "x" in item and "y" in item:
            x, y = str(int(item["x"])), str(int(item["y"]))
        elif position == "bottom_left":
            x, y = str(MARGIN), f"H-h-{MARGIN}"
        elif position == "top_left":
            x, y = str(MARGIN), str(MARGIN)
        elif position == "top_right":
            x, y = f"W-w-{MARGIN}", str(MARGIN)
        else:
            x, y = f"W-w-{MARGIN}", f"H-h-{MARGIN}"
        result = "v" if index == len(overlays) - 1 else f"video_overlay_{index}"
        filters.append(
            f"[{previous}][{label}]overlay=x={x}:y={y}:"
            f"enable='between(t,{start:.6f},{start + duration:.6f})':"
            f"eof_action=pass[{result}]"
        )
        previous = result
    return args, ";".join(filters)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(config: dict[str, Any], root: Path, duration: float) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    hints: list[str] = []
    raw = config.get("overlays")
    if raw is None:
        return errors, hints
    if not isinstance(raw, list):
        return ["Feld overlays muss eine Liste sein"], hints
    numbers: list[int] = []
    gpx_points = None
    gpx_path = root / str(config.get("gpx", ""))
    for index, item in enumerate(raw, start=1):
        label = f"Overlay {index}"
        if not isinstance(item, dict):
            errors.append(f"{label}: Eintrag muss ein Objekt sein")
            continue
        missing = [field for field in ("n", "type", "schnitt_bei") if field not in item]
        if missing:
            errors.append(f"{label}: Pflichtfelder fehlen: {', '.join(missing)}")
            continue
        if isinstance(item["n"], int) and not isinstance(item["n"], bool):
            numbers.append(item["n"])
            label = f"Overlay {item['n']}"
        else:
            errors.append(f"{label}: n muss eine ganze Zahl sein")
        kind = item["type"]
        if kind not in ("route_progress", "image"):
            errors.append(f"{label}: type muss route_progress oder image sein")
            continue
        start = item["schnitt_bei"]
        item_duration = item.get("dauer", DEFAULT_DURATION_S)
        if not _number(start) or not _number(item_duration) or float(item_duration) <= 0:
            errors.append(f"{label}: schnitt_bei/dauer muessen gueltige Zahlen sein")
            continue
        if float(start) < 0 or float(start) + float(item_duration) > duration + 0.001:
            errors.append(f"{label}: liegt ausserhalb der Filmdauer")
        fade_in = item.get("fade_in_s", DEFAULT_FADE_IN_S)
        fade_out = item.get("fade_out_s", DEFAULT_FADE_OUT_S)
        if not _number(fade_in) or not _number(fade_out) or float(fade_in) < 0 or float(fade_out) < 0:
            errors.append(f"{label}: Fadezeiten muessen nichtnegative Zahlen sein")
        elif float(fade_in) + float(fade_out) > float(item_duration):
            errors.append(f"{label}: Fadezeiten sind zusammen laenger als das Overlay")
        if kind == "route_progress":
            if "gpx" not in config or not gpx_path.is_file():
                errors.append(f"{label}: GPX-Datei fehlt: {gpx_path}")
            elif "zeit" not in item:
                errors.append(f"{label}: zeit fehlt")
            else:
                try:
                    gpx_points = gpx_points or read_gpx(gpx_path)
                    progress_at(gpx_points, _time(item["zeit"]))
                except (ValueError, ET.ParseError) as exc:
                    errors.append(f"{label}: {exc}")
        else:
            if "datei" not in item or not (root / str(item.get("datei", ""))).is_file():
                errors.append(f"{label}: Bilddatei fehlt: {item.get('datei', '')}")
            if "breite" in item and (not isinstance(item["breite"], int) or item["breite"] <= 0):
                errors.append(f"{label}: breite muss eine positive ganze Zahl sein")
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        errors.append(f"Overlay-Nummern doppelt vergeben: {duplicates}")
    return errors, hints
