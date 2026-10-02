# Payment Reconciliation Run Ledger & Stale-Scheduler Detection V1

## المشكلة

وجود Cron معلن لا يثبت وحده أن المصالحة تعمل فعليًا. قد يحدث واحد من الآتي:

- لا تكون قيمة `CRON_SECRET` مضبوطة في Production.
- يفشل Vercel Cron في الاستدعاء.
- تبدأ Function ثم تتوقف بسبب crash أو timeout.
- يفشل جلب الـBatch قبل الوصول إلى منطق المصالحة.
- تنتهي المصالحة جزئيًا مع أخطاء يجب أن تبقى قابلة للتدقيق.

بدون Run Ledger تصبح هذه الحالات صامتة.

## Run Ledger

تمت إضافة الجدول:

`payment_reconciliation_runs`

ويسجل لكل تشغيل:

- `started_at`
- `completed_at`
- `status`: running / succeeded / partial_failure / lookup_failure
- scanned
- reconciled
- ignored
- failed
- error_code

لا توجد RLS policy تسمح للمتصفح بقراءته، وجميع RPCs محصورة في `service_role`.

## Lifecycle

المسار `/api/internal/payments/reconcile` ينفذ الآن:

1. يتحقق من `CRON_SECRET`.
2. ينشئ Run بحالة `running`.
3. يطالب Batch عادلة ذريًا.
4. ينفذ المصالحة.
5. ينهي الـRun مرة واحدة فقط:
   - `succeeded`
   - `partial_failure`
   - `lookup_failure`
6. إذا فشل حفظ نتيجة التدقيق بعد تنفيذ العمل، يعيد 503 لكي تكون إعادة المحاولة آمنة بفضل idempotency.

الـRun المكتملة لا يمكن Finalize لها مرة ثانية، ما يمنع الكتابة اللاحقة من تغيير سجل تاريخي.

## Crash Detection

إذا ماتت Function بعد إنشاء الـRun وقبل Finalize، يبقى السجل بحالة `running`.

Health RPC يعتبر أي `running` أقدم من الحد المحدد تشغيلًا عالقًا، فيظهر كـ `stale_running=true`.

## Stale Scheduler

المسار المحمي:

`GET /api/internal/payments/reconcile/health`

يستخدم نفس `CRON_SECRET`.

القيمة الافتراضية:

`NADID_PAYMENT_RECONCILE_MAX_AGE_MINUTES=2160`

أي **36 ساعة**. هذا أوسع من دورة Cron اليومية ويترك هامشًا لعدم دقة توقيت Hobby، لكنه يكشف فقدان أكثر من دورة تشغيل.

- Healthy -> HTTP 200.
- لا يوجد نجاح حديث -> HTTP 503.
- يوجد Run عالق قديم -> HTTP 503.
- فشل قراءة Health -> HTTP 503.

## لماذا لا نمسح الـrunning القديم؟

السجل العالق دليل crash مهم. لا يُحوَّل آليًا إلى success أو failure لأن العملية ربما ماتت قبل أن نعرف أي جزء تم. المصالحة نفسها Idempotent، لذا التشغيل التالي يستطيع إعادة التحقق بأمان، بينما يبقى أثر الانقطاع قابلًا للتدقيق.

## Regression Guards

- Start ينشئ سجلًا durable.
- Finish أحادي الاتجاه.
- المقاييس تحفظ كما حدثت.
- Partial failure لا تُحسب نجاحًا.
- Run قديم غير مكتمل يُكتشف.
- Client roles لا تقرأ الجدول ولا تستدعي RPCs.
- Route لا تعتبر المصالحة ناجحة إذا فشل Finalize للتدقيق.
