"""Optionale weiche Bilduebergaenge zwischen verschiedenen Quellclips.

Mehrere Shots aus derselben Datei koennen technische Teilstuecke sein, etwa
zur Korrektur wechselnder Telefonlage. Sie werden deshalb zuerst verlustfrei
zu einer Gruppe verbunden. Nur zwischen den so entstandenen Clipgruppen liegt
die konfigurierte Blende; dadurch bleiben interne Schnitte framegenau.
"""

from __future__ import annotations

from typing import Any


FIELD = "clipwechsel_blende_s"


def duration(config: dict[str, Any]) -> float:
    """Liefert die Blendendauer; ungueltige Werte behandelt der Validator."""
    value = config.get(FIELD, 0.0)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return 0.0
    return float(value)


def boundary_duration(
    config: dict[str, Any], shots: list[dict[str, Any]], index: int
) -> float:
    """Blendendauer hinter ``shots[index]``; gleiche Datei bleibt hart."""
    value = duration(config)
    if value <= 0 or index + 1 >= len(shots):
        return 0.0
    return value if shots[index]["clip"] != shots[index + 1]["clip"] else 0.0


def group_indices(shots: list[dict[str, Any]]) -> list[list[int]]:
    """Fasst direkt aufeinanderfolgende Shots derselben Quelldatei zusammen."""
    groups: list[list[int]] = []
    for index, shot in enumerate(shots):
        if groups and shots[groups[-1][-1]]["clip"] == shot["clip"]:
            groups[-1].append(index)
        else:
            groups.append([index])
    return groups


def filter_graph(
    group_durations: list[float], transition: float, *, first_input: int = 0
) -> tuple[str, float]:
    """Baut eine xfade-Kette bis ``[video_timeline]`` und liefert ihre Dauer."""
    if not group_durations:
        raise ValueError("Mindestens eine Videogruppe ist erforderlich")
    if transition <= 0 and len(group_durations) > 1:
        raise ValueError("Mehrere Videogruppen brauchen eine positive Blendendauer")

    # Die gerenderten Segmentdateien beginnen bereits bei PTS 0 und sind CFR.
    # Ein zusaetzliches setpts wuerde in ffmpeg 7 die bekannte Framerate am
    # Filterausgang verwerfen (1/0); xfade lehnt den Eingang dann ab.
    filters: list[str] = []
    previous = f"{first_input}:v"
    running = float(group_durations[0])
    for index, item_duration in enumerate(group_durations[1:], start=1):
        result_label = f"transition_{index}"
        offset = running - transition
        filters.append(
            f"[{previous}][{first_input + index}:v]"
            f"xfade=transition=fade:duration={transition:.6f}:"
            f"offset={offset:.6f}[{result_label}]"
        )
        previous = result_label
        running += float(item_duration) - transition

    filters.append(f"[{previous}]null[video_timeline]")
    return ";".join(filters), running


def validate(config: dict[str, Any], shots: list[dict[str, Any]]) -> list[str]:
    """Prueft Typ, Frameraster und ausreichend lange Nachbarshots."""
    if FIELD not in config:
        return []
    raw = config[FIELD]
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return [f"{FIELD} muss eine Zahl sein, ist {raw!r}"]
    value = float(raw)
    if value < 0:
        return [f"{FIELD} darf nicht negativ sein, ist {value:g}"]
    if value == 0:
        return []

    errors: list[str] = []
    fps = float(config["fps"])
    if value * fps < 1:
        errors.append(
            f"{FIELD} {value:g}s ist kuerzer als ein Frame bei {fps:g} fps"
        )
    for index in range(len(shots) - 1):
        if shots[index]["clip"] == shots[index + 1]["clip"]:
            continue
        shortest = min(float(shots[index]["dauer"]),
                       float(shots[index + 1]["dauer"]))
        if value >= shortest:
            errors.append(
                f"Uebergang Shot {shots[index]['n']}->{shots[index + 1]['n']}: "
                f"{value:g}s ist nicht kuerzer als der Nachbarshot ({shortest:g}s)"
            )
    return errors
