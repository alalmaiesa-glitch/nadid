# Storage Object Isolation & Signed Access V1

## الهدف

بعد تثبيت RLS على جداول نَضِيد واختبار PostgREST/JWT، تبقى ملفات DOCX الأصلية نفسها سطحًا أمنيًا مستقلًا.

نَضِيد يستخدم bucket خاصًا باسم `nadid-documents`، ومسار الرفع التشغيلي الحديث:

`owner_id/document_id/v1/source.docx`

ويُصدر الخادم Signed Upload URL للمستخدم بدل منح المتصفح صلاحية مباشرة على Storage.

## عقد الأمان

- bucket يبقى `public = false`.
- `anon` لا يقرأ ولا يكتب مباشرة إلى `nadid-documents`.
- `authenticated` لا يقرأ ولا يكتب مباشرة إلى `nadid-documents`.
- الخادم/Worker يحتفظ بصلاحية Storage اللازمة.
- الوصول المؤقت يتم عبر رابط موقّع محدود للكائن المقصود.
- تغيير مسار الكائن في Signed URL مع الاحتفاظ بالتوقيع يجب أن يفشل.

## Defense in depth

أضيفت سياسات deny صريحة على `storage.objects` للأدوار browser-facing داخل bucket.

هذه السياسات توثق المقصود المعماري بدل الاعتماد فقط على غياب Allow policy.

## E2E المحلي

الاختبار يعمل ضد Supabase Storage المحلي الحقيقي داخل CI، ويغطي 12 حالة:

1. رفع Object 1 بخادم موثوق.
2. رفع Object 2 بخادم موثوق.
3. منع anonymous direct read.
4. منع authenticated direct read حتى لملف المستخدم نفسه.
5. منع cross-user direct read.
6. منع cross-user overwrite.
7. إبقاء server read متاحًا.
8. إنشاء signed download محدود زمنيًا.
9. signed download يعمل بلا browser session.
10. tampered signed path يفشل.
11. مستخدم ثانٍ لا يحصل على direct read.
12. public object endpoint لا يكشف bucket الخاص.

لا يلمس الاختبار المشروع المستضاف أو بيانات إنتاجية.
