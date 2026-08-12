# -*- coding: utf-8 -*-
"""Baut aus einer cutlist_*.json eine DaVinci-Resolve-Timeline - per Resolve-
API, nicht per FCPXML-Import. Warum: siehe CLAUDE.md, Abschnitt "Export nach
DaVinci Resolve". Kurzfassung: FCPXML kam zwar korrekt an, aber Resolve
verknuepfte die Clips nicht gegen den Media Pool (alles offline) bzw. die
Timeline blieb leer. Der API-Weg uebergibt MediaPoolItem-Objekte direkt -
da gibt es keinen Pfad mehr aufzuloesen, das Problem existiert nicht.

WICHTIG - wie dieses Skript laeuft:
Externes Scripting ist in der freien Resolve-Edition nicht verfuegbar (Studio-
only). Dieses Skript muss darum INNERHALB von Resolve laufen: Datei nach

    %APPDATA%\\Blackmagic Design\\DaVinci Resolve\\Support\\Fusion\\Scripts\\Utility

kopieren, Resolve starten (ein leeres Projekt muss NICHT vorher offen sein -
das Skript legt ein neues an), dann Workspace > Scripts > resolve_build.
Dort stellt Resolve das globale `resolve`-Objekt bereits bereit - kein
GetResolve()/scriptapp()-Umweg noetig (der ist fuer externes Scripting).

VORAUSSETZUNG: Fuer jede Einstellung mit "tempo" != 1.0 muss vorher

    .venv\\Scripts\\python.exe resolve_prep_slowmo.py <projekt>/cutlist_vN.json

gelaufen sein. Begruendung siehe dort - kurz: Resolves Scripting-API hat
keine dokumentierte Moeglichkeit, die Geschwindigkeit eines Timeline-Clips zu
setzen, und die Resolve-Timeline laeuft in Quell-Framerate, wo der
fps-Trick aus render.py nicht mehr greift. Die Zeitlupe wird darum vorab per
ffmpeg gebacken und hier nur noch mit Tempo 1.0 eingefuegt.

Konfiguration: CUTLIST_PFAD unten anpassen, oder das Skript ueber die
Resolve-Konsole mit einem Pfad-Argument aufrufen.
"""

import datetime
import json
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# HIER ANPASSEN, falls nicht ueber die Konsole mit Argument aufgerufen:
CUTLIST_PFAD = r"C:\Pfad\zur\werkzeugkette\projekte\<projekt>\cutlist_v1.json"
# ---------------------------------------------------------------------------

if len(sys.argv) > 1:
    CUTLIST_PFAD = sys.argv[1]

CUTLIST = Path(CUTLIST_PFAD)

# Projektwurzel suchen, statt eine feste Verschachtelungstiefe anzunehmen.
# Dieses Skript laeuft aus Resolves Scripts-Ordner, kann sich also nicht an
# der eigenen Lage orientieren. Erkennungsmerkmal ist cutlist.vorlage.json,
# die nur im Wurzelverzeichnis der Werkzeugkette liegt. Eine feste Annahme wie
# CUTLIST.parent.parent bricht, sobald die Ablage sich aendert - genau das ist
# beim Umzug der Schnittlisten nach projekte/<name>/ passiert.
ROOT = None
for kandidat in CUTLIST.resolve().parents:
    if (kandidat / "cutlist.vorlage.json").is_file():
        ROOT = kandidat
        break
if ROOT is None:
    raise SystemExit(
        f"Projektwurzel nicht gefunden: oberhalb von {CUTLIST} liegt kein "
        f"Ordner mit cutlist.vorlage.json. Liegt die Schnittliste ausserhalb "
        f"der Werkzeugkette?"
    )


def melden(*teile):
    """print() geht in die Resolve-Konsole (Workspace > Console, bzw. die
    Fusion-Konsole, aus der das Skript gestartet wurde)."""
    print(" ".join(str(t) for t in teile))


def abbrechen(*teile):
    melden("FEHLER:", *teile)
    raise SystemExit(1)


# --- 0) Laeuft das ueberhaupt innerhalb von Resolve? --------------------
try:
    resolve
except NameError:
    raise SystemExit(
        "Kein 'resolve'-Objekt im globalen Namensraum. Dieses Skript muss "
        "innerhalb von DaVinci Resolve laufen (Workspace > Scripts), nicht "
        "als eigenstaendiges Python-Programm - externes Scripting ist in "
        "der freien Edition nicht verfuegbar. Siehe Kopfkommentar."
    )

if not CUTLIST.exists():
    abbrechen(f"Schnittliste nicht gefunden: {CUTLIST}")

cfg = json.loads(CUTLIST.read_text(encoding="utf-8-sig"))
for pflichtfeld in ("quellen", "quell_fps", "ende_s", "shots"):
    if pflichtfeld not in cfg:
        abbrechen(f"Feld '{pflichtfeld}' fehlt in {CUTLIST.name}")

SRC = ROOT / cfg["quellen"]
QUELL_FPS = float(cfg["quell_fps"])
ENDE = float(cfg["ende_s"])
SHOTS = cfg["shots"]
ZWISCHEN = ROOT / "resolve_zwischen" / CUTLIST.stem

melden(f"Schnittliste: {CUTLIST}")
melden(f"Quellordner:  {SRC}")
melden(f"Zwischenordner (Zeitlupe): {ZWISCHEN}")
melden(f"Timeline-Framerate: {QUELL_FPS:g} (= quell_fps aus der Schnittliste)")

# --- 1) Framezahlen je Shot nachrechnen (identische Formel wie in ---------
#        resolve_prep_slowmo.py und render.py: kumulative Rundung auf
#        Frame-Grenzen, damit keine Teilfehler sich aufsummieren)
plan = []
for idx, s in enumerate(SHOTS):
    tempo = float(s.get("tempo", 1.0))
    timeline_start = float(s["schnitt_bei"])
    timeline_end = (float(SHOTS[idx + 1]["schnitt_bei"])
                    if idx + 1 < len(SHOTS) else ENDE)
    start_frame = int(timeline_start * QUELL_FPS + 0.5)
    end_frame = int(timeline_end * QUELL_FPS + 0.5)
    frames = end_frame - start_frame
    if frames <= 0:
        abbrechen(f"Shot {s['n']}: ungueltige Framedauer ({start_frame} bis {end_frame})")

    # endFrame ist in der Resolve-API EINSCHLUSSIG: das Beispiel
    # 7_add_subclips_to_timeline.py setzt {"startFrame": 0, "endFrame": 23}
    # und kommentiert das explizit als "frame 0 .. 23" - 24 Frames, nicht 23.
    # Also: endFrame = startFrame + frames - 1.
    if abs(tempo - 1.0) < 1e-9:
        pfad = SRC / s["clip"]
        quelle_start = float(s["in"])
        quell_start_frame = int(quelle_start * QUELL_FPS + 0.5)
        quell_end_frame = quell_start_frame + frames - 1
    else:
        pfad = ZWISCHEN / f"shot_{s['n']:02d}_{Path(s['clip']).stem}.mov"
        quell_start_frame = 0
        quell_end_frame = frames - 1  # der Zwischenclip beginnt bei 0 und ist
                                       # exakt 'frames' Frames lang

    if not pfad.exists():
        abbrechen(
            f"Shot {s['n']}: Datei fehlt: {pfad}\n"
            f"  Fuer Zeitlupen-Einstellungen zuerst "
            f"'.venv\\Scripts\\python.exe resolve_prep_slowmo.py {CUTLIST}' "
            f"ausserhalb von Resolve laufen lassen."
        )

    plan.append({
        "n": s["n"], "clip": s["clip"], "tempo": tempo, "frames": frames,
        "pfad": pfad, "quell_start_frame": quell_start_frame,
        "quell_end_frame": quell_end_frame,
    })

melden(f"{len(plan)} Einstellungen geplant, "
       f"{sum(1 for p in plan if p['tempo'] != 1.0)} davon aus vorgebackenen "
       f"Zeitlupen-Zwischenclips.")

# --- 2) Ffprobe-Gegenprobe der Zwischenclips, falls ffprobe erreichbar ----
#        (nur ein zusaetzliches Netz - die eigentliche Pruefung nach dem
#        Bauen der Timeline liest aus Resolve selbst zurueck, siehe unten).
#        Liest nur den Container-Header (nb_frames-Metadatum), nicht per
#        -count_frames voll durchdekodiert: Bei den 600MB-1GB grossen
#        ProRes-Zwischenclips dauert ein voller Decode-Durchlauf laenger als
#        ein grosszuegiges Timeout - gemessen beim Testen dieses Skripts.
#        ffmpeg schreibt nb_frames beim Muxen von .mov zuverlaessig, das
#        reicht als schnelle Gegenprobe.
for p in plan:
    if p["tempo"] == 1.0:
        continue
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=nb_frames", "-of", "csv=p=0", str(p["pfad"])],
            capture_output=True, text=True, timeout=15,
        )
        gemessen = int(r.stdout.strip())
        if gemessen != p["frames"]:
            abbrechen(
                f"Shot {p['n']} {p['pfad'].name}: erwartet {p['frames']} Frames, "
                f"ffprobe misst {gemessen}. resolve_prep_slowmo.py erneut laufen lassen."
            )
    except (FileNotFoundError, ValueError, subprocess.TimeoutExpired):
        melden("HINWEIS: ffprobe innerhalb von Resolve nicht erreichbar oder ohne "
               "brauchbare nb_frames-Metadaten - Gegenprobe der Zwischenclips wird "
               "uebersprungen. Die Pruefung nach dem Bauen der Timeline (Schritt 6) "
               "bleibt bestehen.")
        break

# --- 3) Neues Projekt anlegen, Framerate VOR dem Medienimport setzen -----
#        Resolve laesst die Projekt-Framerate nach dem ersten Medienimport
#        nicht mehr aendern - deshalb hier zuerst.
projectManager = resolve.GetProjectManager()
projektname = f"{CUTLIST.stem}_{datetime.datetime.now():%Y%m%d_%H%M%S}"
project = projectManager.CreateProject(projektname)
if not project:
    abbrechen(f"Projekt '{projektname}' konnte nicht angelegt werden.")
melden(f"Projekt angelegt: {projektname}")

fps_str = str(int(QUELL_FPS)) if QUELL_FPS == int(QUELL_FPS) else str(QUELL_FPS)
if not project.SetSetting("timelineFrameRate", fps_str):
    abbrechen(f"Konnte timelineFrameRate nicht auf {fps_str} setzen.")
melden(f"timelineFrameRate gesetzt: {fps_str}")

# Aufloesung best-effort aus dem ersten Quellclip lesen (ffprobe). Nicht
# kritisch fuer die Aufgabe (Clips + Zeitlupe uebertragen) - schlaegt es
# fehl, bleibt Resolves Projektvorgabe stehen und ist von Hand zu setzen.
try:
    erster_clip = SRC / next(s["clip"] for s in SHOTS)
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(erster_clip)],
        capture_output=True, text=True, timeout=15,
    )
    breite, hoehe = r.stdout.strip().split(",")
    project.SetSetting("timelineResolutionWidth", breite)
    project.SetSetting("timelineResolutionHeight", hoehe)
    melden(f"timelineResolutionWidth/Height gesetzt: {breite}x{hoehe} "
           f"(aus {erster_clip.name} gelesen)")
except Exception as e:
    melden(f"HINWEIS: Aufloesung konnte nicht automatisch gesetzt werden ({e}). "
           f"Bitte in den Projekteinstellungen pruefen.")

# --- 4) Medien importieren -------------------------------------------------
#        Ein ImportMedia-Aufruf pro Datei (nicht als Liste), damit die
#        Zuordnung Pfad -> MediaPoolItem eindeutig ist: bei einem Aufruf mit
#        einer Liste ist in der Resolve-API-Doku nicht zugesichert, dass die
#        Reihenfolge der Rueckgabe der der Eingabe entspricht. Mit genau
#        einem Pfad pro Aufruf gibt es diese Unsicherheit nicht.
mediaPool = project.GetMediaPool()
pool_items = {}  # Pfad (str) -> MediaPoolItem
eindeutige_pfade = []
gesehen = set()
for p in plan:
    key = str(p["pfad"])
    if key not in gesehen:
        eindeutige_pfade.append(p["pfad"])
        gesehen.add(key)

for pfad in eindeutige_pfade:
    ergebnis = mediaPool.ImportMedia([str(pfad)])
    if not ergebnis:
        abbrechen(f"Import fehlgeschlagen: {pfad}")
    pool_items[str(pfad)] = ergebnis[0]
melden(f"{len(pool_items)} Dateien in den Media Pool importiert.")

# --- 5) Leere Timeline anlegen und in Cutlist-Reihenfolge befuellen ------
timeline_name = CUTLIST.stem
timeline = mediaPool.CreateEmptyTimeline(timeline_name)
if not timeline:
    abbrechen(f"Timeline '{timeline_name}' konnte nicht angelegt werden.")
project.SetCurrentTimeline(timeline)
melden(f"Timeline angelegt: {timeline_name}")

# Bewusst OHNE 'recordFrame': recordFrame ist in der Resolve-API-Doku nicht
# eindeutig als absolute oder Timeline-relative Framezahl spezifiziert (die
# Timeline hat je nach Startcode-Einstellung einen Frame-Offset ungleich 0).
# Ein einziger AppendToTimeline-Aufruf mit der Shot-Liste in Cutlist-
# Reihenfolge haengt jeden Clip lueckenlos ans Ende des vorigen an - das ist
# genau das dokumentierte "Append"-Verhalten und braucht diese Annahme nicht.
# mediaType=1 (nur Video): Originalton wird bewusst nicht mitgenommen, siehe
# resolve_prep_slowmo.py. Wird Originalton gebraucht, ist das nachzuruesten.
clip_infos = []
for p in plan:
    clip_infos.append({
        "mediaPoolItem": pool_items[str(p["pfad"])],
        "startFrame": p["quell_start_frame"],
        "endFrame": p["quell_end_frame"],
        "mediaType": 1,
        "trackIndex": 1,
    })

timeline_items = mediaPool.AppendToTimeline(clip_infos)
if not timeline_items:
    abbrechen("AppendToTimeline hat nichts zurueckgegeben - Timeline ist leer geblieben.")

# --- 5b) Musik auf A1 ------------------------------------------------------
#         Eigener AppendToTimeline-Aufruf mit mediaType=2 (nur Audio). A1 ist
#         zu diesem Zeitpunkt leer, weil die Videoclips mit mediaType=1
#         eingefuegt wurden - der Ton landet damit bei Frame 0 und nicht
#         hinter irgendetwas.
musik_item = None
gesamt_soll = sum(p["frames"] for p in plan)
if "audio" in cfg:
    musik_pfad = ROOT / cfg["audio"]
    if not musik_pfad.is_file():
        abbrechen(f"Musikdatei fehlt: {musik_pfad}")
    ergebnis = mediaPool.ImportMedia([str(musik_pfad)])
    if not ergebnis:
        abbrechen(f"Import der Musikdatei fehlgeschlagen: {musik_pfad}")
    musik_pool_item = ergebnis[0]

    # Die Musik ist in der Regel laenger als der Film und wird auf die
    # Timeline-Laenge beschnitten - genauso wie render.py sie per atrim auf
    # ende_s kuerzt.
    musik_items = mediaPool.AppendToTimeline([{
        "mediaPoolItem": musik_pool_item,
        "startFrame": 0,
        "endFrame": gesamt_soll - 1,   # einschliesslich, siehe oben
        "mediaType": 2,
        "trackIndex": 1,
    }])
    if not musik_items:
        melden("HINWEIS: Musik konnte nicht auf A1 gelegt werden. Die Datei "
               "liegt im Media Pool und ist von Hand einzufuegen.")
    else:
        musik_item = musik_items[0]
        melden(f"Musik auf A1: {musik_pfad.name}")
else:
    melden("HINWEIS: Kein Feld 'audio' in der Schnittliste - keine Musik eingefuegt.")

# --- 6) Ruecklesen und gegen den Plan pruefen, statt Erfolg zu behaupten -
melden("\n--- Pruefung: Timeline gegen Schnittliste ---")
probleme = []

if len(timeline_items) != len(plan):
    probleme.append(
        f"Anzahl Clips: erwartet {len(plan)}, Timeline hat {len(timeline_items)}"
    )

vorheriges_ende = None
gesamt_frames = 0
for p, item in zip(plan, timeline_items):
    dauer_ist = item.GetDuration()
    if dauer_ist != p["frames"]:
        probleme.append(
            f"Shot {p['n']} {p['clip']}: erwartet {p['frames']} Frames, "
            f"Timeline zeigt {dauer_ist}"
        )
    start_ist = item.GetStart()
    if vorheriges_ende is not None and start_ist != vorheriges_ende:
        probleme.append(
            f"Shot {p['n']} {p['clip']}: beginnt bei Frame {start_ist}, "
            f"vorige Einstellung endete bei {vorheriges_ende} - Luecke oder "
            f"Ueberlappung von {start_ist - vorheriges_ende} Frames"
        )
    vorheriges_ende = item.GetEnd() + 1
    gesamt_frames += dauer_ist
    melden(f"  Shot {p['n']:2d} {p['clip']:28s} "
           f"{'Zeitlupe' if p['tempo'] != 1.0 else 'Echtzeit':8s}  "
           f"Timeline {item.GetStart()}-{item.GetEnd()} "
           f"({dauer_ist} Frames)")

erwartete_gesamtframes = int(ENDE * QUELL_FPS + 0.5)
if gesamt_frames != erwartete_gesamtframes:
    probleme.append(
        f"Gesamtlaenge: erwartet {erwartete_gesamtframes} Frames "
        f"({ENDE:.3f}s @ {QUELL_FPS:g}fps), Timeline hat {gesamt_frames} Frames "
        f"({gesamt_frames / QUELL_FPS:.3f}s)"
    )

# Musik ebenfalls zurueckgelesen statt nur eingefuegt und gehofft.
if "audio" in cfg:
    if musik_item is None:
        probleme.append("Musik wurde nicht auf A1 eingefuegt.")
    else:
        m_start, m_dauer = musik_item.GetStart(), musik_item.GetDuration()
        melden(f"  Musik    {Path(cfg['audio']).name:28s} "
               f"{'A1':8s}  Timeline {m_start}-{musik_item.GetEnd()} "
               f"({m_dauer} Frames)")
        if m_start != 0:
            probleme.append(f"Musik beginnt bei Frame {m_start} statt 0")
        if m_dauer != gesamt_soll:
            probleme.append(
                f"Musik: erwartet {gesamt_soll} Frames, Timeline zeigt {m_dauer}"
            )

melden(f"\nGesamt: {gesamt_frames} Frames = {gesamt_frames / QUELL_FPS:.3f}s "
       f"(Schnittliste: {ENDE:.3f}s)")

if probleme:
    melden(f"\n{len(probleme)} PROBLEM(E) - Timeline weicht von der Schnittliste ab:")
    for pr in probleme:
        melden("  -", pr)
    melden("\nProjekt wurde angelegt, aber NICHT gespeichert - erst pruefen.")
    raise SystemExit(1)

projectManager.SaveProject()
melden(f"\nOK - {len(plan)} Einstellungen, {gesamt_frames} Frames "
       f"({gesamt_frames / QUELL_FPS:.3f}s), Projekt gespeichert: {projektname}")
melden("Bild auf V1, Musik auf A1. Der Originalton der Clips ist bewusst "
       "nicht dabei (mediaType=1).")
