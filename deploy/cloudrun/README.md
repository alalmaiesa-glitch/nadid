# نشر نَضِيد على Google Cloud Run

المنطقة المعتمدة للحوسبة هي `asia-south1` (Mumbai) لتكون بجوار Supabase نَضِيد في Mumbai.

## الموارد

- `nadid-web` — Cloud Run Service للواجهة وواجهات Next.js.
- `nadid-aee` — Cloud Run Service لمحرك AEE.
- `nadid-worker` — Cloud Run Worker Pool لمعالجة الطابور.
- Artifact Registry باسم `nadid`.
- Secret Manager للأسرار الخادمية.

## الأسرار

لا تحفظ القيم في GitHub أو ملفات `.env` المرفوعة.

الأسماء المستخدمة:

- `nadid-supabase-service-role`
- `nadid-aee-internal-token`

يمكن تشغيل `bootstrap-secrets.sh` محليًا؛ يطلب القيم دون إظهارها على الشاشة.

## البناء

`cloudbuild.yaml` يبني الصور الثلاث ويرفعها إلى Artifact Registry.

المفتاح `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` ليس سرًا، لذلك يمر كـ build substitution.

## النشر

بعد تسجيل الدخول إلى gcloud:

```bash
export GCP_PROJECT_ID="YOUR_PROJECT_ID"
export SUPABASE_PUBLISHABLE_KEY="sb_publishable_..."
bash deploy/cloudrun/bootstrap-secrets.sh
bash deploy/cloudrun/deploy.sh
```

لا تنفذ النشر قبل مراجعة التكلفة واعتماد مشروع Google Cloud.

## ملاحظات أمان

واجهة AEE لها عنوان HTTPS، لكن كل `/v1/*` يتطلب `AEE_INTERNAL_TOKEN`. مسار `/health` فقط غير محمي لقياس صحة الحاوية.

الـWorker Pool بلا endpoint عام.

بعد النشر يجب أن يعيد:

`GET /api/health/ready`

حالة `ready` قبل بدء أي Beta.
