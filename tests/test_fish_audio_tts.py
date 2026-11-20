import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from core.fish_audio_tts import DEFAULT_TTS_MODEL, DEFAULT_VOICE_MODEL_ID, FishAudioError, generate_speech


class FishAudioTtsTests(unittest.TestCase):
    def test_generates_mp3_using_free_model_and_configured_voice(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"ID3" + (b"x" * 2048)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"FISH_API_KEY": "test-key", "FISH_VOICE_MODEL_ID": "test-voice"},
            clear=True,
        ), patch("core.fish_audio_tts.urllib.request.urlopen", return_value=response) as urlopen:
            output = Path(temp_dir) / "voice.mp3"
            generate_speech("مرحبا يا أصدقاء", output)
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size, 1024)
            request = urlopen.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
            self.assertEqual(request.get_header("Model"), DEFAULT_TTS_MODEL)
            self.assertIn(b'"reference_id": "test-voice"', request.data)

    def test_uses_saved_voice_id_when_no_override_is_set(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b"ID3" + (b"x" * 2048)
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"FISH_API_KEY": "test-key"}, clear=True
        ), patch("core.fish_audio_tts.urllib.request.urlopen", return_value=response) as urlopen:
            generate_speech("اختبار", Path(temp_dir) / "voice.mp3")
            request = urlopen.call_args.args[0]
            self.assertIn(DEFAULT_VOICE_MODEL_ID.encode(), request.data)

    def test_missing_api_key_fails_before_network_call(self):
        with patch.dict(os.environ, {}, clear=True), patch(
            "core.fish_audio_tts.urllib.request.urlopen"
        ) as urlopen:
            with self.assertRaises(FishAudioError):
                generate_speech("اختبار", Path("unused.mp3"))
            urlopen.assert_not_called()


if __name__ == "__main__":
    unittest.main()
