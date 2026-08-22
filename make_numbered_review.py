"""Erzeugt eine nummerierte Review-Kopie aus einer gerenderten Schnittliste.

Die Nummern werden als ASS-Untertitel framegenau aus den Shotgrenzen der
Schnittliste abgeleitet. Die vorhandene Ausgabe bleibt unveraendert; nur das
Bild der Review-Kopie wird neu kodiert, die Audiospur wird kopiert.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

import encoder


ROOT = Path(__file__).parent


def ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, rest = divmod(centiseconds, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


parser = argparse.ArgumentParser(description="Erzeugt eine nummerierte Review-Kopie.")
parser.add_argument("cutlist")
parser.add_argument("ausgabe", nargs="?")
parser.add_argument(
    "--source",
    help="Bereits betitelte/weiterverarbeitete Quelle statt cfg.ausgabe",
)
args = parser.parse_args()

cutlist = Path(args.cutlist)
if not cutlist.is_absolute():
    cutlist = ROOT / cutlist

cfg = json.loads(cutlist.read_text(encoding="utf-8-sig"))
source = Path(args.source) if args.source else ROOT / cfg["ausgabe"]
if not source.is_absolute():
    source = ROOT / source
if not source.exists():
    raise SystemExit(f"Gerenderte Arbeitsfassung fehlt: {source}")

if args.ausgabe:
    output = Path(args.ausgabe)
    if not output.is_absolute():
        output = ROOT / output
else:
    output = source.with_name(f"{source.stem}_nummeriert{source.suffix}")
output.parent.mkdir(parents=True, exist_ok=True)

ass_file = ROOT / "sheets" / f"review_numbers_{cutlist.stem}.ass"
ass_file.parent.mkdir(parents=True, exist_ok=True)

# Bezugsaufloesung aus der Schnittliste, nicht festverdrahtet - sonst sitzen
# die Zahlen bei hochkantem Material falsch.
header = f"""[Script Info]
Title: Fortlaufende Szenennummern
ScriptType: v4.00+
PlayResX: {int(cfg["breite"])}
PlayResY: {int(cfg["hoehe"])}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: SceneNumber,Arial,96,&H0000FFFF,&H0000FFFF,&H90000000,&H90000000,-1,0,0,0,100,100,0,0,3,6,0,3,40,60,50,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

events = []
shots = cfg["shots"]
for index, shot in enumerate(shots):
    start = float(shot["schnitt_bei"])
    end = (float(shots[index + 1]["schnitt_bei"])
           if index + 1 < len(shots) else float(cfg["ende_s"]))
    events.append(
        f"Dialogue: 0,{ass_time(start)},{ass_time(end)},SceneNumber,,0,0,0,,{shot['n']}"
    )

ass_file.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")

# Relativer Pfad vermeidet das zu escapende Laufwerkskolon in ffmpegs
# Filtersyntax. Vorwaertsschranke funktionieren auch unter Windows.
ass_relative = ass_file.relative_to(ROOT).as_posix()
cmd = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(source),
    "-vf", f"ass=filename='{ass_relative}'",
    "-map", "0:v:0", "-map", "0:a?",
    *encoder.video_args(),
    "-pix_fmt", "yuv420p",
    "-c:a", "copy",
    "-movflags", "+faststart",
    str(output),
]
subprocess.run(cmd, cwd=ROOT, check=True)
print(output)
