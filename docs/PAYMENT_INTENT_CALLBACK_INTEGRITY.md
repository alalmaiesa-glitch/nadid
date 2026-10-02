# Payment Intent Creation & Callback Verification V1

## الهدف

منع العميل من التحكم في المبلغ أو العملة أو منح نفسه خطة/رصيد، ومنع اعتماد callback URL كحقيقة دفع.

## Intent

`POST /api/payments/intents`

العميل يرسل فقط:
- `productKind`: subscription أو credit_topup.
- `productId`: معرف الخطة أو الحزمة.
- Header: `Idempotency-Key` بصيغة UUID.

الخادم/قاعدة البيانات:
1. تتحقق من المستخدم.
2. تطبق Same-Origin + Rate Limit.
3. تجلب المنتج النشط من billing_plans أو credit_packs.
4. تستخرج amount/currency من المصدر الموثوق.
5. تنشئ payment محلية pending.
6. تستخدم payment UUID كـ Moyasar `given_id`.
7. تعيد بيانات إنشاء الدفع بدون استقبال أي بيانات بطاقة على خادم نَضِيد.

إعادة نفس Idempotency-Key لنفس المنتج تعيد نفس Intent. استخدام المفتاح نفسه لمنتج مختلف يفشل.

## Callback

`GET /api/payments/moyasar/callback?id=...`

لا يقرأ نَضِيد `status` أو `message` من Query كحقيقة مالية.

بدلًا من ذلك:
1. يتحقق من هوية المستخدم وملكية Payment المحلية.
2. يجلب Payment من Moyasar عبر Secret API Key.
3. يتحقق من ID + amount + currency.
4. يحول الحالة الموثقة إلى Event داخل state machine الموجودة.
5. التفعيل يعاد استخدام RPCs الآمنة الموجودة.

Moyasar نفسها توصي بعد العودة من callback بجلب Payment خادميًا والتحقق من status + amount + currency قبل تنفيذ أي business action.

## الأمان

- Card data لا تمر عبر Backend نَضِيد.
- Secret key لا يظهر للمتصفح.
- Publishable key فقط يعاد للواجهة.
- Callback لا يستطيع التحقق من Payment يملكها مستخدم آخر.
- Idempotency يمنع إنشاء intents مزدوجة عند retry.
- Refund/Void وحماية Replay تبقى من الطبقة السابقة.
