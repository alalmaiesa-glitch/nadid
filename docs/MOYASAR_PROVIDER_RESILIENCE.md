# Moyasar Provider Timeout, Retry Budget & Failure Classification V1

## المشكلة

مسار المصالحة يعتمد على اتصال خارجي مع Moyasar. بدون timeout صريح يمكن لاتصال واحد معلّق أن يحتجز دورة المصالحة، وبدون retry budget قد تتحول أخطاء عابرة مثل 429 أو 503 إلى فشل تشغيلي دائم أو إلى إعادة محاولات غير منضبطة.

## السياسة

- timeout افتراضي لكل محاولة: 8000ms.
- الحد الأدنى 1000ms والحد الأعلى 30000ms.
- عدد المحاولات الافتراضي: 3.
- الحد الأدنى محاولة واحدة والحد الأعلى 5.
- يعاد فقط عند network failure أو timeout أو HTTP 408/425/429/500/502/503/504.
- 404 لا يعاد لأنه ليس خطأً عابرًا.
- Retry-After الرقمي يُحترم لكن يُقص عند 2000ms حتى لا تحتجز Function مدة طويلة.
- fallback backoff محدود ومتزايد.
- بعد استنفاد الميزانية يصنف timeout كـ MOYASAR_FETCH_TIMEOUT و429 كـ MOYASAR_RATE_LIMITED وبقية الأعطال كـ MOYASAR_FETCH_FAILED.

## السلامة

لا تؤدي إعادة جلب حالة الدفع إلى mutation مباشرة. الحالة الموثقة ما زالت تمر عبر نفس مسار reconciliation/webhook idempotent، لذلك retry لقراءة provider لا يضاعف الأثر المالي.

## التشغيل

متغيرات البيئة:

- NADID_MOYASAR_FETCH_TIMEOUT_MS=8000
- NADID_MOYASAR_FETCH_MAX_ATTEMPTS=3

القيم غير الصحيحة أو الخارجة عن الحدود لا تستطيع تعطيل الحماية لأن الكود يطبق defaults وحدودًا ثابتة.

## Regression Guard إضافي

اكتشفت هذه الطبقة خلل تنسيق حقيقيًا في .env.example: كانت أسطر إعدادات reconciliation تحتوي literal \\n بدل newline فعلي. تم إصلاحه وإضافة Guard دائم لمنع عودته.
