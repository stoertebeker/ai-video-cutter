# Musikgeschnittene Videomontage

Aus vielen kurzen Clips eine auf Musik geschnittene Montage bauen — mit ffmpeg
und Python, vollständig lokal. Keine API-Keys, keine Cloud, kein Konto.

Gedacht für alle, die einen Ordner voller Clips und ein Musikstück haben und
daraus einen Teaser schneiden wollen, ohne dafür ein Schnittprogramm
aufzumachen.

## Das Prinzip

Zwei Dinge unterscheiden diese Kette von einem Schnittskript:

**Das Material wird angesehen, nicht geraten.** `make_contactsheets.py` zieht
je Clip mehrere Frames und baut daraus beschriftete Kontaktbögen als PNG. Diese
Bilder kann ein KI-Assistent mit seinem Datei-Lesewerkzeug tatsächlich als Bild
lesen. Ohne diesen Schritt kennt er nur Dateinamen — und rät.

**Die Maschine rechnet, der Mensch entscheidet.** Beatraster, Lautstärkeverlauf,
lückenlose Timeline, Zeitlupenarithmetik: das ist Fleißarbeit und wird
gerechnet. Welche Einstellung wohin gehört und ob ein Schnitt sitzt, entscheidet
der Mensch. Jeder Schritt hinterlässt eine Datei, die man anschauen kann.

## Voraussetzungen

- **ffmpeg und ffprobe** im PATH (entwickelt mit 7.1.1)
- **Python 3.13** in einer Venv unter `.venv`
- **librosa** (Beat- und Lautstärkeanalyse), **numpy**, **Pillow**
  (Kontaktbögen), **yt-dlp** (nur um einen Scratch-Track zu ziehen)

```
py -m venv .venv
.venv\Scripts\python.exe -m pip install librosa pillow yt-dlp
```

Die Skripte werden **immer über die Venv** aufgerufen:
`.venv\Scripts\python.exe <skript>.py …`

`CLAUDE.md` beschreibt zusätzlich den Weg über die Kinocut-Extras
(`pip install "kinocut[image,audio-enhanced,audio-analysis]" yt-dlp`), der
dieselben Pakete mitbringt. Kinocut selbst ist optional — kein Skript hier
importiert es.

## Schnellstart

Ausgangslage: ein Ordner Clips und ein Musikstück.

**1. Material ablegen.** Quellclips nach `material/<projekt>/`, Musik nach
`audio/<projekt>/`. Erkannt werden `.mp4 .mov .mts .mkv .avi`,
Groß-/Kleinschreibung egal.

**2. Musik analysieren.** Sie gibt Länge und Schnittraster vor, nicht das Bild.

```
.venv\Scripts\python.exe analyze_music.py audio/<projekt>/track.wav > audio/<projekt>/analyse.json
.venv\Scripts\python.exe plan_raster.py audio/<projekt>/analyse.json 4
```

`analyze_music.py` liefert Tempo, Beatzeiten, Onsets und RMS-Pegel je halbe
Sekunde. `plan_raster.py` nimmt jeden vierten erkannten Beat als Taktgrenze und
schreibt den Pegel daneben — diese Tabelle ist die Vorlage für die
Schnittzeitpunkte. (PowerShells `>` schreibt UTF-8 mit BOM; die Skripte lesen
deshalb mit `utf-8-sig`.)

**3. Material sichten.** Erst grob, dann dicht:

```
.venv\Scripts\python.exe make_contactsheets.py material/<projekt> 3 5
.venv\Scripts\python.exe make_contactsheets.py material/<projekt> 8 6 <filter>
```

Argumente: Quellordner, Frames je Clip, Clips je Bogen, optional ein
Namensfragment als Filter. Ergebnis liegt in `sheets/<projekt>/`. Drei Frames
sortieren Drehorte und Dopplungen; acht Frames zeigen erst die Bewegung
*innerhalb* einer Einstellung — Schärfefahrten, Schwenks, die aus dem Motiv
laufen, abgebrochene Takes.

**4. Schnittliste schreiben.** `cutlist.vorlage.json` nach
`projekte/<projekt>/cutlist_v1.json` kopieren, Kopf ausfüllen, Einstellungen
eintragen.

**5. Prüfen, rendern, kontrollieren.**

```
.venv\Scripts\python.exe validate_cutlist.py      projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe render.py                projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe make_numbered_review.py  projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe sheet_sequence.py        projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe verify_cuts.py           projekte/<projekt>/cutlist_v1.json
```

`validate_cutlist.py` läuft Sekunden, ein Renderlauf Minuten — deshalb immer
zuerst prüfen. Es fängt Lücken in der Timeline, Clips, die über ihr Quellende
hinauslesen, überlappende Mehrfachverwendungen desselben Clips und eine
Dauersumme, die nicht zu `ende_s` passt. Dazu listet es ungenutzte Clips.

Soll das Ergebnis ein anderes Seitenverhältnis haben als das Material, kommt
`sheet_crop.py` dazu — siehe „Hochkant aus Querformat" weiter unten.

**6. Abnahme mit Szenennummern.**

`make_numbered_review.py` ist ein **zweiter Schritt nach dem Rendern**: Es
liest die fertige Datei aus `ausgabe` ein und blendet je Einstellung die
Szenennummer `n` ein, framegenau an den Shotgrenzen. Ergebnis ist
`<ausgabe>_nummeriert.mp4`.

Diese nummerierte Datei ist die Fassung, die man zur Abnahme zeigt — damit
Rückmeldungen lauten „ändere Szene 3" statt „die Stelle mit dem Baum". Nach
jeder Änderung an der Schnittliste neu erzeugen, sonst stimmen die Zahlen
nicht mehr. Die unnummerierte Endfassung entsteht am Schluss von selbst: Es
ist die Datei, die `render.py` ohnehin schreibt.

## Titel und Abspann

```
.venv\Scripts\python.exe make_titles.py projekte/<projekt>/cutlist_vN.json
```

Ebenfalls ein zweiter Schritt nach dem Rendern, Ergebnis ist
`<ausgabe>_titel.mp4`. **Die Texte stehen in der Schnittliste**, nicht im
Skript — Feld `titel` mit `text`, optionaler `unterzeile`, `bei` und `dauer`.
Schrift, Größen und Blenden stehen am Kopf von `make_titles.py` und gelten für
alle Projekte.

`nachlauf_schwarz_s` hängt Schwarzbild hinter `ende_s` an. Damit kann ein
Abspann die Schlussszene noch begleiten und erst danach allein im Schwarzen
stehen: `bei` vor `ende_s` legen, `dauer` darüber hinausreichen lassen.

Für die Abnahme nimmt man `make_numbered_review.py`, für die Endfassung
`make_titles.py` — beides zusammen ergibt keinen Sinn, Szenennummern gehören
nicht in die fertige Fassung.

## Aufbau

**Dieses Repository enthält ausschließlich das Werkzeug.** Projekte liegen
daneben im Arbeitsverzeichnis und werden nicht versioniert — weder Rohmaterial
noch Musik, Schnittlisten, Projektdokumentation oder fertige Videos.

```
                        ── im Repository ──
*.py                    Werkzeuge, projektunabhängig
cutlist.vorlage.json    Vorlage für die Schnittliste
PROJEKT.vorlage.md      Vorlage für das Materialprotokoll
README.md CLAUDE.md AGENTS.md    Doku

                        ── daneben, nicht versioniert ──
projekte/<name>/        Schnittlisten (cutlist_*.json) + PROJEKT.md
material/<name>/        Quellclips
audio/<name>/           Musik und Analysen je Projekt
audio/musikvorschlaege/ lizenzierte Tracks, projektübergreifend
out/                    nummerierte Reviews + freigegebene Endfassungen
sheets/<name>/          Kontaktbögen, Sequenz- und Prüfbögen
frames/<name>/          Einzelframes
segments/<fassung>/     Rendersegmente
verify/<name>/          Prüfframes
resolve_zwischen/       Zeitlupen-Zwischenclips für den Resolve-Export
```

Die letzten fünf Ordner sind Zwischenstände und jederzeit löschbar — sie
entstehen aus Schnittliste plus Quellmaterial neu.

Ein Projekt ist auf vier Orte verteilt, und alle vier stehen als Pfad im Kopf
der Schnittliste: sie selbst liegt in `projekte/<name>/`, `quellen` zeigt auf
den Materialordner, `audio` auf die Musikdatei, `ausgabe` auf das Ziel. Fehlt
eine davon, meldet `validate_cutlist.py` das vor dem Rendern.

Die `.gitignore` ist als Positivliste gebaut: erst wird alles ausgeschlossen,
dann gezielt das Werkzeug wieder hereingenommen. Ein neues Projekt bleibt
dadurch von selbst außerhalb der Versionierung. **Am Code ist für ein neues
Projekt nichts zu ändern.**

| Werkzeug | Was es tut |
|---|---|
| `analyze_music.py` | Tempo, Beats, Onsets, RMS-Verlauf als JSON |
| `plan_raster.py` | Taktraster aus den erkannten Beats, mit Pegel |
| `make_contactsheets.py` | Kontaktbögen aus den Quellclips |
| `validate_cutlist.py` | prüft die Schnittliste vor dem Rendern |
| `sheet_crop.py` | zeigt die gewählten Bildausschnitte im Quellbild |
| `render.py` | Segmente kodieren, aneinanderhängen, Musik drunter |
| `encoder.py` | Videoparameter an einer Stelle — GPU oder CPU |
| `sheet_sequence.py` | ein Frame je Einstellung aus dem fertigen Video |
| `verify_cuts.py` | Frames vor und nach jedem Schnitt |
| `make_numbered_review.py` | erzeugt die nummerierte Abnahmefassung |
| `make_titles.py` | brennt Titel ein, hängt Schwarz für den Abspann an |

### GPU oder CPU

Voreinstellung ist die GPU (`h264_nvenc`), gemessen rund **4× schneller** als
x264 mit `preset slow`. Für die Endfassung lohnt der Wechsel auf CPU:

```
$env:ENCODER="cpu"; .venv\Scripts\python.exe render.py projekte/<projekt>/cutlist_vN.json
```

NVENC ist pro Bit schwächer als x264. In Reviewfassungen fällt das nicht auf,
in dunklen Bildern — Nacht, Fackel- und Kerzenlicht — wird es als Banding
sichtbar. GPU-Dateien sind außerdem rund 60 % größer.

Braucht eine NVIDIA-Karte und ein ffmpeg mit NVENC. Fehlt beides, meldet
`encoder.py` das im Klartext und nennt den CPU-Weg.

## Die Schnittliste

`cutlist_*.json` ist die **einzige Quelle der Wahrheit**. Alles andere wird
daraus erzeugt: Segmente, Video, Prüfbögen. Geändert wird die Schnittliste,
danach neu gerendert — nie am fertigen MP4.

Während der Iteration ist das gerenderte Ergebnis immer die nummerierte
Reviewfassung. Eine unnummerierte Version gilt erst nach ausdrücklicher
Freigabe als Endfassung und wird deshalb nicht parallel zu jeder Feedbackrunde
erzeugt.

Im Kopf steht das Projekt: `quellen` (der Materialordner, z. B.
`material/<projekt>`), `audio`, `ausgabe`, `ende_s`, `breite`/`hoehe`, `fps`,
`quell_fps`, `video_ausblende_s` (optional dazu `video_einblende_s`).

Darunter die Einstellungen, je eine Zeile:

```json
{"n": 17, "clip": "DATEINAME.MP4", "in": 0.40, "tempo": 0.5,
 "schnitt_bei": 42.176, "dauer": 3.541,
 "idee": "Detail in Zeitlupe. ACHTUNG: nur 0.4-2.2s brauchbar, danach laeuft der Schwenk aus dem Motiv."}
```

`n` ist die Szenennummer — sie muss eindeutig sein, weil `render.py` die
Segmente danach benennt und weil sie in Feedbackrunden die gemeinsame Sprache
ist. `in` ist der Einstiegszeitpunkt im Quellclip, `schnitt_bei` die Position
auf der Timeline (lückenlos an die vorige Einstellung anschließend), `dauer`
die Länge auf der Timeline. Die `idee` ist kein Zierrat — sie macht später
nachvollziehbar, was beim Ändern kaputtgeht, und unbrauchbare Clipbereiche
gehören als `ACHTUNG:` genau dorthin.

`tempo` ist optional und der wirksamste Hebel gegen Materialmangel: `0.5`
halbiert die Geschwindigkeit, verbraucht wird `dauer × tempo`. Bei 50-fps-Quelle
und 25-fps-Timeline wird aus jedem Quellframe genau ein Ausgabeframe — echte
Zeitlupe, nichts interpoliert.

Alle Felder mit Erklärung stehen in `cutlist.vorlage.json`.

### Hochkant aus Querformat

Steht in `breite`/`hoehe` ein anderes Seitenverhältnis als im Material — etwa
1080×1920 für Reels aus 16:9-Aufnahmen —, schneidet `render.py` jede
Einstellung zu, statt sie zu verzerren. Wohin, entscheiden drei optionale
Felder je Shot:

| Feld | Vorgabe | Bedeutung |
|---|---|---|
| `crop_x` | 0.5 | Mittelpunkt waagerecht, 0.0 = ganz links, 1.0 = ganz rechts |
| `crop_y` | 0.5 | Mittelpunkt senkrecht, 0.0 = oben, 1.0 = unten |
| `crop_zoom` | 1.0 | 1.0 = größtmöglicher Ausschnitt, größer = enger |

Die Werte sind relativ, nicht in Pixeln — die Schnittliste bleibt dadurch
unabhängig von der Quellauflösung. Bei gleichem Quell- und Zielverhältnis
ändert der Zuschnitt nichts.

Welcher Ausschnitt richtig ist, entscheidet das Bild: Bei einer Totale sitzt
das Motiv selten mittig. `sheet_crop.py` zeichnet den gewählten Ausschnitt als
Rahmen in den Quellframe und dunkelt alles außerhalb ab — ansehen, dann je
Szenennummer nachbessern.

```
.venv\Scripts\python.exe sheet_crop.py projekte/<projekt>/cutlist_v1.json
```

## Die PROJEKT.md

Neben den Schnittlisten liegt je Projekt eine `PROJEKT.md` — das
Materialprotokoll. Dort steht, was beim Sichten aufgefallen ist: welche Clips
Outtakes sind, ab welcher Sekunde eine Schärfefahrt vorbei ist, welche Takes
sich so ähnlich sehen, dass sie nie hintereinander stehen dürfen, wo
Drehort oder Kostüm wechseln.

Das lohnt sich ab der zweiten Fassung. Ohne diese Datei sucht man dieselben
unbrauchbaren Stellen bei jeder Iteration neu.

## Grenzen

- **Export nur nach DaVinci Resolve**, siehe unten. Für andere Programme gibt
  es keinen Weg; FCPXML wurde versucht und verworfen.
- **Originalton wird verworfen.** `render.py` kodiert die Segmente mit `-an` und
  legt nur die Musik darunter. Für Material, bei dem gesprochen wird, ist das
  falsch — eine zweite Tonspur mit `amix` und Ducking ist nicht gebaut.
- **Abweichende Seitenverhältnisse werden beschnitten, nicht gerahmt.** Ein
  Letterbox-Rahmen ist nicht gebaut, ebenso wenig ein animierter Schwenk
  innerhalb einer Einstellung (Ken Burns) — der Ausschnitt steht je Shot fest.
  Der Resolve-Export überträgt ihn nicht.
- **Zeitlupe nur bei passender Framerate.** Sauber ist sie, wenn `quell_fps`
  genau das Doppelte von `fps` ist (50→25, 60→30). Sonst interpoliert oder
  doppelt ffmpeg Frames.
- **Keine Bildstabilisierung.** War über ffmpeg/vid.stab eingebaut und wurde
  bewusst wieder entfernt: Der Gewinn war gering, und bei absichtlichen
  Kamerafahrten machte der Ausgleich das Bild schlechter, weil er die gewollte
  Bewegung nicht vom Wackeln trennen kann und dafür merklich hineinzoomen muss.
  Das gehört ins Schnitt- und Korrekturprogramm.

## Export nach DaVinci Resolve

Für Farbkorrektur und Feinschliff. Zwei Schritte:

```
.venv\Scripts\python.exe resolve_prep_slowmo.py projekte/<projekt>/cutlist_vN.json
```

Dieser Aufruf backt die Zeitlupen vor **und** stellt `resolve_build.py` samt
Pfad zur Schnittliste in Resolves Scripts-Ordner bereit. Danach in Resolve
**Workspace → Scripts → resolve_build**, Ausgabe in **Workspace → Console**.
Beim ersten Mal Resolve einmal neu starten, damit der Menüpunkt erscheint.

Das Skript legt ein Projekt an, baut die Timeline, legt die Musik auf A1 und
prüft anschließend die fertige Timeline gegen die Schnittliste. Bei Abweichung
speichert es nicht. Der Originalton der Clips wird nicht übertragen.

Zeitlupe muss vorgebacken werden, weil Resolves API keine
Geschwindigkeitsänderung setzen kann — das kostet Plattenplatz. Die Vorschau
ruckelt bei großem Material; das betrifft nur die Wiedergabe, nicht den
Export. Details in `CLAUDE.md`.

Quellmaterial wird nie verändert; alles Abgeleitete landet in eigenen Ordnern.

## Musikrechte und Personen

Die Musik in diesem Repository ist **Scratch** — Platzhalter, um das Timing zu
finden. Vor jeder Veröffentlichung ist sie zu lizenzieren oder zu ersetzen:
`analyze_music.py` auf den neuen Track anwenden, Raster ableiten, Schnittpunkte
umrechnen; die Reihenfolge der Einstellungen bleibt dabei erhalten, nur die
Längen verschieben sich. Und bei Material mit erkennbaren Personen — besonders
bei Veranstaltungen, wo Leute im Bild sind, die nicht für die Kamera dort waren
— ist vor der Veröffentlichung zu klären, wer einverstanden ist. Beim Schnitt
erledigt sich das nicht von selbst.

## Weiterlesen

`CLAUDE.md` enthält die ausführliche Arbeitsanweisung: den vollständigen Ablauf,
die Dramaturgie, die es zu befolgen lohnt, und die Fallstricke, die schon Zeit
gekostet haben. `AGENTS.md` ist die Kurzfassung davon für andere KI-Assistenten.
