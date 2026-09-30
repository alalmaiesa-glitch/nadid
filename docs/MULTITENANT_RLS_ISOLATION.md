# Multi-Tenant RLS & Ownership Isolation V1

## الهدف

هذه الطبقة تختبر عزل بيانات مستخدمي نَضِيد على PostgreSQL/Supabase فعلي محلي داخل CI.

لا يكفي أن تحتوي migrations على عبارة `enable row level security`; المطلوب إثبات أن مستخدمًا لا يستطيع رؤية بيانات مستخدم آخر عبر كامل شجرة المستند.

## نطاق V1

يتم إنشاء مستخدمين ومستندين مستقلين، ثم تعبئة البيانات التابعة في:

- documents
- document_versions
- document_nodes
- suggestions
- protected_spans
- analysis_runs
- document_chunks
- document_memory
- memory_terms
- fact_assertions
- fact_conflicts
- document_memory_items

## الحراس

- المستخدم الأول يرى صفوفه فقط عبر جميع الجداول.
- lookup مباشر لمستند المستخدم الثاني لا يعيد صفًا.
- UPDATE على مستند مستخدم آخر يصبح no-op بفعل RLS.
- UPDATE للمستند المملوك مسموح.
- anon لا يرى بيانات المستخدمين.
- service_role يحتفظ بالوصول الخادمي الذي يحتاجه Worker.
- كل الاختبارات تنفذ على قاعدة CI محلية وتُنظف بياناتها في النهاية.

## حدود V1

هذه الطبقة تركز على RLS للقراءة وملكية المستندات والمسار الأساسي للتحديث.

اختبارات REST/JWT end-to-end عبر PostgREST، ومحاولات INSERT/UPDATE السلبية مع التقاط SQLSTATE لكل جدول، يمكن توسيعها في V2.
