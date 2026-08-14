"""Video-Encoder-Parameter an einer Stelle - GPU (NVENC) oder CPU (x264).

Warum zentral: render.py kodiert jedes Segment einzeln und haengt sie per
concat-Demuxer aneinander. Das funktioniert nur, wenn alle Segmente exakt
gleich kodiert sind. Stuenden die Parameter an drei Stellen im Code, wuerden
sie frueher oder spaeter auseinanderlaufen.

Umschalten per Umgebungsvariable:

    ENCODER=cpu  .venv\\Scripts\\python.exe render.py projekte/<p>/cutlist_v1.json

Voreinstellung ist die GPU. Fuer Reviewfassungen ist das richtig - sie sind
schnell fertig und niemand sieht den Unterschied. Fuer die Endfassung ist CPU
die bessere Wahl: NVENC ist pro Bit schwaecher als x264 mit preset slow, und
das faellt ausgerechnet in dunklen Bildern auf (Nachtaufnahmen, Kerzen- und
Fackellicht), wo es als Banding sichtbar wird.
"""

import os
import subprocess

# "gpu" (Vorgabe) oder "cpu"
ENCODER = os.environ.get("ENCODER", "gpu").lower()


def _nvenc_vorhanden() -> bool:
    """Prueft einmalig, ob ffmpeg h264_nvenc kennt."""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                       capture_output=True, text=True)
    return "h264_nvenc" in r.stdout


def video_args() -> list[str]:
    """ffmpeg-Argumente fuer die Videospur, ohne -pix_fmt.

    -pix_fmt bleibt beim Aufrufer, weil resolve_prep_slowmo.py mit ProRes
    einen anderen Farbraum braucht und diese Funktion gar nicht benutzt.
    """
    if ENCODER == "cpu":
        return ["-c:v", "libx264", "-preset", "slow", "-crf", "18"]

    if not _nvenc_vorhanden():
        raise SystemExit(
            "ENCODER=gpu verlangt, aber ffmpeg kennt h264_nvenc nicht.\n"
            "Entweder ffmpeg ohne NVENC-Unterstuetzung, oder kein NVIDIA-\n"
            "Treiber. Mit ENCODER=cpu laeuft es auf der CPU weiter."
        )

    return [
        "-c:v", "h264_nvenc",
        # p1 = schnellste, p7 = beste Qualitaet. p6 liegt etwa dort, wo
        # x264 "slow" liegt, ohne den Geschwindigkeitsvorteil aufzugeben.
        "-preset", "p6",
        # -b:v 0 ist Pflicht: ohne das greift eine Default-Bitrate und -cq
        # bleibt wirkungslos. cq 19 entspricht etwa crf 18 bei x264.
        "-rc", "vbr", "-cq", "19", "-b:v", "0",
        # Adaptive Quantisierung. Kostet kaum Zeit und verhindert Banding
        # in dunklen Flaechen - bei Nachtmaterial der entscheidende Schalter.
        "-spatial-aq", "1", "-temporal-aq", "1",
        "-rc-lookahead", "32",
    ]


def name() -> str:
    """Klartextname fuer Protokollausgaben."""
    return "CPU (libx264)" if ENCODER == "cpu" else "GPU (h264_nvenc)"
