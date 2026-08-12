"""Create a launch-ready first episode without consuming the Groq quota.

This one-off recovery utility uses the configured sandbox OpenAI-compatible proxy to
prepare the first original script and its production metadata.  The ordinary GitHub
workflow can then render and publish the existing asset through Fish Audio and YouTube.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from core.story_planner import build_series_plan

CONTENT = ROOT / "content"
STORY_ID = "case-001"
SERIES_TITLE = "تسجيلات الغرفة رقم 17"

SYSTEM_PROMPT = """أنت كاتب عربي محترف لروايات التحقيق الصوتية الأصلية لقناة يوتيوب عربية.
اكتب بالعربية الفصحى السهلة، بصوت راوٍ واحد دافئ ومباشر، وبإيقاع مشوق يناسب الاستماع.
يجب أن تكون القصة خيالية أصيلة بالكامل: لا قضايا حقيقية، ولا أسماء مشاهير، ولا تقليد لأي كاتب أو قناة.
اكتب جُملاً عربية فصيحة طبيعية وواضحة، وتجنب الاستعارات المبالغ فيها والعبارات الغامضة أو الركيكة.
لا تضع عناوين فرعية ولا مقدمات تفسيرية ولا ملاحظات إنتاج؛ أخرج نص الراوي فقط."""

USER_PROMPT = """اكتب نص الحلقة الأولى كاملاً من رواية تحقيق بوليسية متسلسلة بعنوان «تسجيلات الغرفة رقم 17».
الفكرة: يستلم المحقق السابق نادر سالم تسجيلاً صوتياً من رقم مجهول مرتبطاً بقضية قتل أغلقها قبل سبع سنوات. يبدأ التسجيل بصوت الضحية التي يفترض أنها ماتت، ويكشف أن الدليل الذي برّأ المشتبه به الوحيد كان مزوراً.

متطلبات صارمة:
- النص بين 2800 و3300 كلمة عربية تقريباً، ليكون حلقة طويلة حقيقية لا Hook قصيراً.
- افتتح بجملة صادمة تدفع المستمع لإكمال الحلقة، ثم قدّم نادر وسبب خروجه من الشرطة وتفاصيل القضية القديمة «قضية الغرفة رقم 17» تدريجياً.
- ابنِ الغموض بالقرائن والمشاهد والحوار المنقول بصيغة الراوي، وليس بالملخصات العامة.
- لا تكشف القاتل ولا الحل النهائي؛ اختم بكشف يغيّر مسار التحقيق ويجعل الجزء الثاني ضرورياً.
- أدرج مرة واحدة فقط، قرب منتصف النص، فاصلاً تفاعلياً سلساً من الراوي يدعو المستمع لكتابة نظريته والإعجاب والاشتراك دون كسر الجو.
- اجعل النص آمناً لمنصة عامة: بلا أوصاف دموية فجّة أو عنف تفصيلي.
- لا تقل «في هذه الحلقة» أو «في الجزء التالي» أو «لن أذكره الآن» ولا تذكر أنك نموذج أو كاتب. لا تشرح أسلوبك أو خياراتك. أخرج النص السردي النهائي فقط."""


def generate_script() -> str:
    base = os.environ["OPENAI_API_BASE"].rstrip("/")
    key = os.environ["OPENAI_API_KEY"]
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={
            "model": "gpt-5",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": USER_PROMPT},
            ],
            "max_completion_tokens": 8000,
            "reasoning": {"effort": "low"},
        },
        timeout=240,
    )
    response.raise_for_status()
    payload = response.json()
    text = payload["choices"][0]["message"].get("content") or ""
    text = text.strip()
    if len(text.split()) < 2200:
        raise RuntimeError("alternate writer returned an underlength first episode")
    return text


def main() -> None:
    script = generate_script()
    production = CONTENT / "production" / STORY_ID
    script_path = production / "scripts" / "long" / f"{STORY_ID}-EP01.txt"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script + "\n", encoding="utf-8")

    plan = build_series_plan(
        story_id=STORY_ID,
        series_title=SERIES_TITLE,
        language="ar",
        estimated_total_words=16000,
        start_after=datetime.now(UTC),
    )
    (production / "series_plan.json").write_text(
        json.dumps(plan.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (production / "build_record.json").write_text(
        json.dumps(
            {
                "story_id": STORY_ID,
                "mode": "prebuilt_alternate_provider",
                "writer": "sandbox-openai-compatible/gpt-5",
                "created_at": datetime.now(UTC).isoformat(),
                "note": "First episode staged during a temporary Groq TPD quota exhaustion.",
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"script": str(script_path), "words": len(script.split()), "plan": str(production / "series_plan.json")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
