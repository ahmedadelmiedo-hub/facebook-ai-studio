import json
import os
import pathlib
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path(__file__).parent
CONFIG = json.loads((ROOT / "channel.json").read_text(encoding="utf-8"))
QUEUE = json.loads((ROOT / "queue.json").read_text(encoding="utf-8"))

API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
if not API_KEY:
    raise SystemExit("Missing GROQ_API_KEY GitHub Actions secret")

episode_id = os.environ.get("EPISODE_ID", "").strip()
episodes = QUEUE.get("episodes", [])
episode = next(
    (item for item in episodes if item.get("id") == episode_id),
    None,
) if episode_id else next(
    (item for item in episodes if item.get("status") == "queued"),
    None,
)
if episode is None:
    raise SystemExit(f"No matching queued episode found for EPISODE_ID={episode_id!r}")
if episode.get("status") != "queued":
    raise SystemExit(f"Episode {episode.get('id')} is not queued")

model = "openai/gpt-oss-120b"

# Verify that this exact model is active for the API key before spending a generation request.
models_request = urllib.request.Request(
    "https://api.groq.com/openai/v1/models",
    headers={
        "Authorization": "Bearer " + API_KEY,
        "Accept": "application/json",
        "User-Agent": "secrets-of-the-wilderness/1.2",
    },
    method="GET",
)
try:
    with urllib.request.urlopen(models_request, timeout=45) as response:
        available_models = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    details = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(
        f"Groq model preflight failed (HTTP {exc.code}); "
        f"check that GROQ_API_KEY is valid and can list models: {details[:2000]}"
    ) from None
except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Could not verify Groq model availability: {exc}") from None

model_entry = next(
    (item for item in available_models.get("data", []) if item.get("id") == model),
    None,
)
if model_entry is None or model_entry.get("active") is False:
    raise SystemExit(
        f"Required Groq model {model!r} is not active/available for this API key. "
        "No generation request was sent. Check Groq Console model access."
    )
print(f"Groq model preflight passed: {model}")

prompt = f'''اكتب سيناريو وثائقيًا عربيًا أصليًا لقناة {CONFIG['channel_name']}.
الموضوع: {episode['topic']}. العنوان: {episode['title']}.
الأسلوب: مزيج من الوثائقي المشوق والسرد القصصي، بصوت راوٍ رجالي.
اكتب افتتاحية قوية، ثم 6 إلى 8 مشاهد متسلسلة، وخاتمة. اجعل المعلومات العلمية دقيقة، ولا تختلق حقائق أو أرقامًا أو اقتباسات. ضع [بحاجة إلى تحقق] بجوار أي معلومة غير مؤكدة. أضف وصفًا بصريًا لكل مشهد، ونصوصًا قصيرة على الشاشة، وثلاث أفكار Shorts في النهاية. اللغة عربية واضحة مناسبة للتعليق الصوتي.'''

payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.6,
    "max_completion_tokens": 12000,
    "reasoning_effort": "medium",
}, ensure_ascii=False).encode("utf-8")

request = urllib.request.Request(
    "https://api.groq.com/openai/v1/chat/completions",
    data=payload,
    headers={
        "Authorization": "Bearer " + API_KEY,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "secrets-of-the-wilderness/1.2",
    },
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=300) as response:
        data = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    details = exc.read().decode("utf-8", errors="replace")
    raise SystemExit(f"Groq API returned HTTP {exc.code}: {details[:4000]}") from None
except urllib.error.URLError as exc:
    raise SystemExit(f"Could not reach Groq API: {exc.reason}") from None
except (TimeoutError, json.JSONDecodeError) as exc:
    raise SystemExit(f"Groq API response/connection error: {exc}") from None

try:
    choice = data["choices"][0]
    script = (choice["message"].get("content") or "").strip()
except (KeyError, IndexError, TypeError):
    raise SystemExit("Groq API response did not contain a chat completion choice") from None

if not script:
    raise SystemExit("Groq returned an empty script; no output files were written")

safe_id = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in episode["id"])
out = ROOT / "output"
out.mkdir(exist_ok=True)
script_path = out / f"{safe_id}-script.md"
metadata_path = out / f"{safe_id}-metadata.json"

script_path.write_text(
    "# " + episode["title"] + "\n\n" + script + "\n",
    encoding="utf-8",
)
metadata = {
    "channel": CONFIG["channel_name"],
    "episode": episode,
    "model": data.get("model", model),
    "provider": "Groq",
    "response_id": data.get("id"),
    "finish_reason": choice.get("finish_reason"),
    "usage": data.get("usage"),
    "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    "review_required": True,
}
metadata_path.write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"Created script: {script_path.relative_to(ROOT)}")
print(f"Created metadata: {metadata_path.relative_to(ROOT)}")
print("Human review is required before publishing.")
