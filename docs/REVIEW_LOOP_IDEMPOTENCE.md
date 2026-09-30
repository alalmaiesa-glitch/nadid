# Review Loop & Idempotence V1

## الهدف

اختبار الحلقة التشغيلية الكاملة:

`Review → Safe Auto-Fix Plan → Apply → Re-parse → Review Again`

والتأكد أن التصحيحات الآمنة:

- تتقارب إلى حالة مستقرة.
- لا تعيد اقتراح التصحيح نفسه.
- لا تُنشئ ملاحظات جديدة.
- لا تُنشئ Findings جديدة من نوع High/Critical.
- لا تغيّر المعنى المحمي.
- لا تغيّر هوية العقد أو بنية المستند.
- تصبح النتيجة ثابتة عند تشغيل الحلقة مرة ثانية.

## Fail-Closed Invariants

تتوقف الحلقة وتُعد غير آمنة إذا حدث أي مما يلي:

1. تغير Protected Meaning Signature.
2. تغير Node/Structure Signature.
3. تعذر تطبيق Patch سبق أن وافقت عليه السياسة.
4. ظهر Finding جديد بعد Auto-Fix.
5. ظهر Finding جديد High/Critical.
6. بقي Auto-Fix بعد الحد الأقصى للجولات.

Remaining `Suggest / Require Review / Block` مسموح به؛ الاستقرار يعني عدم بقاء أي Auto-Fix آمن قابل للتطبيق، وليس اختفاء جميع الملاحظات.

## المشكلة التي كشفها V1

التشغيل الأول للـBenchmark حقق **19/20 = 95%** وفشلت `LOOP-016` الخاصة بتكرار المصدر النصي نفسه أكثر من مرة داخل العقدة.

السبب: الاقتراح كان يعرف موضع الخطأ عند إنشاء الـID، لكن PatchOperation لم يكن يحمل Offset صريحًا. لذلك عند تكرار النص نفسه قد يُعاد تعديل أول تطابق بدل التطابق المقصود.

## الإصلاح

تم تحويل المسار الآمن إلى Exact-Span Patching:

- Suggestion يحمل `start_offset / end_offset`.
- Evidence Location يحتفظ بالـOffsets.
- PatchOperation يحمل `start_offset`.
- Meaning Lock يتحقق من النص في الموضع المحدد.
- Auto-Apply يتطلب Precise Source Location.
- الاقتراحات داخل العقدة تطبق من اليمين إلى اليسار.
- DOCX patcher يطبق على الموضع المحدد بدل أول تطابق.
- Table-cell patching يدعم Offset داخل نص الخلية.
- `/v1/validate-patch` و`/v1/apply/docx` يدعمان الـOffset.
- أي اقتراح بلا موضع دقيق لا يصبح Auto-Fix.

## Benchmark V1

20 حالة تغطي المستند النظيف، الإملاء، الترقيم، الأخطاء الكثيفة، الفقرات المتعددة، العناوين، خلايا الجداول، الجمل ذات المعنى الحساس، القيم المحمية، Style-only، تعارض القرار، تعارض الحقائق، التشغيل الثاني، تكرار المصدر النصي، الحفاظ على تنسيق الـRun، وعدم توليد Findings جديدة.

## النتيجة النهائية

- Review Loop & Idempotence V1: **20/20 = 100%**
- Core Quality Benchmark: **149/149 = 100%**
- Mutation Benchmark V1: **53/53 = 100%**
- Consistency Benchmark V1: **28/28 = 100%**
- Evidence Benchmark V1: **12/12 = 100%**
- Confidence & Severity Benchmark V1: **18/18 = 100%**
- Review Action & Auto-Apply Benchmark V1: **20/20 = 100%**

هذه نتائج اختبارات هندسية وليست Human Precision/Recall.

## قاعدة الإصدار

أي Auto-Fix فعلي يجب أن يمر عبر:
1. Exact source span.
2. Action Policy.
3. Meaning Lock.
4. Right-to-left patch ordering داخل العقدة.
5. Sequential revalidation.
6. Post-apply reparse.
7. Meaning + structure invariants.
8. Fresh re-review حتى الاستقرار.
9. Second-run idempotence في الاختبارات الحاكمة.
