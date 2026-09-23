# نشر نَضِيد

نَضِيد يتكون من ثلاث خدمات مستقلة:

1. **Web — Next.js**
2. **AEE — FastAPI**
3. **Data — Supabase PostgreSQL + Storage + Auth**

## الواجهة

يمكن ربط المستودع مباشرة بـ Vercel.

متغيرات البيئة المطلوبة:

```env
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
AEE_BACKEND_URL=
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

بعد نشر الحاوية يوضع عنوانها في `AEE_BACKEND_URL`.

## Supabase

نفّذ migrations بالترتيب من `supabase/migrations/` وتأكد من أن bucket `nadid-documents` خاص Private.

في Supabase Auth أضف `https://YOUR_DOMAIN/auth/callback` إلى Redirect URLs، ومع التطوير `http://localhost:3000/auth/callback`.

## مسار رفع الملفات

```text
Browser
  → signed upload token
  → Supabase Storage
  → finalize-upload
  → AEE
  → PostgreSQL
  → Editor
```

الملفات حتى 6 MB تستخدم signed upload المباشر. الملفات الأكبر تستخدم TUS resumable upload بأجزاء 6 MB.

لا يُفضّل تشغيل AEE داخل Serverless Function قصيرة العمر لمعالجة المستندات الكبيرة؛ يُشغّل كخدمة container، ثم يضاف worker queue عند الانتقال للمعالجة غير المتزامنة واسعة النطاق.
