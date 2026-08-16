"""Generate one talking-avatar segment through the configured D-ID adapter."""

from __future__ import annotations

import argparse
from pathlib import Path

from core.avatar_animation import DIDAvatarProvider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate one D-ID talking-avatar segment")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--name", default="nour-avatar-smoke-test")
    args = parser.parse_args(argv)

    provider = DIDAvatarProvider(source_url=args.source_url)
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
