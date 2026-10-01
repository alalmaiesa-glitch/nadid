# SSR Route Authorization V1

## الهدف

RLS تحمي البيانات داخل Supabase، لكنها لا تكفي وحدها لحماية تجربة التطبيق.

هذه الطبقة تحمي مستوى Next.js نفسه:

- الصفحات التي تتطلب جلسة.
- توجيه المستخدم غير المسجل إلى صفحة الدخول.
- إعادة المستخدم المسجل من صفحة الدخول إلى مساحة المستندات.
- قيمة `next` المستخدمة في Login/OAuth callback.
- الفشل المغلق عندما تكون إعدادات المصادقة ناقصة في Production.

## Protected Routes

المسارات المحمية مركزيًا في:

`lib/auth-routing.ts`

وتشمل حاليًا:

- `/documents`
- `/upload`
- `/editor`

ويتم التطابق بحدود المسار، فلا يصبح مسار مثل `/editorial` محميًا لمجرد أنه يبدأ بالحروف نفسها.

## Safe Internal Redirects

`safeInternalNext()` يقبل فقط مسارًا داخليًا يبدأ بـ `/` ويرفض:

- protocol-relative redirects مثل `//evil.example`
- backslash forms
- raw control characters
- encoded slash/backslash
- encoded control characters

ويعود إلى `/documents` عند الشك.

نفس helper مستخدم في:

1. Middleware.
2. Login page.
3. OAuth callback.

وبذلك لا توجد ثلاث نسخ مختلفة من منطق redirect يمكن أن تنحرف عن بعضها.

## Fail Closed

إذا كانت Supabase Auth غير مهيأة في Production لمسار يحتاج المصادقة، يعيد Middleware:

- HTTP 503

بدل السماح بمرور الصفحة المحمية دون تحقق.

## Benchmark

`SSR-001..SSR-010` تحمي:

- قائمة المسارات المحمية.
- حدود prefix.
- منع open redirect.
- encoded separator/control rejection.
- middleware guard usage.
- authenticated login redirect.
- production auth fail-closed.
- callback redirect guard.
- login redirect guard.
- إزالة المنطق المكرر القديم.

هذه الطبقة تكمل RLS ولا تستبدله.
