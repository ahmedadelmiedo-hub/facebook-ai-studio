"""Character identity loading, prompt composition, and deterministic visual metadata."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class CharacterBible:
    """Validated character definition loaded from a JSON file."""

    raw: dict[str, Any]
    source_path: Path

    @property
    def character_id(self) -> str:
        return str(self.raw["character_id"])

    @property
    def version(self) -> int | str:
        return self.raw.get("version", 1)

    @property
    def reference_image(self) -> str | None:
        assets = self.raw.get("reference_assets", {})
        return assets.get("master_image")


def load_character_bible(path: Path) -> CharacterBible:
    """Load and validate a project character.json without calling any provider."""
    if not path.is_file():
        raise FileNotFoundError(f"character file not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid character JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ValueError("character JSON root must be an object")
    for field in ("character_id", "identity_anchors", "prompt_template"):
        if field not in data:
            raise ValueError(f"character JSON is missing required field: {field}")
    if not isinstance(data["identity_anchors"], dict):
        raise ValueError("identity_anchors must be an object")
    if not isinstance(data["prompt_template"], dict):
        raise ValueError("prompt_template must be an object")
    return CharacterBible(raw=data, source_path=path)


def _flatten_identity(character: CharacterBible) -> str:
    raw = character.raw
    identity = raw.get("identity_anchors", {})
    wardrobe = raw.get("wardrobe_anchors", {})
    style = raw.get("visual_style", {})

    parts: list[str] = []
    for key, value in identity.items():
        parts.append(f"{key}: {value}")
    if wardrobe:
        default_outfit = wardrobe.get("default_outfit")
        if default_outfit:
            parts.append(f"default outfit: {default_outfit}")
        accessories = wardrobe.get("accessories", [])
        if accessories:
            parts.append("accessories: " + ", ".join(map(str, accessories)))
    for key in ("style", "linework", "lighting"):
        if style.get(key):
            parts.append(f"{key}: {style[key]}")
    palette = style.get("palette", [])
    if palette:
        parts.append("palette: " + ", ".join(map(str, palette)))
    return "; ".join(parts)


def _negative_prompt(character: CharacterBible) -> str:
    raw = character.raw
    template = raw.get("prompt_template", {})
    negative = template.get("negative_prompt", "")
    if negative:
        return str(negative)
    identity_negative = raw.get("negative_identity", [])
    return ", ".join(map(str, identity_negative))


def build_prompt(
    character: CharacterBible,
    scene_description: str,
    camera: str = "medium cinematic shot",
) -> tuple[str, str]:
    """Build positive and negative prompts while keeping identity deterministic."""
    scene_description = scene_description.strip()
    camera = camera.strip()
    if not scene_description:
        raise ValueError("scene_description cannot be empty")
    if not camera:
        raise ValueError("camera cannot be empty")

    template = character.raw.get("prompt_template", {})
    style = character.raw.get("visual_style", {})
    style_text = ", ".join(
        str(value)
        for key in ("style", "linework", "lighting")
        if (value := style.get(key))
    )
    positive_parts = [
        _flatten_identity(character),
        style_text,
        f"scene: {scene_description}",
        f"camera: {camera}",
        "no readable text in the image",
    ]
    # Preserve an explicit template prefix when a provider-specific prompt is added later.
    prefix = str(template.get("positive_prompt_prefix", "")).strip()
    if prefix:
        positive_parts.insert(0, prefix)
    positive = "; ".join(part for part in positive_parts if part)
    return positive, _negative_prompt(character)


def generation_key(config: dict[str, Any]) -> str:
    """Return a stable cache key for a complete generation configuration."""
    payload = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:24]


def build_scene_manifest(
    character: CharacterBible,
    scene_description: str,
    camera: str,
    *,
    reference_image: str | None = None,
    seed: int | None = None,
    width: int = 1920,
    height: int = 1080,
    model: str = "provider_default",
    adapter: str = "reference_image",
    adapter_weight: float = 0.72,
) -> dict[str, Any]:
    """Create provider-neutral metadata that a real image adapter can consume."""
    positive, negative = build_prompt(character, scene_description, camera)
    reference = reference_image or character.reference_image
    config = {
        "character_id": character.character_id,
        "character_version": character.version,
        "character_file": str(character.source_path),
        "reference_image": reference,
        "prompt": positive,
        "negative_prompt": negative,
        "seed": seed,
        "width": width,
        "height": height,
        "model": model,
        "adapter": adapter,
        "adapter_weight": adapter_weight,
    }
    return {
        "schema_version": 1,
        "character_id": character.character_id,
        "character_version": character.version,
        "scene": {
            "description": scene_description.strip(),
            "camera": camera.strip(),
        },
        "generation": config,
        "generation_key": generation_key(config),
        "cache_path": f"storage/visual-cache/{character.character_id}/{generation_key(config)}.png",
        "status": "planned",
    }
