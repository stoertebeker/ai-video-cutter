# AGENTS.md

**Lies zuerst `CLAUDE.md` im selben Ordner.** Dort steht die vollständige
Werkzeugkette: Ablauf, Dramaturgie, Fallstricke. Diese Datei ist der Einstieg
und wiederholt die Punkte, an denen man ohne Vorwissen scheitert.

## Was dieses Projekt ist

Eine Werkzeugkette, um aus vielen kurzen Clips eine auf Musik geschnittene
Montage zu bauen. Alles läuft lokal mit ffmpeg und Python, keine API-Keys,
keine Cloud.

Der Kern: **Der Agent sieht sich das Material tatsächlich an.** Kontaktbögen
werden als Bilddateien erzeugt und dann mit dem Datei-Lesewerkzeug als Bild
gelesen. Ohne diesen Schritt kennt der Agent nur Dateinamen und rät.

## Aufbau

Die Skripte im Wurzelverzeichnis sind projektunabhängig. Ein Projekt ist ein
Ordner mit Quellclips, einer oder mehreren `cutlist_*.json` darin und einer
`PROJEKT.md` mit dem, was für dieses Material gilt.

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
.venv\Scripts\python.exe analyze_music.py audio/<track>.wav > audio/analyse.json
.venv\Scripts\python.exe plan_raster.py audio/analyse.json 4
.venv\Scripts\python.exe make_contactsheets.py <projekt> 3 5
.venv\Scripts\python.exe make_contactsheets.py <projekt> 8 6 <filter>
#   -> sheets/<projekt>/*.png als Bilder ansehen, dann Schnittliste schreiben
.venv\Scripts\python.exe validate_cutlist.py <projekt>/cutlist_v1.json
.venv\Scripts\python.exe render.py           <projekt>/cutlist_v1.json
.venv\Scripts\python.exe sheet_sequence.py   <projekt>/cutlist_v1.json
.venv\Scripts\python.exe verify_cuts.py      <projekt>/cutlist_v1.json
```

Die Schnittliste ist die einzige Quelle der Wahrheit. Alles andere wird daraus
erzeugt. Nie am gerenderten MP4 herumschneiden.

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

## Was nicht gebaut ist

- Export in ein Schnittprogramm (FCPXML/Resolve wurde entfernt, kommt neu)
- Originalton der Clips — `render.py` verwirft ihn und legt nur Musik darunter
- gemischte Seitenverhältnisse — es wird hart skaliert, nicht beschnitten
- **Bildstabilisierung** — war eingebaut, wurde bewusst wieder entfernt. Der
  Gewinn war gering, und bei absichtlichen Kamerafahrten verschlechterte der
  Ausgleich das Bild. Passiert im Schnittprogramm. Nicht ungefragt wieder
  einbauen.

## Umgangsformen

- Quellmaterial nie verändern. Alles Abgeleitete in eigene Ordner.
- Behauptungen belegen: Frames ziehen und ansehen, Dauern messen. Vermutung
  und Messung auseinanderhalten, Korrekturen offen benennen.
- Ob ein Schnitt *sitzt*, entscheidet der Mensch. Der Agent rechnet Raster,
  findet Dopplungen, bemerkt Kontinuitätsbrüche und beschreibt Frames.
- Scratch-Musik ist Platzhalter. Vor Veröffentlichung lizenzieren oder
  ersetzen.
