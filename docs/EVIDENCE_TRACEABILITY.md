# Evidence Traceability & Explainability V1

## الهدف

ألا يكتفي نَضِيد بقول «يوجد خطأ» أو «يوجد تعارض»، بل يستطيع لكل Finding مهم أن يعرض دليلًا يمكن للمستخدم التحقق منه مباشرة.

## ما الذي أصبح متاحًا؟

لكل Suggestion أو Semantic Issue أو Fact Conflict يمكن بناء `EvidenceTrace` يحتوي على:
- نوع الـFinding ومعرّفه.
- الفئة.
- العنوان.
- التفسير.
- درجة الثقة.
- Reason Code ثابت.
- موضع/مواضع الدليل.
- المستند المصدر عند توفره.
- Node ID الأصلي وNamespaced Node ID عند Cross-Document.
- Sequence Number.
- نوع العقدة.
- Structural Location Label.
- Source Anchor.
- Excerpt محدود من النص.
- Evidence Values / القيم المتعارضة.
- حالة `complete` أو `partial`.

## Exact Source Anchors

تم تقوية Parser ليحتفظ بـ `block_index` لكل Paragraph وTable، مع row/cell للخلايا.

هذا لا يغير Stable Node IDs؛ هو Metadata إضافي للتتبع فقط.

## التكامل

- `/v1/analyze/docx/deep` يعيد الآن `evidence_traces` مباشرة.
- `review_document_set()` يعيد Evidence Traces جاهزة للتعارضات داخل المستند وعبر المستندات.
- Cross-Document evidence يحتفظ بـ `document_id` و`original_node_id`.
- إذا فُقد مصدر متوقع، لا يخترع نَضِيد دليلًا؛ تتحول الحالة إلى `partial`.

## Evidence Benchmark V1

12 حالة حاكمة تغطي:
- اقتراح لغوي محلي.
- Definition Conflict.
- Fact Conflict.
- Cross-Document semantic conflict.
- Cross-Document fact conflict.
- Long-Range decision conflict.
- Long-Range fact conflict.
- Table-cell location.
- Paragraph block location.
- Missing suggestion source.
- Missing semantic evidence.
- Cross-document original node identity.

Long-Range evidence يفصل بين الدليلين بأكثر من 400 عقدة.

## النتيجة

- Evidence Benchmark V1: 12/12 = 100%.
- Core Quality Benchmark: 149/149 = 100%.
- Mutation Benchmark V1: 53/53 = 100%.
- Consistency Benchmark V1: 28/28 = 100%.

هذه نسب اجتياز لاختبارات هندسية محددة، وليست Human Precision/Recall.

## قاعدة الإصدار

أي Finding مهم في Deep/Consistency Review يجب أن:
1. يحمل عنوانًا وتفسيرًا وReason Code وConfidence.
2. يرتبط بمصدر قابل للتتبع.
3. يعرض الأدلة المتقابلة عند التعارض.
4. لا يدّعي اكتمال الدليل إذا كان أي Evidence Node مفقودًا.
5. يحافظ على Document/Node identity عبر Cross-Document scopes.
