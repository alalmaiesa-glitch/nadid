# Partial-Write Recovery & Idempotent Worker Persistence V1

## الهدف

هذه الطبقة تحمي نَضِيد من الانقطاع في منتصف كتابة نتائج Worker إلى قاعدة البيانات.

الهدف أن تكون إعادة المحاولة قابلة للتكرار دون:
- نسخ مكررة.
- اقتراحات عميقة مكررة.
- Analysis Runs مكررة.
- Memory نصف مكتملة تُعرض كـ ready.
- فقد بيانات التحليل العميق بعد نجاح AEE.

## خللان حقيقيان كشفتهما V1

### 1. متغيرات Deep Review غير معرفة

كان Worker يقرأ:

- `memory`
- `chunks`

ثم يستخدم لاحقًا:

- `terms`
- `facts`
- `conflicts`
- `knowledgeItems`

من دون تعريفها. هذا خطأ Runtime لا يكتشفه `node --check`.

تم ربطها صراحة من نتيجة AEE.

### 2. مخرجات Deep Review لا تُخزن

المسار كان يحذف الجداول القديمة عند retry، لكنه لم يُعد إدخال:
- document_chunks
- memory_terms
- fact_assertions
- fact_conflicts
- document_memory_items

تمت إضافة الكتابة الكاملة لكل مجموعة، مع `version_id` وهوية client deterministic.

## استراتيجية الاستعادة

### Initial Review

- إن كانت Version 1 جاهزة: reuse.
- إن كانت موجودة وغير جاهزة: حذفها.
- FK cascade يحذف العقد/الاقتراحات/الحمايات/التحليلات الجزئية.
- تعاد Version 1 من الصفر.
- عند failure بعد إنشاء version تُعلّم `failed`، وسيحذفها retry التالي.

### Deep Review

- document_memory تتحول أولًا إلى `building`.
- كل artifacts العميقة السابقة تُحذف.
- اقتراحات deep القديمة تُحذف.
- Deep analysis run القديم يُستبدل.
- تعاد كتابة كل المخرجات.
- لا تتحول memory إلى `ready` إلا بعد اكتمال artifacts وanalysis run.
- إذا انقطع Worker في المنتصف، retry التالي يعيد clear-then-rebuild.

## Benchmark V1

12 حالة WID-001 إلى WID-012 تغطي:

- bindings الصحيحة لنتيجة Deep AEE.
- وجود الكتابة لكل جدول عميق.
- deterministic identities.
- ترتيب clear → rebuild → ready.
- idempotence بعد retry مرتين.
- تنظيف deep suggestions وdeep run.
- reuse لـ ready memory.
- تنظيف Version جزئية قبل rebuild.
- وسم Version failed عند partial initial write.
- mappings لكل artifact.
- version-scoped writes.
- منع ready قبل اكتمال writes.

## حدود V1

V1 تضمن منطق Worker وRegression Contracts في CI.

اختبار transaction-level atomicity ضد PostgreSQL حي، وحقن crash حقيقي بين كل statement وآخر، يبقى Integration/Fault-Injection Layer لاحقة.
