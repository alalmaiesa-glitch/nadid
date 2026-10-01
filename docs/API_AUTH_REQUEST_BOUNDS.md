# API Authentication Coverage & Request Bounds V1

## الهدف

بعد حماية Origin/CSRF، يبقى نوعان من المخاطر على Route Handlers:

1. endpoint داخلي التطبيق لكنه لا يطلب جلسة مستخدم.
2. طلب صحيح من ناحية Origin لكنه ضخم أو غير محدود ويستهلك ذاكرة/CPU قبل الرفض.

V1 تغلق هاتين الفجوتين.

## Authentication Coverage

كل API غير Health يجب أن يمر عبر أحد:

- `authorizeUser()`
- `authorizeDocument()`
- `authorizeSuggestion()`

تم تحديد فجوة فعلية في:

`POST /api/validate-patch`

وكان بإمكانه استدعاء AEE دون مصادقة مستخدم. أصبح الآن يطلب `authorizeUser()` قبل قراءة الـJSON أو استدعاء AEE.

## Bounded JSON

تمت إضافة:

`readBoundedJson(request, maxBytes)`

وهي:

- تفحص Content-Length إن وجد.
- تقرأ stream مع عدّ البايتات بدل `request.json()` غير المحدود.
- تلغي القراءة عند تجاوز الحد.
- تتطلب JSON Content-Type.
- تحول JSON التالف إلى 400 بدل Exception غير معالج.

الحدود الحالية:

- Suggestion decision: 16 KiB.
- Upload metadata: 8 KiB.
- Validate Patch: 256 KiB.

## Semantic Bounds

إضافة حدود داخل payload نفسه:

- filename: 255 حرفًا.
- documentId / suggestionId: 128 حرفًا.
- validate-patch blockText: 100,000 حرف.
- original/replacement: 20,000 حرف لكل منهما.
- protectedFacts: 500 عنصر.

## Multipart Preflight

`/api/analyze` كان يفحص `File.size` بعد `request.formData()`.

الآن يوجد فحص مبكر لـ Content-Length قبل multipart parsing، مع بقاء فحص File.size بعد parsing كدفاع ثانٍ.

هذا لا يستبدل حدود منصة Vercel للـstreaming/chunked uploads، لكنه يمنع الطلبات ذات الحجم المعلن الكبير من الوصول إلى parser.

## Query & Numeric Bounds

- Context query: حتى 500 حرف.
- Export version: عدد صحيح موجب فقط.

## Benchmark

`BND-001..BND-012` تحمي:

- Content-Length guard.
- streaming byte limit.
- JSON content contract.
- Auth coverage لكل non-health API.
- validate-patch auth-before-body.
- منع raw request.json في JSON routes الحالية.
- multipart preflight order.
- context query bound.
- upload metadata bounds.
- validate-patch semantic bounds.
- suggestion scope bounds.
- export version validation.
