"""Backt die Zeitlupen-Einstellungen einer Schnittliste zu Zwischenclips fuer
DaVinci Resolve.

Warum das noetig ist: Resolves Scripting-API hat keine dokumentierte
Moeglichkeit, die Geschwindigkeit eines Timeline-Clips zu setzen (siehe
CLAUDE.md, Abschnitt "Export nach DaVinci Resolve" - README.txt der
Resolve-API kennt "RetimeProcess" [nur die Interpolationsart], aber keinen
"Speed"-Schluessel fuer TimelineItem.SetProperty, und CHANGELOG.txt erwaehnt
so etwas nie). Ausserdem laeuft die Resolve-Timeline in Quell-Framerate (50),
damit fehlt der Framerate-Unterschied (Quelle 50 / Render-Timeline 25), den
render.py fuer Zeitlupe ohne Bildwiederholung ausnutzt - bei 50fps-Timeline
und 50fps-Quelle gibt es dafuer keinen "kostenlosen" Trick mehr.

Der Ausweg: die Zeitlupe wird hier per ffmpeg vorgerechnet, genau wie in
render.py (setpts VOR fps, -ss/-t VOR -i), aber mit Ziel-Framerate = Quell-
Framerate (50 statt 25) und ohne Skalierung - volle Aufloesung, damit in
Resolve noch sinnvoll farbkorrigiert werden kann. Ergebnis ist ein
ProRes-Zwischenclip, in dem jede Zeitlupen-Einstellung bereits mit der
richtigen Bildzahl vorliegt. resolve_build.py haengt ihn dann mit Tempo 1.0
in die Timeline - keine Geschwindigkeitsaenderung in Resolve noetig.

Normale (nicht verlangsamte) Einstellungen brauchen das nicht: die werden von
resolve_build.py direkt aus dem Original gelesen, inklusive Originalton (den
Zeitlupen-Zwischenclips fehlt der Ton bewusst, siehe unten).

Aufruf:
    .venv\\Scripts\\python.exe resolve_prep_slowmo.py <projekt>/cutlist_vN.json

Erzeugt <projekt>/../resolve_zwischen/<cutlist-name>/shot_NN_<clip>.mov fuer
jede Einstellung mit tempo != 1.0. Der Ordner wird bei jedem Lauf komplett neu
geschrieben (wie segments/<fassung>/) - reiner Zwischenstand, jederzeit
loeschbar und aus der Schnittliste neu erzeugbar.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

# ProRes-Profil fuer die Zwischenclips: 0=Proxy, 1=LT, 2=422 Standard,
# 3=422 HQ. HQ ist Standard und braucht viel Platz - bei 4K-Material einige
# GB je Minute Zeitlupe. Bei Platzmangel auf 2 (etwa zwei Drittel der Groesse)
# oder 0 (deutlich kleiner, aber sichtbar weicher) stellen.
PRORES_PROFIL = 3

ROOT = Path(__file__).parent
CUTLIST = Path(sys.argv[1]) if len(sys.argv) > 1 else None
if CUTLIST is None:
    raise SystemExit("Aufruf: resolve_prep_slowmo.py <projekt>/cutlist_vN.json")
if not CUTLIST.is_absolute():
    CUTLIST = ROOT / CUTLIST

cfg = json.loads(CUTLIST.read_text(encoding="utf-8-sig"))
if "quellen" not in cfg:
    raise SystemExit(f"{CUTLIST.name}: Feld 'quellen' fehlt")
SRC = ROOT / cfg["quellen"]
QUELL_FPS = float(cfg["quell_fps"])
ENDE = float(cfg["ende_s"])
shots = cfg["shots"]

OUT = ROOT / "resolve_zwischen" / CUTLIST.stem
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)


def run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(args), file=sys.stderr)
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"ffmpeg-Fehler ({r.returncode})")


def zaehle_frames(pfad: Path) -> int:
    """Zaehlt tatsaechlich decodierte Frames - keine Vermutung ueber
    Container-Metadaten, sondern gemessen."""
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0",
         "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(pfad)],
        capture_output=True, text=True, check=True,
    )
    return int(r.stdout.strip())


fehler = []
gebaut = 0
uebersprungen = 0

for idx, s in enumerate(shots):
    tempo = float(s.get("tempo", 1.0))
    timeline_start = float(s["schnitt_bei"])
    timeline_end = (float(shots[idx + 1]["schnitt_bei"])
                    if idx + 1 < len(shots) else ENDE)
    start_frame = int(timeline_start * QUELL_FPS + 0.5)
    end_frame = int(timeline_end * QUELL_FPS + 0.5)
    frames = end_frame - start_frame
    if frames <= 0:
        fehler.append(f"Shot {s['n']}: ungueltige Framedauer ({start_frame} bis {end_frame})")
        continue

    if abs(tempo - 1.0) < 1e-9:
        uebersprungen += 1
        continue

    src = SRC / s["clip"]
    if not src.exists():
        fehler.append(f"Shot {s['n']}: Quelldatei fehlt: {s['clip']}")
        continue

    timeline_duration = frames / QUELL_FPS
    quelle = timeline_duration * tempo  # verbrauchte Quellzeit, wie render.py
    dst = OUT / f"shot_{s['n']:02d}_{Path(s['clip']).stem}.mov"

    # Gleiche Kette wie render.py: setpts vor fps, -ss/-t vor -i. Ziel-fps ist
    # hier die Quell-Framerate (Resolve-Timeline), nicht die Render-Framerate.
    # Keine Skalierung - volle Aufloesung fuer die Farbkorrektur in Resolve.
    vf = f"setpts=PTS/{tempo},fps={QUELL_FPS:g}"
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{s['in']:.3f}", "-t", f"{quelle:.3f}", "-i", str(src),
        "-vf", vf,
        "-frames:v", str(frames),
        "-an",  # kein Ton - verlangsamter Ton waere tonhoehenverschoben
        "-c:v", "prores_ks", "-profile:v", str(PRORES_PROFIL), "-pix_fmt", "yuv422p10le",
        str(dst),
    ])

    gemessen = zaehle_frames(dst)
    status = "OK" if gemessen == frames else "FEHLER"
    if gemessen != frames:
        fehler.append(
            f"Shot {s['n']} {dst.name}: erwartet {frames} Frames, gemessen {gemessen}"
        )
    print(f"Shot {s['n']:2d} {s['clip']:28s} tempo={tempo:g}  "
          f"Quelle {s['in']:.2f}-{s['in']+quelle:.2f}s -> {frames} Frames "
          f"@ {QUELL_FPS:g}fps  [{status}]", file=sys.stderr)
    gebaut += 1

print(f"\n{gebaut} Zeitlupen-Zwischenclips in {OUT}", file=sys.stderr)
print(f"{uebersprungen} Einstellungen ohne Zeitlupe - werden direkt aus dem "
      f"Original gelesen (resolve_build.py).", file=sys.stderr)
for f in fehler:
    print(f"  FEHLER: {f}", file=sys.stderr)
print("OK" if not fehler else "NICHT OK", file=sys.stderr)
sys.exit(1 if fehler else 0)
