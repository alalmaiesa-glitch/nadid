# Partial Capture & Partial Refund Semantics V1

## الهدف

منع نَضِيد من تحويل حالة مالية جزئية إلى استحقاق كامل.

Moyasar تعرض حقلي captured وrefunded ضمن Payment، وتدعم capture/refund الجزئيين. لذلك لا يكفي الاعتماد على اسم الحدث وحده.

## Capture

- payment_paid: يعد دفعًا كاملًا، ويثبت captured_minor = amount_minor.
- payment_captured: لا يمنح استحقاقًا إلا إذا captured_minor يساوي كامل amount_minor.
- Capture ناقص يسجل rejected_mismatch ولا يغير Payment ولا ينشئ استحقاقًا.

## Refund

أضيفت حالة:
- partially_refunded

وقيم مالية دائمة:
- captured_minor
- refunded_minor

إذا كان refunded_minor:
- أكبر من صفر وأقل من amount_minor => partially_refunded.
- مساويًا لـ amount_minor => refunded.
- أكبر من amount_minor أو قيمة غير صالحة => rejected_mismatch.

سياسة V1 محافظة: أي Refund مالي، حتى لو كان جزئيًا، يوقف الاستحقاق المستقبلي المرتبط بالدفعة:
- الاشتراك النشط يصبح cancelled.
- Top-up يصبح refunded ورصيده المتبقي صفرًا.
- الاستهلاك التاريخي لا يحذف ولا يعكس.

## مقاومة ترتيب الأحداث

partially_refunded وrefunded وvoided حالات نهائية بالنسبة إلى paid/captured المتأخر؛ لا يمكن لحدث قديم أن يعيد الاستحقاق.

كما أن Refund نفسه أحادي الاتجاه:
- `refunded` لا يعود إلى `partially_refunded`.
- قيمة `refunded_minor` لا تنخفض إذا وصل Snapshot أقدم أو مكرر.
- أي Refund يتجاوز `captured_minor` يرفض قبل أي mutation.

## تطابق المبلغ والعملة

كل حدث مالي مرتبط بـPayment محلية يجب أن يحمل amount/currency المطابقين للأصل قبل أي mutation، وليس paid فقط.

## الاختبارات

PARTIAL-DB-001..010 تغطي:
- رفض partial capture.
- قبول full capture.
- تسجيل partial refund.
- إلغاء الاستحقاق بعد partial refund.
- منع resurrection.
- full refund لـTop-up.
- رفض refund أكبر من الأصل.
- رفض currency mismatch.
- حماية RPC من authenticated clients.
- منع خفض Full Refund إلى Partial Refund بوصول حدث أقدم.
- منع Refund يتجاوز المبلغ الملتقط فعليًا.
