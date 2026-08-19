"""Daily autonomous content production and YouTube publishing runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import subprocess
import sys
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


def story_was_built_in_dry_run(content_root: Path, story_id: str) -> bool:
    """Return whether a prior dry-run left placeholder scripts that must not be rendered."""
    record_path = content_root / "production" / story_id / "build_record.json"
    if not record_path.exists():
        return False
    return read_json(record_path).get("mode") == "dry_run"


def writer_settings_for(content_root: Path, *, dry_run: bool) -> WriterSettings:
    return WriterSettings(
        api_key=os.getenv("SCRIPTWRITER_API_KEY", "").strip(),
        base_url=os.getenv("SCRIPTWRITER_BASE_URL", "https://api.openai.com/v1").strip(),
        model=os.getenv("SCRIPTWRITER_MODEL", "gpt-5").strip(),
        output_root=content_root,
        dry_run=dry_run,
    )


def find_or_create_story_plan(
    content_root: Path,
    *,
    dry_run: bool,
    start_after: datetime | None = None,
) -> str:
    """Return the first active story, creating its plan once when it is not present."""
    queue = load_queue(content_root)
    for item in queue["stories"]:
        if not isinstance(item, dict):
            continue
        story_id = sanitize_story_id(str(item.get("story_id", "")))
        plan_path = content_root / "production" / story_id / "series_plan.json"
        if plan_path.exists() and not story_is_complete(content_root, story_id):
            if not dry_run and story_was_built_in_dry_run(content_root, story_id):
                build_series(
                    writer_settings_for(content_root, dry_run=False),
                    story_id=story_id,
                    requested_theme=str(item.get("theme", "")),
                    language=str(item.get("language", "auto")),
                    start_after=start_after,
                )
            return story_id

    for item in queue["stories"]:
        if not isinstance(item, dict) or str(item.get("status", "queued")) not in {"queued", "planning"}:
            continue
        story_id = sanitize_story_id(str(item.get("story_id", "")))
        plan_path = content_root / "production" / story_id / "series_plan.json"
        if plan_path.exists() and story_is_complete(content_root, story_id):
            continue
        build_series(
            writer_settings_for(content_root, dry_run=dry_run),
            story_id=story_id,
            requested_theme=str(item.get("theme", "")),
            language=str(item.get("language", "auto")),
            start_after=start_after,
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


def first_pending_short_asset(
    assets: list[PublishableAsset],
    state: dict[str, Any],
) -> PublishableAsset:
    """Return the earliest unuploaded promotional Short without touching long episodes."""
    completed = state.get("assets", {})
    candidates = [
        asset for asset in assets
        if asset.content_format == "short"
        and completed.get(asset.asset_id, {}).get("status") not in DONE_STATUSES
    ]
    if not candidates:
        raise RuntimeError("no pending promotional Short is available")
    return min(candidates, key=lambda item: (item.scheduled_at, item.part_number, item.asset_id))


def next_pending_asset(
    assets: list[PublishableAsset],
    state: dict[str, Any],
    *,
    now: datetime | None = None,
) -> PublishableAsset:
    """Return one next asset and make its immediate-public slot explicit.

    Scheduled runs fire four times per day. Each firing publishes exactly one pending
    asset so long episodes and their three planned Shorts are spread across runs without
    uploading the whole day's queue at once. The story planner still controls the number
    of episodes for each story.
    """
    completed = state.get("assets", {})
    candidates = [
        asset for asset in assets
        if completed.get(asset.asset_id, {}).get("status") not in DONE_STATUSES
    ]
    if not candidates:
        raise RuntimeError("no pending asset is available")
    first = min(
        candidates,
        key=lambda item: (item.scheduled_at, item.part_number, item.asset_id),
    )
    current = (now or datetime.now(UTC)).astimezone(UTC)
    planned = datetime.fromisoformat(first.scheduled_at.replace("Z", "+00:00"))
    # Preserve future YouTube scheduling. Only overdue assets are made immediate,
    # which prevents a Hook from being uploaded after its full episode.
    if planned > current:
        return first
    publish_at = current.isoformat().replace("+00:00", "Z")
    return replace(first, scheduled_at=publish_at)


def ensure_asset_script(asset: PublishableAsset, *, content_root: Path) -> Path:
    """Generate one missing planned script before rendering, without rebuilding published assets."""
    script_path = content_root / asset.script_file
    if script_path.is_file() and script_path.stat().st_size > 0:
        return script_path

    repair_tool = Path(__file__).resolve().parents[1] / "tools" / "repair_missing_scripts.py"
    if not repair_tool.is_file():
        raise FileNotFoundError(f"script repair tool not found: {repair_tool}")
    subprocess.run(
        [
            sys.executable,
            str(repair_tool),
            "--asset-id",
            asset.asset_id,
            "--content-root",
            str(content_root),
        ],
        check=True,
    )
    if not script_path.is_file() or script_path.stat().st_size == 0:
        raise FileNotFoundError(f"script repair completed without creating: {script_path}")
    return script_path


def render_asset(asset: PublishableAsset, *, content_root: Path, output_root: Path) -> Path:
    """Render one planned asset through the existing Fish Audio + MoviePy path."""
    ensure_asset_script(asset, content_root=content_root)
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
    publish_short_now: bool = False,
    publish_long_now: bool = False,
    publish_next: bool = False,
) -> list[dict[str, Any]]:
    """Produce and publish the assets due on the Cairo calendar date."""
    story_id = find_or_create_story_plan(
        content_root,
        dry_run=dry_run,
        start_after=target_date,
    )
    assets = load_series_assets(content_root, story_id)
    state = load_state(content_root, story_id)
    initial_launch = publish_first_now and not state.get("assets")
    if publish_long_now:
        due = [first_pending_long_asset(assets, state, now=target_date)]
    elif publish_short_now:
        due = [first_pending_short_asset(assets, state)]
    elif publish_next:
        due = [next_pending_asset(assets, state, now=target_date)]
    elif initial_launch:
        due = [first_pending_long_asset(assets, state, now=target_date)]
    else:
        due = due_assets_for_date(assets, state, target_date)
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
    parser.add_argument(
        "--publish-short-now",
        action="store_true",
        help="Publish the earliest pending promotional Short without re-uploading long episodes.",
    )
    parser.add_argument(
        "--publish-long-now",
        action="store_true",
        help="Publish the earliest pending long episode immediately as public.",
    )
    parser.add_argument(
        "--publish-next",
        action="store_true",
        help="Publish exactly one next pending asset immediately; used by the four-times-daily scheduler.",
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
            publish_short_now=args.publish_short_now,
            publish_long_now=args.publish_long_now,
            publish_next=args.publish_next,
        )
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
