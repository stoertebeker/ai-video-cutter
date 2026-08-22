"""Prueft eine Schnittliste, bevor gerendert wird.

Geprueft wird: Lueckenlosigkeit der Schnittpunkte, dass kein Bild- oder
Tonsegment ueber sein Quellende hinausliest, dass sich zwei Bildverwendungen
desselben Clips nicht ueberlappen, Audio-/Mixfelder und genutzte Clips.
"""

import collections
import functools
import json
import subprocess
import sys
from pathlib import Path

import audio_timeline
import overlay_timeline

ROOT = Path(__file__).parent
if len(sys.argv) < 2:
    raise SystemExit("Aufruf: validate_cutlist.py <projekt>/cutlist_vN.json")
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
RESERVE = 0.15  # Mindestabstand zum Clipende, in Sekunden
ZOOM_WARN = 4.0  # ab hier ist der Ausschnitt so klein, dass er weich wird
ZIEL_AR = float(cfg["breite"]) / float(cfg["hoehe"])


@functools.cache
def probe(p: Path) -> tuple[float, int, int, bool]:
    """Dauer, Bildmasse und Audiospur in einem einzigen ffprobe-Aufruf.

    Die Masse braucht die Ausschnittspruefung: ob crop_x oder crop_y
    ueberhaupt wirken, haengt am Verhaeltnis von Quelle zu Ziel.
    """
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json",
         "-show_entries", "format=duration:stream=codec_type,width,height", str(p)],
        capture_output=True, text=True, check=True,
    )
    j = json.loads(r.stdout)
    video = next(
        (st for st in j["streams"] if st.get("codec_type") == "video"), None
    )
    has_audio = any(st.get("codec_type") == "audio" for st in j["streams"])
    return (
        float(j["format"]["duration"]),
        int(video["width"]) if video else 0,
        int(video["height"]) if video else 0,
        has_audio,
    )


fehler, hinweise = [], []
pos = 0.0
belegt = collections.defaultdict(list)
# Sammelt, ob ueberhaupt ein Ausschnitt gewaehlt wurde und ob das Quellformat
# vom Ziel abweicht - beides zusammen ergibt erst am Ende einen Hinweis.
crop_x_gesetzt = False
format_weicht_ab = False


def zahl(wert) -> bool:
    """True fuer eine echte Zahl. bool ist in Python eine int-Unterart."""
    return isinstance(wert, (int, float)) and not isinstance(wert, bool)


# Die Szenennummer n muss eindeutig sein: render.py benennt die Segmente
# danach (seg_NN.mp4) und wuerde bei einer Dopplung stillschweigend
# ueberschreiben, und in Feedbackrunden ist n die gemeinsame Sprache zwischen
# Mensch und Schnittliste. Aufsteigend ist nur wuenschenswert.
nummern = [s["n"] for s in cfg["shots"]]
doppelt = sorted({x for x in nummern if nummern.count(x) > 1})
if doppelt:
    fehler.append(f"Szenennummern doppelt vergeben: {doppelt}")
if nummern != sorted(nummern):
    hinweise.append("Szenennummern laufen nicht aufsteigend - erlaubt, aber "
                    "erschwert die Verstaendigung ueber die Reviewfassung")

if not SRC.is_dir():
    fehler.append(f"Quellordner fehlt: {SRC}")
if "musik" not in cfg:
    if "audio" not in cfg:
        fehler.append("Musik fehlt: weder Feld audio noch musik vorhanden")
    else:
        musik = ROOT / cfg["audio"]
        if not musik.is_file():
            fehler.append(f"Musikdatei fehlt: {musik}")

for s in cfg["shots"]:
    pfad = SRC / s["clip"]

    rotation = s.get("rotation", 0)
    if not isinstance(rotation, int) or isinstance(rotation, bool) \
            or rotation not in (0, 180):
        fehler.append(
            f"Shot {s['n']}: rotation muss 0 oder 180 sein, ist {rotation!r}"
        )

    # Bildausschnitt. Die Werte sind relativ, damit die Schnittliste nicht an
    # einer Quellaufloesung klebt - deshalb sind die Grenzen fest und nicht
    # vom Material abhaengig.
    for feld in ("crop_x", "crop_y"):
        if feld not in s:
            continue
        wert = s[feld]
        if not zahl(wert):
            fehler.append(f"Shot {s['n']}: {feld} muss eine Zahl sein, "
                          f"ist {wert!r}")
        elif not 0.0 <= float(wert) <= 1.0:
            fehler.append(
                f"Shot {s['n']}: {feld} {wert} liegt ausserhalb 0.0-1.0 "
                f"(0 = links bzw. oben, 0.5 = Mitte, 1 = rechts bzw. unten)"
            )
    crop_x_gesetzt = crop_x_gesetzt or "crop_x" in s
    zoom = s.get("crop_zoom", 1.0)
    if not zahl(zoom):
        fehler.append(f"Shot {s['n']}: crop_zoom muss eine Zahl sein, "
                      f"ist {zoom!r}")
        zoom = 1.0
    elif float(zoom) < 1.0:
        fehler.append(
            f"Shot {s['n']}: crop_zoom {zoom} kleiner als 1.0 - 1.0 ist "
            f"bereits der groesstmoegliche Ausschnitt, kleiner geht nicht"
        )
    elif float(zoom) > ZOOM_WARN:
        hinweise.append(
            f"Shot {s['n']}: crop_zoom {zoom} - mehr als {ZOOM_WARN:g}fach "
            f"vergroessert, das Bild wird sichtbar weich"
        )

    if not pfad.exists():
        fehler.append(f"Shot {s['n']}: Datei fehlt: {s['clip']}")
        continue

    if abs(s["schnitt_bei"] - pos) > 0.001:
        fehler.append(
            f"Shot {s['n']}: schnitt_bei {s['schnitt_bei']:.3f} "
            f"passt nicht zur Summe davor ({pos:.3f})"
        )

    laenge, quell_w, quell_h, _ = probe(pfad)
    quell_ar = quell_w / quell_h
    if abs(quell_ar - ZIEL_AR) > 0.01:
        format_weicht_ab = True
    # crop_y kann nur wirken, wenn ueberhaupt Hoehe zum Verschieben da ist.
    # Ist die Quelle breiter als das Ziel (Querformat -> Hochkant), nutzt der
    # groesstmoegliche Ausschnitt die volle Bildhoehe - dann bleibt crop_y
    # ohne Wirkung, und wer daran dreht, sucht den Fehler an der falschen
    # Stelle. Erst crop_zoom > 1.0 schafft Spielraum.
    if "crop_y" in s and float(zoom) == 1.0 and quell_ar >= ZIEL_AR - 0.01:
        hinweise.append(
            f"Shot {s['n']} {s['clip']}: crop_y {s['crop_y']} ohne Wirkung - "
            f"bei crop_zoom 1.0 nutzt der Ausschnitt die volle Bildhoehe "
            f"({quell_w}x{quell_h} in {cfg['breite']}x{cfg['hoehe']}). "
            f"Nur crop_x verschiebt hier."
        )
    # Bei Zeitlupe wird weniger Quellmaterial verbraucht als die Einstellung
    # spaeter lang ist: verbraucht = dauer * tempo.
    tempo = float(s.get("tempo", 1.0))
    ende = s["in"] + s["dauer"] * tempo
    if ende > laenge:
        fehler.append(
            f"Shot {s['n']} {s['clip']}: liest bis {ende:.2f}s, "
            f"Clip hat nur {laenge:.2f}s"
        )
    elif laenge - ende < RESERVE:
        hinweise.append(
            f"Shot {s['n']} {s['clip']}: nur {laenge - ende:.2f}s Reserve am Ende"
        )
    if s["in"] < 0.1:
        hinweise.append(f"Shot {s['n']} {s['clip']}: startet {s['in']:.2f}s nach Clipanfang")

    for a, b, n in belegt[s["clip"]]:
        if s["in"] < b and ende > a:
            fehler.append(
                f"Shot {s['n']} ueberlappt Shot {n} im selben Clip "
                f"{s['clip']} ({a:.2f}-{b:.2f} vs {s['in']:.2f}-{ende:.2f})"
            )
    belegt[s["clip"]].append((s["in"], ende, s["n"]))
    pos += s["dauer"]


def probe_audio(pfad: Path) -> tuple[float, bool]:
    laenge, _, _, hat_audio = probe(pfad)
    return laenge, hat_audio


audio_fehler, audio_hinweise = audio_timeline.validate(
    cfg, SRC, float(cfg["ende_s"]), probe_audio
)
fehler.extend(audio_fehler)
hinweise.extend(audio_hinweise)

musik_fehler, musik_hinweise = audio_timeline.validate_music(
    cfg, ROOT, float(cfg["ende_s"]), probe_audio
)
fehler.extend(musik_fehler)
hinweise.extend(musik_hinweise)

overlay_fehler, overlay_hinweise = overlay_timeline.validate(
    cfg, ROOT, float(cfg["ende_s"])
)
fehler.extend(overlay_fehler)
hinweise.extend(overlay_hinweise)

if abs(pos - float(cfg["ende_s"])) > 0.001:
    fehler.append(f"Summe der Dauern {pos:.3f}s != ende_s {cfg['ende_s']}")

# Kein Fehler, aber fast immer ein Versehen: Das Ziel hat ein anderes
# Seitenverhaeltnis als das Material, also wird beschnitten - und ohne crop_x
# schneidet render.py jede Einstellung auf Bildmitte. Bei Totalen sitzt das
# Motiv dort selten.
if format_weicht_ab and not crop_x_gesetzt:
    hinweise.append(
        f"Quellformat weicht vom Ziel {cfg['breite']}x{cfg['hoehe']} ab, aber "
        f"kein Shot hat crop_x - alle Ausschnitte stehen auf Bildmitte. "
        f"sheet_crop.py zeigt die Ausschnitte im Bild."
    )

VIDEO = {".mp4", ".mov", ".mts", ".mkv", ".avi"}
vorhanden = {p.name for p in SRC.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO}
ungenutzt = sorted(vorhanden - set(belegt))
mehrfach = {k: len(v) for k, v in belegt.items() if len(v) > 1}

print(f"{liste.name}: {len(cfg['shots'])} Shots, {pos:.3f}s")
print(f"Clips genutzt: {len(belegt)} von {len(vorhanden)}")
if mehrfach:
    print("mehrfach:      " + ", ".join(f"{k.split('_')[0]} ({v}x)"
                                        for k, v in sorted(mehrfach.items())))
if ungenutzt:
    print("ungenutzt:     " + ", ".join(u.split("_")[0] for u in ungenutzt))
for h in hinweise:
    print(f"  HINWEIS: {h}")
for f in fehler:
    print(f"  FEHLER:  {f}")
print("OK" if not fehler else "NICHT OK")
sys.exit(1 if fehler else 0)
