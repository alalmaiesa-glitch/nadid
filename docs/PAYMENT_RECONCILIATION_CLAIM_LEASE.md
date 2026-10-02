# Payment Reconciliation Claim Lease & Overlap Suppression V1

## المشكلة

استخدام FOR UPDATE SKIP LOCKED يحمي لحظة اختيار الصفوف داخل المعاملة فقط. بعد انتهاء RPC ينتهي قفل PostgreSQL، بينما يبقى الاتصال الخارجي مع Moyasar جاريًا.

إذا بدأ تشغيلان متقاربان وكان عدد المرشحين قليلًا، يستطيع التشغيل الثاني اختيار الصف نفسه بعد انتهاء معاملة التشغيل الأول. Idempotency تمنع مضاعفة الأثر المالي، لكنها لا تمنع اتصالات provider المكررة ولا ضغط rate limits.

## الحل

يضاف إلى payments:

- reconciliation_claimed_until

وعند claim:

- يستبعد أي صف lease الخاصة به ما زالت فعالة.
- يحدد reconciliation_checked_at وreconciliation_claimed_until ذريًا.
- lease الافتراضية 900 ثانية.
- الحد الأدنى 60 ثانية.
- الحد الأعلى 3600 ثانية.
- يبقى FOR UPDATE SKIP LOCKED للحماية أثناء لحظة claim نفسها.

## Crash Recovery

الـlease ليست قفلًا دائمًا. إذا ماتت Function أو انقطع التنفيذ، ينتهي الحجز تلقائيًا بعد المدة ويعود الصف إلى الطابور دون تدخل يدوي.

## Overlap Behavior

تشغيل ثانٍ متزامن أو قريب زمنيًا لا يعيد Claim للدفعات التي يملكها تشغيل آخر ما دامت lease فعالة. ويمكنه معالجة دفعات أخرى غير محجوزة.

## التشغيل

متغير البيئة:

- NADID_PAYMENT_RECONCILE_CLAIM_LEASE_SECONDS=900

Route يمرر القيمة إلى RPC، بينما قاعدة البيانات نفسها تفرض حدود 60..3600 ثانية حتى لو كان إعداد البيئة خاطئًا.

## Regression Guards

- منع إعادة claim داخل lease.
- السماح بعد انتهاء lease.
- بقاء حد batch السابق.
- منع authenticated من استدعاء RPC.
- الحفاظ على التوقيع القديم ذي المعامل الواحد كـ wrapper يمر حتميًا عبر lease افتراضية 900 ثانية، حتى لا ينكسر Fairness V1 ولا توجد طريقة لتجاوز الحماية.
