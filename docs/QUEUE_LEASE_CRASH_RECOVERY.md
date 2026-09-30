# Queue Lease, Retry & Crash Recovery V1

## الهدف

بعد إضافة Backpressure داخل AEE، يجب ضمان أن طابور المعالجة نفسه يتعافى من:

- توقف Worker أثناء job.
- توقفه في المحاولة الأخيرة.
- jobs طويلة تتجاوز مدة stale threshold.
- Worker قديم يحاول إنهاء job بعد انتقال ملكيتها إلى Worker آخر.
- فشل متكرر ثم إعادة المحاولة.

## الثغرات التي أغلقتها V1

### 1. Final-attempt orphan

قبل V1 كان `claim_processing_job` يبحث فقط عن:

`attempts < max_attempts`

إذا مات Worker بعد حجز المحاولة الأخيرة تصبح:

- status = processing
- attempts = max_attempts

وبعد انتهاء lease لا يمكن إعادة حجزها، ولا تتحول تلقائيًا إلى failed.

V1 تجني هذه jobs بعد انتهاء lease وتحوّلها إلى `failed` مع تحرير القفل.

حالة المستند:

- initial_review → `failed`
- deep_review → `partial_ready`

### 2. Long-running duplicate claim

الـlease القديمة كانت تعتمد فقط على `locked_at` وقت claim. إذا استغرق job أكثر من 15 دقيقة، يستطيع Worker آخر اعتباره stale رغم أن Worker الأول ما زال يعمل.

V1 تضيف:

`renew_processing_job_lease(job_id, worker_id)`

والـWorker يجدد lease دوريًا أثناء المعالجة.

### 3. Stale-worker fencing

إغلاق job أو تسجيل فشلها الآن مشروط بـ:

- status = processing
- locked_by = WORKER_ID

وبذلك لا يستطيع Worker فقد الملكية ثم يعود متأخرًا ويكتب complete/failed فوق عمل Worker أحدث.

## Benchmark

12 حالة QRC-001 إلى QRC-012:

- reclaim لمحاولة stale ما زالت قابلة للإعادة.
- إنهاء final-attempt orphan.
- سياسة deep_review عند انتهاء المحاولات.
- عدم سرقة lease حديثة.
- احترام available_at.
- زيادة attempts عند claim.
- lease renewal للمالك.
- رفض renewal من Worker آخر.
- completion للمالك.
- منع stale completion.
- Contract checks لمهاجرة SQL.
- Contract checks للـWorker fencing/renewal.

## حدود V1

هذه الطبقة تثبت state-machine والسياسات البرمجية في CI وتضيف migration حقيقية لـPostgreSQL.

اختبار عدة Workers فعليين ضد Supabase/Postgres حي يبقى Integration Layer لاحقة، لأن CI الحالي لا يشغّل Supabase محليًا.
