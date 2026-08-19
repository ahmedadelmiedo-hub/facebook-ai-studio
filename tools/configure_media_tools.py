from __future__ import annotations

import os
import shutil
from pathlib import Path

import static_ffmpeg


static_ffmpeg.add_paths()
ffmpeg = shutil.which("ffmpeg")
ffprobe = shutil.which("ffprobe")
if not ffmpeg or not ffprobe:
    raise SystemExit("static-ffmpeg did not provide both ffmpeg and ffprobe")

bin_dir = str(Path(ffmpeg).resolve().parent)
with Path(os.environ["GITHUB_PATH"]).open("a", encoding="utf-8") as handle:
    handle.write(bin_dir + "\n")

print(f"Configured media tools from {bin_dir}")
print(f"ffmpeg={ffmpeg}")
print(f"ffprobe={ffprobe}")
