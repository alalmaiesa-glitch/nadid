# مصادقة نَضِيد

يدعم التطبيق ثلاث طرق لإنشاء الحساب والدخول:

1. Google OAuth.
2. رقم الجوال عبر رمز SMS لمرة واحدة.
3. البريد الإلكتروني وكلمة المرور.

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

يحتاج Phone Auth إلى مزود SMS مدعوم ومفعّل في Supabase Auth.
واجهة نَضِيد تقبل الرقم السعودي بصيغ مثل:

- `05xxxxxxxx`
- `5xxxxxxxx`
- `9665xxxxxxxx`
- `+9665xxxxxxxx`

ويتم تحويله داخليًا إلى E.164 قبل إرسال OTP.

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
