# Hikayatuna Kids Production Factory

مصنع خلفي آمن لقناة أطفال عربية أصلية للفئة 3–6 سنوات. هذا المستودع لا يحتوي على موقع أو لوحة تحكم؛ التشغيل يتم عبر Python CLI وGitHub Actions.

## الوضع الآمن الافتراضي

الهدف اليومي هو تجهيز حلقة مدتها 3 دقائق للمراجعة، وليس نشرها للعامة. القيم الافتراضية هي:

```text
KIDS_PRODUCTION_ENABLED=false
KIDS_PUBLISH_ENABLED=false
```

لا يتم استخدام أي مفتاح أو خدمة مدفوعة تلقائيًا، ولا يُعتبر Mock Provider مولدًا حقيقيًا للمحتوى.

## التشغيل

```bash
python -m unittest discover -s tests -v
python -m core.kids_factory --mode prepare --episode-id kids-ep-001
python -m core.kids_script_engine --episode-id kids-ep-001 --provider mock
```

ينتج التحضير:

```text
content/production/kids/kids-ep-001/manifest.json
content/production/kids/kids-ep-001/script.md
content/production/kids/kids-ep-001/storyboard.json
```

هذه ملفات تحضير وليست حلقة MP4 مكتملة. الإنتاج الفعلي يحتاج مزود كتابة وصوت وأصول مشاهد، ثم FFmpeg، ثم بوابة جودة وموافقة بشرية.

محرك النصوص يستخدم `mock` تلقائيًا عند غياب المفتاح. لتشغيل مزود OpenAI-compatible اختياريًا، يوضع المفتاح في Secret باسم `KIDS_TEXT_API_KEY` وتُضبط `KIDS_TEXT_PROVIDER` و`KIDS_TEXT_BASE_URL` و`KIDS_TEXT_MODEL`. لا يرسل المسار أي طلب خارجي في وضع Mock.

## الإنتاج السحابي المجاني بلا اشتراك

- صور المشاهد تُنشأ عبر AI Horde، وهي خدمة مجتمعية تطوعية تستخدم وحدات GPU يتبرع بها المشاركون. لا تحتاج بطاقة أو مفتاحًا مدفوعًا؛ يستخدم المشروع المفتاح المجهول الرسمي.
- الطلبات المجهولة لها أقل أولوية، وقد تنتظر أو تُرفض عند الضغط أو عدم توافر عامل مناسب. لا يوجد ضمان سرعة أو عدد غير محدود.
- الراوي يستخدم Fish Audio عبر النموذج `s2.1-pro-free` وصوت الراوي المحدد في `FISH_VOICE_MODEL_ID`. يلزم وضع `FISH_API_KEY` في GitHub Actions Secrets؛ لا تضع المفتاح داخل الملفات. هذا نموذج تقييم مجاني وليس استخدامًا غير محدودًا مضمونًا؛ إذا لم يكن متاحًا أو طلب رصيدًا، تتوقف المهمة ولا تنتقل تلقائيًا إلى نموذج مدفوع.
- تحريك الصور وتجميعها وإضافة الترجمة يتم على GitHub-hosted runners باستخدام FFmpeg؛ الناتج قصة مصورة بحركة كاميرا، وليس فيديو AI كامل الحركة للشخصيات.
- GitHub Actions له حدود استخدام مجانية تختلف حسب نوع المستودع والخطة. لا نفعّل تشغيلًا مجدولًا ولا ننشئ عمليات مدفوعة.
- لا توجد حاجة إلى Cloudflare أو Pollinations أو vidIQ في مسار الإنتاج. لا يتم استخدام نموذج Fish مدفوع تلقائيًا.
- أضف GitHub Actions Secret باسم `FISH_API_KEY` (ويمكن إضافة `FISH_VOICE_MODEL_ID` لتغيير الصوت). من Actions شغّل `Hikayatuna Kids - daily prepare`. اترك `prepare_only=true` للتحضير والاختبارات؛ اختر `false` لتوليد الحلقة. لا يوجد نشر عام تلقائي.

## المراحل المستهدفة

`idea → script → storyboard → scenes → Arabic voice → FFmpeg MP4 → Shorts → quality gate → owner approval → optional YouTube publish`

## القواعد

- العربية الفصحى المبسطة.
- العمر 3–6 سنوات.
- شخصيات أصلية ثابتة.
- منع العنف والرعب والجريمة والمحتوى غير المناسب.
- بصمة تمنع تكرار الحلقة أو الفكرة.
- لا نشر عام قبل موافقة مالك المشروع.
- الأسرار في GitHub Actions Secrets فقط، ولا توضع داخل المستودع.

## تحويل المستودع

تم الاحتفاظ بمسار قناة «رواة الواقع» داخل `.github/legacy-workflows-rowat-alwaqe/` كأرشيف، وتعطيل Workflows الخاصة به حتى لا يحدث نشر غير مقصود. راجع `KIDS_FACTORY_MIGRATION.md` لمعرفة ما تم تحويله وما بقي للتنفيذ.
