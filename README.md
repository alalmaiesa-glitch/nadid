# نَضِيد

**نَضِيد — محرر العربية الذكي**

> نص أدق. سياق أتم.

نَضِيد منصة لتحرير ومراجعة المستندات العربية الطويلة، مع التركيز على التدقيق اللغوي والصياغة، فهم السياق على مستوى المستند، اتساق المصطلحات، وحماية الأرقام والحقائق والمعنى أثناء التحرير.

## سياسة صيغ المستندات

نَضِيد ليس محرر DOCX فقط. المبدأ المعتمد هو: **قبول أي مستند يمكن استخراج محتواه وبنيته منه بصورة موثوقة وآمنة**، ثم تحويله إلى نموذج مستند موحّد قبل دخوله إلى محرك AEE.

النطاق المستهدف للاستيراد يشمل، متى توفّر محوّل موثوق لكل صيغة:

- DOCX
- PDF النصي
- PDF الممسوح ضوئيًا عبر OCR
- ODT
- RTF
- TXT
- Markdown
- HTML
- EPUB
- PPTX لاستخراج ومراجعة النصوص داخل الشرائح
- ويمكن دعم صيغ أخرى لاحقًا عبر File Adapters دون تغيير محرك المراجعة نفسه.

XLSX وCSV يعاملان كبيانات جدولية؛ ويمكن مراجعة النصوص داخل الخلايا مع حماية الأرقام والصيغ، لكنهما ليسا مستندين تحريريين بالمعنى نفسه.

**الاستيراد والمعالجة لا يعنيان بالضرورة إعادة التصدير بنفس الصيغة الأصلية.** الأصل يبقى محفوظًا، وخيارات التصدير تعتمد على قدرة نَضِيد على الحفاظ على البنية والتنسيق بأمان.

راجع `docs/FILE_FORMATS.md` للتفاصيل.

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

المحرك الخلفي يدعم حاليًا مسار DOCX تشغيليًا، ويجري توسيع الإدخال إلى بنية متعددة الصيغ عبر File Adapters:

- File Adapter Layer
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
