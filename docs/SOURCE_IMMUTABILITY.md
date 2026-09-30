# Upload Lifecycle Integrity & Source Immutability V1

## الهدف

مسار الرفع في نَضِيد يستخدم Signed Upload URL إلى Storage مباشرة. بعد المعالجة الأولى تُحفظ بصمة SHA-256 للمصدر داخل `document_versions.source_sha256`.

الخطر الذي تغلقه هذه الطبقة هو TOCTOU:

1. يرفع المستخدم ملفًا.
2. يعالجه Worker ويعتمد Version 1.
3. يتغير الملف في نفس Storage path لاحقًا، سواء بإعادة استخدام رابط رفع قديم أو بأي مسار إداري غير مقصود.
4. Deep Review أو Export يقرأ bytes مختلفة عن المصدر الذي بُنيت عليه النسخة.

## قاعدة V1

بمجرد أن تكون نسخة المستند `ready` وتملك `source_sha256`، تصبح البصمة مرجع المصدر.

أي قراءة لاحقة للمصدر يجب أن:

- تنزّل bytes.
- تحسب SHA-256.
- تقارنها بـ `source_sha256`.
- تتوقف قبل أي Deep Review أو Export إذا اختلفت.

## الحماية

### Worker deep review

`processDeepReview` يقرأ `source_sha256` مع النسخة، ثم يتحقق من الملف قبل استدعاء AEE Deep.

عند الاختلاف:

`source_integrity_mismatch`

ولا يبدأ التحليل العميق.

### Server downloads / export

`loadDocumentSource` و`downloadDocumentVersion` يطبقان الحارس نفسه.

مسار Export يحول الخطأ إلى:

- HTTP 409
- `SOURCE_INTEGRITY_MISMATCH`

بدل تنزيل ملف لا يطابق النسخة المعتمدة.

## Benchmark

`SRC-001..SRC-010` تتحقق من:

- وجود حارس مركزي للبصمة.
- ربط loadDocumentSource بالبصمة.
- ربط downloadDocumentVersion بالبصمة.
- عقد 409 للتصدير.
- ربط Worker Deep بالبصمة.
- تنفيذ الحارس قبل callAeeDeep.
- حفظ بصمة المصدر في Initial Review.
- كشف mutation فعلي في نموذج SHA-256.
- determinism للبصمة.
- fail-closed عند عدم التطابق.

هذه الطبقة لا تعتمد على انتهاء صلاحية Signed Upload URL؛ بل تحمي المستند حتى لو تغير Storage object لاحقًا.
