"""Free cloud artwork through the volunteer-run AI Horde.

No cloud account, payment method, paid credits, or local GPU is required.
Anonymous requests are lowest priority and may wait or be rejected under load.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API = "https://aihorde.net/api/v2"
ANONYMOUS_KEY = "0000000000"

CHARACTER_BIBLE = (
    "Original children's story characters; keep their appearance consistent: "
    "Nouri is a tiny cute emerald-green firefly, round body, two delicate "
    "translucent wings, large kind expressive eyes, two short antennae, "
    "warm golden glowing abdomen. Rima is a cheerful young girl with dark "
    "brown hair, turquoise headband and coral-pink pajamas. Timo is a small "
    "friendly orange fox cub with cream muzzle and a soft yellow hoodie. "
)
STYLE = (
    "beautiful polished 3D animated storybook illustration, appealing expressive "
    "character design, cinematic soft lighting, rich gentle colors, cozy bedroom "
    "details, warm golden light, magical firefly particles, professional wide "
    "16:9 composition, child-safe soothing bedtime mood. No text, no watermark, "
    "no logo, no horror, no scary faces, no extra limbs, no distorted anatomy."
)
SHOTS = {
    1: "Twilight establishing view of a magical cozy child's bedroom. Nouri floats "
       "above colorful toys beside a softly glowing bedside lamp. Crescent moon "
       "and stars through the window.",
    2: "Rima enters the warm bedroom holding colorful picture cards. Timo carries "
       "a little toy basket. Nouri hovers happily to greet his friends.",
    3: "The three friends tidy the bedroom together: Nouri guides glowing blocks "
       "into a toy chest, Rima places books on a shelf, Timo catches a rolling ball.",
    4: "Bedtime preparation near a child-friendly washbasin and mirror. Nouri "
       "brushes his teeth with a tiny toothbrush while Rima smiles and Timo holds "
       "a folded pajama top.",
    5: "Quiet calming moment beside the bed and moonlit window. Rima dims the "
       "bedside light, Timo places a golden star ornament by the pillow, and "
       "Nouri takes a peaceful breath.",
    6: "Tender final bedtime scene. Nouri lies tucked beneath a soft blanket, "
       "eyes gently closing, while Rima and Timo wave goodnight under tiny "
       "golden stars and peaceful moonlight.",
}


class CloudArtworkError(RuntimeError):
    pass


def _request(path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        API + path,
        data=data,
        headers={
            "apikey": ANONYMOUS_KEY,
            "Client-Agent": "HikayatunaKids:1.0:github-actions",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="GET" if data is None else "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[-1000:]
        raise CloudArtworkError(f"AI Horde returned HTTP {exc.code}: {detail}") from exc
    except Exception as exc:
        raise CloudArtworkError(f"AI Horde request failed: {type(exc).__name__}: {exc}") from exc


def generate_scene_image(index: int, output: Path, scene: dict[str, Any]) -> None:
    if index not in SHOTS:
        raise CloudArtworkError(f"No approved visual prompt exists for scene {index}.")
    prompt = CHARACTER_BIBLE + SHOTS[index] + " " + STYLE
    prompt += " Scene setting: " + str(scene.get("setting", ""))
    prompt += " Scene action: " + str(scene.get("action", ""))
    submitted = _request("/generate/async", {
        "prompt": prompt[:1800],
        "params": {
            "sampler_name": "k_euler",
            "cfg_scale": 7,
            "width": 512,
            "height": 512,
            "steps": 25,
            "n": 1,
        },
        "nsfw": False,
        "censor_nsfw": True,
        "models": ["stable_diffusion"],
        "r2": True,
    })
    job_id = submitted.get("id")
    if not job_id:
        raise CloudArtworkError("AI Horde did not return a generation job ID.")
    deadline = time.monotonic() + 1800
    while time.monotonic() < deadline:
        time.sleep(20)
        check = _request(f"/generate/check/{job_id}")
        if check.get("faulted"):
            raise CloudArtworkError("AI Horde generation failed on all available workers.")
        if check.get("done"):
            break
    else:
        raise CloudArtworkError("AI Horde queue timed out after 30 minutes.")
    result = _request(f"/generate/status/{job_id}")
    generations = result.get("generations") or []
    if not generations or not generations[0].get("img"):
        raise CloudArtworkError("AI Horde completed without returning an image.")
    image_value = generations[0]["img"]
    if image_value.startswith("http://") or image_value.startswith("https://"):
        req = urllib.request.Request(image_value, headers={"User-Agent": "HikayatunaKids/1.0"})
        with urllib.request.urlopen(req, timeout=90) as response:
            image_bytes = response.read()
    else:
        import base64
        image_bytes = base64.b64decode(image_value)
    if len(image_bytes) < 10_000:
        raise CloudArtworkError("AI Horde image failed the file integrity check.")
    if not (image_bytes.startswith(b"\\xff\\xd8\\xff") or image_bytes.startswith(b"\\x89PNG")):
        raise CloudArtworkError("AI Horde returned an unsupported or invalid image format.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(image_bytes)
