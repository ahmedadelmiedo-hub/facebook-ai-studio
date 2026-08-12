# Rowat Alwaqe Production Studio

منظومة Python خفيفة لإنتاج **روايات عربية مسموعة** لقناة [رواة الواقع](https://www.youtube.com/@RowatAlwaqe). تستخدم المنظومة صوت Fish Audio، وتفصل بين الحلقة الطويلة التي تبني عودة المشاهد، وShorts التي تقود المشاهد إلى الحلقة الكاملة.

> المشروع الآن مصمم كخط إنتاج تلقائي: يكتب النظام قصة تحقيق أصلية، يحدد عدد البارتات وموعد كل بارت، ينشئ Playlist مستقلة ومواد Shorts مشتقة، ثم يولّد الصوت والفيديو ويرفعه إلى YouTube بموعد نشر مجدول. الـShort السابق كان اختبارًا تقنيًا فقط، وليس نموذج المحتوى النهائي.

## ما الذي يدعمه المشروع؟

| المسار | المقاس | الاستخدام |
|---|---:|---|
| `long` | 1920×1080 | حلقة رواية طويلة على YouTube، مستهدفة بـ25–45 دقيقة. |
| `short` | 1080×1920 | Hook قصير يثير الفضول ويقود إلى الحلقة الطويلة. |

ينشئ المولد MP4 وسجل JSON بلا أسرار يحتوي على العنوان ونوع الفيديو ووقت التوليد. ويقسّم نصوص الروايات الطويلة إلى مقاطع TTS قبل دمجها لتقليل فشل الطلبات الطويلة. تُحفظ الوسائط في `storage/autopilot/`، بينما تُحفظ النصوص وخطة النشر وحالة YouTube في `content/production/` حتى لا يكرر النظام الرفع.

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
| `SCRIPTWRITER_API_KEY` | مفتاح مزود LLM متوافق مع OpenAI لكتابة النصوص على GitHub Actions. |
| `YOUTUBE_CLIENT_ID` | OAuth Client ID من Google Cloud. |
| `YOUTUBE_CLIENT_SECRET` | OAuth Client Secret من Google Cloud. |
| `YOUTUBE_REFRESH_TOKEN` | Refresh token الناتج من تفويض قناة @RowatAlwaqe مرة واحدة. |

## بنية المحتوى

```text
content/
├── story_queue.json               # طابور القصص واللغة والأنواع المسموح بها
├── series_manifest.json            # تعريف السلسلة القديمة ومؤشرات القياس
├── scripts/
│   ├── long/                      # نصوص البارتات الطويلة التي كتبها النظام
│   └── shorts/                    # Hook ومقطع منتصف وCliffhanger لكل بارت
└── production/<story-id>/
    ├── story_bible.json            # مخطط القصة والشخصيات والأدلة
    ├── series_plan.json            # عدد البارتات والمواعيد وPlaylist
    └── publication_state.json      # IDs وحالة الرفع لمنع التكرار
```

لا يحتاج المستخدم إلى كتابة النص يدويًا. يقرأ `core/script_writer.py` الفكرة من `content/story_queue.json`، ويكتب رواية أصلية في التحقيق البوليسي والغموض والجريمة والاستخبارات، ثم ينشئ ملفات النصوص وخطة الإنتاج.

## التشغيل المحلي

شغّل الاختبارات أولًا:

```bash
python -m unittest discover -s tests -v
```

تحقق من إنشاء خطة قصة وملفاتها بلا اتصال خارجي:

```bash
python core/automation.py --dry-run
```

ولتشغيل مهمة يومية محددة التاريخ في اختبار التخطيط:

```bash
python core/automation.py --dry-run --date 2026-08-13T12:00:00Z
```

أما التوليد الحقيقي فيحتاج إلى `FISH_API_KEY` و`FISH_VOICE_ID` و`SCRIPTWRITER_API_KEY` وبيانات YouTube. عند تشغيل المهمة اليومية، يختار النظام الأصل المستحق من الخطة، ويولّد الصوت والفيديو، ثم يرفع الحلقة الطويلة وShorts الخاصة بيومها. لا يلزم تمرير `--review-status` يدويًا في المسار التلقائي؛ فالنص يمر أولًا بفحوص البنية والطول والحقوق قبل أن يضعه المشغل في حالة إنتاج.

## GitHub Actions

يشغّل Workflow **رواة الواقع - الإنتاج والنشر التلقائي** مرة يوميًا. يستيقظ المشغل في الساعة 06:00 بتوقيت القاهرة تقريبًا، بينما يحدد `series_plan.json` الموعد الدقيق لكل أصل؛ لذلك لا يعتمد النظام على تخمين المنطقة الزمنية داخل GitHub Actions. في كل تشغيل يكتب القصة عند الحاجة، يختار البارت أو الـShort المستحق، ينتج الوسائط، يرفع الفيديو بموعده، ينشئ Playlist القصة إن لم تكن موجودة، ثم يحفظ IDs في `publication_state.json`.

يمكن تشغيله يدويًا مع `dry_run=true` لفحص الخطة والملفات فقط. النشر الفعلي يحتاج `YOUTUBE_REFRESH_TOKEN` بالإضافة إلى Client ID وClient Secret؛ الـRefresh token هو تفويض قناة @RowatAlwaqe وليس Service Account.

## قياس أسبوع العودة

سجّل هذه الأرقام من YouTube Studio بعد 7 أيام: `Impressions` و`CTR` و`Average view duration` و`First 30 seconds retention` و`Returning viewers` و`Subscribers gained`. استخدمها لاتخاذ قرار الحلقة التالية والعناوين والـShorts، لا لمضاعفة النشر عشوائيًا.
