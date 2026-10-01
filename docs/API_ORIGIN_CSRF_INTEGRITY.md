# API Mutation Origin & CSRF Integrity V1

## الهدف

RLS وملكية المستند تحميان البيانات بعد وصول الطلب إلى الخادم، لكن الطلبات المعتمدة على Cookies تحتاج أيضًا إلى حماية طبقة HTTP من الطلبات المتقاطعة التي تحاول تنفيذ عملية باسم المستخدم.

هذه الطبقة تضيف حارسًا مركزيًا للعمليات المتغيرة في Route Handlers:

- POST
- PATCH
- DELETE

ولا تغيّر GET / HEAD / OPTIONS.

## السياسة

`enforceSameOriginMutation(request)` يطبق:

1. رفض `Sec-Fetch-Site: cross-site` مباشرة.
2. تطبيع `Origin` ومقارنته بأصل التطبيق exact-origin.
3. استخدام `NEXT_PUBLIC_APP_URL` كأصل موثوق عند توفره.
4. في Production: غياب إعداد أصل التطبيق يفشل مغلقًا بـ503.
5. في Production: غياب Origin لعملية متغيرة يفشل مغلقًا بـ403.
6. لا توجد wildcard CORS أو مقارنة suffix/substring للأصل.

## نطاق V1

الحارس مطبق على جميع Route Handlers المتغيرة الحالية:

- حذف الحساب.
- تحليل مستند.
- بدء Deep Review.
- Finalize Upload.
- حذف مستند.
- إنشاء نسخة مشتقة.
- قبول/رفض Suggestion.
- إنشاء Upload.
- Validate Patch.

ويعمل الحارس قبل:

- authorizeUser / authorizeDocument.
- request.json / request.formData.
- enqueue / delete / persistence.

الهدف أن الطلب cross-origin المرفوض لا يستهلك عملًا جانبيًا ولا يقترب من طبقة الكتابة.

## Benchmark

`API-001..API-010` تتحقق من:

- استثناء safe methods.
- Fetch Metadata guard.
- exact Origin matching.
- production fail-closed.
- missing Origin policy.
- تغطية جميع Mutating Routes.
- ترتيب الحارس قبل المصادقة والـbody والكتابة.
- Guard واحد لكل mutating handler.
- Origin normalization.
- منع wildcard/suffix origin acceptance.

هذه الطبقة تكمل RLS وSSR Route Authorization ولا تستبدلهما.
