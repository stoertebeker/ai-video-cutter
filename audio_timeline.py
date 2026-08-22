"""Originalton-Timeline und Musik-Ducking fuer den finalen ffmpeg-Pass.

Bild und Ton sind absichtlich getrennte Timelines. Dadurch darf ein visueller
Shot wechseln, waehrend Sprache oder Atmosphaere aus einem anderen Clip
weiterlaeuft. Das Modul baut nur ffmpeg-Argumente und Filter; es veraendert
keine Quelldatei.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


SAMPLE_RATE = 48_000
DEFAULT_FADE_S = 0.02
DEFAULT_MUSIC_FADE_S = 1.5
DEFAULT_MUSIC_DB = -18.0
DEFAULT_ORIGINAL_DB = 0.0
MIN_DB = -60.0
MAX_DB = 12.0

# Ein fester, vorsichtiger Sprach-/Atmo-Ducker. Projektbezogene Lautstaerken
# stehen in der Cutlist; technische Kompressorzeiten bleiben zentral, damit
# zwei Fassungen nicht wegen versteckter Einzelwerte anders reagieren.
DUCK_THRESHOLD = 0.025
DUCK_RATIO = 12
DUCK_ATTACK_MS = 20
DUCK_RELEASE_MS = 550


def entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Liefert Tonsegmente; fehlendes Feld behaelt das alte Renderverhalten."""
    value = config.get("originalton", [])
    return value if isinstance(value, list) else []


def music_entries(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Liefert die optionale Mehrspur-Musiktimeline; sonst bleibt audio aktiv."""
    value = config.get("musik", [])
    return value if isinstance(value, list) else []


def music_input_args(config: dict[str, Any], root: Path) -> list[str]:
    """Baut je Musiksegment einen begrenzten Eingang; Wiederholungen sind erlaubt."""
    args: list[str] = []
    for segment in music_entries(config):
        args.extend(
            [
                "-ss", f"{float(segment.get('in', 0.0)):.6f}",
                "-t", f"{float(segment['dauer']):.6f}",
                "-i", str(root / segment["datei"]),
            ]
        )
    return args


def input_args(config: dict[str, Any], source_dir: Path) -> list[str]:
    """Baut je Tonsegment einen exakt begrenzten ffmpeg-Eingang."""
    args: list[str] = []
    for segment in entries(config):
        args.extend(
            [
                "-ss",
                f"{float(segment['in']):.6f}",
                "-t",
                f"{float(segment['dauer']):.6f}",
                "-i",
                str(source_dir / segment["clip"]),
            ]
        )
    return args


def _volume(value: float) -> str:
    return f"{value:g}dB"


def _music_filters(
    config: dict[str, Any], duration: float, first_music_input: int
) -> list[str]:
    """Erzeugt eine filmlange Musikspur mit Ergebnislabel ``[musik]``."""
    segments = music_entries(config)
    music_db = float(config.get("audio_mix", {}).get("musik_pegel_db", DEFAULT_MUSIC_DB))
    if not segments:
        return [
            f"[{first_music_input}:a:0]"
            f"aresample={SAMPLE_RATE},aformat=sample_fmts=fltp:channel_layouts=stereo,"
            f"atrim=0:{duration:.6f},asetpts=PTS-STARTPTS,"
            f"apad=whole_dur={duration:.6f},atrim=0:{duration:.6f},"
            f"volume={_volume(music_db)}[musik]"
        ]

    filters: list[str] = []
    labels: list[str] = []
    for index, segment in enumerate(segments):
        segment_duration = float(segment["dauer"])
        timeline_start = float(segment["schnitt_bei"])
        fade_in = float(segment.get("fade_in_s", DEFAULT_MUSIC_FADE_S))
        fade_out = float(segment.get("fade_out_s", DEFAULT_MUSIC_FADE_S))
        level = float(segment.get("pegel_db", 0.0))
        chain = [
            f"atrim=0:{segment_duration:.6f}",
            "asetpts=PTS-STARTPTS",
            f"aresample={SAMPLE_RATE}",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
        ]
        if fade_in:
            chain.append(f"afade=t=in:st=0:d={fade_in:.6f}")
        if fade_out:
            chain.append(
                f"afade=t=out:st={segment_duration - fade_out:.6f}:d={fade_out:.6f}"
            )
        if level:
            chain.append(f"volume={_volume(level)}")
        delay_ms = int(timeline_start * 1000 + 0.5)
        if delay_ms:
            chain.append(f"adelay={delay_ms}:all=1")
        label = f"musik_segment_{index}"
        filters.append(
            f"[{first_music_input + index}:a:0]" + ",".join(chain) + f"[{label}]"
        )
        labels.append(f"[{label}]")
    filters.append(
        f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=0:{duration:.6f}[musik_stille]"
    )
    filters.append(
        "[musik_stille]" + "".join(labels)
        + f"amix=inputs={len(labels) + 1}:duration=longest:"
          "dropout_transition=0:normalize=0,"
        + f"atrim=0:{duration:.6f},volume={_volume(music_db)}[musik]"
    )
    return filters


def music_only_filter_graph(
    config: dict[str, Any], duration: float, *, first_music_input: int = 1
) -> str:
    """Mischt die neue Musiktimeline ohne Originalton zu ``[a]``."""
    if not music_entries(config):
        raise ValueError("music_only_filter_graph braucht eine Musiktimeline")
    end_fade = min(0.4, duration)
    filters = _music_filters(config, duration, first_music_input)
    filters.append(
        f"[musik]afade=t=out:st={duration - end_fade:.6f}:d={end_fade:.6f},"
        f"atrim=0:{duration:.6f}[a]"
    )
    return ";".join(filters)


def filter_graph(
    config: dict[str, Any], duration: float, *, music_input: int = 1,
    first_original_input: int = 2,
) -> str:
    """Baut den Audioteil des Filtergraphen mit Ergebnislabel ``[a]``."""
    segments = entries(config)
    if not segments:
        raise ValueError("filter_graph braucht mindestens ein Originaltonsegment")

    mix = config.get("audio_mix", {})
    original_db = float(mix.get("originalton_pegel_db", DEFAULT_ORIGINAL_DB))
    end_fade = min(0.4, duration)
    filters = _music_filters(config, duration, music_input)

    labels: list[str] = []
    for index, segment in enumerate(segments):
        segment_duration = float(segment["dauer"])
        timeline_start = float(segment["schnitt_bei"])
        fade_in = float(segment.get("fade_in_s", DEFAULT_FADE_S))
        fade_out = float(segment.get("fade_out_s", DEFAULT_FADE_S))
        level = float(segment.get("pegel_db", 0.0))
        chain = [
            f"atrim=0:{segment_duration:.6f}",
            "asetpts=PTS-STARTPTS",
            f"aresample={SAMPLE_RATE}",
            "aformat=sample_fmts=fltp:channel_layouts=stereo",
        ]
        if fade_in > 0:
            chain.append(f"afade=t=in:st=0:d={fade_in:.6f}")
        if fade_out > 0:
            chain.append(
                f"afade=t=out:st={segment_duration - fade_out:.6f}:d={fade_out:.6f}"
            )
        if level != 0:
            chain.append(f"volume={_volume(level)}")
        delay_ms = int(timeline_start * 1000 + 0.5)
        if delay_ms:
            chain.append(f"adelay={delay_ms}:all=1")
        label = f"ot{index}"
        filters.append(
            f"[{first_original_input + index}:a:0]" + ",".join(chain) + f"[{label}]"
        )
        labels.append(f"[{label}]")

    # Die explizite Stille macht die Originaltonspur exakt filmlang, auch bei
    # Luecken. Pausen und Atmosphaere in den Segmenten bleiben unangetastet.
    filters.append(
        f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=0:{duration:.6f}[ot_stille]"
    )
    filters.append(
        "[ot_stille]"
        + "".join(labels)
        + f"amix=inputs={len(labels) + 1}:duration=longest:"
          "dropout_transition=0:normalize=0,"
        + f"atrim=0:{duration:.6f},volume={_volume(original_db)}[original_voll]"
    )
    # Das Sidechain-Signal wird vom Kompressor verbraucht. Eine zweite Kopie
    # bleibt hoerbar und wird anschliessend mit der geduckten Musik gemischt.
    filters.append("[original_voll]asplit=2[original_sc][original_mix]")
    filters.append(
        "[musik][original_sc]sidechaincompress="
        f"threshold={DUCK_THRESHOLD:g}:ratio={DUCK_RATIO}:"
        f"attack={DUCK_ATTACK_MS}:release={DUCK_RELEASE_MS}[musik_geduckt]"
    )
    filters.append(
        "[musik_geduckt][original_mix]"
        "amix=inputs=2:duration=longest:dropout_transition=0:normalize=0,"
        "alimiter=limit=0.95:attack=5:release=50:latency=1,"
        f"afade=t=out:st={duration - end_fade:.6f}:d={end_fade:.6f},"
        f"atrim=0:{duration:.6f}[a]"
    )
    return ";".join(filters)


def _number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def validate(
    config: dict[str, Any],
    source_dir: Path,
    duration: float,
    probe_audio: Callable[[Path], tuple[float, bool]],
) -> tuple[list[str], list[str]]:
    """Validiert neue Audiofelder ohne ffprobe-Abhaengigkeit im Modul."""
    errors: list[str] = []
    hints: list[str] = []
    raw_segments = config.get("originalton")
    mix = config.get("audio_mix")

    if raw_segments is None:
        if mix is not None and not music_entries(config):
            hints.append("audio_mix ist gesetzt, aber originalton fehlt - Werte ohne Wirkung")
        elif isinstance(mix, dict) and "originalton_pegel_db" in mix:
            hints.append("audio_mix.originalton_pegel_db ist ohne originalton wirkungslos")
        return errors, hints
    if not isinstance(raw_segments, list):
        return ["Feld originalton muss eine Liste sein"], hints
    if not raw_segments:
        if mix is not None and not music_entries(config):
            hints.append("audio_mix ist gesetzt, aber originalton ist leer - Werte ohne Wirkung")
        elif isinstance(mix, dict) and "originalton_pegel_db" in mix:
            hints.append("audio_mix.originalton_pegel_db ist bei leerem originalton wirkungslos")
        return errors, hints

    numbers: list[int] = []
    timeline_positions: list[float] = []
    for index, segment in enumerate(raw_segments, start=1):
        label = f"Originalton {index}"
        if not isinstance(segment, dict):
            errors.append(f"{label}: Eintrag muss ein Objekt sein")
            continue
        missing = [
            field
            for field in ("n", "clip", "in", "schnitt_bei", "dauer")
            if field not in segment
        ]
        if missing:
            errors.append(f"{label}: Pflichtfelder fehlen: {', '.join(missing)}")
            continue

        number = segment["n"]
        if not isinstance(number, int) or isinstance(number, bool):
            errors.append(f"{label}: n muss eine ganze Zahl sein")
        else:
            numbers.append(number)
            label = f"Originalton {number}"

        numeric_fields = ("in", "schnitt_bei", "dauer")
        if any(not _number(segment[field]) for field in numeric_fields):
            errors.append(f"{label}: in, schnitt_bei und dauer muessen Zahlen sein")
            continue
        source_start = float(segment["in"])
        timeline_start = float(segment["schnitt_bei"])
        segment_duration = float(segment["dauer"])
        timeline_positions.append(timeline_start)
        if source_start < 0:
            errors.append(f"{label}: in darf nicht negativ sein")
        if timeline_start < 0:
            errors.append(f"{label}: schnitt_bei darf nicht negativ sein")
        if segment_duration <= 0:
            errors.append(f"{label}: dauer muss groesser als 0 sein")
        if timeline_start + segment_duration > duration + 0.001:
            errors.append(
                f"{label}: endet bei {timeline_start + segment_duration:.2f}s, "
                f"Film endet bei {duration:.2f}s"
            )

        fade_in = segment.get("fade_in_s", DEFAULT_FADE_S)
        fade_out = segment.get("fade_out_s", DEFAULT_FADE_S)
        if not _number(fade_in) or not _number(fade_out):
            errors.append(f"{label}: fade_in_s und fade_out_s muessen Zahlen sein")
        elif float(fade_in) < 0 or float(fade_out) < 0:
            errors.append(f"{label}: Audio-Fades duerfen nicht negativ sein")
        elif float(fade_in) + float(fade_out) > segment_duration:
            errors.append(f"{label}: Audio-Fades sind zusammen laenger als das Segment")

        level = segment.get("pegel_db", 0.0)
        if not _number(level) or not MIN_DB <= float(level) <= MAX_DB:
            errors.append(f"{label}: pegel_db muss zwischen {MIN_DB:g} und {MAX_DB:g} liegen")

        path = source_dir / str(segment["clip"])
        if not path.is_file():
            errors.append(f"{label}: Datei fehlt: {segment['clip']}")
            continue
        media_duration, has_audio = probe_audio(path)
        if not has_audio:
            errors.append(f"{label}: {segment['clip']} besitzt keine Audiospur")
        if source_start + segment_duration > media_duration + 0.001:
            errors.append(
                f"{label}: liest bis {source_start + segment_duration:.2f}s, "
                f"Clip hat nur {media_duration:.2f}s"
            )

    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        errors.append(f"Originalton-Nummern doppelt vergeben: {duplicates}")
    if timeline_positions != sorted(timeline_positions):
        hints.append("Originaltonsegmente laufen nicht nach schnitt_bei sortiert")

    if mix is None:
        mix = {}
    if not isinstance(mix, dict):
        errors.append("Feld audio_mix muss ein Objekt sein")
    else:
        for field, default in (
            ("musik_pegel_db", DEFAULT_MUSIC_DB),
            ("originalton_pegel_db", DEFAULT_ORIGINAL_DB),
        ):
            value = mix.get(field, default)
            if not _number(value) or not MIN_DB <= float(value) <= MAX_DB:
                errors.append(
                    f"audio_mix.{field} muss zwischen {MIN_DB:g} und {MAX_DB:g} liegen"
                )
    return errors, hints


def validate_music(
    config: dict[str, Any], root: Path, duration: float,
    probe_audio: Callable[[Path], tuple[float, bool]],
) -> tuple[list[str], list[str]]:
    """Validiert die optionale, ueberblendbare Mehrspur-Musiktimeline."""
    errors: list[str] = []
    hints: list[str] = []
    raw = config.get("musik")
    if raw is None:
        return errors, hints
    if not isinstance(raw, list):
        return ["Feld musik muss eine Liste sein"], hints
    if not raw:
        return ["Feld musik darf nicht leer sein; fuer einen Track audio verwenden"], hints
    numbers: list[int] = []
    positions: list[float] = []
    for index, segment in enumerate(raw, start=1):
        label = f"Musik {index}"
        if not isinstance(segment, dict):
            errors.append(f"{label}: Eintrag muss ein Objekt sein")
            continue
        missing = [field for field in ("n", "datei", "schnitt_bei", "dauer")
                   if field not in segment]
        if missing:
            errors.append(f"{label}: Pflichtfelder fehlen: {', '.join(missing)}")
            continue
        if isinstance(segment["n"], int) and not isinstance(segment["n"], bool):
            numbers.append(segment["n"])
            label = f"Musik {segment['n']}"
        else:
            errors.append(f"{label}: n muss eine ganze Zahl sein")
        source_start = segment.get("in", 0.0)
        timeline_start = segment["schnitt_bei"]
        segment_duration = segment["dauer"]
        if not all(_number(value) for value in (source_start, timeline_start, segment_duration)):
            errors.append(f"{label}: in, schnitt_bei und dauer muessen Zahlen sein")
            continue
        source_start = float(source_start)
        timeline_start = float(timeline_start)
        segment_duration = float(segment_duration)
        positions.append(timeline_start)
        if source_start < 0 or timeline_start < 0 or segment_duration <= 0:
            errors.append(f"{label}: in/schnitt_bei duerfen nicht negativ, dauer muss positiv sein")
        if timeline_start + segment_duration > duration + 0.001:
            errors.append(f"{label}: endet hinter der Filmdauer")
        fade_in = segment.get("fade_in_s", DEFAULT_MUSIC_FADE_S)
        fade_out = segment.get("fade_out_s", DEFAULT_MUSIC_FADE_S)
        if not _number(fade_in) or not _number(fade_out) or float(fade_in) < 0 or float(fade_out) < 0:
            errors.append(f"{label}: Fadezeiten muessen nichtnegative Zahlen sein")
        elif float(fade_in) + float(fade_out) > segment_duration:
            errors.append(f"{label}: Fadezeiten sind zusammen laenger als das Segment")
        level = segment.get("pegel_db", 0.0)
        if not _number(level) or not MIN_DB <= float(level) <= MAX_DB:
            errors.append(f"{label}: pegel_db muss zwischen {MIN_DB:g} und {MAX_DB:g} liegen")
        path = root / str(segment["datei"])
        if not path.is_file():
            errors.append(f"{label}: Datei fehlt: {segment['datei']}")
            continue
        media_duration, has_audio = probe_audio(path)
        if not has_audio:
            errors.append(f"{label}: {segment['datei']} besitzt keine Audiospur")
        if source_start + segment_duration > media_duration + 0.001:
            errors.append(
                f"{label}: liest bis {source_start + segment_duration:.2f}s, "
                f"Datei hat nur {media_duration:.2f}s"
            )
    duplicates = sorted({number for number in numbers if numbers.count(number) > 1})
    if duplicates:
        errors.append(f"Musik-Nummern doppelt vergeben: {duplicates}")
    if positions != sorted(positions):
        hints.append("Musiksegmente laufen nicht nach schnitt_bei sortiert")
    mix = config.get("audio_mix", {})
    if not isinstance(mix, dict):
        errors.append("Feld audio_mix muss ein Objekt sein")
    else:
        music_level = mix.get("musik_pegel_db", DEFAULT_MUSIC_DB)
        if not _number(music_level) or not MIN_DB <= float(music_level) <= MAX_DB:
            errors.append(
                f"audio_mix.musik_pegel_db muss zwischen {MIN_DB:g} und {MAX_DB:g} liegen"
            )
    return errors, hints
