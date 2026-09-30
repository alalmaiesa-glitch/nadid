# Visual Layout & Rendering Regression V1

## الهدف

إكمال طبقة DOCX Fidelity باختبار **المظهر الفعلي بعد الرندر**، لا الاكتفاء ببنية ملف Word الداخلية.

تعمل V1 كالتالي:

`DOCX before → LibreOffice Writer → PDF → Rendered comparison`

ثم:

`Nadid safe edit → DOCX after → LibreOffice Writer → PDF → Rendered comparison`

وبذلك يمكن اكتشاف انزياحات لا تظهر من XML وحده، مثل:
- تغير عدد الصفحات.
- تغير مقاس/اتجاه الصفحة.
- تحرك عناصر ثابتة بعد التصحيح.
- تحرك صورة أو جدول.
- تغير كسر الصفحة.
- تغير توزيع صفحة قريبة من الامتلاء.
- اختلاف مرئي واسع ناتج عن reflow غير متوقع.

## Renderer

الـCI يستخدم:
- LibreOffice Writer headless.
- Writer PDF export.
- PyMuPDF لتحليل صفحات PDF.
- Pillow للمقارنة البصرية raster.

لا تعتمد هذه الطبقة على Screenshot يدوي.

## Visual Guards

لكل حالة مناسبة يتم فحص:

1. Page count.
2. Page width / height.
3. Raster changed-pixel ratio.
4. مواضع Anchors ثابتة وغير مستهدفة.
5. الصفحة التي يظهر فيها كل Anchor.
6. Image count + image bounding boxes.
7. Vector drawing geometry للجداول/الحدود عند الحاجة.
8. Explicit page breaks.
9. Sections / landscape rendering.
10. Second-round visual idempotence.

### Raster threshold

V1 لا تطلب Pixel Identity عند وجود تصحيح نصي؛ لأن تغيير حرف مقصود سيغيّر pixels فعلًا.

بدلًا من ذلك تستخدم حدًا محافظًا لنسبة البكسلات المتغيرة:
- Default: 3.5%.
- Rich / near-boundary fixtures: حتى 5%.
- No-op / second idempotent round: 0%.

وتعمل هذه المقارنة إلى جانب Structural Fidelity، وليست بديلًا عنه.

## Benchmark V1

20 حالة Rendering فعلية:

- RTL paragraph.
- Heading + body.
- Table Grid.
- Merged table.
- Numbered list.
- Bullet list.
- Image position.
- Image + caption.
- Header / footer.
- Landscape section.
- Explicit page break.
- Multiple sections.
- Near-page-boundary layout.
- Mixed run formatting.
- Cross-run correction.
- Repeated corrections.
- Arabic + URL / hyperlink.
- Combined rich document.
- Second-round visual identity.
- No-op visual identity.

## مسار الاختبار

التشغيل الأول:
- **19/20 = 95%**
- `VIS-017` لم ينفذ تعديلًا تلقائيًا لأن Fixture جمع هدف التصحيح داخل نفس سياق رابط محمي، فتعامل Action Policy معه بتحفظ.

هذه لم تكن مشكلة Rendering ولا فقدانًا في Fidelity. تم تعديل Fixture ليختبر شيئين بصورة مستقلة:
- تصحيح لغوي آمن في فقرة عربية.
- بقاء URL/Hyperlink ثابتًا في فقرة مرجعية مستقلة.

بعد تصحيح تصميم الاختبار اجتازت الطبقة كاملة.

## النتيجة النهائية

- Visual Layout & Rendering Regression V1: **20/20 = 100%**
- Core Quality Benchmark: **150/150 = 100%**
- Mutation Benchmark V1: **53/53 = 100%**
- Consistency Benchmark V1: **28/28 = 100%**
- Evidence Benchmark V1: **12/12 = 100%**
- Confidence & Severity V1: **18/18 = 100%**
- Review Action & Auto-Apply V1: **20/20 = 100%**
- Review Loop & Idempotence V1: **20/20 = 100%**
- Document Fidelity & Round-Trip Safety V1: **24/24 = 100%**

هذه نسب اجتياز Fixtures هندسية في بيئة Renderer محددة، وليست ضمانًا لكل إصدار من Microsoft Word أو Human Precision/Recall.

## حدود V1

- الـRenderer المرجعي في CI هو LibreOffice، وليس Microsoft Word.
- لا تدعي V1 Pixel-Perfect تطابقًا لكل محررات DOCX.
- المقارنة البصرية تكشف الانزياحات الكبيرة/غير المتوقعة وتعمل مع Package Fidelity.
- مستندات Word ذات ميزات متخصصة جدًا مثل SmartArt المعقد وOLE وTrack Changes المتقدم تحتاج Corpus مرئيًا خاصًا لاحقًا.

## قاعدة الإصدار

أي تغيير في DOCX patching يجب أن يحافظ على:
1. Document Fidelity PASS.
2. Page count / geometry.
3. Stable anchor locations ضمن tolerance.
4. Image/vector geometry عند وجودها.
5. Visual difference تحت الحد المعتمد.
6. Explicit page/section behavior.
7. Zero visual change في no-op وsecond-idempotent round.
