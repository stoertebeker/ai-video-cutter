"""Zeigt je Einstellung den gewaehlten Bildausschnitt im vollen Quellbild.

  python sheet_crop.py <projekt>/cutlist_vN.json

Sobald das Ziel ein anderes Seitenverhaeltnis hat als das Material (Querformat
-> Hochkant), schneidet render.py zu - wohin, sagen crop_x, crop_y und
crop_zoom. Ohne einen Blick aufs Bild waeren diese Zahlen geraten. Der Bogen
zeigt deshalb das ganze Quellbild, den Ausschnitt als Rahmen darin und alles
ausserhalb abgedunkelt. Ergebnis als Bild ansehen und je Szenennummer
nachbessern: "Szene 7 weiter nach links".

Der Frame stammt aus der Mitte der tatsaechlich genutzten Stelle
(in + dauer*tempo/2), nicht aus der Clipmitte - beurteilt wird, was im Film
landet.
"""

import json
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).parent
if len(sys.argv) < 2:
    raise SystemExit("Aufruf: sheet_crop.py <projekt>/cutlist_vN.json")
liste = Path(sys.argv[1])
if not liste.is_absolute():
    liste = ROOT / liste
if not liste.is_file():
    raise SystemExit(f"Schnittliste nicht gefunden: {liste}")

cfg = json.loads(liste.read_text(encoding="utf-8-sig"))
if "quellen" not in cfg:
    raise SystemExit(f"{liste.name}: Feld 'quellen' fehlt (Ordner mit den "
                     f"Quellclips, z.B. \"material/<projekt>\")")
SRC = ROOT / cfg["quellen"]
# nur der letzte Pfadteil, sonst entstuende sheets/material/<projekt>/
PROJEKT = Path(cfg["quellen"]).name
FRAMES = ROOT / "frames" / PROJEKT
SHEETS = ROOT / "sheets" / PROJEKT
FRAMES.mkdir(parents=True, exist_ok=True)
SHEETS.mkdir(parents=True, exist_ok=True)

ZIEL_AR = float(cfg["breite"]) / float(cfg["hoehe"])

TILE_W = 320          # gross genug, dass der Rahmen im Bild lesbar bleibt
LABEL_H = 26
SPALTEN = 4
ZEILEN_JE_BOGEN = 5
RAHMEN = (255, 70, 90)   # kraeftig, damit er auch verkleinert auffaellt
RAHMEN_BREIT = 3
DUNKEL = 3               # Faktor, um den es ausserhalb dunkler wird


def grab(src: Path, t: float, dst: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", str(src),
         "-frames:v", "1", "-vf", f"scale={TILE_W}:-2", str(dst)],
        check=True,
    )


kacheln = []
for s in cfg["shots"]:
    clip = SRC / s["clip"]
    if not clip.is_file():
        print(f"Shot {s['n']}: Datei fehlt: {s['clip']}", file=sys.stderr)
        continue
    tempo = float(s.get("tempo", 1.0))
    # Mitte der genutzten Stelle; bei Zeitlupe ist die kuerzer als die
    # Einstellung spaeter lang ist (verbraucht = dauer * tempo).
    t = s["in"] + s["dauer"] * tempo / 2
    dst = FRAMES / f"crop_{liste.stem}_{s['n']:02d}.png"
    grab(clip, t, dst)
    kacheln.append((s, dst))
    print(f"Shot {s['n']}: {s['clip']} @ {t:.2f}s", file=sys.stderr)

if not kacheln:
    raise SystemExit("Keine Frames gezogen - keine der Quelldateien gefunden.")

tile_h = Image.open(kacheln[0][1]).height
row_h = tile_h + LABEL_H
je_bogen = SPALTEN * ZEILEN_JE_BOGEN

for b, start in enumerate(range(0, len(kacheln), je_bogen), start=1):
    teil = kacheln[start:start + je_bogen]
    zeilen = (len(teil) + SPALTEN - 1) // SPALTEN
    sheet = Image.new("RGB", (TILE_W * SPALTEN, row_h * zeilen), (18, 18, 22))
    d = ImageDraw.Draw(sheet)

    for i, (s, pfad) in enumerate(teil):
        x0 = (i % SPALTEN) * TILE_W
        y0 = (i // SPALTEN) * row_h
        bild = Image.open(pfad).convert("RGB")
        w, h = bild.size

        crop_x = float(s.get("crop_x", 0.5))
        crop_y = float(s.get("crop_y", 0.5))
        zoom = float(s.get("crop_zoom", 1.0))
        # Dieselbe Rechnung wie in render.py, nur in Kachelkoordinaten - die
        # Werte sind relativ, deshalb gilt sie unabhaengig von der Groesse.
        cw = min(w, h * ZIEL_AR) / zoom
        ch = min(h, w / ZIEL_AR) / zoom
        cx = (w - cw) * crop_x
        cy = (h - ch) * crop_y
        kasten = (int(cx), int(cy), int(cx + cw), int(cy + ch))

        # Aussen abdunkeln, damit der Ausschnitt sofort ins Auge faellt.
        gedimmt = Image.eval(bild, lambda v: v // DUNKEL)
        gedimmt.paste(bild.crop(kasten), kasten[:2])
        sheet.paste(gedimmt, (x0, y0 + LABEL_H))
        d.rectangle(
            [x0 + kasten[0], y0 + LABEL_H + kasten[1],
             x0 + kasten[2] - 1, y0 + LABEL_H + kasten[3] - 1],
            outline=RAHMEN, width=RAHMEN_BREIT,
        )

        zusatz = ""
        if crop_y != 0.5:
            zusatz += f"  y={crop_y:g}"
        if zoom != 1.0:
            zusatz += f"  zoom={zoom:g}"
        d.text((x0 + 4, y0 + 2), f"{s['n']:02d}  {Path(s['clip']).stem[:20]}",
               fill=(255, 220, 120))
        d.text((x0 + 4, y0 + 13), f"crop_x={crop_x:g}{zusatz}",
               fill=(140, 200, 255))

    out = SHEETS / f"crop_{liste.stem}_{b}.png"
    sheet.save(out)
    print(f"geschrieben: {out}  ({sheet.width}x{sheet.height})", file=sys.stderr)
