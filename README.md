# Rowat Alwaqe Production Studio

منظومة Python خفيفة لإنتاج **روايات عربية مسموعة** لقناة [رواة الواقع](https://www.youtube.com/@RowatAlwaqe). تستخدم المنظومة صوت Fish Audio، وتفصل بين الحلقة الطويلة التي تبني عودة المشاهد، وShorts التي تقود المشاهد إلى الحلقة الكاملة.

> المشروع **لا ينشر تلقائيًا على YouTube**. كل توليد يحتاج نصًا أصليًا أو مرخّصًا، مراجعة يدوية، واختيار `approved` صراحةً. الناتج يرفع كـGitHub Artifact فقط للمراجعة والتنزيل.

## ما الذي يدعمه المشروع؟

| المسار | المقاس | الاستخدام |
|---|---:|---|
| `long` | 1920×1080 | حلقة رواية طويلة على YouTube، مستهدفة بـ25–45 دقيقة. |
| `short` | 1080×1920 | Hook قصير يثير الفضول ويقود إلى الحلقة الطويلة. |

ينشئ المولد MP4 وسجل JSON بلا أسرار يحتوي على العنوان ونوع الفيديو وحالة المراجعة ووقت التوليد. تُحفظ النتائج في `storage/autopilot/` ولا تُرفع إلى Git.

## المتطلبات

استخدم Python 3.11 أو أحدث:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

ستحتاج أيضًا إلى FFmpeg محليًا إذا لم يوفّره تثبيت MoviePy تلقائيًا.

## الأسرار

أضف هذه القيم كـRepository Secrets في GitHub، ولا تضع أي قيمة حقيقية داخل الكود أو ملفات المشروع.

| Secret | الاستخدام |
|---|---|
| `FISH_API_KEY` | مصادقة Fish Audio. |
| `FISH_VOICE_ID` | Voice ID المعتمد لصوت القناة. |

## بنية المحتوى

```text
content/
├── series_manifest.json           # السلسلة والعناوين ومؤشرات القياس
└── scripts/
    ├── long/EP01.template.md      # قالب كتابة ومراجعة الحلقة الطويلة
    └── shorts/README.md           # بنية hooks ومقاطع Shorts
```

اكتب النص النهائي المعتمد في ملف `.txt` داخل `content/scripts/long/` أو `content/scripts/shorts/`. لا تمرر ملفات القوالب Markdown مباشرة إلى المولد.

## التشغيل المحلي

شغّل الاختبارات أولًا:

```bash
python -m unittest discover -s tests -v
```

تحقق من إعدادات حلقة طويلة بلا اتصال خارجي:

```bash
FISH_VOICE_ID=local-test python core/autopilot.py \
  --dry-run \
  --format long \
  --review-status approved \
  --episode-name EP01
```

بعد اعتماد نص أصلي أو مرخّص، شغّل التوليد الحقيقي:

```bash
python core/autopilot.py \
  --script-file content/scripts/long/EP01.txt \
  --episode-name EP01 \
  --title "رسالة من بيت النخيل | البارت 1 | رواية عربية مسموعة" \
  --format long \
  --review-status approved
```

استخدم `--format short` مع ملف hook معتمد لإنتاج Short رأسي. سيوقف المولد أي محاولة توليد فعلية ما لم تكن حالة المراجعة `approved`.

## GitHub Actions

شغّل workflow **رواة الواقع - مراجعة وإنتاج** يدويًا من تبويب **Actions**. اختر نوع الفيديو، واسم الحلقة، ومسار النص، والعنوان، ثم اختر `approved` فقط بعد اكتمال المراجعة القانونية والتحريرية. يبدأ workflow باختبارات الوحدة، ويتحقق من أن النص داخل مجلدات المحتوى المعتمدة، ثم ينشئ Artifact قابلًا للتنزيل لمدة 7 أيام.

لا يوجد في هذه المرحلة ربط نشر آلي بـYouTube. هذا مقصود لحماية جودة العودة إلى القناة حتى نراجع أول الحلقات ونتائج أول أسبوع.

## قياس أسبوع العودة

سجّل هذه الأرقام من YouTube Studio بعد 7 أيام: `Impressions` و`CTR` و`Average view duration` و`First 30 seconds retention` و`Returning viewers` و`Subscribers gained`. استخدمها لاتخاذ قرار الحلقة التالية والعناوين والـShorts، لا لمضاعفة النشر عشوائيًا.
