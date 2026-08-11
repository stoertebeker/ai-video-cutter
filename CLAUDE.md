# Musikgeschnittene Videomontage — Werkzeugkette

Aus vielen kurzen Clips eine auf Musik geschnittene Montage bauen. Alles lokal,
keine API-Keys, keine Cloud.

Das Prinzip: **Claude übernimmt die Fleißarbeit und die Rhythmusarithmetik, der
Mensch entscheidet über Auswahl und Timing.** Jeder Schritt hinterlässt eine
Datei, die man anschauen kann — dadurch bleibt alles Kreative überprüfbar.

> Andere Agenten finden ihren Einstieg in `AGENTS.md` daneben.

## Aufbau

```
CLAUDE.md AGENTS.md          diese Doku
cutlist.vorlage.json         Vorlage für neue Projekte
*.py                         Werkzeuge, projektunabhängig
.venv/                       Python-Umgebung

<projekt>/                   ein Projekt: Quellclips + Schnittlisten + PROJEKT.md
audio/                       Musik und Analysen
out/                         fertige Videos
sheets/<projekt>/            Kontaktbögen, Sequenz- und Prüfbögen
frames/<projekt>/            Einzelframes
segments/<fassung>/          Rendersegmente
verify/<projekt>/            Prüfframes
```

Die letzten drei sind reine Zwischenstände und jederzeit löschbar.

**Ein Projekt besteht aus einem Ordner mit Quellclips, einer oder mehreren
`cutlist_*.json` darin und einer `PROJEKT.md`** mit dem, was für dieses
Material gilt: Drehorte, unbrauchbare Clipbereiche, Dopplungen. Am Code ist für
ein neues Projekt nichts zu ändern.

## Umgebung

| Werkzeug | Wofür |
|---|---|
| ffmpeg / ffprobe 7.1.1 | Frames ziehen, schneiden, rendern |
| librosa 0.11 | Beat- und Lautstärkeanalyse |
| Pillow 12.3 | Kontaktbögen bauen |
| yt-dlp | Scratch-Track ziehen |
| Kinocut 1.13.1 | Metadaten, QC (optional) |

Immer über die Venv aufrufen: `.venv\Scripts\python.exe <skript>.py`

Pakete via `pip install "kinocut[image,audio-enhanced,audio-analysis]" yt-dlp`.
Mehrere Extras gehören in **einen** Aufruf — zwei getrennte Aufrufe
installieren nur den letzten. Und `kinocut doctor` nennt für librosa das
falsche Extra: es sagt `audio-enhanced`, richtig ist `audio-analysis`.

Kinocut läuft unter Windows **nicht** als MCP-Server: `projectstore/store.py`
importiert `fcntl` (POSIX-only), und `__main__.py:102` verschluckt den echten
ImportError hinter der irreführenden Meldung „MCP mode requires the 'mcp'
package". Die CLI funktioniert vollständig — nicht via `claude mcp add`
registrieren.

## Ablauf

### 1. Musik zuerst, nicht das Bild

Die Musik gibt Länge und Schnittraster vor.

```
yt-dlp -f bestaudio -x --audio-format wav -o "audio/scratch.%(ext)s" <URL>
python analyze_music.py audio/scratch.wav > audio/analyse.json
python plan_raster.py audio/analyse.json 4
```

`analyze_music.py` liefert Tempo, Beatzeiten, Onsets und RMS-Pegel je halbe
Sekunde. Drei Werte daraus entscheiden:

- **`beat_jitter`** — Streuung der Beatabstände. Unter ~0,08 ist das Raster
  belastbar. Darüber (rubato, freies Tempo) taugt Beat-Tracking nicht, dann
  nach Gehör oder nach RMS-Verlauf schneiden.
- **`rms_db_pro_halbsekunde`** — wo der Höhepunkt liegt. Dorthin die beste
  Einstellung, sonst nirgends. Manche Stücke haben zwei; dann bekommt jeder
  einen eigenen Hero-Shot.
- **Nutzbares Ende** — Ausblenden unter ca. −40 dB sind stumm. `ende_s` danach
  bemessen, nicht nach der Dateilänge.

`plan_raster.py` nimmt **jeden vierten erkannten Beat** als Taktgrenze und
schreibt den RMS-Pegel daneben. Ein gerechnetes Raster (`4 × 60 / BPM`) läuft
bei frei gespielter Musik gegen Ende aus dem Takt; die erkannten Beats tun das
nicht. Die Tabelle ist die Vorlage für `schnitt_bei`.

Achtung: PowerShells `>` schreibt UTF-8 **mit BOM**. JSON danach mit
`encoding="utf-8-sig"` lesen, sonst scheitert `json.load`.

### 2. Material sichten — Claude schaut wirklich hin

```
python make_contactsheets.py <projekt> 3 5              # Überblick
python make_contactsheets.py <projekt> 8 6 <filter>     # dicht, gefiltert
```

Baut beschriftete Kontaktbögen in `sheets/<projekt>/`. Diese Bilder liest
Claude mit dem Read-Tool **als Bilder**. Das ist der Kern des Ganzen: Ohne
diesen Schritt kennt Claude nur Dateinamen und rät.

**Zwei Durchgänge, nicht einer.** Drei Frames je Clip reichen, um Drehorte,
Kostümvarianten und Dopplungen zu sortieren. Für jede Einstellung, die
tatsächlich in den Schnitt soll, danach **acht Frames**. Erst dann sieht man
die Bewegung *innerhalb* der Einstellung, und die entscheidet über den
Einstiegszeitpunkt. Was der dichte Durchgang aufdeckt und der grobe nicht:

- Schwenks, die aus dem Motiv herauslaufen
- Schärfefahrten am Clipanfang
- Clips, die nach zwei Dritteln leer sind (nur noch Bokeh)
- abgebrochene Takes — Bewegung beginnt, wird zurückgenommen, startet neu

Alle vier haben schon Einstellungen gekostet, die neu gesetzt werden mussten.

Befunde gehören in die `PROJEKT.md` des Ordners und als `ACHTUNG:` in den
Kommentar der Schnittliste — sonst greift die nächste Sitzung wieder hinein.

### 3. Schnittliste schreiben

`cutlist_*.json` im Projektordner ist die einzige Quelle der Wahrheit. Aufbau
und alle Felder stehen in `cutlist.vorlage.json`.

Pro Einstellung: Quellclip, Einstiegszeitpunkt, Position auf der Timeline,
Dauer, optional `tempo`, plus ein Kommentar, warum die Einstellung dort steht.
Der Kommentar ist kein Zierrat — er macht später nachvollziehbar, was beim
Ändern kaputtgeht.

Dramaturgie, die sich bewährt hat: ruhig und lang beginnen, Schnittfrequenz mit
der Lautstärke erhöhen, beste Einstellung exakt auf den RMS-Peak, danach eine
lange ruhige Einstellung zum Ausblenden. Ortsneutrale Detailaufnahmen taugen
als Brücke zwischen zwei Drehorten.

Zwei Einstellungen desselben Motivs nie direkt hintereinander — das liest sich
als Fehlschnitt, nicht als Schnitt. Ein Zwischenschnitt genügt, um aus einer
Dopplung zwei Momente zu machen.

### 3b. Zeitlupe — gegen Materialmangel

`"tempo": 0.5` halbiert die Geschwindigkeit. Bei 50-fps-Quelle und
25-fps-Timeline wird **jeder Quellframe zu genau einem Ausgabeframe**: echte
Zeitlupe, nichts interpoliert, kein Ruckeln.

Eine Einstellung von 3,5 s verbraucht damit nur 1,75 s Quellmaterial. Bei zu
wenig Material ist das der wirksamste Hebel. Ruhige Einstellungen und
Detailaufnahmen in Zeitlupe, Akzente und Bewegung in Echtzeit.

`verbraucht = dauer * tempo` — `validate_cutlist.py` rechnet es mit.

ffmpeg-Falle: `-t` muss **vor** `-i` stehen. Dahinter begrenzt es die Ausgabe
und schneidet die von `setpts` gedehnte Zeitlupe wieder auf die Quelldauer
zurück. Das Video ist dann halb so lang, der Container zeigt trotzdem die volle
Länge, weil die Tonspur sie vorgibt.

### 4. Rendern und prüfen

```
python validate_cutlist.py <projekt>/cutlist_v1.json   # IMMER vor dem Rendern
python render.py           <projekt>/cutlist_v1.json
python sheet_sequence.py   <projekt>/cutlist_v1.json
python verify_cuts.py      <projekt>/cutlist_v1.json
```

`validate_cutlist.py` prüft: lückenlose Schnittpunkte, kein Clip liest über
sein Quellende hinaus, zwei Verwendungen desselben Clips überlappen sich nicht,
Summe der Dauern gleich `ende_s`. Dazu listet es ungenutzte Clips. Ein
Renderlauf dauert Minuten, die Prüfung Sekunden.

`render.py` kodiert jedes Segment einzeln mit identischen Parametern, hängt sie
per concat-Demuxer aneinander und legt die Musik mit Ausblende darunter.
Einzelsegmente statt eines großen filter_complex, weil Fehler dann lokal
bleiben und sich einzelne Segmente austauschen lassen.

`sheet_sequence.py` zieht aus dem **fertigen Video** einen Frame je Einstellung.
Schnellste Kontrolle der Abfolge — deckt Dopplungen auf, die in der
Schnittliste unsichtbar sind: Zwei Takes derselben Situation stehen dort als
verschiedene Dateinamen, sehen nebeneinander aber aus wie ein Fehlschnitt.

`verify_cuts.py` zieht Frames vor und nach jedem Schnitt. Der Abstand ist
0,18 s und darf nicht kleiner werden: Bei 25 fps ist ein Frame 0,04 s, dazu
kommt Quantisierungsdrift. Unter ~0,15 s erwischt man die falsche Seite und
diagnostiziert einen Fehler, der nicht existiert.

## Neues Projekt aufsetzen

1. Quellclips in einen eigenen Ordner, Musik nach `audio/`.
2. `cutlist.vorlage.json` dorthin kopieren als `cutlist_v1.json`, Kopf
   ausfüllen: `quellen`, `audio`, `ausgabe`, Auflösung, Framerate.
3. `analyze_music.py`, dann `plan_raster.py` — Raster ableiten.
4. Kontaktbögen bauen (erst grob, dann dicht), ansehen, Einstellungen setzen.
5. `validate_cutlist.py`, rendern, `sheet_sequence.py`, iterieren.
6. Befunde zum Material in `<projekt>/PROJEKT.md` festhalten.

Erkannt werden `.mp4 .mov .mts .mkv .avi`, Groß- und Kleinschreibung egal.

## Wenn das Material anders ist

**Seitenverhältnis.** `breite`/`hoehe` umstellen. `render.py` skaliert hart auf
dieses Ziel — bei gemischten Quellformaten wird verzerrt, nicht beschnitten.
Für gemischtes Material den `scale`-Filter um
`force_original_aspect_ratio=decrease` plus `pad` ergänzen.

**Framerate.** Zeitlupe ist nur sauber, wenn Quell-fps genau das Doppelte der
Timeline-fps sind (50→25, 60→30). Sonst interpoliert oder doppelt ffmpeg
Frames. Vorher mit `ffprobe` prüfen.

**Originalton.** `render.py` verwirft den Ton der Clips (`-an`) und legt nur
die Musik darunter. Für Material, bei dem gesprochen wird — Reaktionen,
Kommentare, Atmo — ist das falsch. Dann braucht `render.py` eine zweite
Tonspur: Clipton behalten, per `amix` unter die Musik legen, Musik mit
`sidechaincompress` ducken. Das ist **nicht gebaut**.

**Dramaturgie.** Trägt die Musik alles, gilt der Ablauf oben. Bei einer
Veranstaltung trägt oft der Inhalt: Chronologie, Reaktionen, Pointen. Das
Beatraster bleibt nützlich, aber „beste Einstellung auf den RMS-Peak" wird zu
„beste Reaktion auf den RMS-Peak" — und wenn eine Pointe zwischen zwei Takten
liegt, gewinnt die Pointe.

**Erkennbare Personen.** Bei Veranstaltungsmaterial sind Leute im Bild, die
nicht für die Kamera dort waren. Vor Veröffentlichung klären, wer einverstanden
ist — das erledigt sich beim Schnitt nicht von selbst.

## Bewusst nicht hier

- **Bildstabilisierung.** War über ffmpeg/vid.stab eingebaut und wurde wieder
  entfernt: Der Gewinn war gering, und bei absichtlichen Kamerafahrten machte
  der Ausgleich das Bild schlechter statt besser, weil er die gewollte Bewegung
  nicht vom Wackeln trennen kann — und dafür merklich hineinzoomen muss.
  Gehört ins Schnitt- und Korrekturprogramm, nicht in diese Kette.
  **Nicht wieder einbauen**, ohne dass danach gefragt wird.

## Noch nicht gebaut

- **Export in ein Schnittprogramm.** Der frühere FCPXML-Export und die
  Resolve-Anbindung sind entfernt und werden neu gemacht.
- **Originalton**, siehe oben.
- **Gemischte Seitenverhältnisse**, siehe oben.

## Umgangsformen

- **Quellmaterial nie verändern.** Alles Abgeleitete in eigene Ordner.
- **Nur die Schnittliste von Hand ändern**, dann neu rendern. Nie im MP4
  herumfummeln.
- **Behauptungen belegen.** Wenn der Schnitt sitzen soll: Frames ziehen und
  anschauen. Wenn von Drift die Rede ist: Segmentdauern messen. Vermutung und
  Messung auseinanderhalten und Korrekturen offen benennen.
- **Zurückhaltung beim Urteil über Schnitte.** Claude kann Raster rechnen,
  Dopplungen finden, Kontinuitätsbrüche bemerken und Frames beschreiben. Ob ein
  Schnitt *sitzt*, entscheidet der Mensch.
- **Scratch-Musik ist Platzhalter.** Vor Veröffentlichung lizenzieren oder
  ersetzen; `analyze_music.py` auf den neuen Track anwenden und die
  Schnittpunkte umrechnen.
