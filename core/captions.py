"""Arabic caption cue generation and ASS subtitle writing."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CaptionCue:
    start: float
    end: float
    text: str


def ass_time(seconds: float) -> str:
    """Format seconds as ASS H:MM:SS.cc."""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    whole = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        whole += 1
        centiseconds = 0
    if whole >= 60:
        minutes += whole // 60
        whole %= 60
    if minutes >= 60:
        hours += minutes // 60
        minutes %= 60
    return f"{hours}:{minutes:02d}:{whole:02d}.{centiseconds:02d}"


def split_caption_units(text: str, max_chars: int = 58) -> list[str]:
    """Split Arabic text at sentence/phrase boundaries for readable cues."""
    text = re.sub(r"\s+", " ", text.strip())
    if not text:
        raise ValueError("caption text cannot be empty")
    sentences = [part.strip() for part in re.split(r"(?<=[.!؟?!…])\s+", text) if part.strip()]
    units: list[str] = []
    for sentence in sentences or [text]:
        words = sentence.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > max_chars:
                units.append(current)
                current = word
            else:
                current = candidate
        if current:
            units.append(current)
    return units


def build_estimated_cues(text: str, duration: float, max_chars: int = 58) -> list[CaptionCue]:
    """Create preview cues proportional to text length when ASR timestamps are unavailable."""
    if duration <= 0:
        raise ValueError("duration must be positive")
    units = split_caption_units(text, max_chars=max_chars)
    total_weight = sum(max(1, len(unit)) for unit in units)
    cues: list[CaptionCue] = []
    cursor = 0.0
    for index, unit in enumerate(units):
        weight = max(1, len(unit))
        span = duration * weight / total_weight
        end = duration if index == len(units) - 1 else cursor + span
        cues.append(CaptionCue(start=cursor, end=end, text=unit))
        cursor = end
    return cues


def write_arabic_ass(cues: list[CaptionCue], output: Path, *, vertical: bool) -> Path:
    """Write readable Arabic ASS subtitles with a safe opaque background box."""
    if not cues:
        raise ValueError("at least one caption cue is required")
    play_res_x, play_res_y = (1080, 1920) if vertical else (1920, 1080)
    margin_v = 280 if vertical else 90
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {play_res_x}
PlayResY: {play_res_y}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Arabic,Noto Sans Arabic,52,&H00FFFFFF,&H00FFFFFF,&H00141414,&H99000000,0,0,0,0,100,100,0,0,3,3,0,2,70,70,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for cue in cues:
        if cue.end <= cue.start:
            raise ValueError("caption end must be greater than start")
        text = cue.text.strip().replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")
        events.append(
            f"Dialogue: 0,{ass_time(cue.start)},{ass_time(cue.end)},Arabic,,0,0,0,,{text}"
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return output
