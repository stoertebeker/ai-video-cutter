import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

import transcribe_clips as tc


class FakeModel:
    def transcribe(self, audio, batch_size):
        self.call = (audio, batch_size)
        return {"language": "de", "segments": [{"text": " Rohtext "}]}


class FakeWhisperX:
    def __init__(self):
        self.align_loads = 0

    def load_audio(self, path):
        return f"audio:{path}"

    def load_align_model(self, language_code, device):
        self.align_loads += 1
        return f"align:{language_code}", {"device": device}

    def align(
        self,
        segments,
        align_model,
        align_metadata,
        audio,
        device,
        return_char_alignments,
    ):
        self.last_align = (
            segments,
            align_model,
            align_metadata,
            audio,
            device,
            return_char_alignments,
        )
        return {
            "segments": [
                {
                    "start": 1,
                    "end": 2.5,
                    "text": " Grüß dich ",
                    "words": [
                        {"word": " Grüß", "start": 1, "end": 1.4, "score": 0.9}
                    ],
                }
            ]
        }


class TranscribeClipsTests(unittest.TestCase):
    def test_readable_exports_preserve_text_but_do_not_invent_timestamps(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "clip.mp4.whisperx.json"
            document = {"source": {"file": "clip.mp4"}, "segments": [
                {"start": 59.9996, "end": 62.2, "text": " Grüß\n dich "},
                {"text": "Ohne Zeit"},
                {"start": 4, "end": 3, "text": "Ungültiger Bereich"},
                {"start": 1.0001, "end": 1.0002, "text": "Sehr kurz"},
            ]}
            tc.write_readable_exports(output, document)
            self.assertEqual(output.with_suffix(".srt").read_text(encoding="utf-8"),
                             "1\n00:01:00,000 --> 00:01:02,200\nGrüß dich\n")
            text = output.with_suffix(".txt").read_text(encoding="utf-8")
            self.assertIn("Ohne Zeit", text)
            self.assertIn("Ungültiger Bereich", text)
            self.assertFalse(output.with_suffix(".srt.tmp").exists())

    def test_cached_transcript_backfills_exports_without_loading_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source"
            source.mkdir()
            clip = source / "clip.mp4"
            clip.write_bytes(b"video")
            output = Path(tmp) / "output"
            destination = output / "clip.mp4.whisperx.json"
            document = tc.make_document(
                clip=clip, result={"segments": [{"start": 0, "end": 1, "text": "Hallo"}]},
                model_name="large-v3", requested_language="de", device="cpu",
                compute_type="int8", whisperx_version="test")
            tc.write_json_atomic(destination, document)
            with patch.object(tc, "load_whisperx", side_effect=AssertionError("Modell geladen")):
                self.assertEqual(tc.main([str(source), "--output", str(output)]), 0)
            self.assertTrue(destination.with_suffix(".txt").is_file())
            self.assertTrue(destination.with_suffix(".srt").is_file())

    def test_find_clips_filters_and_sorts_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "B.MP4").touch()
            (source / "a.mov").touch()
            (source / "note.txt").touch()

            self.assertEqual(
                [path.name for path in tc.find_clips(source, [], "")],
                ["a.mov", "B.MP4"],
            )

    def test_transcribe_reuses_alignment_model_and_document_is_json_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            clip = Path(tmp) / "clip.mp4"
            clip.write_bytes(b"video")
            backend = FakeWhisperX()
            model = FakeModel()
            cache = {}

            first = tc.transcribe_one(
                whisperx=backend,
                model=model,
                clip=clip,
                batch_size=4,
                requested_language="de",
                device="cuda",
                alignment_cache=cache,
            )
            tc.transcribe_one(
                whisperx=backend,
                model=model,
                clip=clip,
                batch_size=4,
                requested_language="de",
                device="cuda",
                alignment_cache=cache,
            )
            self.assertEqual(backend.align_loads, 1)

            document = tc.make_document(
                clip=clip,
                result=first,
                model_name="large-v3",
                requested_language="de",
                device="cuda",
                compute_type="float16",
                whisperx_version="test",
            )
            self.assertEqual(document["segments"][0]["text"], "Grüß dich")
            json.dumps(document, ensure_ascii=False)

    def test_atomic_output_is_recognised_as_current(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            clip = root / "clip.mp4"
            output = root / "out" / "clip.whisperx.json"
            clip.write_bytes(b"video")
            document = tc.make_document(
                clip=clip,
                result={"language": "de", "segments": []},
                model_name="large-v3",
                requested_language="de",
                device="cpu",
                compute_type="int8",
                whisperx_version="test",
            )
            tc.write_json_atomic(output, document)

            self.assertTrue(tc.output_is_current(output, clip, "large-v3", "de"))
            self.assertFalse(tc.output_is_current(output, clip, "small", "de"))
            clip.write_bytes(b"changed")
            self.assertFalse(tc.output_is_current(output, clip, "large-v3", "de"))


if __name__ == "__main__":
    unittest.main()
