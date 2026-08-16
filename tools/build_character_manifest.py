"""Build a provider-neutral visual scene manifest from character.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow `python tools/build_character_manifest.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.character_consistency import build_scene_manifest, load_character_bible


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build a character-consistent image generation manifest")
    parser.add_argument("--character-file", type=Path, required=True)
    parser.add_argument("--scene", required=True, help="Scene description")
    parser.add_argument("--camera", default="medium cinematic shot")
    parser.add_argument("--reference-image")
    parser.add_argument("--seed", type=int)
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--model", default="provider_default")
    parser.add_argument("--adapter", default="reference_image")
    parser.add_argument("--adapter-weight", type=float, default=0.72)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    character = load_character_bible(args.character_file)
    manifest = build_scene_manifest(
        character,
        args.scene,
        args.camera,
        reference_image=args.reference_image,
        seed=args.seed,
        width=args.width,
        height=args.height,
        model=args.model,
        adapter=args.adapter,
        adapter_weight=args.adapter_weight,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
