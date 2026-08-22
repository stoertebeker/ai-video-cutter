import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

import overlay_timeline as ot


GPX = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" xmlns="http://www.topografix.com/GPX/1/1">
  <trk><trkseg>
    <trkpt lat="50.0000" lon="8.0000"><time>2025-10-11T10:00:00Z</time></trkpt>
    <trkpt lat="50.0000" lon="8.0010"><time>2025-10-11T10:00:10Z</time></trkpt>
    <trkpt lat="50.0000" lon="8.0020"><time>2025-10-11T10:00:20Z</time></trkpt>
  </trkseg></trk>
</gpx>
"""


class OverlayTimelineTests(unittest.TestCase):
    def test_gpx_progress_interpolates_distance_and_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "route.gpx"
            path.write_text(GPX, encoding="utf-8")
            points = ot.read_gpx(path)
            lat, lon, distance, travelled = ot.progress_at(
                points, datetime(2025, 10, 11, 10, 0, 15, tzinfo=timezone.utc)
            )
            self.assertAlmostEqual(lat, 50.0, places=5)
            self.assertAlmostEqual(lon, 8.0015, places=5)
            self.assertGreater(distance, 100)
            self.assertLess(distance, 120)
            self.assertEqual(travelled[-1], (lat, lon))

    def test_prepare_builds_route_and_future_image_overlays(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "route.gpx").write_text(GPX, encoding="utf-8")
            Image.new("RGB", (100, 50), "red").save(root / "photo.jpg")
            config = {
                "gpx": "route.gpx",
                "overlays": [
                    {"n": 1, "type": "route_progress", "zeit": "2025-10-11T10:00:10Z",
                     "schnitt_bei": 1.0, "dauer": 4.0},
                    {"n": 2, "type": "image", "datei": "photo.jpg",
                     "schnitt_bei": 6.0, "dauer": 2.0, "breite": 300},
                ],
            }
            args, graph = ot.prepare(config, root, root / "assets", 5, 1920, 1080)
            self.assertEqual(args.count("-loop"), 2)
            self.assertTrue((root / "assets" / "route_001.png").is_file())
            self.assertIn("[5:v]", graph)
            self.assertIn("[6:v]", graph)
            self.assertIn("scale=300:-2", graph)
            self.assertTrue(graph.endswith("[v]"))

    def test_validation_rejects_out_of_range_and_missing_image(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "route.gpx").write_text(GPX, encoding="utf-8")
            config = {
                "gpx": "route.gpx",
                "overlays": [
                    {"n": 1, "type": "route_progress", "zeit": "2025-10-11T11:00:00Z",
                     "schnitt_bei": 9.0, "dauer": 4.0},
                    {"n": 1, "type": "image", "datei": "missing.jpg",
                     "schnitt_bei": 1.0, "dauer": 2.0},
                ],
            }
            errors, _ = ot.validate(config, root, 10.0)
            joined = "\n".join(errors)
            self.assertIn("ausserhalb der Filmdauer", joined)
            self.assertIn("Zeit liegt ausserhalb", joined)
            self.assertIn("Bilddatei fehlt", joined)
            self.assertIn("doppelt vergeben", joined)


if __name__ == "__main__":
    unittest.main()
