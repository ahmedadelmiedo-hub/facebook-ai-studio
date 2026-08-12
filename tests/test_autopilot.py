import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.autopilot import build_output_paths, parse_color, sanitize_episode_name


class AutopilotTests(unittest.TestCase):
    def test_parse_color(self):
        self.assertEqual(parse_color("#0A0B0C"), (10, 11, 12))
        self.assertEqual(parse_color("10, 20, 30"), (10, 20, 30))
        with self.assertRaises(ValueError):
            parse_color("256,0,0")

    def test_sanitize_episode_name(self):
        self.assertEqual(sanitize_episode_name("EP 01 / test"), "EP_01_test")

    def test_output_paths_are_created(self):
        with TemporaryDirectory() as directory:
            output_dir = Path(directory) / "artifacts"
            audio_path, video_path = build_output_paths(output_dir, "EP01")
            self.assertTrue(output_dir.is_dir())
            self.assertEqual(audio_path.name, "EP01.mp3")
            self.assertEqual(video_path.name, "EP01.mp4")


if __name__ == "__main__":
    unittest.main()
