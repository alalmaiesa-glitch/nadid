# Confidence Calibration & Severity V1

## الهدف

تمييز **أهمية المشكلة** عن **قوة الثقة في الحكم**.

في نَضِيد لا تعني الثقة العالية أن المشكلة حرجة، ولا تعني الخطورة العالية أن الدليل كافٍ لعرض الحكم بصيغة جازمة.

لذلك تفصل V1 بين محورين مستقلين:

- **Severity:** `critical / high / medium / low`
- **Operational Confidence:** رقم من 0 إلى 1 مع مستوى `high / medium / low`

كما يوجد حقل مستقل:
- `strong_assertion: true/false`

ولا يُسمح بالصياغة القوية إلا عند اجتياز بوابة الدليل.

## تنبيه مهم

`confidence` في V1 هو **Operational Policy Score**، وليس احتمال صحة معايرًا إحصائيًا.

لا يجوز وصفه بأنه "احتمال أن الحكم صحيح" أو "دقة 94%" حتى تتوفر Human Gold labels كافية لإجراء Calibration تجريبي فعلي.

يحفظ نَضِيد كذلك:
- `source_confidence`: الثقة الأصلية من القاعدة/المحرك.
- `calibration_method = policy_v1_unvalidated`
- `calibration_reasons`: لماذا تم رفع/خفض/تقييد الدرجة.

## Severity Policy

### Critical
محجوز حاليًا لحالات **Protection / Meaning Safety** المكتملة الدليل فقط، مع Confidence >= 0.95.

لا يمكن لملاحظة لغوية أو أسلوبية أن تصبح Critical.

### High
يستخدم للتعارضات عالية الأثر ذات الدليل الكافي، مثل:
- Fact Conflict موثق من جهتين.
- Decision Conflict.
- Polarity Conflict.
- Protection finding موثق لكن دون شروط Critical الكاملة.

### Medium
يستخدم عادةً لـ:
- Language findings.
- Definition / Abbreviation conflicts.
- Findings عالية الأثر لكن دليلها جزئي أو غير كافٍ للجزم.

### Low
يستخدم عادةً لـ:
- Style findings.
- Language findings منخفضة الثقة.
- ملاحظات تحسين لا تمس سلامة المعنى.

## Confidence Calibration V1

سياسة V1 محافظة عمدًا:

- Partial أو Insufficient Evidence => cap عند 0.59.
- Style => cap عند 0.79.
- Deterministic Language Rule => cap عند 0.94.
- Definition/Abbreviation semantic conflict => cap عند 0.93.
- Decision/Polarity semantic conflict => cap عند 0.96.
- Complete Fact Conflict => boost محدود +0.02 وبحد أقصى 0.95.
- Complete Protection evidence => cap عند 0.99.

### Confidence Levels
- High: >= 0.90
- Medium: >= 0.70
- Low: < 0.70

## Strong Assertion Gate

لا يظهر الحكم بصيغة قوية إلا إذا:
1. Evidence Trace = complete.
2. Evidence كافٍ حسب نوع الـFinding.
3. Calibrated Confidence >= 0.90.
4. Finding ليس Style.

### Evidence Sufficiency
- Suggestion: موضع دليل واحد على الأقل + قيمة/تحويل موثق.
- Semantic Issue: موضعان على الأقل + قيمتا دليل على الأقل.
- Fact Conflict: موضعان على الأقل + قيمتان متعارضتان على الأقل.

أي نقص يخفض الثقة ويمنع `strong_assertion`.

## ترتيب العرض

ترتب Evidence Traces افتراضيًا حسب:
1. Critical
2. High
3. Medium
4. Low
ثم Strong Assertions أولًا، ثم Confidence.

## Benchmark V1

18 حالة حاكمة تغطي:
- High-confidence language.
- Style cap.
- Definition conflict.
- Decision conflict.
- Polarity conflict.
- Fact conflict.
- Partial semantic evidence.
- Partial language evidence.
- Complete protection => Critical.
- Partial protection => downgrade.
- Low-confidence language.
- Partial fact evidence.
- Style raw confidence = 1.0.
- Semantic issue with insufficient locations رغم trace_status=complete.
- منع Critical خارج Protection.
- Severity ordering.
- Calibration method marker.
- Preservation of source confidence.

## النتيجة

- Confidence & Severity Benchmark V1: 18/18 = 100%.
- Core Quality Benchmark: 149/149 = 100%.
- Mutation Benchmark V1: 53/53 = 100%.
- Consistency Benchmark V1: 28/28 = 100%.
- Evidence Benchmark V1: 12/12 = 100%.

هذه نتائج اختبارات هندسية، وليست Human Precision/Recall ولا empirical probability calibration.

## قاعدة الإصدار

أي تعديل لاحق يجب ألا:
1. يسمح بـ Critical خارج سياسة الحماية المعتمدة.
2. يسمح بـ Strong Assertion مع Partial/Insufficient Evidence.
3. يرفع Style إلى Strong Assertion.
4. يخفي source_confidence الأصلية.
5. يقدم Operational Confidence للمستخدم على أنها Probability قبل Human Calibration.
