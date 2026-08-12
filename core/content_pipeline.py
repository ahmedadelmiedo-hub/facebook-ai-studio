"""Select daily Rowat Alwaqe assets from a generated series plan.

This module stays independent from Fish Audio and YouTube. It maps story-plan metadata
to long/short scripts and records completed assets so a daily workflow does not repeat an
already produced upload.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

CAIRO_TZ = ZoneInfo("Africa/Cairo")


@dataclass(frozen=True)
class PublishableAsset:
    """All metadata needed to render and publish one planned video."""

    asset_id: str
    series_id: str
    series_title: str
    part_number: int
    script_file: str
    content_format: str
    title: str
    description: str
    tags: tuple[str, ...]
    scheduled_at: str
    playlist_title: str
    playlist_description: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"production metadata is missing: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"expected a JSON object in {path}")
    return data


def load_series_assets(content_root: Path, story_id: str) -> list[PublishableAsset]:
    """Load an episode and its three promotional Shorts from a generated plan."""
    plan = read_json(content_root / "production" / story_id / "series_plan.json")
    series_title = str(plan["series_title"])
    playlist_title = str(plan["playlist_title"])
    playlist_description = str(plan["playlist_description"])
    assets: list[PublishableAsset] = []

    for episode in plan.get("episodes", []):
        episode_id = str(episode["id"])
        part_number = int(episode["part_number"])
        episode_title = str(episode["title"])
        assets.append(
            PublishableAsset(
                asset_id=episode_id,
                series_id=story_id,
                series_title=series_title,
                part_number=part_number,
                script_file=f"scripts/long/{episode_id}.txt",
                content_format="long",
                title=episode_title,
                description=(
                    f"{episode_title}\n\n"
                    f"استمع إلى رواية «{series_title}» بالترتيب من خلال Playlist: {playlist_title}.\n\n"
                    "اكتب توقعك في التعليقات، واشترك لتصلك بقية خيوط القضية."
                ),
                tags=("رواة الواقع", "رواية عربية", "قصة بوليسية", "غموض", "تحقيق"),
                scheduled_at=str(episode["long_release_at"]),
                playlist_title=playlist_title,
                playlist_description=playlist_description,
            )
        )
        for short in episode.get("shorts", []):
            short_id = str(short["asset_id"])
            kind = str(short["kind"])
            assets.append(
                PublishableAsset(
                    asset_id=short_id,
                    series_id=story_id,
                    series_title=series_title,
                    part_number=part_number,
                    script_file=f"scripts/shorts/{short_id}.txt",
                    content_format="short",
                    title=f"{series_title} | {kind.replace('_', ' ')} | البارت {part_number}",
                    description=(
                        f"مقطع من «{series_title}» — البارت {part_number}.\n"
                        f"اسمع الحلقة كاملة من Playlist: {playlist_title}.\n"
                        "ما هي نظريتك؟"
                    ),
                    tags=("رواة الواقع", "Shorts", "رواية عربية", "غموض", "تحقيق"),
                    scheduled_at=str(short["scheduled_at"]),
                    playlist_title=playlist_title,
                    playlist_description=playlist_description,
                )
            )
    return assets


def state_path(content_root: Path, story_id: str) -> Path:
    return content_root / "production" / story_id / "publication_state.json"


def load_state(content_root: Path, story_id: str) -> dict[str, Any]:
    path = state_path(content_root, story_id)
    if not path.exists():
        return {"schema_version": 1, "assets": {}}
    data = read_json(path)
    if not isinstance(data.get("assets", {}), dict):
        raise ValueError("publication state assets must be an object")
    return data


def save_state(content_root: Path, story_id: str, state: dict[str, Any]) -> Path:
    path = state_path(content_root, story_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def due_assets_for_date(
    assets: list[PublishableAsset],
    state: dict[str, Any],
    target_date: datetime | None = None,
) -> list[PublishableAsset]:
    """Return assets scheduled for one Cairo calendar day and not already uploaded."""
    local_date = (target_date or datetime.now(UTC)).astimezone(CAIRO_TZ).date()
    completed = state.get("assets", {})
    due: list[PublishableAsset] = []
    for asset in assets:
        scheduled = datetime.fromisoformat(asset.scheduled_at.replace("Z", "+00:00")).astimezone(CAIRO_TZ)
        status = completed.get(asset.asset_id, {}).get("status")
        if scheduled.date() == local_date and status not in {"uploaded", "scheduled", "published"}:
            due.append(asset)
    return sorted(due, key=lambda item: item.scheduled_at)


def mark_uploaded(
    state: dict[str, Any],
    asset: PublishableAsset,
    *,
    video_id: str,
    playlist_id: str,
) -> dict[str, Any]:
    """Record a successful API response so the next daily run does not upload twice."""
    assets = state.setdefault("assets", {})
    assets[asset.asset_id] = {
        "status": "scheduled",
        "scheduled_at": asset.scheduled_at,
        "video_id": video_id,
        "playlist_id": playlist_id,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    return state


def build_parser() -> Any:
    import argparse

    parser = argparse.ArgumentParser(description="List pending Rowat Alwaqe uploads for a Cairo date.")
    parser.add_argument("--story-id", required=True)
    parser.add_argument("--content-root", type=Path, default=Path("content"))
    parser.add_argument("--date", help="Optional ISO time used to select one Cairo date")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    target = datetime.fromisoformat(args.date.replace("Z", "+00:00")) if args.date else None
    assets = load_series_assets(args.content_root, args.story_id)
    state = load_state(args.content_root, args.story_id)
    print(json.dumps(
        [asset.to_dict() for asset in due_assets_for_date(assets, state, target)],
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
