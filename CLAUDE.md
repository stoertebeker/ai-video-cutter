# Musikgeschnittene Videomontage — Werkzeugkette

Aus vielen kurzen Clips eine auf Musik geschnittene Montage bauen. Alles lokal,
keine API-Keys, keine Cloud.

Das Prinzip: **Claude übernimmt die Fleißarbeit und die Rhythmusarithmetik, der
Mensch entscheidet über Auswahl und Timing.** Jeder Schritt hinterlässt eine
Datei, die man anschauen kann — dadurch bleibt alles Kreative überprüfbar.

> Andere Agenten finden ihren Einstieg in `AGENTS.md` daneben.

## Zuerst: `git pull`

**Zu Beginn jeder Sitzung einmal aktualisieren.** Die Werkzeugkette wird
weiterentwickelt; ohne Pull fehlen dir möglicherweise Funktionen oder
Fehlerkorrekturen, und du baust etwas nach, das es schon gibt.

Schlägt der Pull wegen lokaler Änderungen fehl: erst klären, was geändert
wurde, statt blind zu überschreiben. Projekte sind nie betroffen — das
Repository enthält ausschließlich das Werkzeug.

## Aufbau

**Das Git-Repository enthält ausschließlich das Werkzeug.** Kein Projekt landet
darin — weder Rohmaterial noch Musik noch Schnittlisten, Projektdokumentation
oder fertige Videos.

```
                             ── im Repository ──
README.md                    Übersicht für Menschen
CLAUDE.md AGENTS.md          Arbeitsanweisung für Agenten
cutlist.vorlage.json         Vorlage für die Schnittliste
PROJEKT.vorlage.md           Vorlage für das Materialprotokoll
*.py                         Werkzeuge, projektunabhängig

                             ── daneben, nicht versioniert ──
projekte/<name>/             cutlist_*.json + PROJEKT.md
material/<name>/             Quellclips
audio/<name>/                Musik und Analysen je Projekt
audio/musikvorschlaege/      lizenzierte Tracks, projektübergreifend
out/                         nummerierte Reviews + freigegebene Endfassungen
sheets/<name>/               Kontaktbögen, Sequenz- und Prüfbögen
frames/<name>/               Einzelframes
segments/<fassung>/          Rendersegmente
verify/<name>/               Prüfframes
resolve_zwischen/<fassung>/  Zeitlupen-Zwischenclips für den Resolve-Export
.venv/                       Python-Umgebung
```

Die letzten fünf sind Zwischenstände und jederzeit löschbar — sie entstehen aus
Schnittliste plus Quellmaterial neu.

**Ein Projekt ist auf vier Orte verteilt**, und alle vier stehen als Pfad im
Kopf der Schnittliste: `projekte/<name>/` für die Schnittlisten selbst,
`quellen` zeigt auf `material/<name>/`, `audio` auf die Musikdatei, `ausgabe`
auf das Ziel unter `out/`. Fehlt `quellen`, brechen `render.py` und
`validate_cutlist.py` mit Meldung ab; fehlt eine der Dateien, meldet es
`validate_cutlist.py` vor dem Rendern.

Die `.gitignore` arbeitet als Positivliste: erst wird alles ausgeschlossen,
dann gezielt das Werkzeug wieder hereingenommen. Ein neues Projekt landet
dadurch von selbst außerhalb der Versionierung — niemand muss daran denken.

Am Code ist für ein neues Projekt nichts zu ändern.

## Umgebung

| Werkzeug | Wofür |
|---|---|
| ffmpeg / ffprobe 7.1.1 | Frames ziehen, schneiden, rendern |
| librosa 0.11 | Beat- und Lautstärkeanalyse |
| Pillow 12.3 | Kontaktbögen bauen |
| yt-dlp | Scratch-Track ziehen |
| Kinocut 1.13.1 | Metadaten, QC (optional) |
| WhisperX 3.8.6 (separate Python-3.10-Venv) | Wortgenaue Vlog-Transkripte |

Immer über die Venv aufrufen: `.venv\Scripts\python.exe <skript>.py`

Ausnahme ist `transcribe_clips.py`: WhisperX unterstützt die Python-Version
der normalen Venv nicht. Einrichtung und Aufruf der getrennten
`.venv-whisperx` stehen in `WHISPERX.md`.

### Encoder: GPU oder CPU

`encoder.py` hält die Videoparameter für `render.py` und
`make_numbered_review.py` an **einer** Stelle. Das ist kein Selbstzweck:
`render.py` kodiert jedes Segment einzeln und fügt sie per concat-Demuxer
zusammen — das funktioniert nur, wenn alle Segmente exakt gleich kodiert sind.

Voreinstellung ist **GPU** (`h264_nvenc`, rund 4× schneller als x264 mit
`preset slow`, gemessen). Für die Endfassung auf CPU umschalten:

```
$env:ENCODER="cpu"; .venv\Scripts\python.exe render.py projekte/<p>/cutlist_vN.json
```

Der Grund für den Schalter: NVENC ist pro Bit schwächer als x264. Bei
Reviewfassungen ist das gleichgültig, in dunklen Bildern — Nacht-, Fackel- und
Kerzenlicht — wird es als Banding sichtbar. `-spatial-aq`/`-temporal-aq`
dämpfen das, heben es aber nicht auf. GPU-Dateien werden zudem etwa 60 %
größer als CPU-Dateien gleicher Qualitätsstufe.

Ein Wechsel des Encoders mitten in einer Fassung ist unschädlich für den
concat — aber die Segmente in `segments/<fassung>/` stammen dann aus
verschiedenen Encodern. `render.py` löscht den Ordner ohnehin bei jedem Lauf
neu, das Problem entsteht also nicht von selbst.

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
python analyze_music.py audio/<projekt>/track.wav > audio/<projekt>/analyse.json
python plan_raster.py audio/<projekt>/analyse.json 4
```

Liegt die Musik noch nicht als Datei vor, holt `yt-dlp` einen Scratch-Track:

```
yt-dlp -f bestaudio -x --audio-format wav -o "audio/<projekt>/scratch.%(ext)s" <URL>
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

**Und Schnittlisten nie über einen PowerShell-JSON-Umweg bearbeiten**
(`Get-Content -Raw | ConvertFrom-Json | ConvertTo-Json | Out-File`). Windows
PowerShell 5.1 liest UTF-8 ohne BOM als CP1252; aus `Luhmühlen` wird dabei
`LuhmÃ¼hlen`, und im eingebrannten Titel fällt das erst am fertigen Video auf.
Schnittlisten direkt als Datei schreiben.

### 2. Material sichten — Claude schaut wirklich hin

```
python make_contactsheets.py material/<projekt> 3 5           # Überblick
python make_contactsheets.py material/<projekt> 8 6 <filter>  # dicht, gefiltert
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

Zwei Einstellungen, die einander **zum Verwechseln ähneln**, nicht direkt
hintereinander — das liest sich als Fehlschnitt, nicht als Schnitt. Gemeint
sind zwei Takes derselben Situation aus fast gleicher Position: Der Sprung
wirkt dann wie ein Wiedergabefehler. Im Schnitt heißt das Jump Cut, und die
Faustregel dagegen ist der deutliche Wechsel von Blickwinkel oder
Einstellungsgröße (klassisch etwa 30° Kamerawinkel). Ein Zwischenschnitt tut
es auch.

**Kein Verbot ist das für dasselbe Thema.** Mehrere Einstellungen eines
Konzerts, eines Wettkampfs, eines Marktes hintereinander sind in einer Montage
normal und oft gewollt — sie bauen einen Block auf, statt ihn zu zerstreuen.
Verlangt der Mensch einen Cluster, ist der Cluster richtig; dann gilt nur
noch, dass die Einstellungen darin unterscheidbar bleiben. Diese Regel ist
eine gestalterische Faustregel, **keine Prüfregel** — `validate_cutlist.py`
prüft sie nicht und kann sie nicht prüfen.

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
python validate_cutlist.py      projekte/<projekt>/cutlist_v1.json   # IMMER zuerst
python sheet_crop.py            projekte/<projekt>/cutlist_v1.json   # nur bei Formatwechsel
python render.py                projekte/<projekt>/cutlist_v1.json
python make_numbered_review.py  projekte/<projekt>/cutlist_v1.json
python sheet_sequence.py        projekte/<projekt>/cutlist_v1.json
python verify_cuts.py           projekte/<projekt>/cutlist_v1.json
```

`validate_cutlist.py` prüft: lückenlose Schnittpunkte, kein Clip liest über
sein Quellende hinaus, zwei Verwendungen desselben Clips überlappen sich nicht,
Summe der Dauern gleich `ende_s`. Dazu listet es ungenutzte Clips. Ein
Renderlauf dauert Minuten, die Prüfung Sekunden.

`render.py` kodiert jedes Bildsegment einzeln mit identischen Parametern, hängt
sie per concat-Demuxer aneinander und mischt danach Musik sowie optional die
unabhängige `originalton`-Timeline. `audio_timeline.py` setzt Quell- und
Timeline-Zeiten, kurze Schnittfades, Pegel, Sidechain-Ducking und Limiter um.
Fehlt `originalton`, bleibt der bisherige Musikfilter unverändert.
`overlay_timeline.py` baut optionale Einblendungen im selben finalen Pass:
`route_progress` zeichnet aus GPX plus Aufnahmezeit eine lokale Minikarte mit
Zeit seit Start und Kilometerstand; `image` ist der generische Weg für Fotos
in späteren Vlogs. Assets landen unter `sheets/<projekt>/overlays_<fassung>/`.
Das einzelne Feld `audio` bleibt der Legacy-Weg. Lange Vlogs können es durch
eine `musik`-Timeline ersetzen: mehrere Tracksegmente werden per Quell- und
Timeline-Zeit platziert, Überlappungen mit Fades ergeben Crossfades. Die
Originalton-Timeline duckt anschließend den bereits zusammengesetzten Mix.
Einzelsegmente statt eines großen filter_complex, weil Fehler dann lokal
bleiben und sich einzelne Segmente austauschen lassen.

`sheet_crop.py` braucht nur die Quellclips und läuft deshalb **vor** dem
Rendern. Es zeichnet je Einstellung den gewählten Bildausschnitt als Rahmen
ins Quellbild — nötig, sobald Quell- und Zielformat auseinanderfallen, sonst
überflüssig. Siehe „Wenn das Material anders ist".

`sheet_sequence.py` zieht aus dem **fertigen Video** einen Frame je Einstellung.
Schnellste Kontrolle der Abfolge — deckt Dopplungen auf, die in der
Schnittliste unsichtbar sind: Zwei Takes derselben Situation stehen dort als
verschiedene Dateinamen, sehen nebeneinander aber aus wie ein Fehlschnitt.

`verify_cuts.py` zieht Frames vor und nach jedem Schnitt. Der Abstand ist
0,18 s und darf nicht kleiner werden: Bei 25 fps ist ein Frame 0,04 s, dazu
kommt Quantisierungsdrift. Unter ~0,15 s erwischt man die falsche Seite und
diagnostiziert einen Fehler, der nicht existiert.

### 4a. Abnahme mit Szenennummern

`make_numbered_review.py` ist ein **zweiter Schritt nach dem Rendern**, kein
Renderschalter: Es liest die fertige Datei aus `ausgabe`, blendet je
Einstellung die Nummer `n` als Untertitel ein — framegenau an den Shotgrenzen
— und schreibt `<ausgabe>_nummeriert.mp4`. Bild wird neu kodiert, Ton
durchgereicht. Fehlt die gerenderte Datei, bricht es ab.

Diese nummerierte Datei ist die, die man zur Abnahme zeigt. Der Grund ist
schlicht: Rückmeldungen lauten damit „ändere Szene 3" statt „die Stelle nach
dem Baum", und beide Seiten meinen dasselbe.

Nach jeder Änderung an der Schnittliste neu erzeugen — verschobene oder
eingefügte Einstellungen ändern die Zuordnung, alte Zahlen gelten nicht
weiter. Die unnummerierte Endfassung braucht keinen eigenen Schritt: Sie ist
die Datei, die `render.py` ohnehin schreibt.

Für eine Abnahme inklusive Titel/Abspann akzeptiert das Skript zusätzlich
`--source out/<fassung>_titel.mp4`. So wird die bereits betitelte Fassung
nummeriert, ohne die Schnittliste oder ihre eigentliche `ausgabe` umzubiegen.

`n` muss eindeutig sein, sonst überschreiben sich Rendersegmente stillschweigend
und die Verständigung bricht zusammen. `validate_cutlist.py` prüft das und
weist zusätzlich darauf hin, wenn die Nummern nicht aufsteigend laufen.
- Falls ein technischer Zwischenschritt vorübergehend ein unbeschriftetes
  Video erzeugt, ist es nur ein internes Hilfsartefakt und keine abzugebende
  Fassung. Der Arbeitsablauf soll nach Möglichkeit direkt in die nummerierte
  Reviewdatei rendern.

### 4b. Titel und Abspann

```
python make_titles.py projekte/<projekt>/cutlist_vN.json
```

Wie `make_numbered_review.py` ein **zweiter Schritt nach dem Rendern**: liest
die Datei aus `ausgabe`, brennt die Texte ein und schreibt
`<ausgabe>_titel.mp4`. Die Quelle bleibt unangetastet.

**Die Texte stehen in der Schnittliste, nicht im Skript** — Feld `titel` mit
`text`, optionaler `unterzeile`, `bei` und `dauer`. Sonst wäre jede Fassung
wieder Handarbeit, und genau das soll die Kette verhindern. Alles
Gestalterische — Schrift, Größen, Sperrung — steht dagegen am Kopf von
`make_titles.py` und gilt projektübergreifend.

Ein Eintrag mit `"stil": "credit"` wird klein unten rechts gesetzt. Das ist
für einen Urheberhinweis im schwarzen Nachlauf gedacht; ohne das Feld bleibt
der Titel wie bisher zentriert.

**Die Blendendauer ist die Ausnahme davon.** Sie steht dort als Standard
(`EINBLENDE_MS`, `AUSBLENDE_MS`), lässt sich aber je Titel über
`einblende_ms`/`ausblende_ms` überschreiben — anders als eine Schriftwahl
hängt sie nicht am Haus-Stil, sondern an der Filmlänge. Eine Sekunde
Ausblende ist bei sieben Minuten unauffällig und bei einem 23-Sekunden-Trailer
ein Viertel des Abspanns.

`nachlauf_schwarz_s` hängt Schwarzbild hinter `ende_s` an. Das ist der Trick
für einen Abspann, der die Schlussszene noch begleitet und erst danach allein
steht: `bei` vor `ende_s` legen, `dauer` darüber hinausreichen lassen. Ohne
den Nachlauf endet der Film in dem Moment, in dem das Bild schwarz wird — der
Name wäre dann nur über dem ausblendenden Bild zu sehen.

Rechenbeispiel bei `ende_s` 426 und `video_ausblende_s` 9: Ein Abspann mit
`bei` 423 und `dauer` 5 läuft von 423 bis 428. Bis 426 liegt er über der
ausblendenden Szene, danach zwei Sekunden im Schwarzen. `nachlauf_schwarz_s`
3 gibt ihm den Platz dafür plus eine Sekunde Nachlauf.

`make_titles.py` prüft vor dem Kodieren, dass kein Titel hinter dem Filmende
liegt — sonst wäre er im Ergebnis unsichtbar, ohne dass jemand den Fehler
bemerkt. Ebenso, dass Ein- und Ausblende zusammen kürzer sind als die
Standzeit; sonst stünde der Titel nie voll im Bild.

Reihenfolge der Schritte: erst `render.py`, dann wahlweise
`make_numbered_review.py` für die Abnahme **oder** `make_titles.py` für die
Endfassung. Beide auf dieselbe gerenderte Datei anzuwenden ergibt keinen
Sinn — Szenennummern gehören nicht in die Endfassung.

## Export nach DaVinci Resolve

Für den finalen Schnitt und die Farbkorrektur, nicht als Ersatz für die
mp4-Kette oben. Zwei Skripte:

```
.venv\Scripts\python.exe resolve_prep_slowmo.py projekte/<projekt>/cutlist_vN.json
```

Dieser eine Aufruf erledigt alles außerhalb von Resolve: Er backt jede
Zeitlupen-Einstellung zu einem ProRes-Zwischenclip, kopiert `resolve_build.py`
in Resolves Scripts-Ordner und legt den Pfad zur Schnittliste als
`resolve_cutlist.txt` daneben.

Danach in Resolve **Workspace > Scripts > resolve_build**. Nichts von Hand
einzutragen, kein Projekt vorher zu öffnen — das Skript legt selbst eins an.
Beim ersten Mal Resolve nach dem Kopieren einmal neu starten, sonst fehlt der
Menüpunkt.

Dass die Bereitstellung am Vorbereitungsschritt hängt, ist Absicht: So kann in
Resolves Ordner keine veraltete Kopie liegenbleiben und kein Pfad auf ein
früheres Projekt zeigen.

Externes Scripting ist Studio-only. Über `Workspace > Scripts` gestartete
Skripte laufen aber auch in der freien Edition — Resolve stellt dort das
globale `resolve`-Objekt bereit, kein `GetResolve()`-Umweg nötig.

Übertragen wird Bild auf V1 und Musik auf A1; der Originalton der Clips bleibt
draußen. Nach dem Bauen liest das Skript die Timeline zurück und vergleicht
Framezahl je Clip, lückenlosen Anschluss, Gesamtlänge und Lage der Musik mit
der Schnittliste. Bei Abweichung meldet es Shot und Differenz und **speichert
das Projekt nicht** — ein „OK" am Ende ist damit belastbar.

### Zeitlupe muss vorgebacken werden

Resolves Scripting-API kann die Geschwindigkeit eines Timeline-Clips **nicht**
setzen. `TimelineItem.SetProperty()` kennt nur `RetimeProcess`, das die
Interpolationsart eines bereits bestehenden Wechsels regelt; ein `Speed`-Wert
oder `ChangeSpeed()` existiert nirgends. Geprüft im Scripting-SDK unter
`%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting`.

Dazu kommt: Die Resolve-Timeline läuft in `quell_fps`. Der Trick aus
`render.py`, Zeitlupe kostenlos aus dem Unterschied zwischen Quell- und
Render-Framerate zu gewinnen, greift dort nicht mehr.

Deshalb `resolve_prep_slowmo.py`: gleiche ffmpeg-Kette wie `render.py`, aber
Ziel-Framerate = Quell-Framerate und ohne Skalierung, als ProRes.
`resolve_build.py` hängt den fertig verlangsamten Clip mit Tempo 1.0 ein.

Zwei Kosten: Die Farbkorrektur läuft für diese Einstellungen auf dem
Zwischencodec statt auf der Kameradatei, und ProRes braucht **viel** Platz —
bei 4K-Material einige GB je Minute Zeitlupe. `PRORES_PROFIL` am Kopf des
Skripts senkt das (3 = 422 HQ, 2 = 422, 0 = Proxy).

### Verworfen — nicht erneut versuchen

**FCPXML-Import.** Kam strukturell korrekt an, aber Resolve verknüpfte die
Clips nicht gegen den Media Pool; mit `importSourceClips=True` blieb die
Timeline leer. Das Problem liegt in Resolves Konformierung, nicht in der
Datei. Ohne `<adjust-timeMap>` überträgt FCPXML zudem keine Zeitlupe.

**`recordFrame` je Clip.** Die API-Dokumentation sagt nicht, ob absolut oder
timeline-relativ gezählt wird. `resolve_build.py` verzichtet darauf und hängt
sequenziell an — dokumentiertes Verhalten, das diese Annahme nicht braucht.

**`endFrame` zählt einschließlich**: `{"startFrame": 0, "endFrame": 23}` sind
24 Frames. Steht nur im SDK-Beispiel `7_add_subclips_to_timeline.py`.

### Die Timeline ruckelt in der Vorschau

Bei hoher Auflösung und Bildrate schafft Resolve die Echtzeitwiedergabe oft
nicht; es verwirft Bildframes, und der Ton stottert hörbar mit. **Das ist ein
Wiedergabe-, kein Datenproblem** — der Export ist nicht betroffen. Wer die
Ursache im Schnitt sucht, verliert Zeit; der schnellste Gegenbeweis ist das
gerenderte MP4 aus derselben Schnittliste.

Abhilfe: `Wiedergabe → Proxy-Modus → Halbe Auflösung`; oder Media Pool
markieren und **Optimierte Medien generieren** (Format und Auflösung in den
Projekteinstellungen unter *Master-Einstellungen*), danach `Wiedergabe →
Optimierte Medien verwenden`; oder `Wiedergabe → Render-Cache → Smart`.
Beim Rendern nimmt Resolve wieder die Originaldateien.

## Neues Projekt aufsetzen

1. Quellclips nach `material/<projekt>/`, Musik nach `audio/<projekt>/`.
2. `cutlist.vorlage.json` nach `projekte/<projekt>/cutlist_v1.json` kopieren, Kopf
   ausfüllen: `quellen` (= `material/<projekt>`), `audio`, `ausgabe`,
   Auflösung, Framerate.
3. `analyze_music.py`, dann `plan_raster.py` — Raster ableiten.
4. Kontaktbögen bauen (erst grob, dann dicht), ansehen, Einstellungen setzen.
5. `validate_cutlist.py`, bei Formatwechsel zusätzlich `sheet_crop.py`,
   nummerierte Reviewfassung rendern, `sheet_sequence.py`, `verify_cuts.py`,
   iterieren.
6. Nach ausdrücklicher Freigabe einmalig die unnummerierte Endfassung rendern.
7. Befunde zum Material in `projekte/<projekt>/PROJEKT.md` festhalten —
   `PROJEKT.vorlage.md` als Gerüst kopieren.

Erkannt werden `.mp4 .mov .mts .mkv .avi`, Groß- und Kleinschreibung egal.

## Wenn das Material anders ist

**Seitenverhältnis.** `breite`/`hoehe` umstellen. `render.py` schneidet jede
Einstellung zuerst auf das Zielverhältnis zu (`crop`) und skaliert erst
danach. Verzerrt wird dadurch nichts, auch nicht bei gemischten Quellformaten
— was nicht ins Zielverhältnis passt, fällt weg. Wer stattdessen rahmen will
(Letterbox), bräuchte `force_original_aspect_ratio=decrease` plus `pad`; das
ist **nicht gebaut**.

**Formatwechsel quer → hochkant** ist ein anderer Fall und wird von `pad`
falsch gelöst: Querformatmaterial in einem 1080×1920-Rahmen ergibt damit ein
Briefmarkenbild zwischen zwei schwarzen Flächen. Gebraucht wird ein
Bildausschnitt, also `crop` vor dem `scale` — **das ist gebaut.** `breite`/
`hoehe` auf 1080×1920 stellen, den Rest regeln drei optionale Felder je Shot:

| Feld | Vorgabe | Bedeutung |
|---|---|---|
| `crop_x` | 0.5 | Mittelpunkt waagerecht, 0.0 = ganz links, 1.0 = ganz rechts |
| `crop_y` | 0.5 | Mittelpunkt senkrecht, 0.0 = oben, 1.0 = unten |
| `crop_zoom` | 1.0 | 1.0 = größtmöglicher Ausschnitt im Zielformat, größer = enger |

**Wechselnde Telefonlage innerhalb eines Clips.** Dafür den Clip an den
Lagewechseln in mehrere Shots teilen und nur den kopfstehenden Abschnitten
`"rotation": 180` geben. Die Korrektur läuft vor crop/scale und verändert das
Quellmaterial nicht. Andere Winkel sind bewusst nicht zugelassen: 90/270 Grad
würden die Bildmaße tauschen und brauchen eine eigene Formatentscheidung.

Relative Werte, keine Pixel — die Schnittliste bleibt dadurch unabhängig von
der Quellauflösung. `render.py` rechnet die Ausschnittmaße in ffmpegs eigenen
Variablen `iw`/`ih` aus, ohne ffprobe. Stimmen Quell- und Zielverhältnis
überein und ist `crop_zoom` 1.0, ist der Filter exakt die Identität —
bestehende Projekte ändern sich dadurch nicht.

Bei Querformat in Hochkant nutzt der Ausschnitt die volle Bildhöhe; `crop_y`
bleibt dort ohne Wirkung, bis `crop_zoom` über 1.0 den Spielraum dafür
schafft. `validate_cutlist.py` sagt das, prüft die Wertebereiche und meldet
auch den häufigsten Fehler: abweichendes Zielformat, aber nirgends ein
`crop_x` gesetzt — dann steht alles auf Bildmitte.

Die Frage bleibt, **welcher** Ausschnitt: Bei einer Totale sitzt das Motiv
selten mittig, und die Antwort ist je Einstellung eine andere. Das ist
Handarbeit am Bild und nicht automatisierbar. `sheet_crop.py` macht sie
prüfbar — es zeichnet den gewählten Ausschnitt als Rahmen in den Quellframe
und dunkelt alles außerhalb ab:

```
python sheet_crop.py projekte/<projekt>/cutlist_vN.json
```

Ergebnis nach `sheets/<projekt>/crop_<fassung>_N.png`, als Bild ansehen und je
Szenennummer nachbessern („Szene 7 weiter nach links"). Ein animierter
Schwenk innerhalb einer Einstellung (Ken Burns) ist **nicht gebaut** — der
Ausschnitt steht je Shot fest.

**Framerate.** Zeitlupe ist nur sauber, wenn Quell-fps genau das Doppelte der
Timeline-fps sind (50→25, 60→30). Sonst interpoliert oder doppelt ffmpeg
Frames. Vorher mit `ffprobe` prüfen.

**Originalton.** `transcribe_clips.py` erzeugt clip-lokale WhisperX-JSONs mit
Wortzeitmarken; Einrichtung und Pilotablauf stehen in `WHISPERX.md`. Die daraus
gewählten Passagen stehen unabhängig von den Bildshots in `originalton`:
`clip`, Quell-`in`, Timeline-`schnitt_bei`, `dauer`, optional Segmentpegel und
kurze Fades. Damit bleiben Sprache und Atmo unter B-Roll erhalten. `render.py`
mischt die Segmente, duckt die Musik dynamisch und fängt Spitzen per Limiter ab.
Pausen innerhalb eines Segments werden weder erkannt noch entfernt.

Die Grundpegel stehen optional in `audio_mix`: Musik standardmäßig -18 dB,
Originalton 0 dB. Fehlendes oder leeres `originalton` aktiviert aus
Rückwärtskompatibilität exakt den alten Musikweg. `validate_cutlist.py` prüft
Quelldauer, Audiospur, Timeline-Grenzen, Fades, Pegel und eindeutige Nummern.

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

- **Originalton im Resolve-Export.** Die lokale MP4-Pipeline kann ihn samt
  Ducking rendern; `resolve_build.py` überträgt weiterhin nur Bild und Musik.
- **Rahmen statt beschneiden** (Letterbox/Pillarbox). Abweichende Formate
  werden zugeschnitten, siehe oben. Ebenso wenig gebaut ist ein animierter
  Schwenk innerhalb einer Einstellung (Ken Burns) — der Ausschnitt steht je
  Shot fest. Der Resolve-Export kennt die crop-Felder nicht: dort landet das
  Material ungeschnitten, der Ausschnitt wird in Resolve gesetzt.
- **Geschwindigkeitsänderung per Resolve-API.** Siehe „Export nach DaVinci
  Resolve" oben — die Scripting-API hat dafür keinen dokumentierten Weg,
  daher der Umweg über vorgebackene Zwischenclips. Vor einem erneuten Versuch
  erst `README.txt`/`CHANGELOG.txt` des Scripting-SDK auf eine neue
  `Speed`-Eigenschaft oder `ChangeSpeed()`-Methode prüfen.

## Umgangsformen

- **Quellmaterial nie verändern.** Alles Abgeleitete in eigene Ordner.
- **Nur die Schnittliste von Hand ändern**, dann neu rendern. Nie im MP4
  herumfummeln.
- **Während der Abnahme nur nummerierte Reviewfassungen.** Die unnummerierte
  Endfassung wird erst nach ausdrücklicher finaler Freigabe gerendert.
- **Behauptungen belegen.** Wenn der Schnitt sitzen soll: Frames ziehen und
  anschauen. Wenn von Drift die Rede ist: Segmentdauern messen. Vermutung und
  Messung auseinanderhalten und Korrekturen offen benennen.
- **Zurückhaltung beim Urteil über Schnitte.** Claude kann Raster rechnen,
  Dopplungen finden, Kontinuitätsbrüche bemerken und Frames beschreiben. Ob ein
  Schnitt *sitzt*, entscheidet der Mensch.
- **Scratch-Musik ist Platzhalter.** Vor Veröffentlichung lizenzieren oder
  ersetzen; `analyze_music.py` auf den neuen Track anwenden und die
  Schnittpunkte umrechnen.
