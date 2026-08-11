"""Zieht je einen Frame kurz vor und kurz nach jedem Schnitt.

  python verify_cuts.py <schnittliste.json>

Faengt vertauschte Clips und falsche Einstiegszeitpunkte. Wichtig ist der
Abstand zum Schnitt: Bei 25 fps ist ein Frame 0.04s, dazu kommt die
Quantisierung der Segmentlaengen. Unter etwa 0.15s Abstand erwischt man die
falsche Seite und diagnostiziert einen Fehler, der nicht existiert.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
if len(sys.argv) < 2:
    raise SystemExit(__doc__)
liste = Path(sys.argv[1])
if not liste.is_absolute():
    liste = ROOT / liste

cfg = json.loads(liste.read_text(encoding="utf-8-sig"))
VID = ROOT / cfg["ausgabe"]
# nur der letzte Pfadteil, sonst entstuende verify/material/<projekt>/
PROJEKT = Path(cfg.get("quellen", "projekt")).name
TMP = ROOT / "verify" / PROJEKT
TMP.mkdir(parents=True, exist_ok=True)
(ROOT / "sheets" / PROJEKT).mkdir(parents=True, exist_ok=True)

TILE_W = 200
LABEL_H = 20
ABSTAND = 0.18  # Sekunden vor/nach dem Schnitt - siehe Docstring

shots = cfg["shots"]
rows = []
for i, s in enumerate(shots[1:], start=2):
    t = s["schnitt_bei"]
    paar = []
    for tag, tt in (("vor", t - ABSTAND), ("nach", t + ABSTAND)):
        dst = TMP / f"{liste.stem}_cut{i:02d}_{tag}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{tt:.3f}",
             "-i", str(VID), "-frames:v", "1", "-vf", f"scale={TILE_W}:-2",
             str(dst)],
            check=True,
        )
        paar.append((dst, tag, tt))
    rows.append((i, t, s, paar))

tile_h = Image.open(rows[0][3][0][0]).height
row_h = tile_h + LABEL_H
sheet = Image.new("RGB", (TILE_W * 2 + 8, row_h * len(rows)), (18, 18, 22))
d = ImageDraw.Draw(sheet)

for r, (n, t, s, paar) in enumerate(rows):
    y = r * row_h
    kurz = Path(s["clip"]).stem[:18]
    d.text((6, y + 4), f"Schnitt {n - 1}->{n} bei {t:.3f}s  -> {kurz}",
           fill=(255, 220, 120))
    for c, (pfad, tag, tt) in enumerate(paar):
        sheet.paste(Image.open(pfad), (c * (TILE_W + 8), y + LABEL_H))
        d.text((c * (TILE_W + 8) + 5, y + LABEL_H + 3), f"{tag} {tt:.2f}s",
               fill=(120, 255, 200))

out = ROOT / "sheets" / PROJEKT / f"schnitte_{liste.stem}.png"
sheet.save(out)
print(f"{out} ({sheet.width}x{sheet.height})")
