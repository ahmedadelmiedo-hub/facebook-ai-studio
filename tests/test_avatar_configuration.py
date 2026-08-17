import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from core.autopilot import build_parser, settings_from_args


CHARACTER_FILE = Path("content/characters/nour-podcast-host-v1.json")


class AvatarConfigurationTests(unittest.TestCase):
    def _base_args(self, *extra: str):
        return build_parser().parse_args(
            [
                "--voice",
                "test-voice",
                "--model",
                "test-model",
                "--format",
                "long",
                "--review-status",
                "approved",
                "--character-file",
                str(CHARACTER_FILE),
                "--scene-prompt",
                "Nour narrates a case",
                "--avatar-episode",
                "--dry-run",
                *extra,
            ]
        )

    def test_sadtalker_dry_run_uses_local_image(self):
        with TemporaryDirectory() as directory:
            image = Path(directory) / "nour.png"
            image.write_bytes(b"fake")
            settings = settings_from_args(
                self._base_args(
                    "--avatar-provider",
                    "sadtalker",
                    "--avatar-source-image",
                    str(image),
                )
            )
            self.assertEqual(settings.avatar_provider, "sadtalker")
            self.assertEqual(settings.avatar_source_image, image)

    def test_did_avatar_requires_source_url(self):
        with self.assertRaisesRegex(ValueError, "D-ID avatar episodes require"):
            settings_from_args(self._base_args("--avatar-provider", "d_id"))


if __name__ == "__main__":
    unittest.main()
