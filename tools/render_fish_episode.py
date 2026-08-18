"""Render a fast Fish Audio episode with burned Arabic ASS captions."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from core.captions import build_estimated_cues, write_arabic_ass
from core.scene_renderer import mux_audio_and_captions, probe_duration


def _run(command: list[str]) -> None:
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode:
        detail = (result.stderr or result.stdout)[-4000:]
        raise RuntimeError(f"FFmpeg failed ({result.returncode}): {detail}")


def render_episode(audio_path: Path, script_path: Path, output_path: Path, fps: int = 24) -> Path:
    if not audio_path.is_file() or audio_path.stat().st_size == 0:
        raise FileNotFoundError(f"audio file not found or empty: {audio_path}")
    if not script_path.is_file():
        raise FileNotFoundError(f"script file not found: {script_path}")
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
    with TemporaryDirectory(prefix="fish-episode-") as temp_dir:
        background_path = Path(temp_dir) / "background.mp4"
        _run(
            [
                "ffmpeg",
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=c=0b0b12:s=1920x1080:r=24",
                "-t",
                f"{duration:.3f}",
                "-an",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-pix_fmt",
                "yuv420p",
                str(background_path),
            ]
        )
        mux_audio_and_captions(
            background_path,
            audio_path,
            captions_path,
            output_path,
            fonts_dir=Path("/usr/share/fonts/truetype/noto"),
        )
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Fish Audio episode renderer returned an empty file")
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render a Fish Audio episode with Arabic captions")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--script", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fps", type=int, default=24)
    args = parser.parse_args(argv)
    render_episode(args.audio, args.script, args.output, fps=args.fps)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
