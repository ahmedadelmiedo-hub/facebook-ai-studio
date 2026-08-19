"""Render a fast Fish Audio episode with the approved Rowat Alwaqe studio frame."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from core.captions import build_estimated_cues, write_arabic_ass
from core.scene_renderer import mux_audio_and_captions, probe_duration


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MASTER_FRAME = REPO_ROOT / "storage" / "references" / "rowat-host-seated-master-v2.png"
DEFAULT_STUDIO_BACKGROUND = REPO_ROOT / "storage" / "references" / "rowat-arabesque-studio-v1.jpg"
DEFAULT_PRESENTER_IMAGE = REPO_ROOT / "storage" / "references" / "rowat-host-cutout-v1.png"


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = (result.stderr or result.stdout)[-4000:]
        raise RuntimeError(f"FFmpeg failed ({result.returncode}): {detail}")


def _require_asset(path: Path, label: str) -> Path:
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(f"{label} not found or empty: {path}")
    return path


def _render_static_frame(frame_path: Path, output_path: Path, duration: float, fps: int) -> None:
    """Turn one approved master frame into a video stream for the episode duration."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(frame_path),
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(output_path),
        ]
    )


def _render_legacy_composite(
    studio_background: Path,
    presenter_image: Path,
    output_path: Path,
    duration: float,
    fps: int,
) -> None:
    """Keep the previous cutout path available for backward-compatible custom runs."""
    _run(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-loop",
            "1",
            "-i",
            str(studio_background),
            "-loop",
            "1",
            "-i",
            str(presenter_image),
            "-filter_complex",
            (
                "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
                "crop=1920:1080,format=rgb24[bg];"
                "[1:v]scale=-1:980:flags=lanczos,format=rgba[presenter];"
                "[bg][presenter]overlay=x='W-w-40':y='H-h-20':format=auto[composed]"
            ),
            "-map",
            "[composed]",
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(fps),
            str(output_path),
        ]
    )


def render_episode(
    audio_path: Path,
    script_path: Path,
    output_path: Path,
    fps: int = 24,
    studio_background: Path | None = None,
    presenter_image: Path | None = None,
    master_frame: Path | None = None,
) -> Path:
    """Render the approved master frame, Arabic captions, and Fish Audio narration."""
    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise FileNotFoundError(f"audio file not found or empty: {audio_path}")
    if not script_path.is_file():
        raise FileNotFoundError(f"script file not found: {script_path}")
    if fps <= 0:
        raise ValueError("fps must be positive")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration = probe_duration(audio_path)
    captions_path = output_path.with_suffix(".ass")
    script = script_path.read_text(encoding="utf-8").strip()
    if not script:
        raise ValueError("script cannot be empty")
    write_arabic_ass(
        build_estimated_cues(script, duration),
        captions_path,
        vertical=False,
    )

    selected_master = master_frame or DEFAULT_MASTER_FRAME
    selected_background = studio_background or DEFAULT_STUDIO_BACKGROUND
    selected_presenter = presenter_image or DEFAULT_PRESENTER_IMAGE

    with TemporaryDirectory(prefix="fish-episode-") as temp_dir:
        visual_path = Path(temp_dir) / "visual.mp4"
        if selected_master.is_file() and selected_master.stat().st_size > 0:
            _render_static_frame(selected_master, visual_path, duration, fps)
        else:
            _require_asset(selected_background, "studio background")
            _require_asset(selected_presenter, "presenter image")
            _render_legacy_composite(
                selected_background,
                selected_presenter,
                visual_path,
                duration,
                fps,
            )
        mux_audio_and_captions(
            visual_path,
            audio_path,
            captions_path,
            output_path,
            fonts_dir=Path("/usr/share/fonts/truetype/noto"),
        )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Fish Audio episode renderer returned an empty file")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Render a Fish Audio episode with the approved Rowat Alwaqe studio frame"
    )
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--master-frame", type=Path, default=None)
    parser.add_argument("--studio-background", type=Path, default=None)
    parser.add_argument("--presenter-image", type=Path, default=None)
    args = parser.parse_args(argv)
    render_episode(
        args.audio,
        args.script,
        args.output,
        fps=args.fps,
        master_frame=args.master_frame,
        studio_background=args.studio_background,
        presenter_image=args.presenter_image,
    )
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
