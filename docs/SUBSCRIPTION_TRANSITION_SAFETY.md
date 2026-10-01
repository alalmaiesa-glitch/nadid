# Subscription State & Entitlement Transition Safety V1

## الهدف

منع أي اشتراك ناقص أو منتهي أو متعثر من منح مزايا أو حصة أحرف مدفوعة بالخطأ.

## القاعدة

الخطة المدفوعة لا تصبح Effective إلا إذا:

- status = active
- current_period_start غير فارغ
- current_period_end غير فارغ
- البداية <= الوقت الحالي
- النهاية > الوقت الحالي
- النهاية > البداية
- billing plan نفسه active

أي حالة أخرى تعود إلى Free.

## الحالات التي لا تمنح مزايا مدفوعة

- past_due
- cancelled
- expired
- active بفترة منتهية
- active بفترة مستقبلية لم تبدأ
- active بلا بداية
- active بلا نهاية
- فترة معكوسة أو صفرية

## توحيد المصدر

تم تحديث Character Quota كي لا يحسب الخطة المدفوعة باستعلام مستقل. أصبح يقرأ monthly_characters من get_effective_billing_plan نفسها.

بهذا لا يمكن أن تكون المزايا Free بينما حصة الأحرف Pro بسبب اختلاف قواعد التحقق.

## الاختبارات

SUB-001..SUB-008 تحرس شروط الفترة، fallback المجاني، توحيد quota، وصلاحيات RPC.

إعادة بناء Supabase الكاملة في CI تتحقق كذلك من أن migration الجديدة صالحة فوق كل migrations السابقة.
