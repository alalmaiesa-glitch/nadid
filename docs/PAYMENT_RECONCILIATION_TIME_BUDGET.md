# Payment Reconciliation Run Time Budget & Graceful Yield V1

## المشكلة

بعد إضافة timeout وretry budget إلى Moyasar أصبح زمن كل عنصر محدودًا، لكن Batch كاملة قد تتكون من عناصر عديدة. تنفيذها دفعة واحدة قد يقترب من حد منصة التشغيل ويجعل الـFunction تُقتل قبل Finalize لسجل التشغيل.

## الحل

المصالحة تعمل الآن تحت ميزانية زمنية كلية:

- الافتراضي: 240000ms.
- الحد الأدنى: 60000ms.
- الحد الأعلى: 900000ms.
- قبل Claim كل عنصر تحسب route احتياطًا لأسوأ زمن متوقع للمحاولة التالية من timeout × attempts + bounded retry delays + هامش صغير.
- إذا لم يبق وقت كافٍ، تتوقف قبل Claim العنصر التالي.

## لماذا Claim عنصر واحد؟

بدل Claim Batch كاملة ثم اكتشاف نفاد الوقت أثناء معالجتها، يتم Claim صف واحد فقط في كل دورة.

النتيجة:

- الصفوف التي لم يبدأ تنفيذها تبقى unclaimed.
- لا تُستهلك lease على دفعات لم تصل فعليًا إلى Moyasar.
- التشغيل التالي يستطيع مواصلة الطابور مباشرة.
- Claim Lease V1 ما زالت تمنع التداخل على العنصر الجاري.

## Failure semantics

نفاد الميزانية ينهي Run بصورة مدققة كـ partial_failure مع:

PAYMENT_RECONCILIATION_TIME_BUDGET_EXHAUSTED

ويرجع HTTP 503، وبالتالي تبقى إعادة المحاولة آمنة بفضل idempotency وclaim lease.

إذا فشل Claim من قاعدة البيانات قبل أي عنصر تبقى الحالة lookup_failure. وإذا حدث بعد عناصر معالجة، يسجل partial_failure بدل فقدان أثر العمل الذي تم.

## التشغيل

NADID_PAYMENT_RECONCILE_RUN_BUDGET_MS=240000

هذه ميزانية داخل التطبيق وليست ادعاءً بحد ثابت للمنصة. يجب إبقاؤها أقل من حد Function الفعلي في بيئة النشر مع هامش مناسب.
