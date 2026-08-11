"""Leitet aus der Beatanalyse ein Taktraster ab und legt den RMS-Pegel daneben.

Nimmt die tatsaechlich erkannten Beats statt eines gerechneten Rasters - bei
frei gespielter Musik laufen die sonst auseinander.
"""

import json
import sys

pfad = sys.argv[1]
takt = int(sys.argv[2]) if len(sys.argv) > 2 else 4  # Beats je Takt

d = json.load(open(pfad, encoding="utf-8-sig"))
beats = d["beats_s"]
rms = d["rms_db_pro_halbsekunde"]


def pegel(t: float) -> float:
    passend = [db for (zeit, db) in rms if zeit <= t]
    return passend[-1] if passend else rms[0][1]


print(f"{len(beats)} Beats, Takt = {takt} Beats\n")
print(f"{'Takt':>4} {'Beat#':>6} {'Zeit':>8} {'Laenge':>7} {'dB':>7}")
grenzen = beats[::takt]
for i, t in enumerate(grenzen):
    laenge = (grenzen[i + 1] - t) if i + 1 < len(grenzen) else 0.0
    print(f"{i + 1:>4} {i * takt:>6} {t:>8.3f} {laenge:>7.3f} {pegel(t):>7.1f}")
