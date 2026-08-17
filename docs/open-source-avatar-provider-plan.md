# خطة دمج مزود Avatar مفتوح المصدر بدل D-ID

## الخلاصة التنفيذية

البديل الأنسب لشخصية نور هو **SadTalker** لأنه يقبل صورة شخصية واحدة وملفًا صوتيًا ويُخرج فيديو Talking Head، وهو الشكل المطابق مباشرةً لواجهة D-ID الحالية. يذكر المستودع الرسمي أن الترخيص الأساسي Apache 2.0، مع ضرورة مراجعة تراخيص المكونات الخارجية قبل الاستخدام التجاري النهائي [1] [2].

أما **MuseTalk** فهو خيار قوي لمزامنة الشفاه، لكنه يتعامل عمليًا مع فيديو أساس ثم يعدّل منطقة الوجه وفق الصوت؛ لذلك يحتاج إلى مرحلة إضافية لإنشاء فيديو أداء أساسي لنور. ترخيص كود MuseTalk MIT، لكن الأوزان والمكونات التابعة يجب فحصها بحسب ما ستوزعونه أو تستخدمونه [3] [4].

لا أوصي بـWav2Lip للقناة التجارية من دون ترخيص منفصل، لأن المستودع الرسمي يضع النسخة المفتوحة ضمن الاستخدام البحثي/الأكاديمي/الشخصي ويمنع الاستخدام التجاري [5].

## المقارنة

| المقاربة | المدخل | الجودة المتوقعة | التكلفة لكل فيديو | التعقيد | القيد الرئيسي |
|---|---|---:|---:|---:|---|
| SadTalker محلي | صورة نور + WAV | حركة رأس وتعبيرات، مزامنة مقبولة | لا توجد تكلفة API بعد تجهيز الجهاز | متوسط | يحتاج CUDA ووزنات ووقت معالجة |
| MuseTalk محلي | فيديو أساس + WAV | مزامنة فم قوية وسريعة على GPU مناسب | لا توجد تكلفة API بعد تجهيز الجهاز | مرتفع | يحتاج فيديو أداء أساس وبيئة CUDA/MMLab |
| Wav2Lip مفتوح المصدر | فيديو + WAV | مزامنة فم جيدة | لا توجد تكلفة API | منخفض/متوسط | ترخيص النسخة المفتوحة غير مناسب لقناة تجارية |
| D-ID الحالي | صورة + صوت | سهل وجودة جيدة | رصيد/اشتراك | منخفض | نفاد الرصيد واعتماد خارجي |

## التصميم المقترح داخل المشروع

يُفصل مزود Avatar عن `autopilot` عبر واجهة موحدة:

```python
class AvatarProvider(Protocol):
    def create_talking_segment(
        self,
        *,
        audio_path: Path,
        output_path: Path,
        source_image: Path,
        expression_events: list[dict[str, object]],
        name: str,
    ) -> Path: ...
```

تظل دالة `run_avatar_episode()` كما هي تقريبًا. الاختلاف الوحيد هو اختيار المزود من الإعدادات:

```text
AVATAR_PROVIDER=sadtalker
AVATAR_SOURCE_IMAGE=storage/references/nour-master-v1.png
SADTALKER_ROOT=/opt/sadtalker
SADTALKER_PYTHON=/opt/venvs/sadtalker/bin/python
```

عند كل مقطع من خطة الأداء، ينتج Fish Audio ملف WAV أو MP3، ثم يستدعي `SadTalkerProvider`. يبحث الـAdapter عن ملف MP4 الناتج، ينقله إلى مجلد كاش باسم يعتمد على `audio_hash + character_version + provider_version + settings_hash`، ثم يعيد المسار إلى المصيّر. إذا كان الملف موجودًا، لا يعيد التوليد.

## مسار SadTalker المقترح

يُجهّز الجهاز مرة واحدة ببيئة Python 3.8 وPyTorch/CUDA المتوافقين، ويُنزّل FFmpeg والـcheckpoints من مصادر المشروع. الاستدعاء المفاهيمي هو:

```bash
python inference.py \
  --driven_audio /work/segments/A001.wav \
  --source_image /work/references/nour-master-v1.png \
  --result_dir /work/cache/A001 \
  --enhancer gfpgan
```

يحتاج الـAdapter إلى التعامل مع نتيجة SadTalker الفعلية، لأن اسم الملف الناتج يتضمن عادةً طابعًا زمنيًا. لا ينبغي افتراض اسم ثابت؛ يجب البحث عن أحدث MP4 داخل `result_dir` والتحقق من وجود المسار والصوت والمدة.

## Workflow

يجب فصل Workflow الخاص بالـGPU عن Workflow GitHub Actions العادي. GitHub-hosted runner الحالي مناسب للـTTS وFFmpeg، لكنه ليس بيئة CUDA مضمونة لتشغيل SadTalker أو MuseTalk. الخيارات العملية هي جهاز المستخدم المحلي المتصل أثناء التشغيل، أو خادم GPU خارجي، أو runner ذاتي الاستضافة مزود بـCUDA.

ترتيب الخطوات المقترح هو: تثبيت أو التحقق من CUDA، تحميل الـcheckpoints مرة واحدة إلى cache دائم، تثبيت بيئة SadTalker، تشغيل اختبارات CPU للتحقق من CLI فقط، ثم تشغيل مقطع نور من 10–20 ثانية، وبعد نجاحه تشغيل Short كامل، وأخيرًا تشغيل الحلقة الطويلة. لا يُرفع الناتج إلى YouTube إلا بعد Quality Gate صريح.

## Quality Gate

قبل قبول أي مقطع، يفحص النظام أن الملف MP4 غير فارغ، وأنه يحتوي على مسار فيديو ومسار صوت، وأن مدة الفيديو لا تختلف عن مدة الصوت بأكثر من هامش محدد، وأن الوجه موجود في الإطار، وأن Captions قابلة للقراءة. كما يجب الاحتفاظ بملف Manifest يضم اسم المزود، إصدار النموذج، hash الصورة، hash الصوت، الإعدادات، ونسخة الشخصية.

## توصية عملية

للقناة الحالية، ابدأوا بـSadTalker كبديل D-ID، مع إبقاء `DIDAvatarProvider` كخيار احتياطي. هذا يتطلب أولًا توفير جهاز CUDA؛ فلا يمكن تشغيل SadTalker عمليًا داخل GitHub Actions الحالي من دون runner GPU. بعد إعداد الجهاز، نضيف `SadTalkerProvider` إلى `core/avatar_animation.py`، ونضيف `AVATAR_PROVIDER` إلى `autopilot` وWorkflow، ثم نختبر Short نور قبل الحلقة الكاملة.

إذا لم يتوفر GPU، يبقى D-ID هو المسار السحابي الأسهل، لكن بحدود الرصيد. ويمكن تشغيل MuseTalk لاحقًا لتحسين مزامنة الفم إذا أصبح لدينا فيديو أداء أساس مناسب لنور.

## References

[1]: https://github.com/OpenTalker/SadTalker "OpenTalker/SadTalker official repository"
[2]: https://github.com/OpenTalker/SadTalker/blob/main/LICENSE "SadTalker official license"
[3]: https://github.com/TMElyralab/MuseTalk "TMElyralab/MuseTalk official repository"
[4]: https://github.com/TMElyralab/MuseTalk/blob/main/LICENSE "MuseTalk official license"
[5]: https://github.com/Rudrabha/Wav2Lip "Rudrabha/Wav2Lip official repository"
