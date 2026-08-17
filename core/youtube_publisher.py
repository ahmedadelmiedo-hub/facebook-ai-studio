"""Publish scheduled long episodes and Shorts to the authenticated Rowat Alwaqe channel.

The implementation uses YouTube Data API v3 over the standard library so GitHub Actions
needs no local browser login and no service-account credential. The refresh token is the
one-time OAuth grant for the channel owner.
"""

from __future__ import annotations

import http.client
import json
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.content_pipeline import PublishableAsset

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_HOST = "www.googleapis.com"
API_ROOT = "/youtube/v3"
UPLOAD_ROOT = "/upload/youtube/v3"
UPLOAD_SCOPE = "https://www.googleapis.com/auth/youtube.upload"
PLAYLIST_SCOPE = "https://www.googleapis.com/auth/youtube"


@dataclass(frozen=True)
class YouTubeSettings:
    client_id: str
    client_secret: str
    refresh_token: str
    category_id: str = "22"
    default_language: str = "ar"
    notify_subscribers: bool = True


@dataclass(frozen=True)
class UploadResult:
    video_id: str
    playlist_id: str | None
    scheduled_at: str
    video_url: str


def settings_from_env() -> YouTubeSettings:
    required = ("YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN")
    missing = [name for name in required if not os.getenv(name, "").strip()]
    if missing:
        raise ValueError(f"missing YouTube secrets: {', '.join(missing)}")
    return YouTubeSettings(
        client_id=os.environ["YOUTUBE_CLIENT_ID"].strip(),
        client_secret=os.environ["YOUTUBE_CLIENT_SECRET"].strip(),
        refresh_token=os.environ["YOUTUBE_REFRESH_TOKEN"].strip(),
        category_id=os.getenv("YOUTUBE_CATEGORY_ID", "22").strip() or "22",
        default_language=os.getenv("YOUTUBE_DEFAULT_LANGUAGE", "ar").strip() or "ar",
        notify_subscribers=os.getenv("YOUTUBE_NOTIFY_SUBSCRIBERS", "true").lower() == "true",
    )


def parse_google_json(raw: bytes, *, context: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"YouTube returned invalid JSON during {context}") from exc
    if not isinstance(value, dict):
        raise RuntimeError(f"YouTube returned an unexpected response during {context}")
    return value


class YouTubePublisher:
    """Small, idempotent YouTube Data API v3 client for one channel."""

    def __init__(self, settings: YouTubeSettings):
        self.settings = settings
        self._access_token: str | None = None
        self._context = ssl.create_default_context()

    def access_token(self) -> str:
        """Exchange the persistent refresh token for a short-lived access token."""
        if self._access_token:
            return self._access_token
        payload = urllib.parse.urlencode(
            {
                "client_id": self.settings.client_id,
                "client_secret": self.settings.client_secret,
                "refresh_token": self.settings.refresh_token,
                "grant_type": "refresh_token",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=60, context=self._context) as response:
                data = parse_google_json(response.read(), context="OAuth token refresh")
        except urllib.error.HTTPError as exc:
            details = exc.read(800).decode("utf-8", errors="replace")
            raise RuntimeError(f"YouTube OAuth refresh failed with HTTP {exc.code}: {details}") from exc
        token = data.get("access_token")
        if not isinstance(token, str) or not token:
            raise RuntimeError("YouTube OAuth response did not include an access token")
        self._access_token = token
        return token

    def _api_request(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        query_string = urllib.parse.urlencode(query or {})
        url = f"https://{API_HOST}{path}"
        if query_string:
            url = f"{url}?{query_string}"
        headers = {"Authorization": f"Bearer {self.access_token()}"}
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=120, context=self._context) as response:
                return parse_google_json(response.read(), context=f"{method} {path}")
        except urllib.error.HTTPError as exc:
            details = exc.read(1_000).decode("utf-8", errors="replace")
            raise RuntimeError(f"YouTube API {method} {path} failed with HTTP {exc.code}: {details}") from exc

    def ensure_playlist(self, title: str, description: str) -> str:
        """Find the channel playlist by exact title or create it once."""
        page_token = ""
        while True:
            query = {"part": "id,snippet", "mine": "true", "maxResults": "50"}
            if page_token:
                query["pageToken"] = page_token
            data = self._api_request("GET", f"{API_ROOT}/playlists", query=query)
            for item in data.get("items", []):
                snippet = item.get("snippet", {})
                if snippet.get("title") == title and item.get("id"):
                    return str(item["id"])
            page_token = str(data.get("nextPageToken", ""))
            if not page_token:
                break

        data = self._api_request(
            "POST",
            f"{API_ROOT}/playlists",
            query={"part": "snippet,status"},
            body={
                "snippet": {
                    "title": title,
                    "description": description,
                    "defaultLanguage": self.settings.default_language,
                },
                "status": {"privacyStatus": "public"},
            },
        )
        playlist_id = data.get("id")
        if not isinstance(playlist_id, str) or not playlist_id:
            raise RuntimeError("YouTube did not return a playlist ID")
        return playlist_id

    def upload_video(self, asset: PublishableAsset, video_path: Path, playlist_id: str | None) -> UploadResult:
        """Upload one video with scheduled privacy and then add it to its story playlist."""
        if not video_path.is_file() or video_path.stat().st_size == 0:
            raise FileNotFoundError(f"video file not found or empty: {video_path}")
        scheduled_at = datetime.fromisoformat(asset.scheduled_at.replace("Z", "+00:00")).astimezone(UTC)
        privacy_status = "private" if scheduled_at > datetime.now(UTC) else "public"
        publish_at = scheduled_at.isoformat().replace("+00:00", "Z") if privacy_status == "private" else None
        title = asset.title
        if asset.content_format == "short" and "#Shorts" not in title:
            title = f"{title} #Shorts"
        metadata: dict[str, Any] = {
            "snippet": {
                "title": title[:100],
                "description": asset.description,
                "tags": list(asset.tags),
                "categoryId": self.settings.category_id,
                "defaultLanguage": self.settings.default_language,
            },
            "status": {
                "privacyStatus": privacy_status,
                "selfDeclaredMadeForKids": False,
                "embeddable": True,
                "publicStatsViewable": True,
                "containsSyntheticMedia": True,
            },
        }
        if publish_at:
            metadata["status"]["publishAt"] = publish_at
        video_id = self._resumable_upload(video_path, metadata)
        if playlist_id:
            self._api_request(
                "POST",
                f"{API_ROOT}/playlistItems",
                query={"part": "snippet"},
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {"kind": "youtube#video", "videoId": video_id},
                    }
                },
            )
        return UploadResult(
            video_id=video_id,
            playlist_id=playlist_id,
            scheduled_at=asset.scheduled_at,
            video_url=f"https://www.youtube.com/watch?v={video_id}",
        )

    def _resumable_upload(self, video_path: Path, metadata: dict[str, Any]) -> str:
        """Start and stream a resumable upload without loading the whole video in memory."""
        body = json.dumps(metadata, ensure_ascii=False).encode("utf-8")
        init_path = (
            f"{UPLOAD_ROOT}/videos?part=snippet,status&uploadType=resumable"
            f"&notifySubscribers={'true' if self.settings.notify_subscribers else 'false'}"
        )
        init_request = urllib.request.Request(
            f"https://{API_HOST}{init_path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.access_token()}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_path.stat().st_size),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(init_request, timeout=120, context=self._context) as response:
                upload_url = response.headers.get("Location")
        except urllib.error.HTTPError as exc:
            details = exc.read(1_000).decode("utf-8", errors="replace")
            raise RuntimeError(f"YouTube upload initialization failed with HTTP {exc.code}: {details}") from exc
        if not upload_url:
            raise RuntimeError("YouTube did not return a resumable upload URL")

        parsed = urllib.parse.urlsplit(upload_url)
        connection = http.client.HTTPSConnection(parsed.netloc, context=self._context, timeout=600)
        try:
            connection.putrequest("PUT", parsed.path + (("?" + parsed.query) if parsed.query else ""))
            connection.putheader("Authorization", f"Bearer {self.access_token()}")
            connection.putheader("Content-Type", "video/mp4")
            connection.putheader("Content-Length", str(video_path.stat().st_size))
            connection.endheaders()
            with video_path.open("rb") as source:
                while chunk := source.read(8 * 1024 * 1024):
                    connection.send(chunk)
            response = connection.getresponse()
            response_body = response.read()
        finally:
            connection.close()
        if response.status not in (200, 201):
            details = response_body[:1_000].decode("utf-8", errors="replace")
            raise RuntimeError(f"YouTube video upload failed with HTTP {response.status}: {details}")
        data = parse_google_json(response_body, context="video upload")
        video_id = data.get("id")
        if not isinstance(video_id, str) or not video_id:
            raise RuntimeError("YouTube upload response did not include a video ID")
        return video_id
