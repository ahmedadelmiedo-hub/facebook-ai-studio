import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.captions import ass_time, build_estimated_cues, write_arabic_ass
from core.scene_renderer import validate_scene_plan


class VisualPipelineTests(unittest.TestCase):
    def test_ass_time(self):
        self.assertEqual(ass_time(0), "0:00:00.00")
        self.assertEqual(ass_time(12.345), "0:00:12.35")

    def test_estimated_cues_cover_duration(self):
        cues = build_estimated_cues("نور تفحص الشريط. الباب يتحرك.", 10.0)
        self.assertGreaterEqual(len(cues), 2)
        self.assertAlmostEqual(cues[0].start, 0.0)
        self.assertAlmostEqual(cues[-1].end, 10.0)
        for previous, current in zip(cues, cues[1:]):
            self.assertAlmostEqual(previous.end, current.start)

    def test_ass_file_is_written(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "captions.ass"
            cues = build_estimated_cues("نور تتحدث الآن.", 2.0)
            write_arabic_ass(cues, path, vertical=False)
            content = path.read_text(encoding="utf-8")
            self.assertIn("Noto Sans Arabic", content)
            self.assertIn("نور تتحدث الآن", content)

    def test_scene_plan_duration_and_images(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            first = root / "one.png"
            second = root / "two.png"
            first.write_bytes(b"x" * 12_000)
            second.write_bytes(b"y" * 12_000)
            plan = {
                "scenes": [
                    {"start": 0, "end": 2, "image": str(first)},
                    {"start": 2, "end": 4, "image": str(second)},
                ]
            }
            validate_scene_plan(plan, 4.0)

    def test_invalid_scene_gap_is_rejected(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "one.png"
            image.write_bytes(b"x" * 12_000)
            plan = {"scenes": [{"start": 0, "end": 2, "image": str(image)}]}
            with self.assertRaises(ValueError):
                validate_scene_plan(plan, 3.5)


if __name__ == "__main__":
    unittest.main()
