"""Fish Audio REST TTS adapter for the Hikayatuna Kids renderer.

Uses the free evaluation model by default. API credentials are read only from
environment variables and are never written to generated artifacts.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://api.fish.audio/v1/tts"
DEFAULT_VOICE_MODEL_ID = "rPNcQ53R703tTmtue1AT"
DEFAULT_TTS_MODEL = "s2.1-pro-free"


class FishAudioError(RuntimeError):
    """Raised when Fish Audio cannot return a valid narration file."""


def generate_speech(text: str, output_path: Path) -> Path:
    api_key = os.environ.get("FISH_API_KEY", "").strip()
    if not api_key:
        raise FishAudioError(
            "FISH_API_KEY is missing. Add it as a GitHub Actions repository secret."
        )
    reference_id = (
        os.environ.get("FISH_VOICE_MODEL_ID", "").strip()
        or DEFAULT_VOICE_MODEL_ID
    )
    model = os.environ.get("FISH_TTS_MODEL", DEFAULT_TTS_MODEL).strip()
    if not text.strip():
        raise ValueError("Narration text cannot be empty.")

    payload = {
        "text": text.strip(),
        "reference_id": reference_id,
        "format": "mp3",
        "mp3_bitrate": 192,
        "latency": "normal",
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "model": model,
        },
        method="POST",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        if exc.code == 402:
            hint = "Fish Audio reported no available credit for this model; confirm s2.1-pro-free is enabled."
        elif exc.code == 401:
            hint = "Fish Audio rejected FISH_API_KEY; check the GitHub Actions secret."
        elif exc.code == 404:
            hint = "Fish Audio could not find the configured voice model ID."
        else:
            hint = f"Fish Audio returned HTTP {exc.code}."
        raise FishAudioError(f"{hint} Details: {detail}") from exc
    except Exception as exc:
        raise FishAudioError(
            f"Fish Audio request failed: {type(exc).__name__}: {exc}"
        ) from exc

    if len(audio) < 1024 or not (
        audio.startswith(b"ID3") or audio[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2")
    ):
        raise FishAudioError("Fish Audio returned an empty or invalid MP3 response.")
    output_path.write_bytes(audio)
    return output_path
