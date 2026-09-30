# Document Fidelity & Round-Trip Safety V1

## الهدف

ضمان أن تعديل نَضِيد لنص DOCX لا يفسد أي جزء غير مستهدف من المستند.

القاعدة الحاكمة: **التعديل النصي المسموح يجب أن يغير النص المقصود فقط، وأن تبقى بقية الحزمة والبنية والعلاقات والتنسيقات ثابتة.**

## Fidelity Verifier

أضيف `verify_docx_fidelity()` كحاجز fail-closed بعد تطبيق أي Patch.

يتحقق من:

- سلامة حزمة DOCX كملف ZIP.
- بقاء قائمة Package Parts نفسها.
- بقاء Relationships نفسها.
- بقاء Content Types نفسها.
- بقاء الأجزاء غير المستهدفة كما هي دلاليًا أو ثنائيًا حسب نوعها.
- عدم تغير Styles / Numbering / Settings / Themes.
- عدم تغير Headers / Footers / Notes / Custom XML / Embedded payloads.
- بقاء Media binaries كما هي byte-for-byte.
- بقاء البنية غير النصية داخل `word/document.xml`.
- عدم تغير Node identity.
- أن التغييرات النصية مساوية تمامًا للـPatches المصرح بها فقط.

إذا فشل أي فحص، يرفض `/v1/apply/docx` الإخراج برمز:
`DOCUMENT_FIDELITY_REJECTED`.

## Safe Run Editing

تم تقوية محرر DOCX بحيث لا يعيد بناء الـRun كاملًا دون حاجة.

أصبح التعديل:

- يحافظ على `w:rPr` وتنسيق الـRun.
- يحافظ على عقد `w:t` بدل تسطيح البنية.
- يرفض التعديل إذا كان المدى يمر عبر Tabs / Breaks / Drawings / Fields أو Run مركب غير آمن.
- يدعم التصحيح عبر أكثر من Run مع الحفاظ على خصائص كل Run.
- يطبق Exact Offsets.
- يصحح إزاحة الـOffset عند وجود مسافات بادئة لأن Parser يعمل على النص بعد `strip()`.
- يبقي الملف byte-identical إذا لم توجد Patches أو إذا كانت جميعها Skipped.

## Benchmark V1

24 حالة تغطي:

1. فقرة عادية.
2. Bold surrounding run.
3. Italic / underline / font / size.
4. Heading style.
5. Table cell.
6. Merged table cells.
7. Numbered list.
8. Bullet list.
9. Image relationship + media binary.
10. Hyperlink relationship.
11. Header / footer.
12. Page margins + orientation.
13. Multiple sections.
14. Tabs + line breaks.
15. Bookmark.
16. Leading whitespace + exact offset.
17. Repeated exact source spans.
18. Cross-run same formatting.
19. Cross-run mixed formatting.
20. Unsafe special-run span must fail closed.
21. No-patch byte identity.
22. Second-round byte identity.
23. Combined rich document.
24. Target-run formatting preservation.

## المسار الفعلي

التشغيل الأول:
- Fidelity Benchmark: **23/24 = 95.8%**
- الحالة الوحيدة: `FID-017`.

التحليل أظهر أن سبب الفشل لم يكن فساد DOCX، بل فجوة لغوية: الصيغة المتصلة `وهاذا` لم تكن تُلتقط بينما `هاذا` المستقلة تُلتقط.

تم:
- إضافة قاعدة `orthography.hatha_prefixed` للصيغ المتصلة الشائعة مثل `وهاذا → وهذا`.
- إضافة Regression Guard دائم: `LANG-021`.

## النتيجة النهائية

- Document Fidelity & Round-Trip Safety V1: **24/24 = 100%**
- Core Quality Benchmark: **150/150 = 100%**
- Mutation Benchmark V1: **53/53 = 100%**
- Consistency Benchmark V1: **28/28 = 100%**
- Evidence Benchmark V1: **12/12 = 100%**
- Confidence & Severity V1: **18/18 = 100%**
- Review Action & Auto-Apply V1: **20/20 = 100%**
- Review Loop & Idempotence V1: **20/20 = 100%**

هذه نتائج اختبارات هندسية محددة وليست Human Precision/Recall.

## قاعدة الإصدار

أي مسار تعديل DOCX يجب أن يحقق جميع ما يلي قبل التسليم:

1. Exact source span.
2. Meaning Lock PASS عند الحاجة.
3. Patch application complete.
4. Fidelity verifier PASS.
5. No unexpected text change.
6. No package-part loss.
7. No relationship/content-type drift.
8. No media mutation.
9. No non-text document-structure mutation.
10. No formatting flattening داخل الـRuns.
