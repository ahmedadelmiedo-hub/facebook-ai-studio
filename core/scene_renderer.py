"""FFmpeg-based scene renderer for image motion, captions, and narration audio."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any


class RenderError(RuntimeError):
    """Raised when a visual render cannot be completed or validated."""


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = (result.stderr or result.stdout)[-4000:]
        raise RenderError(f"FFmpeg command failed ({result.returncode}): {detail}")


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode or not result.stdout.strip():
        raise RenderError(f"could not read media duration: {path}")
    return float(result.stdout.strip())


def has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=index", "-of", "csv=p=0", str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def load_scene_plan(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"scene plan not found: {path}")
    plan = json.loads(path.read_text(encoding="utf-8"))
    scenes = plan.get("scenes")
    if not isinstance(scenes, list) or not scenes:
        raise ValueError("scene plan must contain a non-empty scenes array")
    return plan


def validate_scene_plan(plan: dict[str, Any], audio_duration: float, tolerance: float = 1.0) -> None:
    scenes = plan["scenes"]
    previous_end = 0.0
    for index, scene in enumerate(scenes):
        start = float(scene["start"])
        end = float(scene["end"])
        image = Path(scene["image"])
        if index == 0 and abs(start) > 0.01:
            raise ValueError("first scene must start at zero")
        if start < previous_end - 0.01 or end <= start:
            raise ValueError("scene timings overlap or are invalid")
        if not image.is_file() or image.stat().st_size < 10_000:
            raise ValueError(f"scene image is missing or too small: {image}")
        previous_end = end
    if abs(previous_end - audio_duration) > tolerance:
        raise ValueError(
            f"scene plan duration {previous_end:.2f}s does not match audio {audio_duration:.2f}s"
        )


def _motion_filter(scene: dict[str, Any], width: int, height: int, fps: int) -> str:
    duration = float(scene["end"]) - float(scene["start"])
    frames = max(1, round(duration * fps))
    motion_type = scene.get("motion", {}).get("type", "slow_zoom")
    if motion_type in {"pan_left", "pan_right"}:
        x_expr = (
            f"(iw-ow)*0.65*(1-on/{frames})"
            if motion_type == "pan_left"
            else f"(iw-ow)*0.35+(iw-ow)*0.65*on/{frames}"
        )
        # Use a large normalized canvas, then pan inside it frame by frame.
        return (
            f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase," 
            f"crop={width*2}:{height*2},zoompan=z=1.0:x='{x_expr}':y='(ih-oh)/2':d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
        )
    zoom_expr = "min(zoom+0.0008,1.05)" if motion_type != "push_in" else "min(zoom+0.0012,1.08)"
    return (
        f"scale={width*2}:{height*2}:force_original_aspect_ratio=increase," 
        f"crop={width*2}:{height*2},zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps={fps},format=yuv420p"
    )


def _render_scene(image: Path, scene: dict[str, Any], output: Path, width: int, height: int, fps: int) -> None:
    duration = float(scene["end"]) - float(scene["start"])
    vf = _motion_filter(scene, width, height, fps)
    command = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-i", str(image), "-t", f"{duration:.3f}",
        "-vf", vf,
        "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
        str(output),
    ]
    _run(command)


def _concat_segments(segments: list[Path], output: Path) -> None:
    concat_file = output.with_suffix(".concat.txt")
    lines = [f"file '{segment.resolve().as_posix()}'" for segment in segments]
    concat_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    try:
        _run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-c", "copy", str(output),
        ])
    finally:
        concat_file.unlink(missing_ok=True)


def prepend_video_intro(
    video_path: Path,
    intro_path: Path,
    output_path: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    fps: int = 24,
) -> None:
    """Prepend a vertical intro, preserving its audio when present."""
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise FileNotFoundError(f"main video not found or empty: {video_path}")
    if not intro_path.is_file() or intro_path.stat().st_size == 0:
        raise FileNotFoundError(f"intro not found or empty: {intro_path}")
    if width <= 0 or height <= 0 or fps <= 0:
        raise ValueError("intro composition dimensions and fps must be positive")

    intro_duration = probe_duration(intro_path)
    if intro_duration <= 0:
        raise RenderError(f"intro has no usable duration: {intro_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    same_path = video_path.resolve() == output_path.resolve()
    with TemporaryDirectory(prefix="shorts-intro-") as temp_dir:
        temp_output = Path(temp_dir) / "with-intro.mp4"
        final_target = temp_output if same_path else output_path
        intro_has_audio = has_audio_stream(intro_path)
        intro_audio_label = "[0:a]" if intro_has_audio else "[2:a]"
        filter_graph = (
            f"[0:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p[intro_v];"
            f"{intro_audio_label}atrim=duration={intro_duration:.3f},asetpts=PTS-STARTPTS[intro_a];"
            f"[1:v]fps={fps},scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,setsar=1,format=yuv420p[main_v];"
            "[1:a]aresample=async=1:first_pts=0[main_a];"
            "[intro_v][intro_a][main_v][main_a]concat=n=2:v=1:a=1[out_v][out_a]"
        )
        command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(intro_path), "-i", str(video_path),
        ]
        if not intro_has_audio:
            command.extend([
                "-f", "lavfi", "-t", f"{intro_duration:.3f}", "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
            ])
        command.extend([
            "-filter_complex", filter_graph,
            "-map", "[out_v]", "-map", "[out_a]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", str(final_target),
        ])
        _run(command)
        if same_path:
            temp_output.replace(output_path)


def mux_audio_and_captions(
    video_path: Path,
    audio_path: Path,
    captions_path: Path | None,
    output_path: Path,
    *,
    fonts_dir: Path | None = None,
) -> None:
    """Mux narration and burn ASS captions into the visual video."""
    subtitle_filter = None
    if captions_path:
        subtitle_filter = f"subtitles=filename='{captions_path.as_posix()}'"
        if fonts_dir:
            subtitle_filter += f":fontsdir='{fonts_dir.as_posix()}'"
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(video_path), "-i", str(audio_path)]
    if subtitle_filter:
        command.extend(["-vf", subtitle_filter])
    command.extend([
        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast",
        "-crf", "22", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k",
        "-shortest", str(output_path),
    ])
    _run(command)


def render_avatar_episode(
    *,
    segment_paths: list[Path],
    captions_path: Path | None,
    output_path: Path,
    fonts_dir: Path | None = None,
) -> Path:
    """Concatenate D-ID avatar segments and burn one caption track over them."""
    if not segment_paths:
        raise RenderError("avatar episode has no segments")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="avatar-episode-") as temp_dir:
        temp_root = Path(temp_dir)
        joined = temp_root / "joined.mp4"
        _concat_segments(segment_paths, joined)
        if captions_path is None:
            output_path.write_bytes(joined.read_bytes())
        else:
            subtitle_filter = f"subtitles=filename='{captions_path.as_posix()}'"
            if fonts_dir:
                subtitle_filter += f":fontsdir='{fonts_dir.as_posix()}'"
            _run([
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-i", str(joined), "-vf", subtitle_filter,
                "-map", "0:v:0", "-map", "0:a:0?",
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
                "-pix_fmt", "yuv420p", "-c:a", "copy", str(output_path),
            ])
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RenderError("avatar episode renderer returned an empty file")
    return output_path


def render_visual_video(
    *,
    scene_plan: Path,
    audio_path: Path,
    captions_path: Path | None,
    output_path: Path,
    profile: str,
    fps: int = 24,
    fonts_dir: Path | None = None,
) -> Path:
    """Render scenes, burn captions, mux narration, and validate duration."""
    plan = load_scene_plan(scene_plan)
    audio_duration = probe_duration(audio_path)
    validate_scene_plan(plan, audio_duration)
    width, height = (1080, 1920) if profile == "short" else (1920, 1080)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="scene-render-") as temp_dir:
        temp_root = Path(temp_dir)
        segments: list[Path] = []
        for index, scene in enumerate(plan["scenes"], start=1):
            segment = temp_root / f"scene-{index:04d}.mp4"
            _render_scene(Path(scene["image"]), scene, segment, width, height, fps)
            segments.append(segment)
        visual_path = temp_root / "visual.mp4"
        _concat_segments(segments, visual_path)
        mux_audio_and_captions(visual_path, audio_path, captions_path, output_path, fonts_dir=fonts_dir)
    rendered_duration = probe_duration(output_path)
    if abs(rendered_duration - audio_duration) > 1.0:
        raise RenderError(
            f"rendered video duration {rendered_duration:.2f}s does not match audio {audio_duration:.2f}s"
        )
    return output_path
