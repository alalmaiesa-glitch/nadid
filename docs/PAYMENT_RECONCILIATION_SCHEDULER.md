# Payment Reconciliation Scheduler & Liveness V1

## الهدف

طبقة Payment Reconciliation السابقة جعلت استعادة Webhook المفقود آمنة وقابلة لإعادة المحاولة، وطبقة Fairness جعلت توزيع الـBatch عادلًا. بقيت فجوة تشغيلية: بدون Scheduler فعلي لن يتم استدعاء المصالحة تلقائيًا في Production.

## Vercel Cron

يضيف نَضِيد الآن `vercel.json` مع Cron رسمي:

- Path: `/api/internal/payments/reconcile`
- Schedule: `17 0 * * *`
- التشغيل: يوميًا عند 00:17 UTC.
- Cron Jobs تُسجَّل من Production deployment.

اخترنا daily في V1 عمدًا لأنه متوافق مع Vercel Hobby، بينما Pro وEnterprise يسمحان بتكرار أدق. يمكن رفع التردد لاحقًا إلى hourly أو كل عدة دقائق بعد التأكد من الخطة التشغيلية، دون تغيير منطق المصالحة نفسه.

## المصادقة

Vercel Cron يرسل:

`Authorization: Bearer <CRON_SECRET>`

والـRoute الحالية تتحقق من `CRON_SECRET` بمقارنة timing-safe وتفشل مغلقًا إذا كان السر غير مضبوط.

يجب أن يكون `CRON_SECRET` موجودًا كمتغير Server-only في بيئة Production. لا يوضع السر في Git ولا في `.env.example`.

## حدود التنفيذ

- Batch الافتراضي 25.
- الحد الأقصى 100.
- الـBatch يُClaim ذريًا وبشكل عادل عبر PostgreSQL.
- Partial failure يعيد HTTP 503.
- إعادة التشغيل آمنة بسبب idempotency في طبقة Payment Reconciliation.
- Preview deployments لا تُعد مصدر الجدولة التشغيلية؛ الاعتماد على Production Cron.

## ما الذي تثبته هذه الطبقة؟

هذه الطبقة تثبت أن مسار الاستعادة لم يعد مجرد Endpoint قابل للاستدعاء يدويًا، بل له trigger إنتاجي معلن ومراجع داخل المستودع.

ولا تدّعي V1 أن `CRON_SECRET` قد تم حقنه في حساب Vercel الخارجي؛ ذلك يبقى إعداد Deployment يجب التحقق منه في بيئة الإنتاج نفسها.
