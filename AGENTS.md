# AGENTS.md

## Zuerst: Werkzeugkette aktualisieren

**Zu Beginn jeder Sitzung einmal `git pull` ausführen.** Die Werkzeuge werden
weiterentwickelt; ohne Pull arbeitest du womöglich mit einem Stand, dem
Funktionen oder Fehlerkorrekturen fehlen.

Schlägt der Pull wegen lokaler Änderungen fehl: erst klären, was da geändert
wurde, nicht blind überschreiben. Projektdateien sind davon nie betroffen —
das Repository enthält nur das Werkzeug.

**Lies dann `CLAUDE.md` im selben Ordner.** Dort steht die vollständige
Werkzeugkette: Ablauf, Dramaturgie, Fallstricke. Diese Datei ist der Einstieg
und wiederholt die Punkte, an denen man ohne Vorwissen scheitert.
`README.md` richtet sich an Menschen und ist die kürzere Übersicht.

## Was dieses Projekt ist

Eine Werkzeugkette, um aus vielen kurzen Clips eine auf Musik geschnittene
Montage zu bauen. Alles läuft lokal mit ffmpeg und Python, keine API-Keys,
keine Cloud.

Der Kern: **Der Agent sieht sich das Material tatsächlich an.** Kontaktbögen
werden als Bilddateien erzeugt und dann mit dem Datei-Lesewerkzeug als Bild
gelesen. Ohne diesen Schritt kennt der Agent nur Dateinamen und rät.

## Aufbau

Die Skripte im Wurzelverzeichnis sind projektunabhängig. **Das Git-Repository
enthält ausschließlich sie und die Doku — kein Projekt landet darin.**

```
*.py *.md cutlist.vorlage.json   das Werkzeug      -> im Repository

projekte/<name>/      cutlist_*.json + PROJEKT.md   -> nicht im Repository
material/<name>/      Quellclips                    -> nicht im Repository
audio/<name>/         Musik und Analysen            -> nicht im Repository
out/ sheets/ frames/ segments/ verify/ resolve_zwischen/   -> nicht im Repo
```

**Ein Projekt ist auf vier Orte verteilt**, alle vier stehen als Pfad im Kopf
der Schnittliste: sie selbst liegt in `projekte/<name>/`, `quellen` zeigt auf
`material/<name>/`, `audio` auf die Musikdatei, `ausgabe` auf das Ziel unter
`out/`. Fehlt `quellen` oder eine der Dateien, meldet `validate_cutlist.py`
das vor dem Rendern. In `projekte/<name>/PROJEKT.md` steht, was für dieses
Material gilt.

Die `.gitignore` ist eine Positivliste: erst alles ausschließen, dann das
Werkzeug wieder hereinnehmen. Neue Projekte bleiben dadurch von selbst außen.

**Vor der Arbeit an einem Projekt dessen `PROJEKT.md` lesen** — dort stehen
unbrauchbare Clipbereiche, Dopplungen und Outtakes. Neue Befunde dort
nachtragen.

Für ein neues Projekt ist am Code nichts zu ändern: `cutlist.vorlage.json`
kopieren und den Kopf ausfüllen.

## Umgebung

Python-Venv liegt in `.venv`, immer darüber aufrufen:

```
.venv\Scripts\python.exe <skript>.py
```

ffmpeg und ffprobe 7.1.1 sind im PATH. Shell ist PowerShell auf Windows.

## Der Ablauf

```
.venv\Scripts\python.exe analyze_music.py audio/<projekt>/<track>.wav > audio/<projekt>/analyse.json
.venv\Scripts\python.exe plan_raster.py audio/<projekt>/analyse.json 4
.venv\Scripts\python.exe make_contactsheets.py material/<projekt> 3 5
.venv\Scripts\python.exe make_contactsheets.py material/<projekt> 8 6 <filter>
#   -> sheets/<projekt>/*.png als Bilder ansehen, dann Schnittliste schreiben
.venv\Scripts\python.exe validate_cutlist.py      projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe sheet_crop.py            projekte/<projekt>/cutlist_v1.json   # nur bei Formatwechsel
.venv\Scripts\python.exe render.py                projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe make_numbered_review.py  projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe sheet_sequence.py        projekte/<projekt>/cutlist_v1.json
.venv\Scripts\python.exe verify_cuts.py           projekte/<projekt>/cutlist_v1.json
```

Die Schnittliste ist die einzige Quelle der Wahrheit. Alles andere wird daraus
erzeugt. Nie am gerenderten MP4 herumschneiden.

### Abnahme immer mit Szenennummern

`make_numbered_review.py` läuft **nach** `render.py`: Es liest die fertige
Datei aus `ausgabe` und blendet je Einstellung die Nummer `n` ein. Ergebnis
ist `<ausgabe>_nummeriert.mp4`.

Diese Datei ist die, die man zeigt — Rückmeldungen lauten dann „ändere Szene
3" statt einer Ortsbeschreibung. Nach jeder Änderung an der Schnittliste neu
erzeugen, sonst stimmen die Zahlen nicht mehr. Die unnummerierte Endfassung
schreibt `render.py` ohnehin; sie braucht keinen eigenen Schritt.

`n` muss eindeutig sein — `validate_cutlist.py` prüft das.

## Sechs Dinge, die Zeit kosten, wenn man sie nicht weiß

1. **`validate_cutlist.py` vor jedem Rendern.** Es fängt Lücken, überschrittene
   Quellenden und überlappende Mehrfachverwendungen desselben Clips. Ein
   Renderlauf dauert Minuten, die Prüfung Sekunden.

2. **Zeitlupe: `-t` gehört vor `-i`.** Dahinter begrenzt es die Ausgabe und
   schneidet die von `setpts` gedehnte Zeitlupe wieder auf die Quelldauer
   zurück. Das Video ist dann halb so lang, der Container zeigt trotzdem die
   volle Länge, weil die Tonspur sie vorgibt.

3. **PowerShells `>` schreibt UTF-8 mit BOM.** JSON danach mit
   `encoding="utf-8-sig"` lesen, sonst scheitert `json.load`.

4. **Drei Frames je Clip reichen nicht** für die Wahl des Einstiegszeitpunkts.
   Acht Frames zeigen erst Schärfefahrten, Schwenks aus dem Motiv und
   abgebrochene Takes. Vier solche Fälle haben schon Einstellungen gekostet.

5. **Beim Prüfen von Schnitten großzügig sampeln** — mindestens 0,15 s Abstand
   zum Schnitt. Bei 25 fps ist ein Frame 0,04 s, dazu kommt
   Quantisierungsdrift. Zu dicht am Schnitt erwischt man die falsche Seite und
   diagnostiziert einen Fehler, der nicht existiert.

6. **Kinocut läuft unter Windows nicht als MCP-Server** (`fcntl`-Import). Die
   CLI funktioniert vollständig. Nicht via `claude mcp add` registrieren.

7. **Resolve-API: `endFrame` in `AppendToTimeline`-Clip-Infos ist
   einschließlich gezählt**, nicht exklusiv — `{"startFrame": 0, "endFrame": 23}`
   sind 24 Frames. Steht so im Kommentar von
   `7_add_subclips_to_timeline.py` im Scripting-SDK, nirgends sonst explizit.
   Leicht zu übersehen, ergibt sonst einen Frame Differenz pro Einstellung.

## Export nach DaVinci Resolve

```
.venv\Scripts\python.exe resolve_prep_slowmo.py projekte/<projekt>/cutlist_vN.json
```
Dieser Aufruf backt die Zeitlupen vor und stellt `resolve_build.py` samt Pfad
zur Schnittliste in Resolves Scripts-Ordner bereit. Danach in Resolve
**Workspace > Scripts > resolve_build** — nichts von Hand einzutragen. Es baut
die Timeline per API und prüft sie danach gegen die Schnittliste.

Verworfen und nicht erneut zu versuchen: FCPXML-Import (Resolve verknüpft die
Clips nicht) und Geschwindigkeitsänderung per API (gibt es nicht, deshalb die
vorgebackenen Zeitlupen). Begründungen in `CLAUDE.md` — dort lesen statt neu
recherchieren.

## Hochkant aus Querformat

Steht in `breite`/`hoehe` ein anderes Seitenverhältnis als im Material,
schneidet `render.py` zu (`crop` vor `scale`) statt zu verzerren. Wohin,
sagen drei optionale Felder je Shot: `crop_x` (0.0 links … 1.0 rechts,
Vorgabe 0.5), `crop_y` (0.0 oben … 1.0 unten) und `crop_zoom` (1.0 =
größtmöglicher Ausschnitt, größer = enger). Bei Querformat in Hochkant wird
die volle Bildhöhe genutzt — `crop_y` wirkt dort erst ab `crop_zoom` > 1.0.

**Nicht raten:** `sheet_crop.py` zeichnet den Ausschnitt als Rahmen in den
Quellframe und dunkelt außen ab. Bogen als Bild ansehen, dann je Szenennummer
nachbessern. Bei gleichem Quell- und Zielformat ist der Filter die Identität,
bestehende Projekte ändern sich nicht.

## Was nicht gebaut ist

- Originalton im Resolve-Export — die lokale MP4-Pipeline rendert eine
  unabhängige `originalton`-Timeline samt Musik-Ducking, Resolve noch nicht
- GPX- und Bild-Overlays im Resolve-Export — die lokale MP4-Pipeline rendert
  die `overlays`-Timeline, Resolve überträgt sie noch nicht
- Mehrere Musiksegmente im Resolve-Export — die lokale MP4-Pipeline mischt
  die `musik`-Timeline samt Crossfades, Resolve kennt weiter nur `audio`
- Clipwechsel-Blenden im Resolve-Export — die lokale MP4-Pipeline kann mit
  `clipwechsel_blende_s` verschiedene Quelldateien weich verbinden; Resolve
  uebertraegt diese Uebergaenge noch nicht
- Rahmen statt beschneiden (Letterbox) — abweichende Formate werden
  zugeschnitten; ebenso wenig gibt es einen animierten Schwenk (Ken Burns),
  und der Resolve-Export kennt die crop-Felder nicht
- **Bildstabilisierung** — war eingebaut, wurde bewusst wieder entfernt. Der
  Gewinn war gering, und bei absichtlichen Kamerafahrten verschlechterte der
  Ausgleich das Bild. Passiert im Schnittprogramm. Nicht ungefragt wieder
  einbauen.

## Umgangsformen

- Quellmaterial nie verändern. Alles Abgeleitete in eigene Ordner.
- Reviewfassungen immer nummeriert; eine unnummerierte Endfassung erst nach
  ausdrücklicher finaler Freigabe.
- Behauptungen belegen: Frames ziehen und ansehen, Dauern messen. Vermutung
  und Messung auseinanderhalten, Korrekturen offen benennen.
- Ob ein Schnitt *sitzt*, entscheidet der Mensch. Der Agent rechnet Raster,
  findet Dopplungen, bemerkt Kontinuitätsbrüche und beschreibt Frames.
- Scratch-Musik ist Platzhalter. Vor Veröffentlichung lizenzieren oder
  ersetzen.
