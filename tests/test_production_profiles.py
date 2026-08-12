import os
import unittest
from unittest.mock import patch

from core.autopilot import build_parser, parse_profile, settings_from_args


class ProductionProfileTests(unittest.TestCase):
    def test_long_profile_uses_landscape_canvas(self):
        profile = parse_profile("long")
        self.assertEqual(profile.canvas, (1920, 1080))
        self.assertEqual(profile.name, "long")

    def test_short_profile_uses_vertical_canvas(self):
        profile = parse_profile("short")
        self.assertEqual(profile.canvas, (1080, 1920))
        self.assertEqual(profile.name, "short")

    def test_unknown_profile_is_rejected(self):
        with self.assertRaises(ValueError):
            parse_profile("square")

    def test_generation_requires_approved_review(self):
        parser = build_parser()
        with patch.dict(os.environ, {"FISH_VOICE_ID": "test-voice"}, clear=False):
            args = parser.parse_args(
                ["--format", "long", "--review-status", "draft", "--voice", "test-voice"]
            )
            with self.assertRaises(ValueError):
                settings_from_args(args)

    def test_approved_long_generation_settings_are_valid(self):
        parser = build_parser()
        with patch.dict(os.environ, {"FISH_VOICE_ID": "test-voice"}, clear=False):
            args = parser.parse_args(
                [
                    "--format",
                    "long",
                    "--review-status",
                    "approved",
                    "--episode-name",
                    "EP01",
                    "--voice",
                    "test-voice",
                ]
            )
            settings = settings_from_args(args)
        self.assertEqual(settings.profile.canvas, (1920, 1080))
        self.assertEqual(settings.review_status, "approved")
        self.assertEqual(settings.title, "EP01")


if __name__ == "__main__":
    unittest.main()
