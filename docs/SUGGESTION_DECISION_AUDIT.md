# Suggestion Decision Scope & Audit Trail V1

## المشكلة

منذ Migration 0023 أصبحت هوية الاقتراح الحتمية:

> `(version_id, client_suggestion_id)`

وهذا صحيح لأن الاقتراح نفسه قد يظهر في أكثر من نسخة أو أكثر من مستند.

لكن endpoint القديم كان:

- يصرح الوصول بواسطة `client_suggestion_id` وحده.
- ويحدث `suggestions.status` بواسطة `client_suggestion_id` وحده.

أي أن واجهة القرار لم تكن متوافقة مع نطاق الهوية الذي اعتمدته قاعدة البيانات.

## العقد الجديد

كل قرار مراجعة يُعرّف بـ:

- `documentId`
- `versionNo`
- `clientSuggestionId`
- `ownerId`
- `decision`

ولا يقبل القرار إلا إذا كانت Version المطلوبة هي **أحدث ready version** للمستند.

إذا ظهرت نسخة أحدث أثناء بقاء المحرر مفتوحًا:

- HTTP 409
- `VERSION_CHANGED`

ولا تُغيّر الواجهة النص المحلي أو حالة الملاحظة قبل نجاح الحفظ.

## Atomic Decision RPC

Migration 0027 تضيف:

`record_suggestion_decision(...)`

وتنفذ داخل transaction PostgreSQL واحدة:

1. التحقق من مالك المستند.
2. تحديد Version المطلوبة.
3. التحقق أنها أحدث ready version.
4. تحديد الاقتراح داخل Version نفسها.
5. `FOR UPDATE` على صف الاقتراح.
6. تحديث status للصف المحدد بالـUUID الحقيقي.
7. إدخال Audit Snapshot.

الـRPC:

- `SECURITY DEFINER`
- Search path ثابت.
- execute مسموح لـ`service_role` فقط.
- مسحوب من `public / anon / authenticated`.

## Audit Snapshot

كل قرار يكتب صفًا في `suggestion_decisions` يحتوي:

- document/version/suggestion IDs.
- deterministic client suggestion ID.
- owner.
- القرار.
- الحالة السابقة.
- وقت القرار.
- Snapshot من:
  - category.
  - title.
  - explanation.
  - original_text.
  - replacement_text.
  - confidence.
  - source_engine.
  - evidence.
  - status_before.

وبذلك يبقى ما وافق عليه المستخدم أو رفضه قابلًا للمراجعة حتى لو تغيرت بيانات الاقتراح لاحقًا.

## الخصوصية والحذف

السجل يتبع المستند والنسخة عبر Foreign Keys مع `ON DELETE CASCADE`، لذلك لا يعطل Secure Deletion.

المستخدم الموثق يستطيع قراءة Audit الخاص بمستنداته عبر RLS، ولا يملك سياسات insert/update/delete مباشرة. الكتابة تتم فقط من Server RPC.

## Database Verification

`supabase/tests/suggestion_decision_scope.sql` يثبت فعليًا أن:

- قرار نسخة قديمة يُرفض.
- نفس `client_suggestion_id` في نسخ مختلفة لا يسبب تحديثًا عابرًا للنسخ.
- نفس ID لدى مستخدم آخر لا يتأثر.
- Snapshot يُكتب.
- owner آخر لا يستطيع استهداف المستند.
- authenticated لا يستطيع تنفيذ RPC المميزة مباشرة.

## Benchmark

`DEC-001..DEC-014` تحمي عقد التطبيق، الصلاحيات، الـAPI والواجهة بالإضافة إلى اختبار PostgreSQL الحقيقي.
