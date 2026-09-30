# Review Action Policy & Auto-Apply Safety V1

## الهدف

تحويل نتائج نَضِيد من مجرد `Severity + Confidence` إلى قرار تشغيلي واضح لكل Finding:

- `auto_fix`
- `suggest`
- `require_review`
- `block`

مع قاعدة حاكمة: **ارتفاع الثقة وحده لا يكفي للتطبيق التلقائي**.

## Auto-Fix Gate

لا يسمح نَضِيد بـ `auto_fix` إلا عندما تتحقق جميع الشروط التالية:

1. Finding من نوع `suggestion`.
2. الفئة `language` فقط.
3. Evidence Trace مكتمل.
4. يوجد Original + Replacement واضحان.
5. Meaning Lock = `PASS`.
6. `strong_assertion = true`.
7. Operational Confidence >= 0.93.
8. Severity ليست `high` أو `critical`.

أي شرط مفقود يمنع التطبيق التلقائي.

## القرارات

### Auto Fix
محجوز للتصحيحات اللغوية الحتمية عالية الثقة التي اجتازت Meaning Lock.

أمثلة:
- مسافة زائدة قبل علامة ترقيم.
- رسم إملائي حتمي مثل «هاذا» → «هذا»، إذا لم يمس معنى محميًا.

### Suggest
ملاحظة يمكن عرضها للمستخدم لكنها لا تطبق تلقائيًا.

أمثلة:
- Style.
- Language مكتمل لكن Confidence دون حد Auto-Fix.
- Language لم يُنفذ عليه Meaning Lock بعد (`UNKNOWN`).

### Require Review
يحتاج حكم المستخدم أو مراجع متخصص.

أمثلة:
- Semantic Conflict.
- Fact Conflict.
- Partial Evidence.
- Finding بلا Replacement جاهز.
- Findings عالية الأثر التي لا يجوز تطبيقها تلقائيًا.

### Block
النظام يمنع التعديل الآلي.

أمثلة:
- Meaning Lock = `BLOCK`.
- Protection / Meaning Safety finding.

## Safe Auto-Apply Planner

أضيف `build_safe_auto_apply_plan()`.

وظيفته:
1. يبني Evidence + Confidence + Severity + Action لكل اقتراح.
2. يأخذ فقط `auto_apply_allowed = true`.
3. يعيد تشغيل Meaning Lock **مرة ثانية بالتتابع** قبل بناء Patch.
4. إذا جعل تعديل سابق اقتراحًا لاحقًا Stale، يتم تخطيه بدل تطبيقه على نص تغير.
5. لا يطبق Style أو Consistency أو Semantic/Fact Conflicts تلقائيًا.

هذه الإعادة المتتابعة مهمة لأن صلاحية اقتراح في النص الأصلي لا تعني أنه ما زال صالحًا بعد تعديل سابق في العقدة نفسها.

## Deep Analysis

`/v1/analyze/docx/deep` يعيد الآن داخل كل Evidence Trace:

- `recommended_action`
- `auto_apply_allowed`
- `meaning_lock_status`
- `action_reasons`

وبالتالي يمكن للواجهة عرض القرار دون إعادة اختراع قواعد السلامة في Frontend.

## Benchmark V1

20 حالة حاكمة تغطي:

- punctuation auto-fix
- orthography auto-fix
- style suggest
- semantic require-review
- fact require-review
- partial evidence require-review
- Meaning Lock block
- unknown Meaning Lock
- missing replacement
- low-confidence language
- protection block
- high-confidence style never auto
- safe-only auto planner
- dangerous meaning-change planner
- stale sequential revalidation
- high semantic/fact never auto
- action reason presence
- auto flag/action equivalence
- safe punctuation inside critical clause

## النتيجة

- Review Action & Auto-Apply Benchmark V1: **20/20 = 100%**
- Core Quality Benchmark: **149/149 = 100%**
- Mutation Benchmark V1: **53/53 = 100%**
- Consistency Benchmark V1: **28/28 = 100%**
- Evidence Benchmark V1: **12/12 = 100%**
- Confidence & Severity Benchmark V1: **18/18 = 100%**

هذه نتائج اختبارات هندسية، وليست Human Precision/Recall.

## قاعدة الإصدار

لا يجوز لأي مسار Auto-Apply أن يتجاوز هذه السياسة أو يطبق Patch مباشرة دون:
1. Action Policy.
2. Meaning Lock PASS.
3. Sequential revalidation.
4. Complete evidence.
5. Concrete replacement.
