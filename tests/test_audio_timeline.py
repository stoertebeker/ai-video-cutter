import json
import math
import os
import shutil
import subprocess
import tempfile
import unittest
import wave
from array import array
from pathlib import Path

import audio_timeline as at


class AudioTimelineTests(unittest.TestCase):
    def test_missing_originalton_keeps_legacy_mode(self):
        self.assertEqual(at.entries({}), [])
        with self.assertRaises(ValueError):
            at.filter_graph({}, 10.0)

    def test_filter_uses_independent_source_and_timeline_times(self):
        config = {
            "originalton": [
                {
                    "n": 7,
                    "clip": "clip.mp4",
                    "in": 12.5,
                    "schnitt_bei": 3.25,
                    "dauer": 4.0,
                    "pegel_db": -2.0,
                }
            ],
            "audio_mix": {"musik_pegel_db": -20.0},
        }
        args = at.input_args(config, Path("material/test"))
        graph = at.filter_graph(config, 10.0)

        self.assertEqual(args[1], "12.500000")
        self.assertEqual(args[3], "4.000000")
        self.assertIn("adelay=3250:all=1", graph)
        self.assertIn("volume=-20dB[musik]", graph)
        self.assertIn("volume=-2dB", graph)
        self.assertIn("sidechaincompress=", graph)
        self.assertTrue(graph.endswith("[a]"))

    def test_validation_checks_audio_bounds_fades_and_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "clip.mp4").touch()
            config = {
                "originalton": [
                    {
                        "n": 1,
                        "clip": "clip.mp4",
                        "in": 9.0,
                        "schnitt_bei": 4.0,
                        "dauer": 2.0,
                        "fade_in_s": 1.5,
                        "fade_out_s": 1.0,
                    },
                    {
                        "n": 1,
                        "clip": "clip.mp4",
                        "in": 0.0,
                        "schnitt_bei": 1.0,
                        "dauer": 1.0,
                    },
                ]
            }

            errors, hints = at.validate(
                config, source, 5.0, lambda _path: (10.0, True)
            )
            joined = "\n".join(errors)
            self.assertIn("Film endet", joined)
            self.assertIn("Clip hat nur", joined)
            self.assertIn("Audio-Fades", joined)
            self.assertIn("doppelt vergeben", joined)
            self.assertIn("nicht nach schnitt_bei sortiert", "\n".join(hints))

    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg fehlt")
    def test_ffmpeg_mix_places_original_audio_on_timeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            music = root / "music.wav"
            voice = root / "voice.wav"
            output = root / "mix.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=2:sample_rate=48000",
                    "-c:a", "pcm_s16le", str(music),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=1000:duration=1:sample_rate=48000",
                    "-c:a", "pcm_s16le", str(voice),
                ],
                check=True,
            )
            config = {
                "originalton": [
                    {
                        "n": 1,
                        "clip": voice.name,
                        "in": 0.0,
                        "schnitt_bei": 0.5,
                        "dauer": 0.7,
                    }
                ],
                "audio_mix": {"musik_pegel_db": -6.0},
            }
            command = [
                "ffmpeg", "-y", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=size=16x16:rate=25:duration=2",
                "-i", str(music),
                *at.input_args(config, root),
                "-filter_complex", at.filter_graph(config, 2.0),
                "-map", "[a]", "-c:a", "pcm_s16le", "-t", "2", str(output),
            ]
            subprocess.run(command, check=True)

            with wave.open(str(output), "rb") as wav:
                self.assertEqual(wav.getframerate(), at.SAMPLE_RATE)
                self.assertEqual(wav.getnchannels(), 2)
                self.assertAlmostEqual(wav.getnframes() / wav.getframerate(), 2.0, places=2)
                samples = array("h", wav.readframes(wav.getnframes()))
                channels = wav.getnchannels()
                rate = wav.getframerate()

            def tone_amplitude(frequency: float, start: float, end: float) -> float:
                first_frame = int(start * rate)
                last_frame = int(end * rate)
                real = imaginary = 0.0
                for frame in range(first_frame, last_frame):
                    mono = sum(
                        samples[frame * channels + channel]
                        for channel in range(channels)
                    ) / channels
                    angle = 2 * math.pi * frequency * frame / rate
                    real += mono * math.cos(angle)
                    imaginary -= mono * math.sin(angle)
                count = last_frame - first_frame
                return 2 * math.hypot(real, imaginary) / count

            # Vor 0.5 s liegt nur 440-Hz-Musik. Ab 0.5 s ist der versetzte
            # 1000-Hz-Originalton da und der Sidechain-Kompressor muss den
            # 440-Hz-Musikanteil messbar absenken.
            music_before = tone_amplitude(440, 0.1, 0.4)
            music_during = tone_amplitude(440, 0.75, 1.05)
            voice_before = tone_amplitude(1000, 0.1, 0.4)
            voice_during = tone_amplitude(1000, 0.75, 1.05)
            self.assertGreater(voice_during, voice_before * 50)
            self.assertLess(music_during, music_before * 0.7)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg oder ffprobe fehlt",
    )
    def test_validator_and_renderer_keep_audio_and_video_in_sync(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            clip = source / "clip.mp4"
            music = root / "music.wav"
            output = root / "rendered.mp4"
            cutlist = root / f"audio_integration_{root.name}.json"
            segment_dir = repository / "segments" / cutlist.stem
            try:
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i", "color=size=320x180:rate=25:duration=2",
                        "-f", "lavfi", "-i", "sine=frequency=1000:duration=2:sample_rate=48000",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(clip),
                    ],
                    check=True,
                )
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                        "-i", "sine=frequency=440:duration=2:sample_rate=48000",
                        "-c:a", "pcm_s16le", str(music),
                    ],
                    check=True,
                )
                config = {
                    "quellen": str(source),
                    "audio": str(music),
                    "ende_s": 2.0,
                    "ausgabe": str(output),
                    "breite": 320,
                    "hoehe": 180,
                    "fps": 25,
                    "quell_fps": 25,
                    "video_ausblende_s": 0.2,
                    "originalton": [
                        {
                            "n": 1,
                            "clip": clip.name,
                            "in": 0.2,
                            "schnitt_bei": 0.5,
                            "dauer": 0.7,
                        }
                    ],
                    "audio_mix": {
                        "musik_pegel_db": -24.0,
                        "originalton_pegel_db": 0.0,
                    },
                    "shots": [
                        {
                            "n": 1,
                            "clip": clip.name,
                            "in": 0.0,
                            "schnitt_bei": 0.0,
                            "dauer": 2.0,
                        }
                    ],
                }
                cutlist.write_text(json.dumps(config), encoding="utf-8")

                validation = subprocess.run(
                    [
                        str(repository / ".venv" / "Scripts" / "python.exe"),
                        str(repository / "validate_cutlist.py"),
                        str(cutlist),
                    ],
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(validation.returncode, 0, validation.stdout + validation.stderr)

                environment = os.environ.copy()
                environment["ENCODER"] = "cpu"
                rendered = subprocess.run(
                    [
                        str(repository / ".venv" / "Scripts" / "python.exe"),
                        str(repository / "render.py"),
                        str(cutlist),
                    ],
                    capture_output=True,
                    text=True,
                    env=environment,
                )
                self.assertEqual(rendered.returncode, 0, rendered.stdout + rendered.stderr)
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-print_format", "json",
                        "-show_entries", "format=duration:stream=codec_type", str(output),
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                media = json.loads(probe.stdout)
                self.assertEqual(
                    {stream["codec_type"] for stream in media["streams"]},
                    {"audio", "video"},
                )
                self.assertAlmostEqual(float(media["format"]["duration"]), 2.0, places=2)

                # Rueckwaertskompatibilitaet: dieselbe Cutlist ohne die neuen
                # Felder muss weiterhin ueber den alten Musikweg rendern.
                legacy_output = root / "legacy.mp4"
                config.pop("originalton")
                config.pop("audio_mix")
                config["ausgabe"] = str(legacy_output)
                cutlist.write_text(json.dumps(config), encoding="utf-8")
                legacy = subprocess.run(
                    [
                        str(repository / ".venv" / "Scripts" / "python.exe"),
                        str(repository / "render.py"),
                        str(cutlist),
                    ],
                    capture_output=True,
                    text=True,
                    env=environment,
                )
                self.assertEqual(legacy.returncode, 0, legacy.stdout + legacy.stderr)
                self.assertTrue(legacy_output.is_file())
            finally:
                shutil.rmtree(segment_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
