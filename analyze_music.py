"""Analyse des Scratch-Tracks: Tempo, Beats, Onsets, Lautstaerkeverlauf."""

import json
import sys

import librosa
import numpy as np

path = sys.argv[1]
y, sr = librosa.load(path, sr=None, mono=True)
dur = librosa.get_duration(y=y, sr=sr)

# Tempo und Beats
onset_env = librosa.onset.onset_strength(y=y, sr=sr)
tempo, beats = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, units="time")
tempo = float(np.atleast_1d(tempo)[0])

# Wie verlaesslich ist das Beat-Tracking? Streuung der Intervalle.
ibi = np.diff(beats)
jitter = float(np.std(ibi) / np.mean(ibi)) if len(ibi) > 1 else float("nan")

# Onsets als Alternative zu Beats (besser bei rubato/Klavier)
onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, units="time",
                                    backtrack=True)

# RMS-Lautstaerke in 0.5s-Fenstern
hop = 512
rms = librosa.feature.rms(y=y, hop_length=hop)[0]
times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
db = librosa.amplitude_to_db(rms, ref=np.max)

buckets = []
for t0 in np.arange(0, dur, 0.5):
    m = (times >= t0) & (times < t0 + 0.5)
    if m.any():
        buckets.append((round(float(t0), 1), round(float(db[m].mean()), 1)))

result = {
    "datei": path,
    "dauer_s": round(dur, 2),
    "samplerate": sr,
    "tempo_bpm": round(tempo, 1),
    "beat_jitter": round(jitter, 3),
    "beats_s": [round(float(b), 3) for b in beats],
    "onsets_s": [round(float(o), 3) for o in onsets],
    "rms_db_pro_halbsekunde": buckets,
}
print(json.dumps(result, indent=2, ensure_ascii=False))
