# نشر نَضِيد

نَضِيد يتكون من أربع خدمات مستقلة:

1. **Web — Next.js**
2. **AEE — FastAPI**
3. **Worker — معالج مستندات خلفي دائم**
4. **Data — Supabase PostgreSQL + Storage + Auth**

## الواجهة

يمكن ربط المستودع مباشرة بـ Vercel.

متغيرات البيئة المطلوبة:

```env
NEXT_PUBLIC_SUPABASE_URL=https://jcyfhfpulckpsdaiecoe.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
AEE_BACKEND_URL=
AEE_INTERNAL_TOKEN=
NEXT_PUBLIC_APP_URL=
```

لا يوضع `SUPABASE_SERVICE_ROLE_KEY` في أي متغير يبدأ بـ `NEXT_PUBLIC_`.

## AEE

يوجد Dockerfile في `backend/Dockerfile`.

```bash
docker build -t nadid-aee ./backend
docker run --rm -p 8000:8000 nadid-aee
```

Health check: `GET /health`.

جميع مسارات `/v1/*` محمية في الإنتاج بـ `AEE_INTERNAL_TOKEN`. يجب وضع القيمة نفسها في بيئة Next.js وبيئة حاوية AEE. يبقى `/health` عامًا لمراقبة الخدمة.

بعد نشر الحاوية يوضع عنوانها في `AEE_BACKEND_URL`.

## Supabase

مشروع الإنتاج المعتمد لنَضِيد:

- Project Ref: `jcyfhfpulckpsdaiecoe`
- Region: `ap-south-1` — Mumbai
- URL: `https://jcyfhfpulckpsdaiecoe.supabase.co`

نفّذ migrations بالترتيب من `supabase/migrations/` وتأكد من أن bucket `nadid-documents` خاص Private. المدفوعات مؤجلة، لذلك لا تعتمد migration `0008_billing_foundation.sql` ضمن إطلاق V1 الحالي.

في Supabase Auth أضف `https://YOUR_DOMAIN/auth/callback` إلى Redirect URLs، ومع التطوير `http://localhost:3000/auth/callback`.

## مسار رفع الملفات

```text
Browser
  → signed upload token
  → Supabase Private Storage
  → finalize-upload
  → processing_jobs
  → Worker
  → AEE
  → PostgreSQL
  → Editor
```

الملفات حتى 6 MB تستخدم signed upload المباشر. الملفات الأكبر تستخدم TUS resumable upload بأجزاء 6 MB.

لا يُفضّل تشغيل AEE داخل Serverless Function قصيرة العمر لمعالجة المستندات الكبيرة؛ يُشغّل كخدمة container، ثم يضاف worker queue عند الانتقال للمعالجة غير المتزامنة واسعة النطاق.


## Worker

العامل الخلفي موجود في:

`worker/index.mjs`

ويُبنى من:

`worker/Dockerfile`

المتغيرات المطلوبة:

```env
SUPABASE_URL=https://jcyfhfpulckpsdaiecoe.supabase.co
SUPABASE_SERVICE_ROLE_KEY=
AEE_BACKEND_URL=
AEE_INTERNAL_TOKEN=
WORKER_ID=
WORKER_POLL_INTERVAL_MS=2000
```

العامل يطالب بالوظائف ذريًا عبر `claim_processing_job`، ويعيد الوظائف العالقة بعد مهلة القفل، ويكتب heartbeat كل 30 ثانية.

## Production readiness

المسار:

`GET /api/health/ready`

لا يعيد HTTP 200 إلا عندما تكون:

- إعدادات الإنتاج الأساسية مكتملة.
- قاعدة البيانات قابلة للوصول.
- خدمة AEE سليمة.
- يوجد Worker حي خلال آخر دقيقتين.

كما يعيد أعداد الوظائف `queued / processing / failed` للمراقبة التشغيلية.
