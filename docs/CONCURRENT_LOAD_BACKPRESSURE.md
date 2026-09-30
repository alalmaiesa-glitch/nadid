# Concurrent Load, Failure Isolation & Backpressure V1

## الهدف

بعد حماية ملف DOCX نفسه، يجب حماية الخدمة من تداخل الطلبات ومن الاستنزاف الناتج عن معالجة عدة مستندات ثقيلة في الوقت نفسه.

V1 تضع ثلاثة عقود:

1. **Isolation** — لا ينتقل نص أو state من طلب إلى طلب آخر.
2. **Failure isolation** — ملف تالف في طلب لا يسمم الطلبات الصحيحة المتزامنة أو اللاحقة.
3. **Backpressure** — عندما تمتلئ سعة المعالجة، ترفض الخدمة العمل الزائد بوضوح بدل السماح بتضخم CPU/Memory غير المنضبط.

## تغيير التنفيذ

كانت endpoints الخاصة بـDOCX معرفة كـ `async def` ثم تنفذ Parser/Review/Memory كعمل CPU متزامن داخل event loop.

V1 تحول:

- `/v1/analyze/docx`
- `/v1/analyze/docx/deep`
- `/v1/apply/docx`

إلى Sync FastAPI handlers. وبذلك يشغلها FastAPI في threadpool بدل حجز event loop أثناء العمل الثقيل.

## Work slots

يوجد Gate مستقل لمعالجة DOCX:

- الافتراضي: **4** عمليات DOCX متزامنة لكل process.
- قابل للضبط عبر `AEE_MAX_CONCURRENT_JOBS`.
- الحد الأدنى دائمًا 1.

عند امتلاء السعة:

- HTTP **503**
- code: `AEE_BUSY`
- header: `Retry-After: 1`

الرفض فوري ولا يدخل الطلب في طابور غير محدود.

## ما لا يخضع للـGate

`/health` لا يستهلك Work Slot، حتى يمكن لمنصة التشغيل مراقبة صحة الخدمة أثناء التشبع.

## Benchmark V1

11 حالة `CON-001` إلى `CON-011`:

- مستندات متوازية بعلامات مختلفة وعدم تسرب النص.
- deterministic IDs تحت التنفيذ المتوازي.
- valid + malformed بالتوازي.
- تشبع كل Work Slots والتحقق من 503.
- بقاء health متاحًا أثناء التشبع.
- التعافي بعد تحرير السعة.
- burst صالح.
- burst تالف.
- Deep Analyze متوازٍ.
- سلسلة ملفات تالفة ثم طلب صحيح للتأكد من عدم تسرب slot أو state.\n- عمليتا No-op Apply متوازيتان مع التحقق من بقاء الاستجابة DOCX سليمة ومن عداد التعديلات.

## مبدأ النجاح

لا يُعد ارتفاع عدد 503 تحت burst فشلًا في هذه الطبقة؛ 503 هو **سلوك backpressure مقصود**.

الفشل الحقيقي هو:

- 5xx غير 503.
- تسرب نص بين الطلبات.
- فقد deterministic output.
- عدم استعادة السعة بعد الخطأ.
- تعطل health بسبب امتلاء Work Slots.
- قبول حمل يتجاوز Gate دون حد.
- أو فشل طلب صحيح ضمن عدد العمال المسموح.

## حدود V1

هذا Gate محلي لكل process. إذا شغلت البنية عدة replicas، فكل replica لها سعتها الخاصة.

V1 لا تستبدل:

- rate limiting على مستوى المستخدم/الحساب.
- queue موزعة.
- autoscaling.
- quotas حسب الباقة.
- timeouts على مستوى reverse proxy.
- process memory limits.

هذه عناصر تشغيلية لاحقة فوق طبقة العزل والـbackpressure المحلية.
