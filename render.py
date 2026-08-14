"""Rendert den Teaser aus cutlist.json: Segmente schneiden, concat, Musik drunter."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import encoder

ROOT = Path(__file__).parent
# Schnittliste als Pflichtargument - so koennen mehrere Fassungen eines
# Projekts nebeneinander bestehen.
if len(sys.argv) < 2:
    raise SystemExit("Aufruf: render.py <projekt>/cutlist_vN.json")
CUTLIST = Path(sys.argv[1])
if not CUTLIST.is_absolute():
    CUTLIST = ROOT / CUTLIST
if not CUTLIST.is_file():
    raise SystemExit(f"Schnittliste nicht gefunden: {CUTLIST}")
# Eigener Segmentordner je Fassung, sonst ueberschreiben sie sich gegenseitig.
SEG = ROOT / "segments" / CUTLIST.stem

cfg = json.loads(CUTLIST.read_text(encoding="utf-8-sig"))
if "quellen" not in cfg:
    raise SystemExit(f"{CUTLIST.name}: Feld 'quellen' fehlt (Ordner mit den "
                     f"Quellclips, z.B. \"material/<projekt>\")")
SRC = ROOT / cfg["quellen"]
W, H, FPS = cfg["breite"], cfg["hoehe"], cfg["fps"]
ende = float(cfg["ende_s"])
fade = float(cfg["video_ausblende_s"])
fade_in = float(cfg.get("video_einblende_s", 0.0))

if SEG.exists():
    shutil.rmtree(SEG)
SEG.mkdir(parents=True)

out = ROOT / cfg["ausgabe"]
out.parent.mkdir(exist_ok=True)


def run(args: list[str]) -> None:
    r = subprocess.run(args, capture_output=True, text=True)
    if r.returncode != 0:
        print(" ".join(args), file=sys.stderr)
        print(r.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"ffmpeg-Fehler ({r.returncode})")


# 1) Jedes Segment einzeln und identisch kodieren
seg_files = []
shots = cfg["shots"]
for idx, s in enumerate(shots):
    src = SRC / s["clip"]
    dst = SEG / f"seg_{s['n']:02d}.mp4"
    # tempo 0.5 = halbe Geschwindigkeit. Das Quellmaterial hat 50 fps, die
    # Timeline 25 - bei 0.5 wird also aus jedem Quellframe genau ein
    # Ausgabeframe. Echte Zeitlupe, nichts interpoliert.
    tempo = float(s.get("tempo", 1.0))
    # Jeder Schnitt wird zuerst auf seine absolute Position im Ausgabe-
    # Frameraster gerundet. Wuerde stattdessen jede einzelne Shot-Dauer
    # gerundet, addierten sich die Teilfehler bis zum Filmende und spaete
    # Musikmarken koennten um mehrere Frames verfehlt werden.
    timeline_start = float(s["schnitt_bei"])
    timeline_end = (float(shots[idx + 1]["schnitt_bei"])
                    if idx + 1 < len(shots) else ende)
    start_frame = int(timeline_start * FPS + 0.5)
    end_frame = int(timeline_end * FPS + 0.5)
    frames = end_frame - start_frame
    if frames <= 0:
        raise SystemExit(
            f"Ungueltige Framedauer bei Shot {s['n']}: "
            f"Frame {start_frame} bis {end_frame}"
        )
    timeline_duration = frames / FPS
    quelle = timeline_duration * tempo    # so viel Material wird verbraucht
    # Bildausschnitt vor der Skalierung. Noetig, sobald Quell- und
    # Zielseitenverhaeltnis auseinanderfallen (Querformat -> Hochkant): scale
    # allein wuerde dann verzerren, pad ergaebe ein Briefmarkenbild.
    # crop_x/crop_y sind der Mittelpunkt des Ausschnitts (0 = links/oben,
    # 1 = rechts/unten), crop_zoom 1.0 der groesstmoegliche Ausschnitt im
    # Zielformat. Relative Werte, damit die Schnittliste nicht an einer
    # Quellaufloesung klebt.
    crop_x = float(s.get("crop_x", 0.5))
    crop_y = float(s.get("crop_y", 0.5))
    zoom = float(s.get("crop_zoom", 1.0))
    # Gerechnet wird in ffmpegs eigenen Variablen iw/ih statt per ffprobe -
    # das spart einen Prozessaufruf je Segment und bleibt auch dann richtig,
    # wenn die Clips unterschiedlich gross sind. Multiplikation vor Division
    # (ih*W/H statt ih*(W/H)), sonst kommt bei gleichem Seitenverhaeltnis
    # durch Fliesskommarundung 1919.9999 heraus und der Ausschnitt verliert
    # zwei Pixel. So bleibt der Filter bei gleichem Verhaeltnis und Zoom 1.0
    # exakt die Identitaet - bestehende Projekte aendern sich nicht.
    # 2*floor(.../2) rundet auf gerade Kantenlaengen ab, die verlangt yuv420p.
    max_w = f"min(iw,ih*{W}/{H})"
    max_h = f"min(ih,iw*{H}/{W})"
    # Ausdruecke in einfache Anfuehrungszeichen: die Kommas in min() waeren
    # sonst Filtertrenner im Filtergraphen.
    crop = (f"crop=w='2*floor({max_w}/{zoom:g}/2)'"
            f":h='2*floor({max_h}/{zoom:g}/2)'"
            f":x='2*floor((iw-ow)*{crop_x:g}/2)'"
            f":y='2*floor((ih-oh)*{crop_y:g}/2)'")
    # setpts muss vor fps stehen, sonst wird erst dezimiert und dann gedehnt.
    vf = (f"{crop},scale={W}:{H}:flags=lanczos,setpts=PTS/{tempo},"
          f"fps={FPS},setsar=1")
    # -ss UND -t vor -i: beides sind hier Eingabe-Optionen. Stuende -t hinter
    # -i, wuerde es die Ausgabe begrenzen und die von setpts gedehnte
    # Zeitlupe wieder auf die Quelldauer zurueckschneiden.
    run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-ss", f"{s['in']:.3f}", "-t", f"{quelle:.3f}", "-i", str(src),
        "-vf", vf,
        "-frames:v", str(frames),
        "-an",
        *encoder.video_args(),
        "-pix_fmt", "yuv420p",
        str(dst),
    ])
    seg_files.append(dst)
    lupe = f"  [Zeitlupe {tempo:g}x, Quelle {quelle:.3f}s]" if tempo != 1.0 else ""
    schnitt = ("" if (crop_x, crop_y, zoom) == (0.5, 0.5, 1.0)
               else f"  [Ausschnitt x={crop_x:g} y={crop_y:g} zoom={zoom:g}]")
    print(f"Segment {s['n']}: {s['clip']} @ {s['in']:.2f}s, "
          f"{timeline_duration:.3f}s / {frames} Frames{lupe}{schnitt}",
          file=sys.stderr)

# 2) Concat
listfile = SEG / "concat.txt"
listfile.write_text(
    "".join(f"file '{p.as_posix()}'\n" for p in seg_files), encoding="utf-8"
)
stumm = SEG / "stumm.mp4"
run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
     "-i", str(listfile), "-c", "copy", str(stumm)])

# 3) Musik drunter, Video- und Audio-Ausblende, hart auf ende_s
audio = ROOT / cfg["audio"]
video_fades = []
if fade_in > 0:
    video_fades.append(f"fade=t=in:st=0:d={fade_in:.3f}")
video_fades.append(f"fade=t=out:st={ende - fade:.3f}:d={fade:.3f}")
video_filter = ",".join(video_fades)
run([
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(stumm), "-i", str(audio),
    "-filter_complex",
    f"[0:v]{video_filter}[v];"
    f"[1:a]atrim=0:{ende:.3f},afade=t=out:st={ende - 0.4:.3f}:d=0.4[a]",
    "-map", "[v]", "-map", "[a]",
    *encoder.video_args(), "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k",
    "-t", f"{ende:.3f}",
    "-movflags", "+faststart",
    str(out),
])

print(f"\nFertig: {out}", file=sys.stderr)
