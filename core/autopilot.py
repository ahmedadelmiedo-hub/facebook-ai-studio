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
from datetime import datetime, timezone
from pathlib import Path

from core.avatar_animation import build_avatar_provider
from core.captions import CaptionCue, build_estimated_cues, write_arabic_ass
from core.character_consistency import build_scene_manifest, load_character_bible
from core.performance_planner import split_script_into_performance_segments, write_performance_plan
from core.scene_renderer import probe_duration, render_avatar_episode, render_visual_video

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
    tts_max_characters: int
    dry_run: bool
    character_file: Path | None
    scene_prompt: str
    scene_camera: str
    scene_plan_file: Path | None
    captions_file: Path | None
    visual_render: bool
    render_only: bool
    audio_file: Path | None
    avatar_episode: bool
    avatar_provider: str
    avatar_source_url: str | None
    avatar_source_image: Path | None
    avatar_max_characters: int


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
    parser.add_argument(
        "--tts-max-characters",
        type=int,
        default=int(os.getenv("AUTOPILOT_TTS_MAX_CHARACTERS", "2800")),
        help="Maximum script characters per Fish Audio request for long narration",
    )
    parser.add_argument("--keep-audio", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--character-file",
        type=Path,
        default=Path(os.getenv("AUTOPILOT_CHARACTER_FILE")) if os.getenv("AUTOPILOT_CHARACTER_FILE") else None,
        help="Character Bible JSON used to build a provider-neutral visual scene manifest",
    )
    parser.add_argument(
        "--scene-prompt",
        default=os.getenv("AUTOPILOT_SCENE_PROMPT", ""),
        help="Visual scene description to combine with the character identity",
    )
    parser.add_argument(
        "--scene-camera",
        default=os.getenv("AUTOPILOT_SCENE_CAMERA", "medium cinematic shot"),
        help="Camera and composition description for the visual scene",
    )
    parser.add_argument("--scene-plan", type=Path, help="Validated JSON scene plan for visual rendering")
    parser.add_argument("--captions-file", type=Path, help="ASS captions file to burn into the rendered video")
    parser.add_argument("--visual-render", action="store_true", help="Render scene images instead of the color fallback")
    parser.add_argument("--render-only", action="store_true", help="Render from an existing audio file without calling Fish Audio")
    parser.add_argument("--audio-file", type=Path, help="Existing audio file used with --render-only")
    parser.add_argument("--avatar-episode", action="store_true", help="Generate a full episode from provider-backed talking-avatar segments")
    parser.add_argument("--avatar-provider", default=os.getenv("AVATAR_PROVIDER", "d_id"), choices=("d_id", "sadtalker"), help="Avatar backend: d_id or sadtalker")
    parser.add_argument("--avatar-source-url", default=os.getenv("D_ID_SOURCE_URL", ""), help="HTTPS image URL used by the D-ID provider")
    parser.add_argument("--avatar-source-image", type=Path, default=Path(os.getenv("AVATAR_SOURCE_IMAGE")) if os.getenv("AVATAR_SOURCE_IMAGE") else None, help="Local Nour portrait used by SadTalker")
    parser.add_argument("--avatar-max-characters", type=int, default=int(os.getenv("AVATAR_MAX_CHARACTERS", "900")), help="Maximum narration characters per Avatar segment")
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
    if not 500 <= args.tts_max_characters <= 10_000:
        raise ValueError("tts max characters must be between 500 and 10000")
    if not args.dry_run and args.review_status != "approved":
        raise ValueError("review status must be approved before generating media")
    episode_name = sanitize_episode_name(args.episode_name)
    character_file = args.character_file
    scene_prompt = args.scene_prompt.strip()
    scene_camera = args.scene_camera.strip()
    if character_file:
        load_character_bible(character_file)
        if not scene_prompt:
            raise ValueError("scene prompt is required when --character-file is provided")
    if not scene_camera:
        raise ValueError("scene camera cannot be empty")
    if args.visual_render and not args.scene_plan:
        raise ValueError("--scene-plan is required with --visual-render")
    if args.render_only and not args.audio_file:
        raise ValueError("--audio-file is required with --render-only")
    if args.render_only and not args.visual_render:
        raise ValueError("--render-only requires --visual-render")
    if not 120 <= args.avatar_max_characters <= 5000:
        raise ValueError("avatar max characters must be between 120 and 5000")
    if args.avatar_episode and not character_file:
        raise ValueError("--avatar-episode requires --character-file")
    avatar_provider = args.avatar_provider.strip().lower().replace("-", "_")
    if args.avatar_episode and avatar_provider == "d_id" and not args.avatar_source_url.strip():
        raise ValueError("D-ID avatar episodes require --avatar-source-url or D_ID_SOURCE_URL")
    if args.avatar_episode and avatar_provider == "sadtalker" and not args.avatar_source_image:
        raise ValueError("SadTalker avatar episodes require --avatar-source-image or AVATAR_SOURCE_IMAGE")
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
        tts_max_characters=args.tts_max_characters,
        dry_run=args.dry_run,
        character_file=character_file,
        scene_prompt=scene_prompt,
        scene_camera=scene_camera,
        scene_plan_file=args.scene_plan,
        captions_file=args.captions_file,
        visual_render=args.visual_render,
        render_only=args.render_only,
        audio_file=args.audio_file,
        avatar_episode=args.avatar_episode,
        avatar_provider=avatar_provider,
        avatar_source_url=args.avatar_source_url.strip() or None,
        avatar_source_image=args.avatar_source_image,
        avatar_max_characters=args.avatar_max_characters,
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
            "chunk_length": 300,
            "max_new_tokens": 4096,
            "condition_on_previous_chunks": True,
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


def split_script_for_tts(script: str, max_characters: int) -> list[str]:
    """Split a long narration at paragraph or sentence boundaries for resilient TTS calls."""
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", script) if paragraph.strip()]
    units: list[str] = []
    for paragraph in paragraphs:
        for sentence in re.split(r"(?<=[.!؟?])\s+", paragraph) or [paragraph]:
            sentence = sentence.strip()
            if not sentence:
                continue
            if len(sentence) <= max_characters:
                units.append(sentence)
                continue
            piece = ""
            for word in sentence.split():
                candidate = f"{piece} {word}".strip()
                if piece and len(candidate) > max_characters:
                    units.append(piece)
                    piece = word
                else:
                    piece = candidate
            if piece:
                units.append(piece)

    chunks: list[str] = []
    current = ""
    for unit in units:
        candidate = f"{current}\n\n{unit}".strip()
        if current and len(candidate) > max_characters:
            chunks.append(current)
            current = unit
        else:
            current = candidate
    if current:
        chunks.append(current)
    if not chunks:
        raise ValueError("script text cannot be split into TTS chunks")
    return chunks


def concatenate_mp3_chunks(chunk_paths: list[Path], audio_path: Path) -> None:
    """Join MP3 frames returned by Fish Audio in their original order."""
    with audio_path.open("wb") as destination:
        for chunk_path in chunk_paths:
            destination.write(chunk_path.read_bytes())
    if audio_path.stat().st_size == 0:
        raise RuntimeError("Fish Audio returned empty audio chunks")


async def synthesize_audio(settings: Settings, audio_path: Path) -> None:
    """Generate each narration segment with retries, then assemble one MP3 for rendering."""
    chunks = split_script_for_tts(settings.script, settings.tts_max_characters)
    chunk_dir = audio_path.parent / f".{audio_path.stem}_chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    chunk_paths: list[Path] = []
    try:
        for index, chunk_text in enumerate(chunks, start=1):
            chunk_path = chunk_dir / f"{index:04d}.mp3"
            chunk_settings = Settings(
                script=chunk_text,
                voice=settings.voice,
                model=settings.model,
                output_dir=settings.output_dir,
                episode_name=settings.episode_name,
                title=settings.title,
                profile=settings.profile,
                review_status=settings.review_status,
                background=settings.background,
                fps=settings.fps,
                keep_audio=settings.keep_audio,
                retries=settings.retries,
                tts_max_characters=settings.tts_max_characters,
                dry_run=settings.dry_run,
                character_file=settings.character_file,
                scene_prompt=settings.scene_prompt,
                scene_camera=settings.scene_camera,
                scene_plan_file=settings.scene_plan_file,
                captions_file=settings.captions_file,
                visual_render=settings.visual_render,
                render_only=settings.render_only,
                audio_file=settings.audio_file,
                avatar_episode=settings.avatar_episode,
                avatar_provider=settings.avatar_provider,
                avatar_source_url=settings.avatar_source_url,
                avatar_source_image=settings.avatar_source_image,
                avatar_max_characters=settings.avatar_max_characters,
            )
            for attempt in range(1, settings.retries + 1):
                try:
                    await asyncio.to_thread(fish_audio_request, chunk_settings, chunk_path)
                    break
                except RuntimeError:
                    chunk_path.unlink(missing_ok=True)
                    if attempt == settings.retries:
                        raise
                    delay = attempt * 2
                    LOGGER.warning(
                        "Fish Audio segment %s/%s attempt %s/%s failed; retrying in %ss",
                        index,
                        len(chunks),
                        attempt,
                        settings.retries,
                        delay,
                    )
                    await asyncio.sleep(delay)
            chunk_paths.append(chunk_path)
        concatenate_mp3_chunks(chunk_paths, audio_path)
        LOGGER.info("Audio assembled from %s Fish Audio segment(s)", len(chunk_paths))
    finally:
        for chunk_path in chunk_paths:
            chunk_path.unlink(missing_ok=True)
        chunk_dir.rmdir() if chunk_dir.exists() and not any(chunk_dir.iterdir()) else None


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


def write_visual_scene_manifest(settings: Settings, video_path: Path) -> Path | None:
    """Build visual metadata from character.json without invoking an image provider."""
    if not settings.character_file:
        return None
    character = load_character_bible(settings.character_file)
    manifest = build_scene_manifest(
        character,
        settings.scene_prompt,
        settings.scene_camera,
        seed=None,
        width=settings.profile.canvas[0],
        height=settings.profile.canvas[1],
    )
    manifest_path = video_path.with_suffix(".scene.json")
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def _avatar_segment_settings(settings: Settings, text: str) -> Settings:
    return Settings(
        script=text,
        voice=settings.voice,
        model=settings.model,
        output_dir=settings.output_dir,
        episode_name=settings.episode_name,
        title=settings.title,
        profile=settings.profile,
        review_status=settings.review_status,
        background=settings.background,
        fps=settings.fps,
        keep_audio=True,
        retries=settings.retries,
        tts_max_characters=settings.tts_max_characters,
        dry_run=False,
        character_file=settings.character_file,
        scene_prompt=settings.scene_prompt,
        scene_camera=settings.scene_camera,
        scene_plan_file=None,
        captions_file=None,
        visual_render=False,
        render_only=False,
        audio_file=None,
        avatar_episode=False,
        avatar_provider=settings.avatar_provider,
        avatar_source_url=settings.avatar_source_url,
        avatar_source_image=settings.avatar_source_image,
        avatar_max_characters=settings.avatar_max_characters,
    )


async def run_avatar_episode(settings: Settings, video_path: Path) -> Path:
    """Create per-sentence audio/avatar segments, then compose a captioned episode."""
    segments = split_script_into_performance_segments(settings.script, settings.avatar_max_characters)
    avatar_dir = settings.output_dir / f".{settings.episode_name}_avatar"
    avatar_dir.mkdir(parents=True, exist_ok=True)
    write_performance_plan(
        segments,
        avatar_dir / "performance_plan.json",
        episode_id=settings.episode_name,
        character_id="podcast_host_nour_v1",
    )
    provider = build_avatar_provider(
        settings.avatar_provider,
        source_url=settings.avatar_source_url,
        source_image=settings.avatar_source_image,
    )
    segment_videos: list[Path] = []
    captions: list[CaptionCue] = []
    performance_records: list[dict[str, object]] = []
    offset = 0.0
    expression_by_emotion = {
        "serious": "serious",
        "quiet_suspense": "serious",
        "discovery": "surprise",
    }
    for segment in segments:
        audio_path = avatar_dir / f"{segment.segment_id}.mp3"
        video_segment = avatar_dir / f"{segment.segment_id}.mp4"
        await synthesize_audio(_avatar_segment_settings(settings, segment.text), audio_path)
        if not video_segment.is_file():
            await asyncio.to_thread(
                provider.create_talking_segment,
                audio_path=audio_path,
                output_path=video_segment,
                expression_events=[
                    {
                        "start_frame": 0,
                        "expression": expression_by_emotion.get(segment.emotion, "neutral"),
                        "intensity": 0.6,
                    }
                ],
                name=f"{settings.episode_name}-{segment.segment_id}",
            )
        duration = probe_duration(audio_path)
        for cue in build_estimated_cues(segment.text, duration):
            captions.append(CaptionCue(start=cue.start + offset, end=cue.end + offset, text=cue.text))
        performance_records.append(
            {
                **segment.to_dict(),
                "audio": str(audio_path),
                "video": str(video_segment),
                "duration": duration,
                "start": offset,
                "end": offset + duration,
            }
        )
        offset += duration
        segment_videos.append(video_segment)
    (avatar_dir / "performance_runtime.json").write_text(
        json.dumps({"segments": performance_records, "duration": offset}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    captions_path = video_path.with_suffix(".ass")
    write_arabic_ass(captions, captions_path, vertical=settings.profile.name == "short")
    render_avatar_episode(
        segment_paths=segment_videos,
        captions_path=captions_path,
        output_path=video_path,
        fonts_dir=Path("/usr/share/fonts/truetype/noto"),
    )
    if not settings.keep_audio:
        for segment in segments:
            (avatar_dir / f"{segment.segment_id}.mp3").unlink(missing_ok=True)
    return video_path


def write_production_record(settings: Settings, video_path: Path) -> Path:
    """Save non-secret metadata so a generated artifact remains reviewable."""
    record_path = video_path.with_suffix(".json")
    record = {
        "episode_name": settings.episode_name,
        "character_file": str(settings.character_file) if settings.character_file else None,
        "scene_prompt": settings.scene_prompt or None,
        "scene_camera": settings.scene_camera if settings.character_file else None,
        "title": settings.title,
        "render_profile": asdict(settings.profile),
        "review_status": settings.review_status,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "video_path": str(video_path),
        "script_characters": len(settings.script),
        "voice_provider": "fish_audio",
        "avatar_provider": settings.avatar_provider if settings.avatar_episode else None,
        "avatar_episode": settings.avatar_episode,
        "model": settings.model,
    }
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record_path


async def run(settings: Settings) -> Path:
    audio_path, video_path = build_output_paths(settings.output_dir, settings.episode_name)
    LOGGER.info("%s [%s] -> %s", settings.episode_name, settings.profile.name, video_path)
    if settings.dry_run:
        if settings.avatar_episode:
            planned = split_script_into_performance_segments(settings.script, settings.avatar_max_characters)
            LOGGER.info("Avatar dry run: %s segment(s) planned for provider %s; no external request sent", len(planned), settings.avatar_provider)
        else:
            LOGGER.info("Dry run complete; no audio or video generated")
        return video_path
    if settings.avatar_episode:
        if settings.render_only:
            raise ValueError("--avatar-episode cannot be combined with --render-only")
        result = await run_avatar_episode(settings, video_path)
        record_path = write_production_record(settings, result)
        LOGGER.info("Avatar episode generated: %s", result)
        LOGGER.info("Production record: %s", record_path)
        return result
    if settings.render_only:
        audio_path = settings.audio_file.resolve()
        if not audio_path.is_file():
            raise FileNotFoundError(f"audio file not found: {audio_path}")
        LOGGER.info("Using existing audio: %s", audio_path)
    else:
        await synthesize_audio(settings, audio_path)
        LOGGER.info("Audio generated: %s", audio_path)
    manifest_path = write_visual_scene_manifest(settings, video_path)
    if manifest_path:
        LOGGER.info("Visual scene manifest generated: %s", manifest_path)
    if settings.visual_render:
        captions_path = settings.captions_file
        if captions_path is None:
            captions_path = video_path.with_suffix(".ass")
            duration = __import__("core.scene_renderer", fromlist=["probe_duration"]).probe_duration(audio_path)
            cues = build_estimated_cues(settings.script, duration)
            write_arabic_ass(cues, captions_path, vertical=settings.profile.name == "short")
        render_visual_video(
            scene_plan=settings.scene_plan_file,
            audio_path=audio_path,
            captions_path=captions_path,
            output_path=video_path,
            profile=settings.profile.name,
            fps=settings.fps,
            fonts_dir=Path("/usr/share/fonts/truetype/noto"),
        )
    else:
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
