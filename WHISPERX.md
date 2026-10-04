# Lokale Clip-Transkription mit WhisperX

`transcribe_clips.py` erzeugt für jeden Quellclip ein deutsches Transkript mit
wortgenauen Zeitmarken. Die Zeiten bleiben clip-lokal und können deshalb direkt
für `in`- und `out`-Entscheidungen verwendet werden. Die JSON-Dateien sind
abgeleitete Arbeitsdaten; die Videos werden weder verändert noch verschoben.

## Eigene Umgebung

Die normale `.venv` verwendet eine für WhisperX zu neue Python-Version.
WhisperX läuft deshalb getrennt unter dem lokal installierten Python 3.10:

```powershell
py -3.10 -m venv .venv-whisperx
.venv-whisperx\Scripts\python.exe -m pip install --upgrade pip
.venv-whisperx\Scripts\python.exe -m pip install torch==2.8.0 torchvision==0.23.0 torchaudio==2.8.0 --index-url https://download.pytorch.org/whl/cu128
.venv-whisperx\Scripts\python.exe -m pip install whisperx==3.8.6
```

Diese Kombination ist auf dem Arbeitsrechner mit CUDA 12.8 getestet. Der
explizite PyTorch-Index ist wichtig: Der normale PyPI-Index installiert unter
Windows sonst die CPU-Ausgabe. WhisperX und PyTorch laden mehrere große Pakete;
beim ersten Lauf kommt zusätzlich das gewählte Sprachmodell hinzu. Das Skript
meldet verständlich, wenn PyTorch die GPU nicht sieht. Als langsamer Fallback
funktioniert `--device cpu --compute-type int8`.

Unter Windows erscheint derzeit beim Import eine Warnung, dass TorchCodec seine
eigene Audio-DLL nicht laden konnte. Das ist für dieses Werkzeug unschädlich:
`transcribe_clips.py` lädt das Audio vorab über WhisperX, und der getestete
Transkriptions- und Alignment-Lauf endet vollständig. Ein echter Fehler wird
pro Clip als `FEHLER` ausgegeben und führt zu Exitcode 1.

## Erst Pilot, dann alle Clips

Der Dry-Run lädt weder WhisperX noch ein Modell:

```powershell
.venv\Scripts\python.exe transcribe_clips.py material/Megamarsch_Frankfurt_2025 --dry-run
```

Für den Piloten einzelne Dateinamen auswählen:

```powershell
.venv-whisperx\Scripts\python.exe transcribe_clips.py material/Megamarsch_Frankfurt_2025 --clip DATEI1.mp4 --clip DATEI2.mp4
```

Danach den ganzen Ordner verarbeiten:

```powershell
.venv-whisperx\Scripts\python.exe transcribe_clips.py material/Megamarsch_Frankfurt_2025
```

Vorgaben sind `large-v3`, Deutsch, Batchgröße 4 und automatische Wahl zwischen
CUDA/`float16` und CPU/`int8`. Bei zu wenig GPU-Speicher zuerst
`--batch-size 2` oder `--batch-size 1` versuchen. `--language auto` erkennt die
Sprache je Clip.

Die Ausgabe liegt unter
`audio/Megamarsch_Frankfurt_2025/transkripte/<clip.mp4>.whisperx.json`. Bereits
aktuelle Dateien werden übersprungen. Eine geänderte Quelle, ein anderes Modell
oder eine andere Sprachvorgabe löst eine neue Transkription aus; `--force`
erzwingt sie ausdrücklich.

Zusätzlich entstehen je Clip `.whisperx.txt` mit gut lesbarem Text und
clip-lokalen Zeitbereichen sowie `.whisperx.srt` mit segmentweisen Untertiteln.
Das JSON bleibt die Quelle für wortgenaue Schnittentscheidungen. Die SRT
verwendet nur vorhandene, gültige Segmentzeiten; fehlende Wortzeiten werden
nicht erfunden. Alle Texte sind automatische Arbeitsfassungen: Namen,
Produktbezeichnungen und Aussagen vor einer Veröffentlichung prüfen.

Auch bestehende aktuelle JSON-Dateien erhalten diese Exporte beim nächsten
Aufruf, ohne WhisperX oder ein Modell zu laden. Dafür reicht die normale
Werkzeug-Venv. `--dry-run` schreibt weiterhin keine Dateien. Beispiel:

```powershell
.venv\Scripts\python.exe transcribe_clips.py material/icy-box
```

Videos, Transkripte und Modell-Downloads bleiben lokale Projekt-/Cache-Daten.
Für GitHub gehören nur Skript, Dokumentation und Tests ins Repository.

## JSON-Vertrag

Jede Datei enthält:

- Identität der Quelldatei (Name, Größe, Änderungszeit),
- WhisperX-Version und Laufzeiteinstellungen,
- erkannte Sprache,
- Segmente mit Start, Ende und Text,
- je Segment die ausgerichteten Wörter mit Start, Ende und Konfidenz.

Nicht jedes Wort lässt sich bei Wind, Überlagerungen oder Zahlen zuverlässig
ausrichten. Fehlende Wortzeitmarken werden daher nicht erfunden. WhisperX ist
für den Schnitt eine Navigationshilfe: Pausen werden nicht automatisch
entfernt, und inhaltliche Kürzungen bleiben eine menschliche Entscheidung.

Sprechertrennung ist im ersten Modul absichtlich nicht enthalten. Sie benötigt
zusätzliche Modelle, einen Hugging-Face-Zugriff und eine eigene Qualitätsprüfung.
