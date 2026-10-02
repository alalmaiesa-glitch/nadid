# Payment Webhook Authenticity, Replay & Reversal Safety V1

## الهدف

ربط حقيقة الدفع القادمة من Moyasar بطبقة الاستحقاقات بدون السماح لـ:
- Webhook مزور.
- إعادة نفس Event لمنح الاستحقاق مرتين.
- Event ID واحد بمحتوى مختلف.
- Paid event متأخر بإحياء دفعة سبق Refund/Void لها.
- Refund أو Void يترك اشتراكًا أو Top-up قابلًا للاستخدام.

## مصادقة Moyasar

وفق توثيق Moyasar الحالي، Webhook يحمل `secret_token` الذي يضبطه التاجر عند إنشاء الـWebhook. Endpoint نَضِيد يقارن هذا السر مع `MOYASAR_WEBHOOK_SECRET` باستخدام مقارنة ثابتة الزمن، ولا يخزن السر في قاعدة البيانات أو التقارير.

## Replay ledger

جدول `payment_webhook_events` يحفظ:
- provider + provider_event_id (Unique).
- event_type.
- provider_payment_id.
- live/test.
- SHA-256 للـraw payload.
- local_payment_id.
- outcome.

إذا تكرر Event نفسه بنفس المحتوى، يعاد استخدام النتيجة. إذا تكرر ID نفسه بمحتوى مختلف، يفشل بـ `webhook_event_replay_mismatch`.

## State machine

- paid/captured: يتطلب تطابق amount + currency مع Payment المحلية.
- refunded/voided: حالات مالية نهائية لا يستطيع paid متأخر إحياءها.
- failed: يغير pending فقط؛ لا يخفض دفعة paid.
- authorized/verified وغيرها: تسجل وتُهمل حتى نحتاجها تشغيليًا.

## Reversal

Refund:
- payment -> refunded.
- subscription المرتبطة بنفس payment -> cancelled وينتهي الاستحقاق الحالي.
- top-up المرتبط -> refunded وcharacters_remaining = 0.

Void:
- payment -> voided.
- subscription -> cancelled.
- top-up -> voided وcharacters_remaining = 0.

الاستخدام التاريخي لا يُمحى؛ نوقف الاستحقاق المستقبلي فقط.

## Activation

بعد paid/captured الموثق:
- subscription تقرأ `metadata.plan_id` وتستدعي RPC التفعيل الحالية.
- credit_topup تقرأ `metadata.pack_id` وتستدعي RPC التفعيل الحالية.
- RPCs نفسها idempotent، لذلك Replay لا ينشئ استحقاقًا ثانيًا.

## HTTP policy

Endpoint:
`POST /api/payments/moyasar/webhook`

- 401 secret خاطئ.
- 400 JSON/payload غير صالح.
- 413 payload أكبر من 256 KiB.
- 409 Event replay mismatch.
- 200 للأحداث applied/ignored/unmatched الموثقة، حتى لا نصنع retry storm.
