# Derived Version Lineage & Orphan-Safe Persistence V1

## الهدف

نَضِيد لا يكتفي بحفظ ملفات متعددة باسم «نسخ». كل نسخة مشتقة يجب أن تكون قابلة للإثبات كسليل مباشر للنسخة السابقة، وألا ينشأ ملف Storage بلا سجل قاعدة بيانات عند فشل إنشاء النسخة.

## العقد المعتمد

سلسلة النسخ خطية:

- Version 1 هي Source Root:
  - `is_source = true`
  - `parent_version_id = null`
- كل Version > 1:
  - `is_source = false`
  - لها Parent إلزامي.
  - Parent من المستند نفسه.
  - `parent.version_no = child.version_no - 1`

هذا العقد يُفرض بطبقتين:

1. Runtime قبل الإنشاء.
2. PostgreSQL Trigger مستقل عن التطبيق.

## منع السباق

قبل إنشاء نسخة مشتقة، يعيد Server قراءة أحدث نسخة `ready`.

إذا لم تعد هي نفس `parentVersionId / parentVersionNo` التي بُنيت منها الـpatches، يفشل الطلب بـ:

- HTTP 409
- `VERSION_CHANGED`

وهذا يمنع طلبًا بطيئًا من إنشاء نسخة جديدة فوق Parent قديم بعد أن سبقته عملية أخرى.

## Persistence Order

المسار السابق كان:

> Storage upload → DB version insert

وبالتالي يمكن لفشل DB بعد نجاح Storage أن يترك object يتيمًا.

V1 تعتمد:

> validate lineage → reserve DB row as `creating` → Storage upload → persist analysis → mark `ready`

إذا فشل Storage أو التحليل، تبقى النسخة كسجل `failed` بدل وجود ملف مجهول بلا سجل.

عند إعادة المحاولة على نفس Version Number:

- إذا كانت الخانة `failed`، ينظف نَضِيد Storage المشار إليه أولًا.
- يحذف سجل النسخة الفاشلة.
- ثم يعيد المحاولة.
- إذا تعذر التنظيف، يتوقف بـ `VERSION_CLEANUP_FAILED` بدل صناعة orphan جديد.

## مسارات النسخ المشتقة

كل Derived Version تستخدم مسارًا:

`{owner}/{document}/versions/v{N}/{sha256}/source.docx`

المسار:

- Owner-scoped.
- Document-scoped.
- Version-scoped.
- Content-addressed.

وهذا يجعل orphan cleanup القائم على Owner prefix قادرًا على اكتشاف أي بقايا أيضًا.

## Auditability

قائمة النسخ تعرض بالإضافة إلى رقم النسخة:

- `parentVersionId`
- `sourceSha256`
- `changeSummary`

وبذلك يستطيع النظام لاحقًا بناء Audit Trail كامل من النسخة الحالية حتى Source Root.

## قاعدة البيانات

Migration `0026_document_version_lineage.sql` تضيف Trigger يمنع:

- Source version غير رقم 1.
- Source version لها Parent.
- Derived version بلا Parent.
- Parent من مستند آخر.
- تخطي Parent version.

ويفشل الـdeployment إذا اكتشف تاريخ نسخ موجودًا يخالف العقد، بدل اعتماد lineage مكسور بصمت.

## Benchmark

`VER-001..VER-015` تحمي:

- Trigger contract.
- Source root rules.
- Same-document parent.
- Immediate-parent rule.
- Runtime latest-parent guard.
- Sequential version number.
- Failed-slot cleanup.
- Owner/content-addressed storage.
- DB reservation before Storage.
- DB conflict normalization.
- ready-after-persistence ordering.
- partial failure state.
- HTTP conflict contract.
- lineage visibility.
- deterministic derived paths.

كما يعمل `supabase/tests/document_version_lineage.sql` ضد PostgreSQL المحلي في CI للتحقق من القيود فعليًا.
