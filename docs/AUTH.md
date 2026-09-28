# مصادقة نَضِيد

يدعم التطبيق ثلاث طرق لإنشاء الحساب والدخول:

1. Google OAuth.
2. البريد الإلكتروني وكلمة المرور.

التسجيل برقم الجوال مؤجل حاليًا ولا يظهر للمستخدم.

## النطاق

النطاق العام الحالي:
`https://nadidai.com`

عند نشر تطبيق Next.js الكامل على هذا النطاق، تضبط إعدادات Supabase Auth كالتالي:

- Site URL: `https://nadidai.com`
- Redirect URL: `https://nadidai.com/auth/callback`

## Google

يحتاج تفعيل Google Provider في Supabase إلى:

- Google OAuth Client ID
- Google OAuth Client Secret

في Google Auth Platform:
- Authorized JavaScript origin: `https://nadidai.com`
- Authorized redirect URI: استخدم Supabase Auth callback URL الظاهر داخل إعدادات Google Provider لمشروع نَضِيد.

لا تحفظ Client Secret في GitHub أو في المتصفح.

## رقم الجوال

مؤجل حاليًا. لا يظهر كخيار تسجيل في واجهة نَضِيد، وPhone Auth غير مفعّل في Supabase.

## البريد الإلكتروني

إنشاء الحساب:
- Email + password.
- الحد الأدنى في الواجهة: 8 أحرف لكلمة المرور.
- إذا كان تأكيد البريد مفعلًا في Supabase، ينتظر المستخدم رسالة التأكيد.
- إذا كان غير مطلوب، تبدأ الجلسة مباشرة.

تسجيل الدخول:
- Email + password.

## الأمان

- OAuth يعود فقط إلى `/auth/callback`.
- قيمة `next` تقبل المسارات الداخلية فقط.
- أسرار Google وSMS لا توضع في GitHub.
- لا تُنشأ جلسة هاتف حتى ينجح `verifyOtp`.
