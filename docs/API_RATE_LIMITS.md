# API Rate Limits & Abuse Quotas V1

## الهدف

حدود الحجم تمنع الطلب الواحد من استنزاف الموارد، لكنها لا تمنع مستخدمًا مصادقًا من إرسال عدد كبير من الطلبات الصغيرة والمتكررة.

V1 تضيف Rate Limiting تشغيليًا للمسارات المكلفة، مع بقاء حصص الأحرف الشهرية وقيود الرفع كسياسات مستقلة.

## لماذا PostgreSQL؟

نَضِيد يعمل على بيئة Serverless، لذلك عداد داخل ذاكرة عملية Node لا يضمن الاتساق بين النسخ.

تم إنشاء:

- `api_rate_windows`
- `consume_api_rate_limit(...)`

يوجد صف واحد فقط لكل:

`user_id + action`

ويتم تحديثه عبر `INSERT ... ON CONFLICT DO UPDATE` بصورة ذرية.

## السياسات التشغيلية V1

- Analyze: 12 / دقيقة.
- Validate Patch: 120 / دقيقة.
- Context Search: 120 / دقيقة.
- Deep Review creation: 6 / ساعة.
- Upload creation: 30 / دقيقة.
- Upload finalization: 30 / دقيقة.
- Suggestion decisions: 120 / دقيقة.
- Derived version creation: 12 / دقيقة.

هذه حدود Abuse عالية نسبيًا وليست بديلًا عن باقات الاستخدام أو الحصص الشهرية.

## Fail Closed

في Production:

- غياب user identity للحد -> 503.
- غياب Supabase Admin -> 503.
- فشل RPC -> 503.

عند تجاوز الحد:

- HTTP 429
- `Retry-After`
- code: `RATE_LIMITED`

## موضع الحارس

يعمل بعد نجاح المصادقة/الملكية، وقبل العمل المكلف مثل:

- multipart parsing.
- JSON processing المكلف.
- context search.
- enqueue.
- AEE patch/export work.

ولا يطبق حد Deep Review على GET polling؛ الحد مخصص لـPOST الإنشائي.

## الاختبارات

`RATE-001..RATE-010` تتحقق من المعمارية والتغطية والترتيب.

كما يوجد PostgreSQL regression فعلي يختبر:

- السماح داخل الحد.
- 429-equivalent decision بعد التجاوز.
- صف واحد فقط لكل نافذة.
- منع authenticated من استدعاء RPC مباشرة.
- إعادة ضبط النافذة بعد الانتهاء.
