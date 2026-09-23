# نَضِيد

**نَضِيد — محرر العربية الذكي**

> نصٌّ أدق. سياقٌ أتم.

نَضِيد منصة لتحرير ومراجعة المستندات العربية الطويلة، مع التركيز على التدقيق اللغوي والصياغة، فهم السياق على مستوى المستند، اتساق المصطلحات، وحماية الأرقام والحقائق والمعنى أثناء التحرير.

## بنية المشروع

هذا المستودع هو المصدر الرئيسي والوحيد لنَضِيد:

- `app/` — واجهة Next.js
- `backend/` — محرك AEE المبني بـ FastAPI
- `supabase/` — PostgreSQL + Storage + RLS + migrations
- `lib/` — العقود والموصلات المشتركة
- `.github/workflows/` — اختبارات وبناء CI
- `docs/ARCHITECTURE.md` — المعمارية العامة

## الواجهة الحالية

- الصفحة الرئيسية: `/`
- رفع المستند: `/upload`
- المحرر: `/editor`

## AEE Backend

المحرك الخلفي يدعم حاليًا:

- DOCX Parser
- Node Builder
- Structure-aware Chunker
- Fast Arabic Review
- Protected Spans
- Fact Lock
- Patch Validation
- Document Memory
- Fact Extraction
- Conflict Detection
- Context Retrieval

## تشغيل الواجهة

```bash
npm install
npm run dev
```

ثم:

```
http://localhost:3000
```

## تشغيل AEE

من مجلد `backend/`:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Supabase

تعريف قاعدة البيانات موجود داخل نفس المستودع:

```
supabase/config.toml
supabase/migrations/
```

يمكن تشغيله محليًا عبر Supabase CLI أو ربطه لاحقًا بمشروع Supabase مستضاف خاص بنَضِيد.

## الحالة

GitHub Actions يفحص الواجهة والـBackend عند كل Push.


## الحسابات ومساحة العمل

عند ربط Supabase بالقيم الموجودة في `.env.example`:

- `/login` — تسجيل دخول بدون كلمة مرور عبر البريد.
- `/documents` — مساحة «مستنداتي».
- `/upload` و`/editor` — مسارات محمية للمستخدم المسجل.
- كل مستند يرتبط بـ `owner_id`.
- APIs تتحقق من الملكية قبل القراءة، المراجعة، إنشاء النسخ أو التنزيل.

يجب إضافة رابط التطبيق ورابط `/auth/callback` إلى Redirect URLs المسموح بها في إعدادات Supabase Auth عند النشر.

إذا لم تكن Supabase مفعلة، يبقى وضع التطوير المحلي متاحًا وتُحفظ نتائج التجربة في IndexedDB.
