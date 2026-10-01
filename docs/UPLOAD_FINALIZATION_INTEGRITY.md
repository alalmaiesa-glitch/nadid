# Upload Finalization & Signed Upload Replay V1

## الهدف

الرفع المباشر إلى Supabase Storage يتم برابط موقّع. لذلك يجب ألا تكون صلاحية رابط الرفع هي الحارس الوحيد بين لحظة اكتمال الرفع وبدء Worker.

عند finalize يقوم نَضِيد الآن بتنزيل المصدر من Storage، حساب SHA-256، وتثبيت البصمة في documents.upload_sha256 مع upload_finalized_at قبل إدخال المهمة للطابور.

إذا تكرر finalize:
- الملف نفسه: يسمح بالاستمرار idempotently.
- bytes مختلفة: upload_integrity_mismatch.
- عمليتا finalize متزامنتان: update الشرطي على upload_sha256 IS NULL يجعل أول بصمة مثبتة هي المرجع، ثم تعيد العملية الأخرى قراءة البصمة وتقارنها.

Worker initial review يعيد حساب SHA-256 قبل استدعاء AEE. إذا تغير Storage object بعد finalize، تتوقف المهمة قبل التحليل.

API يحول اختلاف المصدر إلى HTTP 409 / UPLOAD_INTEGRITY_MISMATCH. كما يمنع finalize في حالات deleting و delete_failed.

UPL-001..UPL-012 تحمي migration contract، تثبيت البصمة، CAS/concurrency، ترتيب pin-before-queue، Worker replay guard، route conflicts، ونموذج replay deterministic.
