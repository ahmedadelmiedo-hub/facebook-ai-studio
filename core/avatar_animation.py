from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import requests


class AvatarProviderError(RuntimeError):
    """Raised when a talking-avatar provider request fails."""


@dataclass(frozen=True)
class AvatarJob:
    job_id: str
    status: str
    result_url: str | None = None


class AvatarProvider(Protocol):
    """Provider-neutral interface used by the autopilot segment renderer."""

    def create_talking_segment(
        self,
        *,
        audio_path: Path,
        output_path: Path,
        expression_events: list[dict[str, Any]] | None = None,
        name: str | None = None,
    ) -> Path:
        ...


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


class SadTalkerProvider:
    """Local SadTalker CLI adapter for image-plus-audio talking-head generation."""

    def __init__(
        self,
        source_image: Path | str | None = None,
        *,
        repository_root: Path | str | None = None,
        python_executable: Path | str | None = None,
        enhancer: str | None = None,
        still: bool | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        image_value = source_image or os.getenv("AVATAR_SOURCE_IMAGE", "")
        self.source_image = Path(str(image_value)).expanduser() if str(image_value).strip() else None
        if self.source_image is None or not self.source_image.is_file():
            raise AvatarProviderError("AVATAR_SOURCE_IMAGE must point to an existing local image")

        root_value = repository_root or os.getenv("SADTALKER_ROOT", "")
        self.repository_root = Path(str(root_value)).expanduser() if str(root_value).strip() else None
        if self.repository_root is None:
            raise AvatarProviderError("SADTALKER_ROOT must point to the local SadTalker repository")
        self.inference_script = self.repository_root / "inference.py"
        if not self.inference_script.is_file():
            raise AvatarProviderError(f"SadTalker inference.py not found: {self.inference_script}")

        executable = python_executable or os.getenv("SADTALKER_PYTHON", sys.executable)
        self.python_executable = str(Path(str(executable)).expanduser())
        if not Path(self.python_executable).is_file() and shutil.which(self.python_executable) is None:
            raise AvatarProviderError(f"SadTalker Python executable not found: {self.python_executable}")

        configured_enhancer = enhancer if enhancer is not None else os.getenv("SADTALKER_ENHANCER", "")
        self.enhancer = configured_enhancer.strip()
        if still is None:
            self.still = os.getenv("SADTALKER_STILL", "0").strip().lower() in {"1", "true", "yes", "on"}
        else:
            self.still = still
        self.cpu = os.getenv("SADTALKER_CPU", "0").strip().lower() in {"1", "true", "yes", "on"}
        self.timeout_seconds = timeout_seconds

    def _command(self, audio_path: Path, result_dir: Path) -> list[str]:
        command = [
            self.python_executable,
            str(self.inference_script),
            "--driven_audio",
            str(audio_path.resolve()),
            "--source_image",
            str(self.source_image.resolve()),
            "--result_dir",
            str(result_dir.resolve()),
        ]
        if self.enhancer:
            command.extend(["--enhancer", self.enhancer])
        if self.still:
            command.append("--still")
        if self.cpu:
            command.append("--cpu")
        return command

    def create_talking_segment(
        self,
        *,
        audio_path: Path,
        output_path: Path,
        expression_events: list[dict[str, Any]] | None = None,
        name: str | None = None,
    ) -> Path:
        del expression_events
        if not audio_path.is_file():
            raise FileNotFoundError(f"avatar audio not found: {audio_path}")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result_dir = output_path.parent / f".{output_path.stem}_sadtalker"
        if result_dir.exists():
            shutil.rmtree(result_dir)
        result_dir.mkdir(parents=True, exist_ok=True)
        if name:
            (result_dir / "segment_name.txt").write_text(name, encoding="utf-8")

        try:
            completed = subprocess.run(
                self._command(audio_path, result_dir),
                cwd=self.repository_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise AvatarProviderError(f"SadTalker timed out after {self.timeout_seconds}s") from exc
        except OSError as exc:
            raise AvatarProviderError(f"SadTalker process could not start: {exc}") from exc

        if completed.returncode != 0:
            details = "\n".join(part for part in (completed.stderr, completed.stdout) if part).strip()
            diagnostic = details[-12000:] if details else "unknown SadTalker error"
            print("SadTalker process diagnostic:\n" + diagnostic, flush=True)
            raise AvatarProviderError(f"SadTalker failed ({completed.returncode}): {diagnostic}")

        candidates = sorted(result_dir.rglob("*.mp4"), key=lambda item: item.stat().st_mtime, reverse=True)
        if not candidates:
            raise AvatarProviderError(f"SadTalker completed without an MP4 in {result_dir}")
        shutil.copyfile(candidates[0], output_path)
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise AvatarProviderError("SadTalker returned an empty video")
        return output_path


def build_avatar_provider(
    provider: str | None = None,
    *,
    source_url: str | None = None,
    source_image: Path | str | None = None,
) -> AvatarProvider:
    """Build the configured provider without exposing provider secrets."""
    selected = (provider or os.getenv("AVATAR_PROVIDER", "d_id")).strip().lower().replace("-", "_")
    if selected in {"d_id", "did"}:
        return DIDAvatarProvider(source_url=source_url)
    if selected in {"sadtalker", "sad_talker"}:
        return SadTalkerProvider(source_image=source_image)
    raise AvatarProviderError(f"unsupported AVATAR_PROVIDER: {selected}")
