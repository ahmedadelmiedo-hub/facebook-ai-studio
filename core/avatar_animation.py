"""Talking-avatar provider adapters for audio-driven character segments."""

from __future__ import annotations

import base64
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests


class AvatarProviderError(RuntimeError):
    """Raised when a talking-avatar provider request fails."""


@dataclass(frozen=True)
class AvatarJob:
    job_id: str
    status: str
    result_url: str | None = None


class DIDAvatarProvider:
    """D-ID Talks API adapter using a pre-hosted source image URL."""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = "https://api.d-id.com",
        source_url: str | None = None,
        timeout: int = 60,
    ) -> None:
        self.api_key = (api_key or os.getenv("D_ID_API_KEY", "")).strip()
        self.base_url = base_url.rstrip("/")
        self.source_url = (source_url or os.getenv("D_ID_SOURCE_URL", "")).strip()
        self.timeout = timeout
        if not self.api_key:
            raise AvatarProviderError("D_ID_API_KEY is not configured")
        if not self.source_url:
            raise AvatarProviderError("D_ID_SOURCE_URL must be an https image URL")
        if not self.source_url.startswith(("https://", "s3://")):
            raise AvatarProviderError("D_ID_SOURCE_URL must use https:// or s3://")

    def _headers(self) -> dict[str, str]:
        token = base64.b64encode(f"{self.api_key}:".encode("utf-8")).decode("ascii")
        return {
            "Authorization": f"Basic {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def upload_audio(self, audio_path: Path) -> str:
        """Upload local audio to D-ID temporary storage and return its URL."""
        if not audio_path.is_file():
            raise FileNotFoundError(f"avatar audio not found: {audio_path}")
        with audio_path.open("rb") as handle:
            response = requests.post(
                f"{self.base_url}/audios",
                headers={"Authorization": self._headers()["Authorization"]},
                files={"audio": (audio_path.name, handle, "audio/wav")},
                timeout=self.timeout,
            )
        if response.status_code >= 400:
            raise AvatarProviderError(f"D-ID audio upload failed ({response.status_code}): {response.text[:500]}")
        payload = response.json()
        audio_url = payload.get("url")
        if not audio_url:
            raise AvatarProviderError("D-ID audio upload response has no url")
        return str(audio_url)

    def create_talk(
        self,
        *,
        audio_url: str,
        expression_events: list[dict[str, Any]] | None = None,
        name: str | None = None,
    ) -> AvatarJob:
        script: dict[str, Any] = {"type": "audio", "audio_url": audio_url}
        payload: dict[str, Any] = {
            "source_url": self.source_url,
            "script": script,
            "config": {"result_format": "mp4", "stitch": True},
        }
        if expression_events:
            payload["config"]["driver_expressions"] = {
                "expressions": expression_events,
                "transition_frames": 10,
            }
        if name:
            payload["name"] = name
        response = requests.post(
            f"{self.base_url}/talks",
            headers=self._headers(),
            json=payload,
            timeout=self.timeout,
        )
        if response.status_code >= 400:
            raise AvatarProviderError(f"D-ID talk creation failed ({response.status_code}): {response.text[:800]}")
        data = response.json()
        return AvatarJob(job_id=str(data["id"]), status=str(data.get("status", "created")))

    def wait_for_result(
        self,
        job: AvatarJob,
        output_path: Path,
        *,
        poll_interval: int = 10,
        timeout_seconds: int = 900,
    ) -> Path:
        """Poll D-ID until done, then download the result MP4."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            response = requests.get(
                f"{self.base_url}/talks/{job.job_id}",
                headers=self._headers(),
                timeout=self.timeout,
            )
            if response.status_code >= 400:
                raise AvatarProviderError(f"D-ID talk polling failed ({response.status_code}): {response.text[:800]}")
            data = response.json()
            status = str(data.get("status", ""))
            if status == "done":
                result_url = data.get("result_url")
                if not result_url:
                    raise AvatarProviderError("D-ID talk completed without result_url")
                output_path.parent.mkdir(parents=True, exist_ok=True)
                video = requests.get(result_url, timeout=self.timeout)
                video.raise_for_status()
                output_path.write_bytes(video.content)
                if output_path.stat().st_size == 0:
                    raise AvatarProviderError("D-ID returned an empty video")
                return output_path
            if status in {"error", "rejected"}:
                raise AvatarProviderError(f"D-ID talk ended with status: {status}")
            time.sleep(poll_interval)
        raise AvatarProviderError(f"D-ID talk timed out after {timeout_seconds}s")

    def create_talking_segment(
        self,
        *,
        audio_path: Path,
        output_path: Path,
        expression_events: list[dict[str, Any]] | None = None,
        name: str | None = None,
    ) -> Path:
        audio_url = self.upload_audio(audio_path)
        job = self.create_talk(audio_url=audio_url, expression_events=expression_events, name=name)
        return self.wait_for_result(job, output_path)
