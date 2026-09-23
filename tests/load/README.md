# اختبارات الضغط لنَضِيد

لا تُشغَّل هذه الاختبارات على ملفات المستخدمين أو على بيئة Production قبل اعتماد نافذة اختبار.

## AEE

المتطلبات:

```bash
cd backend
pip install -r requirements.txt
```

ثم من جذر المستودع:

```bash
export AEE_BACKEND_URL="https://AEE_URL"
export AEE_INTERNAL_TOKEN="..."
python tests/load/aee_load.py \
  --requests 20 \
  --concurrency 5 \
  --paragraphs 250
```

المخرجات تشمل:

- success/error rate
- p50
- p95
- p99
- mean latency

بوابة Beta المبدئية:

- error rate <= 1%
- لا crash أو OOM
- p95 ضمن الحد المتفق عليه للحجم المختبر
- جميع الوظائف الفاشلة يمكن إعادة محاولتها دون تكرار بيانات

نرفع الاختبار تدريجيًا: 5 ثم 10 ثم 25 ثم 50 عملية متزامنة، ولا ننتقل للمستوى التالي إذا فشل المستوى السابق.
