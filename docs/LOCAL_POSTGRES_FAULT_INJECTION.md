# Local Supabase/PostgreSQL Fault Injection V1

## الهدف

تنقل هذه الطبقة اختبار Idempotency من فحص منطق Worker فقط إلى PostgreSQL حقيقي مع migrations نَضِيد الفعلية.

تعمل داخل GitHub Actions على Supabase محلي معزول، ولا تتصل بقاعدة الإنتاج ولا تستخدم بيانات مستخدمين.

## المسار

1. تشغيل Supabase CLI محليًا داخل CI.
2. تطبيق سلسلة migrations كاملة عبر `supabase db reset --local`.
3. تشغيل SQL fault-injection مباشر على PostgreSQL المحلي.
4. إيقاف البيئة المحلية دائمًا بعد الاختبار.

## الحالات V1

- **DBF-001**: نفس `client_suggestion_id` مسموح في نسختين مختلفتين.
- **DBF-002**: تكرار `client_suggestion_id` داخل النسخة نفسها يُرفض بقيد unique.
- **DBF-003**: حذف Version جزئية يزيل بالـFK cascade كل Deep Artifacts التابعة.
- **DBF-004**: transaction يتم rollback لها لا تترك Version أو child rows جزئية.
- **DBF-005**: clear-then-rebuild retry يعيد deterministic row واحدة فقط.

## لماذا هذه الطبقة مهمة؟

طبقة WID السابقة أثبتت ترتيب Worker وعقود الـidempotency في الكود. هذه الطبقة تثبت أن PostgreSQL نفسه يطبق الافتراضات التي يعتمد عليها Worker:

- constraints الفعلية.
- cascade الفعلي.
- rollback الفعلي.
- migration chain من قاعدة فارغة.
- version-scoped deterministic identity.

## العزل

الاختبار يستخدم UUIDs ثابتة داخل قاعدة CI محلية فقط. لا يتصل بمشروع Supabase مستضاف.

## حدود V1

- لا يقتل Worker process بين كل statement وآخر.
- لا يختبر انقطاع الشبكة الحقيقي بين Worker وSupabase.
- لا يحقن disk-full أو Postgres restart.
- لا يختبر قاعدة الإنتاج.

هذه تبقى Fault Injection V2 لاحقًا.
