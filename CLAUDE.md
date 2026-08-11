# Musikgeschnittene Videomontage — Werkzeugkette

Aus vielen kurzen Clips eine auf Musik geschnittene Montage bauen. Alles lokal,
keine API-Keys, keine Cloud.

Das Prinzip: **Claude übernimmt die Fleißarbeit und die Rhythmusarithmetik, der
Mensch entscheidet über Auswahl und Timing.** Jeder Schritt hinterlässt eine
Datei, die man anschauen kann — dadurch bleibt alles Kreative überprüfbar.

> Andere Agenten finden ihren Einstieg in `AGENTS.md` daneben.

## Aufbau

**Das Git-Repository enthält ausschließlich das Werkzeug.** Kein Projekt landet
darin — weder Rohmaterial noch Musik noch Schnittlisten, Projektdokumentation
oder fertige Videos.

```
                             ── im Repository ──
README.md                    Übersicht für Menschen
CLAUDE.md AGENTS.md          Arbeitsanweisung für Agenten
cutlist.vorlage.json         Vorlage für neue Projekte
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
yt-dlp -f bestaudio -x --audio-format wav -o "audio/<projekt>/scratch.%(ext)s" <URL>
python analyze_music.py audio/<projekt>/scratch.wav > audio/<projekt>/analyse.json
python plan_raster.py audio/<projekt>/analyse.json 4
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
python validate_cutlist.py projekte/<projekt>/cutlist_v1.json   # IMMER vor dem Rendern
python render.py           projekte/<projekt>/cutlist_v1.json
python sheet_sequence.py   projekte/<projekt>/cutlist_v1.json
python verify_cuts.py      projekte/<projekt>/cutlist_v1.json
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

### 4a. Review-Schleife — nummeriert bis zur Freigabe

Diese Regel gilt **für jedes Projekt**:

- In jeder Feedbackrunde wird ausschließlich eine nummerierte Arbeitsfassung
  ausgegeben. Unten rechts steht pro Einstellung eine große fortlaufende Zahl,
  die framegenau dem Feld `n` der aktuellen Schnittliste entspricht.
- Nach jedem Einfügen, Entfernen oder Verschieben von Einstellungen die Zahlen
  aus der aktuellen Schnittliste neu erzeugen. Szenennummern aus älteren
  Reviewfassungen gelten danach nicht automatisch weiter.
- Keine zusätzliche unnummerierte Parallelfassung für die Abnahme rendern oder
  ausgeben. Während der Iteration ist die Datei mit dem Zusatz
  `_nummeriert` die einzige Reviewfassung.
- Erst nach der ausdrücklichen finalen Freigabe des Bildschnitts einmalig die
  saubere Endfassung ohne Zahlen rendern. Danach technische Endprüfung und
  gegebenenfalls Veröffentlichungs-Export durchführen.
- Falls ein technischer Zwischenschritt vorübergehend ein unbeschriftetes
  Video erzeugt, ist es nur ein internes Hilfsartefakt und keine abzugebende
  Fassung. Der Arbeitsablauf soll nach Möglichkeit direkt in die nummerierte
  Reviewdatei rendern.

## Export nach DaVinci Resolve

Für den finalen Schnitt und die Farbkorrektur, nicht als Ersatz für die
mp4-Kette oben. Zwei Skripte:

```
.venv\Scripts\python.exe resolve_prep_slowmo.py projekte/<projekt>/cutlist_vN.json
```
backt jede Zeitlupen-Einstellung zu einem ProRes-Zwischenclip (läuft normal
in der Venv, außerhalb von Resolve). Danach `resolve_build.py` nach
`%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility`
kopieren, den Pfad zur Schnittliste am Kopf der Datei eintragen (Konstante
`CUTLIST_PFAD`), Resolve öffnen, **Workspace > Scripts > resolve_build**. Das
Skript legt selbst ein neues, durchnummeriertes Projekt an — es muss vorher
kein leeres Projekt offen sein.

Umgebung: DaVinci Resolve 21.0.4.5, freie Edition. Externes Scripting ist
Studio-only und nicht verfügbar; Skripte, die über Workspace > Scripts
laufen, funktionieren aber vollständig — Resolve stellt dort das globale
`resolve`-Objekt selbst bereit, kein `GetResolve()`/`scriptapp()`-Umweg nötig.

### Warum nicht FCPXML

Erster Versuch: FCPXML 1.8 + `File > Import > Timeline`. Kam strukturell
korrekt an (Reihenfolge, Längen, Musik auf A2, framegenau), aber Resolve
verknüpfte die Clips nicht gegen den Media Pool — alle Clips blieben offline.
Mit `importSourceClips=True` blieb die Timeline stattdessen komplett leer.
Beides ließ sich mit einer korrekten, selbst validierten FCPXML-Datei nicht
beheben — das Problem liegt in Resolves Konformierung, nicht in der Datei.

Dazu kommt: FCPXML kennt keine Geschwindigkeitsänderung ohne
`<adjust-timeMap>`, und die zwölf bis fünfzehn Zeitlupen-Einstellungen dieser
Projekte sind kein Rand-, sondern der Hauptfall. Ein Export, der Zeitlupe
nicht überträgt, ist für dieses Werkzeug wertlos.

**Zweiter Versuch, direkt verworfen:** die Resolve-API mit expliziten
`recordFrame`-Werten je Clip in einem `AppendToTimeline`-Aufruf zu füttern
(so macht es ein früherer, nie getesteter Anlauf). Das Problem: die
API-Dokumentation (`README.txt` im Scripting-SDK) sagt nicht, ob `recordFrame`
absolut (inklusive des Timeline-Startcodes, oft `01:00:00:00` ≠ Frame 0) oder
relativ zum Timeline-Anfang gezählt wird. Ungetestet ist das ein Fünfzig-
Fünfzig-Risiko auf eine komplett falsch platzierte Timeline. `resolve_build.py`
verzichtet deshalb ganz auf `recordFrame` und hängt die Einstellungen in
Cutlist-Reihenfolge sequenziell an — das ist das dokumentierte und in allen
Beispiel-Skripten des SDK vorgeführte Verhalten von `AppendToTimeline` und
braucht diese Annahme nicht.

### Warum die Zeitlupe vorgebacken wird, statt sie in Resolve zu setzen

Geprüft (nicht vermutet): `README.txt` im Scripting-SDK
(`%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting`)
listet unter „Looking up Timeline item properties" alle Schlüssel, die
`TimelineItem.SetProperty()` akzeptiert — `RetimeProcess` ist dabei, das
regelt aber nur die *Interpolationsart* eines schon bestehenden
Geschwindigkeitswechsels (nearest/frame blend/optical flow), keinen
`Speed`-Wert. Ein `ChangeSpeed()` oder vergleichbares gibt es in keiner
Klasse. `CHANGELOG.txt` desselben SDK erwähnt „speed" oder „retime" an
keiner Stelle. Es gibt also keine dokumentierte Möglichkeit, die
Geschwindigkeit eines Timeline-Clips per Scripting zu setzen — unabhängig
von freier oder Studio-Edition, das ist eine Lücke der Scripting-API selbst.

Der zweite Grund: die Resolve-Timeline läuft in Quell-Framerate (50), nicht
in der Render-Framerate (25). `render.py` erzeugt Zeitlupe kostenlos über den
Framerate-*Unterschied* zwischen Quelle (50) und Ziel (25) — bei `tempo=0.5`
landet zufällig jeder Quellframe auf genau einem Ausgabeframe. Läuft die
Resolve-Timeline dagegen selbst mit 50fps, gibt es diesen Unterschied nicht
mehr: der Trick greift nur noch bei `tempo=1.0`, also gar keiner Zeitlupe.
Echte Verlangsamung braucht auf einer 50fps-Timeline mit 50fps-Quelle
zwingend eine echte Geschwindigkeitsänderung — und genau die ist nicht
scriptbar.

**Lösung:** Zeitlupe vorab mit ffmpeg backen (`resolve_prep_slowmo.py`,
dieselbe Filterkette wie `render.py` — `setpts` vor `fps`, `-ss`/`-t` vor
`-i` — aber mit Ziel-Framerate = Quell-Framerate statt Render-Framerate, ohne
Skalierung, als ProRes 422 HQ). `resolve_build.py` hängt diesen bereits
verlangsamten Zwischenclip mit Tempo 1.0 in die Timeline — Resolve muss dann
gar nichts mehr retimen. Nachteil: Farbkorrektur läuft für diese Einstellungen
auf dem Zwischencodec, nicht auf der Kameradatei. Gemessen für
`projekte/zelda/cutlist_v4.json` (15 Zeitlupen-Einstellungen, 2160×3840): **8,9 GB**
Zwischenmaterial für rund 47 s Zeitlupenanteil. Bei Platzmangel
`PRORES_PROFIL` am Kopf von `resolve_prep_slowmo.py` auf 2 (422 Standard) oder
0 (Proxy) stellen.

Nebeneffekt: Einstellungen in Echtzeit (`tempo` fehlt oder `1.0`) werden
unverändert aus der Originaldatei gelesen — deren Originalton kommt beim
Import automatisch mit in den Media Pool (Resolve importiert die ganze
Datei). Die Zeitlupen-Zwischenclips haben bewusst keinen Ton (`-an`):
zeitlupenverzerrter, tonhöhenverschobener Ton wäre ohnehin unbrauchbar, und
für dieses Projekt ist der Originalton laut `PROJEKT.md` sowieso Wind.

### Was `resolve_build.py` beim Bauen selbst prüft

Kein Erfolg wird behauptet, ohne zurückgelesen zu haben: nach
`AppendToTimeline` liest das Skript für jede Einstellung `GetDuration()`,
`GetStart()` und `GetEnd()` aus der entstandenen Timeline zurück und
vergleicht sie mit der aus der Schnittliste vorausberechneten Framezahl —
inklusive Lückenprüfung zwischen aufeinanderfolgenden Einstellungen und
Gesamtlänge gegen `ende_s`. Bei Abweichung wird das Projekt **nicht**
gespeichert, sondern die konkrete Differenz gemeldet. `endFrame` in
`AppendToTimeline`-Clip-Infos ist einschließlich gezählt — belegt durch den
Kommentar im mitgelieferten Beispiel `7_add_subclips_to_timeline.py`
(`{"startFrame": 0, "endFrame": 23}` wird dort als „frame 0 .. 23", also 24
Frames, beschrieben).

### Was getestet ist und was nicht

Getestet: die ffmpeg-Kette in `resolve_prep_slowmo.py` (an echtem
Zelda-Material gerechnet und mit `ffprobe -count_frames` nachgezählt — exakte
Framezahl, kein Rundungsfehler); die Frame-Arithmetik und Dateisuche in
`resolve_build.py` bis zu dem Punkt, an dem echtes Resolve gebraucht wird
(per Test-Harness mit einem Fake-`resolve`-Objekt durchlaufen); die schnelle
`nb_frames`-Gegenprobe der Zwischenclips per `ffprobe`.

**Nicht getestet, weil nicht bedienbar:** alles ab dem Anlegen des
Resolve-Projekts — `CreateProject`, `SetSetting("timelineFrameRate", …)`,
`ImportMedia`, `CreateEmptyTimeline`, `AppendToTimeline` und die
Rücklese-Prüfung selbst. Diese Aufrufe sind gegen die offizielle
API-Dokumentation und deren eigene Beispiel-Skripte abgesichert, aber nicht
in echtem Resolve gelaufen. Größtes verbleibendes Risiko: ob
`AppendToTimeline` ohne `recordFrame` bei gemischten Medienquellen
(Original + Zwischenclip) zuverlässig lückenlos aneinanderhängt. Die
eingebaute Rücklese-Prüfung deckt das beim ersten echten Lauf auf, statt es
stillschweigend falsch zu lassen.

## Neues Projekt aufsetzen

1. Quellclips nach `material/<projekt>/`, Musik nach `audio/<projekt>/`.
2. `cutlist.vorlage.json` nach `projekte/<projekt>/cutlist_v1.json` kopieren, Kopf
   ausfüllen: `quellen` (= `material/<projekt>`), `audio`, `ausgabe`,
   Auflösung, Framerate.
3. `analyze_music.py`, dann `plan_raster.py` — Raster ableiten.
4. Kontaktbögen bauen (erst grob, dann dicht), ansehen, Einstellungen setzen.
5. `validate_cutlist.py`, nummerierte Reviewfassung rendern,
   `sheet_sequence.py`, `verify_cuts.py`, iterieren.
6. Nach ausdrücklicher Freigabe einmalig die unnummerierte Endfassung rendern.
7. Befunde zum Material in `projekte/<projekt>/PROJEKT.md` festhalten.

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

- **Originalton**, siehe oben. Gilt auch für den Resolve-Export: Musik wird
  von `resolve_build.py` nicht in die Timeline gelegt, das ist von Hand
  nachzutragen.
- **Gemischte Seitenverhältnisse**, siehe oben.
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
