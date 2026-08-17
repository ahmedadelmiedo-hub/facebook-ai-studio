"""Deterministic script-to-performance planning for the Nour avatar."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PerformanceSegment:
    segment_id: str
    text: str
    mode: str = "talking_medium"
    emotion: str = "serious"
    gaze: str = "toward_camera"
    head_motion: str = "subtle_nod"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    return [part.strip() for part in re.split(r"(?<=[.!؟?!…])\s+", normalized) if part.strip()]


def split_script_into_performance_segments(script: str, max_characters: int = 420) -> list[PerformanceSegment]:
    """Split narration at sentence boundaries and assign a stable performance profile."""
    if max_characters < 120:
        raise ValueError("max_characters must be at least 120")
    sentences = _sentences(script)
    if not sentences:
        raise ValueError("script text cannot be empty")
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_characters:
            words = sentence.split()
            piece = ""
            for word in words:
                candidate = f"{piece} {word}".strip()
                if piece and len(candidate) > max_characters:
                    chunks.append(piece)
                    piece = word
                else:
                    piece = candidate
            if piece:
                sentences_to_add = [piece]
            else:
                sentences_to_add = []
        else:
            sentences_to_add = [sentence]
        for unit in sentences_to_add:
            candidate = f"{current} {unit}".strip()
            if current and len(candidate) > max_characters:
                chunks.append(current)
                current = unit
            else:
                current = candidate
    if current:
        chunks.append(current)

    segments: list[PerformanceSegment] = []
    profiles = [
        ("serious", "toward_camera", "subtle_nod"),
        ("quiet_suspense", "toward_left", "small_turn_left"),
        ("discovery", "down_then_camera", "small_lean_forward"),
        ("serious", "toward_camera", "subtle_nod"),
    ]
    for index, chunk in enumerate(chunks, start=1):
        emotion, gaze, head_motion = profiles[(index - 1) % len(profiles)]
        segments.append(
            PerformanceSegment(
                segment_id=f"A{index:03d}",
                text=chunk,
                emotion=emotion,
                gaze=gaze,
                head_motion=head_motion,
            )
        )
    return segments


def write_performance_plan(
    segments: list[PerformanceSegment],
    output: Path,
    *,
    episode_id: str,
    character_id: str,
) -> Path:
    if not segments:
        raise ValueError("performance plan cannot be empty")
    payload = {
        "schema_version": 1,
        "episode_id": episode_id,
        "character_id": character_id,
        "timing_source": "audio_probe_after_tts",
        "segments": [segment.to_dict() for segment in segments],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    import json

    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output
