"""Generate reviewed Arabic audio-story artifacts with Fish Audio TTS."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

LOGGER = logging.getLogger("facebook_ai_studio.autopilot")
DEFAULT_SCRIPT = """ياسر: جالي تليفون الساعة 2 وربع.. جثة في شقة مهجورة في طنطا.
أمينة: الجثة بقالها 6 ساعات. شايف الرقم اللي على الحيطة؟ 71 مكتوب بدم.
ياسر: نفس الرقم اللي كان في الملف اللي اتقفل من 5 سنين.
الباب خبط.. ظرف على الأرض جواه صورة لنفس الشقة قبل الجريمة بساعة."""
DEFAULT_OUTPUT_DIR = Path("storage/autopilot")
DEFAULT_MODEL = "s2.1-pro-free"
FISH_TTS_URL = "https://api.fish.audio/v1/tts"


@dataclass(frozen=True)
class RenderProfile:
    name: str
    canvas: tuple[int, int]
    intended_use: str


RENDER_PROFILES = {
    "short": RenderProfile("short", (1080, 1920), "YouTube Shorts discovery clip"),
    "long": RenderProfile("long", (1920, 1080), "YouTube long-form episode"),
}


@dataclass(frozen=True)
class Settings:
    script: str
    voice: str
    model: str
    output_dir: Path
    episode_name: str
    title: str
    profile: RenderProfile
    review_status: str
    background: tuple[int, int, int]
    fps: int
    keep_audio: bool
    retries: int
    dry_run: bool


def parse_color(value: str) -> tuple[int, int, int]:
    """Parse #RRGGBB or R,G,B into an RGB tuple."""
    value = value.strip()
    if value.startswith("#"):
        hex_value = value[1:]
        if len(hex_value) != 6:
            raise ValueError("background must use #RRGGBB or R,G,B")
        try:
            return tuple(int(hex_value[index : index + 2], 16) for index in (0, 2, 4))
        except ValueError as exc:
            raise ValueError("background contains invalid hexadecimal values") from exc
    try:
        color = tuple(int(part.strip()) for part in value.split(","))
    except ValueError as exc:
        raise ValueError("background must use #RRGGBB or R,G,B") from exc
    if len(color) != 3 or any(channel < 0 or channel > 255 for channel in color):
        raise ValueError("RGB channels must be between 0 and 255")
    return color


def parse_profile(value: str) -> RenderProfile:
    """Return one of the safe, explicit render profiles."""
    try:
        return RENDER_PROFILES[value.strip().lower()]
    except KeyError as exc:
        choices = ", ".join(RENDER_PROFILES)
        raise ValueError(f"format must be one of: {choices}") from exc


def sanitize_episode_name(value: str) -> str:
    """Return a safe output-file stem."""
    result = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip()).strip("._-")
    if not result:
        raise ValueError("episode name cannot be empty")
    return result[:80]


def load_script(script_file: Path | None) -> str:
    """Load a UTF-8 script file, environment value, or the default script."""
    if script_file:
        if not script_file.is_file():
            raise FileNotFoundError(f"script file not found: {script_file}")
        script = script_file.read_text(encoding="utf-8")
    else:
        script = os.getenv("AUTOPILOT_SCRIPT", DEFAULT_SCRIPT)
    script = script.strip()
    if not script:
        raise ValueError("script text cannot be empty")
    return script


def build_output_paths(output_dir: Path, episode_name: str) -> tuple[Path, Path]:
    """Create deterministic media paths without committing generated media."""
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = sanitize_episode_name(episode_name)
    return output_dir / f"{stem}.mp3", output_dir / f"{stem}.mp4"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a reviewed Arabic story video with Fish Audio.")
    parser.add_argument("--script-file", type=Path, help="Approved UTF-8 script file")
    parser.add_argument("--voice", default=os.getenv("FISH_VOICE_ID", ""), help="Fish Audio voice model ID")
    parser.add_argument("--model", default=os.getenv("FISH_MODEL", DEFAULT_MODEL))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("AUTOPILOT_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))),
    )
    parser.add_argument("--episode-name", default=os.getenv("AUTOPILOT_EPISODE_NAME", "EP01"))
    parser.add_argument("--title", default=os.getenv("AUTOPILOT_TITLE", ""))
    parser.add_argument(
        "--format",
        choices=sorted(RENDER_PROFILES),
        default=os.getenv("AUTOPILOT_FORMAT", "short"),
        help="short for 1080x1920 discovery clips or long for 1920x1080 episodes",
    )
    parser.add_argument(
        "--review-status",
        choices=("draft", "approved"),
        default=os.getenv("AUTOPILOT_REVIEW_STATUS", "draft"),
        help="Only approved scripts may call the speech provider",
    )
    parser.add_argument("--background", default=os.getenv("AUTOPILOT_BACKGROUND", "10,10,10"))
    parser.add_argument("--fps", type=int, default=int(os.getenv("AUTOPILOT_FPS", "24")))
    parser.add_argument(
        "--tts-retries",
        type=int,
        default=int(os.getenv("AUTOPILOT_TTS_RETRIES", "3")),
        help="Fish Audio attempts for transient failures",
    )
    parser.add_argument("--keep-audio", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def settings_from_args(args: argparse.Namespace) -> Settings:
    if not args.voice.strip():
        raise ValueError("Fish Audio voice ID is missing; set FISH_VOICE_ID or pass --voice")
    if not args.model.strip():
        raise ValueError("Fish Audio model cannot be empty")
    if not 1 <= args.fps <= 120:
        raise ValueError("fps must be between 1 and 120")
    if not 1 <= args.tts_retries <= 10:
        raise ValueError("tts retries must be between 1 and 10")
    if not args.dry_run and args.review_status != "approved":
        raise ValueError("review status must be approved before generating media")
    episode_name = sanitize_episode_name(args.episode_name)
    return Settings(
        script=load_script(args.script_file),
        voice=args.voice.strip(),
        model=args.model.strip(),
        output_dir=args.output_dir,
        episode_name=episode_name,
        title=args.title.strip() or episode_name,
        profile=parse_profile(args.format),
        review_status=args.review_status,
        background=parse_color(args.background),
        fps=args.fps,
        keep_audio=args.keep_audio,
        retries=args.tts_retries,
        dry_run=args.dry_run,
    )


def fish_audio_request(settings: Settings, audio_path: Path) -> None:
    """Call Fish Audio's JSON TTS endpoint and write the returned MP3."""
    api_key = os.getenv("FISH_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("FISH_API_KEY is not configured")
    payload = json.dumps(
        {
            "text": settings.script,
            "reference_id": settings.voice,
            "format": "mp3",
            "sample_rate": 44100,
            "mp3_bitrate": 128,
            "normalize": True,
            "latency": "normal",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        FISH_TTS_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "model": settings.model,
            "User-Agent": "facebook-ai-studio/1.1",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            audio_path.write_bytes(response.read())
    except urllib.error.HTTPError as exc:
        details = exc.read(400).decode("utf-8", errors="replace")
        raise RuntimeError(f"Fish Audio returned HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Fish Audio network error: {exc.reason}") from exc
    if not audio_path.exists() or audio_path.stat().st_size == 0:
        raise RuntimeError("Fish Audio returned an empty audio response")


async def synthesize_audio(settings: Settings, audio_path: Path) -> None:
    """Generate audio, retrying transient provider or network failures."""
    for attempt in range(1, settings.retries + 1):
        try:
            await asyncio.to_thread(fish_audio_request, settings, audio_path)
            return
        except RuntimeError:
            audio_path.unlink(missing_ok=True)
            if attempt == settings.retries:
                raise
            delay = attempt * 2
            LOGGER.warning("Fish Audio attempt %s/%s failed; retrying in %ss", attempt, settings.retries, delay)
            await asyncio.sleep(delay)


def render_video(audio_path: Path, video_path: Path, settings: Settings) -> None:
    """Render either a landscape episode or a vertical Short with voice-over."""
    try:
        from moviepy.editor import AudioFileClip, ColorClip
    except ImportError:
        from moviepy import AudioFileClip, ColorClip
    audio = AudioFileClip(str(audio_path))
    video = ColorClip(size=settings.profile.canvas, color=settings.background, duration=audio.duration)
    try:
        video = video.with_audio(audio) if hasattr(video, "with_audio") else video.set_audio(audio)
        video.write_videofile(
            str(video_path),
            fps=settings.fps,
            codec="libx264",
            audio_codec="aac",
            logger=None,
        )
    finally:
        video.close()
        audio.close()


def write_production_record(settings: Settings, video_path: Path) -> Path:
    """Save non-secret metadata so a generated artifact remains reviewable."""
    record_path = video_path.with_suffix(".json")
    record = {
        "episode_name": settings.episode_name,
        "title": settings.title,
        "render_profile": asdict(settings.profile),
        "review_status": settings.review_status,
        "generated_at": datetime.now(UTC).isoformat(),
        "video_path": str(video_path),
        "script_characters": len(settings.script),
        "voice_provider": "fish_audio",
        "model": settings.model,
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record_path


async def run(settings: Settings) -> Path:
    audio_path, video_path = build_output_paths(settings.output_dir, settings.episode_name)
    LOGGER.info("%s [%s] -> %s", settings.episode_name, settings.profile.name, video_path)
    if settings.dry_run:
        LOGGER.info("Dry run complete; no audio or video generated")
        return video_path
    await synthesize_audio(settings, audio_path)
    LOGGER.info("Audio generated: %s", audio_path)
    render_video(audio_path, video_path, settings)
    record_path = write_production_record(settings, video_path)
    LOGGER.info("Video generated: %s", video_path)
    LOGGER.info("Production record: %s", record_path)
    if not settings.keep_audio:
        audio_path.unlink(missing_ok=True)
        LOGGER.info("Temporary audio removed")
    return video_path


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        settings = settings_from_args(build_parser().parse_args(argv))
        asyncio.run(run(settings))
    except (FileNotFoundError, ValueError) as exc:
        LOGGER.error("Configuration error: %s", exc)
        return 2
    except Exception:
        LOGGER.exception("Episode generation failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
