# Finalized Source Promotion & Storage TOCTOU V1

## الهدف

طبقة Upload Finalization V1 تثبت SHA-256 قبل queue، والـWorker يعيد التحقق قبل AEE. هذا يمنع تحليل bytes مبدلة، لكنه يترك المصدر القانوني في نفس Storage object الذي استُخدم معه signed upload token حتى يبدأ الـWorker.

هذه الطبقة تزيل هذا الاعتماد.

## النموذج الجديد

عند finalize:

1. ينزل نَضِيد bytes من مسار الرفع.
2. يحسب SHA-256.
3. يبني مسارًا نهائيًا content-addressed:
   `{owner}/{document}/finalized/{sha256}/source.docx`
4. يرفع **نفس bytes التي تم حساب بصمتها** Server-side إلى المسار النهائي مع `upsert:false`.
5. إذا كان المسار النهائي موجودًا مسبقًا، ينزله نَضِيد ويتحقق من SHA بدل الكتابة فوقه.
6. يثبت في صف documents، بعملية CAS:
   - `upload_sha256`
   - `upload_finalized_at`
   - `storage_path` الجديد
7. لا يدخل initial review إلى queue إلا بعد التحقق من وجود canonical object.

وبذلك يبقى signed upload token القديم مرتبطًا بمسار الرفع السابق، بينما الـWorker يقرأ فقط canonical path المخزن في documents.

## لماذا هذا أفضل من hash-only؟

Hash-only يمنع التحليل الخاطئ لكنه قد يحول replay لاحق إلى فشل مهمة.

Source promotion يفصل:
- **Staging/upload capability**
- **Canonical processing source**

لذلك إعادة الكتابة إلى staging بعد finalize لا تغير المصدر الذي ستعالجه المهمة.

## Concurrency

إذا حدث finalize متزامن:

- نفس bytes ينتج عنها نفس content-addressed path.
- `upsert:false` يمنع overwrite.
- عند وجود object مسبقًا يتم التحقق من SHA.
- CAS يثبت SHA والمسار معًا.
- العملية التي تخسر CAS تعيد قراءة **البصمة والمسار معًا** قبل الاستمرار.

## Legacy promotion

إذا كان مستند قد ثُبت SHA له سابقًا لكن `storage_path` ما زال يشير إلى staging، فإن finalize لاحقًا يستطيع ترقيته إلى canonical path بشرط تطابق bytes مع البصمة المثبتة.

إذا كانت bytes قد تغيرت بالفعل، يفشل مغلقًا ولا يحاول إعادة اعتمادها.

## حدود الضمان

هذا لا يجعل Supabase Storage نفسه WORM أمام service-role أو مشغل البنية التحتية. الضمان المقصود هنا أضيق وأكثر عملية:

> signed upload capability الصادرة للمتصفح لا تستطيع تعديل canonical source بعد promotion لأنها موقعة لمسار مختلف.

وتبقى طبقات `source_sha256` في Worker وexport/deep review دفاعًا إضافيًا حتى على canonical object.

## Benchmark

`FSP-001..FSP-012` تتحقق من:

- content-addressed path.
- server-side no-upsert promotion.
- collision integrity verification.
- promote-before-pin-before-queue ordering.
- atomic hash + path CAS.
- concurrent hash/path recheck.
- legacy pinned-source promotion.
- canonical object existence before queue.
- HTTP 409 integrity contract.
- signed-token path isolation model.
- deterministic content addressing.
- Worker canonical pointer + hash guard.
