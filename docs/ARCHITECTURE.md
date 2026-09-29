# بنية نَضِيد

هذا المستودع هو المصدر الرئيسي والوحيد للمشروع.

## المكونات

- `app/` — واجهة Next.js
- `backend/` — محرك AEE المبني بـ FastAPI
- `supabase/` — قاعدة البيانات، التخزين، وسياسات RLS وMigrations
- `.github/workflows/` — CI
- `lib/` — العقود والموصلات المشتركة

## المسار التشغيلي

```
Browser
  ↓
Next.js
  ↓
File Type Detection
  ↓
File Adapter (DOCX / PDF / ODT / RTF / TXT / MD / HTML / EPUB / PPTX / ...)
  ↓
Normalized Document Model
  ↓
AEE FastAPI
  ↓
Nodes → Chunker
  ↓
Fast Review
  ↓
Document Memory
  ↓
Fact Extractor
  ↓
Fact Lock
  ↓
Context Retrieval
  ↓
Deep Review
  ↓
Supabase PostgreSQL + Storage
```

## قاعدة البيانات

ملفات SQL المعتمدة توجد في:

```
supabase/migrations/
```

ولا توجد قاعدة بيانات منفصلة داخل مستودع آخر.

يمكن تشغيل بيئة Supabase محليًا عبر Supabase CLI، أو ربط المستودع لاحقًا بمشروع Supabase مستضاف مستقل خاص بنَضِيد.

## طبقة إدخال المستندات

المبدأ المعماري المعتمد هو:

Source File → Type Detection → Format-specific Adapter → Normalized Document Model → AEE

لا يعتمد محرك AEE على صيغة الملف الأصلية. مسؤولية كل Adapter هي استخراج ما يمكن من:
- العناوين والفقرات والقوائم
- الجداول والخلايا
- الصفحات أو الشرائح عند توفرها
- الحواشي والملاحظات عند توفرها
- بيانات المصدر اللازمة لإرجاع التعديلات أو التصدير

ويحتفظ النموذج الموحّد بـ `source_type` و`source_anchor` حتى يمكن تتبع كل عقدة إلى موضعها في الملف الأصلي.

### PDF

- PDF نصي: استخراج النص والبنية مباشرة.
- PDF مصور/ممسوح: يمر عبر OCR قبل التطبيع.
- يجب إظهار حالة الثقة/جودة الاستخراج للمستخدم عندما يكون المحتوى ناتجًا عن OCR.

### التصدير

الاستيراد متعدد الصيغ لا يفرض دعم التصدير بنفس الصيغة. DOCX يظل أفضل صيغة لإعادة بناء مستند قابل للتحرير. يمكن تقديم DOCX وPDF وTXT كخيارات تصدير بحسب مستوى الحفاظ على البنية، مع إبقاء الملف الأصلي محفوظًا دائمًا.
