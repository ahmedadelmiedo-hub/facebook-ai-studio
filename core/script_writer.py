"""Write original, long Arabic investigative-fiction series for Rowat Alwaqe.

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
    """Build the prompt that establishes an original fictional series before writing it."""
    system = """أنت كاتب روايات عربي محترف لقناة يوتيوب اسمها «رواة الواقع».
اكتب قصصًا خيالية أصلية فقط في التحقيق البوليسي والغموض والجريمة والاستخبارات.
لا تقلّد أسلوب أي كاتب أو راوٍ أو قناة معروفة، ولا تنقل من قصة قائمة أو قضية حقيقية، ولا تستخدم أسماء أشخاص حقيقيين. لا تشرح أو تصف كيفية تنفيذ جريمة أو إخفاء آثارها. ابتعد عن العنف الدموي الصريح.
القصص موجهة للقراءة الصوتية: راوٍ مباشر، مشاهد إنسانية، أدلة متدرجة، حوار قصير طبيعي، إيقاع متصاعد، وكل جزء ينتهي بانعطافة لا تكشف الحل.
أعد JSON فقط وبالمفاتيح المطلوبة دون Markdown."""
    user = f"""أنشئ مخططًا أصليًا لسلسلة تحقيق طويلة.
معرّف السلسلة: {story_id}
الفكرة الأولية: {requested_theme or 'قضية غامضة في مدينة مصرية معاصرة'}
تفضيل اللغة: {language or 'اختر بين الفصحى المعاصرة والعامية المصرية المفهومة حسب القصة'}

أعد JSON يطابق هذا الشكل:
{{
  "series_title": "عنوان قصير وجذاب",
  "language": "الفصحى المعاصرة أو العامية المصرية المبسطة",
  "estimated_total_words": 16000,
  "logline": "جملة واحدة",
  "setting": "المكان والزمن",
  "protagonist": "وصف الراوي/المحقق",
  "core_mystery": "السؤال المحرك للقصة",
  "stakes": "ما الذي سيخسره البطل",
  "suspects": ["مشتبه به 1", "مشتبه به 2", "مشتبه به 3"],
  "evidence_ladder": ["دليل 1", "دليل 2", "دليل 3", "دليل 4", "دليل 5"],
  "final_reveal": "حل أصلي عادل لا يظهر قبل الجزء الأخير",
  "tone": "وصف الإيقاع",
  "content_warning": "تنبيه قصير إن لزم أو سلسلة فارغة"
}}

يجب أن تكون estimated_total_words بين 12000 و36000، مع مساحة كافية لحلقات طويلة لا لقصص قصيرة."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def validate_blueprint(data: dict[str, Any]) -> dict[str, Any]:
    """Validate provider output before it becomes a production plan."""
    required_strings = (
        "series_title",
        "language",
        "logline",
        "setting",
        "protagonist",
        "core_mystery",
        "stakes",
        "final_reveal",
        "tone",
    )
    for key in required_strings:
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise RuntimeError(f"blueprint is missing {key}")
    words = data.get("estimated_total_words")
    if not isinstance(words, int) or not 12_000 <= words <= 36_000:
        raise RuntimeError("blueprint estimated_total_words must be between 12000 and 36000")
    for key in ("suspects", "evidence_ladder"):
        if not isinstance(data.get(key), list) or len(data[key]) < 3:
            raise RuntimeError(f"blueprint must include at least three values for {key}")
    warning = data.get("content_warning", "")
    if not isinstance(warning, (str, list)):
        raise RuntimeError("blueprint content_warning has an unsupported type")
    return data


def dry_run_blueprint(story_id: str, language: str) -> dict[str, Any]:
    """Provide deterministic content for offline validation without claiming it is a final script."""
    return {
        "series_title": "ملف الرصد 17",
        "language": language if language and language != "auto" else "العامية المصرية المبسطة",
        "estimated_total_words": 16_000,
        "logline": "محقق سابق يتلقى تسجيلاً صوتيًا يكشف أن قضية أغلقها منذ سنوات لم تكن كما ظن.",
        "setting": "القاهرة المعاصرة بين حي قديم ومقر أرشيف مهمل",
        "protagonist": "آدم، محقق سابق يعاني من أثر قرار قديم",
        "core_mystery": "من أرسل التسجيل، ولماذا عاد رقم القضية بعد سبع سنوات؟",
        "stakes": "إذا أخطأ آدم مرة أخرى سيتهم شخص بريء وتضيع فرصة إنصاف الضحية.",
        "suspects": ["زميل قديم", "صحفية أرشيف", "شاهد اختفى"],
        "evidence_ladder": ["تسجيل مجهول", "تاريخ مزور", "كاميرا معطلة", "دفتر مفقود", "اسم داخل الأرشيف"],
        "final_reveal": "الحل يكشف دافعًا إنسانيًا معقدًا ويعالج كل الأدلة السابقة بعدل.",
        "tone": "هادئ ومريب ثم متسارع مع نهاية كل بارت",
        "content_warning": "",
    }


def chapter_role(part_number: int, episode_count: int) -> str:
    """Describe the narrative work required of each chapter."""
    if part_number == 1:
        return "الافتتاح: جريمة أو دليل صادم، تعريف البطل، وسؤال مركزي قوي من أول دقيقة."
    if part_number == episode_count:
        return "الختام: ربط جميع الأدلة وكشف الحقيقة بعدل، مع خاتمة عاطفية مكتملة ودعوة لمشاركة الانطباع."
    if part_number == episode_count - 1:
        return "ما قبل الحل: انهيار النظرية السائدة وظهور دليل يقلب معنى كل ما سبق."
    return "التصعيد: كشف دليل جديد، توسيع دائرة الشك، وإجبار البطل على دفع ثمن شخصي قبل Cliffhanger."


def build_episode_prompt(
    *,
    blueprint: dict[str, Any],
    plan: SeriesPlan,
    episode: EpisodePlan,
    previous_tail: str,
) -> list[dict[str, str]]:
    """Ask for spoken Arabic narration for exactly one long part."""
    system = """أنت تكتب نصًا صوتيًا طويلًا أصليًا لرواية تحقيق عربية خيالية.
أعد النص الذي سيقرأه راوي واحد بصوته مباشرة، بلا عناوين، بلا Markdown، وبلا أي ملاحظات للمخرج أو للممثل. اجعل السرد متصلًا وسهل النطق باللهجة/الفصحى المطلوبة. استخدم فقرات قصيرة وحوارًا محدودًا بصيغة الراوي مثل: «قال لي...» بدلاً من تغيير صوت المتحدثين.
لا تذكر أن النص مولد أو أنك ذكاء اصطناعي. لا تقلّد أسلوب أي شخص أو قناة. لا تحوّل الجريمة إلى تعليمات عملية ولا تتضمن عنفًا دمويًا تفصيليًا. لا تكشف حل القضية قبل موعده.
يجب أن تحتوي الحلقة على فاصل تفاعل واحد فقط، مدمج طبيعيًا داخل السرد، يدعو المشاهد أن يكتب توقعه حول دليل أو مشتبه به، ويطلب الإعجاب والاشتراك لاستكمال التحقيق. لا تستخدم عبارة «فاصل إعلاني» ولا تكسر الجو."""
    bible = json.dumps(blueprint, ensure_ascii=False)
    previous_context = previous_tail or "هذه هي الحلقة الأولى ولا يوجد سياق سابق."
    user = f"""اكتب البارت {episode.part_number} من {plan.episode_count} لرواية «{plan.series_title}».
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
    system = """أنت تكمل نصًا صوتيًا عربيًا أصليًا لرواية تحقيق خيالية.
أعد الاستكمال فقط، بلا عنوان أو تلخيص أو Markdown أو ملاحظات. أكمل من آخر جملة بسلاسة وباللغة نفسها، واحتفظ بالراوي الواحد والإيقاع المتصاعد. لا تكشف الحل النهائي ولا تقلّد أسلوب أي شخص، ولا تقدّم تعليمات لتنفيذ جريمة. لا تُنهِ البارت قبل أن تضيف مشاهد وأدلة وحوارًا قصيرًا كافيًا."""
    user = f"""هذه متابعة للبارت {episode.part_number} من {plan.episode_count} في رواية «{plan.series_title}».
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
    system = """أنت كاتب Shorts عربي لقناة روايات تحقيق. اكتب نصًا أصليًا قصيرًا يُقرأ بصوت راوٍ واحد.
لا تضع عنوانًا أو هاشتاغات أو تعليمات تصوير. لا تكشف الجاني أو الحل. لا تقلّد أسلوب أي شخص. النهاية يجب أن تقود المشاهد إلى الحلقة الكاملة أو الـPlaylist بعبارة طبيعية."""
    user = f"""القصة: {series_title}
البارت: {episode.part_number}
نوع الـShort: {kind}
التوجيه: {instruction}

النص المرجعي من الحلقة (استخدم معناه فقط، ولا تنسخ أكثر من جملة قصيرة):
{source}

اكتب بين 80 و125 كلمة عربية فقط."""
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


def build_series(settings: WriterSettings, *, story_id: str, requested_theme: str, language: str) -> SeriesPlan:
    """Create all scripts and supporting metadata for one original story series."""
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
