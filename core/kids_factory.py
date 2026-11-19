"""Safe, review-first production factory for Hikayatuna Kids.

This module prepares deterministic episode manifests and validates policy before any
external media provider is called. It deliberately never publishes publicly by default.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "kids-channel.json"
RULES_PATH = ROOT / "config" / "kids-content-rules.json"
QUEUE_PATH = ROOT / "content" / "kids-story-queue.json"
ARCHIVE_PATH = ROOT / "content" / "kids-production" / "episode-archive.json"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def normalize(value: str) -> str:
    return re.sub(r"\s+", " ", str(value).strip().lower())


def fingerprint(story: dict[str, Any], rules: dict[str, Any]) -> str:
    fields = rules["originality"]["fingerprint_fields"]
    payload = "|".join(normalize(story.get(field, "")) if not isinstance(story.get(field), list) else ",".join(sorted(normalize(x) for x in story[field])) for field in fields)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def safety_issues(story: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    text = normalize(" ".join(str(story.get(key, "")) for key in ("title", "learning_goal", "setting", "conflict")))
    forbidden = rules["safety"]["forbidden_topics"]
    return [f"forbidden topic: {term}" for term in forbidden if normalize(term) in text]


def validate_story(story: dict[str, Any], rules: dict[str, Any]) -> list[str]:
    required = ("episode_id", "title", "content_type", "learning_goal", "setting", "conflict", "character_pair", "duration_minutes")
    issues = [f"missing field: {key}" for key in required if not story.get(key)]
    if story.get("duration_minutes") != 3:
        issues.append("duration_minutes must be exactly 3 for the daily target")
    if not isinstance(story.get("character_pair"), list) or not 1 <= len(story["character_pair"]) <= 3:
        issues.append("character_pair must contain one to three characters")
    issues.extend(safety_issues(story, rules))
    return issues


def load_archive() -> dict[str, Any]:
    if ARCHIVE_PATH.exists():
        return read_json(ARCHIVE_PATH)
    return {"schema_version": 1, "episodes": []}


def choose_episode(queue: dict[str, Any], rules: dict[str, Any], episode_id: str | None = None) -> tuple[dict[str, Any], str]:
    archive = load_archive()
    archived_ids = {item.get("episode_id") for item in archive.get("episodes", [])}
    candidates = [item for item in queue.get("stories", []) if item.get("status") == "queued" and item.get("episode_id") not in archived_ids]
    if episode_id:
        candidates = [item for item in candidates if item.get("episode_id") == episode_id]
    if not candidates:
        raise RuntimeError("no queued, non-archived kids episode is available")
    story = candidates[0]
    issues = validate_story(story, rules)
    if issues:
        raise ValueError("episode policy failed: " + "; ".join(issues))
    fp = fingerprint(story, rules)
    previous = {item.get("fingerprint") for item in archive.get("episodes", [])}
    if fp in previous:
        raise ValueError(f"duplicate content fingerprint detected: {fp}")
    return story, fp


def prepare_episode(episode_id: str | None = None) -> Path:
    config = read_json(CONFIG_PATH)
    rules = read_json(RULES_PATH)
    queue = read_json(QUEUE_PATH)
    story, fp = choose_episode(queue, rules, episode_id)
    out_dir = ROOT / config["production_root"] / story["episode_id"]
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema_version": 1,
        "episode_id": story["episode_id"],
        "title": story["title"],
        "channel": config["channel_name"],
        "audience": f"{rules['audience']['min_age']}-{rules['audience']['max_age']}",
        "language": config["language_mode"],
        "duration_minutes": 3,
        "content_type": story["content_type"],
        "learning_goal": story["learning_goal"],
        "characters": story["character_pair"],
        "fingerprint": fp,
        "status": "prepared_for_review",
        "provider_status": {"text": "not_called", "image": "not_called", "voice": "not_called", "video": "not_called"},
        "quality_gate": {"status": "blocked", "checks": rules["quality_gate"], "human_approval": False},
        "publishing": {"enabled": False, "privacy": "private", "youtube_video_id": None},
        "created_at": datetime.now(UTC).isoformat(),
        "artifacts": {"script": str(out_dir / "script.md"), "storyboard": str(out_dir / "storyboard.json"), "video": str(out_dir / "episode.mp4"), "short": str(out_dir / "short.mp4"), "quality": str(out_dir / "quality-report.json")},
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "script.md").write_text(f"# {story['title']}\n\n[PREPARED ONLY] النص الفعلي يحتاج مزود كتابة معتمد ومراجعة بشرية قبل الإنتاج.\n\nهدف التعلم: {story['learning_goal']}\n", encoding="utf-8")
    (out_dir / "storyboard.json").write_text(json.dumps({"status":"pending_provider","scenes":[]}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return out_dir / "manifest.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare a safe Hikayatuna Kids episode artifact")
    parser.add_argument("--episode-id")
    parser.add_argument("--mode", choices=("prepare", "validate"), default="prepare")
    args = parser.parse_args()
    path = prepare_episode(args.episode_id)
    print(json.dumps({"status": "prepared_for_review", "manifest": str(path.relative_to(ROOT)), "publish_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
