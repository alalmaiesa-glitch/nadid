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
AEE FastAPI
  ↓
Parser → Nodes → Chunker
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
