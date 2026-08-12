"""Daily autonomous content production and YouTube publishing runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.autopilot import build_parser as build_autopilot_parser
from core.autopilot import run as run_autopilot
from core.autopilot import settings_from_args as autopilot_settings_from_args
from core.content_pipeline import (
    PublishableAsset,
    due_assets_for_date,
    load_series_assets,
    load_state,
    mark_uploaded,
    read_json,
    save_state,
)
from core.script_writer import (
    WriterSettings,
    build_series,
    sanitize_story_id,
)
from core.youtube_publisher import YouTubePublisher, settings_from_env

DONE_STATUSES = {"uploaded", "scheduled", "published"}


def load_queue(content_root: Path) -> dict[str, Any]:
    data = read_json(content_root / "story_queue.json")
    stories = data.get("stories")
    if not isinstance(stories, list):
        raise ValueError("story_queue.json must contain a stories array")
    return data


def story_is_complete(content_root: Path, story_id: str) -> bool:
    plan_path = content_root / "production" / story_id / "series_plan.json"
    if not plan_path.exists():
        return False
    assets = load_series_assets(content_root, story_id)
    state = load_state(content_root, story_id)
    return bool(assets) and all(
        state.get("assets", {}).get(asset.asset_id, {}).get("status") in DONE_STATUSES
        for asset in assets
    )


def find_or_create_story_plan(
    content_root: Path,
    *,
    dry_run: bool,
) -> str:
    """Return the first active story, creating its plan once when it is not present."""
    queue = load_queue(content_root)
    for item in queue["stories"]:
        if not isinstance(item, dict):
            continue
        story_id = sanitize_story_id(str(item.get("story_id", "")))
        plan_path = content_root / "production" / story_id / "series_plan.json"
        if plan_path.exists() and not story_is_complete(content_root, story_id):
            return story_id

    for item in queue["stories"]:
        if not isinstance(item, dict) or str(item.get("status", "queued")) not in {"queued", "planning"}:
            continue
        story_id = sanitize_story_id(str(item.get("story_id", "")))
        writer_settings = WriterSettings(
            api_key=os.getenv("SCRIPTWRITER_API_KEY", "").strip(),
            base_url=os.getenv("SCRIPTWRITER_BASE_URL", "https://api.openai.com/v1").strip(),
            model=os.getenv("SCRIPTWRITER_MODEL", "gpt-5").strip(),
            output_root=content_root,
            dry_run=dry_run,
        )
        build_series(
            writer_settings,
            story_id=story_id,
            requested_theme=str(item.get("theme", "")),
            language=str(item.get("language", "auto")),
        )
        return story_id
    raise RuntimeError("story queue has no active or queued story")


def first_pending_long_asset(
    assets: list[PublishableAsset],
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> PublishableAsset:
    """Return the first unuploaded long episode and make it public immediately once."""
    completed = state.get("assets", {})
    candidates = [
        asset for asset in assets
        if asset.content_format == "long"
        and completed.get(asset.asset_id, {}).get("status") not in DONE_STATUSES
    ]
    if not candidates:
        raise RuntimeError("no pending long episode is available for the initial launch")
    first = min(candidates, key=lambda item: (item.part_number, item.scheduled_at))
    launch_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat().replace("+00:00", "Z")
    return replace(first, scheduled_at=launch_at)


def render_asset(asset: PublishableAsset, *, content_root: Path, output_root: Path) -> Path:
    """Render one planned asset through the existing Fish Audio + MoviePy path."""
    args = build_autopilot_parser().parse_args(
        [
            "--script-file",
            str(content_root / asset.script_file),
            "--episode-name",
            asset.asset_id,
            "--title",
            asset.title,
            "--format",
            asset.content_format,
            "--output-dir",
            str(output_root),
            "--review-status",
            "approved",
        ]
    )
    settings = autopilot_settings_from_args(args)
    return asyncio.run(run_autopilot(settings))


def run_daily(
    *,
    content_root: Path,
    output_root: Path,
    target_date: datetime | None = None,
    dry_run: bool = False,
    publish_first_now: bool = False,
) -> list[dict[str, Any]]:
    """Produce and publish the assets due on the Cairo calendar date."""
    story_id = find_or_create_story_plan(content_root, dry_run=dry_run)
    assets = load_series_assets(content_root, story_id)
    state = load_state(content_root, story_id)
    initial_launch = publish_first_now and not state.get("assets")
    due = (
        [first_pending_long_asset(assets, state, now=target_date)]
        if initial_launch
        else due_assets_for_date(assets, state, target_date)
    )
    if not due:
        return []
    if dry_run:
        return [asset.to_dict() for asset in due]

    publisher = YouTubePublisher(settings_from_env())
    results: list[dict[str, Any]] = []
    for asset in due:
        video_path = render_asset(asset, content_root=content_root, output_root=output_root)
        playlist_id = publisher.ensure_playlist(asset.playlist_title, asset.playlist_description) if asset.content_format == "long" else None
        result = publisher.upload_video(asset, video_path, playlist_id)
        state = mark_uploaded(
            state,
            asset,
            video_id=result.video_id,
            playlist_id=result.playlist_id or "",
        )
        save_state(content_root, story_id, state)
        results.append(
            {
                "asset_id": asset.asset_id,
                "format": asset.content_format,
                "video_id": result.video_id,
                "video_url": result.video_url,
                "playlist_id": result.playlist_id,
                "scheduled_at": result.scheduled_at,
            }
        )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the Rowat Alwaqe daily production and publishing job.")
    parser.add_argument("--content-root", type=Path, default=Path(os.getenv("CONTENT_ROOT", "content")))
    parser.add_argument("--output-root", type=Path, default=Path(os.getenv("AUTOPILOT_OUTPUT_DIR", "storage/autopilot")))
    parser.add_argument("--date", help="Optional ISO timestamp for deterministic testing")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--publish-first-now",
        action="store_true",
        help="Publish the first long episode immediately on the initial manual launch.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = datetime.fromisoformat(args.date.replace("Z", "+00:00")) if args.date else None
    try:
        result = run_daily(
            content_root=args.content_root,
            output_root=args.output_root,
            target_date=target,
            dry_run=args.dry_run,
            publish_first_now=args.publish_first_now,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
