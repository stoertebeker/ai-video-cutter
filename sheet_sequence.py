"""Baut aus dem fertigen Video einen Kontaktbogen: ein Frame je Einstellung.

Zeigt die Abfolge auf einen Blick und deckt vertauschte oder falsch
angesetzte Clips auf.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
if len(sys.argv) < 2:
    raise SystemExit("Aufruf: sheet_sequence.py <projekt>/cutlist_vN.json")
liste = Path(sys.argv[1])
if not liste.is_absolute():
    liste = ROOT / liste
if not liste.is_file():
    raise SystemExit(f"Schnittliste nicht gefunden: {liste}")

cfg = json.loads(liste.read_text(encoding="utf-8-sig"))
VID = ROOT / cfg["ausgabe"]
# nur der letzte Pfadteil, sonst entstuende sheets/material/<projekt>/
PROJEKT = Path(cfg.get("quellen", "projekt")).name
TMP = ROOT / "verify" / PROJEKT
TMP.mkdir(parents=True, exist_ok=True)
(ROOT / "sheets" / PROJEKT).mkdir(parents=True, exist_ok=True)

TILE_W = 150
LABEL_H = 26
SPALTEN = 6

kacheln = []
for s in cfg["shots"]:
    # Mitte der Einstellung, damit kein Uebergangsframe erwischt wird
    t = s["schnitt_bei"] + s["dauer"] / 2
    dst = TMP / f"seq_{liste.stem}_{s['n']:02d}.png"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(VID),
         "-frames:v", "1", "-vf", f"scale={TILE_W}:-2", str(dst)],
        check=True,
    )
    kacheln.append((s, dst, t))

tile_h = Image.open(kacheln[0][1]).height
zeilen = (len(kacheln) + SPALTEN - 1) // SPALTEN
sheet = Image.new("RGB", (TILE_W * SPALTEN, (tile_h + LABEL_H) * zeilen), (18, 18, 22))
d = ImageDraw.Draw(sheet)

for i, (s, pfad, t) in enumerate(kacheln):
    x = (i % SPALTEN) * TILE_W
    y = (i // SPALTEN) * (tile_h + LABEL_H)
    kurz = s["clip"].split("_")[0].replace("5V4A", "")
    d.text((x + 4, y + 2), f"{s['n']:02d}  {kurz}", fill=(255, 220, 120))
    d.text((x + 4, y + 13), f"{t:.1f}s  {s['dauer']:.2f}s", fill=(140, 200, 255))
    sheet.paste(Image.open(pfad), (x, y + LABEL_H))

out = ROOT / "sheets" / PROJEKT / f"sequenz_{liste.stem}.png"
sheet.save(out)
print(f"{out} ({sheet.width}x{sheet.height})")
