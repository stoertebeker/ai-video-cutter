import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import transition_timeline as tt


class TransitionTimelineTests(unittest.TestCase):
    def test_same_clip_is_grouped_and_does_not_get_a_transition(self):
        shots = [
            {"n": 1, "clip": "a.mp4", "dauer": 2.0},
            {"n": 2, "clip": "a.mp4", "dauer": 3.0},
            {"n": 3, "clip": "b.mp4", "dauer": 4.0},
        ]
        config = {"clipwechsel_blende_s": 0.35}

        self.assertEqual(tt.group_indices(shots), [[0, 1], [2]])
        self.assertEqual(tt.boundary_duration(config, shots, 0), 0.0)
        self.assertEqual(tt.boundary_duration(config, shots, 1), 0.35)

    def test_filter_graph_accounts_for_every_overlap(self):
        graph, duration = tt.filter_graph([5.0, 4.0, 3.0], 0.35)

        self.assertIn("offset=4.650000", graph)
        self.assertIn("offset=8.300000", graph)
        self.assertTrue(graph.endswith("[video_timeline]"))
        self.assertAlmostEqual(duration, 11.3)

    def test_validation_rejects_bad_or_too_long_values(self):
        shots = [
            {"n": 1, "clip": "a.mp4", "dauer": 0.2},
            {"n": 2, "clip": "b.mp4", "dauer": 1.0},
        ]
        self.assertIn("Zahl", tt.validate(
            {"clipwechsel_blende_s": True, "fps": 30}, shots
        )[0])
        joined = "\n".join(tt.validate(
            {"clipwechsel_blende_s": 0.2, "fps": 30}, shots
        ))
        self.assertIn("Nachbarshot", joined)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg oder ffprobe fehlt",
    )
    def test_ffmpeg_chain_has_expected_duration_and_middle_mix(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = []
            for index, color in enumerate(("red", "blue", "green")):
                path = root / f"{index}.mp4"
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i",
                        f"color={color}:size=64x36:rate=25:duration=1",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(path),
                    ],
                    check=True,
                )
                inputs.extend(["-i", str(path)])

            graph, expected = tt.filter_graph([1.0, 1.0, 1.0], 0.2)
            output = root / "result.mp4"
            environment = os.environ.copy()
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", *inputs,
                    "-filter_complex", graph, "-map", "[video_timeline]",
                    "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                    str(output),
                ],
                check=True,
                env=environment,
            )
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    "format=duration", "-of", "json", str(output),
                ],
                capture_output=True, text=True, check=True,
            )
            actual = float(json.loads(probe.stdout)["format"]["duration"])
            self.assertAlmostEqual(actual, expected, places=2)

    @unittest.skipUnless(
        shutil.which("ffmpeg") and shutil.which("ffprobe"),
        "ffmpeg oder ffprobe fehlt",
    )
    def test_render_integrates_grouped_video_music_and_original_audio(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            for name, color, tone in (
                ("a.mp4", "red", 700),
                ("b.mp4", "blue", 1000),
            ):
                subprocess.run(
                    [
                        "ffmpeg", "-y", "-loglevel", "error",
                        "-f", "lavfi", "-i",
                        f"color={color}:size=160x90:rate=25:duration=2",
                        "-f", "lavfi", "-i",
                        f"sine=frequency={tone}:duration=2:sample_rate=48000",
                        "-c:v", "libx264", "-pix_fmt", "yuv420p",
                        "-c:a", "aac", "-shortest", str(source / name),
                    ],
                    check=True,
                )
            music = root / "music.wav"
            subprocess.run(
                [
                    "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "sine=frequency=440:duration=2:sample_rate=48000",
                    "-c:a", "pcm_s16le", str(music),
                ],
                check=True,
            )

            output = root / "result.mp4"
            cutlist = root / f"transition_integration_{root.name}.json"
            config = {
                "quellen": str(source),
                "audio": str(music),
                "ende_s": 1.65,
                "ausgabe": str(output),
                "breite": 160,
                "hoehe": 90,
                "fps": 25,
                "quell_fps": 25,
                "video_ausblende_s": 0.2,
                "clipwechsel_blende_s": 0.35,
                "audio_mix": {
                    "musik_pegel_db": -24.0,
                    "originalton_pegel_db": 0.0,
                },
                "originalton": [
                    {
                        "n": 1, "clip": "a.mp4", "in": 0.0,
                        "schnitt_bei": 0.0, "dauer": 1.0,
                        "fade_out_s": 0.35,
                    },
                    {
                        "n": 2, "clip": "b.mp4", "in": 0.0,
                        "schnitt_bei": 0.65, "dauer": 1.0,
                        "fade_in_s": 0.35,
                    },
                ],
                "shots": [
                    {
                        "n": 1, "clip": "a.mp4", "in": 0.0,
                        "schnitt_bei": 0.0, "dauer": 0.5,
                    },
                    {
                        "n": 2, "clip": "a.mp4", "in": 0.5,
                        "schnitt_bei": 0.5, "dauer": 0.5,
                    },
                    {
                        "n": 3, "clip": "b.mp4", "in": 0.0,
                        "schnitt_bei": 0.65, "dauer": 1.0,
                    },
                ],
            }
            cutlist.write_text(json.dumps(config), encoding="utf-8")
            segment_dir = repository / "segments" / cutlist.stem
            environment = os.environ.copy()
            environment["ENCODER"] = "cpu"
            try:
                validation = subprocess.run(
                    [sys.executable, str(repository / "validate_cutlist.py"),
                     str(cutlist)],
                    capture_output=True, text=True, env=environment,
                )
                self.assertEqual(
                    validation.returncode, 0,
                    validation.stdout + validation.stderr,
                )
                render = subprocess.run(
                    [sys.executable, str(repository / "render.py"), str(cutlist)],
                    capture_output=True, text=True, env=environment,
                )
                self.assertEqual(render.returncode, 0, render.stdout + render.stderr)
                probe = subprocess.run(
                    [
                        "ffprobe", "-v", "error", "-show_entries",
                        "format=duration", "-of", "json", str(output),
                    ],
                    capture_output=True, text=True, check=True,
                )
                actual = float(json.loads(probe.stdout)["format"]["duration"])
                # Die Containerdauer liegt auf dem 25-fps-Raster; 1.65 s
                # werden deshalb auf den naechsten ganzen Frame quantisiert.
                self.assertAlmostEqual(actual, 1.65, delta=1 / 25)
            finally:
                shutil.rmtree(segment_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
