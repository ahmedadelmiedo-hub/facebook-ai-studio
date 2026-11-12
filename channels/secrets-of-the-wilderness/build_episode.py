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

prompt = f'''أنت كاتب ومحرر علمي لوثائقيات الحياة البرية. اكتب حلقة عربية أصلية لقناة {CONFIG['channel_name']}.
العنوان: {episode['title']}. الموضوع: {episode['topic']}.
الجمهور: عام عربي. الأسلوب: وثائقي مشوق ممزوج بسرد قصصي، بصوت راوٍ رجالي طبيعي.

شرط الطول الإلزامي:
- اكتب من 1300 إلى 1550 كلمة عربية منطوقة في قسم عنوانه حرفيًا: ## النص الكامل للتعليق الصوتي.
- هذا القسم وحده يحتوي السرد الكامل مقسمًا إلى 8 مشاهد مترابطة، وليس ملخصًا أو نقاطًا.
- لا تحتسب خطة الصورة أو المصادر أو أفكار Shorts ضمن عدد الكلمات.
- لا تحشو ولا تكرر للوصول إلى الطول.

قواعد الدقة العلمية:
1) ممنوع اختراع أسماء أنواع أو سلوكيات أو أرقام أو اقتباسات. لا تستخدم أسماء تبدو علمية بلا مصدر.
2) عند ذكر نوع محدد، اكتب اسمه العربي واسمه العلمي اللاتيني الصحيح. إن لم تتأكد، استخدم وصفًا عامًا ولا تخترع اسمًا.
3) لا تعمم صفة نوع واحد على كل المجموعة. فرّق بين الليلي والشفقِي، وبين الضوء الخافت والظلام المطلق.
4) لا تذكر أرقامًا أو نسبًا إلا بمصدر محدد. ممنوع ادعاء "مئات الروائح في الثانية".
5) لا تصف مسارات النمل بأنها خطوط فوسفاتية مضيئة، ولا تخلط بين الصقور والحمام أو بين أنواع القرود.
6) استخدم الحقائق المرجعية التالية بدقة:
- الخفافيش تستخدم تحديد الموقع بالصدى؛ تصدر أصواتًا وتستقبل أصداءها لتقدير مواقع الأجسام والفرائس.
- كثير من البوم يصطاد ليلًا ويعتمد على السمع والرؤية في الضوء الخافت. ريش بعض الأنواع يقلل صوت الطيران. لا تقل إنها ترى في ظلام مطلق.
- آي آي (Daubentonia madagascariensis) ليمور ليلي؛ تذكر National Geographic أنه الرئيسيات المعروف الوحيد الذي يستخدم تحديد الموقع بالصدى للعثور على الفرائس. انسب المعلومة للمصدر ولا توسعها.
- التارسير له عيون كبيرة جدًا نسبةً إلى حجم الجسم وفق متحف التاريخ الطبيعي البريطاني.
- ثعلب الفنك (Vulpes zerda) متكيف مع النشاط الليلي في الصحراء، وأذناه تساعدانه على التقاط الأصوات وتبديد الحرارة؛ لا تقدمه كحيوان غابة.
- تنشط حيوانات ليلًا لأسباب مختلفة، منها تجنب حرارة النهار أو البحث عن الغذاء أو التزاوج أو تفادي المفترسات؛ لا تجعل سببًا واحدًا قاعدة عامة.
7) ميّز بين الحقيقة الموثقة والتشبيه الأدبي.
8) أدرج 5 إلى 6 مصادر من القائمة التالية فقط، مع رابط كامل ومعلومة يسندها. لا تخترع مراجع أو روابط:
- National Geographic, Nocturnal animals, explained: https://www.nationalgeographic.com/animals/article/nocturnal-animals-explained
- National Geographic, How Echolocation Lets Animals—and Some Humans—Navigate by Sound: https://www.nationalgeographic.com/animals/article/echolocation-is-nature-built-in-sonar-here-is-how-it-works
- National Geographic, Owls, facts and information: https://www.nationalgeographic.com/animals/birds/facts/owls
- Natural History Museum, Superior senses in the dark: https://www.nhm.ac.uk/discover/superior-senses-in-the-dark.html
- Oxford Academic, Evolution and Ecology of Silent Flight in Owls and Other Flying Vertebrates: https://academic.oup.com/iob/article/2/1/obaa001/5709817
- U.S. National Park Service, Animals Need the Dark: https://www.nps.gov/articles/nocturnal_earthnight.htm

بنية المخرجات:
## النص الكامل للتعليق الصوتي
ثمانية مشاهد كاملة، 1300-1550 كلمة منطوقة، افتتاحية قوية وخاتمة مؤثرة.
## خطة المشاهد والصورة
وصف بصري قابل للتنفيذ ونص قصير على الشاشة لكل مشهد.
## أفكار Shorts
ثلاث أفكار مشتقة من الحلقة.
## المصادر العلمية
المصدر والرابط والمعلومة التي يسندها.
## ملاحظات المراجعة
أي معلومة تحتاج تحققًا، مع التأكيد أن النص غير معتمد للنشر تلقائيًا.
'''

payload = json.dumps({
    "model": model,
    "messages": [{"role": "user", "content": prompt}],
    "temperature": 0.3,
    "max_completion_tokens": 16000,
    "reasoning_effort": "low",
    "include_reasoning": False,
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

import re

voice_match = re.search(
    r"##\s*النص الكامل للتعليق الصوتي\s*(.*?)(?=\n##\s|\Z)",
    script,
    flags=re.DOTALL,
)
if not voice_match:
    raise SystemExit("Quality gate failed: missing full narration section. No output files were written.")

voice_text = re.sub(r"^#+.*$", " ", voice_match.group(1), flags=re.MULTILINE)
voice_words = re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", voice_text, flags=re.UNICODE)
word_count = len(voice_words)

# Retry expansion more than once. The first attempt returned 848 words,
# so a single retry is not sufficient for the required 1300-1700-word narration.
for attempt in range(1, 4):
    if 1300 <= word_count <= 1700:
        break
    print(
        f"Narration length is {word_count} words; "
        f"requesting expansion attempt {attempt}/3."
    )
    repair_prompt = (
        prompt
        + "\n\nمهم جدًا: النص السابق لم يحقق شرط الطول. وسّع النص السابق نفسه توسعة حقيقية "
        + "ولا تلخصه أو تعِد إنتاج نسخة أقصر. المطلوب أن يصبح قسم التعليق الصوتي وحده "
        + "بين 1400 و1550 كلمة عربية منطوقة. حافظ على المشاهد الثمانية، واجعل كل مشهد "
        + "مفصلًا بما يكفي (نحو 175-190 كلمة). أضف شرحًا علميًا وسردًا ومواقف وصفية "
        + "مفيدة دون تكرار أو حشو، ولا تغيّر الحقائق أو المصادر. أخرج الحزمة كاملة "
        + "بكل العناوين الخمسة المطلوبة، وليس التعليق الصوتي وحده."
        + f"\n\nعدد كلمات المحاولة السابقة وفق الفاحص: {word_count}."
        + "\n\nالنص السابق المطلوب توسيعه:\n"
        + script
    )
    retry_payload = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": repair_prompt}],
        "temperature": 0.35,
        "max_completion_tokens": 20000,
        "reasoning_effort": "low",
        "include_reasoning": False,
    }, ensure_ascii=False).encode("utf-8")
    retry_request = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=retry_payload,
        headers={
            "Authorization": "Bearer " + API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "secrets-of-the-wilderness/1.4",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(retry_request, timeout=300) as response:
            retry_data = json.loads(response.read().decode("utf-8"))
        retry_choice = retry_data["choices"][0]
        retry_script = (retry_choice["message"].get("content") or "").strip()
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(
            f"Groq expansion attempt {attempt} failed (HTTP {exc.code}): {details[:3000]}"
        ) from None
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise SystemExit(f"Groq expansion attempt {attempt} failed: {exc}") from None

    if not retry_script:
        raise SystemExit(
            f"Groq expansion attempt {attempt} returned empty content; "
            "no output files were written."
        )

    data = retry_data
    choice = retry_choice
    script = retry_script
    voice_match = re.search(
        r"##\s*النص الكامل للتعليق الصوتي\s*(.*?)(?=\n##\s|\Z)",
        script,
        flags=re.DOTALL,
    )
    if not voice_match:
        raise SystemExit(
            f"Quality gate failed after expansion attempt {attempt}: "
            "missing narration section. No output files were written."
        )
    voice_text = re.sub(r"^#+.*$", " ", voice_match.group(1), flags=re.MULTILINE)
    voice_words = re.findall(r"[^\W_]+(?:[’'-][^\W_]+)*", voice_text, flags=re.UNICODE)
    word_count = len(voice_words)
    print(f"Expansion attempt {attempt} narration length: {word_count} words.")

if word_count < 1300 or word_count > 1700:
    raise SystemExit(
        f"Quality gate failed after 3 expansion attempts: narration has {word_count} words; "
        "expected 1300-1700. No output files were written."
    )

required_sections = [
    "## خطة المشاهد والصورة",
    "## أفكار Shorts",
    "## المصادر العلمية",
    "## ملاحظات المراجعة",
]
missing_sections = [heading for heading in required_sections if heading not in script]
if missing_sections:
    raise SystemExit("Quality gate failed: missing sections: " + ", ".join(missing_sections))

source_section = script.split("## المصادر العلمية", 1)[1].split("## ملاحظات المراجعة", 1)[0]
source_urls = re.findall(r"https?://[^\s)]+", source_section)
if len(source_urls) < 4:
    raise SystemExit(f"Quality gate failed: only {len(source_urls)} source links found; minimum is 4.")

print(f"Quality gate passed: {word_count} narration words and {len(source_urls)} source links.")

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
    "narration_word_count": word_count,
    "source_link_count": len(source_urls),
    "quality_gate": "passed",
}
metadata_path.write_text(
    json.dumps(metadata, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)

print(f"Created script: {script_path.relative_to(ROOT)}")
print(f"Created metadata: {metadata_path.relative_to(ROOT)}")
print("Human review is required before publishing.")
