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

## الإنتاج السحابي المجاني

- صور المشاهد تُنشأ عبر Cloudflare Workers AI باستخدام `@cf/black-forest-labs/flux-1-schnell`؛ لا توجد نماذج تُنزّل أو تعمل على جهاز المستخدم.
- الراوي يستخدم Edge TTS المستضاف بصوت مصري رجالي `ar-EG-ShakirNeural`. إذا تعذّر الاتصال، تتوقف المهمة بدل استخدام صوت محلي منخفض الجودة.
- تحريك الصور وتجميعها وإضافة الترجمة يتم على GitHub-hosted runners باستخدام FFmpeg. هذا إخراج قصصي متحرك بحركة كاميرا على الصور، وليس توليد فيديو AI بحركة كاملة للشخصيات.
- حصة Cloudflare Workers AI المجانية المنشورة هي 10,000 Neurons يوميًا، وتُعاد عند 00:00 UTC؛ عند نفادها تفشل الطلبات بدل التحويل التلقائي إلى خطة مدفوعة. راجع [التسعير الرسمي](https://developers.cloudflare.com/workers-ai/platform/pricing/).
- يلزم إعداد GitHub Actions Secrets باسمَي `CLOUDFLARE_ACCOUNT_ID` و`CLOUDFLARE_API_TOKEN` (صلاحية Workers AI). لا تُحفظ المفاتيح في الملفات أو السجلات.
- من Actions شغّل `Hikayatuna Kids - daily prepare`. اترك `prepare_only=true` للتحضير والاختبارات فقط؛ اختر `false` لتوليد الحلقة الخاصة. لا يوجد نشر عام تلقائي.
- لم يعد هناك تشغيل مجدول يومي يستهلك موارد دون طلب، ولا يتم استدعاء vidIQ في هذا المسار.

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
