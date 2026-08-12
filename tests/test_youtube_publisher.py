from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from core.content_pipeline import PublishableAsset
from core.youtube_publisher import YouTubePublisher, YouTubeSettings


class YouTubePublisherTests(unittest.TestCase):
    def setUp(self):
        self.publisher = YouTubePublisher(
            YouTubeSettings(
                client_id="client",
                client_secret="secret",
                refresh_token="refresh",
            )
        )
        future = (datetime.now(UTC) + timedelta(days=2)).isoformat().replace("+00:00", "Z")
        self.asset = PublishableAsset(
            asset_id="case-001-EP01",
            series_id="case-001",
            series_title="ملف الرصد 17",
            part_number=1,
            script_file="scripts/long/case-001-EP01.txt",
            content_format="long",
            title="ملف الرصد 17 | البارت 1",
            description="وصف الحلقة",
            tags=("رواة الواقع", "تحقيق"),
            scheduled_at=future,
            playlist_title="ملف الرصد 17 | رواية كاملة",
            playlist_description="وصف القائمة",
        )

    def test_ensure_playlist_reuses_existing_or_creates_once(self):
        with patch.object(self.publisher, "_api_request") as request:
            request.side_effect = [
                {"items": [{"id": "existing", "snippet": {"title": "ملف الرصد 17 | رواية كاملة"}}]},
            ]
            self.assertEqual(self.publisher.ensure_playlist("ملف الرصد 17 | رواية كاملة", "desc"), "existing")
            self.assertEqual(request.call_count, 1)

            request.reset_mock()
            request.side_effect = [
                {"items": []},
                {"id": "created"},
            ]
            self.assertEqual(self.publisher.ensure_playlist("قائمة جديدة", "desc"), "created")
            self.assertEqual(request.call_count, 2)

    def test_future_upload_uses_private_publish_at_and_playlist(self):
        with TemporaryDirectory() as directory:
            video = Path(directory) / "episode.mp4"
            video.write_bytes(b"video")
            with patch.object(self.publisher, "_resumable_upload", return_value="video123") as upload:
                with patch.object(self.publisher, "_api_request", return_value={}) as request:
                    result = self.publisher.upload_video(self.asset, video, "playlist123")
            metadata = upload.call_args.args[1]
            self.assertEqual(metadata["status"]["privacyStatus"], "private")
            self.assertIn("publishAt", metadata["status"])
            self.assertEqual(result.video_id, "video123")
            self.assertEqual(result.playlist_id, "playlist123")
            self.assertEqual(request.call_args.kwargs["body"]["snippet"]["playlistId"], "playlist123")

    def test_short_upload_does_not_require_story_playlist(self):
        with TemporaryDirectory() as directory:
            video = Path(directory) / "short.mp4"
            video.write_bytes(b"video")
            short_asset = PublishableAsset(**{**self.asset.__dict__, "content_format": "short"})
            with patch.object(self.publisher, "_resumable_upload", return_value="short123") as upload:
                with patch.object(self.publisher, "_api_request") as request:
                    result = self.publisher.upload_video(short_asset, video, None)
            self.assertEqual(result.playlist_id, None)
            self.assertEqual(upload.call_args.args[1]["snippet"]["title"].endswith("#Shorts"), True)
            request.assert_not_called()


if __name__ == "__main__":
    unittest.main()
