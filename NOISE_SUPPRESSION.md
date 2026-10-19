# Hintergrundgeräusche bei Sprachaufnahmen reduzieren

Bewährter Ablauf aus den ICY-BOX-Preisübergaben im Chat „Northcon-reel“ und
dem Sponsorenvideo der gv#36: Sprache mit **Audo** isolieren, bereinigten und
unbearbeiteten Ton auf vergleichbaren Pegel bringen und anschließend
**75 % bereinigte Sprache mit 25 % Originalton** mischen. So bleibt ein Teil
der Veranstaltungsatmosphäre erhalten. Dieses Verhältnis ist ein Ausgangspunkt
für die Hörabnahme, keine feste Vorgabe für jedes Material.

Der normale Schnitt und Render laufen lokal. Audo ist eine **optionale externe
Verarbeitung**: Der Auftrag muss die Übertragung der ausgewählten Sprachaufnahme
an diesen Anbieter abdecken. Eine schon erteilte, passende Freigabe nicht erneut
abfragen. Ausschließlich die benötigten Tonbereiche übertragen, keine Videos,
Bloopers oder vollständigen Materialordner. Die lokale Alternative steht unten.

## 1. Auswahl und Ableitungen festhalten

Zuerst die gelungenen Takes und vollständigen Sätze auswählen. Die
`originalton`-Timeline ist unabhängig von den Bildschnitten; bei B-Roll darf
ein Satz unter mehreren Einstellungen weiterlaufen. Ausgewählte Quellbereiche,
Reihenfolge und Timelinepositionen kommen aus der Schnittliste, niemals aus
nachträglichen Änderungen an der gerenderten MP4.

Alles Abgeleitete liegt unter `audio/<projekt>/entrauschung_<fassung>/`:

- ausgewählter Originalton und gegebenenfalls einzelne Szenen-WAVs,
- Audo-Antworten und Header, getrennt je verarbeitetem Abschnitt,
- pegelangepasste Original-/Sprachspuren und endgültige Mischungen,
- Messprotokoll mit Dauern, Versatz, Mischanteilen und Lautheitswerten.

Parameter und Pfade in der Schnittliste dokumentieren, Bearbeitungsschritte
zusätzlich in der jeweiligen `PROJEKT.md`. Projektbezogene Vorbereitungsskripte
lesen diese Werte und erzeugen die Audiodateien daraus. Eigene Metadatenfelder
wie `_noise_suppression` sind **kein eingebauter Filter von `render.py`**.
Nach Änderungen an Auswahl oder Timing die Ableitungen entsprechend neu erzeugen.
Rohmaterial und frühere Fassungen nicht überschreiben.

## 2. Nur den ausgewählten Ton vorbereiten

Quellbereiche mit `-ss` und `-t` vor `-i` extrahieren, Zeitstempel auf null
setzen und auf einheitlich 48 kHz / Stereo bringen. Für Zwischenstände
verlustfreies PCM-WAV verwenden. Die Abschnitte bei Bedarf zu einer Tonspur
zusammensetzen; ihre Grenzen und die Zuordnung zu den Originalclips erhalten.

Ein Hochpass um 70–80 Hz kann tieffrequentes Rumpeln reduzieren. Eine
Lautheitsanpassung allein ist **keine Geräuschunterdrückung**: Sie macht mit der
Sprache auch die Hintergrundgeräusche lauter. Bei stark verschiedenen Aufnahme-
pegeln die ausgewählten Sprachabschnitte einzeln angleichen.

## 3. Audo verarbeiten lassen und Vollständigkeit prüfen

Im bisherigen Workflow wurde der folgende Test-Endpunkt verwendet. Beispiel
aus dem Repository-Wurzelverzeichnis; `PROJEKT` und `FASSUNG` ersetzen:

```powershell
curl.exe --silent --show-error --max-time 55 --user-agent 'Codex-audio-project' `
  -F 'file=@audio/PROJEKT/entrauschung_FASSUNG/original.wav' `
  https://audo.ai/api/try/remove-noise `
  -D 'audio/PROJEKT/entrauschung_FASSUNG/audo_headers.txt' `
  -o 'audio/PROJEKT/entrauschung_FASSUNG/audo_response.body'
if ($LASTEXITCODE -ne 0) { throw 'Audo-Anfrage fehlgeschlagen' }
Get-Content -LiteralPath 'audio/PROJEKT/entrauschung_FASSUNG/audo_headers.txt' |
  Select-String 'HTTP/|Content-Type:|Audo-Processed-Seconds:'
```

Vor der Verwendung HTTP-Status, tatsächlichen Medientyp und dekodierte Dauer
prüfen. Eine Fehlerantwort nicht als Audiodatei behandeln. Die Endung `.body`
bewahrt die Antwort unverändert; ffmpeg erkennt das Audioformat am Inhalt.

```powershell
ffprobe -v error -show_entries format=duration:stream=codec_name,sample_rate,channels `
  -of json 'audio/PROJEKT/entrauschung_FASSUNG/audo_response.body'
```

**HTTP 200 bedeutet nicht, dass der ganze Upload verarbeitet wurde.** Beim
gv#36-Sponsorenvideo am 19.10.2026 enthielt die Anfrage 71,4 s; Audo meldete
`audo-processed-seconds: 60` und lieferte exakt 60,0 s Audio. Das frühere
53,44-s-ICY-BOX-Video war vollständig verarbeitet worden. Testangebot,
Kontingente und Grenzen können sich ändern; weder unbegrenzte Dauer noch
dauerhaft kostenlosen Zugang voraussetzen oder automatisch kostenpflichtig
wechseln.

Längeres Material innerhalb der erlaubten Dienstgrenzen in vollständige
Sprachabschnitte aufteilen, möglichst an vorhandenen Szenengrenzen. Im genannten
Fall wurde der ganze 21,8-s-Schlussgang separat verarbeitet. Die erste Antwort
wurde nur bis zum Beginn dieser Szene bei 49,6 s verwendet, danach die vollständige
Schlussantwort. So entstand eine lückenlose 71,4-s-Spur ohne Naht mitten im Satz.
Für **jeden** Teil die volle benötigte Dauer nachweisen. Begrenzungen nicht durch
einen unbearbeiteten Originalton-Anhang verdecken.

Antworten lokal aufbewahren, damit neue Mischverhältnisse keinen erneuten
Upload benötigen. Header können zeitlich begrenzte Job-URLs enthalten; diese
gehören wie Medien und Antworten nicht ins Git-Repository.

## 4. Sprache und Originalton synchronisieren

Beide Spuren mit gleicher Abtastrate und Kanalzahl dekodieren. Dauer und
Samplezahl müssen für den verwendeten Ausschnitt übereinstimmen. Einen
abweichenden Anhang oder fehlende Sprache nicht stillschweigend durch Padding
ersetzen.

Versatz je Sprachabschnitt per Kreuzkorrelation prüfen, nicht nur einmal über
den gesamten Film. Bewährt: Mono-Vergleich bei 8 kHz, Sprachband etwa 250–3400 Hz,
Suche zunächst in ±0,2 s. Bei eindeutiger Korrelation einen gemessenen Versatz
korrigieren und die Sollsamplezahl erhalten. Bei uneindeutigen Ergebnissen
sprachreiche Stellen gesondert prüfen, statt blind einen Versatz zu übernehmen.

In den bisherigen Audo-Fassungen lag der gemessene Versatz bei null. Das ist
ein Befund dieser Dateien, keine Zusicherung für andere Anbieter oder Modelle.

## 5. Pegel angleichen, dann Atmosphäre beimischen

Bereinigte Sprache und Original müssen vor dem Mischen auf vergleichbarem Pegel
liegen. Zweistufiges ffmpeg-`loudnorm` verwenden: zuerst mit
`print_format=json` messen, danach die Messwerte `input_i`, `input_tp`,
`input_lra`, `input_thresh` und `target_offset` als `measured_I`, `measured_TP`,
`measured_LRA`, `measured_thresh` und `offset` in den zweiten Durchgang übernehmen.
Im zweiten Durchgang `linear=true` angeben und den tatsächlichen Normalisierungstyp
protokollieren; die Spitzenbegrenzung kann einen dynamischen Durchgang erfordern.

Bewährtes Ziel für diese Sprachbeiträge: −18 LUFS. Für die gv#36-Zwischenstände
wurde −4 dBTP als Spitzenziel gewählt, um Reserve für Mischung und AAC-Encoding
zu lassen. Frühere ICY-BOX-Vergleiche verwendeten −2 dBTP. Das fertige Video
erneut messen; ein Zielwert der Vorstufe ist kein gemessener Exportwert.

Bei unterschiedlich aufgenommenen Szenen diese Anpassung je Szene durchführen.
Anschließend beide synchronen, pegelangepassten Spuren mischen:

```text
[clean][original]amix=inputs=2:weights=0.75 0.25:normalize=0:duration=shortest[mix]
```

Die Gewichte sind lineare Signalanteile. 25 % Original entsprechen ungefähr
−12 dB gegenüber derselben Originalspur allein, **nicht** einer garantierten
wahrgenommenen Geräuschreduktion. Auch die bereinigte Spur kann Restgeräusche
enthalten. `duration=shortest` erst nach der Längenprüfung verwenden.

Die Mischung erneut auf den gewählten Zielpegel bringen. Bei ICY BOX wurde
zunächst auch 85/15 getestet; freigegeben wurde später 75/25. Hörvergleiche
immer bei vergleichbarer Lautheit machen. Natürlichkeit, Verständlichkeit und
eventuelle Filterartefakte entscheidet der Mensch beim Anhören.

## 6. Einbinden, rendern, abnehmen

Die abgeleiteten WAVs über `originalton` mit ihren korrekten Timelinepositionen
einbinden. Ein portables Beispiel für eine Datei außerhalb des Quellordners:

```json
{
  "n": 1,
  "clip": "../../audio/PROJEKT/entrauschung_FASSUNG/ambiente_01.wav",
  "in": 0.0,
  "schnitt_bei": 0.0,
  "dauer": 7.4,
  "pegel_db": -1.0,
  "fade_in_s": 0.015,
  "fade_out_s": 0.025
}
```

`clip` wird relativ zu `quellen` aufgelöst; das Beispiel setzt
`quellen: material/PROJEKT` voraus. Quellclip, ursprünglichen Zeitbereich und
Bearbeitungsrezept zusätzlich dokumentieren. Diese WAV beginnt bei null;
die ursprüngliche Quellzeit darf nicht nochmals als ihr `in` gesetzt werden.

Kurze Tonblenden verhindern Klicks, ohne Satzanfänge oder Dank abzuschneiden.
Bei später verlängerten Szenen auch den Zusatzton bearbeiten und auf denselben
Atmosphärenanteil bringen. Ein Wechsel auf 100 % Rohmaterial verursacht einen
hörbaren Hintergrundsprung; bei einem Anschluss innerhalb derselben Aufnahme
mit ausreichendem Kontext arbeiten und bei Bedarf weich überblenden.

Bei unveränderter Auswahl kann eine neue Mischung aus den gespeicherten
Antworten erzeugt werden. Danach immer die Schnittliste validieren, daraus neu
rendern und eine neue nummerierte Abnahme erzeugen. Den gesamten Export
dekodieren, Bild-/Tonlänge, Segmentgrenzen, Sprachvollständigkeit, Lautheit und
True Peak prüfen. Automatische Transkripte helfen beim Finden von Auslassungen;
sie ersetzen keinen Hörvergleich und können besonders bei Eigennamen irren.

Der Standardrenderer verwendet bei vorhandener `originalton`-Timeline
Musik-Ducking und einen Limiter. Bei Sprachvideos ohne zusätzliche Musik wurde
bisher eine technische Stille-WAV als `audio` verwendet. Eine andere Einbindung,
etwa ein vorbereiteter Gesamtmix über `musik` ohne Ducking, im Projekt ausdrücklich
dokumentieren; keine Musik oder doppelte Originaltonspur unbeabsichtigt addieren.

## Lokale Alternative: RNNoise

Beim später verlängerten ICY-BOX-Schluss wurde lokal ffmpeg-`arnndn` mit
`std.rnnn` aus [richardpl/arnndn-models](https://github.com/richardpl/arnndn-models)
verwendet. Modell lokal ablegen und seine Herkunft und Version bzw. Prüfsumme
im Projekt festhalten. Der Audiofilter lautet bei einem relativen Modellpfad:

```text
arnndn=m=audio/PROJEKT/entrauschung_FASSUNG/std.rnnn
```

Dort wurden zwei Sekunden Kontext vor dem benötigten Ausschnitt mitverarbeitet,
ein gemessener Filterversatz von 10 ms korrigiert und ebenfalls 25 % Originalton
beigemischt. Diesen Versatz neu messen, nicht für andere Dateien fest übernehmen.
RNNoise ist eine andere Bearbeitung als Audo und benötigt eine eigene Hörabnahme.
Im damaligen Vergleich empfand der Nutzer stärkere FFT-Rauschminderung mit
`afftdn` als zu dumpf; sie ist deshalb kein gleichwertiger Ersatz für die
freigegebene Audo-Mischung.

Diese Anleitung dokumentiert einen Bearbeitungsablauf. Sie fügt dem allgemeinen
Renderer keinen automatischen Upload und keinen neuen Entrauschungsfilter hinzu.
