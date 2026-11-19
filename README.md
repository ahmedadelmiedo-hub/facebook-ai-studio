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
```

ينتج التحضير:

```text
content/production/kids/kids-ep-001/manifest.json
content/production/kids/kids-ep-001/script.md
content/production/kids/kids-ep-001/storyboard.json
```

هذه ملفات تحضير وليست حلقة MP4 مكتملة. الإنتاج الفعلي يحتاج مزود كتابة وصوت وأصول مشاهد، ثم FFmpeg، ثم بوابة جودة وموافقة بشرية.

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
