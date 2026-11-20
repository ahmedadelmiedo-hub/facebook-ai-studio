"""Cloud-hosted AI artwork for the Hikayatuna Kids renderer.

Uses Cloudflare Workers AI FLUX.1 schnell. No local model, no paid vidIQ credits,
and deliberately no low-quality local-art fallback.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

MODEL = "@cf/black-forest-labs/flux-1-schnell"
CHARACTER_BIBLE = (
    "Keep these original characters visually consistent in every image: "
    "Nouri is a tiny cute emerald-green firefly, round body, two delicate "
    "translucent wings, large kind expressive eyes, two short antennae, "
    "a warm golden glowing abdomen; Rima is a cheerful young girl with "
    "dark brown hair, turquoise headband and coral-pink pajamas; Timo is "
    "a small friendly orange fox cub with cream muzzle and a soft yellow hoodie. "
)
STYLE = (
    "Premium feature-quality 3D animated family film still, beautiful polished "
    "storybook art direction, expressive appealing character design, cinematic "
    "soft global illumination, rich but gentle colors, intricate cozy bedroom "
    "details, warm golden practical lighting, magical firefly particles, "
    "professional composition, child-safe and soothing bedtime mood. "
    "Wide 16:9 landscape frame. No text, no letters, no watermark, no logo, "
    "no horror, no scary faces, no extra limbs, no distorted anatomy."
)
SHOTS = {
    1: "Establishing shot of a magical cozy child's bedroom at twilight. Nouri "
       "floats above scattered colorful toys beside a softly glowing bedside lamp, "
       "looking sleepy and curious. A crescent moon and stars are visible through "
       "the window. Wide cinematic composition.",
    2: "Rima enters the warm magical bedroom holding three colorful picture cards. "
       "Timo the orange fox cub carries a small toy basket. Nouri hovers happily "
       "to greet his friends. Medium-wide welcoming shot.",
    3: "The three friends happily tidy the bedroom together: Nouri guides glowing "
       "blocks into a toy chest, Rima places books on a shelf, and Timo catches "
       "a rolling ball. Energetic but gentle action, wide shot.",
    4: "Bedtime preparation scene near a child-friendly washbasin and bedroom "
       "mirror. Nouri brushes his teeth with a tiny toothbrush while Rima smiles "
       "encouragingly and Timo holds a folded pajama top. Warm clean bathroom nook.",
    5: "Quiet calming moment beside the bed and moonlit window. Rima gently dims "
       "the bedside light, Timo places a little golden star ornament by the pillow, "
       "and Nouri takes a peaceful slow breath as his golden abdomen glows softly.",
    6: "Tender final bedtime scene. Nouri lies comfortably tucked beneath a soft "
       "blanket in his cozy bed, eyes gently closing, while Rima and Timo wave "
       "goodnight. The room glows with tiny golden stars and peaceful moonlight.",
}


class CloudArtworkError(RuntimeError):
    """Raised when cloud artwork cannot be generated and validated."""


def generate_scene_image(index: int, output: Path, scene: dict[str, Any]) -> None:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    if not account_id or not token:
        raise CloudArtworkError(
            "Cloud image generation is not configured. Add CLOUDFLARE_ACCOUNT_ID "
            "and CLOUDFLARE_API_TOKEN as GitHub Actions secrets."
        )
    if index not in SHOTS:
        raise CloudArtworkError(f"No approved visual prompt exists for scene {index}.")

    prompt = (
        CHARACTER_BIBLE
        + SHOTS[index]
        + " Scene context: " + str(scene.get("setting", ""))
        + ". Action: " + str(scene.get("action", ""))
        + ". " + STYLE
    )
    # The API accepts at most 2048 prompt characters.
    prompt = prompt[:2048]
    seed = int(os.environ.get("KIDS_IMAGE_SEED", "711001")) + index
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
    payload = json.dumps({"prompt": prompt, "steps": 8, "seed": seed}).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "HikayatunaKidsProduction/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1200:]
        raise CloudArtworkError(
            f"Cloudflare image API returned HTTP {exc.code}: {detail}"
        ) from exc
    except Exception as exc:
        raise CloudArtworkError(
            f"Cloudflare image request failed: {type(exc).__name__}: {exc}"
        ) from exc

    encoded = data.get("result", {}).get("image")
    if not encoded:
        raise CloudArtworkError(
            "Cloudflare returned no image: " + json.dumps(data, ensure_ascii=False)[:1200]
        )
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise CloudArtworkError("Cloud image payload was not valid base64.") from exc
    if len(image_bytes) < 20_000 or not (
        image_bytes.startswith(b"\xff\xd8\xff") or image_bytes.startswith(b"\x89PNG")
    ):
        raise CloudArtworkError(
            f"Generated image failed integrity checks ({len(image_bytes)} bytes)."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image_bytes)
