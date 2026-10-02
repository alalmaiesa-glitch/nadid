# Payment Environment Isolation V1

## الهدف

منع أي تداخل بين بيئة Moyasar التجريبية والبيئة الحية.

المشكلة التي تحلها الطبقة:
- مفاتيح Publishable وSecret من بيئتين مختلفتين.
- Intent تجريبية تستقبل Webhook حيًا.
- Intent حية تستقبل Webhook تجريبيًا.
- Callback يتحقق بمفتاح من بيئة تختلف عن Payment المحلية.

## قاعدة المفاتيح

نَضِيد يقبل زوجًا واحدًا متناسقًا فقط:
- pk_test_ + sk_test_ => test.
- pk_live_ + sk_live_ => live.

أي غياب أو Prefix غير معروف أو خلط بين الوضعين يفشل مغلقًا قبل إنشاء Intent.

## قاعدة البيانات

أضيف payments.provider_mode بقيم:
- test
- live

كل Intent جديدة تسجل الوضع داخل العمود وداخل metadata.

RPC apply_payment_webhook_event تقارن:
- webhook.live = true مع provider_mode = live.
- webhook.live = false مع provider_mode = test.

أي اختلاف:
- يسجل Event للـaudit.
- outcome = rejected_mismatch.
- لا يغير حالة Payment.
- لا يمنح اشتراكًا أو رصيدًا.

## Callback

عميل Moyasar الخادمي يحدد الوضع من زوج المفاتيح الموثق.
Callback تقارن الوضع مع Payment المحلية قبل reconciliation.

## Idempotency

نفس Idempotency-Key لا يمكن إعادة استخدامه عبر بيئتين مختلفتين حتى لو كان المنتج نفسه.

## الاختبارات

ENV-DB-001..006:
- حفظ test mode.
- رفض live event على test intent.
- قبول test event المطابق.
- رفض test event على live intent.
- منع cross-mode idempotency reuse.
- رفض provider mode غير معروف.
