# Private Professional Arabic Corpus

هذا المسار مخصص لاختبارات Regression على مستندات عربية مهنية حقيقية، مع قاعدة صارمة: **محتوى المستندات الخاصة لا يدخل المستودع العام**.

## ما يُحفظ محليًا فقط

- ملفات DOCX الأصلية.
- manifest الذي يحوي المسارات المحلية.
- baseline الخاص بكل مستند.
- تقارير التشغيل التفصيلية.

كلها مستبعدة عبر `.gitignore`.

## ما يجوز رفعه للمستودع

- مشغل الاختبار.
- سياسة الخصوصية والمنهجية.
- حالات مشتقة ومنزوعة الهوية من مشكلات اكتُشفت أثناء الاختبار.
- أرقام إجمالية لا تكشف محتوى المستندات.

## التشغيل

أنشئ ملفًا محليًا مثل:

```json
{
  "documents": [
    {"path": "/secure/path/document-1.docx"},
    {"path": "/secure/path/document-2.docx"}
  ]
}
```

ثم:

```bash
PYTHONPATH=backend python benchmark/run_corpus_regression.py \
  --manifest benchmark/corpus/private/manifest.json \
  --report benchmark/corpus/reports/latest.json \
  --write-baseline benchmark/corpus/private/baseline.json
```

وفي التشغيلات اللاحقة:

```bash
PYTHONPATH=backend python benchmark/run_corpus_regression.py \
  --manifest benchmark/corpus/private/manifest.json \
  --report benchmark/corpus/reports/latest.json \
  --baseline benchmark/corpus/private/baseline.json
```

## ما يقيسه الاختبار

- قدرة Parser على قراءة المستند كاملًا.
- ثبات عدد العقد والبنية.
- استقرار Suggestion IDs وProtected IDs وMemory IDs وSemantic Issue IDs.
- عدم حدوث انفجار مفاجئ في عدد الاقتراحات.
- أعداد الحماية والحقائق والذاكرة والمشكلات الدلالية.
- سلامة تشغيل المحرك على مستندات طويلة وكثيفة الجداول.

هذه الطبقة تكمل الـBenchmark المصطنع ولا تستبدله: الاختبارات الدقيقة الصغيرة تكتشف السبب، والـCorpus الواقعي يكتشف أثر التغييرات على مستند مهني كامل.
