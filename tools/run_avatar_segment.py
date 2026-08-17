from __future__ import annotations

import argparse
from pathlib import Path

from core.avatar_animation import build_avatar_provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate one talking-avatar segment")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--provider", choices=("d_id", "sadtalker"), default="d_id")
    parser.add_argument("--source-url", help="HTTPS image URL for D-ID")
    parser.add_argument("--source-image", type=Path, help="Local portrait image for SadTalker")
    parser.add_argument("--name", default="nour-avatar-smoke-test")
    args = parser.parse_args(argv)

    if args.provider == "d_id" and not args.source_url:
        parser.error("--source-url is required with --provider d_id")
    if args.provider == "sadtalker" and not args.source_image:
        parser.error("--source-image is required with --provider sadtalker")

    provider = build_avatar_provider(
        args.provider,
        source_url=args.source_url,
        source_image=args.source_image,
    )
    result = provider.create_talking_segment(
        audio_path=args.audio,
        output_path=args.output,
        name=args.name,
        expression_events=[
            {"start_frame": 0, "expression": "serious", "intensity": 0.55},
        ],
    )
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
