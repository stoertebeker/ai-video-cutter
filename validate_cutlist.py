"""Prueft eine Schnittliste, bevor gerendert wird.

Geprueft wird: Lueckenlosigkeit der Schnittpunkte, dass kein Clip ueber sein
Quellende hinausliest, dass sich zwei Verwendungen desselben Clips nicht
ueberlappen, und welche Clips ueberhaupt vorkommen.
"""

import collections
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
liste = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "cutlist.json"
if not liste.is_absolute():
    liste = ROOT / liste

cfg = json.loads(liste.read_text(encoding="utf-8-sig"))
if "quellen" not in cfg:
    raise SystemExit(f"{liste.name}: Feld 'quellen' fehlt (Ordner mit den "
                     f"Quellclips, z.B. \"material/<projekt>\")")
SRC = ROOT / cfg["quellen"]
RESERVE = 0.15  # Mindestabstand zum Clipende, in Sekunden


def dauer(p: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(p)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


fehler, hinweise = [], []
pos = 0.0
belegt = collections.defaultdict(list)

for s in cfg["shots"]:
    pfad = SRC / s["clip"]
    if not pfad.exists():
        fehler.append(f"Shot {s['n']}: Datei fehlt: {s['clip']}")
        continue

    if abs(s["schnitt_bei"] - pos) > 0.001:
        fehler.append(
            f"Shot {s['n']}: schnitt_bei {s['schnitt_bei']:.3f} "
            f"passt nicht zur Summe davor ({pos:.3f})"
        )

    laenge = dauer(pfad)
    # Bei Zeitlupe wird weniger Quellmaterial verbraucht als die Einstellung
    # spaeter lang ist: verbraucht = dauer * tempo.
    tempo = float(s.get("tempo", 1.0))
    ende = s["in"] + s["dauer"] * tempo
    if ende > laenge:
        fehler.append(
            f"Shot {s['n']} {s['clip']}: liest bis {ende:.2f}s, "
            f"Clip hat nur {laenge:.2f}s"
        )
    elif laenge - ende < RESERVE:
        hinweise.append(
            f"Shot {s['n']} {s['clip']}: nur {laenge - ende:.2f}s Reserve am Ende"
        )
    if s["in"] < 0.1:
        hinweise.append(f"Shot {s['n']} {s['clip']}: startet {s['in']:.2f}s nach Clipanfang")

    for a, b, n in belegt[s["clip"]]:
        if s["in"] < b and ende > a:
            fehler.append(
                f"Shot {s['n']} ueberlappt Shot {n} im selben Clip "
                f"{s['clip']} ({a:.2f}-{b:.2f} vs {s['in']:.2f}-{ende:.2f})"
            )
    belegt[s["clip"]].append((s["in"], ende, s["n"]))
    pos += s["dauer"]

if abs(pos - float(cfg["ende_s"])) > 0.001:
    fehler.append(f"Summe der Dauern {pos:.3f}s != ende_s {cfg['ende_s']}")

VIDEO = {".mp4", ".mov", ".mts", ".mkv", ".avi"}
vorhanden = {p.name for p in SRC.iterdir()
             if p.is_file() and p.suffix.lower() in VIDEO}
ungenutzt = sorted(vorhanden - set(belegt))
mehrfach = {k: len(v) for k, v in belegt.items() if len(v) > 1}

print(f"{liste.name}: {len(cfg['shots'])} Shots, {pos:.3f}s")
print(f"Clips genutzt: {len(belegt)} von {len(vorhanden)}")
if mehrfach:
    print("mehrfach:      " + ", ".join(f"{k.split('_')[0]} ({v}x)"
                                        for k, v in sorted(mehrfach.items())))
if ungenutzt:
    print("ungenutzt:     " + ", ".join(u.split("_")[0] for u in ungenutzt))
for h in hinweise:
    print(f"  HINWEIS: {h}")
for f in fehler:
    print(f"  FEHLER:  {f}")
print("OK" if not fehler else "NICHT OK")
sys.exit(1 if fehler else 0)
