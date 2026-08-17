from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from core.content_pipeline import PublishableAsset
from core.youtube_publisher import YouTubePublisher, settings_from_env


def build_asset(args: argparse.Namespace) -> PublishableAsset:
    now = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    return PublishableAsset(
        asset_id=args.asset_id,
        series_id=args.series_id,
        series_title=args.series_title,
        part_number=args.part_number,
        script_file=args.script_file,
        content_format="long",
        title=args.title,
        description=args.description,
        tags=tuple(tag.strip() for tag in args.tags.split(",") if tag.strip()),
        scheduled_at=now,
        playlist_title=args.playlist_title,
        playlist_description=args.playlist_description,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Upload one generated episode to YouTube immediately as Public")
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--asset-id", default="case-001-EP02")
    parser.add_argument("--series-id", default="case-001")
    parser.add_argument("--series-title", default="ملف الرصد 17")
    parser.add_argument("--part-number", type=int, default=2)
    parser.add_argument("--script-file", default="scripts/long/case-001-EP02.txt")
    parser.add_argument("--title", default="ملف الرصد 17 | الحلقة 02 | رواة الواقع")
    parser.add_argument(
        "--description",
        default=(
            "الحلقة الثانية من الرواية البوليسية العربية «ملف الرصد 17».\n\n"
            "تقديم نور من قناة رواة الواقع. هذا الفيديو يتضمن شخصية وصوتًا مولدين بالذكاء الاصطناعي.\n\n"
            "اكتب توقعك في التعليقات واشترك لمتابعة بقية خيوط القضية."
        ),
    )
    parser.add_argument("--tags", default="رواة الواقع,رواية عربية,قصة بوليسية,غموض,تحقيق,روايات صوتية")
    parser.add_argument("--playlist-title", default="ملف الرصد 17 | الرواية الكاملة")
    parser.add_argument("--playlist-description", default="الحلقات الكاملة من رواية ملف الرصد 17 على قناة رواة الواقع.")
    parser.add_argument("--no-playlist", action="store_true")
    args = parser.parse_args(argv)

    video_path = args.video.resolve()
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise FileNotFoundError(f"video file not found or empty: {video_path}")

    publisher = YouTubePublisher(settings_from_env())
    asset = build_asset(args)
    playlist_id = None if args.no_playlist else publisher.ensure_playlist(args.playlist_title, args.playlist_description)
    result = publisher.upload_video(asset, video_path, playlist_id)
    print(
        json.dumps(
            {
                "video_id": result.video_id,
                "video_url": result.video_url,
                "playlist_id": result.playlist_id,
                "privacy_status": "public",
                "contains_synthetic_media": True,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
