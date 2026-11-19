"""Provider-agnostic Arabic script engine for Hikayatuna Kids.

The default provider is deterministic Mock and never calls an external service.
A compatible text provider can be enabled explicitly with environment variables.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from core.kids_factory import CONFIG_PATH, QUEUE_PATH, RULES_PATH, ROOT, read_json, safety_issues

PRODUCTION_ROOT = ROOT / "content" / "production" / "kids"
MIN_WORDS = 300
MAX_WORDS = 500


class TextProvider(Protocol):
    name: str
    experimental: bool

    def generate(self, prompt: str) -> dict[str, Any]: ...


@dataclass
class MockTextProvider:
    name: str = "mock"
    experimental: bool = True

    def generate(self, prompt: str) -> dict[str, Any]:
        return {
            "provider": self.name,
            "experimental": True,
            "title": "مصباح نوري لا ينام",
            "learning_goal": "ترتيب خطوات ما قبل النوم",
            "scenes": [
                {"number": 1, "setting": "غرفة نوري الدافئة", "action": "يلمع نوري ثم يطفئ ويضيء مصباحه الصغير.", "dialogue": "قال نوري: أريد أن أنام، لكن مصباحي لا يهدأ.", "narration": "في ليلة هادئة، كان نوري يستعد للنوم. غسل وجهه، وارتدى ثوبه الناعم، ثم نظر إلى غرفته. كل شيء كان في مكانه تقريبًا، لكن المصباح الصغير ظل يلمع بسرعة. مرة يضيء، ومرة يخف ضوؤه، وكأنه لا يعرف كيف يقول تصبحون على خير. حاول نوري أن يغمض عينيه، فسمع صوتًا صغيرًا من المصباح."},
                {"number": 2, "setting": "باب الغرفة", "action": "تدخل ريما بابتسامة وتحمل ثلاث نجوم ورقية.", "dialogue": "قالت ريما: لكل شيء ترتيب بسيط. هل نجربه معًا؟", "narration": "سمعت ريما صوت نوري، فجاءت لتساعده. حملت ثلاث نجوم ورقية، وقالت إن كل نجمة تذكرنا بخطوة. لم تسرع ريما، ولم تقل إن هناك مشكلة كبيرة. جلست بجانب نوري وسألته: ماذا فعلت قبل أن تحاول النوم؟ فكر نوري قليلًا، ثم قال إنه ترك لعبته مفتوحة، ونسِي أن يضع كتابه على الرف، وبقي يفكر في لعب الغد. ابتسمت ريما وقالت: عندما نرتب الأشياء، يصبح القلب أكثر هدوءًا."},
                {"number": 3, "setting": "رف الألعاب", "action": "يضع نوري لعبته في صندوقها.", "dialogue": "قال نوري: أولًا نرتب.", "narration": "بدأ نوري بالخطوة الأولى: أعاد لعبته إلى مكانها. وضع المكعبات في الصندوق، وأغلق الغطاء بهدوء، ثم وضع الكتاب على الرف. وجد تيمو كرة صغيرة قرب الباب، فأعادها أيضًا إلى السلة. لم يكن الترتيب سباقًا، ولم يهتم الأصدقاء بمن ينتهي أولًا. كانوا يعملون ببطء، وكلما عاد شيء إلى مكانه، شعر نوري أن الغرفة أصبحت أوسع. نظر إلى مصباحه، فلاحظ أن لمعانه صار أبطأ قليلًا. قال نوري: يبدو أنه يحب الغرفة المرتبة."},
                {"number": 4, "setting": "قرب النافذة", "action": "يشرب نوري ماءً صغيرًا ويتنفس ببطء.", "dialogue": "قالت ريما: ثم نهدأ. نأخذ نفسًا لطيفًا، ونترك أفكار اليوم تمر مثل غيمة.", "narration": "بعد ذلك، جلس الأصدقاء قرب النافذة. شرب نوري قليلًا من الماء، ثم وضع الكوب في مكانه. أغلقت ريما الستارة نصف إغلاق، فبقي ضوء القمر ناعمًا. تنفسوا ببطء: واحدًا، ثم اثنين، ثم ثلاثة. لم يحاول أحد أن يطرد كل الأفكار دفعة واحدة. عندما تذكر نوري لعبة الغد، قال لنفسه: سأفكر فيها صباحًا. وعندما سمع صوتًا بعيدًا، عرف أنه صوت آمن من خارج الغرفة. بدأ المصباح يلمع بلطف، وكأنه يتنفس معهم."},
                {"number": 5, "setting": "سرير نوري", "action": "يصل تيمو ويخفض ضوء النجمة بجانب السرير.", "dialogue": "قال تيمو: وأخيرًا ننام. يمكن أن تكون الأحلام هادئة مثل ضوء النجمة.", "narration": "جاء تيمو بهدوء، ووضع نجمة صغيرة قرب السرير. سأل نوري إن كان يحتاج إلى شيء آخر، فأجاب نوري: أحتاج إلى غطاء دافئ وكلمة طيبة. أعطته ريما الغطاء، وقال تيمو: تصبح على خير يا نوري. شكرهم نوري، ثم وضع يديه تحت خده. بقيت النجمة الورقية قربه، وبقي المصباح الصغير يرسل ضوءًا خفيفًا لا يزعج العين. شعر نوري أن أصدقاءه قريبون، وأن الغرفة تعرف وقت الراحة."},
                {"number": 6, "setting": "الغرفة بعد أن هدأت", "action": "ينطفئ ضوء المصباح تدريجيًا ويبقى ضوء النجمة ناعمًا.", "dialogue": "قال نوري: أولًا نرتب، ثم نهدأ، وأخيرًا ننام.", "narration": "هدأ المصباح، وابتسم نوري. تذكر الخطوات الثلاث، فصارت سهلة مثل أغنية قصيرة. أولًا نعيد الأشياء إلى أماكنها، ثم نهدئ أجسامنا وأفكارنا، وأخيرًا نغلق أعيننا وننام. لم تختف كل الأصوات من العالم، ولم يحتج نوري إلى أن يجعل الليل صامتًا تمامًا. كان يكفي أن يعرف أنه آمن ومستعد للراحة. قالت ريما: غدًا نكمل لعبتنا. ولوح تيمو بيده. وقبل أن ينام نوري، سأل أصدقاءه الصغار: ما خطوتكم المفضلة قبل النوم؟"}
            ],
            "original_song": "نرتب، نهدأ، ثم ننام، في ليلنا الحلو لا نضام.",
            "quiz": "ما الخطوة التي تأتي بعد الترتيب؟"
        }


@dataclass
class CompatibleTextProvider:
    api_key: str
    base_url: str
    model: str
    name: str = "compatible-text"
    experimental: bool = False

    def generate(self, prompt: str) -> dict[str, Any]:
        payload = {"model": self.model, "messages": [{"role": "system", "content": "أنت كاتب قصص أطفال آمنة بالعربية."}, {"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
        request = urllib.request.Request(
            f"{self.base_url.rstrip('/')}/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json", "User-Agent": "hikayatuna-kids-script-engine"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read(1200).decode("utf-8", errors="replace")
            raise RuntimeError(f"text provider HTTP {exc.code}: {detail}") from None
        except urllib.error.URLError as exc:
            raise RuntimeError(f"text provider network error: {exc.reason}") from exc
        try:
            content = data["choices"][0]["message"]["content"]
            if isinstance(content, str) and content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.I)
            result = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise RuntimeError("text provider returned invalid JSON episode data") from exc
        if not isinstance(result, dict):
            raise RuntimeError("text provider response must be a JSON object")
        return {**result, "provider": self.name, "experimental": False}


def provider_from_env(provider_name: str | None = None) -> TextProvider:
    selected = (provider_name or os.getenv("KIDS_TEXT_PROVIDER", "mock")).strip().lower()
    if selected in {"openai", "gemini", "openrouter", "compatible"}:
        key = os.getenv("KIDS_TEXT_API_KEY", "").strip()
        if not key:
            return MockTextProvider()
        return CompatibleTextProvider(key, os.getenv("KIDS_TEXT_BASE_URL", "https://api.openai.com/v1"), os.getenv("KIDS_TEXT_MODEL", "gpt-4o-mini"))
    return MockTextProvider()


def find_episode(episode_id: str) -> dict[str, Any]:
    queue = read_json(QUEUE_PATH)
    for item in queue.get("stories", []):
        if item.get("episode_id") == episode_id:
            return item
    raise ValueError(f"episode not found in kids queue: {episode_id}")


def build_prompt(episode: dict[str, Any], characters: dict[str, Any], rules: dict[str, Any]) -> str:
    names = ", ".join(character["name"] for character in characters["characters"] if character["id"] in episode["character_pair"])
    return f"""اكتب JSON فقط لحلقة أطفال أصلية بعنوان {episode['title']} مدتها 3 دقائق للفئة 3–6 سنوات. اللغة: العربية الفصحى المبسطة. الهدف التعليمي: {episode['learning_goal']}. الشخصيات المسموحة: {names}. الموقف: {episode['conflict']}. قسم القصة إلى 6 مشاهد. اجعل النص المنطوق بين {MIN_WORDS} و{MAX_WORDS} كلمة تقريبًا، بنهاية إيجابية، وأغنية أصلية قصيرة وسؤال بسيط. ممنوع الرعب والعنف والجريمة والموت وأي شخصية محمية. أعد المفاتيح: title, learning_goal, scenes (number, setting, action, dialogue, narration), original_song, quiz."""


def flatten_spoken(script: dict[str, Any]) -> str:
    parts: list[str] = []
    for scene in script.get("scenes", []):
        parts.extend([str(scene.get("narration", "")), str(scene.get("dialogue", ""))])
    parts.extend([str(script.get("original_song", "")), str(script.get("quiz", ""))])
    return " ".join(p.strip() for p in parts if p.strip())


def validate_script(script: dict[str, Any], episode: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(script.get("title"), str) or not script["title"].strip():
        raise ValueError("script title is missing")
    scenes = script.get("scenes")
    if not isinstance(scenes, list) or len(scenes) != 6:
        raise ValueError("kids episode must contain exactly 6 scenes")
    for index, scene in enumerate(scenes, start=1):
        if scene.get("number") != index or not all(str(scene.get(key, "")).strip() for key in ("setting", "action", "dialogue", "narration")):
            raise ValueError(f"scene {index} is incomplete")
    spoken = flatten_spoken(script)
    words = re.findall(r"[^\W_]+", spoken, flags=re.UNICODE)
    if not MIN_WORDS <= len(words) <= MAX_WORDS:
        raise ValueError(f"spoken script has {len(words)} words; expected {MIN_WORDS}-{MAX_WORDS}")
    issues = safety_issues({**episode, "conflict": spoken}, rules)
    if issues:
        raise ValueError("script policy failed: " + "; ".join(issues))
    script["word_count"] = len(words)
    script["duration_minutes"] = 3
    return script


def write_script(episode_id: str, provider_name: str | None = None) -> Path:
    config = read_json(CONFIG_PATH)
    rules = read_json(RULES_PATH)
    episode = find_episode(episode_id)
    characters = read_json(ROOT / "content" / "characters" / "kids" / "characters.json")
    provider = provider_from_env(provider_name)
    result = provider.generate(build_prompt(episode, characters, rules))
    result = validate_script(result, episode, rules)
    result.update({"episode_id": episode_id, "provider": provider.name, "experimental": provider.experimental, "generated_at": datetime.now(UTC).isoformat(), "publish_enabled": False, "script_fingerprint": hashlib.sha256(flatten_spoken(result).encode("utf-8")).hexdigest()[:16]})
    out_dir = ROOT / config["production_root"] / episode_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "script.json"
    md_path = out_dir / "script.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = [f"# {result['title']}", "", f"مزود الكتابة: {provider.name}", f"تجريبي: {'نعم' if provider.experimental else 'لا'}", f"عدد الكلمات: {result['word_count']}", ""]
    for scene in result["scenes"]:
        markdown += [f"## المشهد {scene['number']} — {scene['setting']}", scene["narration"], scene["dialogue"], f"*الحركة: {scene['action']}*", ""]
    markdown += ["## الأنشودة الأصلية", result["original_song"], "", "## السؤال", result["quiz"], ""]
    md_path.write_text("\n".join(markdown), encoding="utf-8")
    manifest_path = out_dir / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest.setdefault("provider_status", {})["text"] = provider.name
        manifest.setdefault("quality_gate", {})["script_validation"] = "passed"
        manifest.setdefault("quality_gate", {})["status"] = "blocked"
        manifest["quality_gate"]["human_approval"] = False
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and validate a Hikayatuna Kids episode script")
    parser.add_argument("--episode-id", default="kids-ep-001")
    parser.add_argument("--provider", default=None)
    args = parser.parse_args()
    path = write_script(args.episode_id, args.provider)
    print(json.dumps({"status": "script_ready_for_review", "script": str(path.relative_to(ROOT)), "publish_enabled": False}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
