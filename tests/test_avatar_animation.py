import os
import unittest
from unittest.mock import patch

from core.avatar_animation import AvatarProviderError, DIDAvatarProvider


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


if __name__ == "__main__":
    unittest.main()
