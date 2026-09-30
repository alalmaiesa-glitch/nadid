# Adversarial OOXML & Resource Exhaustion / Security Fuzzing V1

## الهدف

نَضِيد يقرأ ملفات يرفعها المستخدم، لذلك يجب اعتبار DOCX حزمة OOXML غير موثوقة حتى تثبت سلامتها.

هذه الطبقة لا تحاول استغلال النظام، بل تبني **حواجز دفاعية قابلة للقياس** ضد أكثر أسطح المخاطر ارتباطًا بمسار نَضِيد:

- ZIP/package resource exhaustion.
- XML complexity bombs.
- DTD / Entity expansion.
- Macro-enabled payloads المتنكرة بامتداد DOCX.
- OLE / ActiveX / embedded active content.
- External Relationships التي قد تحوّل المستند إلى قناة تحميل خارجي.
- malformed package mutation fuzzing.
- regressions التي تعيد 5xx بدل الرفض المنضبط.

## السياسة

### Active content

نَضِيد محرر ومراجع نصوص، وليس بيئة تنفيذ Office.

لذلك V1 ترفض:

- VBA project/signature parts.
- ActiveX.
- OLE/embedded objects.
- controls.
- customUI.
- macro-enabled content types.
- العلاقات الخاصة بـ OLE / controls / attached templates / VBA.

هذا قرار Fail-Closed مقصود.

### External relationships

لا يحتاج محرك نَضِيد إلى جلب موارد خارجية أثناء تحليل DOCX.

لذلك:

- يسمح فقط بعلاقة Hyperlink خارجية.
- Hyperlink المسموح: `http` و`https` و`mailto`.
- External image/template/OLE وغيرها: رفض.
- `file:` و`ftp:` و`javascript:`: رفض.

بهذا تبقى الروابط الطبيعية في المستندات صالحة، دون السماح بتحويل التحليل إلى fetch غير مقصود أو الحفاظ على بروتوكولات خطرة.

## XML resource guards

V1 تضيف حدودًا مستقلة لطبقة XML:

- أقصى XML part: 32 MiB.
- إجمالي XML داخل الحزمة: 96 MiB.
- أقصى عمق XML: 128.
- أقصى عدد عناصر XML: 1,000,000.
- أقصى Attributes على عنصر واحد: 256.
- DTD/Entity/External Entity: مرفوضة.

هذه الحدود منفصلة عن حدود ZIP العامة، لأن XML يتحول إلى بنى شجرية في الذاكرة وقد تكون كلفته أكبر من حجمه المضغوط.

## Benchmark

32 حالة ثابتة `SEC-001` إلى `SEC-032` تغطي:

- DOCX طبيعي وDeep Analyze.
- HTTPS/Mailto hyperlinks.
- VBA / ActiveX / OLE / Custom UI.
- Macro content types.
- External template/image relationships.
- Unsafe hyperlink schemes.
- DTD / Entity.
- XML depth/elements/attributes.
- XML entry/aggregate sizes.
- upload/uncompressed/single-entry/compression-ratio/entry-count limits.
- duplicate/path traversal baselines.
- malformed relationship/content-type XML.
- internal OLE relationship.

## Bounded resource testing

لا تُنشئ CI قنبلة ZIP فعلية بمئات الميجابايت أو XML bomb حقيقية.

بدلًا من ذلك يتم خفض Threshold مؤقتًا داخل Benchmark، ثم استخدام Payload صغير يثبت أن الحارس يعمل. هذا يختبر المنطق نفسه دون تعريض Runner أو المطور إلى استنزاف حقيقي.

## Deterministic mutation fuzzing

بعد الحالات الثابتة، يأخذ V1 DOCX سليمًا ويولّد 24 Mutation بحبة ثابتة:

- truncations متعددة.
- single/multi-byte bit flips.

العقد هنا ليس أن كل Mutation يجب أن ترفض؛ بعض التغييرات قد تصيب bytes غير مؤثرة.

العقد هو:

- لا 5xx.
- لا تعليق طويل.
- الاستجابة تبقى ضمن الحالات المعروفة.
- التشغيل قابل لإعادة الإنتاج عبر Seed ثابت.

## حدود V1

V1 ليست Malware Scanner ولا Sandbox لملفات Office، ولا تدعي كشف كل عينة خبيثة ممكنة.

ولا تستبدل:

- فحص AV/Content scanning على مستوى البنية التحتية.
- sandboxing للمعالجة عند الحاجة.
- rate limiting / quotas.
- process-level memory/CPU limits.
- fuzzers native طويلة التشغيل مثل AFL/libFuzzer.

إنها طبقة Regression دفاعية داخل CI، هدفها منع إعادة فتح ثغرات واضحة في مسار OOXML.
