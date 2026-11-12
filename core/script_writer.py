"""Write Arabic wildlife documentary scripts for Secrets of the Wild.

The module deliberately separates narrative planning from media generation. It asks an
OpenAI-compatible text model for an original story bible, turns the bible into a
release plan, then saves one spoken-text script per long episode plus three Shorts.
No provider key is embedded in this repository.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from core.story_planner import EpisodePlan, SeriesPlan, build_series_plan

DEFAULT_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5"
MIN_EPISODE_COMPLETION_RATIO = 0.62
MAX_BLUEPRINT_COMPLETION_TOKENS = 2_000
MAX_EPISODE_COMPLETION_TOKENS = 5_200
MAX_CONTINUATION_COMPLETION_TOKENS = 2_600
MAX_EPISODE_CONTINUATIONS = 3
MAX_SHORT_COMPLETION_TOKENS = 900
MAX_PROVIDER_RETRIES = 4


@dataclass(frozen=True)
class WriterSettings:
    """Non-secret options for the compatible text-generation provider."""

    api_key: str
    base_url: str
    model: str
    output_root: Path
    dry_run: bool


def sanitize_story_id(value: str) -> str:
    """Return a safe stable identifier for files and YouTube metadata."""
    safe = re.sub(r"[^a-z0-9-]+", "-", value.strip().lower()).strip("-")
    if not safe:
        raise ValueError("story id must contain letters or numbers")
    return safe[:60]


def parse_json_response(text: str) -> dict[str, Any]:
    """Parse a JSON object even if a provider wrapped it in a Markdown fence."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("text provider returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise RuntimeError("text provider must return a JSON object")
    return data


def retry_after_seconds(details: str) -> float:
    """Extract a provider retry delay from a rate-limit message with a safe fallback."""
    match = re.search(r"try again in\s+([0-9.]+)s", details, flags=re.IGNORECASE)
    return float(match.group(1)) + 2.0 if match else 25.0


def request_chat(settings: WriterSettings, messages: list[dict[str, str]], *, max_tokens: int) -> str:
    """Call an OpenAI-compatible Chat Completions endpoint using only stdlib HTTP."""
    if settings.dry_run:
        raise RuntimeError("request_chat is unavailable in dry-run mode")
    if not settings.api_key:
        raise RuntimeError("SCRIPTWRITER_API_KEY is not configured")
    endpoint = f"{settings.base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": settings.model,
        "messages": messages,
        "temperature": 0.7,
        "max_completion_tokens": max_tokens,
    }
    if "groq.com" in settings.base_url:
        # GPT-OSS spends part of its completion budget on reasoning. Low effort plus
        # hidden reasoning reserves the response for the spoken Arabic script.
        payload.update({"reasoning_effort": "low", "include_reasoning": False})
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {settings.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "facebook-ai-studio/script-writer",
        },
        method="POST",
    )
    for attempt in range(MAX_PROVIDER_RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read(1_000).decode("utf-8", errors="replace")
            if exc.code == 429 and attempt < MAX_PROVIDER_RETRIES - 1:
                time.sleep(retry_after_seconds(details))
                continue
            raise RuntimeError(f"script provider returned HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"script provider network error: {exc.reason}") from exc

        choices = data.get("choices", [])
        content = choices[0].get("message", {}).get("content", "") if choices else ""
        if isinstance(content, str) and content.strip():
            return content.strip()
        if attempt < MAX_PROVIDER_RETRIES - 1:
            time.sleep(3)
            continue
        if not choices:
            raise RuntimeError("script provider returned no choices")
        raise RuntimeError("script provider returned an empty script")
    raise RuntimeError("script provider retry loop ended unexpectedly")


def build_blueprint_prompt(*, story_id: str, requested_theme: str, language: str) -> list[dict[str, str]]:
    """Build a fact-aware wildlife documentary episode blueprint."""
    system = """أنت منتج وكاتب وثائقيات حياة برية لقناة يوتيوب «أسرار البرية».
اكتب محتوى وثائقيًا عربيًا أصليًا عن الحيوانات وسلوكها وبيئاتها وتكيفاتها. افصل بوضوح بين الحقائق العلمية الراسخة والفرضيات، ولا تختلق أرقامًا أو وقائع أو اقتباسات. لا تقدّم الحيوان كأنه يفكر أو يتكلم كإنسان. تجنب مشاهد إيذاء الحيوانات أو تشجيع الاقتراب من الحيوانات الخطرة. أعد JSON فقط."""
    user = f"""أنشئ مخططًا لحلقة وثائقية عن الحياة البرية.
معرّف الحلقة: {story_id}
الموضوع: {requested_theme or 'الأخطبوط وذكاؤه وقدرته على الهروب'}
اللغة: {language or 'العربية الفصحى المبسطة'}
الأسلوب: وثائقي هجين، مشاهد سينمائية مع شرح علمي واضح.
المدة المستهدفة للحلقة الأولى: 8 إلى 9 دقائق.

أعد JSON بالمفاتيح:
{{
  "series_title": "عنوان جذاب",
  "language": "العربية الفصحى المبسطة",
  "estimated_total_words": 1200,
  "logline": "ملخص جذاب",
  "setting": "الموطن والبيئة",
  "protagonist": "الحيوان وخصائصه",
  "core_mystery": "السؤال العلمي الذي تجيب عنه الحلقة",
  "stakes": "أهمية السلوك أو التكيف للبقاء",
  "animals": ["النوع أو الأنواع المحورية"],
  "habitats": ["الموائل ذات الصلة"],
  "adaptations": ["تكيف أو سلوك موثق 1", "تكيف 2", "تكيف 3"],
  "threats": ["تهديد بيئي موثق 1", "تهديد 2", "تهديد 3"],
  "evidence_ladder": ["حقيقة علمية 1", "حقيقة 2", "حقيقة 3"],
  "final_reveal": "الخلاصة العلمية",
  "tone": "وثائقي مشوق ودقيق",
  "content_warning": ""
}}
لا تستخدم قصة تحقيق أو مشتبهين أو جريمة خيالية. لا تذكر مصادر علمية غير متأكد من وجودها."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

def validate_blueprint(data: dict[str, Any]) -> dict[str, Any]:
    """Validate a wildlife documentary blueprint before production."""
    required_strings = ("series_title", "language", "logline", "setting", "protagonist", "core_mystery", "stakes", "final_reveal", "tone")
    for key in required_strings:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise RuntimeError(f"blueprint is missing {key}")
    words = data.get("estimated_total_words")
    if not isinstance(words, int) or not 1_000 <= words <= 36_000:
        raise RuntimeError("blueprint estimated_total_words must be between 1000 and 36000")
    for key in ("animals", "habitats", "adaptations", "threats", "evidence_ladder"):
        if not isinstance(data.get(key), list) or len(data[key]) < 1:
            raise RuntimeError(f"blueprint must include at least one value for {key}")
    warning = data.get("content_warning", "")
    if not isinstance(warning, (str, list)):
        raise RuntimeError("blueprint content_warning has an unsupported type")
    return data

def dry_run_blueprint(story_id: str, language: str) -> dict[str, Any]:
    """Offline wildlife placeholder used only to validate planning and paths."""
    return {
        "series_title": "الأخطبوط: عبقري الهروب",
        "language": language if language and language != "auto" else "العربية الفصحى المبسطة",
        "estimated_total_words": 1_200,
        "logline": "رحلة تكشف كيف يستخدم الأخطبوط جسده وذكاءه لاستكشاف العالم والنجاة.",
        "setting": "الشعاب المرجانية والقيعان الساحلية",
        "protagonist": "الأخطبوط الشائع وقدراته العصبية والحسية",
        "core_mystery": "كيف يمر الأخطبوط من فتحات ضيقة ويحل مشكلات معقدة؟",
        "stakes": "التخفي والهروب والبحث عن الغذاء وتجنب المفترسات",
        "animals": ["الأخطبوط الشائع"],
        "habitats": ["الشعاب المرجانية", "الشقوق الصخرية"],
        "adaptations": ["جسم مرن بلا هيكل عظمي صلب", "أذرع مزودة بممصات", "تمويه وتغيير لون وملمس الجلد"],
        "threats": ["تدهور الموائل البحرية", "الصيد العرضي", "التلوث البحري"],
        "evidence_ladder": ["مرونة الجسم", "التعلم وحل المشكلات", "التمويه والسلوك الدفاعي"],
        "final_reveal": "قوة الأخطبوط ناتجة عن اجتماع المرونة والحواس والتعلم والسلوك المرن.",
        "tone": "وثائقي سينمائي مشوق ودقيق",
        "content_warning": "",
    }

def chapter_role(part_number: int, episode_count: int) -> str:
    """Describe the educational arc of a wildlife documentary episode."""
    if part_number == 1:
        return "افتتاح بصري قوي، تقديم الحيوان وموطنه، وطرح السؤال العلمي الرئيسي."
    if part_number == episode_count:
        return "الخلاصة: جمع الحقائق، توضيح أهمية السلوك للحياة البرية، وخاتمة مؤثرة."
    if part_number == episode_count - 1:
        return "كشف أعمق للتكيفات والتحديات البيئية مع تصحيح المفاهيم الشائعة."
    return "التعمق في السلوك والقدرات والتكيفات مع أمثلة موثقة وانتقالات سينمائية."

def build_episode_prompt(
    *,
    blueprint: dict[str, Any],
    plan: SeriesPlan,
    episode: EpisodePlan,
    previous_tail: str,
) -> list[dict[str, str]]:
    """Ask for spoken Arabic narration for exactly one long part."""
    system = """أنت تكتب نصًا صوتيًا لوثائقي عربي عن الحياة البرية لقناة «أسرار البرية».
أعد النص الذي سيقرأه راوي واحد بصوته مباشرة، بلا عناوين، بلا Markdown، وبلا أي ملاحظات للمخرج أو للممثل. اجعل السرد متصلًا وسهل النطق باللهجة/الفصحى المطلوبة. استخدم فقرات قصيرة وحوارًا محدودًا بصيغة الراوي مثل: «قال لي...» بدلاً من تغيير صوت المتحدثين.
لا تذكر أن النص مولد أو أنك ذكاء اصطناعي. لا تقلّد أسلوب أي شخص أو قناة. لا تحوّل الجريمة إلى تعليمات عملية ولا تتضمن عنفًا دمويًا تفصيليًا. لا تخترع سلوكًا أو معلومة علمية، وميّز بين المعلومة المؤكدة والتفسير المحتمل.
يجب أن تحتوي الحلقة على فاصل تفاعل واحد فقط، مدمج طبيعيًا داخل السرد، يدعو المشاهد لمشاركة أكثر سلوك أدهشه، ويطلب الإعجاب والاشتراك لمشاهدة وثائقيات أخرى. لا تستخدم عبارة «فاصل إعلاني» ولا تكسر الجو."""
    bible = json.dumps(blueprint, ensure_ascii=False)
    previous_context = previous_tail or "هذه هي الحلقة الأولى ولا يوجد سياق سابق."
    user = f"""اكتب الجزء {episode.part_number} من {plan.episode_count} للوثائقي «{plan.series_title}».
اللغة: {plan.language}
عدد الكلمات المستهدف: {episode.target_words} كلمة تقريبًا. لا تقل عن {int(episode.target_words * MIN_EPISODE_COMPLETION_RATIO)} كلمة.
وظيفة البارت: {chapter_role(episode.part_number, plan.episode_count)}
نقطة فاصل التفاعل: بعد نحو {episode.engagement_break_after_words} كلمة. هدفه: {episode.engagement_goal}
نهاية البارت: {episode.cliffhanger_goal}

كتاب القصة المرجعي (لا تنسخه حرفيًا إلى النص):
{bible}

آخر مقطع من البارت السابق كي تحافظ على الاستمرارية:
{previous_context}

أعد النص المنطوق للبارت فقط."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def build_episode_continuation_prompt(
    *,
    plan: SeriesPlan,
    episode: EpisodePlan,
    existing_script: str,
    minimum_words: int,
) -> list[dict[str, str]]:
    """Request only the missing natural continuation of an underlength long episode."""
    tail = existing_script[-1_200:]
    system = """أنت تكمل نصًا صوتيًا عربيًا أصليًا لوثائقي حياة برية.
أعد الاستكمال فقط، بلا عنوان أو تلخيص أو Markdown أو ملاحظات. أكمل من آخر جملة بسلاسة وباللغة نفسها، واحتفظ بالراوي الواحد والإيقاع المتصاعد. لا تختلق حقائق أو أرقامًا علمية، ولا تقلّد أسلوب أي شخص. لا تُنهِ البارت قبل أن تضيف مشاهد وأدلة وحوارًا قصيرًا كافيًا."""
    user = f"""هذه متابعة للجزء {episode.part_number} من {plan.episode_count} في وثائقي «{plan.series_title}».
اللغة: {plan.language}
الحد الأدنى المطلوب للبارت كاملًا: {minimum_words} كلمة. النص الحالي أقصر من ذلك، لذلك أكمل السرد وحده.

آخر مقطع مكتوب يجب أن تتابع منه مباشرة:
{tail}

أعد الاستكمال المنطوق فقط."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def complete_underlength_episode(
    settings: WriterSettings,
    *,
    plan: SeriesPlan,
    episode: EpisodePlan,
    script: str,
) -> str:
    """Append provider continuations until a long episode reaches its minimum narration length."""
    minimum_words = int(episode.target_words * MIN_EPISODE_COMPLETION_RATIO)
    for _ in range(MAX_EPISODE_CONTINUATIONS):
        if word_count(script) >= minimum_words:
            return script
        continuation = request_chat(
            settings,
            build_episode_continuation_prompt(
                plan=plan,
                episode=episode,
                existing_script=script,
                minimum_words=minimum_words,
            ),
            max_tokens=MAX_CONTINUATION_COMPLETION_TOKENS,
        )
        script = f"{script.rstrip()}\n\n{continuation.strip()}"
    return script


def build_short_prompt(*, script: str, episode: EpisodePlan, series_title: str, kind: str, instruction: str) -> list[dict[str, str]]:
    """Build a self-contained teaser prompt without copying the full episode verbatim."""
    source_limit = 2_400
    source = script[:source_limit]
    if kind != "opening_hook":
        source = script[max(0, len(script) // 3) : max(0, len(script) // 3) + source_limit]
    system = """أنت كاتب مقاطع قصيرة لقناة وثائقيات الحياة البرية «أسرار البرية». اكتب نصًا علميًا مشوقًا قصيرًا يُقرأ بصوت راوٍ واحد.
ابدأ خلال أول جملة أو أول 10 كلمات بدليل صادم أو خطر مباشر أو سؤال غامض يجعل المشاهد يريد معرفة الباقي. لا تبدأ بتمهيد عام مثل: في هذه القصة، منذ سنوات، أو دعونا نحكي.
اجعل الإيقاع سريعًا بجمل قصيرة وصور حسية واضحة، واحتفظ بأهم معلومة ناقصة حتى النهاية. لا تضع عنوانًا أو هاشتاغات أو تعليمات تصوير. لا تختلق معلومات عن الحيوان، ولا تقلّد أسلوب أي شخص.
اختم بسؤال محدد يدعو المشاهد لكتابة نظريته، ثم دعوة طبيعية لمتابعة الحلقة الوثائقية الكاملة."""
    user = f"""القصة: {series_title}
البارت: {episode.part_number}
نوع الـShort: {kind}
التوجيه: {instruction}

النص المرجعي من الحلقة (استخدم معناه فقط، ولا تنسخ أكثر من جملة قصيرة):
{source}

اكتب بين 80 و125 كلمة عربية فقط. اجعل أول جملة قابلة للاستخدام كHook مستقل، واجعل آخر جملة سؤالًا تفاعليًا واضحًا."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def word_count(text: str) -> int:
    return len(re.findall(r"\S+", text, flags=re.UNICODE))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.strip() + "\n", encoding="utf-8")


def episode_text_for_dry_run(episode: EpisodePlan) -> str:
    """Small placeholder used only to verify paths, plans, and workflow wiring."""
    return (
        "هذه مسودة اختبارية وليست نصًا للنشر. "
        f"البارت {episode.part_number} يحتاج إلى توليد فعلي من مزود كاتب النصوص."
    )


def build_series(
    settings: WriterSettings,
    *,
    story_id: str,
    requested_theme: str,
    language: str,
    start_after: datetime | None = None,
) -> SeriesPlan:
    """Create scripts and supporting metadata for one wildlife documentary episode."""
    story_id = sanitize_story_id(story_id)
    blueprint = dry_run_blueprint(story_id, language) if settings.dry_run else validate_blueprint(
        parse_json_response(request_chat(settings, build_blueprint_prompt(
            story_id=story_id,
            requested_theme=requested_theme,
            language=language,
        ), max_tokens=MAX_BLUEPRINT_COMPLETION_TOKENS))
    )
    plan = build_series_plan(
        story_id=story_id,
        series_title=blueprint["series_title"],
        language=blueprint["language"],
        estimated_total_words=blueprint["estimated_total_words"],
        start_after=start_after,
    )

    metadata_dir = settings.output_root / "production" / story_id
    scripts_long_dir = settings.output_root / "scripts" / "long"
    scripts_short_dir = settings.output_root / "scripts" / "shorts"
    write_text(metadata_dir / "story_bible.json", json.dumps(blueprint, ensure_ascii=False, indent=2))
    write_text(metadata_dir / "series_plan.json", json.dumps(plan.to_dict(), ensure_ascii=False, indent=2))

    previous_tail = ""
    for episode in plan.episodes:
        long_path = scripts_long_dir / f"{episode.id}.txt"
        script = episode_text_for_dry_run(episode) if settings.dry_run else request_chat(
            settings,
            build_episode_prompt(
                blueprint=blueprint,
                plan=plan,
                episode=episode,
                previous_tail=previous_tail,
            ),
            max_tokens=MAX_EPISODE_COMPLETION_TOKENS,
        )
        if not settings.dry_run:
            script = complete_underlength_episode(
                settings,
                plan=plan,
                episode=episode,
                script=script,
            )
            if word_count(script) < int(episode.target_words * MIN_EPISODE_COMPLETION_RATIO):
                raise RuntimeError(
                    f"{episode.id} is too short after continuations ({word_count(script)} words); expected at least "
                    f"{int(episode.target_words * MIN_EPISODE_COMPLETION_RATIO)}"
                )
        write_text(long_path, script)
        previous_tail = script[-2_500:]

        for short in episode.shorts:
            short_path = scripts_short_dir / f"{short.asset_id}.txt"
            short_script = (
                f"مسودة اختبارية لـ {short.kind}."
                if settings.dry_run
                else request_chat(
                    settings,
                    build_short_prompt(
                        script=script,
                        episode=episode,
                        series_title=plan.series_title,
                        kind=short.kind,
                        instruction=short.source_instruction,
                    ),
                    max_tokens=MAX_SHORT_COMPLETION_TOKENS,
                )
            )
            write_text(short_path, short_script)

    build_record = {
        "story_id": story_id,
        "series_title": plan.series_title,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "dry_run" if settings.dry_run else "provider_generated",
        "episode_count": plan.episode_count,
        "playlist_title": plan.playlist_title,
    }
    write_text(metadata_dir / "build_record.json", json.dumps(build_record, ensure_ascii=False, indent=2))
    return plan


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Write an original Rowat Alwaqe long-story season.")
    parser.add_argument("--story-id", default=os.getenv("STORY_ID", "case-001"))
    parser.add_argument("--theme", default=os.getenv("STORY_THEME", ""))
    parser.add_argument("--language", default=os.getenv("STORY_LANGUAGE", "auto"))
    parser.add_argument("--output-root", type=Path, default=Path(os.getenv("CONTENT_ROOT", "content")))
    parser.add_argument("--model", default=os.getenv("SCRIPTWRITER_MODEL", DEFAULT_MODEL))
    parser.add_argument("--base-url", default=os.getenv("SCRIPTWRITER_BASE_URL", DEFAULT_BASE_URL))
    parser.add_argument("--dry-run", action="store_true")
    return parser


def settings_from_args(args: argparse.Namespace) -> WriterSettings:
    if not args.dry_run and not os.getenv("SCRIPTWRITER_API_KEY", "").strip():
        raise ValueError("SCRIPTWRITER_API_KEY is missing")
    if not args.model.strip():
        raise ValueError("scriptwriter model cannot be empty")
    return WriterSettings(
        api_key=os.getenv("SCRIPTWRITER_API_KEY", "").strip(),
        base_url=args.base_url.strip(),
        model=args.model.strip(),
        output_root=args.output_root,
        dry_run=args.dry_run,
    )


def main(argv: list[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        settings = settings_from_args(args)
        plan = build_series(
            settings,
            story_id=args.story_id,
            requested_theme=args.theme,
            language=args.language,
        )
    except (ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}")
        return 2
    print(json.dumps({
        "story_id": plan.story_id,
        "series_title": plan.series_title,
        "episodes": plan.episode_count,
        "playlist_title": plan.playlist_title,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
