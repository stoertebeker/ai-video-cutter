r"""Transkribiert die Tonspur aller Clips eines Projekts mit WhisperX.

WhisperX laeuft absichtlich in einer separaten Python-3.10-Umgebung. Das
Skript selbst importiert WhisperX erst nach der Dateipruefung, damit
``--dry-run`` auch in der normalen Werkzeug-Venv funktioniert.

Beispiel:

    .venv-whisperx\Scripts\python.exe transcribe_clips.py \
        material/Megamarsch_Frankfurt_2025

Die abgeleiteten JSON-Dateien landen standardmaessig unter
``audio/<projekt>/transkripte``. Quellclips werden nie veraendert.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from importlib import metadata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).parent
VIDEO_SUFFIXES = {".mp4", ".mov", ".mts", ".mkv", ".avi"}
SCHEMA_VERSION = 1


def resolve_path(value: str | Path) -> Path:
    """Loest relative Pfade wie die uebrigen Werkzeuge gegen das Repo auf."""
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def find_clips(source: Path, names: list[str], name_filter: str) -> list[Path]:
    """Findet Videos deterministisch; ``names`` sind exakte Dateinamen."""
    if not source.is_dir():
        raise ValueError(f"Quellordner fehlt: {source}")

    requested = set(names)
    clips = sorted(
        (
            path
            for path in source.iterdir()
            if path.is_file()
            and path.suffix.lower() in VIDEO_SUFFIXES
            and (not requested or path.name in requested)
            and name_filter in path.name
        ),
        key=lambda path: path.name.casefold(),
    )

    if requested:
        missing = sorted(requested - {path.name for path in clips})
        if missing:
            raise ValueError("Angeforderte Clips fehlen: " + ", ".join(missing))
    if not clips:
        raise ValueError(f"Keine passenden Videoclips in {source}")
    return clips


def source_identity(clip: Path) -> dict[str, int | str]:
    """Kleine Identitaet fuer sicheres Fortsetzen ohne Videohash."""
    stat = clip.stat()
    return {
        "file": clip.name,
        "size_bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def output_is_current(
    output: Path, clip: Path, model_name: str, requested_language: str | None
) -> bool:
    """True, wenn Quelle und inhaltlich relevante Einstellungen gleich sind."""
    try:
        document = json.loads(output.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, UnicodeError, json.JSONDecodeError):
        return False

    if not isinstance(document, dict):
        return False
    settings = document.get("settings", {})
    if not isinstance(settings, dict):
        return False
    return (
        document.get("schema_version") == SCHEMA_VERSION
        and document.get("source") == source_identity(clip)
        and settings.get("model") == model_name
        and settings.get("requested_language") == requested_language
    )


def _finite_float(value: Any) -> float | None:
    """Konvertiert auch numpy-Zahlen und verwirft NaN/Inf."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return round(number, 6) if math.isfinite(number) else None


def _normalise_word(word: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {"word": str(word.get("word", ""))}
    for field in ("start", "end", "score"):
        value = _finite_float(word.get(field))
        if value is not None:
            clean[field] = value
    if word.get("speaker") is not None:
        clean["speaker"] = str(word["speaker"])
    return clean


def _normalise_segment(segment: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {"text": str(segment.get("text", "")).strip()}
    for field in ("start", "end"):
        value = _finite_float(segment.get(field))
        if value is not None:
            clean[field] = value
    words = segment.get("words") or []
    clean["words"] = [_normalise_word(word) for word in words]
    if segment.get("speaker") is not None:
        clean["speaker"] = str(segment["speaker"])
    return clean


def make_document(
    *,
    clip: Path,
    result: dict[str, Any],
    model_name: str,
    requested_language: str | None,
    device: str,
    compute_type: str,
    whisperx_version: str,
) -> dict[str, Any]:
    """Baut das stabile, schnittfreundliche JSON aus WhisperX-Ausgaben."""
    detected_language = result.get("language") or requested_language
    return {
        "schema_version": SCHEMA_VERSION,
        "source": source_identity(clip),
        "engine": {"name": "whisperx", "version": whisperx_version},
        "settings": {
            "model": model_name,
            "requested_language": requested_language,
            "device": device,
            "compute_type": compute_type,
        },
        "language": detected_language,
        "segments": [
            _normalise_segment(segment) for segment in result.get("segments", [])
        ],
    }


def write_json_atomic(path: Path, document: dict[str, Any]) -> None:
    """Schreibt nie eine halbfertige Transkriptdatei an den Zielpfad."""
    write_text_atomic(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")


def write_text_atomic(path: Path, text: str) -> None:
    """Speichert auch lesbare Exporte atomar als UTF-8."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def format_timestamp(seconds: float) -> str:
    """SRT-Zeit mit Millisekunden, auch beim Uebertrag zur naechsten Minute."""
    total_ms = max(0, int(seconds * 1000 + 0.5))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{whole_seconds:02},{milliseconds:03}"


def write_readable_exports(path: Path, document: dict[str, Any]) -> None:
    """Ergaenzt TXT und segmentbasierte SRT; fehlende Zeiten nie erfinden.

    JSON bleibt der Vertrag fuer wortgenaue Schnittentscheidungen. Die SRT
    verwendet ausschliesslich vorhandene Segmentzeiten, keine geratenen
    Wortzeiten und keine automatische Sprecherzuordnung.
    """
    lines = [f"Transkript: {document['source']['file']}",
             "Zeitmarken beziehen sich auf den Originalclip.", ""]
    cues = []
    for segment in document.get("segments", []):
        text = " ".join(str(segment.get("text", "")).split())
        if not text:
            continue
        start = _finite_float(segment.get("start"))
        end = _finite_float(segment.get("end"))
        timed = start is not None and end is not None and 0 <= start < end
        if timed:
            a, b = format_timestamp(start), format_timestamp(end)
            lines.append(f"[{a} – {b}] {text}")
            # Nach Rundung duerfen keine Null-Laengen-Cues entstehen.
            if a != b:
                cues.append(f"{len(cues) + 1}\n{a} --> {b}\n{text}\n")
        else:
            lines.append(text)
    write_text_atomic(path.with_suffix(".txt"), "\n".join(lines) + "\n")
    write_text_atomic(path.with_suffix(".srt"), "\n".join(cues))


def transcribe_one(
    *,
    whisperx: Any,
    model: Any,
    clip: Path,
    batch_size: int,
    requested_language: str | None,
    device: str,
    alignment_cache: dict[str, tuple[Any, Any]],
) -> dict[str, Any]:
    """Transkribiert und richtet ein Cliptranskript wortgenau aus."""
    audio = whisperx.load_audio(str(clip))
    raw = model.transcribe(audio, batch_size=batch_size)
    language = raw.get("language") or requested_language
    if not language:
        raise RuntimeError(f"WhisperX hat fuer {clip.name} keine Sprache erkannt")

    if language not in alignment_cache:
        alignment_cache[language] = whisperx.load_align_model(
            language_code=language, device=device
        )
    align_model, align_metadata = alignment_cache[language]
    aligned = whisperx.align(
        raw.get("segments", []),
        align_model,
        align_metadata,
        audio,
        device,
        return_char_alignments=False,
    )
    aligned["language"] = language
    return aligned


def load_whisperx() -> tuple[Any, Any]:
    """Importiert die schwere Laufzeit erst, wenn wirklich gearbeitet wird."""
    try:
        import torch
        import whisperx
    except ImportError as exc:
        raise RuntimeError(
            "WhisperX ist in diesem Python nicht installiert. "
            "Die separate Umgebung ist in WHISPERX.md beschrieben."
        ) from exc
    return whisperx, torch


def choose_runtime(device: str, compute_type: str, torch: Any) -> tuple[str, str]:
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    if device == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("--device cuda gewaehlt, aber PyTorch sieht keine CUDA-GPU")
    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"
    return device, compute_type


def package_version(name: str) -> str:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return "unbekannt"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="Quellordner, z.B. material/<projekt>")
    parser.add_argument(
        "--output",
        help="Zielordner; Vorgabe: audio/<projekt>/transkripte",
    )
    parser.add_argument(
        "--clip",
        action="append",
        default=[],
        help="Nur dieser exakte Dateiname; mehrfach verwendbar",
    )
    parser.add_argument("--filter", default="", help="Namensfragment als Filter")
    parser.add_argument("--model", default="large-v3", help="Whisper-Modell")
    parser.add_argument(
        "--language",
        default="de",
        help="Sprachcode; 'auto' fuer Erkennung je Clip (Vorgabe: de)",
    )
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--device", choices=("auto", "cuda", "cpu"), default="auto")
    parser.add_argument(
        "--compute-type",
        choices=("auto", "float16", "float32", "int8"),
        default="auto",
    )
    parser.add_argument("--force", action="store_true", help="Vorhandene JSON neu bauen")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Clips und Zielpfade zeigen, ohne WhisperX zu laden",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.batch_size < 1:
        raise SystemExit("--batch-size muss mindestens 1 sein")

    source = resolve_path(args.source)
    output = (
        resolve_path(args.output)
        if args.output
        else ROOT / "audio" / source.name / "transkripte"
    )
    requested_language = None if args.language.lower() == "auto" else args.language
    try:
        clips = find_clips(source, args.clip, args.filter)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc

    pending: list[tuple[Path, Path]] = []
    for clip in clips:
        # Vollstaendiger Dateiname verhindert Kollisionen wie clip.mov und
        # clip.mp4 im selben Materialordner.
        destination = output / f"{clip.name}.whisperx.json"
        current = output_is_current(
            destination, clip, args.model, requested_language
        )
        status = "NEU" if args.force or not current else "AKTUELL"
        print(f"{status:7} {clip.name} -> {destination}")
        if args.force or not current:
            pending.append((clip, destination))
        elif not args.dry_run:
            # Auch alte, aktuelle JSONs erhalten Exporte ohne Modell-Lauf.
            write_readable_exports(
                destination, json.loads(destination.read_text(encoding="utf-8-sig"))
            )

    if args.dry_run or not pending:
        print(f"{len(pending)} von {len(clips)} Clip(s) zu transkribieren")
        return 0

    try:
        whisperx, torch = load_whisperx()
        device, compute_type = choose_runtime(args.device, args.compute_type, torch)
        model = whisperx.load_model(
            args.model,
            device,
            compute_type=compute_type,
            language=requested_language,
        )
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    print(
        f"WhisperX {package_version('whisperx')}, {device}/{compute_type}, "
        f"Modell {args.model}, Batch {args.batch_size}"
    )
    failures: list[str] = []
    alignment_cache: dict[str, tuple[Any, Any]] = {}
    for index, (clip, destination) in enumerate(pending, start=1):
        print(f"[{index}/{len(pending)}] {clip.name}", flush=True)
        try:
            result = transcribe_one(
                whisperx=whisperx,
                model=model,
                clip=clip,
                batch_size=args.batch_size,
                requested_language=requested_language,
                device=device,
                alignment_cache=alignment_cache,
            )
            document = make_document(
                clip=clip,
                result=result,
                model_name=args.model,
                requested_language=requested_language,
                device=device,
                compute_type=compute_type,
                whisperx_version=package_version("whisperx"),
            )
            write_json_atomic(destination, document)
            write_readable_exports(destination, document)
        except Exception as exc:  # pro Clip fortsetzen, Fehler am Ende melden
            failures.append(f"{clip.name}: {exc}")
            print(f"FEHLER  {clip.name}: {exc}", file=sys.stderr)

    if failures:
        print("\nNicht transkribiert:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1
    print(f"Fertig: {len(pending)} Transkript(e) in {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
