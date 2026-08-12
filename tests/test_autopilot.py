import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.autopilot import (
    build_output_paths,
    concatenate_mp3_chunks,
    parse_color,
    sanitize_episode_name,
    split_script_for_tts,
)


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

    def test_long_script_is_split_at_sentence_boundaries(self):
        script = "أول جملة طويلة جدا. ثاني جملة طويلة جدا.\n\nثالث جملة طويلة جدا."
        chunks = split_script_for_tts(script, 35)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(" ".join(chunks).replace("  ", " "), script.replace("\n\n", " "))
        self.assertTrue(all(len(chunk) <= 35 for chunk in chunks))

    def test_mp3_chunks_are_concatenated_in_order(self):
        with TemporaryDirectory() as directory:
            folder = Path(directory)
            first = folder / "one.mp3"
            second = folder / "two.mp3"
            output = folder / "final.mp3"
            first.write_bytes(b"FIRST")
            second.write_bytes(b"SECOND")
            concatenate_mp3_chunks([first, second], output)
            self.assertEqual(output.read_bytes(), b"FIRSTSECOND")


if __name__ == "__main__":
    unittest.main()
