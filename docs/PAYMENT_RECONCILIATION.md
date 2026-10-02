# Payment Reconciliation & Missing-Webhook Recovery V1

## الهدف

Webhook وCallback كلاهما مساران لحظيان وقد يتأخر أحدهما أو يفشل وصوله. لذلك لا يجوز أن تعتمد الحالة المالية النهائية لنَضِيد على وصول حدث واحد فقط.

تضيف V1 مسار Reconciliation داخليًا يعيد جلب حالة الدفعات القابلة للمصالحة من Moyasar ثم يمرر الحالة الموثقة إلى نفس منطق Webhook وقواعد قاعدة البيانات.

## الحالات المرشحة

المسار يراجع فقط دفعات Moyasar ذات الحالات المحلية:

- `pending`
- `paid`
- `partially_refunded`

السبب:

- `pending`: لاستعادة paid/captured/failed/voided الذي لم يصل Webhook له.
- `paid`: لاستعادة refund/void المتأخر.
- `partially_refunded`: لاستعادة زيادة refund أو full refund.

الحالات النهائية مثل `refunded` و`voided` لا تدخل Batch الدوري.

## الأمان

Endpoint الداخلي:

`GET /api/internal/payments/reconcile`

ويشترط:

- `Authorization: Bearer <CRON_SECRET>`
- مقارنة timing-safe.
- Fail closed إذا لم يكن `CRON_SECRET` مضبوطًا.
- Service Role فقط للوصول إلى جدول payments.
- Batch محدود افتراضيًا إلى 25 وبحد أقصى 100.
- لا يقبل Payment ID من العميل؛ المرشحون يأتون من قاعدة البيانات فقط.

## Idempotency

لكل حالة Provider موثقة ينشأ Event ID حتمي من:

- payment id
- provider status
- captured amount
- refunded amount
- provider occurred/updated timestamp

كما أن digest يعتمد على canonical verified state لا على raw JSON formatting. لذلك إعادة تشغيل المصالحة للحالة نفسها آمنة ولا تنشئ mutation ثانية.

## Failure behavior

- أخطاء Provider أو DB لا تمنح استحقاقًا.
- أي فشل داخل Batch يجعل endpoint يعيد 503 حتى يستطيع المجدول إعادة المحاولة.
- نجاح بعض العناصر قبل فشل عنصر لاحق آمن بسبب idempotency.
- amount/currency/environment/refund semantics تبقى محمية داخل `apply_payment_webhook_event`.

## التشغيل

يضاف إلى البيئة:

- `CRON_SECRET`
- `NADID_PAYMENT_RECONCILE_BATCH=25`

يمكن استدعاء endpoint من Scheduler موثوق. V1 لا تفترض مزود Scheduler بعينه داخل المستودع؛ تردد التشغيل يحدد عند ربط بيئة الإنتاج.

## نطاق V1

هذه الطبقة تعالج **drift بين حالة Moyasar والحالة المحلية**. لا تعد Settlement/Bank reconciliation ولا محاسبة دفتر أستاذ مزدوج.
