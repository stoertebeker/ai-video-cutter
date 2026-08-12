"""Zieht je Clip mehrere Frames und baut beschriftete Kontaktbogen.

  python make_contactsheets.py <quellordner> [frames_je_clip] [clips_je_bogen] [filter]

`filter` waehlt Clips ueber ein Namensfragment, z.B. "134" fuer 1340-1349.
Mehr Frames je Clip zeigen die Bewegung innerhalb einer Einstellung - wichtig,
um zu beurteilen, wo ein Schwenk anfaengt und wo er aus dem Motiv laeuft.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
if len(sys.argv) < 2:
    raise SystemExit(__doc__)
SRC = ROOT / sys.argv[1]
# Abgeleitetes je Projekt trennen, damit sich mehrere Projekte im selben
# Ordner nicht in die Quere kommen.
OUT = ROOT / "frames" / SRC.name
SHEETS = ROOT / "sheets" / SRC.name

FRAMES_PER_CLIP = int(sys.argv[2]) if len(sys.argv) > 2 else 3
CLIPS_PER_SHEET = int(sys.argv[3]) if len(sys.argv) > 3 else 5
FILTER = sys.argv[4] if len(sys.argv) > 4 else ""

TILE_W = max(90, int(1000 / FRAMES_PER_CLIP))
LABEL_H = 22

OUT.mkdir(parents=True, exist_ok=True)
SHEETS.mkdir(parents=True, exist_ok=True)


def duration(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(p)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def grab(src: Path, t: float, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"scale={TILE_W}:-2", str(dst)],
        check=True,
    )


VIDEO = {".mp4", ".mov", ".mts", ".mkv", ".avi"}
clips = sorted(
    p for p in SRC.iterdir()
    if p.is_file() and p.suffix.lower() in VIDEO and FILTER in p.name
)
if not clips:
    raise SystemExit(f"Keine Clips in {SRC} passend zu '{FILTER}'")

rows = []
for clip in clips:
    dur = duration(clip)
    name = clip.stem
    tiles = []
    for i in range(FRAMES_PER_CLIP):
        # gleichmaessig verteilt, aber nicht ganz am Rand
        frac = (i + 0.5) / FRAMES_PER_CLIP
        t = dur * frac
        dst = OUT / f"{name}_n{FRAMES_PER_CLIP}_{i}.png"
        if not dst.exists():
            grab(clip, t, dst)
        tiles.append((dst, t))
    rows.append((name, dur, tiles))
    print(f"{name}: {dur:.2f}s -> {len(tiles)} Frames", file=sys.stderr)

tile_h = Image.open(rows[0][2][0][0]).height
row_h = tile_h + LABEL_H
sheet_w = TILE_W * FRAMES_PER_CLIP

marke = f"_{FILTER}" if FILTER else ""
for s in range(0, len(rows), CLIPS_PER_SHEET):
    chunk = rows[s:s + CLIPS_PER_SHEET]
    sheet = Image.new("RGB", (sheet_w, row_h * len(chunk)), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    for r, (name, dur, tiles) in enumerate(chunk):
        y = r * row_h
        d.text((6, y + 5), f"{name}   {dur:.2f}s", fill=(255, 220, 120))
        for c, (path, t) in enumerate(tiles):
            sheet.paste(Image.open(path), (c * TILE_W, y + LABEL_H))
            d.text((c * TILE_W + 5, y + LABEL_H + 3), f"{t:.1f}s", fill=(120, 255, 200))
    out = SHEETS / f"dicht{marke}_{s // CLIPS_PER_SHEET + 1}.png"
    sheet.save(out)
    print(f"geschrieben: {out}  ({sheet.width}x{sheet.height})", file=sys.stderr)
