"""Brennt Titeleinblendungen in eine gerenderte Fassung und haengt Schwarz an.

Zweiter Schritt nach dem Rendern, wie make_numbered_review.py: Die Quelle
bleibt unveraendert, das Ergebnis landet als <ausgabe>_titel.mp4 daneben.

Die Texte stehen in der Schnittliste, nicht hier im Code - sonst waere jede
Fassung wieder Handarbeit. Zwei Felder im Kopf:

    "titel": [
      {"text": "MPS Luhmuehlen 2023", "unterzeile": "Heerlager X",
       "bei": 2.8, "dauer": 7.6},
      {"text": "Name Fotografie 2026", "bei": 423.0, "dauer": 5.0,
       "ausblende_ms": 250}
    ],
    "nachlauf_schwarz_s": 3.0

`bei` und `dauer` zaehlen wie `schnitt_bei` in Sekunden auf der Timeline.
`einblende_ms` und `ausblende_ms` sind optional und ueberschreiben je Titel
die Blendendauer aus den Konstanten unten - gebraucht bei kurzen Fassungen,
wo eine Sekunde Ausblende einen spuerbaren Teil des Abspanns frisst.
`nachlauf_schwarz_s` haengt Schwarzbild hinten an, damit ein Abspann noch
stehen kann, nachdem das Bild ausgeblendet ist - der Ton laeuft dort stumm
weiter. Ohne das Feld endet der Film wie gerendert.

Beides ist optional: Fehlt "titel", bricht das Skript mit Hinweis ab.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import encoder


ROOT = Path(__file__).parent

# Gestaltung an einer Stelle. Serifenschrift, weil sie neben historischem
# Motiv weniger nach Buerosoftware aussieht als eine Grotesk.
SCHRIFT = "Palatino Linotype"
GROESSE_TITEL = 96
GROESSE_UNTERZEILE = 50
# Sperrung: bei grossen Versalien wirkt der Satz sonst gedraengt.
SPERRUNG_TITEL = 6
SPERRUNG_UNTERZEILE = 4
# Weiche Blenden in Millisekunden. Titel duerfen nicht aufblitzen.
# Das ist der Standard fuer einen Film normaler Laenge. Je Titel ueber
# "einblende_ms"/"ausblende_ms" ueberschreibbar - anders als Schrift und
# Groesse haengt die Blendendauer nicht am Haus-Stil, sondern an der
# Filmlaenge: eine Sekunde ist bei sieben Minuten unauffaellig und bei einem
# 23-Sekunden-Trailer ein Viertel des Abspanns.
EINBLENDE_MS = 1000
AUSBLENDE_MS = 900
# Kontur haelt die Schrift auch ueber hellem Bild lesbar. Im Schwarzbild
# faellt sie nicht auf, deshalb ein Wert fuer beide Faelle.
KONTUR = 2
SCHATTEN = 2
GROESSE_CREDIT = 34


def ass_time(seconds: float) -> str:
    centiseconds = int(round(seconds * 100))
    hours, rest = divmod(centiseconds, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def ass_escape(text: str) -> str:
    """Schuetzt Zeichen, die ASS als Steuerzeichen liest."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


if len(sys.argv) < 2:
    raise SystemExit("Aufruf: python make_titles.py <cutlist.json> [ausgabe.mp4]")

cutlist = Path(sys.argv[1])
if not cutlist.is_absolute():
    cutlist = ROOT / cutlist

cfg = json.loads(cutlist.read_text(encoding="utf-8-sig"))

titel = cfg.get("titel")
if not titel:
    raise SystemExit(
        f"{cutlist.name}: Feld 'titel' fehlt oder ist leer.\n"
        "Aufbau steht im Kopf von make_titles.py und in cutlist.vorlage.json."
    )

source = ROOT / cfg["ausgabe"]
if not source.exists():
    raise SystemExit(f"Gerenderte Fassung fehlt: {source}\nErst render.py laufen lassen.")

if len(sys.argv) > 2:
    output = Path(sys.argv[2])
    if not output.is_absolute():
        output = ROOT / output
else:
    output = source.with_name(f"{source.stem}_titel{source.suffix}")
output.parent.mkdir(parents=True, exist_ok=True)

breite, hoehe = int(cfg["breite"]), int(cfg["hoehe"])
ende = float(cfg["ende_s"])
nachlauf = float(cfg.get("nachlauf_schwarz_s", 0.0))
gesamt = ende + nachlauf

# Pruefen, bevor ffmpeg minutenlang rechnet: Ein Titel hinter dem Filmende
# waere im Ergebnis unsichtbar, ohne dass jemand den Fehler bemerkt.
for eintrag in titel:
    bei = float(eintrag["bei"])
    dauer = float(eintrag["dauer"])
    if bei < 0 or bei + dauer > gesamt + 0.001:
        raise SystemExit(
            f"Titel \"{eintrag['text']}\" liegt bei {bei:.2f}s bis "
            f"{bei + dauer:.2f}s, der Film ist aber nur {gesamt:.2f}s lang "
            f"(ende_s {ende:.2f} + nachlauf_schwarz_s {nachlauf:.2f})."
        )
    if eintrag.get("stil", "titel") not in ("titel", "credit"):
        raise SystemExit(
            f"Titel \"{eintrag['text']}\": stil muss 'titel' oder 'credit' sein."
        )
    # Blenden, die zusammen laenger sind als die Standzeit, hiessen: der
    # Titel steht nie voll da. Das faellt im Ergebnis kaum auf und ist
    # trotzdem falsch, deshalb hier abfangen.
    blenden = (float(eintrag.get("einblende_ms", EINBLENDE_MS))
               + float(eintrag.get("ausblende_ms", AUSBLENDE_MS)))
    if blenden < 0 or eintrag.get("einblende_ms", 0) < 0 \
            or eintrag.get("ausblende_ms", 0) < 0:
        raise SystemExit(
            f"Titel \"{eintrag['text']}\": Blendendauer darf nicht negativ sein."
        )
    if blenden > dauer * 1000:
        raise SystemExit(
            f"Titel \"{eintrag['text']}\": Ein- und Ausblende dauern zusammen "
            f"{blenden / 1000:.2f}s, die Standzeit betraegt aber nur "
            f"{dauer:.2f}s - der Titel stuende nie voll im Bild."
        )

mitte = hoehe / 2
header = f"""[Script Info]
Title: Titeleinblendungen
ScriptType: v4.00+
PlayResX: {breite}
PlayResY: {hoehe}
ScaledBorderAndShadow: yes
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Titel,{SCHRIFT},{GROESSE_TITEL},&H00FFFFFF,&H00FFFFFF,&HC0000000,&HA0000000,0,0,0,0,100,100,{SPERRUNG_TITEL},0,1,{KONTUR},{SCHATTEN},5,80,80,0,1
Style: Unterzeile,{SCHRIFT},{GROESSE_UNTERZEILE},&H00EAEAEA,&H00EAEAEA,&HC0000000,&HA0000000,0,0,0,0,100,100,{SPERRUNG_UNTERZEILE},0,1,{KONTUR},{SCHATTEN},5,80,80,0,1
Style: Credit,{SCHRIFT},{GROESSE_CREDIT},&H00D8D8D8,&H00D8D8D8,&HC0000000,&HA0000000,0,0,0,0,100,100,2,0,1,1,1,3,50,50,36,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

events = []
for eintrag in titel:
    bei = float(eintrag["bei"])
    dauer = float(eintrag["dauer"])
    ende_titel = bei + dauer
    unterzeile = eintrag.get("unterzeile")
    ein_ms = int(eintrag.get("einblende_ms", EINBLENDE_MS))
    aus_ms = int(eintrag.get("ausblende_ms", AUSBLENDE_MS))
    fad = f"\\fad({ein_ms},{aus_ms})"
    stil = eintrag.get("stil", "titel")

    if stil == "credit":
        events.append(
            f"Dialogue: 0,{ass_time(bei)},{ass_time(ende_titel)},Credit,,0,0,0,,"
            f"{{{fad}}}{ass_escape(eintrag['text'])}"
        )
    elif unterzeile:
        # Zweizeilig: Titel nach oben, Unterzeile nach unten ruecken, damit
        # der Block optisch um die Bildmitte sitzt.
        y_titel = mitte - GROESSE_UNTERZEILE * 0.80
        y_unter = mitte + GROESSE_TITEL * 0.70
        events.append(
            f"Dialogue: 0,{ass_time(bei)},{ass_time(ende_titel)},Titel,,0,0,0,,"
            f"{{\\pos({breite / 2:.0f},{y_titel:.0f}){fad}}}{ass_escape(eintrag['text'])}"
        )
        # Die Unterzeile kommt spaeter und geht frueher - erst der Ort, dann
        # die Zugehoerigkeit, statt beides auf einmal.
        events.append(
            f"Dialogue: 0,{ass_time(bei + 1.1)},{ass_time(ende_titel)},Unterzeile,,0,0,0,,"
            f"{{\\pos({breite / 2:.0f},{y_unter:.0f})"
            f"{fad}}}{ass_escape(unterzeile)}"
        )
    else:
        events.append(
            f"Dialogue: 0,{ass_time(bei)},{ass_time(ende_titel)},Titel,,0,0,0,,"
            f"{{\\pos({breite / 2:.0f},{mitte:.0f}){fad}}}{ass_escape(eintrag['text'])}"
        )

ass_file = ROOT / "sheets" / f"titles_{cutlist.stem}.ass"
ass_file.parent.mkdir(parents=True, exist_ok=True)
ass_file.write_text(header + "\n".join(events) + "\n", encoding="utf-8-sig")

# Relativer Pfad vermeidet das zu escapende Laufwerkskolon in ffmpegs
# Filtersyntax. Vorwaertsschraege funktioniert auch unter Windows.
ass_relative = ass_file.relative_to(ROOT).as_posix()

# tpad muss VOR ass stehen: Der Untertitelfilter soll auch auf den
# angehaengten Schwarzframes zeichnen duerfen, sonst endet der Abspann
# genau dort, wo er allein stehen soll.
if nachlauf > 0:
    vf = (f"tpad=stop_mode=add:stop_duration={nachlauf:.3f}:color=black,"
          f"ass=filename='{ass_relative}'")
    af = ["-af", f"apad=pad_dur={nachlauf:.3f}"]
else:
    vf = f"ass=filename='{ass_relative}'"
    af = []

cmd = [
    "ffmpeg", "-y", "-loglevel", "error",
    "-i", str(source),
    "-vf", vf,
    *af,
    "-map", "0:v:0", "-map", "0:a?",
    *encoder.video_args(),
    "-pix_fmt", "yuv420p",
    "-c:a", "aac", "-b:a", "192k",
    "-t", f"{gesamt:.3f}",
    "-movflags", "+faststart",
    str(output),
]
print(f"Encoder: {encoder.name()}, {len(titel)} Titel, "
      f"Nachlauf {nachlauf:.1f}s, Gesamtlaenge {gesamt:.2f}s", file=sys.stderr)
subprocess.run(cmd, cwd=ROOT, check=True)
print(output)
