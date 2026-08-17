import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from core.avatar_animation import AvatarProviderError, DIDAvatarProvider, SadTalkerProvider, build_avatar_provider


class AvatarAnimationTests(unittest.TestCase):
    def test_provider_requires_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(AvatarProviderError, "D_ID_API_KEY"):
                DIDAvatarProvider()

    def test_provider_requires_https_source_image(self):
        with patch.dict(
            os.environ,
            {"D_ID_API_KEY": "test-key", "D_ID_SOURCE_URL": "file:///tmp/nour.png"},
            clear=True,
        ):
            with self.assertRaisesRegex(AvatarProviderError, "https://"):
                DIDAvatarProvider()

    def test_provider_accepts_configured_source(self):
        with patch.dict(
            os.environ,
            {"D_ID_API_KEY": "test-key", "D_ID_SOURCE_URL": "https://example.com/nour.png"},
            clear=True,
        ):
            provider = DIDAvatarProvider()
            self.assertEqual(provider.source_url, "https://example.com/nour.png")
            self.assertIn("Authorization", provider._headers())

    def test_sadtalker_requires_local_source_image(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "inference.py").write_text("# fake SadTalker entrypoint\n", encoding="utf-8")
            with self.assertRaisesRegex(AvatarProviderError, "AVATAR_SOURCE_IMAGE"):
                SadTalkerProvider(repository_root=root, python_executable=sys.executable)

    def test_sadtalker_runs_cli_and_copies_latest_mp4(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "nour.png"
            audio = root / "segment.wav"
            output = root / "output.mp4"
            image.write_bytes(b"fake-png")
            audio.write_bytes(b"fake-wav")
            (root / "inference.py").write_text(
                """import argparse\nfrom pathlib import Path\n\nparser = argparse.ArgumentParser()\nparser.add_argument('--driven_audio', required=True)\nparser.add_argument('--source_image', required=True)\nparser.add_argument('--result_dir', required=True)\nparser.add_argument('--enhancer')\nparser.add_argument('--still', action='store_true')\nargs = parser.parse_args()\nout = Path(args.result_dir) / 'generated.mp4'\nout.write_bytes(b'fake-mp4')\n""",
                encoding="utf-8",
            )
            provider = SadTalkerProvider(
                source_image=image,
                repository_root=root,
                python_executable=sys.executable,
            )
            result = provider.create_talking_segment(audio_path=audio, output_path=output, name="test-segment")
            self.assertEqual(result, output)
            self.assertEqual(output.read_bytes(), b"fake-mp4")

    def test_factory_selects_sadtalker(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "nour.png"
            image.write_bytes(b"fake-png")
            (root / "inference.py").write_text("# fake SadTalker entrypoint\n", encoding="utf-8")
            with patch.dict(
                os.environ,
                {"SADTALKER_ROOT": str(root), "SADTALKER_PYTHON": sys.executable},
                clear=True,
            ):
                provider = build_avatar_provider("sadtalker", source_image=image)
                self.assertIsInstance(provider, SadTalkerProvider)

    def test_factory_rejects_unknown_provider(self):
        with self.assertRaisesRegex(AvatarProviderError, "unsupported AVATAR_PROVIDER"):
            build_avatar_provider("unknown")


if __name__ == "__main__":
    unittest.main()
